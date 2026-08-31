"""Document-component composition registry.

Each doc type's template used to be one fixed structure that every scenario's data got
poured into - the DESIGN (typography, layout conventions, page chrome) and the STRUCTURE
(which sections exist) were the same thing, so a scenario that genuinely needed a different
shape (police-report serving both real auto-collision reports and property-incident
reports) got forced into a template that couldn't represent it - e.g. a fire-damage report
showing empty "Driver 1 / Driver 2" vehicle tables.

This module is the split: each template is decomposed into named Jinja macros ("components"),
and COMPONENT_COMPOSITION says, for a given (doc_type, scenario), which components are
assembled and in what order. The template's CSS/typography/page chrome never changes - only
which macros get called does. Templates read this via the `components` list synthetic_data.py
puts in the data dict; see renderers/templates/police_report.html for the reference
implementation (the doc type this was built for - the only one with two genuinely different
document shapes today, auto-collision vs. property-incident).

For doc types whose real-world document shape does NOT vary by scenario (a legal complaint,
a federal claim form, a SOAP note keep the same sections regardless of injury/drug type),
every scenario intentionally resolves to the SAME component list - the mechanism still
applies uniformly (every template is decomposed into macros, every doc type is registered
here), it's just not exercised to produce different shapes for those doc types, because their
real-world documents don't.
"""

from __future__ import annotations

_POLICE_REPORT_AUTO = [
    "incident_header", "auto_parties", "injuries", "property_damage",
    "witnesses", "enforcement_action", "evidence", "narrative",
    "field_sketch", "officer_certification",
]
_POLICE_REPORT_PROPERTY = [
    "incident_header", "property_incident", "witnesses", "evidence",
    "narrative", "officer_certification",
]

_ACORD_25_ALL = [
    "header", "clauses", "producer_insurer_insured", "certification_bar",
    "coverages", "description_of_operations", "holder_cancellation", "footer",
]

_AUTO_ACCIDENT_REPORT_ALL = [
    "doc_header", "instructions", "state_employee", "vehicle1", "other_vehicles",
    "other_property", "injured_parties", "witnesses", "other_section",
    "scenario_details", "footer_note",
]

_CMS_1500_ALL = [
    "title_payer_box", "patient_insured_grid", "service_lines",
    "tax_totals_signatures", "footer_note",
]

_DEMAND_LETTER_ALL = [
    "letterhead", "date_recipient", "re_line", "representation_para",
    "facts_summary_para", "scenario_details", "damages_and_demand", "closing_signature",
]

_DISCHARGE_SUMMARY_ALL = [
    "doc_header", "info_grid", "reason_for_discharge", "summary_of_care",
    "status_of_discharge", "plan_for_transition", "discharge_instructions",
    "scenario_details", "signature",
]

_EOB_EXPLANATION_ALL = [
    "claim_box", "claims_table", "notes_legend", "scenario_details", "benefit_summary",
]

_LITIGATION_DOCUMENT_ALL = [
    "cover_letter", "caption_page", "allegations_page",
    "causes_of_action_page", "prayer_and_signature_page", "verification_and_notary_page",
]

_MEDICAL_BILL_ALL = [
    "masthead", "patient_demographics", "chief_complaint", "hpi", "vitals",
    "physical_exam", "assessment", "plan", "scenario_details", "signature",
]

_MEDICAL_RECORD_ALL = [
    "header_bar", "patient_info", "chief_complaint", "hpi", "vitals",
    "physical_exam", "assessment", "plan", "scenario_details", "signature",
]

_PHARMACY_INVOICE_ALL = [
    "header", "gstin_row", "detail_box", "items_table", "words_row",
    "hsn_table", "tax_words_row", "bottom_grid", "footer_note",
]

_PROPERTY_LOSS_NOTICE_ALL = [
    "header", "insured_information", "loss_information", "scenario_details",
    "mortgage_lienholder", "adjuster_assignment", "signature",
]

_UB_04_ALL = [
    "header_boxes", "revenue_code_lines", "payer_diagnosis_boxes", "footer_legend",
]

# doc_type -> {scenario_name: [ordered component_id, ...]}, plus a "general" fallback
# used for any scenario name not explicitly listed (including one that has nothing to
# do with this doc type at all - see the police-report/collision_type bug this session).
COMPONENT_COMPOSITION: dict[str, dict[str, list[str]]] = {
    "police-report": {
        "rear_end_collision": _POLICE_REPORT_AUTO,
        "intersection_accident": _POLICE_REPORT_AUTO,
        "hit_and_run": _POLICE_REPORT_AUTO,
        "fire_damage": _POLICE_REPORT_PROPERTY,
        "water_damage": _POLICE_REPORT_PROPERTY,
        "theft": _POLICE_REPORT_PROPERTY,
        "wind_damage": _POLICE_REPORT_PROPERTY,
        "general": _POLICE_REPORT_AUTO,
    },
    "acord-25": {"general": _ACORD_25_ALL},
    "auto-accident-report": {
        "rear_end_collision": _AUTO_ACCIDENT_REPORT_ALL,
        "intersection_accident": _AUTO_ACCIDENT_REPORT_ALL,
        "hit_and_run": _AUTO_ACCIDENT_REPORT_ALL,
        "general": _AUTO_ACCIDENT_REPORT_ALL,
    },
    "cms-1500": {"general": _CMS_1500_ALL},
    "demand-letter": {
        "slip_and_fall": _DEMAND_LETTER_ALL,
        "medical_malpractice": _DEMAND_LETTER_ALL,
        "product_liability": _DEMAND_LETTER_ALL,
        "general": _DEMAND_LETTER_ALL,
    },
    "discharge-summary": {
        "hospital_admission": _DISCHARGE_SUMMARY_ALL,
        "surgery": _DISCHARGE_SUMMARY_ALL,
        "emergency_visit": _DISCHARGE_SUMMARY_ALL,
        "outpatient_procedure": _DISCHARGE_SUMMARY_ALL,
        "general": _DISCHARGE_SUMMARY_ALL,
    },
    "eob-explanation": {"general": _EOB_EXPLANATION_ALL},
    "litigation-document": {"general": _LITIGATION_DOCUMENT_ALL},
    "medical-bill": {"general": _MEDICAL_BILL_ALL},
    "medical-record": {"general": _MEDICAL_RECORD_ALL},
    "pharmacy-invoice": {"general": _PHARMACY_INVOICE_ALL},
    "property-loss-notice": {
        "fire_damage": _PROPERTY_LOSS_NOTICE_ALL,
        "water_damage": _PROPERTY_LOSS_NOTICE_ALL,
        "theft": _PROPERTY_LOSS_NOTICE_ALL,
        "wind_damage": _PROPERTY_LOSS_NOTICE_ALL,
        "general": _PROPERTY_LOSS_NOTICE_ALL,
    },
    "ub-04": {"general": _UB_04_ALL},
}


def get_components(doc_type: str, scenario: str) -> list[str]:
    """The ordered list of component ids to assemble for (doc_type, scenario). Falls back to
    the doc type's "general" composition for any scenario name not explicitly registered -
    including one that has nothing to do with this doc type (see the
    police-report/scenario="surgery" bug this session: any scenario string can arrive here,
    so an unmatched one must resolve to a real, complete document, never an empty list)."""
    per_doc = COMPONENT_COMPOSITION.get(doc_type, {})
    return per_doc.get(scenario) or per_doc.get("general", [])
