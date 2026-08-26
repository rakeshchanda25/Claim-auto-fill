import random
import string
from datetime import date, timedelta
from faker import Faker

_fake = Faker()

_ICD10 = {
    "emergency_visit":    [("S09.90XA", "Unspecified injury of head"), ("M54.5", "Low back pain"), ("R07.9", "Chest pain, unspecified")],
    "surgery":            [("K80.20", "Calculus of gallbladder"), ("M23.20", "Derangement of meniscus"), ("K35.80", "Acute appendicitis")],
    "hospital_admission": [("I21.9", "Acute myocardial infarction"), ("J18.9", "Pneumonia, unspecified"), ("N39.0", "Urinary tract infection")],
    "outpatient_procedure": [("Z12.11", "Encounter for screening for colon cancer"), ("M54.4", "Lumbago with sciatica"), ("H52.4", "Presbyopia")],
    "slip_and_fall":      [("S52.501A", "Fracture of radius"), ("M79.3", "Panniculitis"), ("S09.90XA", "Unspecified injury of head")],
    "rear_end_collision": [("S14.0XXA", "Concussion of cervical spinal cord"), ("M54.2", "Cervicalgia"), ("S13.4XXA", "Sprain of ligaments of cervical spine")],
    "intersection_accident": [("S72.001A", "Fracture of femur"), ("S22.20XA", "Unspecified fracture of sternum"), ("S09.90XA", "Head injury")],
    "medical_malpractice": [("T80.89XA", "Other complications of surgical procedure"), ("N17.9", "Acute kidney failure")],
    "general":            [("Z00.00", "Encounter for general exam"), ("J06.9", "Acute upper respiratory infection"), ("M54.5", "Low back pain")],
}

_CPT = {
    "emergency_visit":    ["99283", "99284", "71046", "93000"],
    "surgery":            ["47562", "27447", "44950", "93454"],
    "hospital_admission": ["99223", "99232", "93010", "80053"],
    "outpatient_procedure": ["45378", "97110", "92015", "99213"],
    "general":            ["99213", "93000", "85025", "80053"],
}

_NDC_DRUGS = [
    ("Lisinopril 10mg", "00378-2145-01", "tablet"),
    ("Atorvastatin 40mg", "00093-7278-98", "tablet"),
    ("Metformin 500mg", "00591-0217-01", "tablet"),
    ("Amoxicillin 500mg", "00093-4152-01", "capsule"),
    ("Alprazolam 0.5mg", "00378-4006-10", "tablet"),
    ("Omeprazole 20mg", "00378-4021-10", "capsule"),
    ("Sertraline 50mg", "00093-7225-56", "tablet"),
    ("Hydrocodone 5mg/Acetaminophen 325mg", "00406-0512-01", "tablet"),
]

_STATES = ["CA", "TX", "FL", "NY", "PA", "OH", "GA", "NC", "MI", "NJ"]
_INSURERS = ["BlueCross BlueShield", "Aetna", "Cigna", "United Healthcare", "Humana", "Anthem", "Kaiser Permanente"]
_HOSPITALS = ["St. Mary's Medical Center", "General Hospital", "Regional Medical Center", "University Hospital", "Memorial Health System"]
_SPECIALTIES = ["Internal Medicine", "Emergency Medicine", "Orthopedics", "Cardiology", "Family Medicine", "Neurology"]


def _rand_date_recent(years_back=2) -> date:
    start = date.today() - timedelta(days=years_back * 365)
    return start + timedelta(days=random.randint(0, years_back * 365))


def _mrn():
    return str(random.randint(1000000, 9999999))


def _claim_number():
    return "CLM" + "".join(random.choices(string.digits, k=10))


def _policy_number():
    return "POL" + "".join(random.choices(string.ascii_uppercase + string.digits, k=9))


def _npi():
    return "".join(random.choices(string.digits, k=10))


def _rx_number():
    return "RX" + "".join(random.choices(string.digits, k=8))


def _icd10_codes(scenario: str, count: int = 2):
    pool = _ICD10.get(scenario, _ICD10["general"])
    return random.sample(pool, min(count, len(pool)))


def _cpt_codes(scenario: str, count: int = 3):
    pool = _CPT.get(scenario, _CPT["general"])
    return random.sample(pool, min(count, len(pool)))


