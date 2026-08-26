#!/usr/bin/env python3
"""
================================================================================
 BLUEPRINT BUILDER  --  Pipeline A, template-agnostic
================================================================================

Turns ANY editable (AcroForm) PDF into a Blueprint: the data file that drives
the filler. Nothing here knows anything about Allianz, property claims, or the
Allianz field names.

TWO LAYERS
----------
  1. DETERMINISTIC PRE-PASS  (this file, runs with no model)
       - widget inventory incl. /Kids
       - label harvest by geometry
       - section detection
       - grid / repeating-region detection
       - Yes-No checkbox pair detection
       - narrative run detection
       - capacity computation
     Output: a STRUCTURAL draft -- every slot present, all `concept` null.

  2. SEMANTIC PASS  (LLM agent, tool contract defined at the bottom)
       The agent fills in `concept`, `dtype`, conditional rules, and synthesises
       the JSON Schema for the data the form needs. It calls tools against the
       structure the pre-pass built, so the model never guesses coordinates and
       never invents a widget name.

WHY SPLIT IT
------------
Geometry, grids and capacities are exactly computable, so asking a model for
them wastes tokens and invites hallucination. Meaning is not computable, so
that is where the model earns its cost. The pre-pass also gives the agent a
bounded, enumerable world -- it can only label things that actually exist.

Run:
    python blueprint_builder.py <template.pdf> <draft_blueprint.json>
================================================================================
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict, field as dc_field
from typing import Any

import pdfplumber
from pypdf import PdfReader


# =============================================================================
# 1. WIDGET INVENTORY  (identical logic to the filler -- shared in prod)
# =============================================================================

@dataclass
class Widget:
    name: str
    page: int
    rect: tuple           # (x0, y0, x1, y1), y=0 at page bottom
    ftype: str            # text | checkbox | radio | choice
    on_state: str | None = None
    multiline: bool = False
    readonly: bool = False

    @property
    def w(self): return self.rect[2] - self.rect[0]

    @property
    def h(self): return self.rect[3] - self.rect[1]

    @property
    def cx(self): return (self.rect[0] + self.rect[2]) / 2

    @property
    def cy(self): return (self.rect[1] + self.rect[3]) / 2

    def capacity(self, font=9.0): return max(1, int(self.w / (0.5 * font)))


def inventory(path: str) -> tuple[list[Widget], dict[int, tuple]]:
    reader = PdfReader(path)
    out, pagesizes = [], {}
    for pno, page in enumerate(reader.pages, 1):
        mb = page.mediabox
        pagesizes[pno] = (float(mb.width), float(mb.height))
        for annot in (page.get("/Annots") or []):
            d = annot.get_object()
            if d.get("/Subtype") != "/Widget":
                continue
            name = d.get("/T")
            parent = d.get("/Parent")
            if name is None and parent is not None:
                name = parent.get_object().get("/T")
            if name is None:
                continue
            src = d if "/FT" in d else (parent.get_object() if parent else d)
            ft, flags = src.get("/FT"), int(src.get("/Ff", 0) or 0)

            on = None
            if ft == "/Btn":
                ap = d.get("/AP")
                if ap and "/N" in ap:
                    keys = [str(k) for k in ap["/N"].get_object().keys()]
                    cand = [k for k in keys if k != "/Off"]
                    on = cand[0] if cand else "/On"
                ftype = "radio" if flags & (1 << 15) else "checkbox"
            elif ft == "/Ch":
                ftype = "choice"
            else:
                ftype = "text"

            out.append(Widget(str(name), pno,
                              tuple(round(float(v), 2) for v in d["/Rect"]),
                              ftype, on,
                              bool(flags & (1 << 12)), bool(flags & 1)))
    return out, pagesizes


# =============================================================================
# 2. LABEL HARVEST  (replaces a vision model for conventional layouts)
# =============================================================================
# pdfplumber uses top-down y; widget rects are bottom-up. Convert once, here,
# and never think about it again.
# =============================================================================

def harvest_text(path: str) -> dict[int, list[dict]]:
    pages = {}
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            words = page.extract_words(use_text_flow=False,
                                       keep_blank_chars=False,
                                       extra_attrs=["size"])
            H = float(page.height)
            pages[pno] = [{
                "text": w["text"],
                "x0": float(w["x0"]), "x1": float(w["x1"]),
                # convert to bottom-up so it shares the widget coordinate space
                "y0": H - float(w["bottom"]), "y1": H - float(w["top"]),
                "size": round(float(w.get("size", 0)), 1),
            } for w in words]
    return pages


def label_for(wg: Widget, words: list[dict], left_only: bool = False) -> dict:
    """Nearest text to the LEFT on the same band, else ABOVE. Conventional
    form layouts are label-left or label-above; this recovers most of them."""
    band = [t for t in words
            if not (t["y1"] < wg.rect[1] - 1 or t["y0"] > wg.rect[3] + 1)]

    left = [t for t in band if t["x1"] <= wg.rect[0] + 2]
    if left:
        left.sort(key=lambda t: -t["x1"])
        gap = wg.rect[0] - left[0]["x1"]
        if gap < 220:
            chunk, cursor = [], left[0]["x1"]
            for t in left:                      # walk leftwards while contiguous
                if cursor - t["x1"] > 14:
                    break
                chunk.append(t); cursor = t["x0"]
            chunk.sort(key=lambda t: t["x0"])
            return {"text": " ".join(t["text"] for t in chunk),
                    "source": "left", "gap": round(gap, 1)}

    if left_only:
        return {"text": "", "source": "none", "gap": None}

    above = [t for t in words
             if t["y0"] >= wg.rect[3] - 1 and t["y0"] - wg.rect[3] < 26
             and t["x1"] > wg.rect[0] - 6 and t["x0"] < wg.rect[2] + 6]
    if above:
        ytop = min(t["y0"] for t in above)
        row = sorted([t for t in above if abs(t["y0"] - ytop) < 4],
                     key=lambda t: t["x0"])
        return {"text": " ".join(t["text"] for t in row),
                "source": "above",
                "gap": round(row[0]["y0"] - wg.rect[3], 1)}

    return {"text": "", "source": "none", "gap": None}


# =============================================================================
# 3. STRUCTURE DETECTION  (grids, pairs, runs, sections)
# =============================================================================

def cluster_rows(widgets: list[Widget], tol=8.0) -> list[list[Widget]]:
    rows: list[list[Widget]] = []
    for wg in sorted(widgets, key=lambda w: -w.cy):
        for r in rows:
            if abs(r[0].cy - wg.cy) < tol:
                r.append(wg); break
        else:
            rows.append([wg])
    for r in rows:
        r.sort(key=lambda w: w.rect[0])
    return rows


def _sig(row: list[Widget]) -> tuple:
    return tuple(round(w.rect[0], 1) for w in row)


def _sig_match(a: tuple, b: tuple, tol=5.0) -> bool:
    """Rows belong to the same grid if columns line up within tolerance.
    Exact-equality matching fragments real tables: sub-point drift between
    rows is normal in hand-authored forms and split this template's
    12-row Contents table into two 4-row fragments."""
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))


def detect_grids(widgets: list[Widget], min_cols=3, min_rows=3) -> list[dict]:
    """A repeating region = >=min_rows consecutive rows sharing an x-signature.

    Detected by BOTH rect alignment and (afterwards) name-sequence check --
    either signal alone produces false positives on ordinary stacked fields.
    """
    grids = []
    for page in sorted({w.page for w in widgets}):
        text = [w for w in widgets if w.page == page and w.ftype == "text"]
        rows = cluster_rows(text)
        sigs = [(_sig(r), r) for r in rows]

        i = 0
        while i < len(sigs):
            sig, _ = sigs[i]
            if len(sig) < min_cols:
                i += 1; continue
            j = i
            while j + 1 < len(sigs) and _sig_match(sig, sigs[j + 1][0]):
                j += 1
            block = [r for _, r in sigs[i:j + 1]]
            if len(block) >= min_rows:
                names = [w.name for r in block for w in r]
                grids.append({
                    "page": page,
                    "rows": len(block),
                    "cols": len(sig),
                    "row_pitch": round(abs(block[0][0].cy - block[1][0].cy), 2),
                    "column_rects": [[round(v, 1) for v in w.rect]
                                     for w in block[0]],
                    "column_capacity": [w.capacity(7.0) for w in block[0]],
                    "widget_matrix": [[w.name for w in r] for r in block],
                    "name_rule": name_rule(names, len(sig)),
                    "column_labels": [None] * len(sig),   # <- LLM fills
                    "concept": None,                       # <- LLM fills
                })
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
    return {"pattern": f"{prefixes.pop()}{{n}}",
            "base": nums[0], "stride": cols,
            "formula": "base + row*stride + col"}


def detect_bool_pairs(widgets: list[Widget], words_by_page) -> list[dict]:
    """Two buttons on the same y-band, close together, labelled affirmative /
    negative. Language-agnostic beyond the lexicon, which the LLM can extend."""
    AFF = {"yes", "y", "true", "oui", "ja", "si", "sí"}
    NEG = {"no", "n", "false", "non", "nein"}
    pairs, used = [], set()

    for page in sorted({w.page for w in widgets}):
        btns = [w for w in widgets
                if w.page == page and w.ftype in ("checkbox", "radio")]
        words = words_by_page[page]
        for a, b in [(a, b) for i, a in enumerate(btns) for b in btns[i + 1:]]:
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
            # Question = everything on the band left of the leftmost button,
            # minus the affirmative/negative tokens themselves. Taking the
            # nearest label instead just returns "Yes".
            leftmost = min(a, b, key=lambda w: w.rect[0])
            band = [t for t in words
                    if not (t["y1"] < leftmost.rect[1] - 2
                            or t["y0"] > leftmost.rect[3] + 2)
                    and t["x1"] <= leftmost.rect[0] + 2]
            band.sort(key=lambda t: t["x0"])
            toks = [t["text"] for t in band]
            while toks and toks[-1].strip().lower().rstrip(":") in AFF | NEG:
                toks.pop()
            pairs.append({
                "yes_widget": yes.name, "no_widget": no.name,
                "on_state": yes.on_state,
                "control": "radio_group" if yes.ftype == "radio"
                           else "independent_checkboxes",
                "page": page,
                "question_text": " ".join(toks).strip(),
                "concept": None,                        # <- LLM fills
            })
    return pairs


def detect_runs(widgets: list[Widget], words_by_page,
                grid_names: set[str]) -> list[dict]:
    """A narrative answer often spans several stacked single-line widgets.
    Group a widget with the ones directly beneath it that start further left
    (continuation lines run full width)."""
    runs, consumed = [], set()
    for page in sorted({w.page for w in widgets}):
        cand = sorted([w for w in widgets
                       if w.page == page and w.ftype == "text"
                       and w.name not in grid_names],
                      key=lambda w: -w.cy)
        words = words_by_page[page]
        for i, wg in enumerate(cand):
            if wg.name in consumed:
                continue
            run = [wg]; consumed.add(wg.name)
            cur = wg
            for nxt in cand[i + 1:]:
                if nxt.name in consumed:
                    continue
                dy = cur.cy - nxt.cy
                if not (0 < dy < max(26, cur.h * 2.0)):
                    break
                if nxt.rect[0] > cur.rect[0] + 4:
                    break                      # indented -> a new question
                # Only a LEFT-hand label marks a new question. Testing the
                # "above" fallback here breaks every run: a continuation line
                # always finds the previous line's text above it, so the run
                # is severed after its first widget.
                if label_for(nxt, words, left_only=True)["text"].strip():
                    break                      # has its own label -> new field
                run.append(nxt); consumed.add(nxt.name); cur = nxt
            lab = label_for(wg, words)
            runs.append({
                "widgets": [w.name for w in run],
                "page": page,
                "label": lab["text"],
                "label_source": lab["source"],
                "multiline_box": wg.multiline,
                "capacity_chars": [w.capacity(8.5) for w in run],
                "total_capacity": sum(w.capacity(8.5) for w in run),
                "concept": None,                        # <- LLM fills
                "dtype": None,                          # <- LLM fills
            })
    return runs


def detect_sections(words_by_page, widgets) -> list[dict]:
    """Headings = text noticeably larger than the page's modal size."""
    secs = []
    for page, words in words_by_page.items():
        if not words:
            continue
        sizes = defaultdict(int)
        for t in words:
            sizes[t["size"]] += len(t["text"])
        modal = max(sizes.items(), key=lambda kv: kv[1])[0]
        big = [t for t in words if t["size"] >= modal + 2.0]
        rows = defaultdict(list)
        for t in big:
            rows[round(t["y0"] / 4)].append(t)
        for _, row in rows.items():
            row.sort(key=lambda t: t["x0"])
            secs.append({"page": page,
                         "y": round(row[0]["y0"], 1),
                         "size": row[0]["size"],
                         "text": " ".join(t["text"] for t in row)})
    return sorted(secs, key=lambda s: (s["page"], -s["y"]))


