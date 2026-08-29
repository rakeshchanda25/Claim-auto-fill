"""
Tests for packet building in ai_doc_generator/tools.py (build_packet /
render_packet).

Two things are being guarded here, one correctness and one cost:

CORRECTNESS - every document in a packet must describe the SAME claim.
build_packet used to call build_synthetic_data once per component, each of
which draws a fresh random patient, and (when seeded) deliberately varied the
seed per component as `seed + comp["order"]`. A five-document "Medical Claims
Packet" therefore contained five different patients with five different MRNs -
worthless as IDP test data, since cross-document entity matching is the main
thing such a packet exists to exercise.

COST - build_packet used to return every component's full data dict, ~12,400
characters into the model's context in one go, which the model then had to
echo back one component at a time to render each. The data now stays
server-side and render_packet renders the whole packet in a single call.

render_packet itself needs a working WeasyPrint (absent in this sandbox), so
these tests cover the planning/staging half; the rendering half is exercised
by the app on the VM.
"""

from __future__ import annotations

import json
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
from ai_doc_generator.packets import PACKET_REGISTRY  # noqa: E402

# The identity fields that must agree across a packet's documents. Every
# packet's components share at least these, whatever their doc types.
_IDENTITY = ("patient_name", "mrn", "claim_number", "policy_number", "insurer_name")


@pytest.fixture(autouse=True)
def _clean_staging():
    tools.clear_staged_artifact()
    tools.clear_staged_packet()
    tools.clear_staged_packet_plan()
    tools.clear_staged_doc_data()
    yield
    tools.clear_staged_artifact()
    tools.clear_staged_packet()
    tools.clear_staged_packet_plan()
    tools.clear_staged_doc_data()


@pytest.mark.parametrize("packet_name", sorted(PACKET_REGISTRY))
def test_every_packet_shares_one_identity_across_its_components(packet_name):
    tools.build_packet(packet_name=packet_name, scenario="general")
    plan = tools.get_staged_packet_plan()
    assert len(plan) == len(PACKET_REGISTRY[packet_name]["components"])

    for field in _IDENTITY:
        values = {
            comp["data"][field] for comp in plan if field in comp["data"]
        }
        assert len(values) <= 1, (
            f"{packet_name}: components disagree on {field} -> {values}. "
            "Every document in one packet must describe the same claim."
        )


def test_packet_components_still_get_their_own_doc_specific_content():
    """Sharing an identity must not flatten the components into copies of
    each other - each still carries its own document type's fields."""
    tools.build_packet(packet_name="medical-packet", scenario="hospital_admission")
    plan = {c["doc_type"]: c["data"] for c in tools.get_staged_packet_plan()}

    assert "account_number" in plan["medical-bill"]
    assert "revenue_codes" in plan["ub-04"]
    assert "insured_id" in plan["cms-1500"]
    assert "hospital_course" in plan["discharge-summary"]


def test_build_packet_keeps_component_data_out_of_the_model_context():
    """The return value is a plan, not the documents' data - the data is
    staged instead. Guards the ~12KB context dump the old version produced."""
    result = tools.build_packet(packet_name="medical-packet", scenario="general")
    payload = json.dumps(result, default=str)

    assert "data" not in result
    assert len(payload) < 1500, f"build_packet returned {len(payload)} chars: {payload[:200]}"
    assert result["component_count"] == len(tools.get_staged_packet_plan())
    assert [c["label"] for c in result["components"]]


def test_build_packet_is_reproducible_under_a_seed():
    tools.build_packet(packet_name="medical-packet", scenario="general", seed=1234)
    first = tools.get_staged_packet_plan()[0]["data"]["patient_name"]
    tools.clear_staged_packet_plan()
    tools.build_packet(packet_name="medical-packet", scenario="general", seed=1234)
    assert tools.get_staged_packet_plan()[0]["data"]["patient_name"] == first


def test_build_packet_rejects_an_unknown_packet():
    with pytest.raises(ValueError, match="Unknown packet"):
        tools.build_packet(packet_name="no-such-packet", scenario="general")


def test_render_packet_without_a_plan_raises():
    with pytest.raises(ValueError, match="No packet has been planned"):
        tools.render_packet()