def _line_items(scenario: str):
    cpts = _cpt_codes(scenario)
    items = []
    for code in cpts:
        charge = round(random.uniform(150, 2500), 2)
        items.append({"cpt": code, "description": f"Service code {code}", "units": 1, "charge": charge})
    return items


def _address():
    return {
        "street": _fake.street_address(),
        "city": _fake.city(),
        "state": random.choice(_STATES),
        "zip": _fake.zipcode(),
    }


def _build_patient():
    return {
        "patient_name": _fake.name(),
        "dob": _fake.date_of_birth(minimum_age=18, maximum_age=85).strftime("%m/%d/%Y"),
        "gender": random.choice(["Male", "Female"]),
        "address": _address(),
        "phone": _fake.phone_number(),
        "mrn": _mrn(),
        "insurance_id": "INS" + "".join(random.choices(string.digits, k=9)),
        "group_number": "GRP" + "".join(random.choices(string.digits, k=6)),
    }


def _build_physician():
    specialty = random.choice(_SPECIALTIES)
    return {
        "physician_name": "Dr. " + _fake.name(),
        "npi": _npi(),
        "specialty": specialty,
        "dea": "B" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8)),
        "phone": _fake.phone_number(),
        "hospital": random.choice(_HOSPITALS),
    }


def build_synthetic_data(doc_type: str, scenario: str = "general") -> dict:
    patient = _build_patient()
    physician = _build_physician()
    insurer = random.choice(_INSURERS)
    dos = _rand_date_recent()
    icd_codes = _icd10_codes(scenario)
    line_items = _line_items(scenario)
    total = round(sum(i["charge"] for i in line_items), 2)
    claim_num = _claim_number()
    policy_num = _policy_number()

    base = {
        **patient,
        **physician,
        "insurer_name": insurer,
        "dos": dos.strftime("%m/%d/%Y"),
        "dos_from": dos.strftime("%m/%d/%Y"),
        "dos_to": (dos + timedelta(days=random.randint(0, 3))).strftime("%m/%d/%Y"),
        "service_date": dos.strftime("%m/%d/%Y"),
        "diagnosis_codes": icd_codes,
        "procedure_codes": _cpt_codes(scenario),
        "line_items": line_items,
        "total_amount": total,
        "claim_number": claim_num,
        "policy_number": policy_num,
        "provider_npi": _npi(),
        "scenario": scenario,
    }

    if doc_type == "medical-record":
        base.update({
            "chief_complaint": _fake.sentence(nb_words=8),
            "hpi": _fake.paragraph(nb_sentences=4),
            "vitals": {
                "bp": f"{random.randint(100,140)}/{random.randint(60,90)}",
                "hr": str(random.randint(60, 100)),
                "temp": f"{round(random.uniform(97.5, 99.5), 1)}°F",
                "rr": str(random.randint(14, 20)),
                "spo2": f"{random.randint(95, 100)}%",
                "weight": f"{random.randint(120, 280)} lbs",
            },
            "physical_exam": _fake.paragraph(nb_sentences=3),
            "assessment": _fake.sentence(nb_words=6),
            "plan": _fake.paragraph(nb_sentences=3),
        })

    elif doc_type == "discharge-summary":
        admission_date = dos - timedelta(days=random.randint(1, 7))
        discharge_date = dos
        base.update({
            "admission_date": admission_date.strftime("%m/%d/%Y"),
            "discharge_date": discharge_date.strftime("%m/%d/%Y"),
            "admission_diagnosis": icd_codes[0][1] if icd_codes else "Acute illness",
            "discharge_diagnosis": icd_codes[0][1] if icd_codes else "Resolved",
            "hospital_course": _fake.paragraph(nb_sentences=5),
            "discharge_condition": random.choice(["Stable", "Improved", "Good"]),
            "discharge_instructions": _fake.paragraph(nb_sentences=3),
            "follow_up": f"Follow up with {physician['physician_name']} in {random.randint(7, 21)} days",
            "medications_at_discharge": [
                {"name": d[0], "dose": "As directed", "frequency": "Daily"}
                for d in random.sample(_NDC_DRUGS, 3)
            ],
            "drg_code": str(random.randint(100, 999)),
            "length_of_stay": str((discharge_date - admission_date).days),
        })

    elif doc_type == "medical-bill":
        base.update({
            "account_number": "ACC" + "".join(random.choices(string.digits, k=8)),
            "statement_date": date.today().strftime("%m/%d/%Y"),
            "due_date": (date.today() + timedelta(days=30)).strftime("%m/%d/%Y"),
            "amount_due": total,
            "amount_paid": 0.00,
            "adjustments": round(total * 0.15, 2),
            "balance": round(total * 0.85, 2),
        })

    elif doc_type == "cms-1500":
        base.update({
            "insured_id": patient["insurance_id"],
            "insured_name": patient["patient_name"],
            "insured_dob": patient["dob"],
            "relationship_to_insured": "Self",
            "prior_auth_number": "AUTH" + "".join(random.choices(string.digits, k=8)),
            "federal_tax_id": "".join(random.choices(string.digits, k=9)),
            "accept_assignment": "YES",
            "total_charge": total,
            "amount_paid": 0.00,
            "rendering_provider_npi": _npi(),
        })

    elif doc_type == "eob-explanation":
        allowed = round(total * 0.80, 2)
        paid = round(allowed * 0.80, 2)
        base.update({
            "member_id": patient["insurance_id"],
            "billed_amount": total,
            "allowed_amount": allowed,
            "plan_paid": paid,
            "patient_responsibility": round(allowed - paid, 2),
            "deductible_applied": round(random.uniform(0, 500), 2),
            "copay": round(random.uniform(20, 60), 2),
            "coinsurance": round(random.uniform(0, 200), 2),
            "denial_reason": None,
        })

    elif doc_type == "acord-25":
        base.update({
            "insured_name": _fake.company(),
            "agency_name": _fake.company() + " Insurance Agency",
            "agency_address": _address(),
            "effective_date": dos.strftime("%m/%d/%Y"),
            "expiration_date": (dos + timedelta(days=365)).strftime("%m/%d/%Y"),
            "general_liability_limit": "1,000,000",
            "umbrella_limit": "2,000,000",
            "workers_comp_limit": "500,000",
            "certificate_holder": _fake.company(),
            "certificate_holder_address": _address(),
        })

    elif doc_type == "police-report":
        base.update({
            "incident_number": "RPT" + "".join(random.choices(string.digits, k=8)),
            "incident_date": dos.strftime("%m/%d/%Y"),
            "incident_time": f"{random.randint(0,23):02d}:{random.randint(0,59):02d}",
            "location": _fake.street_address() + ", " + _fake.city() + ", " + random.choice(_STATES),
            "officer_name": "Officer " + _fake.last_name(),
            "badge_number": str(random.randint(1000, 9999)),
            "department": _fake.city() + " Police Department",
            "narrative": _fake.paragraph(nb_sentences=5),
            "parties_involved": [
                {"name": _fake.name(), "role": "Driver 1", "dob": _fake.date_of_birth(minimum_age=18, maximum_age=70).strftime("%m/%d/%Y")},
                {"name": _fake.name(), "role": "Driver 2", "dob": _fake.date_of_birth(minimum_age=18, maximum_age=70).strftime("%m/%d/%Y")},
            ],
        })

    elif doc_type == "demand-letter":
        demand_amt = round(random.uniform(25000, 500000), 2)
        base.update({
            "claimant_name": patient["patient_name"],
            "claimant_attorney": "Law Offices of " + _fake.last_name() + " & " + _fake.last_name(),
            "attorney_address": _address(),
            "bar_number": "BAR" + "".join(random.choices(string.digits, k=6)),
            "incident_date": dos.strftime("%m/%d/%Y"),
            "demand_amount": demand_amt,
            "special_damages": round(demand_amt * 0.4, 2),
            "general_damages": round(demand_amt * 0.6, 2),
            "settlement_deadline": (date.today() + timedelta(days=30)).strftime("%m/%d/%Y"),
            "letter_date": date.today().strftime("%m/%d/%Y"),
            "facts_summary": _fake.paragraph(nb_sentences=6),
        })

    elif doc_type == "pharmacy-invoice":
        drug = random.choice(_NDC_DRUGS)
        qty = random.choice([30, 60, 90])
        unit_price = round(random.uniform(1.5, 25.0), 2)
        base.update({
            "rx_number": _rx_number(),
            "fill_date": dos.strftime("%m/%d/%Y"),
            "drug_name": drug[0],
            "ndc_code": drug[1],
            "form": drug[2],
            "quantity": qty,
            "days_supply": qty,
            "unit_price": unit_price,
            "total_charge": round(unit_price * qty, 2),
            "dispensing_fee": round(random.uniform(2.0, 5.0), 2),
            "copay": round(random.uniform(5.0, 50.0), 2),
            "pharmacy_name": _fake.company() + " Pharmacy",
            "pharmacy_npi": _npi(),
            "pharmacy_address": _address(),
            "prescriber_name": physician["physician_name"],
            "prescriber_dea": physician["dea"],
            "prescriber_npi": physician["npi"],
        })

    elif doc_type == "property-loss-notice":
        base.update({
            "insured_name": _fake.name(),
            "loss_date": dos.strftime("%m/%d/%Y"),
            "loss_location": _fake.street_address() + ", " + _fake.city() + ", " + random.choice(_STATES),
            "cause_of_loss": scenario.replace("_", " ").title(),
            "property_description": _fake.sentence(nb_words=8),
            "estimated_loss": round(random.uniform(5000, 150000), 2),
            "mortgagee_name": _fake.company() + " Bank",
            "loan_number": "LN" + "".join(random.choices(string.digits, k=10)),
            "coverage_type": random.choice(["Dwelling", "Contents", "Both"]),
            "deductible": round(random.uniform(500, 5000), 2),
            "adjuster_name": _fake.name(),
            "adjuster_phone": _fake.phone_number(),
        })

    elif doc_type == "auto-accident-report":
        base.update({
            "accident_date": dos.strftime("%m/%d/%Y"),
            "accident_location": _fake.street_address() + ", " + _fake.city() + ", " + random.choice(_STATES),
            "vehicle_info": {
                "year": str(random.randint(2010, 2024)),
                "make": random.choice(["Toyota", "Honda", "Ford", "Chevrolet", "BMW", "Tesla"]),
                "model": random.choice(["Camry", "Accord", "F-150", "Malibu", "3 Series", "Model 3"]),
                "vin": "".join(random.choices(string.ascii_uppercase + string.digits, k=17)),
                "license_plate": "".join(random.choices(string.ascii_uppercase, k=3)) + "".join(random.choices(string.digits, k=4)),
            },
            "damage_description": _fake.sentence(nb_words=12),
            "airbags_deployed": random.choice(["Yes", "No"]),
            "police_report_number": "RPT" + "".join(random.choices(string.digits, k=8)),
            "at_fault": random.choice(["Yes", "No", "Disputed"]),
            "bodily_injury": random.choice(["Yes", "No"]),
        })

    elif doc_type == "litigation-document":
        base.update({
            "plaintiff_name": patient["patient_name"],
            "defendant_name": _fake.company(),
            "case_number": f"CV-{dos.year}-{random.randint(10000, 99999)}",
            "court_name": f"Superior Court of {_fake.state()}",
            "jurisdiction": _fake.state(),
            "incident_date": dos.strftime("%m/%d/%Y"),
            "filing_date": date.today().strftime("%m/%d/%Y"),
            "causes_of_action": ["Negligence", "Breach of Duty"],
            "prayer_for_relief": f"${round(random.uniform(50000, 1000000), 0):,.0f}",
            "attorney_name": "Esq. " + _fake.name(),
            "bar_number": "BAR" + "".join(random.choices(string.digits, k=6)),
            "facts": _fake.paragraph(nb_sentences=6),
        })

    elif doc_type == "ub-04":
        adm_date = dos - timedelta(days=random.randint(1, 5))
        base.update({
            "admission_date": adm_date.strftime("%m/%d/%Y"),
            "discharge_date": dos.strftime("%m/%d/%Y"),
            "type_of_bill": "111",
            "revenue_codes": [
                {"code": "0110", "description": "Room & Board – Medical/Surgical", "units": 3, "charge": round(random.uniform(1500, 4000), 2)},
                {"code": "0300", "description": "Laboratory", "units": 1, "charge": round(random.uniform(200, 800), 2)},
                {"code": "0450", "description": "Emergency Room", "units": 1, "charge": round(random.uniform(800, 2500), 2)},
            ],
            "total_charges": total,
            "payer_name": insurer,
            "drg_code": str(random.randint(100, 999)),
            "patient_control_number": _mrn(),
            "medical_record_number": _mrn(),
            "attending_physician_npi": _npi(),
        })

    return base
