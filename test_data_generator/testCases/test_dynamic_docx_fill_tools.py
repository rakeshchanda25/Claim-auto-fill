"""
Tests for the @tool-decorated wrappers in ai_doc_generator/tools.py that
back skills/dynamic-docx-fill. Same rationale as
test_dynamic_form_fill_tools.py: stub weasyprint (unrelated, only needed
because tools.py transitively imports renderers.html_renderer) and call the
tool functions directly - no live Agent/Ollama needed.
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


@pytest.fixture(scope="module")
def docx_bytes() -> bytes:
    return build_fixture_docx()


def test_inspect_docx_form_structure_returns_the_real_draft(docx_bytes):
    draft = tools.inspect_docx_form_structure(docx_bytes)
    assert draft["stats"]["controls"] == 4
    assert draft["status"] == "DRAFT_STRUCTURAL"


def test_fill_docx_form_controls_then_verify_round_trips(docx_bytes):
    values = {"full_name": "Rohan Verma"}
    checks = {"is_policyholder": True}
    choices = {"state": "Tamil Nadu"}

    filled = tools.fill_docx_form_controls(docx_bytes, values, checks, choices)
    verification = tools.verify_docx_fill(filled, {**values, **checks, **choices})

    assert verification["ok"] is True
    assert verification["mismatches"] == {}


def test_verify_docx_fill_reports_a_real_mismatch(docx_bytes):
    filled = tools.fill_docx_form_controls(docx_bytes, {"full_name": "actual value"})
    verification = tools.verify_docx_fill(filled, {"full_name": "expected different value"})

    assert verification["ok"] is False
    assert "full_name" in verification["mismatches"]


def test_inspect_docx_form_structure_on_plain_docx_reports_zero_controls():
    from docx import Document
    import io

    plain = Document()
    plain.add_paragraph("No form fields in this one.")
    buf = io.BytesIO()
    plain.save(buf)

    draft = tools.inspect_docx_form_structure(buf.getvalue())
    assert draft["stats"]["controls"] == 0
