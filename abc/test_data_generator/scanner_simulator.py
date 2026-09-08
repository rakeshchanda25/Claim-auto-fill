import fitz
import cv2
import json
import random
import numpy as np
import io

from PIL import Image, ImageDraw, ImageFont

from handwriting import INK_COLORS, find_handwriting_font

_INK_COLORS = INK_COLORS

_DEFAULT_NOTES = (
    "Verified w/ insured", "Called claimant - no answer", "See attached estimate",
    "Approved", "Needs adjuster review", "Copy sent to legal", "Check DOL",
    "Rec'd", "Incomplete - follow up", "Confirm policy #", "Paid in full",
    "Duplicate?", "OK to close", "Photos on file",
)

_MARKINGS = ("circle", "underline", "strikethrough", "check", "arrow")


def apply_dark_background(img_array: np.ndarray, intensity: float = 0.55,
                          mode: str = "photo", rng: random.Random = None) -> np.ndarray:
    """Darken the paper while leaving the ink dark, so text sits on a grey or
    near-black ground.

    Multiplying is what makes this realistic: white paper (255) drops to the
    target level while black text (0) stays black, which is exactly the loss of
    contrast that makes OCR struggle - as opposed to blending, which would wash
    the text out along with the paper.
    """
    rng = rng or random.Random()
    intensity = float(np.clip(intensity, 0.05, 0.95))
    result = img_array.astype(np.float32)
    h, w = result.shape[:2]

    # Per-pixel multiplier: 1.0 leaves the paper white, (1 - intensity) is the
    # darkest the paper gets.
    gain = np.ones((h, w), dtype=np.float32)
    floor = 1.0 - intensity

    if mode == "full":
        gain[:, :] = floor

    elif mode == "shadow":
        # A book-scan shadow: dark at one edge, fading across the page.
        edge = rng.choice(("left", "right", "top", "bottom"))
        ramp = np.linspace(floor, 1.0, w if edge in ("left", "right") else h,
                           dtype=np.float32)
        if edge == "right":
            ramp = ramp[::-1]
        if edge == "bottom":
            ramp = ramp[::-1]
        gain = np.tile(ramp, (h, 1)) if edge in ("left", "right") else \
            np.tile(ramp.reshape(-1, 1), (1, w))

    elif mode == "blocks":
        for _ in range(rng.randint(2, 4)):
            bw, bh = rng.randint(w // 4, w // 2), rng.randint(h // 12, h // 5)
            x0, y0 = rng.randint(0, max(1, w - bw)), rng.randint(0, max(1, h - bh))
            gain[y0:y0 + bh, x0:x0 + bw] = floor

    elif mode == "photo":
        # A page photographed in poor light, which is how most "dark
        # background" documents actually arrive: darker overall, darker still
        # towards the edges, and unevenly lit across the sheet.
        gain[:, :] = floor + (1.0 - floor) * 0.35

        # Vignette - corners fall away faster than the centre.
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        cy, cx = h / 2.0, w / 2.0
        radius = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
        gain *= np.clip(1.0 - 0.55 * intensity * (radius / 1.414) ** 1.6, 0.05, 1.0)

        # Uneven illumination: a handful of random low-frequency values blown
        # up to page size, so the light falls across the sheet in broad soft
        # patches rather than in visible blocks.
        coarse = np.array([[rng.uniform(0.72, 1.12) for _ in range(4)] for _ in range(5)],
                          dtype=np.float32)
        blotches = cv2.resize(coarse, (w, h), interpolation=cv2.INTER_CUBIC)
        gain *= cv2.GaussianBlur(blotches, (0, 0), sigmaX=max(8, w / 40))

        gain = np.clip(gain, 0.03, 1.0)

    else:  # "band" - a shaded section running the width of the page
        for _ in range(rng.randint(1, 2)):
            bh = rng.randint(h // 8, h // 4)
            y0 = rng.randint(0, max(1, h - bh))
            gain[y0:y0 + bh, :] = floor

    result *= gain[:, :, None]

    if mode == "photo":
        # Grain is what separates a photograph from a flat fill.
        grain = np.random.normal(0, 4.0 + 8.0 * intensity, result.shape).astype(np.float32)
        result += grain

    return np.clip(result, 0, 255).astype(np.uint8)


def apply_crop(img_array: np.ndarray, percent: float = 8.0,
               edges: str = "right,bottom") -> np.ndarray:
    """Cut the given edges off the page, removing whatever content was there.

    The remaining area is stretched back to the original raster size, so the
    PDF page geometry is unchanged and the only difference is that the fields
    at those edges are genuinely gone.
    """
    wanted = {e.strip().lower() for e in edges.split(",") if e.strip()}
    if not wanted:
        return img_array

    h, w = img_array.shape[:2]
    # Capped so a careless 60% on both sides cannot leave an empty image.
    fraction = float(np.clip(percent, 0.0, 40.0)) / 100.0
    dx, dy = int(w * fraction), int(h * fraction)

    x0 = dx if "left" in wanted else 0
    x1 = w - dx if "right" in wanted else w
    y0 = dy if "top" in wanted else 0
    y1 = h - dy if "bottom" in wanted else h

    cropped = img_array[y0:y1, x0:x1]
    if cropped.size == 0:
        return img_array
    return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)


def _ink_map(img_array: np.ndarray, cell: int = 40) -> np.ndarray:
    """Coarse grid of how much ink each cell holds, used to place annotations
    either over printed content or in a clear margin."""
    grey = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
    dark = (grey < 160).astype(np.float32)
    h, w = dark.shape
    gh, gw = max(1, h // cell), max(1, w // cell)
    return cv2.resize(dark, (gw, gh), interpolation=cv2.INTER_AREA)


def _pick_spot(ink: np.ndarray, img_shape, over_text: bool, rng: random.Random):
    """A pixel position in a cell that either has ink (over_text) or does not."""
    gh, gw = ink.shape
    h, w = img_shape[:2]
    cells = [(y, x) for y in range(gh) for x in range(gw)
             if (ink[y, x] > 0.08) == over_text]
    if not cells:
        cells = [(y, x) for y in range(gh) for x in range(gw)]
    cy, cx = rng.choice(cells)
    return (int((cx + rng.random()) * w / gw), int((cy + rng.random()) * h / gh))


def _jittered_line(draw: ImageDraw.ImageDraw, points, color, width, rng):
    """Draw a polyline with small random offsets so the stroke reads as
    hand-drawn rather than as a vector shape."""
    wobbled = [(x + rng.uniform(-2.5, 2.5), y + rng.uniform(-2.5, 2.5)) for x, y in points]
    draw.line(wobbled, fill=color, width=width, joint="curve")


def _draw_marking(draw, kind, x, y, color, rng, scale=1.0):
    width = max(2, int(3 * scale))
    if kind == "circle":
        rx, ry = 90 * scale, 26 * scale
        pts = []
        for i in range(37):
            a = i * (2 * np.pi / 36)
            pts.append((x + rx * np.cos(a), y + ry * np.sin(a)))
        _jittered_line(draw, pts, color, width, rng)
    elif kind == "underline":
        _jittered_line(draw, [(x - 80 * scale, y), (x + 80 * scale, y)], color, width, rng)
    elif kind == "strikethrough":
        _jittered_line(draw, [(x - 85 * scale, y + 4), (x + 85 * scale, y - 4)],
                       color, width, rng)
    elif kind == "check":
        _jittered_line(draw, [(x - 18 * scale, y), (x - 4 * scale, y + 16 * scale),
                              (x + 22 * scale, y - 20 * scale)], color, width + 1, rng)
    else:  # arrow
        _jittered_line(draw, [(x - 70 * scale, y), (x + 20 * scale, y)], color, width, rng)
        _jittered_line(draw, [(x + 20 * scale, y), (x + 4 * scale, y - 12 * scale)],
                       color, width, rng)
        _jittered_line(draw, [(x + 20 * scale, y), (x + 4 * scale, y + 12 * scale)],
                       color, width, rng)


def apply_handwritten_annotations(img_array: np.ndarray, count: int = 3,
                                  ink: str = "blue", notes: str = "",
                                  font_path: str = "",
                                  rng: random.Random = None) -> np.ndarray:
    """Add handwritten notes and markings over and around the printed content.

    The printed document is untouched - these are added on top, the way a
    reviewer annotates a page after it was printed.
    """
    if count <= 0:
        return img_array

    rng = rng or random.Random()
    font_file = find_handwriting_font(font_path)
    color = _INK_COLORS.get(ink, _INK_COLORS["blue"])

    supplied = [n.strip() for n in notes.replace("\n", ",").split(",") if n.strip()]
    phrases = supplied or list(_DEFAULT_NOTES)

    h, w = img_array.shape[:2]
    scale = w / 1200.0  # annotations sized relative to the page, not the DPI
    ink_grid = _ink_map(img_array)

    # cv2 arrays are BGR; PIL works in RGB.
    canvas = Image.fromarray(cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)).convert("RGBA")

    for i in range(count):
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)

        # Notes go in clear space so they stay readable; markings go over the
        # text they are marking.
        as_marking = rng.random() < 0.4
        x, y = _pick_spot(ink_grid, img_array.shape, over_text=as_marking, rng=rng)

        if as_marking:
            _draw_marking(draw, rng.choice(_MARKINGS), x, y,
                          color + (235,), rng, scale=scale)
        else:
            size = max(14, int(rng.uniform(26, 40) * scale))
            font = ImageFont.truetype(font_file, size)
            text = rng.choice(phrases)
            draw.text((x, y), text, font=font, fill=color + (240,))

        # A few degrees of tilt - nobody writes on a perfect baseline.
        layer = layer.rotate(rng.uniform(-7, 7), resample=Image.BICUBIC, center=(x, y))
        canvas = Image.alpha_composite(canvas, layer)

    return cv2.cvtColor(np.array(canvas.convert("RGB")), cv2.COLOR_RGB2BGR)


