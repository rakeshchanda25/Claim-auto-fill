DOC_TYPES = [
    {"id": "medical-record",       "label": "Medical Record",       "icon": "🏥", "category": "Clinical"},
    {"id": "medical-bill",         "label": "Medical Bill",         "icon": "💊", "category": "Billing"},
    {"id": "discharge-summary",    "label": "Discharge Summary",    "icon": "🏨", "category": "Clinical"},
    {"id": "cms-1500",             "label": "CMS-1500",             "icon": "📋", "category": "Billing"},
    {"id": "ub-04",                "label": "UB-04",                "icon": "🏦", "category": "Billing"},
    {"id": "eob-explanation",      "label": "EOB",                  "icon": "📄", "category": "Insurance"},
    {"id": "acord-25",             "label": "ACORD 25",             "icon": "📜", "category": "Insurance"},
    {"id": "police-report",        "label": "Police Report",        "icon": "🚔", "category": "Legal"},
    {"id": "demand-letter",        "label": "Demand Letter",        "icon": "⚖️", "category": "Legal"},
    {"id": "litigation-document",  "label": "Litigation Document",  "icon": "🏛️", "category": "Legal"},
    {"id": "pharmacy-invoice",     "label": "Pharmacy Invoice",     "icon": "💉", "category": "Billing"},
    {"id": "property-loss-notice", "label": "Property Loss Notice", "icon": "🏠", "category": "Property"},
    {"id": "auto-accident-report", "label": "Auto Accident Report", "icon": "🚗", "category": "Auto"},
]

PACKET_REGISTRY = {
    "medical-packet": {
        "display_name": "Medical Claims Packet",
        "description": "Full medical bundle: bill, clinical notes, discharge summary, CMS-1500, UB-04",
        "components": [
            {"doc_type": "medical-bill",      "label": "Medical Bill",         "order": 1},
            {"doc_type": "medical-record",    "label": "Clinical Visit Notes", "order": 2},
            {"doc_type": "discharge-summary", "label": "Discharge Summary",    "order": 3},
            {"doc_type": "cms-1500",          "label": "CMS-1500 Claim Form",  "order": 4},
            {"doc_type": "ub-04",             "label": "UB-04 Institutional Claim", "order": 5},
        ],
        "compatible_scenarios": [
            "hospital_admission", "surgery", "emergency_visit", "outpatient_procedure"
        ],
    },
    "auto-accident-packet": {
        "display_name": "Auto Accident Packet",
        "description": "Police report, auto loss notice, ER visit, and ACORD certificate",
        "components": [
            {"doc_type": "police-report",         "label": "Police Report",        "order": 1},
            {"doc_type": "auto-accident-report",  "label": "Auto Loss Notice",     "order": 2},
            {"doc_type": "medical-record",        "label": "ER Visit Notes",       "order": 3},
            {"doc_type": "medical-bill",          "label": "ER Bill",              "order": 4},
            {"doc_type": "acord-25",              "label": "ACORD 25 Certificate", "order": 5},
        ],
        "compatible_scenarios": ["rear_end_collision", "intersection_accident", "hit_and_run"],
    },
    "property-claim-packet": {
        "display_name": "Property Damage Packet",
        "description": "Property loss notice, incident report, and certificate of insurance",
        "components": [
            {"doc_type": "property-loss-notice", "label": "Property Loss Notice",     "order": 1},
            {"doc_type": "police-report",        "label": "Incident Report",          "order": 2},
            {"doc_type": "acord-25",             "label": "Certificate of Insurance", "order": 3},
        ],
        "compatible_scenarios": ["fire_damage", "water_damage", "theft", "wind_damage"],
    },
    "litigation-packet": {
        "display_name": "Litigation Support Packet",
        "description": "Demand letter, filed complaint, medical records, EOB, and medical bills",
        "components": [
            {"doc_type": "demand-letter",       "label": "Demand Letter",       "order": 1},
            {"doc_type": "litigation-document", "label": "Filed Complaint",     "order": 2},
            {"doc_type": "medical-record",      "label": "Medical Records",     "order": 3},
            {"doc_type": "eob-explanation",     "label": "EOB",                 "order": 4},
            {"doc_type": "medical-bill",        "label": "Medical Bills",       "order": 5},
        ],
        "compatible_scenarios": ["slip_and_fall", "medical_malpractice", "product_liability"],
    },
    "pharmacy-claim-packet": {
        "display_name": "Pharmacy Claims Packet",
        "description": "Pharmacy invoice, prescribing notes, and EOB",
        "components": [
            {"doc_type": "pharmacy-invoice", "label": "Pharmacy Invoice",    "order": 1},
            {"doc_type": "medical-record",   "label": "Prescribing Notes",   "order": 2},
            {"doc_type": "eob-explanation",  "label": "EOB – Pharmacy",      "order": 3},
        ],
        "compatible_scenarios": ["chronic_medication", "specialty_drug", "compounded_medication"],
    },
}

