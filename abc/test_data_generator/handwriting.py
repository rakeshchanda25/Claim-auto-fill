"""Where handwriting comes from: the font file and the pen colour.

Shared by the scan simulator (annotations drawn on the raster) and the PDF
manipulator (form values re-rendered as embedded text).
"""

from pathlib import Path

# Drop any .ttf/.otf here to control what handwriting looks like.
FONT_DIR = Path(__file__).parent / "assets" / "fonts"

# Handwriting faces that ship with common systems, tried in order when the
# project directory is empty.
# Ordered by how much they read as a person filling in a form rather than as
# a typeface. Print-hands come first because that is how people write into
# boxes; the cursive and cartoon faces are last-resort.
SYSTEM_HANDWRITING_FONTS = (
    "C:/Windows/Fonts/Inkfree.ttf",
    "C:/Windows/Fonts/segoepr.ttf",
    "/usr/share/fonts/truetype/comic-neue/ComicNeue-Regular.ttf",
    "C:/Windows/Fonts/segoesc.ttf",
    "/usr/share/fonts/opentype/urw-base35/Z003-MediumItalic.otf",
    "/usr/share/fonts/urw-base35/Z003-MediumItalic.otf",
    "/usr/share/fonts/truetype/msttcorefonts/Comic_Sans_MS.ttf",
    "C:/Windows/Fonts/comic.ttf",
)

# RGB. Ballpoint blue is what most forms are actually filled in with.
INK_COLORS = {
    "blue": (20, 30, 140),
    "black": (25, 25, 25),
    "red": (150, 25, 25),
}


def find_handwriting_font(explicit_path: str = "") -> str:
    """Path to a handwriting font: an explicit one, then assets/fonts/, then a
    known system face. Raises rather than silently falling back to Arial,
    because a typeface that is not handwriting makes the feature a lie."""
    if explicit_path:
        if not Path(explicit_path).is_file():
            raise ValueError(f"Handwriting font not found: {explicit_path}")
        return explicit_path

    if FONT_DIR.is_dir():
        for pattern in ("*.ttf", "*.otf", "*.TTF", "*.OTF"):
            for candidate in sorted(FONT_DIR.glob(pattern)):
                return str(candidate)

    for candidate in SYSTEM_HANDWRITING_FONTS:
        if Path(candidate).is_file():
            return candidate

    raise ValueError(
        "No handwriting font available. Put a handwriting .ttf/.otf in "
        f"{FONT_DIR} (e.g. Caveat, Patrick Hand, Homemade Apple from Google "
        "Fonts), or install one system-wide (Linux: apt install fonts-comic-neue)."
    )


def ink_rgb(name: str) -> tuple:
    return INK_COLORS.get(name, INK_COLORS["blue"])


def ink_unit(name: str) -> tuple:
    """Same colour as 0-1 floats, which is what PyMuPDF wants."""
    return tuple(c / 255.0 for c in ink_rgb(name))
