"""
Tests for the @tool-decorated wrappers in ai_doc_generator/tools.py that
back skills/dynamic-docx-fill. Same rationale as
test_dynamic_form_fill_tools.py: stub weasyprint (unrelated, only needed
because tools.py transitively imports renderers.html_renderer) and call the
tool functions directly - no live Agent/Ollama needed.

inspect_docx_form_structure / fill_docx_form_controls take NO docx_bytes
argument - a tool-calling LLM cannot transcribe a docx's raw bytes as a JSON
argument, so they read a staged "current reference document" instead
(tools.set_reference_document). Tests stage it via the `staged_docx` fixture.

Symmetrically, fill_docx_form_controls does not RETURN the filled docx's
bytes either - it stages the result (tools.stage_artifact) and
verify_docx_fill reads that staged result instead of taking it as an
argument. Tests read the staged bytes back via tools.get_staged_artifact().
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

if "weasyprint" not in sys.modules:
    _fake_weasyprint = types.ModuleType("weasyprint")
    _fake_weasyprint.HTML = object
    sys.modules["weasyprint"] = _fake_weasyprint

from ai_doc_generator import tools  # noqa: E402
from test_dynamic_docx_fill import build_fixture_docx  # noqa: E402


@pytest.fixture
def staged_docx():
    """Stages the synthetic content-control fixture docx as the current
    request's reference document, and un-stages it afterwards."""
    tools.set_reference_document(build_fixture_docx())
    try:
        yield
    finally:
        tools.set_reference_document(None)
        tools.clear_staged_artifact()


def test_inspect_docx_form_structure_returns_the_real_draft(staged_docx):
    draft = tools.inspect_docx_form_structure()
    assert draft["stats"]["controls"] == 4
    assert draft["status"] == "DRAFT_STRUCTURAL"


def test_fill_docx_form_controls_then_verify_round_trips(staged_docx):
    values = {"full_name": "Rohan Verma"}
    checks = {"is_policyholder": True}
    choices = {"state": "Tamil Nadu"}

    status = tools.fill_docx_form_controls(values, checks, choices)
    assert status["status"] == "staged" and status["kind"] == "docx"
    verification = tools.verify_docx_fill({**values, **checks, **choices})

    assert verification["ok"] is True
    assert verification["mismatches"] == {}

    staged_bytes, staged_kind = tools.get_staged_artifact()
    assert staged_kind == "docx"
    assert staged_bytes[:2] == b"PK"  # docx is a zip archive


def test_verify_docx_fill_reports_a_real_mismatch(staged_docx):
    tools.fill_docx_form_controls({"full_name": "actual value"})
    verification = tools.verify_docx_fill({"full_name": "expected different value"})

    assert verification["ok"] is False
    assert "full_name" in verification["mismatches"]


def test_verify_docx_fill_without_a_staged_result_raises(staged_docx):
    tools.clear_staged_artifact()
    with pytest.raises(ValueError, match="No document has been staged"):
        tools.verify_docx_fill({"anything": "value"})


def test_inspect_docx_form_structure_on_plain_docx_reports_zero_controls():
    from docx import Document
    import io

    plain = Document()
    plain.add_paragraph("No form fields in this one.")
    buf = io.BytesIO()
    plain.save(buf)

    tools.set_reference_document(buf.getvalue())
    try:
        draft = tools.inspect_docx_form_structure()
    finally:
        tools.set_reference_document(None)
    assert draft["stats"]["controls"] == 0


def test_inspect_docx_form_structure_without_a_staged_document_raises():
    with pytest.raises(ValueError, match="No reference document"):
        tools.inspect_docx_form_structure()
