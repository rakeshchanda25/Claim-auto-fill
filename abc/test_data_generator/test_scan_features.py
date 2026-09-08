"""Self-check for the scan degradation features.

    python test_scan_features.py            # assert behaviour
    python test_scan_features.py --samples  # also write sample PDFs to ./scan_samples

Each check fails loudly if the feature stops doing what it claims, which is the
only way to notice - the output is a picture, and a picture always looks like
something.
"""
import sys

import cv2
import fitz
import numpy as np

from scanner_simulator import (
    apply_crop,
    apply_dark_background,
    apply_handwritten_annotations,
    find_handwriting_font,
    simulate_scan,
)


def _sample_pdf() -> bytes:
    """A page with text top and bottom and a red box, so cropping, shading and
    colour handling are all observable."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 70), "CLAIM NUMBER: 000-00-000123", fontsize=14)
    page.insert_text((60, 110), "POLICY: HO-8837412   DATE OF LOSS: 03/01/2026", fontsize=11)
    for i in range(14):
        page.insert_text((60, 170 + i * 22), f"Line {i:02d}  insured statement text", fontsize=10)
    page.insert_text((60, 740), "BOTTOM EDGE FIELD: adjuster signature", fontsize=11)
    page.draw_rect(fitz.Rect(430, 60, 560, 120), color=None, fill=(1, 0, 0))
    out = doc.tobytes()
    doc.close()
    return out


def _page_image(pdf_bytes: bytes) -> np.ndarray:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[0].get_pixmap(alpha=False, colorspace=fitz.csRGB)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)
    doc.close()
    return img.copy()


def _white_page(h=800, w=600) -> np.ndarray:
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    cv2.putText(img, "CLAIM 000-123", (40, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
    cv2.putText(img, "BOTTOM FIELD", (40, h - 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    return img


def check_dark_background():
    img = _white_page()
    before_paper = img[img.mean(axis=2) > 200].mean()
    for mode in ("band", "full", "shadow", "blocks"):
        out = apply_dark_background(img, intensity=0.6, mode=mode)
        assert out.shape == img.shape, mode
        assert out.mean() < img.mean() - 5, f"{mode}: page did not get darker"
        # Ink must stay dark - multiplying paper down must not lift the text.
        assert out.min() < 40, f"{mode}: text was washed out instead of the paper darkened"
    full = apply_dark_background(img, intensity=0.6, mode="full")
    paper_after = full[img.mean(axis=2) > 200].mean()
    assert paper_after < before_paper * 0.5, "full mode barely darkened the paper"
    print(f"  dark background   ok   paper {before_paper:.0f} -> {paper_after:.0f}")


def check_crop():
    img = _white_page()
    ink_bottom_before = (img[-200:] < 128).sum()
    out = apply_crop(img, percent=20, edges="bottom")
    assert out.shape == img.shape, "page geometry should be preserved"
    ink_bottom_after = (out[-200:] < 128).sum()
    assert ink_bottom_before > 0, "test fixture has no bottom content"
    assert ink_bottom_after < ink_bottom_before * 0.5, "bottom field survived the crop"

    # Every edge combination stays in range and never blanks the page.
    for edges in ("left", "right", "top", "bottom", "left,right", "top,bottom",
                  "left,right,top,bottom"):
        o = apply_crop(img, percent=50, edges=edges)   # over the 40% cap
        assert o.shape == img.shape and o.size > 0, edges
    assert apply_crop(img, percent=10, edges="").shape == img.shape
    print(f"  cropped document  ok   bottom ink {ink_bottom_before} -> {ink_bottom_after}")


def check_handwritten():
    print(f"  font in use            {find_handwriting_font()}")
    img = _white_page()
    out = apply_handwritten_annotations(img, count=6, ink="blue")
    assert out.shape == img.shape

    changed = (np.abs(out.astype(int) - img.astype(int)).sum(axis=2) > 30).sum()
    assert changed > 500, f"barely any ink was added ({changed} px)"

    # Blue ink must actually be blue in BGR, not red.
    diff = np.abs(out.astype(int) - img.astype(int)).sum(axis=2) > 30
    b, g, r = [out[:, :, c][diff].mean() for c in range(3)]
    assert b > r + 15, f"ink is not blue (B={b:.0f} R={r:.0f})"

    red = apply_handwritten_annotations(img, count=6, ink="red")
    d2 = np.abs(red.astype(int) - img.astype(int)).sum(axis=2) > 30
    rb, _, rr = [red[:, :, c][d2].mean() for c in range(3)]
    assert rr > rb + 15, f"red ink is not red (R={rr:.0f} B={rb:.0f})"

    assert apply_handwritten_annotations(img, count=0).tobytes() == img.tobytes(), \
        "count=0 should be a no-op"
    print(f"  handwritten annot ok   {changed} px of ink, blue B={b:.0f}/R={r:.0f}")


def check_colour_fidelity():
    """The red box must still be red after a scan - the RGB/BGR fix."""
    out = simulate_scan(_sample_pdf(), False, False, False, False, seed=1)
    img = _page_image(out)                      # RGB
    box = img[70:110, 450:540].reshape(-1, 3).mean(axis=0)
    assert box[0] > box[2] + 60, f"red box did not survive the scan as red: RGB={box}"
    print(f"  colour fidelity   ok   red box RGB=({box[0]:.0f},{box[1]:.0f},{box[2]:.0f})")


def check_full_pipeline():
    pdf = _sample_pdf()
    out = simulate_scan(
        pdf, skew=True, blur=True, noise=True, low_dpi=False,
        dark_background=True, dark_intensity=0.45, dark_mode="band",
        crop=True, crop_percent=10, crop_edges="right,bottom",
        handwritten=True, annotation_count=4, annotation_ink="blue",
        seed=7,
    )
    assert out[:4] == b"%PDF", "output is not a PDF"
    assert len(out) > 1000
    doc = fitz.open(stream=out, filetype="pdf")
    assert len(doc) == 1
    doc.close()

    # Same seed, same bytes - reproducible test data.
    again = simulate_scan(
        pdf, skew=True, blur=True, noise=True, low_dpi=False,
        dark_background=True, dark_intensity=0.45, dark_mode="band",
        crop=True, crop_percent=10, crop_edges="right,bottom",
        handwritten=True, annotation_count=4, annotation_ink="blue",
        seed=7,
    )
    assert _page_image(out).tobytes() == _page_image(again).tobytes(), \
        "same seed produced a different page"
    print(f"  full pipeline     ok   {len(out)} bytes, reproducible with seed=7")


def write_samples():
    from pathlib import Path
    out_dir = Path("scan_samples")
    out_dir.mkdir(exist_ok=True)
    pdf = _sample_pdf()
    cases = {
        "01_original": {},
        "02_dark_band": dict(dark_background=True, dark_mode="band", dark_intensity=0.55),
        "03_dark_full": dict(dark_background=True, dark_mode="full", dark_intensity=0.6),
        "04_dark_shadow": dict(dark_background=True, dark_mode="shadow", dark_intensity=0.7),
        "05_cropped": dict(crop=True, crop_percent=12, crop_edges="right,bottom"),
        "06_handwritten": dict(handwritten=True, annotation_count=5, annotation_ink="blue"),
        "07_all": dict(dark_background=True, dark_mode="band", crop=True,
                       handwritten=True, annotation_count=4, skew=True, noise=True),
    }
    for name, kwargs in cases.items():
        kwargs.setdefault("skew", False)
        kwargs.setdefault("blur", False)
        kwargs.setdefault("noise", False)
        kwargs.setdefault("low_dpi", False)
        data = simulate_scan(pdf, kwargs.pop("skew"), kwargs.pop("blur"),
                             kwargs.pop("noise"), kwargs.pop("low_dpi"), seed=5, **kwargs)
        (out_dir / f"{name}.pdf").write_bytes(data)
        print(f"  wrote {out_dir / (name + '.pdf')}")


if __name__ == "__main__":
    print("scan feature checks")
    check_dark_background()
    check_crop()
    check_handwritten()
    check_colour_fidelity()
    check_full_pipeline()
    print("all checks passed")
    if "--samples" in sys.argv:
        print("\nsamples")
        write_samples()
