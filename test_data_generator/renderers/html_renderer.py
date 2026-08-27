import html as _html
import io
import logging
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from .form_filler import fill_pdf_form

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


# WeasyPrint's PDF-forms UA stylesheet (weasyprint/css/html5_ua_form.css,
# loaded ONLY when pdf_forms=True) contains:
#     input:not([type="submit"])::before { visibility: hidden }
# which hides the ::before pseudo-element that html5_ua.css:175 would
# otherwise use to draw an input's text:
#     input[value]:not(...)::before { content: attr(value); ... }
# That is deliberate on WeasyPrint's part - with pdf_forms=True it assumes the
# PDF VIEWER will paint each field's value from the AcroForm data. But
# honouring that is optional per the PDF spec (it hinges on /NeedAppearances)
# and plenty of viewers simply don't, which is exactly why these forms came
# out completely blank. Un-hiding it puts the value back into the page's own
# content stream - visible in every viewer - while the real AcroForm field
# stays underneath, so the output is still a genuine fillable form.
_FORM_TEXT_VISIBLE_CSS = (
    "<style>"
    'input:not([type="submit"])::before{visibility:visible !important;}'
    "</style>"
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
    logger.info(f"render path: {'standardized-form (placeholder-then-fill)' if is_standard_form else 'direct render'}")

    if is_standard_form:
        flat_data = flatten_data(data)
        placeholders = make_placeholder_data(data)
        html_str = template.render(**placeholders)
        logger.info(f"placeholder pass rendered: {len(html_str)} chars")

        # Values go INTO the input elements: that is both what WeasyPrint draws
        # (content: attr(value)) and what it writes into each field's /V.
        html_str, widget_source = substitute_form_inputs(html_str, value_for=flat_data)
        dupes = len(widget_source) - len(set(widget_source.values()))
        with_values = sum(1 for src in widget_source.values() if flat_data.get(src))
        logger.info(f"substituted {len(widget_source)} placeholder token(s) with <input> elements "
                    f"({len(set(widget_source.values()))} distinct data key(s), "
                    f"{dupes} repeated occurrence(s) given unique widget names, "
                    f"{with_values} carrying a non-empty value)")

        # Re-enable the input text WeasyPrint's PDF-forms stylesheet hides.
        if "</head>" in html_str:
            html_str = html_str.replace("</head>", _FORM_TEXT_VISIBLE_CSS + "</head>", 1)
        else:
            html_str = _FORM_TEXT_VISIBLE_CSS + html_str
        logger.info("injected CSS to un-hide input text (WeasyPrint hides it when pdf_forms=True)")

        # pdf_forms=True is required for WeasyPrint to emit a /AcroForm at
        # all - it's off by default (weasyprint/__init__.py's DEFAULT_OPTIONS
        # has pdf_forms=None), so every <input> element above would
        # otherwise be laid out as plain, non-interactive visual boxes with
        # no PDF form fields behind them.
        logger.info("calling WeasyPrint (pdf_forms=True)...")
        pdf_bytes = HTML(string=html_str, base_url=str(_TEMPLATES_DIR)).write_pdf(pdf_forms=True)
        logger.info(f"WeasyPrint produced {len(pdf_bytes)} bytes")

        # Set /V for every field and flag /NeedAppearances. flatten=False: the
        # text is already drawn in the page content by WeasyPrint above, so
        # letting pypdf bake its own appearance on top would double-print it.
        field_map = {widget: flat_data.get(src, "") for widget, src in widget_source.items()}
        logger.info(f"setting AcroForm values for {len(field_map)} field(s)")
        filled_pdf = fill_pdf_form(pdf_bytes, field_map, flatten=False)

        # Verify the values are genuinely in the page content, not merely in
        # the form data - that distinction is the whole bug this guards.
        samples = [v for v in {flat_data.get(s, "") for s in widget_source.values()} if len(v) >= 4][:8]
        visible = _visible_text(filled_pdf)
        found = [s for s in samples if s in visible]
        logger.info(f"visible-text check: {len(found)}/{len(samples)} sampled value(s) found in page content")
        if samples and not found:
            logger.warning(
                "NO sampled values are visible in the page content - the AcroForm render did not "
                "paint them. Falling back to a plain (non-fillable) direct render so the document "
                "is at least readable; the output will have no form fields."
            )
            html_str = template.render(**data)
            filled_pdf = HTML(string=html_str, base_url=str(_TEMPLATES_DIR)).write_pdf()

        logger.info(f"render_html_to_pdf done: {len(filled_pdf)} bytes")
        return filled_pdf

    html_str = template.render(**data)
    logger.info(f"template rendered: {len(html_str)} chars; calling WeasyPrint...")
    pdf_bytes = HTML(string=html_str, base_url=str(_TEMPLATES_DIR)).write_pdf()
    logger.info(f"render_html_to_pdf done: {len(pdf_bytes)} bytes")
    return pdf_bytes
