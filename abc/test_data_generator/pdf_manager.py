import fitz
import json
import os
import pathlib
import random
import re

def _normalize_font_name(raw_font: str) -> str:
    
    fname = raw_font.lower()

    if '+' in fname:
        fname = fname.split('+', 1)[1]

    for sep in ('-', '_', ' ', ','):
        fname = fname.replace(sep, '')

    is_bold   = any(kw in fname for kw in ('bold', 'heavy', 'black', 'semibold', 'demibold', 'medium'))
    is_italic = any(kw in fname for kw in ('italic', 'oblique', 'slant'))

    serif_keywords = ('times', 'georgia', 'garamond', 'palatino', 'bookman',
                      'cambria', 'constantia', 'didot', 'caslon', 'bodoni',
                      'minion', 'charter', 'gentium', 'literata')

    mono_keywords  = ('courier', 'mono', 'consolas', 'inconsolata', 'dejavumono',
                      'lucidaconsole', 'menlo', 'sourcecodemono', 'firacode',
                      'ubuntumono', 'droidsans')

    if any(kw in fname for kw in serif_keywords):
        if is_bold and is_italic:  return 'tibi'
        if is_bold:                return 'tibo'
        if is_italic:              return 'tiit'
        return 'tiro'
    elif any(kw in fname for kw in mono_keywords):
        if is_bold and is_italic:  return 'cobi'
        if is_bold:                return 'cobo'
        if is_italic:              return 'coit'
        return 'cour'
    else:
        if is_bold and is_italic:  return 'hebi'
        if is_bold:                return 'hebo'
        if is_italic:              return 'heit'
        return 'helv'


def _find_best_span(text_dict: dict, inst_rect: fitz.Rect):
    
    cx = (inst_rect.x0 + inst_rect.x1) / 2
    cy = (inst_rect.y0 + inst_rect.y1) / 2
    centre = fitz.Point(cx, cy)

    best_overlap = None
    best_overlap_area = 0.0

    for block in text_dict.get('blocks', []):
        if block.get('type') != 0:
            continue
        for line in block.get('lines', []):
            for span in line.get('spans', []):
                span_rect = fitz.Rect(span['bbox'])

                if span_rect.contains(centre):
                    return span

                intersection = span_rect & inst_rect
                if not intersection.is_empty:
                    area = intersection.width * intersection.height
                    if area > best_overlap_area:
                        best_overlap_area = area
                        best_overlap = span

    return best_overlap


