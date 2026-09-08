"""Self-check for the scan degradation features.

    python test_scan_features.py            # assert behaviour
    python test_scan_features.py --samples  # also write sample PDFs to ./scan_samples

Each check fails loudly if the feature stops doing what it claims, which is the
only way to notice - the output is a picture, and a picture always looks like
something.
"""
import json
import re
import sys

import cv2
import fitz
import numpy as np

from pdf_manager import handwrite_values_in_pdf
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


def _form_pdf() -> bytes:
    """A printed form: typed labels, typed values - the thing that should come
    back with the labels printed and the values handwritten."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=500)
    page.insert_text((40, 50), "HOSPITAL EMPANELMENT REQUEST FORM", fontsize=13)
    for i, (label, value) in enumerate([
            ("Name of Hospital", "Rishab Hospital"),
            ("Complete Address", "G-12 Kardhani, Kalwar Road, Jaipur"),
            ("Telephone Nos", "0141-2405692"),
            ("PAN No", "AAVPS8821F"),
            ("No. of Beds", "50")]):
        page.insert_text((40, 100 + i * 34), f"{label}: {value}", fontsize=11)
    out = doc.tobytes()
    doc.close()
    return out


def _fonts_by_text(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    found = {}
    for block in doc[0].get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                found[span["text"].strip()] = span["font"]
    doc.close()
    return found


def check_handwritten_values():
    """The image-2 behaviour: schema printed, values handwritten.

    Uses detect="rules" so the check runs without a model - the LLM path is
    exercised separately by check_llm_classifier when one is reachable.
    """
    out, report = handwrite_values_in_pdf(_form_pdf(), seed=3, detect="rules")
    assert report["method"] == "rules" and report["written"] >= 5, report
    fonts = _fonts_by_text(out)

    printed = [t for t, f in fonts.items() if "Ink" not in f and "Comic" not in f
               and "Z003" not in f and "Segoe" not in f]
    handwritten = [t for t, f in fonts.items() if t not in printed]

    assert any("Name of Hospital" in t for t in printed), f"labels lost: {printed}"
    assert "Rishab Hospital" in handwritten, f"values not handwritten: {handwritten}"
    assert "0141-2405692" in handwritten
    assert "50" in handwritten
    # A label must never be converted - that would be rewriting the template.
    assert not any("Telephone Nos" in t for t in handwritten), "a label got handwritten"

    # Explicit values take precedence over the label heuristic.
    only, rep2 = handwrite_values_in_pdf(_form_pdf(), values=["Rishab Hospital"], seed=3)
    assert rep2["method"] == "explicit", rep2
    f2 = _fonts_by_text(only)
    hand2 = [t for t, f in f2.items() if "Ink" in f or "Comic" in f or "Z003" in f
             or "Segoe" in f]
    assert hand2 == ["Rishab Hospital"], f"explicit list not respected: {hand2}"

    # A document with nothing fillable must say so, not silently do nothing.
    blank = fitz.open()
    blank.new_page(width=200, height=100).insert_text((20, 50), "no fields here", fontsize=11)
    data = blank.tobytes()
    blank.close()
    try:
        handwrite_values_in_pdf(data, detect="rules")
        raise AssertionError("should have refused a document with no values")
    except ValueError as exc:
        assert "No filled-in values were found" in str(exc)

    print(f"  handwritten vals  ok   {len(handwritten)} values handwritten, "
          f"{len(printed)} labels left printed")


def check_classifier_contract():
    """The classifier's parsing and rule fallback, without calling a model."""
    from value_classifier import _parse_reply, _render_lines, classify_page_by_rules

    lines = [[(0, "Name of Hospital:"), (1, "Rishab Hospital")],
             [(2, "Complete Address: G-12 Kardhani, Jaipur")]]
    rendered = _render_lines(lines)
    assert '[1]"Rishab Hospital"' in rendered and rendered.startswith("L1:")

    # The model's reply survives a code fence and stray prose.
    reply = '```json\n{"values": [{"span": 1, "text": "Rishab Hospital"}]}\n```'
    assert _parse_reply(reply, {0, 1, 2}) == [(1, "Rishab Hospital")]
    # Spans it invented are dropped rather than crashing the run.
    assert _parse_reply('{"values":[{"span":99,"text":"x"}]}', {0, 1}) == []
    try:
        _parse_reply("I could not do that", {0, 1})
        raise AssertionError("unparseable reply should raise")
    except ValueError:
        pass

    by_rules = classify_page_by_rules(lines)
    assert (1, "Rishab Hospital") in by_rules
    assert (2, "G-12 Kardhani, Jaipur") in by_rules
    print(f"  classifier        ok   parses replies, drops bad spans, "
          f"rules found {len(by_rules)}")