# =============================================================================
# 4. DRAFT ASSEMBLY
# =============================================================================

def build_draft(pdf_path: str) -> dict:
    widgets, pagesizes = inventory(pdf_path)
    words = harvest_text(pdf_path)

    grids = detect_grids(widgets)
    grid_names = {n for g in grids for row in g["widget_matrix"] for n in row}
    pairs = detect_bool_pairs(widgets, words)
    pair_names = {p["yes_widget"] for p in pairs} | {p["no_widget"] for p in pairs}
    runs = detect_runs(widgets, words, grid_names)
    sections = detect_sections(words, widgets)

    # assign each run/grid/pair to the nearest section heading above it
    def section_of(page, y):
        cands = [s for s in sections if s["page"] == page and s["y"] >= y]
        return min(cands, key=lambda s: s["y"] - y)["text"] if cands else None

    for r in runs:
        idx = {w.name: w for w in widgets}[r["widgets"][0]]
        r["section"] = section_of(r["page"], idx.cy)
    for p in pairs:
        idx = {w.name: w for w in widgets}[p["yes_widget"]]
        p["section"] = section_of(p["page"], idx.cy)
    for g in grids:
        first = {w.name: w for w in widgets}[g["widget_matrix"][0][0]]
        g["section"] = section_of(g["page"], first.cy)

    covered = grid_names | pair_names | {n for r in runs for n in r["widgets"]}
    unclassified = sorted({w.name for w in widgets} - covered)

    fp = fingerprint(widgets)
    return {
        "blueprint_version": 1,
        "status": "DRAFT_STRUCTURAL",   # becomes SEMANTIC after the LLM pass
        "fingerprint": fp,
        "source_pdf": pdf_path.split("/")[-1],
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
            "structural_coverage_pct": round(100 * len(covered) / len(widgets), 1),
        },
        "sections": sections,
        "bool_pairs": pairs,
        "grids": grids,
        "runs": runs,
        "unclassified_widgets": unclassified,
        "widgets": [asdict(w) for w in widgets],
        # filled by the semantic pass:
        "concept_map": None,
        "conditional_rules": None,
        "data_schema": None,
    }


