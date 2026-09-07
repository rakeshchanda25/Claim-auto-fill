from __future__ import annotations

_POLICE_REPORT_AUTO = [
    "incident_header", "auto_parties", "injuries", "property_damage",
    "witnesses", "enforcement_action", "evidence", "narrative",
    "field_sketch", "officer_certification",
]
# A person was hurt but no vehicle was involved (workplace, premises, assault).
_POLICE_REPORT_INCIDENT_INJURY = [
    "incident_header", "property_incident", "injuries", "witnesses", "evidence",
    "narrative", "officer_certification",
]
# Property damaged or taken, nobody hurt (fire, water, theft, storm).
_POLICE_REPORT_PROPERTY = [
    "incident_header", "property_incident", "property_damage", "witnesses",
    "evidence", "narrative", "officer_certification",
]
# Police attended something, but neither injury nor property loss is
# established. The safe minimum.
_POLICE_REPORT_INCIDENT = [
    "incident_header", "property_incident", "witnesses", "evidence",
    "narrative", "officer_certification",
]

_ACORD_25_ALL = [
    "header", "clauses", "producer_insurer_insured", "certification_bar",
    "coverages", "description_of_operations", "holder_cancellation", "footer",
]

# Two vehicles, someone hurt - the full form.
_AUTO_ACCIDENT_REPORT_ALL = [
    "doc_header", "instructions", "state_employee", "vehicle1", "other_vehicles",
    "other_property", "injured_parties", "witnesses", "other_section",
    "scenario_details", "footer_note",
]
# Damage only - no injured party to list.
_AUTO_ACCIDENT_REPORT_NO_INJURY = [
    "doc_header", "instructions", "state_employee", "vehicle1", "other_vehicles",
    "other_property", "witnesses", "other_section", "scenario_details", "footer_note",
]
# One vehicle, no other party (theft, fire, hail, animal strike): there is no
# second vehicle and no injured party to report.
_AUTO_ACCIDENT_REPORT_SINGLE_VEHICLE = [
    "doc_header", "instructions", "state_employee", "vehicle1", "other_property",
    "witnesses", "other_section", "scenario_details", "footer_note",
]

_CMS_1500_ALL = [
    "title_payer_box", "patient_insured_grid", "service_lines",
    "tax_totals_signatures", "footer_note",
]

