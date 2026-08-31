import logging
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from weasyprint import HTML

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def custom_format_filter(fmt_str, val):
    try:
        return fmt_str % val
    except Exception:
        return str(val)


# StrictUndefined: a template field that synthetic_data never supplies is a
# BUG, and Jinja's default silently renders it as an empty string - which
# surfaces only as a mysterious blank spot in the finished PDF, the exact
# failure mode that is hardest to trace back to its cause. (Two real
# instances: ub_04.html's provider telephone, and every field of a newly
# added variant template whose doc_type resolved to no data branch at all.)
# Failing loudly here names the missing field instead.
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
    undefined=StrictUndefined,
)
_env.filters["format"] = custom_format_filter


# Pagination/alignment rules applied to EVERY generated document, injected at
# render time rather than copied into each template - so a template added
# later inherits them for free, which is the whole point of putting them here.
# Each rule fixes a specific way a multi-page render comes out misaligned:
#   thead/tfoot   - a table continuing onto page 2 loses its column headers
#                   entirely without this, so the continued rows read as
#                   unlabelled columns.
#   tr            - a row split across a page boundary leaves its cells
#                   visually offset from the row's other cells.
#   headings      - a section heading stranded alone at the foot of a page,
#                   with its content overleaf.
#   orphans/widows - a single dangling line of a paragraph.
# WeasyPrint honours break-inside on rows and row groups
# (weasyprint/layout/table.py checks row/group style['break_inside']).
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


def render_html_to_pdf(template_name: str, data: dict) -> bytes:
    """Renders a template directly with its real data and prints it - every
    template gets this same single, simple path.

    This used to branch: acord-25/cms-1500/ub-04 went through a "placeholder
    then substitute" pass instead - render once with every value replaced by
    a __FORM_FIELD_x__ token, regex the tokens into <input value="..."> tags,
    render again. That existed to give WeasyPrint's pdf_forms=True flag real
    AcroForm widgets to attach values to. pdf_forms=True was removed earlier
    (a widget with a /V but no /AP appearance is exactly what a real PDF
    viewer auto-synthesizes its own appearance text for, drawn right on top
    of the value already painted as page content - a double-paint bug), which
    left the placeholder pass doing nothing useful. Worse, it was actively
    harmful once these three templates' layouts stopped being simple label/
    value table cells: wrapping a value in an <input style="width:100%"> that
    lands inline in flowing text (e.g. a 2-character state abbreviation in
    "street, city, state zip") stretches that input to the width of its
    containing block, breaking the layout around it. Plain rendering is what
    every other template already does correctly - see git history if the
    placeholder mechanism (make_placeholder_data / substitute_form_inputs /
    flatten_data) is ever needed again."""
    logger.info(f"render_html_to_pdf: template={template_name} data_fields={len(data)}")
    template_file = template_name.replace("-", "_") + ".html"
    template = _env.get_template(template_file)

    # data=data (in addition to **data) lets a template's component macros take the
    # whole dict as one parameter instead of each needing its own long, hand-maintained
    # parameter list - existing top-level references (`{{ patient_name }}` etc, used by
    # each template's fixed chrome) keep working unchanged via the **data spread.
    html_str = template.render(data=data, **data)
    logger.info(f"template rendered: {len(html_str)} chars; calling WeasyPrint...")
    pdf_bytes = HTML(string=_with_print_css(html_str), base_url=str(_TEMPLATES_DIR)).write_pdf()
    logger.info(f"render_html_to_pdf done: {len(pdf_bytes)} bytes")
    return pdf_bytes
