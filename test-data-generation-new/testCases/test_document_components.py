"""
Guards the component-library architecture: renderers/components.py decides, per
(doc_type, scenario), which named Jinja macros ("components") a document assembles - the
fix for a fixed template being forced to represent scenarios it structurally can't (a
fire-damage police report showing empty Driver 1/Driver 2 vehicle tables). See
renderers/components.py's module docstring and renderers/templates/police_report.html for
the reference implementation.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

if "weasyprint" not in sys.modules:
    _fake_weasyprint = types.ModuleType("weasyprint")
    _fake_weasyprint.HTML = object
    sys.modules["weasyprint"] = _fake_weasyprint

from renderers.html_renderer import _env  # noqa: E402
from renderers.synthetic_data import build_synthetic_data  # noqa: E402
from renderers.components import get_components, COMPONENT_COMPOSITION  # noqa: E402
from ai_doc_generator.packets import PACKET_REGISTRY  # noqa: E402


def _all_doc_type_scenario_pairs():
    pairs = set()
    for packet in PACKET_REGISTRY.values():
        for comp in packet["components"]:
            for scenario in packet["compatible_scenarios"]:
                pairs.add((comp["doc_type"], scenario))
            pairs.add((comp["doc_type"], "general"))
    return sorted(pairs)


def test_every_registered_doc_type_has_a_component_composition():
    doc_types = {comp["doc_type"] for packet in PACKET_REGISTRY.values() for comp in packet["components"]}
    missing = doc_types - set(COMPONENT_COMPOSITION)
    assert not missing, f"doc types with no COMPONENT_COMPOSITION entry: {missing}"


def test_get_components_never_returns_empty_for_any_registered_pair():
    # Including an out-of-domain scenario name (e.g. "surgery" passed to
    # police-report - the real bug that triggered this whole rewrite): every
    # (doc_type, scenario) pair must still resolve to a real, complete document.
    for doc_type, scenario in _all_doc_type_scenario_pairs():
        components = get_components(doc_type, scenario)
        assert components, f"{doc_type}/{scenario} resolved to an empty component list"


def test_build_synthetic_data_components_field_matches_the_registry():
    for doc_type, scenario in _all_doc_type_scenario_pairs():
        data = build_synthetic_data(doc_type, scenario)
        assert data["components"] == get_components(doc_type, scenario)


def test_police_report_fire_damage_omits_every_vehicle_collision_component():
    # The concrete bug this session fixed: a fire-damage report showing
    # Driver 1/Driver 2 vehicle tables and an Injuries section that has
    # nothing to do with a property incident.
    data = build_synthetic_data("police-report", "fire_damage")
    components = data["components"]
    assert "auto_parties" not in components
    assert "injuries" not in components
    assert "enforcement_action" not in components
    assert "field_sketch" not in components
    assert "property_incident" in components

    html = _env.get_template("police_report.html").render(data=data, **data)
    assert "Driver 1" not in html
    assert "Section 4 — Injuries" not in html
    assert "Reporting Party" in html
    assert data["scenario_facts_title"] in html


def test_police_report_auto_scenarios_keep_the_full_collision_report_shape():
    for scenario in ("rear_end_collision", "intersection_accident", "hit_and_run"):
        data = build_synthetic_data("police-report", scenario)
        components = data["components"]
        assert "auto_parties" in components
        assert "injuries" in components
        assert "property_incident" not in components

        html = _env.get_template("police_report.html").render(data=data, **data)
        assert "Driver 1" in html
        assert "Section 4 — Injuries and Medical Transport" in html


def test_litigation_document_page_count_tracks_causes_of_action_count():
    # Each cause of action gets its own physical page (renderers/templates/
    # litigation_document.html's causes_of_action_page macro loops per cause) rather
    # than cramming 2-3 onto one fixed 8.5x11in overflow:hidden page, which used to
    # silently clip content past 11in tall. Page count must therefore vary with
    # len(causes_of_action) (2 or 3), not be fixed regardless of scenario.
    import re
    for scenario in ("slip_and_fall", "medical_malpractice", "product_liability", "general"):
        data = build_synthetic_data("litigation-document", scenario)
        html = _env.get_template("litigation_document.html").render(data=data, **data)
        pleading_pages = len(re.findall(r'<div class="page pleading"', html))
        total_pages = len(re.findall(r'<div class="page"|<div class="page pleading"', html))
        causes_count = len(data["causes_of_action"])
        assert pleading_pages == 4 + causes_count, (
            f"{scenario}: expected {4 + causes_count} pleading pages for {causes_count} "
            f"causes of action, got {pleading_pages}"
        )
        assert total_pages == 1 + pleading_pages  # +1 for the (unnumbered) cover letter


def test_police_report_out_of_domain_scenario_still_renders_the_full_auto_shape():
    # doc_type=police-report, scenario="surgery" - the exact pairing seen in the
    # user's own terminal log. A scenario name unrelated to this doc type must
    # fall back to the general/auto composition, not an empty or broken document.
    data = build_synthetic_data("police-report", "surgery")
    assert data["components"] == get_components("police-report", "general")
    html = _env.get_template("police_report.html").render(data=data, **data)
    assert "Driver 1" in html
