import re
from pathlib import Path

LAYOUTS_DIR = Path(__file__).parent / "layouts"

_KEY = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,31}$")


def normalize_key(key) -> str | None:
    if not key:
        return None
    candidate = str(key).strip().upper().replace(" ", "_")
    return candidate if _KEY.match(candidate) else None


def layout_path(doc_type: str, key: str) -> Path:
    return LAYOUTS_DIR / doc_type / f"{key}.html"


def get_layout(doc_type: str, key, shape: str | None = None) -> str | None:
    key = normalize_key(key)
    if not key:
        return None
    candidates = []
    if shape and shape != "default":
        candidates.append(f"{key}__{shape.upper()}")
    candidates.append(key)
    for candidate in candidates:
        path = layout_path(doc_type, candidate)
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return None


def save_layout(doc_type: str, key: str, html: str) -> Path:
    key = normalize_key(key)
    if not key:
        raise ValueError(f"Invalid layout key: {key!r}")
    path = layout_path(doc_type, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def available_layouts(doc_type: str) -> list[str]:
    directory = LAYOUTS_DIR / doc_type
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.html"))


def all_layouts() -> dict[str, list[str]]:
    if not LAYOUTS_DIR.is_dir():
        return {}
    return {
        d.name: available_layouts(d.name)
        for d in sorted(LAYOUTS_DIR.iterdir())
        if d.is_dir() and available_layouts(d.name)
    }