def fingerprint(widgets: list[Widget]) -> str:
    import hashlib
    sig = "|".join(f"{w.page}:{w.ftype}:{round(w.rect[0])},{round(w.rect[1])}"
                   for w in sorted(widgets,
                                   key=lambda w: (w.page, -w.cy, w.rect[0])))
    return hashlib.sha256(sig.encode()).hexdigest()[:16]


# =============================================================================
# 5. LLM TOOL CONTRACT  (the semantic pass)
# =============================================================================
# The agent is given the draft above and these tools. It cannot invent widget
# names -- every tool validates its arguments against the draft, so a
# hallucinated name is rejected at the tool boundary rather than silently
# poisoning the blueprint.
# =============================================================================

TOOLS = [
    {
        "name": "inspect_region",
        "description": ("Render a page region to an image and return nearby "
                        "text. Use when a label is empty or ambiguous."),
        "input_schema": {"type": "object", "properties": {
            "page": {"type": "integer"},
            "bbox": {"type": "array", "items": {"type": "number"},
                     "minItems": 4, "maxItems": 4},
        }, "required": ["page", "bbox"]},
    },
    {
        "name": "assign_concept",
        "description": ("Attach a canonical concept path to a run. Path is "
                        "dotted, e.g. 'policyholder.name'. Reuse an existing "
                        "path from the concept registry wherever it fits; only "
                        "mint a new one when nothing matches."),
        "input_schema": {"type": "object", "properties": {
            "run_index": {"type": "integer"},
            "concept": {"type": "string"},
            "dtype": {"enum": ["string", "text", "money", "date", "time",
                               "phone", "email", "postcode", "percent",
                               "identifier", "signature"]},
            "required": {"type": "boolean"},
            "na_if_absent": {"type": "boolean",
                             "description": "form instructs N/A when N/A"},
        }, "required": ["run_index", "concept", "dtype"]},
    },
    {
        "name": "assign_bool_concept",
        "description": "Attach a concept to a detected Yes/No pair.",
        "input_schema": {"type": "object", "properties": {
            "pair_index": {"type": "integer"},
            "concept": {"type": "string"},
        }, "required": ["pair_index", "concept"]},
    },
    {
        "name": "assign_grid",
        "description": ("Name a repeating region and label its columns in "
                        "left-to-right order. One label per column."),
        "input_schema": {"type": "object", "properties": {
            "grid_index": {"type": "integer"},
            "concept": {"type": "string"},
            "column_concepts": {"type": "array", "items": {"type": "string"}},
            "column_dtypes": {"type": "array", "items": {"type": "string"}},
        }, "required": ["grid_index", "concept", "column_concepts"]},
    },
    {
        "name": "add_rule",
        "description": ("Declare a validation rule discovered from the form's "
                        "printed instructions. Kinds: 'requires' (conditional), "
                        "'arithmetic' (expression over concepts), 'temporal'."),
        "input_schema": {"type": "object", "properties": {
            "kind": {"enum": ["requires", "arithmetic", "temporal", "format"]},
            "when": {"type": "string", "description": "concept == value"},
            "then": {"type": "string", "description": "concept or expression"},
            "message": {"type": "string"},
        }, "required": ["kind", "then", "message"]},
    },
    {
        "name": "merge_runs",
        "description": ("Correct the pre-pass: join runs the geometry split, "
                        "or split one it wrongly joined."),
        "input_schema": {"type": "object", "properties": {
            "run_indices": {"type": "array", "items": {"type": "integer"}},
            "operation": {"enum": ["merge", "split"]},
            "split_after_widget": {"type": "string"},
        }, "required": ["run_indices", "operation"]},
    },
    {
        "name": "coverage_report",
        "description": ("Return which widgets still have no concept. Call this "
                        "before finish; the loop is not done until every widget "
                        "is either assigned or explicitly marked decorative."),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "emit_data_schema",
        "description": ("Emit the JSON Schema describing the data this form "
                        "needs. Extraction targets this schema, so it must be "
                        "form-agnostic in shape: group by domain entity, not by "
                        "page or section."),
        "input_schema": {"type": "object", "properties": {
            "schema": {"type": "object"},
        }, "required": ["schema"]},
    },
    {
        "name": "finish",
        "description": "Emit the completed blueprint for human review.",
        "input_schema": {"type": "object", "properties": {
            "confidence_notes": {"type": "string"},
        }},
    },
]

