import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _format_filter(fmt_str, val):
    try:
        return fmt_str % val
    except Exception:
        return str(val)


# StrictUndefined: a template field synthetic_data never supplies is a bug, and
# Jinja's default renders it as an empty string - which surfaces only as a
# mysterious blank in the finished PDF. Failing loudly names the missing field.
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
    undefined=StrictUndefined,
)
_env.filters["format"] = _format_filter


# Applied to every document at render time rather than copied into each template,
# so a template added later inherits them. Each rule fixes one way a multi-page
# render comes out wrong: tables losing their headers on page 2, a row split
# across a page break, a heading stranded at the foot of a page, a dangling line.
_PRINT_CSS = (
    "<style>"
    "thead{display:table-header-group;}"
    "tfoot{display:table-footer-group;}"
    "tr{break-inside:avoid;page-break-inside:avoid;}"
    "h1,h2,h3,h4,.section-bar{break-after:avoid;page-break-after:avoid;}"
    "p{orphans:2;widows:2;}"
    "</style>"
)


def _with_print_css(html_str: str) -> str:
    """Injects _PRINT_CSS last in <head> so it wins over same-specificity
    template rules, falling back to a prepend for a fragment with no head."""
    if "</head>" in html_str:
        return html_str.replace("</head>", _PRINT_CSS + "</head>", 1)
    return _PRINT_CSS + html_str


def render_html(template_name: str, data: dict) -> str:
    """Renders a document template to an HTML string.

    `data=data` alongside `**data` lets a template's component macros take the
    whole dict as one parameter, while each template's fixed chrome keeps using
    top-level references like {{ patient_name }}.
    """
    template = _env.get_template(template_name.replace("-", "_") + ".html")
    return template.render(data=data, **data)


def render_html_to_pdf(template_name: str, data: dict) -> bytes:
    # Imported here, not at module scope: WeasyPrint needs system libraries
    # (Pango/cairo/GDK-pixbuf) that are absent on plenty of dev machines. Only
    # this one function needs them, so templates stay renderable - and testable -
    # everywhere else.
    from weasyprint import HTML

    logger.info(f"render: template={template_name} fields={len(data)}")
    html_str = render_html(template_name, data)
    pdf_bytes = HTML(string=_with_print_css(html_str), base_url=str(_TEMPLATES_DIR)).write_pdf()
    logger.info(f"render done: {len(html_str)} chars HTML -> {len(pdf_bytes)} bytes PDF")
    return pdf_bytes