def check_llm_pipeline_with_stub():
    """The whole LLM path with a canned model reply.

    Proves the plumbing - prompt built, reply parsed, value located inside its
    span, handwriting drawn - without needing a reachable model. Only the
    model's judgement is left untested, and check_llm_classifier covers that
    when one is up.
    """
    import types
    import value_classifier

    seen = {}

    def fake_completion(model=None, messages=None, **kwargs):
        seen["model"] = model
        seen["prompt"] = messages[1]["content"]
        # Values only: the labels and the heading must be left alone.
        wanted = ("Rishab Hospital", "G-12 Kardhani, Kalwar Road, Jaipur",
                  "0141-2405692", "AAVPS8821F", "50")
        picks = []
        for line in messages[1]["content"].splitlines():
            for match in re.finditer(r'\[(\d+)\]"([^"]*)"', line):
                span_id, text = int(match.group(1)), match.group(2)
                for value in wanted:
                    if text.strip().endswith(value):
                        picks.append({"span": span_id, "text": value})
                        break
        body = json.dumps({"values": picks})
        message = types.SimpleNamespace(content="```json\n" + body + "\n```")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    real = sys.modules.get("litellm")
    sys.modules["litellm"] = types.SimpleNamespace(completion=fake_completion)
    try:
        out, report = handwrite_values_in_pdf(_form_pdf(), seed=3, detect="llm")
    finally:
        if real is not None:
            sys.modules["litellm"] = real
        else:
            del sys.modules["litellm"]

    assert report["method"] == "llm", report
    assert report["fallback_reason"] is None, report
    assert report["written"] == 5, report

    fonts = _fonts_by_text(out)
    hand = [t for t, f in fonts.items()
            if any(k in f for k in ("Ink", "Comic", "Z003", "Segoe"))]
    assert "Rishab Hospital" in hand and "AAVPS8821F" in hand, hand
    assert not any("HOSPITAL EMPANELMENT" in t for t in hand), "heading was handwritten"
    assert not any(t.startswith("PAN No") for t in hand), "label was handwritten"
    assert seen["model"] == value_classifier._configured_model()
    assert 'L1:' in seen["prompt"] and '[0]"' in seen["prompt"]

    # A model that dies mid-run falls back to rules and says so.
    def boom(**kwargs):
        raise RuntimeError("model gone")
    sys.modules["litellm"] = types.SimpleNamespace(completion=boom)
    try:
        _, fallback = handwrite_values_in_pdf(_form_pdf(), seed=3, detect="llm")
    finally:
        if real is not None:
            sys.modules["litellm"] = real
        else:
            del sys.modules["litellm"]
    assert fallback["method"] == "rules" and "model gone" in fallback["fallback_reason"]

    print(f"  llm pipeline      ok   stubbed model -> {report['written']} values "
          f"handwritten; failure falls back to rules")


def check_llm_classifier():
    """Runs the real model if one is reachable; skips cleanly if not."""
    from value_classifier import _configured_model, classify_page
    model = _configured_model()
    lines = [[(0, "Name of Hospital:"), (1, "Rishab Hospital")],
             [(2, "No. of Beds:"), (3, "50")],
             [(4, "HOSPITAL EMPANELMENT REQUEST FORM")]]
    try:
        found = classify_page(lines, timeout=45)
    except Exception as exc:
        print(f"  llm classifier    skipped  ({model} unreachable: "
              f"{type(exc).__name__})")
        return
    ids = {span for span, _ in found}
    assert 1 in ids and 3 in ids, f"model missed the values: {found}"
    assert 4 not in ids, f"model called the heading a value: {found}"
    assert 0 not in ids and 2 not in ids, f"model called a label a value: {found}"
    print(f"  llm classifier    ok   {model} classified {len(found)} values correctly")


def check_photo_darkness():
    """Photo mode must be uneven - a flat fill is what it is replacing."""
    img = _white_page()
    out = apply_dark_background(img, intensity=0.55, mode="photo")
    assert out.mean() < img.mean() - 20, "page did not darken"

    grey = out.mean(axis=2)
    h, w = grey.shape
    corners = np.mean([grey[:h // 5, :w // 5].mean(), grey[:h // 5, -w // 5:].mean(),
                       grey[-h // 5:, :w // 5].mean(), grey[-h // 5:, -w // 5:].mean()])
    centre = grey[2 * h // 5:3 * h // 5, 2 * w // 5:3 * w // 5].mean()
    assert centre > corners + 8, f"no vignette (centre {centre:.0f} vs corners {corners:.0f})"

    flat = apply_dark_background(img, intensity=0.55, mode="full")
    paper = img.mean(axis=2) > 200
    assert out[paper].std() > flat[paper].std() + 5, "photo mode is as flat as a plain fill"
    print(f"  photo darkness    ok   centre {centre:.0f} vs corners {corners:.0f}, "
          f"variation {out[paper].std():.1f} (flat fill {flat[paper].std():.1f})")


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
        "02_dark_photo": dict(dark_background=True, dark_mode="photo", dark_intensity=0.55),
        "02b_dark_band": dict(dark_background=True, dark_mode="band", dark_intensity=0.55),
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
    check_handwritten_values()
    check_classifier_contract()
    check_llm_pipeline_with_stub()
    check_llm_classifier()
    check_photo_darkness()
    check_colour_fidelity()
    check_full_pipeline()
    print("all checks passed")
    if "--samples" in sys.argv:
        print("\nsamples")
        write_samples()
