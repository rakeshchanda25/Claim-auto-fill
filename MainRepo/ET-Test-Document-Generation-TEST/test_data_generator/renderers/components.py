"""Which sections each document is assembled from.

A template holds the DESIGN (typography, page chrome) and a set of named Jinja macros. This
registry holds the STRUCTURE: for a given (doc_type, scenario), which macros are called and
in what order. Keeping them apart is what lets one police-report template serve both an auto
collision and a fire - previously a fire-damage report rendered empty "Driver 1 / Driver 2"
vehicle tables, because structure and design were the same fixed thing.

Templates read the resulting list from the `components` key synthetic_data.py puts in the
data dict. See renderers/templates/police_report.html for the reference implementation.

Only police-report's structure actually varies by scenario; a legal complaint, a federal
claim form and a SOAP note keep the same sections whatever the scenario, so they register a
single "general" list. get_components falls back to "general" for any scenario not named.
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
        "fire_damage": _POLICE_REPORT_PROPERTY,
        "water_damage": _POLICE_REPORT_PROPERTY,
        "theft": _POLICE_REPORT_PROPERTY,
        "wind_damage": _POLICE_REPORT_PROPERTY,
        "general": _POLICE_REPORT_AUTO,
    },
    "acord-25": {"general": _ACORD_25_ALL},
    "auto-accident-report": {"general": _AUTO_ACCIDENT_REPORT_ALL},
    "cms-1500": {"general": _CMS_1500_ALL},
    "demand-letter": {"general": _DEMAND_LETTER_ALL},
    "discharge-summary": {"general": _DISCHARGE_SUMMARY_ALL},
    "eob-explanation": {"general": _EOB_EXPLANATION_ALL},
    "litigation-document": {"general": _LITIGATION_DOCUMENT_ALL},
    "medical-bill": {"general": _MEDICAL_BILL_ALL},
    "medical-record": {"general": _MEDICAL_RECORD_ALL},
    "pharmacy-invoice": {"general": _PHARMACY_INVOICE_ALL},
    "property-loss-notice": {"general": _PROPERTY_LOSS_NOTICE_ALL},
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
