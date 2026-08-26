"""
Standalone demo of the dynamic-form-fill pipeline against two real AcroForm
PDFs, with no live LLM/Ollama needed.

In production, skills/dynamic-form-fill/SKILL.md drives a WorkspaceAgent
through this same tool sequence (inspect_pdf_form_structure ->
inspect_region_image -> flow_text_into_widgets/fit_grid_row ->
fill_pdf_widgets -> verify_pdf_fill), with the AGENT deciding what each
harvested label means and what value belongs there.

This script performs that same "decide what a label means" step with a
small keyword->value-generator table instead of an LLM, so the rest of the
(real, unmodified) pipeline can be exercised end-to-end and the outputs can
be inspected directly. Nothing here is a template-specific hack: the
classification is driven entirely by the labels/keywords build_draft()
already harvested, the same signal an agent would see.
"""

from __future__ import annotations

import random
from pathlib import Path

from renderers import form_structure
from renderers.form_filler import fill_widgets_precise, fit_cell, flow, read_back_widgets

ROOT = Path(__file__).resolve().parent

INDIAN_FIRST_NAMES = ["Aarav", "Vihaan", "Ishaan", "Ananya", "Diya", "Kavya", "Rohan", "Priya", "Aditya", "Sneha"]
INDIAN_LAST_NAMES = ["Sharma", "Verma", "Iyer", "Reddy", "Nair", "Patel", "Gupta", "Menon", "Rao", "Chatterjee"]
INDIAN_CITIES = [("Mumbai", "Maharashtra", "400001"), ("Bengaluru", "Karnataka", "560001"),
                  ("Chennai", "Tamil Nadu", "600001"), ("Pune", "Maharashtra", "411001")]


def rand_indian_name() -> str:
    return f"{random.choice(INDIAN_FIRST_NAMES)} {random.choice(INDIAN_LAST_NAMES)}"


def rand_indian_phone() -> str:
    return f"+91 {random.randint(70000, 99999)} {random.randint(10000, 99999)}"


def rand_indian_address() -> str:
    city, state, pin = random.choice(INDIAN_CITIES)
    return f"{random.randint(1, 999)} MG Road, {city}, {state} {pin}"


def rand_date() -> str:
    return f"{random.randint(1, 28):02d}/{random.randint(1, 12):02d}/2025"


def rand_policy_no() -> str:
    return f"POL-IN-{random.randint(100000, 999999)}"


def rand_claim_no() -> str:
    return f"CLM-{random.randint(10000, 99999)}"


# (keyword-in-label, value generator) - first match wins, checked in order.
LABEL_RULES = [
    ("policy", rand_policy_no),
    ("claim no", rand_claim_no),
    ("claim number", rand_claim_no),
    ("phone", rand_indian_phone),
    ("telephone", rand_indian_phone),
    ("mobile", rand_indian_phone),
    ("email", lambda: f"{random.choice(INDIAN_FIRST_NAMES).lower()}.{random.choice(INDIAN_LAST_NAMES).lower()}@example.in"),
    ("date", rand_date),
    ("address", rand_indian_address),
    ("city", lambda: random.choice(INDIAN_CITIES)[0]),
    ("state", lambda: random.choice(INDIAN_CITIES)[1]),
    ("zip", lambda: random.choice(INDIAN_CITIES)[2]),
    ("pin", lambda: random.choice(INDIAN_CITIES)[2]),
    ("name", rand_indian_name),
    ("description", lambda: "Synthetic demonstration entry - no real loss or claim."),
    ("amount", lambda: f"Rs. {random.randint(5000, 250000):,}"),
    ("nationality", lambda: "Indian"),
]


def value_for_label(label: str) -> str:
    low = label.lower()
    for keyword, gen in LABEL_RULES:
        if keyword in low:
            return gen()
    return "Synthetic test data"


def fill_form(pdf_path: Path, out_path: Path) -> None:
    pdf_bytes = pdf_path.read_bytes()
    draft = form_structure.build_draft(pdf_bytes)
    print(f"\n=== {pdf_path.name} ===")
    print(f"widgets={draft['stats']['widgets']} runs={len(draft['runs'])} "
          f"grids={len(draft['grids'])} bool_pairs={len(draft['bool_pairs'])}")

    if draft["stats"]["widgets"] == 0:
        print("No AcroForm fields - nothing to fill (flat/scanned PDF).")
        return

    widgets, _ = form_structure.inventory(pdf_bytes)
    index = {w.name: w for w in widgets}

    values: dict[str, str] = {}
    fonts: dict[str, float] = {}

    for run in draft["runs"]:
        ws = [index[n] for n in run["widgets"] if n in index]
        if not ws:
            continue
        text = value_for_label(run["label"])
        v, f, warns = flow(text, ws, 9.0)
        values.update(v)
        fonts.update(f)
        for w in warns:
            print(f"  [warn] {w}")

    for grid in draft["grids"]:
        # Grids carry no single label (column_labels is agent-filled); a live
        # agent would call inspect_region_image on the header row to see what
        # each column means. Standing in for that, alternate a short
        # description/amount pattern across columns by position.
        for row in grid["widget_matrix"]:
            cell_font = 7.0
            texts = {}
            for col, name in enumerate(row):
                if name not in index:
                    continue
                texts[name] = rand_policy_no() if col == 0 else f"Rs. {random.randint(500, 50000):,}"
            for name, text in texts.items():
                size, overflow = fit_cell(text, index[name], cell_font)
                cell_font = min(cell_font, size)
                values[name] = text
            for name in texts:
                fonts[name] = cell_font

    for pair in draft["bool_pairs"]:
        chosen = pair["yes_widget"] if random.random() < 0.5 else pair["no_widget"]
        on_state = pair["on_state"] or "/Yes"
        values[chosen] = on_state

    filled_bytes = fill_widgets_precise(pdf_bytes, values, fonts)
    back = read_back_widgets(filled_bytes)
    mismatches = {k: (v, back.get(k)) for k, v in values.items() if back.get(k) != v}

    out_path.write_bytes(filled_bytes)
    print(f"filled {len(values)} widgets, {len(mismatches)} mismatches after read-back")
    if mismatches:
        for k, (expected, got) in list(mismatches.items())[:5]:
            print(f"  [mismatch] {k}: expected={expected!r} got={got!r}")
    print(f"saved -> {out_path}")


if __name__ == "__main__":
    random.seed()
    fill_form(ROOT / "Property_General_Claim_Form-v3.pdf", ROOT / "filled_property_claim_indian_data.pdf")
    fill_form(ROOT / "downloaded_acroform_test.pdf", ROOT / "filled_downloaded_acroform_test.pdf")