# Third-party liability: written by the claimant's attorney, so it opens by
# stating who they represent.
_DEMAND_LETTER_ALL = [
    "letterhead", "date_recipient", "re_line", "representation_para",
    "facts_summary_para", "scenario_details", "damages_and_demand", "closing_signature",
]
# First-party: the insured writing to their own carrier. No representation
# paragraph, because nobody is representing anybody against anybody.
_DEMAND_LETTER_FIRST_PARTY = [
    "letterhead", "date_recipient", "re_line", "facts_summary_para",
    "scenario_details", "damages_and_demand", "closing_signature",
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
# Most complaints are signed by counsel alone. A VERIFIED complaint - the
# plaintiff swearing to the allegations before a notary - is the exception:
# required for medical malpractice in many states (affidavit / certificate of
# merit) and common in product liability, but not used for a routine premises
# suit.
_LITIGATION_DOCUMENT_UNVERIFIED = [
    "cover_letter", "caption_page", "allegations_page",
    "causes_of_action_page", "prayer_and_signature_page",
]

_MEDICAL_BILL_ALL = [
    "masthead", "patient_demographics", "chief_complaint", "hpi", "vitals",
    "physical_exam", "assessment", "plan", "scenario_details", "signature",
]
# A prescribing / medication-review encounter: no vitals taken, no exam done.
_MEDICAL_BILL_MED_REVIEW = [
    "masthead", "patient_demographics", "chief_complaint", "hpi",
    "assessment", "plan", "scenario_details", "signature",
]

_MEDICAL_RECORD_ALL = [
    "header_bar", "patient_info", "chief_complaint", "hpi", "vitals",
    "physical_exam", "assessment", "plan", "scenario_details", "signature",
]
_MEDICAL_RECORD_MED_REVIEW = [
    "header_bar", "patient_info", "chief_complaint", "hpi",
    "assessment", "plan", "scenario_details", "signature",
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

COMPONENT_COMPOSITION: dict[str, dict[str, list[str]]] = {
    # The auto shape (Driver 1 / Driver 2, collision manner, vehicle damage) is
    # only correct when a vehicle was actually involved, so it is opt-in per
    # scenario. Everything else - including any scenario not listed here - gets
    # the generic incident shape, because rendering a two-vehicle collision
    # report for a workplace exposure or an illness is a total failure, while a
    # generic incident report for an auto claim is merely less specific.
    "police-report": {
        "rear_end_collision": _POLICE_REPORT_AUTO,
        "intersection_accident": _POLICE_REPORT_AUTO,
        "hit_and_run": _POLICE_REPORT_AUTO,
        "fire_damage": _POLICE_REPORT_PROPERTY,
        "water_damage": _POLICE_REPORT_PROPERTY,
        "theft": _POLICE_REPORT_PROPERTY,
        "wind_damage": _POLICE_REPORT_PROPERTY,
        "slip_and_fall": _POLICE_REPORT_INCIDENT_INJURY,
        "workplace_injury": _POLICE_REPORT_INCIDENT_INJURY,
        "occupational_exposure": _POLICE_REPORT_INCIDENT_INJURY,
        "general": _POLICE_REPORT_INCIDENT,
    },
    "acord-25": {"general": _ACORD_25_ALL},
    "auto-accident-report": {
        "rear_end_collision": _AUTO_ACCIDENT_REPORT_ALL,
        "intersection_accident": _AUTO_ACCIDENT_REPORT_ALL,
        "hit_and_run": _AUTO_ACCIDENT_REPORT_ALL,
        "theft": _AUTO_ACCIDENT_REPORT_SINGLE_VEHICLE,
        "fire_damage": _AUTO_ACCIDENT_REPORT_SINGLE_VEHICLE,
        "wind_damage": _AUTO_ACCIDENT_REPORT_SINGLE_VEHICLE,
        "water_damage": _AUTO_ACCIDENT_REPORT_SINGLE_VEHICLE,
        "general": _AUTO_ACCIDENT_REPORT_NO_INJURY,
    },
    "cms-1500": {"general": _CMS_1500_ALL},
    "demand-letter": {
        "fire_damage": _DEMAND_LETTER_FIRST_PARTY,
        "water_damage": _DEMAND_LETTER_FIRST_PARTY,
        "theft": _DEMAND_LETTER_FIRST_PARTY,
        "wind_damage": _DEMAND_LETTER_FIRST_PARTY,
        "general": _DEMAND_LETTER_ALL,
    },
    "discharge-summary": {"general": _DISCHARGE_SUMMARY_ALL},
    "eob-explanation": {"general": _EOB_EXPLANATION_ALL},
    "litigation-document": {
        "medical_malpractice": _LITIGATION_DOCUMENT_ALL,
        "product_liability": _LITIGATION_DOCUMENT_ALL,
        "general": _LITIGATION_DOCUMENT_UNVERIFIED,
    },
    "medical-bill": {
        "chronic_medication": _MEDICAL_BILL_MED_REVIEW,
        "specialty_drug": _MEDICAL_BILL_MED_REVIEW,
        "compounded_medication": _MEDICAL_BILL_MED_REVIEW,
        "general": _MEDICAL_BILL_ALL,
    },
    "medical-record": {
        "chronic_medication": _MEDICAL_RECORD_MED_REVIEW,
        "specialty_drug": _MEDICAL_RECORD_MED_REVIEW,
        "compounded_medication": _MEDICAL_RECORD_MED_REVIEW,
        "general": _MEDICAL_RECORD_ALL,
    },
    "pharmacy-invoice": {"general": _PHARMACY_INVOICE_ALL},
    "property-loss-notice": {"general": _PROPERTY_LOSS_NOTICE_ALL},
    "ub-04": {"general": _UB_04_ALL},
}


def get_components(doc_type: str, scenario: str) -> list[str]:
    per_doc = COMPONENT_COMPOSITION.get(doc_type, {})
    return per_doc.get(scenario) or per_doc.get("general", [])
