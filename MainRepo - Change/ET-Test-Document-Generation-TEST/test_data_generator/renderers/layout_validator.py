import re

REQUIRED_MARKERS = ("SPECIMEN",)
MIN_RENDERED_CHARS = 800
MAX_RENDERED_CHARS = 400_000

_TAG = re.compile(r"<[^>]+>")


def _visible_text(html: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub(" ", html))


def _scalar_values(data: dict, fields) -> dict:
    values = {}
    for name in fields:
        value = data.get(name)
        if isinstance(value, str) and value.strip():
            values[name] = value
    return values


def validate_layout(html: str, data: dict, required_fields=()) -> list[str]:
    from .html_renderer import render_template_string

    if not html or not html.strip():
        return ["layout is empty"]

    try:
        rendered = render_template_string(html, data)
    except Exception as exc:
        return [f"layout failed to render: {type(exc).__name__}: {exc}"]

    problems = []
    if len(rendered) < MIN_RENDERED_CHARS:
        problems.append(f"rendered output is only {len(rendered)} chars")
    if len(rendered) > MAX_RENDERED_CHARS:
        problems.append(f"rendered output is {len(rendered)} chars, over the sanity limit")

    text = _visible_text(rendered)
    for name, value in _scalar_values(data, required_fields).items():
        if value not in rendered:
            problems.append(f"required field {name!r} value is missing from the output")

    for marker in REQUIRED_MARKERS:
        if marker not in text:
            problems.append(f"missing required marker {marker!r}")

    return problems