def apply_degradations(img_array: np.ndarray, skew: bool, blur: bool, noise: bool, low_dpi: bool, skew_angle: float, blur_strength: int, noise_intensity: float, rotate: bool = False, rotation_angle: float = 0.0) -> np.ndarray:
    result = img_array.copy()

    if low_dpi:
        h, w = result.shape[:2]
        result = cv2.resize(result, (w // 3, h // 3), interpolation=cv2.INTER_LINEAR)
        result = cv2.resize(result, (w, h), interpolation=cv2.INTER_NEAREST)

    if blur:

        ksize = blur_strength if blur_strength % 2 == 1 else blur_strength + 1
        result = cv2.GaussianBlur(result, (ksize, ksize), 0)

    if skew:
        h, w = result.shape[:2]
        angle = np.random.uniform(-skew_angle, skew_angle)
        M = cv2.getRotationMatrix2D((w/2, h/2), angle, 1)
        result = cv2.warpAffine(result, M, (w, h), borderValue=(255, 255, 255))

    if rotate:
        h, w = result.shape[:2]
        original_h, original_w = h, w

        angle_rad = np.radians(abs(rotation_angle))
        cos_a = abs(np.cos(angle_rad))
        sin_a = abs(np.sin(angle_rad))

        new_w = original_w * cos_a + original_h * sin_a
        new_h = original_w * sin_a + original_h * cos_a

        scale_factor = min(original_w / new_w, original_h / new_h) * 0.95
        scale_factor = max(scale_factor, 0.6)
        scaled_h, scaled_w = int(h * scale_factor), int(w * scale_factor)
        result = cv2.resize(result, (scaled_w, scaled_h), interpolation=cv2.INTER_LINEAR)

        canvas = np.full((original_h, original_w, 3), 255, dtype=np.uint8)

        y_offset = (original_h - scaled_h) // 2
        x_offset = (original_w - scaled_w) // 2

        canvas[y_offset:y_offset + scaled_h, x_offset:x_offset + scaled_w] = result

        M = cv2.getRotationMatrix2D((original_w/2, original_h/2), -rotation_angle, 1)
        result = cv2.warpAffine(canvas, M, (original_w, original_h), borderValue=(255, 255, 255))

    if noise:
        noise_img = np.random.normal(0, noise_intensity, result.shape).astype(np.float32)
        result = np.clip(result.astype(np.float32) + noise_img, 0, 255).astype(np.uint8)

    return result

def simulate_scan(
    pdf_bytes: bytes,
    skew: bool,
    blur: bool,
    noise: bool,
    low_dpi: bool,
    skew_angle: float = 1.5,
    blur_strength: int = 5,
    noise_intensity: float = 15.0,
    overlay_image_bytes: bytes = None,
    rotation: bool = False,
    rotation_rules: str = "[]",
    dark_background: bool = False,
    dark_intensity: float = 0.55,
    dark_mode: str = "photo",
    crop: bool = False,
    crop_percent: float = 8.0,
    crop_edges: str = "right,bottom",
    handwritten: bool = False,
    annotation_count: int = 3,
    annotation_ink: str = "blue",
    annotation_text: str = "",
    annotation_font: str = "",
    seed: int = None,
) -> bytes:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out_doc = fitz.open()

    rng = random.Random(seed)
    if seed is not None:
        np.random.seed(seed)

    page_rotations = {}
    if rotation:
        try:
            rules = json.loads(rotation_rules)
            for rule in rules:
                pages = rule.get('pages', '').strip()
                angle = float(rule.get('angle', 0))

                if pages:
                    parts = pages.split(',')
                    for part in parts:
                        part = part.strip()
                        if '-' in part:
                            start, end = map(int, part.split('-'))
                            for p in range(start - 1, end):
                                page_rotations[p] = angle
                        else:
                            page_num = int(part) - 1
                            page_rotations[page_num] = angle
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

    for page_num in range(len(doc)):
        page = doc[page_num]

        if overlay_image_bytes:
            rect = fitz.Rect(page.rect.width - 220, 20, page.rect.width - 20, 220)
            page.insert_image(rect, stream=overlay_image_bytes)

        zoom = 2.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=fitz.csRGB)

        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)
        # PyMuPDF gives RGB but cv2 works in - and writes - BGR. Without this
        # swap every colour is mirrored on the way out (a red stamp scans blue).
        img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        # Annotations belong to the paper, so they go on before any scan
        # artefact is applied to it.
        if handwritten:
            img_array = apply_handwritten_annotations(
                img_array, count=annotation_count, ink=annotation_ink,
                notes=annotation_text, font_path=annotation_font, rng=rng)

        if dark_background:
            img_array = apply_dark_background(
                img_array, intensity=dark_intensity, mode=dark_mode, rng=rng)

        rotation_angle = page_rotations.get(page_num, 0)
        should_rotate = rotation and (page_num in page_rotations)

        degraded = apply_degradations(img_array, skew, blur, noise, low_dpi, skew_angle, blur_strength, noise_intensity,rotate=should_rotate,rotation_angle=rotation_angle
        )

        # Cropping last: it is the scanner's capture window, so it cuts
        # whatever the scanner actually saw after skew and rotation.
        if crop:
            degraded = apply_crop(degraded, percent=crop_percent, edges=crop_edges)

        _, img_encoded = cv2.imencode('.png', degraded)
        img_bytes = img_encoded.tobytes()

        new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, stream=img_bytes)

    out_pdf = io.BytesIO()
    out_doc.save(out_pdf, garbage=4, deflate=True)

    doc.close()
    out_doc.close()

    return out_pdf.getvalue()
