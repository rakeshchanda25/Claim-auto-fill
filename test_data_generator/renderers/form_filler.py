import io
import logging
from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, NameObject, NumberObject, TextStringObject

logger = logging.getLogger(__name__)


def enumerate_pdf_fields(pdf_bytes: bytes) -> dict:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    fields = reader.get_fields()
    if not fields:
        return {}
    return {name: (field.value if hasattr(field, "value") else "") for name, field in fields.items()}


def fill_pdf_form(pdf_bytes: bytes, field_map: dict, flatten: bool = True) -> bytes:
    logger.info(f"fill_pdf_form: input={len(pdf_bytes)} bytes, {len(field_map)} field(s) to set, flatten={flatten}")

    # PdfWriter(clone_from=...) does one atomic clone of the whole document
    # graph. The old add_page()-per-page + clone_reader_document_root()
    # combo clones the pages once via add_page, then clones the WHOLE
    # document root a second time - two inconsistent passes over the same
    # source that can leave the object table out of sync with an indirect
    # reference pypdf tries to resolve later, raising a bare
    # "IndexError: list index out of range" deep in pypdf's own clone()
    # with no indication of what actually went wrong. clone_from is the same
    # pattern fill_widgets_precise (below) already uses reliably.
    writer = PdfWriter(clone_from=io.BytesIO(pdf_bytes))

    acro_ref = writer._root_object.get("/AcroForm")
    if acro_ref is None:
        # Fails loudly and specifically here instead of letting pypdf's
        # update_page_form_field_values raise its own generic PyPdfError a
        # few lines down - this is exactly what happens if the source PDF
        # was never given real form fields to begin with (e.g. WeasyPrint's
        # pdf_forms=True flag wasn't set when it was generated).
        raise ValueError(
            "PDF has no /AcroForm dictionary - nothing to fill. If this PDF came from "
            "render_html_to_pdf's placeholder pipeline, check that pdf_forms=True was "
            "passed to WeasyPrint's write_pdf()."
        )
    # /NeedAppearances is required or most real PDF viewers render the page
    # exactly as before the fill - blank - even though the value is saved
    # correctly in the file (auto_regenerate=False so pypdf doesn't attempt
    # its own appearance-stream generation, which is what produced blank
    # fields against WeasyPrint's own field structure here). Same fix
    # fill_widgets_precise below already relies on for the dynamic-fill path.
    acro = acro_ref.get_object() if hasattr(acro_ref, "get_object") else acro_ref
    acro[NameObject("/NeedAppearances")] = BooleanObject(True)
    logger.info(f"writer has {len(writer.pages)} page(s), /AcroForm present, /NeedAppearances set - filling...")

    # Diagnostic: names actually present as real widgets in the PDF vs.
    # names field_map is trying to set. If these two sets barely overlap,
    # update_page_form_field_values silently no-ops for every name it can't
    # find - it does not warn or raise, which is exactly how a fill can
    # "succeed" (no exception, correct byte count) while nothing visible
    # changes.
    real_names = set()
    for page in writer.pages:
        for annot in (page.get("/Annots") or []):
            d = annot.get_object()
            if d.get("/Subtype") == "/Widget" and d.get("/T"):
                real_names.add(str(d["/T"]))
    matched = real_names & set(field_map.keys())
    logger.info(f"widget names in PDF: {len(real_names)}, field_map keys: {len(field_map)}, "
                f"matched: {len(matched)}")
    if len(matched) < len(real_names):
        logger.warning(f"{len(real_names) - len(matched)} real widget name(s) have NO matching "
                        f"field_map key - sample unmatched widget names: {sorted(real_names - matched)[:10]}")
    if len(matched) < len(field_map):
        logger.warning(f"{len(field_map) - len(matched)} field_map key(s) don't match any real "
                        f"widget - sample: {sorted(set(field_map.keys()) - matched)[:10]}")

    for page_num in range(len(writer.pages)):
        writer.update_page_form_field_values(writer.pages[page_num], field_map, auto_regenerate=False)

    if flatten:
        flattened = 0
        for page in writer.pages:
            if "/Annots" in page:
                for annot in page["/Annots"]:
                    annot_obj = annot.get_object()
                    if annot_obj.get("/Subtype") == "/Widget":
                        annot_obj.update({NameObject("/F"): NumberObject(4)})
                        flattened += 1
        logger.info(f"flattened {flattened} widget(s)")

    output = io.BytesIO()
    writer.write(output)
    result = output.getvalue()
    logger.info(f"fill_pdf_form done: output={len(result)} bytes")
    return result


# =============================================================================
# Geometry-aware fill/verify - used by the dynamic-form-fill skill/tools
# (ai_doc_generator/tools.py::fill_pdf_widgets / verify_pdf_fill), separate
# from fill_pdf_form()/enumerate_pdf_fields() above, which the existing
# generate/packet pipeline (renderers/html_renderer.py) already depends on
# and which this deliberately does not touch.
#
# Ported from the standalone claim_filler.py prototype's PypdfBackend -
# same fixes that made THAT template render correctly, generalized: fonts
# are set per-WIDGET (not per-field) because kid widgets inherit /FT from
# their parent but viewers resolve /DA from the widget first, and
# /NeedAppearances is required or many viewers render nothing at all even
# though the value is saved in the file.
# =============================================================================