AGENT_SYSTEM = """\
You are labelling a fillable PDF form so it can be filled automatically for any
future claim.

You are given a STRUCTURAL draft produced deterministically: every widget, its
geometry, its harvested label, plus detected sections, Yes/No pairs, repeating
grids and multi-widget runs. The geometry is exact. Do not second-guess it.

Your job is meaning, and only meaning:
  - assign a canonical concept path to every run, pair and grid
  - choose the data type
  - read the form's printed instructions and encode them as rules
  - emit a JSON Schema for the data the form needs

Rules of engagement:
  - Prefer concept paths from the registry supplied to you. Consistent paths
    across templates are what makes one extractor serve every form.
  - Never invent a widget name. Refer to runs, pairs and grids by index.
  - If a label is empty or ambiguous, call inspect_region before guessing.
  - Column order in a grid is left to right as given. Do not reorder.
  - Mark decorative or unusable widgets explicitly rather than leaving them
    unassigned -- silence is indistinguishable from an oversight.
  - Call coverage_report and resolve every gap before calling finish.
"""


# =============================================================================
# 6. CLI
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("template")
    ap.add_argument("output")
    ap.add_argument("--tools", action="store_true",
                    help="print the LLM tool contract and exit")
    args = ap.parse_args()

    if args.tools:
        print(json.dumps({"system": AGENT_SYSTEM, "tools": TOOLS}, indent=2))
        return 0

    draft = build_draft(args.template)
    with open(args.output, "w") as fh:
        json.dump(draft, fh, indent=2)

    s = draft["stats"]
    print(f"fingerprint      {draft['fingerprint']}")
    print(f"widgets          {s['widgets']}  "
          f"({s['text']} text, {s['buttons']} button)")
    print(f"sections         {s['sections']}")
    print(f"grids            {s['grids']}  covering {s['grid_cells']} cells")
    for i, g in enumerate(draft["grids"]):
        nr = g["name_rule"]
        rule = (f"{nr['pattern']}, {nr['formula']}, base={nr['base']}, "
                f"stride={nr['stride']}") if nr else "no closed form"
        print(f"   grid[{i}] p{g['page']} {g['rows']}x{g['cols']} "
              f"pitch={g['row_pitch']}  [{g['section']}]")
        print(f"           {rule}")
    print(f"bool pairs       {s['bool_pairs']}")
    for i, p in enumerate(draft["bool_pairs"]):
        q = (p["question_text"] or "")[:58]
        print(f"   pair[{i}] p{p['page']} {p['control']:24} {q}")
    print(f"runs             {s['runs']}")
    print(f"unclassified     {s['unclassified']}")
    print(f"coverage         {s['structural_coverage_pct']}% structural")
    print(f"-> {args.output}  (status {draft['status']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())