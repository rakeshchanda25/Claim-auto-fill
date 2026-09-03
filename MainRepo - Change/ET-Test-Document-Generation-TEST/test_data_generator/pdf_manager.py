import fitz
import io

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

