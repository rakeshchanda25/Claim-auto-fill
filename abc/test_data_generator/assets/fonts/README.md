# Handwriting fonts

Drop a handwriting `.ttf` or `.otf` in this folder to control what the
"Handwritten annotation" scan option writes with. The first font found here
wins, so keep only the one you want.

Good free choices (Google Fonts, SIL Open Font License):

- **Caveat** - fast, legible ballpoint, closest to a real adjuster's note
- **Patrick Hand** - neat printing, good when the note must stay OCR-readable
- **Homemade Apple** - looser cursive, harder for OCR (useful for HITL tests)
- **Reenie Beanie** - scrappy marker

If this folder is empty the simulator falls back to a handwriting face
installed on the machine (Ink Free / Segoe Script / Segoe Print / Comic Sans on
Windows, Comic Neue or URW Chancery on Linux). If it finds none it raises
rather than quietly writing in Arial - install one with:

    sudo apt install fonts-comic-neue
