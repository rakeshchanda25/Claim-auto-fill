"""
Tests for the packet-staging accumulator in ai_doc_generator/tools.py
(stage_packet_component / get_staged_packet / clear_staged_packet).

Packet mode renders N documents in one agent run. render_document_to_pdf's
single staging slot (tools.stage_artifact) holds only one document at a
time - the bug this accumulator fixes is that calling it a second time for
component 2 used to silently overwrite component 1, so only the LAST
component of any packet ever survived to the zip. stage_packet_component
moves each render out of that single slot into a list before the next
render can clobber it.

These tests exercise the accumulator directly via tools.stage_artifact
(the same primitive render_document_to_pdf calls internally) rather than
render_document_to_pdf itself, since that needs a working WeasyPrint this
sandbox doesn't have - the accumulator logic under test here doesn't touch
WeasyPrint at all.
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


@pytest.fixture(autouse=True)
def _clean_staging():
    tools.clear_staged_artifact()
    tools.clear_staged_packet()
    yield
    tools.clear_staged_artifact()
    tools.clear_staged_packet()


def test_stage_packet_component_moves_the_single_slot_into_the_list():
    tools.stage_artifact(b"pdf-bytes-1", "pdf")
    result = tools.stage_packet_component("Medical Bill")

    assert result["status"] == "added_to_packet"
    assert result["components_so_far"] == 1
    assert tools.get_staged_artifact() == (None, None), "single slot must be freed for the next render"

    packet = tools.get_staged_packet()
    assert packet == [{"label": "Medical Bill", "kind": "pdf", "bytes": b"pdf-bytes-1"}]


def test_multiple_components_accumulate_instead_of_overwriting():
    tools.stage_artifact(b"pdf-bytes-1", "pdf")
    tools.stage_packet_component("Medical Bill")
    tools.stage_artifact(b"pdf-bytes-2", "pdf")
    tools.stage_packet_component("Clinical Notes")
    tools.stage_artifact(b"pdf-bytes-3", "pdf")
    tools.stage_packet_component("CMS-1500")

    packet = tools.get_staged_packet()
    assert [c["label"] for c in packet] == ["Medical Bill", "Clinical Notes", "CMS-1500"]
    assert [c["bytes"] for c in packet] == [b"pdf-bytes-1", b"pdf-bytes-2", b"pdf-bytes-3"]


def test_stage_packet_component_without_a_render_raises():
    with pytest.raises(ValueError, match="No document has been staged"):
        tools.stage_packet_component("Medical Bill")


def test_clear_staged_packet_resets_to_none():
    tools.stage_artifact(b"pdf-bytes", "pdf")
    tools.stage_packet_component("Medical Bill")
    assert tools.get_staged_packet() is not None

    tools.clear_staged_packet()
    assert tools.get_staged_packet() is None
