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

        input_style = (
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

        def repl(match):
            name = match.group(1)
            return f'<input type="text" name="{name}" style="{input_style}" />'

        html_str, n_subbed = re.subn(r"__FORM_FIELD_([a-zA-Z0-9_]+)__", repl, html_str)
        logger.info(f"substituted {n_subbed} placeholder token(s) with <input> elements")

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

        flat_data = flatten_data(data)
        logger.info(f"filling AcroForm with {len(flat_data)} flattened field(s)...")
        filled_pdf = fill_pdf_form(pdf_bytes, flat_data, flatten=True)
        logger.info(f"render_html_to_pdf done: {len(filled_pdf)} bytes")
        return filled_pdf

    html_str = template.render(**data)
    logger.info(f"template rendered: {len(html_str)} chars; calling WeasyPrint...")
    pdf_bytes = HTML(string=html_str, base_url=str(_TEMPLATES_DIR)).write_pdf()
    logger.info(f"render_html_to_pdf done: {len(pdf_bytes)} bytes")
    return pdf_bytes