SCENARIO_REGISTRY = {
    "general": "General claim",
    "hospital_admission": "Hospital inpatient admission",
    "surgery": "Surgical procedure",
    "emergency_visit": "Emergency room visit",
    "outpatient_procedure": "Outpatient procedure",
    "rear_end_collision": "Rear-end auto collision",
    "intersection_accident": "Intersection auto accident",
    "hit_and_run": "Hit and run incident",
    "fire_damage": "Fire damage to property",
    "water_damage": "Water/flood damage",
    "theft": "Property theft",
    "wind_damage": "Wind/storm damage",
    "slip_and_fall": "Slip and fall injury",
    "medical_malpractice": "Medical malpractice claim",
    "product_liability": "Product liability claim",
    "chronic_medication": "Chronic condition medication",
    "specialty_drug": "Specialty drug claim",
    "compounded_medication": "Compounded medication",
}

US_STATES = [
    {"code": "AL", "name": "Alabama"},
    {"code": "AK", "name": "Alaska"},
    {"code": "AZ", "name": "Arizona"},
    {"code": "AR", "name": "Arkansas"},
    {"code": "CA", "name": "California"},
    {"code": "CO", "name": "Colorado"},
    {"code": "CT", "name": "Connecticut"},
    {"code": "DE", "name": "Delaware"},
    {"code": "FL", "name": "Florida"},
    {"code": "GA", "name": "Georgia"},
    {"code": "HI", "name": "Hawaii"},
    {"code": "ID", "name": "Idaho"},
    {"code": "IL", "name": "Illinois"},
    {"code": "IN", "name": "Indiana"},
    {"code": "IA", "name": "Iowa"},
    {"code": "KS", "name": "Kansas"},
    {"code": "KY", "name": "Kentucky"},
    {"code": "LA", "name": "Louisiana"},
    {"code": "ME", "name": "Maine"},
    {"code": "MD", "name": "Maryland"},
    {"code": "MA", "name": "Massachusetts"},
    {"code": "MI", "name": "Michigan"},
    {"code": "MN", "name": "Minnesota"},
    {"code": "MS", "name": "Mississippi"},
    {"code": "MO", "name": "Missouri"},
    {"code": "MT", "name": "Montana"},
    {"code": "NE", "name": "Nebraska"},
    {"code": "NV", "name": "Nevada"},
    {"code": "NH", "name": "New Hampshire"},
    {"code": "NJ", "name": "New Jersey"},
    {"code": "NM", "name": "New Mexico"},
    {"code": "NY", "name": "New York"},
    {"code": "NC", "name": "North Carolina"},
    {"code": "ND", "name": "North Dakota"},
    {"code": "OH", "name": "Ohio"},
    {"code": "OK", "name": "Oklahoma"},
    {"code": "OR", "name": "Oregon"},
    {"code": "PA", "name": "Pennsylvania"},
    {"code": "RI", "name": "Rhode Island"},
    {"code": "SC", "name": "South Carolina"},
    {"code": "SD", "name": "South Dakota"},
    {"code": "TN", "name": "Tennessee"},
    {"code": "TX", "name": "Texas"},
    {"code": "UT", "name": "Utah"},
    {"code": "VT", "name": "Vermont"},
    {"code": "VA", "name": "Virginia"},
    {"code": "WA", "name": "Washington"},
    {"code": "WV", "name": "West Virginia"},
    {"code": "WI", "name": "Wisconsin"},
    {"code": "WY", "name": "Wyoming"},
]

LAYOUT_AXIS = {
    "police-report": "state",
    "auto-accident-report": "state",
    "property-loss-notice": "state",
}

FIXED_FORM_DOC_TYPES = ("acord-25", "cms-1500", "ub-04")


def layout_axis(doc_type: str) -> str | None:
    return LAYOUT_AXIS.get(doc_type)


def layout_keys(doc_type: str) -> list[dict]:
    if layout_axis(doc_type) != "state":
        return []
    return US_STATES
