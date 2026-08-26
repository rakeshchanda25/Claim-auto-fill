"""
Tests for the @tool-decorated wrappers in ai_doc_generator/tools.py that
back skills/dynamic-form-fill. Calls each tool function directly (the
`tool` decorator falls back to identity when the andromeda package/its
optional deps aren't importable, which is exactly the case in this
sandbox - the same fallback ai_doc_generator/tools.py itself already
defines), so this exercises the real tool bodies without needing a live
Agent or Ollama.

The reference-consuming tools (inspect_pdf_form_structure,
inspect_region_image, flow_text_into_widgets, fit_grid_row,
fill_pdf_widgets) take NO pdf_bytes argument - a tool-calling LLM cannot
transcribe a PDF's raw bytes as a JSON argument, so they read a staged
"current reference document" instead (tools.set_reference_document, held
for the run by agent_factory.run_with_reference in real requests). Tests
stage it themselves via the `staged_pdf` fixture.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# WeasyPrint needs system libs not present in this sandbox; stub it so
# ai_doc_generator.tools (which imports renderers.html_renderer transitively)
# can still be imported. Unrelated to anything under test here.
if "weasyprint" not in sys.modules:
    _fake_weasyprint = types.ModuleType("weasyprint")
    _fake_weasyprint.HTML = object
    sys.modules["weasyprint"] = _fake_weasyprint

from ai_doc_generator import tools  # noqa: E402

ACROFORM_PDF = _ROOT / "Property_General_Claim_Form-v3.pdf"
FLAT_PDF = _ROOT / "TATA_AIG_claim_form.pdf"


@pytest.fixture
def staged_pdf():
    """Stages Property_General_Claim_Form-v3.pdf as the current request's
    reference document, and un-stages it afterwards so tests don't leak
    state into each other."""
    tools.set_reference_document(ACROFORM_PDF.read_bytes())
    try:
        yield
    finally:
        tools.set_reference_document(None)


def test_inspect_pdf_form_structure_returns_the_real_draft(staged_pdf):
    draft = tools.inspect_pdf_form_structure()
    assert draft["stats"]["widgets"] > 100
    assert draft["status"] == "DRAFT_STRUCTURAL"


def test_flow_text_into_widgets_places_text_and_returns_font(staged_pdf):
    draft = tools.inspect_pdf_form_structure()
    run = next(r for r in draft["runs"] if r["widgets"])

    result = tools.flow_text_into_widgets(run["widgets"], "Synthetic answer text")

    assert result["values"], "expected at least one widget filled"
    assert result["fonts"]
    assert isinstance(result["warnings"], list)


def test_flow_text_into_widgets_handles_unknown_widget_names_gracefully(staged_pdf):
    result = tools.flow_text_into_widgets(["Does Not Exist 999"], "text")
    assert result["values"] == {}
    assert result["warnings"]  # explicit, not silent


def test_fit_grid_row_returns_one_common_font_for_the_row(staged_pdf):
    draft = tools.inspect_pdf_form_structure()
    grid = draft["grids"][0]
    row = grid["widget_matrix"][0]
    cells = [f"cell {i}" for i in range(len(row))]

    result = tools.fit_grid_row(row, cells)

    assert set(result["fonts"].values()) == {list(result["fonts"].values())[0]}, "must be ONE font for the whole row"
    assert result["values"] == dict(zip(row, cells))


def test_fill_pdf_widgets_then_verify_pdf_fill_round_trips(staged_pdf):
    draft = tools.inspect_pdf_form_structure()
    run = next(r for r in draft["runs"] if r["widgets"])
    fitted = tools.flow_text_into_widgets(run["widgets"], "Synthetic value")

    filled = tools.fill_pdf_widgets(fitted["values"], fitted["fonts"])
    verification = tools.verify_pdf_fill(filled, fitted["values"])

    assert verification["ok"] is True
    assert verification["mismatches"] == {}


def test_verify_pdf_fill_reports_a_real_mismatch(staged_pdf):
    draft = tools.inspect_pdf_form_structure()
    run = next(r for r in draft["runs"] if r["widgets"])
    filled = tools.fill_pdf_widgets({run["widgets"][0]: "actual value"}, {})

    verification = tools.verify_pdf_fill(filled, {run["widgets"][0]: "expected different value"})

    assert verification["ok"] is False
    assert run["widgets"][0] in verification["mismatches"]


def test_inspect_pdf_form_structure_on_flat_pdf_reports_no_widgets():
    # Confirms the tool layer surfaces the same honest "nothing to fill"
    # signal as the underlying module, rather than masking it.
    tools.set_reference_document(FLAT_PDF.read_bytes())
    try:
        draft = tools.inspect_pdf_form_structure()
    finally:
        tools.set_reference_document(None)
    assert draft["stats"]["widgets"] == 0


def test_inspect_pdf_form_structure_without_a_staged_document_raises():
    # Mirrors what happens if fill mode somehow runs with no upload at all -
    # must fail loudly, not silently fall through to generating something.
    with pytest.raises(ValueError, match="No reference document"):
        tools.inspect_pdf_form_structure()


def test_inspect_region_image_returns_a_real_png(staged_pdf):
    draft = tools.inspect_pdf_form_structure()
    widget = draft["widgets"][0]

    result = tools.inspect_region_image(page=widget["page"], bbox=widget["rect"])

    import base64
    png_bytes = base64.b64decode(result["image_base64_png"])
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"  # real PNG signature, not a placeholder
    assert isinstance(result["nearby_text"], str)
