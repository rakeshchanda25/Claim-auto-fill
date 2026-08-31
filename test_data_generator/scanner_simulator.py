import fitz
import cv2
import json
import numpy as np
import io

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
    rotation_rules: str = "[]"
) -> bytes:    
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out_doc = fitz.open()
    
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
        
        rotation_angle = page_rotations.get(page_num, 0)
        should_rotate = rotation and (page_num in page_rotations)
        
        degraded = apply_degradations(img_array, skew, blur, noise, low_dpi, skew_angle, blur_strength, noise_intensity,rotate=should_rotate,rotation_angle=rotation_angle
        )

        _, img_encoded = cv2.imencode('.png', degraded)
        img_bytes = img_encoded.tobytes()
        
        new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, stream=img_bytes)
        
    out_pdf = io.BytesIO()
    out_doc.save(out_pdf, garbage=4, deflate=True)
    
    doc.close()
    out_doc.close()
    
    return out_pdf.getvalue()
