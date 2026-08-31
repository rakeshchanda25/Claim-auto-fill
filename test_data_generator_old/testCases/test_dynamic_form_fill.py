"""
Tests for the dynamic-form-fill layer: structure discovery, text fitting,
fill, and read-back verification.

These run against the REAL Property_General_Claim_Form-v3.pdf in the repo -
no LLM and no live model needed anywhere, because everything under test here
is the deterministic half (geometry). The agent's half (deciding what each
field means) is what the SKILL.md governs and is not unit-testable without a
live model.

Nothing here asserts on any specific field name or label from that form
beyond what geometry genuinely determines - the whole point is that the code
is template-agnostic, so the tests check structural properties, not a
hardcoded field list.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from renderers import form_structure  # noqa: E402
from renderers.form_filler import (  # noqa: E402
    fill_widgets_precise,
    fit_cell,
    flow,
    read_back_widgets,
)

ACROFORM_PDF = _ROOT / "Property_General_Claim_Form-v3.pdf"
FLAT_PDF = _ROOT / "TATA_AIG_claim_form.pdf"


@pytest.fixture(scope="module")
def acroform_bytes() -> bytes:
    return ACROFORM_PDF.read_bytes()


@pytest.fixture(scope="module")
def draft(acroform_bytes) -> dict:
    return form_structure.build_draft(acroform_bytes)


# =============================================================================
# Structure discovery
# =============================================================================

def test_discovers_widgets_including_kid_widgets(draft):
    # Kid widgets carry no /T of their own; a naive walk misses them and
    # silently loses the repeating grids built from them.
    assert draft["stats"]["widgets"] > 100
    assert draft["stats"]["text"] > 0
    assert draft["stats"]["buttons"] > 0


def test_every_widget_is_structurally_accounted_for(draft):
    assert draft["stats"]["structural_coverage_pct"] == 100.0
    assert draft["unclassified_widgets"] == []


def test_harvests_real_labels_not_widget_names(draft):
    labelled = [r for r in draft["runs"] if r["label"].strip()]
    assert len(labelled) > 10
    # A harvested label must be page text, never the auto-generated internal name.
    for r in labelled:
        assert not r["label"].startswith("Text Field")


def test_detects_repeating_grids_with_a_widget_matrix(draft):
    assert draft["stats"]["grids"] >= 1
    for g in draft["grids"]:
        assert g["rows"] >= 3 and g["cols"] >= 3
        assert len(g["widget_matrix"]) == g["rows"]
        assert all(len(row) == g["cols"] for row in g["widget_matrix"])


def test_detects_yes_no_pairs_with_their_real_on_state(draft):
    assert draft["stats"]["bool_pairs"] >= 1
    for p in draft["bool_pairs"]:
        assert p["yes_widget"] != p["no_widget"]
        # The "ticked" value is whatever the form's author used, NOT "Yes" -
        # assuming "/Yes" is a classic silent-failure cause.
        assert p["on_state"] is None or p["on_state"].startswith("/")
        assert p["control"] in ("radio_group", "independent_checkboxes")


def test_meaning_is_left_for_the_agent_not_decided_here(draft):
    # This layer is deliberately geometry-only: every semantic slot stays null.
    assert draft["status"] == "DRAFT_STRUCTURAL"
    assert all(r["concept"] is None and r["dtype"] is None for r in draft["runs"])
    assert all(p["concept"] is None for p in draft["bool_pairs"])
    assert all(g["concept"] is None for g in draft["grids"])


def test_fingerprint_is_stable_for_the_same_pdf(acroform_bytes):
    a = form_structure.build_draft(acroform_bytes)["fingerprint"]
    b = form_structure.build_draft(acroform_bytes)["fingerprint"]
    assert a == b and len(a) == 16


# =============================================================================
# Text fitting
# =============================================================================

def test_flow_shrinks_font_rather_than_truncating(acroform_bytes, draft):
    widgets, _ = form_structure.inventory(acroform_bytes)
    index = {w.name: w for w in widgets}
    run = next(r for r in draft["runs"] if len(r["widgets"]) == 1)
    ws = [index[n] for n in run["widgets"]]

    long_text = "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor"
    values, fonts, warns = flow(long_text, ws, 9.0)

    assert values, "text must be placed, never dropped"
    # Either it fit at 9pt, or it was shrunk - but the words survive either way.
    assert all(size <= 9.0 for size in fonts.values())
    placed = " ".join(values.values())
    assert long_text.split()[0] in placed


def test_fit_cell_reports_when_text_still_overflows(acroform_bytes, draft):
    widgets, _ = form_structure.inventory(acroform_bytes)
    grid = draft["grids"][0]
    narrow_name = grid["widget_matrix"][0][0]
    w = {x.name: x for x in widgets}[narrow_name]

    size, still_over = fit_cell("x" * 500, w, 7.0)
    assert size <= 7.0
    assert still_over is True  # must be surfaced, not silently clipped


# =============================================================================
# Fill + verify round trip
# =============================================================================

def test_fill_then_read_back_matches(acroform_bytes, draft):
    widgets, _ = form_structure.inventory(acroform_bytes)
    index = {w.name: w for w in widgets}

    values, fonts = {}, {}
    for r in draft["runs"][:6]:
        ws = [index[n] for n in r["widgets"] if n in index]
        if not ws:
            continue
        v, f, _ = flow("SYNTHETIC TEST VALUE", ws, 9.0)
        values.update(v)
        fonts.update(f)

    assert values, "expected at least one fillable run"

    filled = fill_widgets_precise(acroform_bytes, values, fonts)
    back = read_back_widgets(filled)

    for name, expected in values.items():
        assert back.get(name) == expected, f"{name} did not round-trip"


def test_fill_sets_synthetic_provenance_metadata(acroform_bytes, draft):
    from pypdf import PdfReader
    import io

    widgets, _ = form_structure.inventory(acroform_bytes)
    first_run = draft["runs"][0]
    name = first_run["widgets"][0]

    filled = fill_widgets_precise(acroform_bytes, {name: "SYNTHETIC"}, {})
    meta = PdfReader(io.BytesIO(filled)).metadata
    assert "SYNTHETIC" in str(meta.get("/Subject", "")).upper()


def test_flat_pdf_without_acroform_fails_loudly(acroform_bytes):
    # A flat/scanned PDF has no widgets to fill. Failing loudly is correct -
    # silently returning an unchanged file would look like success.
    flat_bytes = FLAT_PDF.read_bytes()
    with pytest.raises(ValueError, match="no /AcroForm"):
        fill_widgets_precise(flat_bytes, {"anything": "value"}, {})


def test_flat_pdf_structure_scan_reports_zero_widgets():
    # build_draft itself does not raise - it honestly reports "nothing here",
    # which is what lets the agent detect the situation and say so.
    draft = form_structure.build_draft(FLAT_PDF.read_bytes())
    assert draft["stats"]["widgets"] == 0