def replace_text_in_pdf(pdf_bytes: bytes, replacements: dict) -> bytes:
    """ 
    Replaces text in a PDF by redacting the old text and inserting the new text.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page in doc:
        text_dict = page.get_text("dict")
        insertions = []

        for old_text, new_text in replacements.items():
            if not old_text:
                continue

            for inst in page.search_for(old_text):
                inst_rect = fitz.Rect(inst)

                font_name  = "helv"
                font_size  = (inst.y1 - inst.y0) * 0.8
                text_color = (0, 0, 0)
                baseline_y = inst.y1 - (font_size * 0.25)

                matched_span = _find_best_span(text_dict, inst_rect)

                if matched_span:
                    font_name = _normalize_font_name(matched_span.get("font", "helv"))
                    font_size = matched_span.get("size", font_size)

                    color_int  = matched_span.get("color", 0)
                    r = ((color_int >> 16) & 0xFF) / 255.0
                    g = ((color_int >>  8) & 0xFF) / 255.0
                    b = ( color_int        & 0xFF) / 255.0
                    text_color = (r, g, b)
                    baseline_y = matched_span["origin"][1]
#requeue redact
                page.add_redact_annot(inst, fill=(1, 1, 1))

                insertions.append({
                    "rect":     inst_rect,
                    "baseline_y": baseline_y,
                    "text":     new_text,
                    "fontname": font_name,
                    "fontsize": font_size,
                    "color":    text_color,
                })

        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        for item in insertions:
        
            r = item["rect"]
            insert_rect = fitz.Rect(r.x0, r.y0 - 2, r.x1 + 200, r.y1 + 4)
            result = page.insert_textbox(
                insert_rect,
                item["text"],
                fontname=item["fontname"],
                fontsize=item["fontsize"],
                color=item["color"],
                align=0,
            )
           
            if result < 0:
                page.insert_text(
                    fitz.Point(r.x0, item["baseline_y"]),
                    item["text"],
                    fontname=item["fontname"],
                    fontsize=item["fontsize"],
                    color=item["color"],
                )

    out_bytes = doc.write(garbage=4, deflate=True)
    doc.close()
    return out_bytes

def parse_page_spec(spec: str, total_pages: int) -> list[int]:
    """
    Parses a page range string like '1-3, 5, 7-9' into a 0-indexed list.
    Returns all pages if spec is empty or 'all'.
    """
    spec = spec.strip().lower()
    if not spec or spec == "all":
        return list(range(total_pages))
    
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            start = max(1, int(start.strip()))
            end = min(total_pages, int(end.strip()))
            pages.extend(range(start - 1, end))
        else:
            p = int(part.strip())
            if 1 <= p <= total_pages:
                pages.append(p - 1)
    return pages

def image_to_pdf_bytes(image_bytes: bytes) -> bytes:
    """Converts an image (PNG, JPG, BMP, TIFF) into a single-page PDF."""
    pix = fitz.Pixmap(image_bytes)
    if pix.n > 4 or (pix.n == 4 and pix.alpha):
        pix = fitz.Pixmap(fitz.csRGB, pix)
    doc = fitz.open()
    
    img_w, img_h = pix.width, pix.height
    
    if img_w > img_h:
        a4_w, a4_h = 842, 595  
    else:
        a4_w, a4_h = 595, 842  
        
    page = doc.new_page(width=a4_w, height=a4_h)
    
    scale = min(a4_w / img_w, a4_h / img_h)
    new_w = img_w * scale
    new_h = img_h * scale

    x_offset = (a4_w - new_w) / 2
    y_offset = (a4_h - new_h) / 2
    
    target_rect = fitz.Rect(x_offset, y_offset, x_offset + new_w, y_offset + new_h)
    page.insert_image(target_rect, pixmap=pix)
    
    out_bytes = doc.write(garbage=4, deflate=True)
    doc.close()
    return out_bytes


def combine_pdfs(
    pdf_bytes_list: list[bytes],
    page_specs: list[str] = None,
    file_order: list[int] = None,
    file_types: list[str] = None
) -> bytes:

    if not pdf_bytes_list:
        return b""

    n_files = len(pdf_bytes_list)

    if file_order is None:
        file_order = list(range(n_files))
    if page_specs is None or len(page_specs) != len(file_order):
        page_specs = ["all"] * len(file_order)
    if file_types is None or len(file_types) != n_files:
        file_types = ["pdf"] * n_files

    out_pdf = fitz.open()

    for position, idx in enumerate(file_order):
        raw_bytes = pdf_bytes_list[idx]
        ftype = file_types[idx] if idx < len(file_types) else "pdf"
        spec  = page_specs[position]

        if ftype == "image":
            img_pdf_bytes = image_to_pdf_bytes(raw_bytes)
            doc = fitz.open(stream=img_pdf_bytes, filetype="pdf")
            out_pdf.insert_pdf(doc, from_page=0, to_page=0)
            doc.close()
        else:
            doc = fitz.open(stream=raw_bytes, filetype="pdf")
            total = doc.page_count
            pages = parse_page_spec(spec, total)
            for page_num in pages:
                out_pdf.insert_pdf(doc, from_page=page_num, to_page=page_num)
            doc.close()

    out_bytes = out_pdf.write(garbage=4, deflate=True)
    out_pdf.close()

    return out_bytes


# --------------------------------------------------------------------------
# Handwritten form values
#
# A filled-in document is a PRINTED schema with HANDWRITTEN values: the label
# "Name of Hospital" is printed, "Rishab Hospital" is written in. The whole
# page is read, the model says which text is which, and every value is redrawn
# in a handwriting font with the schema left untouched.
# --------------------------------------------------------------------------

# Drop a .ttf/.otf here to control what the handwriting looks like.
FONT_DIR = pathlib.Path(__file__).parent / "assets" / "fonts"

# System faces to fall back on, print-hands first: that is how people write
# into boxes. Cursive and cartoon faces are last resort.
_SYSTEM_FONTS = (
    "C:/Windows/Fonts/Inkfree.ttf",
    "C:/Windows/Fonts/segoepr.ttf",
    "/usr/share/fonts/truetype/comic-neue/ComicNeue-Regular.ttf",
    "C:/Windows/Fonts/segoesc.ttf",
    "/usr/share/fonts/opentype/urw-base35/Z003-MediumItalic.otf",
    "/usr/share/fonts/urw-base35/Z003-MediumItalic.otf",
    "C:/Windows/Fonts/comic.ttf",
)

_INKS = {"blue": (0.08, 0.12, 0.55), "black": (0.10, 0.10, 0.10),
         "red": (0.59, 0.10, 0.10)}

# Longer than this is prose, not something written into a form box.
_MAX_VALUE_LEN = 120

# Spans per model request: a whole page of context without blowing the window.
_CHUNK = 140

_MODEL_CONFIG = pathlib.Path(__file__).parent / ".andromeda" / "agents" / "doc-generator.yaml"

_SYSTEM_PROMPT = """You separate a form's pre-printed schema from the data filled into it.

