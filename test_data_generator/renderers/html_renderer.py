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


def substitute_form_inputs(html_str: str) -> tuple[str, dict[str, str]]:
    """Replace every __FORM_FIELD_x__ token with an <input>, giving each
    occurrence a UNIQUE widget name. Returns (html, {widget_name: data_key}).

    A template legitimately renders the same data key more than once: ACORD-25
    repeats effective_date/expiration_date across all four coverage rows,
    CMS-1500 repeats dos_from and the NPIs per service line, UB-04 repeats
    discharge_date on every revenue-code row. Emitting <input
    name="discharge_date"> six times produces six widgets sharing one /T,
    which AcroForm treats as ONE field with six appearances - pypdf then
    collides on the per-field XObject it builds while flattening ("XObject
    '/Fm effective_date' already added to page resources. This might be an
    issue.") and only one of those locations can be drawn correctly.

    Naming them discharge_date, discharge_date__2, ... makes each its own
    field with its own appearance stream, while the returned mapping keeps
    every one of them pointed at the original data key for the fill.
    """
    seen: dict[str, int] = {}
    widget_source: dict[str, str] = {}

    def repl(match):
        base = match.group(1)
        n = seen.get(base, 0)
        seen[base] = n + 1
        unique = base if n == 0 else f"{base}__{n + 1}"
        widget_source[unique] = base
        return f'<input type="text" name="{unique}" style="{_INPUT_STYLE}" />'

    return re.sub(r"__FORM_FIELD_([a-zA-Z0-9_]+)__", repl, html_str), widget_source


def render_html_to_pdf(template_name: str, data: dict) -> bytes:
    logger.info(f"render_html_to_pdf: template={template_name} data_fields={len(data)}")
    template_file = template_name.replace("-", "_") + ".html"
    template = _env.get_template(template_file)

    is_standard_form = template_name in ("acord-25", "cms-1500", "ub-04", "acord_25", "cms_1500", "ub_04")
    logger.info(f"render path: {'standardized-form (placeholder-then-fill)' if is_standard_form else 'direct render'}")

    if is_standard_form:
        placeholders = make_placeholder_data(data)
        html_str = template.render(**placeholders)
        logger.info(f"placeholder pass rendered: {len(html_str)} chars")

        html_str, widget_source = substitute_form_inputs(html_str)
        dupes = len(widget_source) - len(set(widget_source.values()))
        logger.info(f"substituted {len(widget_source)} placeholder token(s) with <input> elements "
                    f"({len(set(widget_source.values()))} distinct data key(s), "
                    f"{dupes} repeated occurrence(s) given unique widget names)")

        # pdf_forms=True is required for WeasyPrint to emit a /AcroForm at
        # all - it's off by default (weasyprint/__init__.py's DEFAULT_OPTIONS
        # has pdf_forms=None), so every <input> element above would
        # otherwise be laid out as plain, non-interactive visual boxes with
        # no PDF form fields behind them. Without this flag,
        # fill_pdf_form()'s update_page_form_field_values() call below fails
        # with "No /AcroForm dictionary in PDF of PdfWriter Object" - the
        # rendered PDF literally has nothing for it to fill.
        logger.info("calling WeasyPrint (pdf_forms=True)...")
        pdf_bytes = HTML(string=html_str, base_url=str(_TEMPLATES_DIR)).write_pdf(pdf_forms=True)
        logger.info(f"WeasyPrint produced {len(pdf_bytes)} bytes")

        # Build the fill map from the widgets actually emitted, not from every
        # key in `data`. The latter sent ~100 keys at a form with ~41 widgets,
        # so most were silent no-ops (update_page_form_field_values ignores
        # unknown names without warning) and a genuinely missing widget would
        # have been invisible in that noise.
        flat_data = flatten_data(data)
        field_map = {widget: flat_data.get(src, "") for widget, src in widget_source.items()}
        logger.info(f"filling AcroForm with {len(field_map)} field(s) mapped from {len(flat_data)} data value(s)")
        filled_pdf = fill_pdf_form(pdf_bytes, field_map, flatten=True)
        logger.info(f"render_html_to_pdf done: {len(filled_pdf)} bytes")
        return filled_pdf

    html_str = template.render(**data)
    logger.info(f"template rendered: {len(html_str)} chars; calling WeasyPrint...")
    pdf_bytes = HTML(string=html_str, base_url=str(_TEMPLATES_DIR)).write_pdf()
    logger.info(f"render_html_to_pdf done: {len(pdf_bytes)} bytes")
    return pdf_bytes
