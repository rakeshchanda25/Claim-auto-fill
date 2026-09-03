from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from .layouts import get_layout

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _format_filter(fmt_str, val):
    try:
        return fmt_str % val
    except Exception:
        return str(val)


_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
    undefined=StrictUndefined,
)
_env.filters["format"] = _format_filter


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
    if "</head>" in html_str:
        return html_str.replace("</head>", _PRINT_CSS + "</head>", 1)
    return _PRINT_CSS + html_str


def render_template_string(html: str, data: dict) -> str:
    return _env.from_string(html).render(data=data, **data)


def render_html(template_name: str, data: dict) -> str:
    doc_type = template_name.replace("_", "-")
    layout = get_layout(doc_type, data.get("layout_key"), data.get("layout_shape"))
    if layout is not None:
        return render_template_string(layout, data)
    template = _env.get_template(template_name.replace("-", "_") + ".html")
    return template.render(data=data, **data)


def render_html_to_pdf(template_name: str, data: dict) -> bytes:
    from weasyprint import HTML

    html_str = render_html(template_name, data)
    return HTML(string=_with_print_css(html_str), base_url=str(_TEMPLATES_DIR)).write_pdf()