You are given the text spans of ONE page, grouped by line, each span numbered.
Decide for every span whether it is SCHEMA or VALUE.

SCHEMA - pre-printed, identical on every blank copy: field labels, section
headings, table column headers, instructions, units printed as part of the
form, legal boilerplate, footers, page numbers, and the letterhead of the
organisation that printed the form.

VALUE - specific to THIS document: names, addresses, phone and account
numbers, policy/claim/reference numbers, dates, amounts, quantities,
diagnoses, descriptions, ticked options, signatures, free-text answers.

Rules:
- A span may hold a label and its value ("Name: Ram"). Return only the value
  part as `text` ("Ram"), copied exactly as it appears.
- When a span is genuinely ambiguous, call it schema. Turning a label into
  handwriting is worse than leaving one value printed.

Reply with JSON only, no prose, no code fence:
{"values": [{"span": <number>, "text": "<the value text>"}]}"""


def find_handwriting_font(explicit_path: str = "") -> str:
    """A handwriting font: an explicit one, then assets/fonts/, then a system
    face. Raises rather than falling back to Arial, which would not be
    handwriting at all."""
    if explicit_path:
        if not pathlib.Path(explicit_path).is_file():
            raise ValueError(f"Handwriting font not found: {explicit_path}")
        return explicit_path

    if FONT_DIR.is_dir():
        for pattern in ("*.ttf", "*.otf", "*.TTF", "*.OTF"):
            for candidate in sorted(FONT_DIR.glob(pattern)):
                return str(candidate)

    for candidate in _SYSTEM_FONTS:
        if pathlib.Path(candidate).is_file():
            return candidate

    raise ValueError(
        f"No handwriting font available. Put one in {FONT_DIR} (Caveat or "
        "Patrick Hand from Google Fonts), or install one system-wide "
        "(Linux: apt install fonts-comic-neue).")


def _model_name() -> str:
    """The model the app already talks to, so this needs no separate setup."""
    if env := os.environ.get("HANDWRITE_MODEL"):
        return env
    try:
        import yaml
        config = yaml.safe_load(_MODEL_CONFIG.read_text(encoding="utf-8"))
        if name := (config.get("model") or {}).get("name"):
            return name
    except Exception:
        pass
    return "openai/qwen3.6:27b"


def _parse_reply(reply: str, valid_ids: set) -> list:
    """Pull the JSON out of whatever the model wrapped it in."""
    text = re.sub(r"^```(?:json)?|```$", "", reply.strip(), flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object in model reply: {reply[:200]!r}")

    found = []
    for entry in json.loads(match.group(0)).get("values", []):
        if not isinstance(entry, dict):
            continue
        try:
            span_id = int(entry.get("span"))
        except (TypeError, ValueError):
            continue
        value = (entry.get("text") or "").strip()
        if span_id in valid_ids and value:
            found.append((span_id, value))
    return found


def classify_values(lines: list, model: str = "", timeout: int = 120) -> list:
    """Ask the model which spans are filled-in values.

    `lines` is a list of lines, each a list of (span_id, text). Returns
    [(span_id, value_text), ...]. Raises if the model is unreachable: guessing
    a document's schema with rules gave worse results than not running.
    """
    valid_ids = {idx for line in lines for idx, _ in line}
    if not valid_ids:
        return []

    # Imported here because litellm takes many seconds to import and most
    # requests never classify anything.
    from litellm import completion

    model = model or _model_name()
    flat = [(idx, text) for line in lines for idx, text in line]
    found = []

    for start in range(0, len(flat), _CHUNK):
        chunk = {idx for idx, _ in flat[start:start + _CHUNK]}
        rendered = "\n".join(
            "L%d: %s" % (n, " ".join(f'[{i}]"{t}"' for i, t in line))
            for n, line in enumerate(
                [[(i, t) for i, t in line if i in chunk] for line in lines], 1)
            if line)

        reply = completion(
            model=model,
            messages=[{"role": "system", "content": _SYSTEM_PROMPT},
                      {"role": "user", "content": rendered}],
            temperature=0, timeout=timeout,
        ).choices[0].message.content
        found.extend(_parse_reply(reply, chunk))

    return found


def _page_lines(page) -> tuple:
    """(lines, spans): `lines` is what the model reads, `spans` maps a span id
    back to the span so the value lands where the printed text was."""
    lines, spans = [], {}
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            entry = []
            for span in line.get("spans", []):
                if span["text"].strip():
                    spans[len(spans)] = span
                    entry.append((len(spans) - 1, span["text"]))
            if entry:
                lines.append(entry)
    return lines, spans


def _value_rect(span, value_text):
    """Where in the span the value sits. For a partial match the offset is
    estimated from the character position and nudged right by a third of a
    character, because leaving a sliver of the label beats redacting its end."""
    x0, y0, x1, y1 = span["bbox"]
    text = span["text"]

    if value_text == text.strip():
        return fitz.Rect(x0, y0, x1, y1), x0

    index = text.find(value_text)
    if index <= 0:
        return fitz.Rect(x0, y0, x1, y1), x0

    avg_char = (x1 - x0) / max(1, len(text))
    start_x = min(x1 - 1, x0 + avg_char * index + avg_char * 0.35)
    return fitz.Rect(start_x, y0, x1, y1), start_x


def _widget_values(page) -> list:
    """Filled AcroForm fields, the one case where the values are known exactly."""
    jobs = []
    for widget in page.widgets() or []:
        value = (widget.field_value or "").strip()
        if not value:
            continue
        rect = widget.rect
        jobs.append((rect, fitz.Point(rect.x0 + 2, rect.y1 - rect.height * 0.25),
                     value, max(6.0, rect.height * 0.62)))
        try:
            page.delete_widget(widget)
        except Exception:
            pass
    return jobs


def _write_by_word(page, point, text, size, color, font_file, metrics, rng) -> None:
    """Write a value one word at a time.

    Setting a whole string at one size and angle is what makes generated
    handwriting look generated: every letter on a perfect baseline at an
    identical size. Real writing drifts, so each word gets its own baseline
    offset, tilt, size and following space.
    """
    x, drift = point.x, 0.0

    for word in text.split(" "):
        if not word:
            x += metrics.text_length(" ", fontsize=size)
            continue

        # Damped so a long value wanders without sliding off the row.
        drift = drift * 0.65 + rng.uniform(-0.9, 0.9)
        word_size = size * rng.uniform(0.96, 1.05)
        at = fitz.Point(x, point.y + drift)

        page.insert_text(
            at, word,
            # fontfile repeats per call because apply_redactions drops the
            # page's font registration; PyMuPDF de-duplicates by fontname.
            fontname="handwriting", fontfile=font_file,
            fontsize=word_size, color=color,
            morph=(at, fitz.Matrix(rng.uniform(-2.6, 2.6))),
        )
        x += metrics.text_length(word, fontsize=word_size)
        x += metrics.text_length(" ", fontsize=size) * rng.uniform(0.85, 1.4)


def handwrite_values_in_pdf(pdf_bytes: bytes, values: list = None, ink: str = "blue",
                            font_path: str = "", seed: int = None, scale: float = 1.15,
                            model: str = "") -> tuple:
    """Rewrite everything filled into a document in handwriting, keeping the
    printed schema exactly as it is.

    The model decides which text is the pre-printed form and which was filled
    in; pass `values` to skip that and handwrite an exact list of strings.

    Returns (pdf_bytes, report). Raises if the model cannot be reached or the
    document has nothing fillable in it.
    """
    rng = random.Random(seed)
    font_file = find_handwriting_font(font_path)
    base_color = _INKS.get(ink, _INKS["blue"])
    metrics = fitz.Font(fontfile=font_file)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    report = {"method": "llm", "written": 0, "pages": len(doc)}
    wanted = {v.strip() for v in (values or []) if v and v.strip()}

    for page in doc:
        jobs = _widget_values(page)
        lines, spans = _page_lines(page)

        if wanted:
            report["method"] = "explicit"
            for value in wanted:
                if len(value) > _MAX_VALUE_LEN:
                    continue
                for rect in page.search_for(value):
                    size = max(6.0, (rect.y1 - rect.y0) * 0.85)
                    jobs.append((rect, fitz.Point(rect.x0, rect.y1 - size * 0.18),
                                 value, size))
        elif lines:
            for span_id, value_text in classify_values(lines, model=model):
                span = spans.get(span_id)
                if span is None or len(value_text) > _MAX_VALUE_LEN:
                    continue
                rect, start_x = _value_rect(span, value_text)
                jobs.append((rect, fitz.Point(start_x, span["origin"][1]),
                             value_text, span["size"]))

        # Redactions apply per page, so the typed text has to go before
        # anything is drawn, or the new text would be wiped with it. Padded
        # right and vertically only: growing leftwards would clip the label.
        for rect, _, _, _ in jobs:
            page.add_redact_annot(fitz.Rect(rect.x0, rect.y0 - 0.5,
                                            rect.x1 + 0.5, rect.y1 + 0.5), fill=(1, 1, 1))
        if jobs:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        for rect, point, value, size in jobs:
            size = max(6.0, size * scale)

            # Handwriting runs wider than print. Shrink only enough to stay on
            # the page; overrunning the printed line a little is what real
            # handwriting does.
            available = page.rect.x1 - point.x - 6
            width = metrics.text_length(value, fontsize=size)
            if width > available > 0:
                size = max(5.0, size * available / width)

            # Ink varies with pen and pressure; identical RGB reads as printed.
            color = tuple(min(1.0, max(0.0, c + rng.uniform(-0.045, 0.045)))
                          for c in base_color)
            start = fitz.Point(point.x + rng.uniform(-0.8, 1.6),
                               point.y + rng.uniform(-1.0, 0.8))
            _write_by_word(page, start, value, size, color, font_file, metrics, rng)
            report["written"] += 1

    if not report["written"]:
        doc.close()
        raise ValueError(
            "No filled-in values were found to handwrite - nothing in this "
            "document looked like entered data. Pass the values explicitly.")

    out = doc.write(garbage=4, deflate=True)
    doc.close()
    return out, report
