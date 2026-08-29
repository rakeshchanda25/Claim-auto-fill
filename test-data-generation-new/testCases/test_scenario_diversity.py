"""
Guards that a doc type's registered scenarios actually produce DIFFERENT
documents, not the same template with different values plugged in.

The bug: several doc types register 3-4 scenarios (property-loss-notice's
fire_damage/water_damage/theft/wind_damage, police-report's rear_end_collision/
intersection_accident/hit_and_run, litigation-document's slip_and_fall/
medical_malpractice/product_liability, pharmacy-invoice's chronic_medication/
specialty_drug/compounded_medication) that all rendered through the exact
same template with independently-randomized content - the scenario name
itself never drove anything. A "hit and run" police report was no more
likely to actually flag hit_and_run="Yes" than a rear-end collision report.

Two fixes, both scenario -> Python-only, no template touched:
  - property-loss-notice gets a genuinely NEW structural section per scenario
    (_property_scenario_facts: a title + list of facts, rendered by one
    generic {% if scenario_facts %} loop the template never needs to grow a
    new branch for);
  - police-report/litigation-document/pharmacy-invoice have EXISTING fields
    that used to be independently random - correlated to the scenario name
    instead (collision_type/hit_and_run/primary_factor, causes_of_action,
    item pool/pricing respectively).
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

_TRIALS = 30


def test_property_loss_notice_gets_a_distinct_section_per_scenario():
    expected_titles = {
        "fire_damage": "Fire Details",
        "water_damage": "Water Details",
        "theft": "Theft Details",
        "wind_damage": "Storm Details",
    }
    seen_titles = set()
    for scenario, title in expected_titles.items():
        data = build_synthetic_data("property-loss-notice", scenario)
        assert data["scenario_facts_title"] == title
        assert len(data["scenario_facts"]) > 0
        seen_titles.add(title)
        html = _env.get_template("property_loss_notice.html").render(**data)
        assert title in html, f"{scenario}'s section heading never made it into the rendered HTML"

    assert len(seen_titles) == 4, "all four property scenarios must produce DIFFERENT sections"


def test_property_loss_notice_omits_the_section_for_an_unmapped_scenario():
    # "general" (and any future scenario nobody has written facts for yet)
    # must not render an empty heading with nothing under it.
    data = build_synthetic_data("property-loss-notice", "general")
    assert data["scenario_facts"] == []
    html = _env.get_template("property_loss_notice.html").render(**data)
    assert "Fire Details" not in html and "Water Details" not in html


def test_police_report_hit_and_run_scenario_actually_flags_hit_and_run():
    hit_and_run_count = sum(
        1 for _ in range(_TRIALS)
        if build_synthetic_data("police-report", "hit_and_run")["hit_and_run"] == "Yes"
    )
    other_count = sum(
        1 for _ in range(_TRIALS)
        if build_synthetic_data("police-report", "rear_end_collision")["hit_and_run"] == "Yes"
    )
    assert hit_and_run_count > _TRIALS * 0.6, (
        f"hit_and_run scenario only flagged Yes {hit_and_run_count}/{_TRIALS} times"
    )
    assert other_count < hit_and_run_count, "a non-hit_and_run scenario must not match as often"


def test_police_report_collision_type_matches_its_scenario():
    for _ in range(_TRIALS):
        data = build_synthetic_data("police-report", "rear_end_collision")
        assert data["collision_type"] == "Rear-end"


def test_police_report_hit_and_run_collision_type_is_never_single_vehicle():
    # A hit-and-run necessarily involves a second vehicle that fled - a
    # "Single Vehicle" collision_type contradicts hit_and_run="Yes" and made
    # the narrative literally read "Two-vehicle single vehicle collision".
    # hit_and_run_flag is only ~85% likely even for the "hit_and_run" scenario
    # (see synthetic_data.py), so this must check the actual outcome
    # (data["hit_and_run"]), not just the scenario name - a trial where the
    # flag lands False is a legitimate non-hit-and-run report and Single
    # Vehicle is a valid collision_type for it.
    for _ in range(_TRIALS):
        data = build_synthetic_data("police-report", "hit_and_run")
        if data["hit_and_run"] == "Yes":
            assert data["collision_type"] != "Single Vehicle"
            assert "single vehicle" not in data["narrative"].lower()


def test_police_report_never_shows_single_vehicle_with_hit_and_run_yes_for_any_scenario():
    # Real bug seen in production: doc_type=police-report was called with
    # scenario='surgery' (a medical-family scenario name, meaningless for a
    # police report) - since collision_type/primary_factor used to be branched
    # on the scenario STRING rather than on hit_and_run_flag, a report could
    # come back with COLLISION TYPE: Single Vehicle and HIT & RUN: Yes side by
    # side, which is a logical contradiction (a "single vehicle" collision has
    # no second vehicle to flee). This must hold for every scenario name that
    # can arrive here - including ones that have nothing to do with this doc
    # type - not just the literal "hit_and_run" scenario.
    for scenario in ("surgery", "hospital_admission", "chronic_medication", "general", "slip_and_fall"):
        for _ in range(_TRIALS):
            data = build_synthetic_data("police-report", scenario)
            if data["hit_and_run"] == "Yes":
                assert data["collision_type"] != "Single Vehicle", (
                    f"scenario={scenario!r}: hit_and_run=Yes but collision_type=Single Vehicle"
                )


def test_police_report_dispatch_arrival_cleared_times_are_chronologically_ordered():
    for _ in range(_TRIALS):
        data = build_synthetic_data("police-report", "general")
        dispatch = data["dispatch_time"]
        arrival = data["arrival_time"]
        cleared = data["cleared_time"]
        assert dispatch <= arrival <= cleared, (
            f"dispatch={dispatch} arrival={arrival} cleared={cleared} out of order"
        )


def test_police_report_narrative_is_scenario_specific_not_generic_filler():
    # narrative/narrative_paragraphs used to be pure Faker Lorem-Ipsum-style
    # text regardless of scenario - assert the narrative actually names the
    # parties and mechanism already generated for this report, and that two
    # different scenarios produce genuinely different prose.
    rear_end = build_synthetic_data("police-report", "rear_end_collision")
    assert any(rear_end["parties_involved"][1]["name"] in p for p in rear_end["narrative_paragraphs"])
    assert "struck the rear" in rear_end["narrative_paragraphs"][0]

    hit_and_run = build_synthetic_data("police-report", "hit_and_run")
    assert "fled the scene" in hit_and_run["narrative_paragraphs"][0]

    intersection = build_synthetic_data("police-report", "intersection_accident")
    assert "intersection" in intersection["narrative_paragraphs"][0].lower()

    assert rear_end["narrative"] != hit_and_run["narrative"] != intersection["narrative"]


def test_litigation_document_facts_narrative_matches_the_anchored_cause():
    # facts/general_allegations used to be generic Faker paragraphs unrelated
    # to causes_of_action even though causes_of_action was already anchored.
    slip = build_synthetic_data("litigation-document", "slip_and_fall")
    assert "slipped and fell" in slip["facts"]
    assert "premises" in slip["general_allegations"][0].lower()

    malpractice = build_synthetic_data("litigation-document", "medical_malpractice")
    assert "standard of care" in malpractice["facts"]

    product = build_synthetic_data("litigation-document", "product_liability")
    assert "defect" in product["facts"]

    assert slip["facts"] != malpractice["facts"] != product["facts"]


def test_demand_letter_facts_summary_matches_its_scenario():
    slip = build_synthetic_data("demand-letter", "slip_and_fall")
    assert "slipped and fell" in slip["facts_summary"]
    product = build_synthetic_data("demand-letter", "product_liability")
    assert "defect" in product["facts_summary"]
    assert slip["facts_summary"] != product["facts_summary"]


def test_auto_accident_report_damage_descriptions_match_collision_type():
    rear_end = build_synthetic_data("auto-accident-report", "rear_end_collision")
    assert "rear" in rear_end["vehicle1"]["damage_description"].lower()
    assert "front" in rear_end["vehicle2"]["damage_description"].lower()


def test_medical_record_clinical_note_text_is_scenario_specific_not_generic_filler():
    # chief_complaint/hpi/physical_exam/plan used to be pure Faker Lorem-Ipsum-style text
    # regardless of scenario, unlike scenario_facts (a separate section) which already
    # varied. Assert the actual clinical narrative differs and names the scenario mechanism.
    surgery = build_synthetic_data("medical-record", "surgery")
    assert "surgical" in surgery["hpi"].lower()
    assert surgery["diagnosis_codes"][0][1] in surgery["hpi"]

    slip = build_synthetic_data("medical-record", "slip_and_fall")
    assert "fall" in slip["hpi"].lower()

    chronic = build_synthetic_data("medical-record", "chronic_medication")
    assert "chronic" in chronic["hpi"].lower()

    assert surgery["hpi"] != slip["hpi"] != chronic["hpi"]
    # general/unmatched scenario still gets real prose, not blank or crashing
    general = build_synthetic_data("medical-record", "general")
    assert general["hpi"] and "Patient reports" in general["hpi"]


def test_discharge_summary_summary_of_care_plan_is_scenario_specific():
    # Before this fix, synthetic_data.py never set summary_of_care_plan/
    # goals_achieved_summary at all - discharge_summary.html's own Jinja
    # `| default(...)` fallback then printed the SAME hardcoded pregnancy/
    # antepartum boilerplate on every discharge summary regardless of scenario.
    surgery = build_synthetic_data("discharge-summary", "surgery")
    assert "surgical" in surgery["summary_of_care_plan"].lower()
    assert "antepartum" not in surgery["summary_of_care_plan"].lower()

    hospital = build_synthetic_data("discharge-summary", "hospital_admission")
    assert "antepartum" not in hospital["summary_of_care_plan"].lower()
    assert surgery["summary_of_care_plan"] != hospital["summary_of_care_plan"]

    html = _env.get_template("discharge_summary.html").render(**surgery)
    assert "Antepartum assessment" not in html


def test_litigation_document_cause_of_action_always_matches_its_scenario():
    anchors = {
        "slip_and_fall": "Premises Liability",
        "medical_malpractice": "Negligence",
        "product_liability": "Strict Product Liability",
    }
    for scenario, anchor in anchors.items():
        for _ in range(_TRIALS):
            data = build_synthetic_data("litigation-document", scenario)
            assert anchor in data["causes_of_action"], (
                f"{scenario} complaint missing its defining cause of action {anchor!r}: "
                f"{data['causes_of_action']}"
            )


def test_pharmacy_invoice_items_differ_by_scenario():
    chronic = build_synthetic_data("pharmacy-invoice", "chronic_medication")
    specialty = build_synthetic_data("pharmacy-invoice", "specialty_drug")
    compounded = build_synthetic_data("pharmacy-invoice", "compounded_medication")

    chronic_names = {i["name"] for i in chronic["items"]}
    specialty_names = {i["name"] for i in specialty["items"]}
    compounded_names = {i["name"] for i in compounded["items"]}

    assert not (specialty_names & chronic_names), "specialty items must not overlap the chronic-med pool"
    assert not (compounded_names & chronic_names), "compounded items must not overlap the chronic-med pool"
    assert any("Compounded" in n for n in compounded_names)

    # Specialty drugs (biologics) are priced far above routine chronic refills.
    specialty_rate = max(i["rate"] for i in specialty["items"])
    chronic_rate = max(i["rate"] for i in chronic["items"])
    assert specialty_rate > chronic_rate


def test_pharmacy_invoice_still_reconciles_for_every_scenario():
    for scenario in ("chronic_medication", "specialty_drug", "compounded_medication"):
        data = build_synthetic_data("pharmacy-invoice", scenario)
        _env.get_template("pharmacy_invoice.html").render(**data)
        subtotal = round(sum(i["taxable_value"] for i in data["items"]), 2)
        assert subtotal == data["subtotal_taxable_value"]


# ---------------------------------------------------------------------------
# Second pass: the same scenario_facts mechanism extended to every remaining
# doc type/scenario combination a packet can actually request (see
# ai_doc_generator/packets.py's PACKET_REGISTRY/compatible_scenarios). Each
# doc type below used to render scenario_facts as an undefined StrictUndefined
# reference (a template edit with no matching Python branch) until wired here.
# ---------------------------------------------------------------------------

def test_auto_accident_report_gets_a_distinct_section_per_scenario():
    expected_titles = {
        "rear_end_collision": "Rear-End Collision Details",
        "intersection_accident": "Intersection Details",
        "hit_and_run": "Hit and Run Details",
    }
    seen_titles = set()
    for scenario, title in expected_titles.items():
        data = build_synthetic_data("auto-accident-report", scenario)
        assert data["scenario_facts_title"] == title
        assert len(data["scenario_facts"]) > 0
        seen_titles.add(title)
        html = _env.get_template("auto_accident_report.html").render(**data)
        assert title.upper() in html, "auto_accident_report.html renders the tab heading via |upper"
    assert len(seen_titles) == 3


def test_demand_letter_gets_a_distinct_section_per_scenario():
    for scenario in ("slip_and_fall", "medical_malpractice", "product_liability"):
        data = build_synthetic_data("demand-letter", scenario)
        assert data["scenario_facts_title"]
        assert len(data["scenario_facts"]) > 0
        html = _env.get_template("demand_letter.html").render(**data)
        assert data["scenario_facts_title"] in html


def test_eob_explanation_covers_both_litigation_and_pharmacy_scenario_names():
    for scenario in (
        "slip_and_fall", "medical_malpractice", "product_liability",
        "chronic_medication", "specialty_drug", "compounded_medication",
    ):
        data = build_synthetic_data("eob-explanation", scenario)
        assert data["scenario_facts_title"], f"{scenario} produced no facts section"
        html = _env.get_template("eob_explanation.html").render(**data)
        assert data["scenario_facts_title"] in html


def test_police_report_also_covers_property_scenarios_it_serves_as_incident_report_for():
    # police-report is reused as "Incident Report" in the property-claim
    # packet (fire_damage/water_damage/theft/wind_damage), not just the
    # auto-accident packet - it must pick up _property_scenario_facts too.
    data = build_synthetic_data("police-report", "fire_damage")
    assert data["scenario_facts_title"] == "Fire Details"
    html = _env.get_template("police_report.html").render(**data)
    assert "Fire Details" in html

    # An auto scenario already has its own dedicated fields (collision_type
    # etc) - scenario_facts stays empty rather than duplicating that.
    auto_data = build_synthetic_data("police-report", "rear_end_collision")
    assert auto_data["scenario_facts"] == []


def test_medical_record_covers_every_cross_family_scenario_it_can_be_called_with():
    # medical-record is reused by all 4 packets (see PACKET_REGISTRY), so it
    # can be called with 13 different scenario names, not just the 4
    # "medical" ones. The 3 auto-collision scenarios intentionally share one
    # section title ("Mechanism of Injury") - a chart note groups them under
    # the same clinical heading - so distinctness is asserted on the facts
    # content (label/value pairs), not the title.
    all_scenarios = [
        "hospital_admission", "surgery", "emergency_visit", "outpatient_procedure",
        "rear_end_collision", "intersection_accident", "hit_and_run",
        "slip_and_fall", "medical_malpractice", "product_liability",
        "chronic_medication", "specialty_drug", "compounded_medication",
    ]
    seen_facts = set()
    for scenario in all_scenarios:
        data = build_synthetic_data("medical-record", scenario)
        assert data["scenario_facts_title"], f"{scenario} produced no facts section"
        facts_key = tuple(f["label"] for f in data["scenario_facts"])
        seen_facts.add((data["scenario_facts_title"], facts_key))
        html = _env.get_template("medical_record.html").render(**data)
        assert data["scenario_facts_title"] in html
    assert len(seen_facts) == len(all_scenarios), "every scenario must produce distinct facts content"


def test_medical_bill_and_discharge_summary_and_ub04_all_wire_the_same_facts():
    for doc_type, template_file in (
        ("medical-bill", "medical_bill.html"),
        ("discharge-summary", "discharge_summary.html"),
    ):
        data = build_synthetic_data(doc_type, "surgery")
        assert data["scenario_facts_title"] == "Surgical Details"
        html = _env.get_template(template_file).render(**data)
        assert "Surgical Details" in html or "SURGICAL DETAILS" in html

    # cms-1500 and ub-04 are fixed-layout federal forms (real box numbering) -
    # scenario facts go into their existing free-text boxes instead of a new
    # section, so assert the facts text landed there rather than in a
    # scenario_facts key the template doesn't reference.
    cms = build_synthetic_data("cms-1500", "surgery")
    assert "Anesthesia Type" in cms["additional_claim_info"]
    ub04 = build_synthetic_data("ub-04", "surgery")
    assert "Anesthesia Type" in ub04["remarks"]
