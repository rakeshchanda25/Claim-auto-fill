"""
renderers/form_structure.py

Deterministic, template-agnostic structural analysis of ANY AcroForm PDF.
Ported from the standalone blueprint_builder.py prototype into this
project's tool layer - same detection logic, adapted to work on PDF
bytes (matching every other renderer/tool in this project) instead of a
file path, with the CLI/tool-contract-as-a-spec parts removed since
that contract is now implemented for real as Andromeda tools in
ai_doc_generator/tools.py + skills/dynamic-form-fill/SKILL.md.

Nothing in this file knows about any specific form, field, or insurer.
It only computes what is exactly computable from geometry: widget
inventory (including /Kids), nearest-label harvesting, repeating grids,
Yes/No checkbox pairs, multi-widget narrative runs, and section
headings. Meaning (what a run/pair/grid actually represents) is
deliberately NOT decided here - that is the agent's job, using this
structural draft plus the inspect_region_image tool for anything
ambiguous.
"""

from __future__ import annotations

import hashlib
import io
import re
from collections import defaultdict
from dataclasses import asdict, dataclass

import pdfplumber
from pypdf import PdfReader


# =============================================================================
# 1. WIDGET INVENTORY
# =============================================================================

@dataclass
class Widget:
    name: str
    page: int
    rect: tuple            # (x0, y0, x1, y1), y=0 at page bottom
    ftype: str              # text | checkbox | radio | choice
    on_state: str | None = None
    multiline: bool = False
    readonly: bool = False

    @property
    def w(self) -> float:
        return self.rect[2] - self.rect[0]

    @property
    def h(self) -> float:
        return self.rect[3] - self.rect[1]

    @property
    def cx(self) -> float:
        return (self.rect[0] + self.rect[2]) / 2

    @property
    def cy(self) -> float:
        return (self.rect[1] + self.rect[3]) / 2

    def capacity(self, font: float = 9.0) -> int:
        """Approx chars that fit on one line. Helvetica avg glyph ~0.5em."""
        return max(1, int(self.w / (0.5 * font)))


def inventory(pdf_bytes: bytes) -> tuple[list[Widget], dict[int, tuple]]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    out: list[Widget] = []
    pagesizes: dict[int, tuple] = {}

    for pno, page in enumerate(reader.pages, 1):
        mb = page.mediabox
        pagesizes[pno] = (float(mb.width), float(mb.height))
        for annot in (page.get("/Annots") or []):
            d = annot.get_object()
            if d.get("/Subtype") != "/Widget":
                continue

            # Kid widgets carry no /T -- the name lives on the parent. A naive
            # walk misses them entirely and silently loses repeating grids
            # built from kid widgets (verified against real templates in
            # this repo, which have exactly this shape).
            name = d.get("/T")
            parent = d.get("/Parent")
            if name is None and parent is not None:
                name = parent.get_object().get("/T")
            if name is None:
                continue
            name = str(name)

            src = d if "/FT" in d else (parent.get_object() if parent else d)
            ft = src.get("/FT")
            flags = int(src.get("/Ff", 0) or 0)

            on_state = None
            if ft == "/Btn":
                ap = d.get("/AP")
                if ap and "/N" in ap:
                    keys = [str(k) for k in ap["/N"].get_object().keys()]
                    cand = [k for k in keys if k != "/Off"]
                    on_state = cand[0] if cand else "/On"
                ftype = "radio" if flags & (1 << 15) else "checkbox"
            elif ft == "/Ch":
                ftype = "choice"
            else:
                ftype = "text"

            out.append(
                Widget(
                    name=name,
                    page=pno,
                    rect=tuple(round(float(v), 2) for v in d["/Rect"]),
                    ftype=ftype,
                    on_state=on_state,
                    multiline=bool(flags & (1 << 12)),
                    readonly=bool(flags & 1),
                )
            )

    return out, pagesizes


# =============================================================================
# 2. LABEL HARVEST  (geometry, not a vision model, for conventional layouts)
# =============================================================================
# pdfplumber uses top-down y; widget rects are bottom-up. Convert once, here,
# and never think about it again.
# =============================================================================

