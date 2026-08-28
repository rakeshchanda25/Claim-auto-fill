import functools
import logging
import random
import threading
import time
from faker import Faker
try:
    from andromeda.tools import tool
except Exception:
    def tool(func):
        return func

logger = logging.getLogger(__name__)


def _summarize(value, maxlen=120):
    """Short, log-safe representation of a tool argument/return value -
    never dumps a full document's bytes or a huge dict into the log."""
    if isinstance(value, bytes):
        return f"<bytes: {len(value)}>"
    if isinstance(value, dict):
        return f"<dict: {len(value)} keys>"
    if isinstance(value, (list, tuple)):
        return f"<{type(value).__name__}: {len(value)} items>"
    r = repr(value)
    return r if len(r) <= maxlen else r[: maxlen] + f"...<+{len(r) - maxlen} chars>"


def _log_exceptions(func):
    """Logs every tool call's entry (args), success (result), and full
    traceback on failure - this is the only place a real traceback survives:
    andromeda's ToolErrorHandlerMiddleware (andromeda/core/middleware/
    tooling.py) catches every tool exception and reduces it to just
    f"Tool error: ... ({exc})" before it reaches the model or the console -
    for something like IndexError that's literally "list index out of
    range" with zero file/line context."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        parts = [_summarize(a) for a in args] + [f"{k}={_summarize(v)}" for k, v in kwargs.items()]
        logger.info(f"tool call -> {func.__name__}({', '.join(parts)})")
        t0 = time.monotonic()
        try:
            result = func(*args, **kwargs)
        except Exception:
            logger.exception(f"tool '{func.__name__}' raised after {time.monotonic() - t0:.2f}s")
            raise
        logger.info(f"tool ok    <- {func.__name__} ({time.monotonic() - t0:.2f}s) = {_summarize(result)}")
        return result
    return wrapper

from renderers.synthetic_data import build_synthetic_data, resolve_doc_type
from renderers.html_renderer import render_html_to_pdf
from renderers.form_filler import (
    enumerate_pdf_fields,
    fill_pdf_form,
    fill_widgets_precise,
    fit_cell,
    flow,
    read_back_widgets,
)
from renderers.form_structure import build_draft, inventory
from renderers.docx_parser import extract_docx_layout
from renderers.docx_structure import build_draft as build_docx_draft
from renderers.docx_filler import fill_docx_controls, read_back_docx_controls
from .packets import PACKET_REGISTRY


_fake = Faker()


# =============================================================================
# Reference-document staging.
#
# A tool-calling LLM emits its arguments as text/JSON tokens - it cannot
# transcribe a real PDF/docx/image's raw bytes as a tool-call argument (a
# claim form is ~100-300KB of binary data; there is no way for the model to
# "type out" that content correctly). The fill/recreate tools below used to
# declare a `pdf_bytes`/`docx_bytes`/`file_bytes` parameter anyway, which the
# model could never satisfy - it would silently fail or improvise, which is
# the actual root cause of "fill" mode producing a brand-new generated
# document instead of touching the uploaded one at all.
#
# The fix: the uploaded file's real bytes are staged here BEFORE the agent
# runs (see agent_factory.run_with_reference), and the tools read them from
# here instead of taking them as an LLM-supplied argument. Guarded by a lock
# because the agent instance is shared/reused across requests (see
# agent_factory.get_shared_agent) - run_with_reference holds this lock for
# the whole run so two requests' reference documents can never cross.
# =============================================================================

reference_lock = threading.Lock()
_reference_bytes: bytes | None = None


def set_reference_document(data: bytes | None) -> None:
    global _reference_bytes
    _reference_bytes = data


def _require_reference_bytes() -> bytes:
    if _reference_bytes is None:
        raise ValueError(
            "No reference document is staged for this request. The user must upload a "
            "reference file for fill/recreate mode - there is nothing to inspect or fill."
        )
    return _reference_bytes


# =============================================================================
# Output-artifact staging.
#
# The same "an LLM cannot carry raw bytes through its own text" problem that
# reference-document staging fixes on the way IN also applies on the way
# OUT: render_document_to_pdf/fill_pdf_widgets/fill_docx_form_controls used
# to return the finished document as raw `bytes`. LangChain's tool-calling
# layer stringifies a non-string tool return with plain str() when it builds
# the ToolMessage - for bytes that produces exactly "b'%PDF-1.3\\n...'", the
# garbled text a user actually saw appear as the agent's "response". Even if
# it hadn't been mangled, the prompt was then asking the model to read that
# blob back out of its own context and hand-transcribe it as a base64 string
# in its final answer - tens to hundreds of thousands of characters, which is
# both why generation was slow (huge, pointless output) and why it broke down
# entirely on anything past a trivial document.
#
# The fix mirrors reference-document staging: a tool that produces a
# document stages the real bytes here and returns a small status object
# instead. agent_factory.run_with_reference reads the staged bytes directly
# once the run finishes - the actual file content never has to pass through
# the model's generated text at all.
# =============================================================================

_staged_artifact_bytes: bytes | None = None
_staged_artifact_kind: str | None = None


def stage_artifact(data: bytes, kind: str) -> dict:
    global _staged_artifact_bytes, _staged_artifact_kind
    _staged_artifact_bytes = data
    _staged_artifact_kind = kind
    return {"status": "staged", "kind": kind, "size_bytes": len(data)}


def get_staged_artifact() -> tuple[bytes | None, str | None]:
    return _staged_artifact_bytes, _staged_artifact_kind


def clear_staged_artifact() -> None:
    global _staged_artifact_bytes, _staged_artifact_kind
    _staged_artifact_bytes = None
    _staged_artifact_kind = None


def _require_staged_artifact() -> bytes:
    data, _ = get_staged_artifact()
    if data is None:
        raise ValueError("No document has been staged yet in this request.")
    return data


# Packet mode needs several documents to survive one request, but the single
# staging slot above is overwritten by each render_document_to_pdf call - by
# the time a packet's last component renders, every earlier one is already
# gone. This is a second, list-shaped staging slot that ACCUMULATES instead
# of overwriting: stage_packet_component moves whatever render_document_to_pdf
# just staged into this list (under a label) and clears the single slot so
# the next component can use it. Same non-negotiable rule as the single slot -
# the bytes never pass through the model's own text.
_staged_packet: list[dict] | None = None


def get_staged_packet() -> list[dict] | None:
    return _staged_packet


def clear_staged_packet() -> None:
    global _staged_packet
    _staged_packet = None


# =============================================================================
# Document-DATA staging.
#
# Same principle as the artifact staging above, applied to the thing that
# actually dominates wall-clock time. The tools used to return the full data
# dict, which the model then had to re-emit verbatim as an argument to
# render_document_to_pdf(data=...) - ~670 OUTPUT tokens per document (measured
# across the six largest doc types; acord-25 is ~890). Output tokens are
# generated sequentially and are by far the slowest part of local inference,
# so that echo cost tens of seconds per document and risked corrupting a field
# every time. It also bought nothing: the data came from a deterministic
# generator the model had just called.
#
# Now the generator stages the dict here and returns only a compact summary
# (field NAMES, no values). Field names are cheap - they arrive as input
# tokens, which prefill in parallel - and are all the model needs to reason
# about coverage or target a revision. render_document_to_pdf reads the
# staged dict directly, so a document's data never crosses the model's text.
# =============================================================================

_staged_doc_data: dict | None = None


def get_staged_doc_data() -> dict | None:
    return _staged_doc_data


def clear_staged_doc_data() -> None:
    global _staged_doc_data
    _staged_doc_data = None


def _stage_doc_data(data: dict, doc_type: str, scenario: str) -> dict:
    global _staged_doc_data
    _staged_doc_data = data
    return {
        "status": "staged",
        "doc_type": doc_type,
        "scenario": scenario,
        "field_count": len(data),
        "fields": sorted(k for k in data if not k.startswith("_")),
    }


def _require_staged_doc_data() -> dict:
    if _staged_doc_data is None:
        raise ValueError(
            "No document data has been staged yet - call generate_synthetic_data (or "
            "recreate_document_data) before rendering."
        )
    return _staged_doc_data


def _overlay_values(dst: dict, src: dict, path: str = "", unmapped: list | None = None) -> list:
    """Overlays `src` onto `dst` in place, merging nested dicts key-by-key so a
    partial address overrides only the keys supplied. Returns the dotted paths
    that had no counterpart in `dst` - reported rather than silently dropped,
    since a mistyped key would otherwise leave the document quietly carrying
    generated data where a caller-supplied value belonged."""
    if unmapped is None:
        unmapped = []
    for key, value in (src or {}).items():
        full = f"{path}.{key}" if path else key
        if key not in dst:
            unmapped.append(full)
        elif isinstance(value, dict) and isinstance(dst[key], dict):
            _overlay_values(dst[key], value, full, unmapped)
        else:
            dst[key] = value
    return unmapped




@tool
@_log_exceptions
def generate_synthetic_data(doc_type: str, scenario: str = "general", seed: int = None) -> dict:
    """Generate synthetic insurance claim data for the given document type and
    scenario, and stage it for rendering.

    Returns a SUMMARY (the field names), not the data itself - the data is
    held server-side and render_document_to_pdf picks it up automatically, so
    you never have to repeat it back. To change specific values before
    rendering, call revise_document_data with just the fields you want to
    change; do not try to restate the whole document."""
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)
    data = build_synthetic_data(doc_type, scenario)
    return _stage_doc_data(data, doc_type, scenario)


@tool
@_log_exceptions
def revise_document_data(changes: dict) -> dict:
    """Change specific fields of the currently staged document data, leaving
    everything else as generated. Pass ONLY the fields you are changing, e.g.
    {"patient_name": "...", "address": {"city": "..."}} - nested dicts merge
    key-by-key. Use this to apply user-supplied values or to fill a gap
    validate_document_structure reported. Field names that do not exist for
    this document come back under "unmapped_keys" so you can correct them."""
    data = _require_staged_doc_data()
    unmapped = _overlay_values(data, changes)
    if unmapped:
        logger.warning(f"revise_document_data: {len(unmapped)} unmapped key(s): {unmapped}")
    return {
        "status": "revised",
        "changed": [k for k in (changes or {}) if k not in unmapped],
        "unmapped_keys": unmapped,
    }


@tool
@_log_exceptions
def render_document_to_pdf(template_name: str, data: dict = None) -> dict:
    """Render the staged document data into the final PDF using the named
    Jinja2 HTML template.

    Do NOT pass `data` - it defaults to whatever generate_synthetic_data or
    recreate_document_data staged, so the document's fields never have to be
    repeated back through your output. (It is accepted only for the rare case
    of rendering a dict that was never staged.)

    Returns a small status object, NOT the PDF bytes - a tool-calling model
    cannot carry binary content through its own generated text. The rendered
    PDF is staged automatically and attached to the response once you
    finish; just confirm success in your final answer."""
    pdf_bytes = render_html_to_pdf(template_name, data if data is not None else _require_staged_doc_data())
    return stage_artifact(pdf_bytes, "pdf")


@tool
@_log_exceptions
def fill_pdf_form_tool(pdf_bytes: bytes, field_map: dict, flatten: bool = True) -> bytes:
    """Fill AcroForm fields in a PDF and return the result as bytes."""
    return fill_pdf_form(pdf_bytes, field_map, flatten=flatten)


@tool
@_log_exceptions
def get_pdf_form_fields(pdf_bytes: bytes) -> dict:
    """Return a mapping of AcroForm field names to their current values in the PDF.
    For a genuine form-FILLING task, prefer inspect_pdf_form_structure instead -
    this only gives raw field names with no label/geometry, which is not enough
    signal to map a name like "Text Field0" to what it actually asks for."""
    return enumerate_pdf_fields(pdf_bytes)


# =============================================================================
# Dynamic form-fill tools (skills/dynamic-form-fill) - template-agnostic.
# Nothing here hardcodes any field name, label, or layout for any specific
# form. Structure detection is exactly computable (geometry), so it is a
# tool, not something the agent guesses; meaning (what a field actually
# represents, and what value belongs in it) is the agent's job.
# =============================================================================

@tool
@_log_exceptions
def inspect_pdf_form_structure() -> dict:
    """Analyze the uploaded reference AcroForm PDF and return its structural
    draft: every widget's geometry, its harvested nearby label text, detected
    section headings, detected repeating grids (tables), detected Yes/No
    checkbox pairs, and detected multi-widget narrative runs (a single answer
    spanning several stacked one-line boxes). This is purely geometric - no
    meaning is assigned to anything yet. Operates on the file the user
    uploaded for this request - takes no arguments, there is nothing to pass.
    ALWAYS call this first for a form-filling task; never infer a widget's
    purpose from its raw internal name alone (e.g. "Text Field0" carries no
    information - the harvested label does). Raises if the PDF has no
    /AcroForm at all (a flat/scanned form needs a different strategy - see
    analyze_uploaded_reference)."""
    return build_draft(_require_reference_bytes())


@tool
@_log_exceptions
def inspect_region(page: int, bbox: list) -> dict:
    """Read ALL printed text inside one region of the uploaded reference PDF,
    including text that sits outside a widget's own harvested label. Use when
    a run/pair/grid's label came back empty or ambiguous and you need more of
    the surrounding page to decide what a field is asking for. `page` is
    1-based. `bbox` is [x0, y0, x1, y1] in PDF points using the SAME
    bottom-up coordinate space as inspect_pdf_form_structure's widget rects
    (a margin is added automatically so surrounding context is included).
    Returns the region's text - there is no image: you cannot see pictures,
    so asking for one would only waste your context."""
    import pymupdf

    doc = pymupdf.open(stream=_require_reference_bytes(), filetype="pdf")
    pg = doc[page - 1]
    page_h = pg.rect.height
    x0, y0, x1, y1 = bbox
    # widget/harvest coordinates are bottom-up; pymupdf is top-down - flip once, here.
    raw_clip = pymupdf.Rect(x0, page_h - y1, x1, page_h - y0)
    pad = 20
    clip = pymupdf.Rect(raw_clip.x0 - pad, raw_clip.y0 - pad, raw_clip.x1 + pad, raw_clip.y1 + pad) & pg.rect

    # This deliberately does NOT return a rendered image. It used to hand back
    # a base64 PNG, but a tool result reaches the model as plain text: even a
    # vision-capable model cannot see an image smuggled through a JSON string
    # field, so those thousands of base64 characters were pure context
    # poison. A real run spent 32 minutes and 38 messages after four such
    # calls and never produced an answer at all. The extracted text is the
    # part the model can actually use.
    return {
        "page": page,
        "region": [round(v, 1) for v in (clip.x0, clip.y0, clip.x1, clip.y1)],
        "text": pg.get_textbox(clip).strip(),
    }


@tool
@_log_exceptions
def flow_text_into_widgets(widget_names: list, text: str, base_font: float = 9.0) -> dict:
    """Deterministically wraps `text` across one detected run's widgets (in
    the uploaded reference PDF), in order, shrinking the font before ever
    truncating a word. Returns {"values": {...}, "fonts": {...}, "warnings":
    [...]} - merge these straight into fill_pdf_widgets' widget_values/
    widget_fonts. Use this for any multi-widget run, or any single widget
    where the text might not fit at the default size - font-fitting is
    exactly computable from widget geometry, so never guess a font size
    yourself."""
    widgets, _ = inventory(_require_reference_bytes())
    index = {w.name: w for w in widgets}
    ws = [index[n] for n in widget_names if n in index]
    if not ws:
        return {"values": {}, "fonts": {}, "warnings": [f"no matching widgets for {widget_names}"]}
    values, fonts, warns = flow(text, ws, base_font)
    return {"values": values, "fonts": fonts, "warnings": warns}


@tool
@_log_exceptions
def fit_grid_row(widget_names: list, cell_texts: list, base_font: float = 7.0) -> dict:
    """For one row of a detected grid in the uploaded reference PDF, computes
    ONE common font size that fits every cell in the row - never mix font
    sizes within a row, it is an obvious tell of a machine-filled form.
    `widget_names` and `cell_texts` must be the same length and in the same
    left-to-right column order. Returns {"values": {...}, "fonts": {...},
    "warnings": [...]}."""
    widgets, _ = inventory(_require_reference_bytes())
    index = {w.name: w for w in widgets}
    pairs = [(n, t) for n, t in zip(widget_names, cell_texts) if n in index]
    if not pairs:
        return {"values": {}, "fonts": {}, "warnings": [f"no matching widgets for {widget_names}"]}

    warns = []
    sizes = []
    for n, t in pairs:
        size, still_over = fit_cell(t, index[n], base_font)
        sizes.append(size)
        if still_over:
            warns.append(f"{n}: {t!r} still overflows at {size}pt")
    row_size = round(min(sizes), 1)
    return {
        "values": {n: t for n, t in pairs},
        "fonts": {n: row_size for n, _ in pairs},
        "warnings": warns,
    }


@tool
@_log_exceptions
def fill_pdf_widgets(widget_values: dict, widget_fonts: dict = None, watermark: str = None) -> dict:
    """Fill the uploaded reference PDF's AcroForm widgets by exact widget name
    with already-fitted text (from flow_text_into_widgets / fit_grid_row, or
    a short single-line value with no font override needed). Sets
    /NeedAppearances so real PDF viewers actually render the values (many
    otherwise show nothing despite the value being saved in the file).
    Returns a small status object, NOT the filled PDF bytes - a tool-calling
    model cannot carry a document's binary content through its own generated
    text. The filled PDF is staged automatically; call verify_pdf_fill next
    (it reads the staged result automatically too) - never report success
    without confirming the values actually took."""
    pdf_bytes = fill_widgets_precise(_require_reference_bytes(), widget_values, widget_fonts, watermark)
    return stage_artifact(pdf_bytes, "pdf")


@tool
@_log_exceptions
def verify_pdf_fill(expected_values: dict) -> dict:
    """Reads the just-filled PDF's (staged by fill_pdf_widgets) AcroForm
    values back out and diffs them against what was requested - no PDF
    argument, it reads the staged result automatically. Call this after
    every fill_pdf_widgets - a mismatch here means the fill silently did not
    take for that widget."""
    back = read_back_widgets(_require_staged_artifact())
    mismatches = {
        k: {"expected": v, "actual": back.get(k, "<absent>")}
        for k, v in expected_values.items()
        if back.get(k) != v
    }
    return {"ok": len(mismatches) == 0, "checked": len(expected_values), "mismatches": mismatches}


# =============================================================================
# Dynamic docx-fill tools (skills/dynamic-docx-fill) - template-agnostic,
# same discover/decide/fill/verify split as the PDF tools above, but for
# Word content-control forms (w:sdt) instead of AcroForm widgets. Docx has
# no fixed-box geometry (Word grows the paragraph to fit), so there is no
# docx equivalent of flow_text_into_widgets/fit_grid_row - nothing to fit.
# =============================================================================

@tool
@_log_exceptions
def inspect_docx_form_structure() -> dict:
    """Analyze the uploaded reference .docx's Word content controls and
    return its structural draft: every control's type (text/richText/date/
    checkbox/dropdown/combobox), its harvested context label (the control's
    own `alias` if the template author set one, else nearby paragraph/table-
    cell text), and - for dropdown/comboBox controls - the exact list of
    selectable choices. No meaning is assigned yet. Operates on the file the
    user uploaded for this request - takes no arguments, there is nothing to
    pass. ALWAYS call this first for a docx fill task; never infer a
    control's purpose from its raw `tag` alone. A docx with no content
    controls returns an empty controls list (0 = nothing to fill, not an
    error) - the doc likely needs a different strategy (see
    analyze_uploaded_reference)."""
    return build_docx_draft(_require_reference_bytes())


@tool
@_log_exceptions
def fill_docx_form_controls(
    values: dict = None,
    checks: dict = None,
    choices: dict = None,
) -> dict:
    """Fill the uploaded reference .docx's Word content controls by exact
    control name (from inspect_docx_form_structure). `values` is name->text
    for text/richText/date controls. `checks` is name->bool for checkbox
    controls - never assume a checkbox displays "X" when checked, the fill
    uses the control's own configured checked-state glyph and font.
    `choices` is name->displayText for dropdown/comboBox controls, and MUST
    be one of that control's own listItem displayText values (raises
    otherwise - never invent an option the template doesn't offer). Returns
    a small status object, NOT the filled docx bytes - a tool-calling model
    cannot carry a document's binary content through its own generated text.
    The filled docx is staged automatically; always call verify_docx_fill
    afterwards (it reads the staged result automatically too)."""
    docx_bytes = fill_docx_controls(_require_reference_bytes(), values, checks, choices)
    return stage_artifact(docx_bytes, "docx")


@tool
@_log_exceptions
def verify_docx_fill(expected_values: dict) -> dict:
    """Reads the just-filled docx's (staged by fill_docx_form_controls)
    content controls back out and diffs them against what was requested
    (expected_values maps name -> the text, or the bool for a checkbox, or
    the displayText for a dropdown/comboBox, that was written) - no docx
    argument, it reads the staged result automatically. Call this after
    every fill_docx_form_controls - a mismatch means the fill silently did
    not take for that control."""
    back = read_back_docx_controls(_require_staged_artifact())
    mismatches = {
        k: {"expected": v, "actual": back.get(k, "<absent>")}
        for k, v in expected_values.items()
        if back.get(k) != v
    }
    return {"ok": len(mismatches) == 0, "checked": len(expected_values), "mismatches": mismatches}


def analyze_reference_document(file_bytes: bytes, file_type: str) -> dict:
    """Analyze a reference document and return its detected structure and field layout.
    Supported file_type: pdf, jpg, jpeg, png, tiff, docx, doc.

    Plain function, not an @tool - used directly (with real bytes already in
    hand) by the synchronous /api/ai-analyze-reference preview endpoint,
    which has nothing to do with the agent/LLM. See
    analyze_uploaded_reference below for the agent-facing version.
    """
    file_type = file_type.lower().lstrip(".")

    if file_type in ("docx", "doc"):
        return extract_docx_layout(file_bytes)

    if file_type == "pdf":
        import pymupdf
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        result = {"pages": [], "file_type": "pdf"}
        for page_num in range(min(3, len(doc))):
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]
            text_blocks = []
            for b in blocks:
                if b.get("type") == 0:
                    for line in b.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            if text:
                                text_blocks.append({
                                    "text": text,
                                    "font_size": round(span.get("size", 10), 1),
                                    "bold": bool(span.get("flags", 0) & 2**4),
                                    "bbox": [round(v, 1) for v in span.get("bbox", [])],
                                })
            result["pages"].append({
                "page": page_num + 1,
                # Plain reading order, for actually READING the document's
                # values (recreate mode needs the claimant/policy/provider
                # values, not their coordinates). The positioned spans below
                # describe layout; they are a poor way to read prose.
                "text": page.get_text().strip(),
                "text_blocks": text_blocks[:60],
            })
        return result

    return {"file_type": file_type, "note": "image analysis requires vision-capable model"}


@tool
@_log_exceptions
def analyze_uploaded_reference(file_type: str) -> dict:
    """Analyze the reference document the user uploaded for this request and
    return its detected structure and field layout. `file_type` is the
    uploaded file's extension (pdf, jpg, jpeg, png, tiff, docx, doc) - the
    file's own bytes are supplied automatically, do not attempt to pass
    them."""
    return analyze_reference_document(_require_reference_bytes(), file_type)


@tool
@_log_exceptions
def recreate_document_data(doc_type: str, scenario: str, carried_values: dict) -> dict:
    """Build the data for a RECREATE-mode document and stage it for rendering.
    Returns a SUMMARY (field names), not the data - render_document_to_pdf
    picks the staged data up automatically, so never repeat it back.

    Recreate means: keep the uploaded reference document's own identity, but
    re-tell it as a DIFFERENT scenario. So this generates fresh synthetic data
    for the new `scenario` (diagnoses, procedures, dates, amounts, narrative -
    everything the scenario drives), then overlays `carried_values` on top:
    the real values you read out of the reference document and want preserved.

    `carried_values` is a plain dict of just the fields worth carrying over -
    typically the people and identifiers, e.g. patient_name, dob, mrn,
    insurance_id, policy_number, claim_number, physician_name, insurer_name,
    and address dicts. Do NOT carry scenario-driven content (diagnosis_codes,
    procedure_codes, line_items, narratives, totals) - letting those through
    would defeat the point, since re-telling the document under the new
    scenario is the whole job.

    Nested dicts merge key-by-key, so {"address": {"city": "Pune"}} overrides
    only the city and leaves street/state/zip intact. Keys that do not exist
    for this doc type cannot be carried and come back under "unmapped_keys"
    so you can retry them under their real names."""
    resolved = resolve_doc_type(doc_type)
    data = build_synthetic_data(resolved, scenario)
    unmapped = _overlay_values(data, carried_values or {})

    carried_ok = sum(1 for k in (carried_values or {}) if k not in unmapped)
    logger.info(
        f"recreate_document_data: doc_type={doc_type} scenario={scenario!r} - "
        f"carried {carried_ok}/{len(carried_values or {})} value(s) onto fresh {scenario!r} data"
    )
    if unmapped:
        logger.warning(f"recreate_document_data: {len(unmapped)} unmapped key(s): {unmapped}")

    summary = _stage_doc_data(data, doc_type, scenario)
    summary["carried_keys"] = carried_ok
    summary["unmapped_keys"] = unmapped
    return summary


# The claim-level facts that must be IDENTICAL across every document in one
# packet - the people, the identifiers, and the encounter it all describes.
# build_synthetic_data draws these fresh per call, so without pinning them a
# "Medical Claims Packet" came out as five documents about five different
# patients: worthless as IDP test data, since cross-document entity matching
# is the main thing such a packet exists to exercise.
_PACKET_SHARED_FIELDS = (
    # who the claim is about
    "patient_name", "dob", "gender", "address", "phone", "mrn",
    "insurance_id", "group_number",
    # who treated them
    "physician_name", "npi", "specialty", "dea", "hospital",
    # the claim and the encounter
    "insurer_name", "claim_number", "policy_number",
    "dos", "dos_from", "dos_to", "service_date",
)

_staged_packet_plan: list[dict] | None = None


def get_staged_packet_plan() -> list[dict] | None:
    return _staged_packet_plan


def clear_staged_packet_plan() -> None:
    global _staged_packet_plan
    _staged_packet_plan = None


@tool
@_log_exceptions
def build_packet(packet_name: str, scenario: str = "general", seed: int = None) -> dict:
    """Plan a named document packet: works out its components and generates
    each one's data, all sharing ONE claimant, provider, claim number and
    encounter date so the documents belong to the same claim.

    Returns only the component list (labels and template names) - the data
    itself is staged server-side. Follow this with render_packet() to produce
    every component; you never handle any component's data or bytes."""
    global _staged_packet_plan
    spec = PACKET_REGISTRY.get(packet_name)
    if not spec:
        raise ValueError(f"Unknown packet: {packet_name}. Available: {list(PACKET_REGISTRY.keys())}")

    components = sorted(spec["components"], key=lambda c: c["order"])
    if seed is not None:
        # One seed for the packet, NOT seed+order per component - varying it
        # per component is what guaranteed a different identity in each.
        Faker.seed(seed)
        random.seed(seed)

    # Establish the shared identity once, from the first component, then pin
    # it onto every other component's freshly generated scenario content.
    first = build_synthetic_data(components[0]["doc_type"], scenario)
    shared = {k: first[k] for k in _PACKET_SHARED_FIELDS if k in first}

    plan = []
    for comp in components:
        data = first if comp is components[0] else build_synthetic_data(comp["doc_type"], scenario)
        if data is not first:
            _overlay_values(data, shared)
        plan.append({
            "label": comp["label"],
            "doc_type": comp["doc_type"],
            "template_name": comp["doc_type"].replace("-", "_"),
            "data": data,
        })

    _staged_packet_plan = plan
    logger.info(
        f"build_packet: {packet_name} / {scenario!r} - {len(plan)} component(s) staged, "
        f"sharing claimant={shared.get('patient_name')!r} claim={shared.get('claim_number')!r}"
    )
    return {
        "packet": packet_name,
        "scenario": scenario,
        "component_count": len(plan),
        "components": [{k: c[k] for k in ("label", "doc_type", "template_name")} for c in plan],
        "shared_identity": {k: shared.get(k) for k in ("patient_name", "claim_number", "policy_number")},
    }


