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
from renderers.docx_parser import extract_docx_layout
# render_html_to_pdf comes from the renderers package (not renderers.html_renderer
# directly) because renderers/__init__.py already wraps this import in a try/except
# that substitutes a clear-error stub when WeasyPrint's native deps (Pango/cairo)
# aren't installed - importing the submodule directly bypasses that guard and
# crashes tools.py itself at import time, taking down analyze_reference_document,
# generate_synthetic_data, revise_document_data, and validate_document_structure
# with it even though none of them render a PDF. Only actually calling
# render_document_to_pdf/render_packet needs a real PDF renderer.
from renderers import render_html_to_pdf
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
            "reference file for recreate mode - there is nothing to analyze."
        )
    return _reference_bytes


# =============================================================================
# Output-artifact staging.
#
# The same "an LLM cannot carry raw bytes through its own text" problem that
# reference-document staging fixes on the way IN also applies on the way
# OUT: render_document_to_pdf used to return the finished document as raw
# `bytes`. LangChain's tool-calling
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
    that had NO counterpart applied in `dst` - reported rather than silently
    dropped/corrupted, since either a mistyped key or a shape mismatch would
    otherwise leave the document quietly wrong.

    Two rejection cases, both reported the same way:
      - the key does not exist in `dst` at all (mistyped field name);
      - `dst[key]` is a dict (a structured field like an address) but the
        supplied value is a plain scalar. A caller reading unstructured text
        off a reference document (recreate mode) naturally extracts an
        address as one flat string - applying that would silently replace
        the whole {street, city, state, zip} structure with a string, and
        every template line reading a sub-key (producer_address.street, ...)
        would then crash far from here with a confusing 'str has no
        attribute' error. Rejecting it up front means the field just falls
        back to its generated value instead - worse fidelity, not a crash.
    """
    if unmapped is None:
        unmapped = []
    for key, value in (src or {}).items():
        full = f"{path}.{key}" if path else key
        if key not in dst:
            unmapped.append(full)
        elif isinstance(dst[key], dict):
            if isinstance(value, dict):
                _overlay_values(dst[key], value, full, unmapped)
            else:
                unmapped.append(full)
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
        "discharge-summary": ["patient_name", "date_of_admission", "date_of_discharge", "diagnosis", "reason", "clinician_signature"],
        "acord-25": ["insured_name", "policy_number", "effective_date", "expiration_date", "insurer_name"],
        "cms-1500": ["patient_name", "insured_id", "dos_from", "diagnosis_codes", "procedure_codes", "provider_npi"],
        "ub-04": ["patient_name", "admission_date", "discharge_date", "revenue_codes", "total_charges"],
        "eob-explanation": ["subscriber_name", "claim_number", "provider_name", "claims", "totals"],
        "litigation-document": ["plaintiff_name", "defendant_name", "case_number", "court_name", "incident_date"],
        "demand-letter": ["claimant_name", "insurer_name", "claim_number", "incident_date", "demand_amount"],
        "police-report": ["incident_number", "incident_date", "location", "officer_name", "badge_number"],
        "pharmacy-invoice": ["invoice_number", "invoice_date", "company_gstin", "customer_name", "items", "grand_total"],
        "property-loss-notice": ["insured_name", "policy_number", "loss_date", "loss_location", "cause_of_loss"],
        "auto-accident-report": ["accident_date", "employee", "vehicle1", "vehicle2"],
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