def harvest_text(pdf_bytes: bytes) -> dict[int, list[dict]]:
    pages: dict[int, list[dict]] = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            words = page.extract_words(
                use_text_flow=False, keep_blank_chars=False, extra_attrs=["size"]
            )
            H = float(page.height)
            pages[pno] = [
                {
                    "text": w["text"],
                    "x0": float(w["x0"]),
                    "x1": float(w["x1"]),
                    # convert to bottom-up so it shares the widget coordinate space
                    "y0": H - float(w["bottom"]),
                    "y1": H - float(w["top"]),
                    "size": round(float(w.get("size", 0)), 1),
                }
                for w in words
            ]
    return pages


def label_for(wg: Widget, words: list[dict], left_only: bool = False) -> dict:
    """Nearest text to the LEFT on the same band, else ABOVE. Conventional
    form layouts are label-left or label-above; this recovers most of them."""
    band = [t for t in words if not (t["y1"] < wg.rect[1] - 1 or t["y0"] > wg.rect[3] + 1)]

    left = [t for t in band if t["x1"] <= wg.rect[0] + 2]
    if left:
        left.sort(key=lambda t: -t["x1"])
        gap = wg.rect[0] - left[0]["x1"]
        if gap < 220:
            chunk, cursor = [], left[0]["x1"]
            for t in left:  # walk leftwards while contiguous
                if cursor - t["x1"] > 14:
                    break
                chunk.append(t)
                cursor = t["x0"]
            chunk.sort(key=lambda t: t["x0"])
            return {
                "text": " ".join(t["text"] for t in chunk),
                "source": "left",
                "gap": round(gap, 1),
            }

    if left_only:
        return {"text": "", "source": "none", "gap": None}

    above = [
        t
        for t in words
        if t["y0"] >= wg.rect[3] - 1
        and t["y0"] - wg.rect[3] < 26
        and t["x1"] > wg.rect[0] - 6
        and t["x0"] < wg.rect[2] + 6
    ]
    if above:
        ytop = min(t["y0"] for t in above)
        row = sorted([t for t in above if abs(t["y0"] - ytop) < 4], key=lambda t: t["x0"])
        return {
            "text": " ".join(t["text"] for t in row),
            "source": "above",
            "gap": round(row[0]["y0"] - wg.rect[3], 1),
        }

    return {"text": "", "source": "none", "gap": None}


# =============================================================================
# 3. STRUCTURE DETECTION  (grids, pairs, runs, sections)
# =============================================================================

def cluster_rows(widgets: list[Widget], tol: float = 8.0) -> list[list[Widget]]:
    rows: list[list[Widget]] = []
    for wg in sorted(widgets, key=lambda w: -w.cy):
        for r in rows:
            if abs(r[0].cy - wg.cy) < tol:
                r.append(wg)
                break
        else:
            rows.append([wg])
    for r in rows:
        r.sort(key=lambda w: w.rect[0])
    return rows


def _sig(row: list[Widget]) -> tuple:
    return tuple(round(w.rect[0], 1) for w in row)


def _sig_match(a: tuple, b: tuple, tol: float = 5.0) -> bool:
    """Rows belong to the same grid if columns line up within tolerance.
    Exact-equality matching fragments real tables: sub-point drift between
    rows is normal in hand-authored forms."""
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))


def detect_grids(widgets: list[Widget], min_cols: int = 3, min_rows: int = 3) -> list[dict]:
    """A repeating region = >=min_rows consecutive rows sharing an x-signature."""
    grids = []
    for page in sorted({w.page for w in widgets}):
        text = [w for w in widgets if w.page == page and w.ftype == "text"]
        rows = cluster_rows(text)
        sigs = [(_sig(r), r) for r in rows]

        i = 0
        while i < len(sigs):
            sig, _ = sigs[i]
            if len(sig) < min_cols:
                i += 1
                continue
            j = i
            while j + 1 < len(sigs) and _sig_match(sig, sigs[j + 1][0]):
                j += 1
            block = [r for _, r in sigs[i : j + 1]]
            if len(block) >= min_rows:
                names = [w.name for r in block for w in r]
                grids.append(
                    {
                        "page": page,
                        "rows": len(block),
                        "cols": len(sig),
                        "row_pitch": round(abs(block[0][0].cy - block[1][0].cy), 2),
                        "column_rects": [[round(v, 1) for v in w.rect] for w in block[0]],
                        "column_capacity": [w.capacity(7.0) for w in block[0]],
                        "widget_matrix": [[w.name for w in r] for r in block],
                        "name_rule": name_rule(names, len(sig)),
                        "column_labels": [None] * len(sig),  # <- agent fills
                        "concept": None,  # <- agent fills
                    }
                )
                i = j + 1
            else:
                i += 1
    return grids