@tool
@_log_exceptions
def render_packet() -> dict:
    """Render every component build_packet staged, in order, and collect them
    into the packet returned to the user. One call does the whole packet -
    there is no per-component step, and no component's data or bytes ever
    passes through your output."""
    global _staged_packet
    plan = _staged_packet_plan
    if not plan:
        raise ValueError("No packet has been planned yet - call build_packet first.")

    _staged_packet = []
    for comp in plan:
        pdf_bytes = render_html_to_pdf(comp["template_name"], comp["data"])
        _staged_packet.append({"label": comp["label"], "kind": "pdf", "bytes": pdf_bytes})
        logger.info(f"render_packet: rendered {comp['label']!r} ({len(pdf_bytes)} bytes)")

    return {
        "status": "rendered",
        "components": [{"label": c["label"], "size_bytes": len(c["bytes"])} for c in _staged_packet],
    }


@tool
@_log_exceptions
def validate_document_structure(doc_type: str, data: dict = None) -> dict:
    """Check the staged document data has every field this document type
    requires. Do NOT pass `data` - it defaults to the staged data, so there is
    no need to repeat the document back. Fix anything reported missing with
    revise_document_data."""
    if data is None:
        data = _require_staged_doc_data()
    required_fields = {
        "medical-record": ["patient_name", "dob", "mrn", "dos", "diagnosis_codes", "physician_name"],
        "medical-bill": ["patient_name", "account_number", "service_date", "line_items", "total_amount"],
        "discharge-summary": ["patient_name", "admission_date", "discharge_date", "attending_physician", "discharge_diagnosis"],
        "acord-25": ["insured_name", "policy_number", "effective_date", "expiration_date", "insurer_name"],
        "cms-1500": ["patient_name", "insured_id", "dos_from", "diagnosis_codes", "procedure_codes", "provider_npi"],
        "ub-04": ["patient_name", "admission_date", "discharge_date", "revenue_codes", "total_charges"],
        "eob-explanation": ["member_id", "claim_number", "service_date", "provider_name", "billed_amount", "allowed_amount", "paid_amount"],
        "litigation-document": ["plaintiff_name", "defendant_name", "case_number", "court_name", "incident_date"],
        "demand-letter": ["claimant_name", "insurer_name", "claim_number", "incident_date", "demand_amount"],
        "police-report": ["incident_number", "incident_date", "location", "officer_name", "badge_number"],
        "pharmacy-invoice": ["patient_name", "rx_number", "drug_name", "ndc_code", "quantity", "days_supply", "total_charge"],
        "property-loss-notice": ["insured_name", "policy_number", "loss_date", "loss_location", "cause_of_loss"],
        "auto-accident-report": ["insured_name", "policy_number", "accident_date", "accident_location", "vehicle_info"],
    }

    resolved = resolve_doc_type(doc_type)
    if resolved not in required_fields:
        # Previously an unknown doc_type fell through to `[]` required fields
        # and was reported valid - so a typo'd or brand-new doc_type always
        # "passed" validation and the emptiness only showed up in the PDF.
        return {
            "valid": False,
            "missing_fields": [],
            "doc_type": doc_type,
            "error": (
                f"Unknown doc_type {doc_type!r} - no required-field list is defined for it, so "
                f"this document cannot be validated. Known types: {sorted(required_fields)}. If "
                f"this is a new variant template, add it to _DOC_TYPE_ALIASES in "
                f"renderers/synthetic_data.py."
            ),
        }

    missing = [f for f in required_fields[resolved] if f not in data or data[f] is None]
    return {"valid": len(missing) == 0, "missing_fields": missing, "doc_type": doc_type}
