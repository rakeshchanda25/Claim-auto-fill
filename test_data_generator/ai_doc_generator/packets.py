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