def name_rule(names: list[str], cols: int) -> dict | None:
    """If widget names are a row-major arithmetic sequence, emit the closed
    form so the grid needs no per-cell mapping at all."""
    m = [re.fullmatch(r"(.*?)(\d+)$", n) for n in names]
    if not all(m):
        return None
    prefixes = {x.group(1) for x in m}
    if len(prefixes) != 1:
        return None
    nums = [int(x.group(2)) for x in m]
    if nums != list(range(nums[0], nums[0] + len(nums))):
        return None
    return {
        "pattern": f"{prefixes.pop()}{{n}}",
        "base": nums[0],
        "stride": cols,
        "formula": "base + row*stride + col",
    }


def detect_bool_pairs(widgets: list[Widget], words_by_page: dict) -> list[dict]:
    """Two buttons on the same y-band, close together, labelled affirmative /
    negative. Language-agnostic beyond the lexicon."""
    AFF = {"yes", "y", "true", "oui", "ja", "si", "sí"}
    NEG = {"no", "n", "false", "non", "nein"}
    pairs, used = [], set()

    for page in sorted({w.page for w in widgets}):
        btns = [w for w in widgets if w.page == page and w.ftype in ("checkbox", "radio")]
        words = words_by_page[page]
        for a, b in [(a, b) for i, a in enumerate(btns) for b in btns[i + 1 :]]:
            if a.name in used or b.name in used:
                continue
            if abs(a.cy - b.cy) > 6 or abs(a.cx - b.cx) > 240:
                continue
            la = label_for(a, words)["text"].strip().lower().rstrip(":")
            lb = label_for(b, words)["text"].strip().lower().rstrip(":")
            ta = la.split()[-1] if la else ""
            tb = lb.split()[-1] if lb else ""
            if ta in AFF and tb in NEG:
                yes, no = a, b
            elif tb in AFF and ta in NEG:
                yes, no = b, a
            else:
                continue
            used.update({a.name, b.name})
            leftmost = min(a, b, key=lambda w: w.rect[0])
            band = [
                t
                for t in words
                if not (t["y1"] < leftmost.rect[1] - 2 or t["y0"] > leftmost.rect[3] + 2)
                and t["x1"] <= leftmost.rect[0] + 2
            ]
            band.sort(key=lambda t: t["x0"])
            toks = [t["text"] for t in band]
            while toks and toks[-1].strip().lower().rstrip(":") in AFF | NEG:
                toks.pop()
            pairs.append(
                {
                    "yes_widget": yes.name,
                    "no_widget": no.name,
                    "on_state": yes.on_state,
                    "control": "radio_group" if yes.ftype == "radio" else "independent_checkboxes",
                    "page": page,
                    "question_text": " ".join(toks).strip(),
                    "concept": None,  # <- agent fills
                }
            )
    return pairs


def detect_runs(widgets: list[Widget], words_by_page: dict, grid_names: set[str]) -> list[dict]:
    """A narrative answer often spans several stacked single-line widgets.
    Group a widget with the ones directly beneath it that start further left
    (continuation lines run full width)."""
    runs, consumed = [], set()
    for page in sorted({w.page for w in widgets}):
        cand = sorted(
            [w for w in widgets if w.page == page and w.ftype == "text" and w.name not in grid_names],
            key=lambda w: -w.cy,
        )
        words = words_by_page[page]
        for i, wg in enumerate(cand):
            if wg.name in consumed:
                continue
            run = [wg]
            consumed.add(wg.name)
            cur = wg
            for nxt in cand[i + 1 :]:
                if nxt.name in consumed:
                    continue
                dy = cur.cy - nxt.cy
                if not (0 < dy < max(26, cur.h * 2.0)):
                    break
                if nxt.rect[0] > cur.rect[0] + 4:
                    break  # indented -> a new question
                if label_for(nxt, words, left_only=True)["text"].strip():
                    break  # has its own label -> new field
                run.append(nxt)
                consumed.add(nxt.name)
                cur = nxt
            lab = label_for(wg, words)
            runs.append(
                {
                    "widgets": [w.name for w in run],
                    "page": page,
                    "label": lab["text"],
                    "label_source": lab["source"],
                    "multiline_box": wg.multiline,
                    "capacity_chars": [w.capacity(8.5) for w in run],
                    "total_capacity": sum(w.capacity(8.5) for w in run),
                    "concept": None,  # <- agent fills
                    "dtype": None,  # <- agent fills
                }
            )
    return runs


