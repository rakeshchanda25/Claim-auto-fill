import html as _html
import io
import logging
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def custom_format_filter(fmt_str, val):
    if isinstance(val, str) and val.startswith("__FORM_FIELD_"):
        return val
    try:
        return fmt_str % val
    except Exception:
        return str(val)


_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)
_env.filters["format"] = custom_format_filter


def make_placeholder_data(d, parent_key=""):
    if isinstance(d, dict):
        return {k: make_placeholder_data(v, f"{parent_key}_{k}" if parent_key else k) for k, v in d.items()}
    elif isinstance(d, (list, tuple)):
        return [make_placeholder_data(v, f"{parent_key}_{i}") for i, v in enumerate(d)]
    else:
        return f"__FORM_FIELD_{parent_key}__"


def flatten_data(d, parent_key=""):
    flat = {}
    if isinstance(d, dict):
        for k, v in d.items():
            flat.update(flatten_data(v, f"{parent_key}_{k}" if parent_key else k))
    elif isinstance(d, (list, tuple)):
        for i, v in enumerate(d):
            flat.update(flatten_data(v, f"{parent_key}_{i}"))
    else:
        flat[parent_key] = str(d) if d is not None else ""
    return flat


_INPUT_STYLE = (
    "border:none !important;"
    "background:transparent !important;"
    "font-family:inherit !important;"
    "font-size:inherit !important;"
    "font-weight:inherit !important;"
    "color:#000 !important;"
    "width:100% !important;"
    "height:100% !important;"
    "box-sizing:border-box !important;"
    "padding:0 !important;"
    "margin:0 !important;"
)


def substitute_form_inputs(
    html_str: str, value_for: dict[str, str] | None = None
) -> tuple[str, dict[str, str]]:
    """Replace every __FORM_FIELD_x__ token with an <input>, giving each
    occurrence a UNIQUE widget name and (when `value_for` is supplied) its
    real value. Returns (html, {widget_name: data_key}).

    Unique names matter because a template legitimately renders the same data
    key more than once: ACORD-25 repeats effective_date/expiration_date across
    all four coverage rows, CMS-1500 repeats dos_from and the NPIs per service
    line, UB-04 repeats discharge_date on every revenue-code row. Emitting
    <input name="discharge_date"> six times produces six widgets sharing one
    /T, which AcroForm treats as ONE field with six appearances - pypdf then
    collides on the per-field XObject it builds while flattening ("XObject
    '/Fm effective_date' already added to page resources. This might be an
    issue.") and only one of those locations can be drawn correctly.

    The value attribute matters because it is the ONLY thing WeasyPrint can
    draw from (html5_ua.css uses `content: attr(value)`) and the only thing it
    writes into the field's /V (pdf/anchors.py: `field['V'] =
    element.attrib.get('value', '')`). Without it both the visible text and
    the form value are empty.
    """
    seen: dict[str, int] = {}
    widget_source: dict[str, str] = {}

    def repl(match):
        base = match.group(1)
        n = seen.get(base, 0)
        seen[base] = n + 1
        unique = base if n == 0 else f"{base}__{n + 1}"
        widget_source[unique] = base

        value_attr = ""
        if value_for:
            raw = value_for.get(base, "")
            if raw:
                value_attr = f' value="{_html.escape(str(raw), quote=True)}"'
        return f'<input type="text" name="{unique}"{value_attr} style="{_INPUT_STYLE}" />'

    return re.sub(r"__FORM_FIELD_([a-zA-Z0-9_]+)__", repl, html_str), widget_source


def _visible_text(pdf_bytes: bytes) -> str:
    """Text actually present in the pages' content streams - i.e. what a
    viewer draws without interpreting any AcroForm data."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return " ".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        logger.exception("could not extract text to verify the render")
        return ""


def render_html_to_pdf(template_name: str, data: dict) -> bytes:
    logger.info(f"render_html_to_pdf: template={template_name} data_fields={len(data)}")
    template_file = template_name.replace("-", "_") + ".html"
    template = _env.get_template(template_file)

    is_standard_form = template_name in ("acord-25", "cms-1500", "ub-04", "acord_25", "cms_1500", "ub_04")
    logger.info(f"render path: {'standardized-form (placeholder-then-substitute)' if is_standard_form else 'direct render'}")

    if is_standard_form:
        flat_data = flatten_data(data)
        placeholders = make_placeholder_data(data)
        html_str = template.render(**placeholders)
        logger.info(f"placeholder pass rendered: {len(html_str)} chars")

        # Values go into each <input>'s value="..." attribute - the only
        # thing WeasyPrint draws for an input's text (html5_ua.css:
        # input[value]::before { content: attr(value) }, part of the BASE
        # stylesheet, always active).
        html_str, widget_source = substitute_form_inputs(html_str, value_for=flat_data)
        dupes = len(widget_source) - len(set(widget_source.values()))
        with_values = sum(1 for src in widget_source.values() if flat_data.get(src))
        logger.info(f"substituted {len(widget_source)} placeholder token(s) with <input> elements "
                    f"({len(set(widget_source.values()))} distinct data key(s), "
                    f"{dupes} repeated occurrence(s) given unique widget names, "
                    f"{with_values} carrying a non-empty value)")

        # Deliberately NOT passing pdf_forms=True. That flag makes WeasyPrint
        # emit a real AcroForm widget for every <input> (its is_input() check
        # requires the appearance:auto CSS that only html5_ua_form.css, loaded
        # solely under pdf_forms=True, sets) - and a widget with a /V but no
        # /AP appearance stream is exactly what a real PDF viewer auto-
        # synthesizes its OWN appearance text for, drawn right on top of the
        # value already painted as page content above. That double-paint
        # survived an earlier fix that only cleared /NeedAppearances, because
        # viewers synthesize a missing /AP regardless of that flag. Without
        # pdf_forms, <input> is never recognized as a form widget at all -
        # just a plain styled box showing its attr(value) text once.
        logger.info("calling WeasyPrint (no pdf_forms - plain page content only)...")
        pdf_bytes = HTML(string=html_str, base_url=str(_TEMPLATES_DIR)).write_pdf()
        logger.info(f"WeasyPrint produced {len(pdf_bytes)} bytes")

        # Sanity check: confirm the values are genuinely in the page content.
        samples = [v for v in {flat_data.get(s, "") for s in widget_source.values()} if len(v) >= 4][:8]
        visible = _visible_text(pdf_bytes)
        found = [s for s in samples if s in visible]
        logger.info(f"visible-text check: {len(found)}/{len(samples)} sampled value(s) found in page content")
        if samples and not found:
            logger.warning("NO sampled values are visible in the page content - check the template's "
                            "<input> markup for this doc type.")

        logger.info(f"render_html_to_pdf done: {len(pdf_bytes)} bytes")
        return pdf_bytes

    html_str = template.render(**data)
    logger.info(f"template rendered: {len(html_str)} chars; calling WeasyPrint...")
    pdf_bytes = HTML(string=html_str, base_url=str(_TEMPLATES_DIR)).write_pdf()
    logger.info(f"render_html_to_pdf done: {len(pdf_bytes)} bytes")
    return pdf_bytes