def fill_widgets_precise(
    pdf_bytes: bytes,
    values: dict[str, str],
    fonts: dict[str, float] | None = None,
    watermark: str | None = None,
) -> bytes:
    logger.info(f"fill_widgets_precise: input={len(pdf_bytes)} bytes, {len(values)} value(s), "
                f"{len(fonts or {})} font override(s), watermark={'yes' if watermark else 'no'}")
    fonts = fonts or {}
    writer = PdfWriter(clone_from=io.BytesIO(pdf_bytes))

    acro_ref = writer._root_object.get("/AcroForm")
    if acro_ref is None:
        raise ValueError("PDF has no /AcroForm - nothing to fill (see analyze_uploaded_reference for flat/no-field PDFs)")
    acro = acro_ref.get_object() if hasattr(acro_ref, "get_object") else acro_ref
    acro[NameObject("/NeedAppearances")] = BooleanObject(True)

    for page in writer.pages:
        for annot in (page.get("/Annots") or []):
            d = annot.get_object()
            nm = d.get("/T") or (d.get("/Parent").get_object().get("/T") if d.get("/Parent") else None)
            if nm is None:
                continue
            size = fonts.get(str(nm))
            if size:
                d[NameObject("/DA")] = TextStringObject(f"/Helv {size} Tf 0 g")

    for page in writer.pages:
        page_names = set()
        for annot in (page.get("/Annots") or []):
            d = annot.get_object()
            nm = d.get("/T") or (d.get("/Parent").get_object().get("/T") if d.get("/Parent") else None)
            if nm:
                page_names.add(str(nm))
        subset = {k: v for k, v in values.items() if k in page_names}
        if subset:
            writer.update_page_form_field_values(page, subset, auto_regenerate=False)

    if watermark:
        _stamp(writer, watermark)

    writer.add_metadata({
        "/Producer": "ClaimDocuGen dynamic-form-fill",
        "/Subject": "SYNTHETIC / DEMONSTRATION DATA - not a submitted claim",
        "/Keywords": "synthetic;demo;not-a-real-claim",
    })

    output = io.BytesIO()
    writer.write(output)
    result = output.getvalue()
    logger.info(f"fill_widgets_precise done: output={len(result)} bytes")
    return result


def _stamp(writer: PdfWriter, text: str) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.saveState()
    c.setFont("Helvetica-Bold", 46)
    c.setFillColorRGB(0.85, 0.15, 0.15, alpha=0.16)
    c.translate(A4[0] / 2, A4[1] / 2)
    c.rotate(38)
    c.drawCentredString(0, 0, text)
    c.restoreState()
    c.save()
    buf.seek(0)
    stamp = PdfReader(buf).pages[0]
    for page in writer.pages:
        page.merge_page(stamp)


def read_back_widgets(pdf_bytes: bytes) -> dict[str, str]:
    """Reads the just-written values back out, for verify_pdf_fill to diff
    against what was requested - never trust a fill worked, confirm it."""
    out = {}
    fields = PdfReader(io.BytesIO(pdf_bytes)).get_fields() or {}
    for name, f in fields.items():
        v = f.get("/V")
        if v is not None:
            out[str(name)] = str(v)
    return out


# --- text fitting -------------------------------------------------------
# Geometry (available width/height, capacity, font floor) is exactly
# computable, so this stays deterministic, non-LLM code - the agent decides
# WHAT text goes where, this decides HOW it fits.

FONT_FLOOR = 5.4  # below this, output stops being legible


def money(v: float) -> str:
    return f"{v:,.2f}"


def _pack(words: list[str], widgets: list, font: float):
    lines, idx = [], 0
    for w in widgets:
        cap = w.capacity(font)
        line, used = [], 0
        while idx < len(words):
            add = len(words[idx]) + (1 if line else 0)
            if used + add > cap:
                break
            line.append(words[idx])
            used += add
            idx += 1
        lines.append(" ".join(line))
    return lines, len(words) - idx


def flow(text: str, widgets: list, font: float):
    """Fit text into a run of widgets, shrinking the font before ever
    truncating. Returns (values, fonts, warnings). `widgets` are
    renderers.form_structure.Widget instances for one detected run."""
    values, fonts, warns = {}, {}, []

    if len(widgets) == 1 and widgets[0].multiline:
        w = widgets[0]
        size = font

        def needed(sz: float) -> int:
            cap = w.capacity(sz)
            return sum(max(1, -(-len(ln) // cap)) for ln in text.split("\n"))

        while size > FONT_FLOOR and needed(size) * size * 1.18 > (w.h - 2):
            size -= 0.5
        if size < font:
            warns.append(f"{w.name}: auto-shrunk {font} -> {size}pt ({needed(size)} lines into {w.h:.0f}pt box)")
        values[w.name] = text
        fonts[w.name] = size
        return values, fonts, warns

    words = " ".join(text.split()).split()
    size = font
    lines, left = _pack(words, widgets, size)
    while left > 0 and size > FONT_FLOOR:
        size -= 0.5
        lines, left = _pack(words, widgets, size)

    if left > 0:
        warns.append(
            f"{widgets[0].name} run: {left} word(s) will not fit {len(widgets)} widget(s) even at "
            f"{size}pt - content needs a continuation sheet"
        )
        lines[-1] = (lines[-1] + " " + " ".join(words[len(words) - left :]))
    elif size < font:
        warns.append(f"{widgets[0].name} run: auto-shrunk {font} -> {size}pt to fit")

    for w, line in zip(widgets, lines):
        if line:
            values[w.name] = line
            fonts[w.name] = size
    return values, fonts, warns


def fit_cell(text: str, w, font: float) -> tuple[float, bool]:
    """Shrink a single table cell's font until the string fits. Returns
    (size, still_overflowing)."""
    size = font
    while size > FONT_FLOOR and len(text) > w.capacity(size):
        size -= 0.3
    return size, (len(text) > w.capacity(size))