def detect_sections(words_by_page: dict, widgets: list[Widget]) -> list[dict]:
    """Headings = text noticeably larger than the page's modal size."""
    secs = []
    for page, words in words_by_page.items():
        if not words:
            continue
        sizes: dict = defaultdict(int)
        for t in words:
            sizes[t["size"]] += len(t["text"])
        modal = max(sizes.items(), key=lambda kv: kv[1])[0]
        big = [t for t in words if t["size"] >= modal + 2.0]
        rows: dict = defaultdict(list)
        for t in big:
            rows[round(t["y0"] / 4)].append(t)
        for _, row in rows.items():
            row.sort(key=lambda t: t["x0"])
            secs.append(
                {"page": page, "y": round(row[0]["y0"], 1), "size": row[0]["size"], "text": " ".join(t["text"] for t in row)}
            )
    return sorted(secs, key=lambda s: (s["page"], -s["y"]))


# =============================================================================
# 4. DRAFT ASSEMBLY
# =============================================================================

def fingerprint(widgets: list[Widget]) -> str:
    sig = "|".join(
        f"{w.page}:{w.ftype}:{round(w.rect[0])},{round(w.rect[1])}"
        for w in sorted(widgets, key=lambda w: (w.page, -w.cy, w.rect[0]))
    )
    return hashlib.sha256(sig.encode()).hexdigest()[:16]


def build_draft(pdf_bytes: bytes) -> dict:
    """The single entry point: PDF bytes in, a full structural draft out.
    Every widget is present; nothing about MEANING is decided here - every
    'concept'/'dtype' field is left null for the agent to fill via tool
    calls, per skills/dynamic-form-fill/SKILL.md."""
    widgets, pagesizes = inventory(pdf_bytes)
    words = harvest_text(pdf_bytes)

    grids = detect_grids(widgets)
    grid_names = {n for g in grids for row in g["widget_matrix"] for n in row}
    pairs = detect_bool_pairs(widgets, words)
    pair_names = {p["yes_widget"] for p in pairs} | {p["no_widget"] for p in pairs}
    runs = detect_runs(widgets, words, grid_names)
    sections = detect_sections(words, widgets)

    def section_of(page: int, y: float) -> str | None:
        cands = [s for s in sections if s["page"] == page and s["y"] >= y]
        return min(cands, key=lambda s: s["y"] - y)["text"] if cands else None

    widgets_by_name = {w.name: w for w in widgets}
    for r in runs:
        idx = widgets_by_name[r["widgets"][0]]
        r["section"] = section_of(r["page"], idx.cy)
    for p in pairs:
        idx = widgets_by_name[p["yes_widget"]]
        p["section"] = section_of(p["page"], idx.cy)
    for g in grids:
        first = widgets_by_name[g["widget_matrix"][0][0]]
        g["section"] = section_of(g["page"], first.cy)

    covered = grid_names | pair_names | {n for r in runs for n in r["widgets"]}
    unclassified = sorted({w.name for w in widgets} - covered)

    return {
        "blueprint_version": 1,
        "status": "DRAFT_STRUCTURAL",  # becomes SEMANTIC once the agent assigns concepts
        "fingerprint": fingerprint(widgets),
        "pages": {str(k): list(v) for k, v in pagesizes.items()},
        "stats": {
            "widgets": len(widgets),
            "text": sum(w.ftype == "text" for w in widgets),
            "buttons": sum(w.ftype in ("checkbox", "radio") for w in widgets),
            "grids": len(grids),
            "grid_cells": len(grid_names),
            "bool_pairs": len(pairs),
            "runs": len(runs),
            "sections": len(sections),
            "unclassified": len(unclassified),
            "structural_coverage_pct": round(100 * len(covered) / len(widgets), 1) if widgets else 0.0,
        },
        "sections": sections,
        "bool_pairs": pairs,
        "grids": grids,
        "runs": runs,
        "unclassified_widgets": unclassified,
        "widgets": [asdict(w) for w in widgets],
    }
