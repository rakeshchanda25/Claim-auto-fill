try:
    from .html_renderer import render_html_to_pdf
except Exception as _html_renderer_error:  # pragma: no cover - environment-dependent
    # WeasyPrint needs system libs (Pango/GDK-pixbuf/cairo) that aren't always
    # present. The generate/packet pipeline needs it; docx_parser's reference-document
    # analysis (used by recreate mode) does not touch HTML rendering at all, so it
    # should not be unimportable just because WeasyPrint's native deps are missing
    # in this environment.
    #
    # `except ... as name` unbinds `name` when the block exits (Python
    # deletes it to avoid a reference cycle), so it cannot be captured
    # directly by the closure below - stringify it into a plain local first.
    _html_renderer_error_message = str(_html_renderer_error)

    def render_html_to_pdf(*args, **kwargs):
        raise RuntimeError(
            f"render_html_to_pdf is unavailable: WeasyPrint failed to import "
            f"({_html_renderer_error_message}). Install its system dependencies: "
            f"https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation"
        )

from .docx_parser import extract_docx_layout
from .synthetic_data import build_synthetic_data
