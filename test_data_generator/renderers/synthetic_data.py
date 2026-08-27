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


def _mark(is_checked: bool) -> str:
    """Checkbox glyph for a data-driven form checkbox. Templates for the
    standardized forms (acord-25, cms-1500, ub-04) may never branch on a
    data value themselves (see the maintainer note atop cms_1500.html) - the
    placeholder-then-substitute render pass would see a placeholder string,
    not the real value, so any {% if %} there would always take the same
    branch. Deciding which box is ticked has to happen here instead, then
    the template just plain-substitutes the glyph like any other field."""
    return "☑" if is_checked else "☐"


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


_DIAG_POINTERS = ["A", "B", "C", "D"]


def _line_items(scenario: str):
    cpts = _cpt_codes(scenario)
    items = []
    for i, code in enumerate(cpts):
        charge = round(random.uniform(150, 2500), 2)
        items.append({
            "cpt": code,
            "description": f"Service code {code}",
            "units": 1,
            "charge": charge,
            "pos": "11",
            "modifier": "",
            "diag_pointer": _DIAG_POINTERS[i % len(_DIAG_POINTERS)],
            "emg": "",
        })
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
            "encounter_type": random.choice(["Office Visit", "Emergency Visit", "Follow-Up", "Consultation"]),
            "chief_complaint": _fake.sentence(nb_words=8),
            "hpi": _fake.paragraph(nb_sentences=4),
            "allergies": random.choice(["NKDA (No Known Drug Allergies)", "Penicillin", "Sulfa drugs", "Latex"]),
            "current_medications": [d[0] for d in random.sample(_NDC_DRUGS, 2)],
            "vitals": {
                "bp": f"{random.randint(100,140)}/{random.randint(60,90)}",
                "hr": str(random.randint(60, 100)),
                "temp": f"{round(random.uniform(97.5, 99.5), 1)}°F",
                "rr": str(random.randint(14, 20)),
                "spo2": f"{random.randint(95, 100)}%",
                "weight": f"{random.randint(120, 280)} lbs",
                "height": f"{random.randint(60, 74)} in",
            },
            "physical_exam": _fake.paragraph(nb_sentences=3),
            "assessment": _fake.sentence(nb_words=6),
            "plan": _fake.paragraph(nb_sentences=3),
            "signed_by": physician["physician_name"],
            "signed_date": dos.strftime("%m/%d/%Y"),
        })

    elif doc_type == "discharge-summary":
        admission_date = dos - timedelta(days=random.randint(1, 7))
        discharge_date = dos
        base.update({
            "attending_physician": physician["physician_name"],
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
        insurance_type = random.choice(
            ["Medicare", "Medicaid", "TRICARE", "CHAMPVA", "Group Health Plan", "FECA Blk Lung", "Other"]
        )
        illness_date = dos - timedelta(days=random.randint(0, 14))
        base.update({
            "insured_id": patient["insurance_id"],
            "insured_name": patient["patient_name"],
            "insured_dob": patient["dob"],
            "insured_gender": patient["gender"],
            "insured_address": patient["address"],
            "insured_phone": patient["phone"],
            "relationship_to_insured": "Self",
            "insurance_type": insurance_type,
            # One-of-seven payer checkbox row (cms_1500.html) - previously
            # hardcoded to always tick OTHER regardless of insurance_type,
            # so e.g. "Medicare" printed next to a ticked OTHER box instead
            # of a ticked MEDICARE box. Precomputed here, not with a
            # template {% if %}, per the placeholder-pass constraint.
            "payer_mark_medicare": _mark(insurance_type == "Medicare"),
            "payer_mark_medicaid": _mark(insurance_type == "Medicaid"),
            "payer_mark_tricare": _mark(insurance_type == "TRICARE"),
            "payer_mark_champva": _mark(insurance_type == "CHAMPVA"),
            "payer_mark_group_health": _mark(insurance_type == "Group Health Plan"),
            "payer_mark_feca": _mark(insurance_type == "FECA Blk Lung"),
            "payer_mark_other": _mark(insurance_type == "Other"),
            "insurance_type_other_label": insurance_type if insurance_type == "Other" else "",
            "employment_related": "NO",
            "auto_accident_related": "YES" if scenario in ("rear_end_collision", "intersection_accident", "slip_and_fall") else "NO",
            "auto_accident_state": random.choice(_STATES) if scenario in ("rear_end_collision", "intersection_accident") else "",
            "other_accident_related": "NO",
            "insured_policy_group": patient["group_number"],
            "date_of_illness": illness_date.strftime("%m/%d/%Y"),
            "date_of_illness_qualifier": random.choice(["431 Onset of Current Symptoms", "484 Last Menstrual Period"]),
            "unable_to_work_from": "",
            "unable_to_work_to": "",
            "hospitalization_from": "",
            "hospitalization_to": "",
            "outside_lab": "NO",
            "outside_lab_charges": 0.00,
            "additional_claim_info": "",
            "resubmission_code": "",
            "original_ref_number": "",
            "prior_auth_number": "AUTH" + "".join(random.choices(string.digits, k=8)),
            "federal_tax_id": "".join(random.choices(string.digits, k=9)),
            "federal_tax_id_type": "EIN",
            "patient_account_number": _mrn(),
            "accept_assignment": "YES",
            "total_charge": total,
            "amount_paid": 0.00,
            "balance_due": total,
            "rendering_provider_npi": _npi(),
            "service_facility": physician["hospital"],
            "service_facility_address": _address(),
            "billing_provider_name": physician["hospital"],
            "billing_provider_address": _address(),
            "billing_provider_phone": physician["phone"],
        })

    elif doc_type == "eob-explanation":
        allowed = round(total * 0.80, 2)
        paid = round(allowed * 0.80, 2)
        eob_lines = []
        remaining_allowed, remaining_paid = allowed, paid
        for i, item in enumerate(line_items):
            is_last = i == len(line_items) - 1
            line_allowed = remaining_allowed if is_last else round(item["charge"] * 0.80, 2)
            line_paid = remaining_paid if is_last else round(line_allowed * 0.80, 2)
            remaining_allowed -= line_allowed
            remaining_paid -= line_paid
            eob_lines.append({
                "cpt": item["cpt"], "billed": item["charge"], "allowed": line_allowed,
                "paid": line_paid, "patient_owes": round(line_allowed - line_paid, 2),
                "reason_code": random.choice(["", "", "CO-45"]),
            })
        base.update({
            "member_id": patient["insurance_id"],
            "group_number": patient["group_number"],
            "provider_name": physician["physician_name"],
            "eob_lines": eob_lines,
            "billed_amount": total,
            "allowed_amount": allowed,
            "plan_paid": paid,
            "paid_amount": paid,
            "patient_responsibility": round(allowed - paid, 2),
            "deductible_applied": round(random.uniform(0, 500), 2),
            "copay": round(random.uniform(20, 60), 2),
            "coinsurance": round(random.uniform(0, 200), 2),
            "denial_reason": None,
            "network_status": "In-Network",
            "processed_date": date.today().strftime("%m/%d/%Y"),
            "check_number": "CHK" + "".join(random.choices(string.digits, k=8)),
            "reason_code_legend": "CO-45: Charge exceeds fee schedule/maximum allowable amount",
        })

    elif doc_type == "acord-25":
        eff = dos
        exp = dos + timedelta(days=365)
        # Which checkbox is ticked in each either/or group - decided here
        # (never in the template, see _mark's docstring) so acord_25.html
        # and acord_new.html can both plain-substitute the resulting glyphs.
        gl_claims_basis = random.choice(["occurrence", "claims_made"])
        gl_aggregate_applies_per = random.choices(["policy", "project", "loc"], weights=[70, 20, 10])[0]
        auto_any_auto = random.random() < 0.6
        umbrella_form = random.choice(["umbrella", "excess"])
        umbrella_basis = random.choice(["occur", "claims_made"])
        umb_ded_or_retention = random.choice(["ded", "retention"])
        wc_officer_excluded = random.choices(["Y", "N"], weights=[25, 75])[0]
        wc_limits_basis = random.choices(["statutory", "other"], weights=[85, 15])[0]
        base.update({
            "certificate_date": date.today().strftime("%m/%d/%Y"),
            "producer_name": _fake.company() + " Insurance Agency",
            "producer_address": _address(),
            "producer_phone": _fake.phone_number(),
            "producer_email": _fake.company_email(),
            "insured_name": _fake.company(),
            "insured_address": _address(),
            "insurer_a": insurer,
            "insurer_a_naic": str(random.randint(10000, 99999)),
            "effective_date": eff.strftime("%m/%d/%Y"),
            "expiration_date": exp.strftime("%m/%d/%Y"),
            # Commercial General Liability
            "gl_policy_number": "GL" + "".join(random.choices(string.digits, k=8)),
            "gl_each_occurrence": "1,000,000",
            "gl_damage_rented_premises": "300,000",
            "gl_med_exp": "10,000",
            "gl_personal_injury": "1,000,000",
            "gl_general_aggregate": "2,000,000",
            "gl_products_agg": "2,000,000",
            "gl_occurrence_mark": _mark(gl_claims_basis == "occurrence"),
            "gl_claims_made_mark": _mark(gl_claims_basis == "claims_made"),
            "gl_agg_policy_mark": _mark(gl_aggregate_applies_per == "policy"),
            "gl_agg_project_mark": _mark(gl_aggregate_applies_per == "project"),
            "gl_agg_loc_mark": _mark(gl_aggregate_applies_per == "loc"),
            # Automobile Liability
            "auto_policy_number": "CA" + "".join(random.choices(string.digits, k=8)),
            "auto_combined_single_limit": "1,000,000",
            "auto_any_auto_mark": _mark(auto_any_auto),
            "auto_all_owned_mark": _mark(not auto_any_auto),
            "auto_scheduled_mark": _mark(not auto_any_auto),
            "auto_hired_mark": _mark(not auto_any_auto),
            "auto_non_owned_mark": _mark(not auto_any_auto),
            # Umbrella Liability
            "umb_policy_number": "UMB" + "".join(random.choices(string.digits, k=8)),
            "umb_each_occurrence": "2,000,000",
            "umb_aggregate": "2,000,000",
            "umb_umbrella_mark": _mark(umbrella_form == "umbrella"),
            "umb_excess_mark": _mark(umbrella_form == "excess"),
            "umb_occur_mark": _mark(umbrella_basis == "occur"),
            "umb_claims_made_mark": _mark(umbrella_basis == "claims_made"),
            "umb_ded_mark": _mark(umb_ded_or_retention == "ded"),
            "umb_retention_mark": _mark(umb_ded_or_retention == "retention"),
            # Workers Compensation & Employers' Liability
            "wc_policy_number": "WC" + "".join(random.choices(string.digits, k=8)),
            "wc_officer_excluded_y_mark": _mark(wc_officer_excluded == "Y"),
            "wc_officer_excluded_n_mark": _mark(wc_officer_excluded == "N"),
            "wc_statutory_mark": _mark(wc_limits_basis == "statutory"),
            "wc_other_mark": _mark(wc_limits_basis == "other"),
            "wc_el_each_accident": "500,000",
            "wc_el_disease_employee": "500,000",
            "wc_el_disease_policy": "500,000",
            "general_liability_limit": "1,000,000",
            "umbrella_limit": "2,000,000",
            "workers_comp_limit": "500,000",
            "description_of_operations": (
                "Certificate holder is named as additional insured with respect to General Liability, "
                "per attached endorsement, in connection with work performed by the insured."
            ),
            "certificate_holder": _fake.company(),
            "certificate_holder_address": _address(),
            "authorized_representative": _fake.name(),
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
            "case_status": random.choice(["Open", "Closed", "Under Investigation"]),
            "citation_issued": random.choice(["Yes", "No"]),
            "weather_conditions": random.choice(["Clear", "Rain", "Fog", "Snow", "Overcast"]),
            "road_conditions": random.choice(["Dry", "Wet", "Icy", "Under Construction"]),
            "narrative": _fake.paragraph(nb_sentences=5),
            "parties_involved": [
                {"name": _fake.name(), "role": "Driver 1", "dob": _fake.date_of_birth(minimum_age=18, maximum_age=70).strftime("%m/%d/%Y"), "license_number": _fake.bothify("??#######").upper()},
                {"name": _fake.name(), "role": "Driver 2", "dob": _fake.date_of_birth(minimum_age=18, maximum_age=70).strftime("%m/%d/%Y"), "license_number": _fake.bothify("??#######").upper()},
            ],
            "witnesses": [{"name": _fake.name(), "phone": _fake.phone_number()}],
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
            "insured_name": patient["patient_name"],
            "accident_date": dos.strftime("%m/%d/%Y"),
            "accident_time": f"{random.randint(0,23):02d}:{random.randint(0,59):02d}",
            "accident_location": _fake.street_address() + ", " + _fake.city() + ", " + random.choice(_STATES),
            "vehicle_info": {
                "year": str(random.randint(2010, 2024)),
                "make": random.choice(["Toyota", "Honda", "Ford", "Chevrolet", "BMW", "Tesla"]),
                "model": random.choice(["Camry", "Accord", "F-150", "Malibu", "3 Series", "Model 3"]),
                "vin": "".join(random.choices(string.ascii_uppercase + string.digits, k=17)),
                "license_plate": "".join(random.choices(string.ascii_uppercase, k=3)) + "".join(random.choices(string.digits, k=4)),
            },
            "driver_name": patient["patient_name"],
            "driver_license_number": _fake.bothify("??#######").upper(),
            "other_vehicle": {
                "year": str(random.randint(2010, 2024)),
                "make": random.choice(["Nissan", "Hyundai", "Jeep", "Subaru", "Mazda"]),
                "model": random.choice(["Altima", "Elantra", "Wrangler", "Outback", "CX-5"]),
                "license_plate": "".join(random.choices(string.ascii_uppercase, k=3)) + "".join(random.choices(string.digits, k=4)),
            },
            "other_driver_name": _fake.name(),
            "other_driver_insurer": random.choice(_INSURERS),
            "other_driver_policy_number": _policy_number(),
            "damage_description": _fake.sentence(nb_words=12),
            "estimated_damage": round(random.uniform(1500, 25000), 2),
            "airbags_deployed": random.choice(["Yes", "No"]),
            "vehicle_towed": random.choice(["Yes", "No"]),
            "police_report_number": "RPT" + "".join(random.choices(string.digits, k=8)),
            "at_fault": random.choice(["Yes", "No", "Disputed"]),
            "bodily_injury": random.choice(["Yes", "No"]),
            "witnesses": [{"name": _fake.name(), "phone": _fake.phone_number()}],
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
        rev_codes = [
            {"code": "0110", "description": "Room & Board – Medical/Surgical", "hcpcs": "", "units": 3, "charge": round(random.uniform(1500, 4000), 2)},
            {"code": "0250", "description": "Pharmacy", "hcpcs": "", "units": 1, "charge": round(random.uniform(100, 600), 2)},
            {"code": "0300", "description": "Laboratory", "hcpcs": "80053", "units": 1, "charge": round(random.uniform(200, 800), 2)},
            {"code": "0450", "description": "Emergency Room", "hcpcs": "99284", "units": 1, "charge": round(random.uniform(800, 2500), 2)},
            {"code": "0710", "description": "Recovery Room", "hcpcs": "", "units": 1, "charge": round(random.uniform(300, 900), 2)},
        ]
        ub_total = round(sum(r["charge"] for r in rev_codes), 2)
        base.update({
            "provider_name": physician["hospital"],
            "provider_address": _address(),
            "provider_npi": _npi(),
            "admission_date": adm_date.strftime("%m/%d/%Y"),
            "discharge_date": dos.strftime("%m/%d/%Y"),
            "statement_period_from": adm_date.strftime("%m/%d/%Y"),
            "statement_period_to": dos.strftime("%m/%d/%Y"),
            "type_of_bill": "111",
            "admission_hour": f"{random.randint(0,23):02d}",
            "admission_type": random.choice(["1 Emergency", "2 Urgent", "3 Elective"]),
            "admission_source": random.choice(["1 Physician Referral", "7 Emergency Room"]),
            "discharge_status": random.choice(["01 Discharged to Home", "02 Discharged/Transferred", "30 Still Patient"]),
            "condition_codes": [],
            "occurrence_codes": [{"code": "11", "date": dos.strftime("%m/%d/%Y")}],
            "value_codes": [{"code": "80", "amount": ub_total}],
            "revenue_codes": rev_codes,
            "total_charges": ub_total,
            "non_covered_charges": 0.00,
            "payer_name": insurer,
            "prior_payments": 0.00,
            "principal_diagnosis": icd_codes[0][0] if icd_codes else "",
            "other_diagnoses": [c[0] for c in icd_codes[1:]] if len(icd_codes) > 1 else [],
            "admitting_diagnosis": icd_codes[0][0] if icd_codes else "",
            "principal_procedure_code": (_cpt_codes(scenario) or [""])[0],
            "principal_procedure_date": dos.strftime("%m/%d/%Y"),
            "drg_code": str(random.randint(100, 999)),
            "patient_control_number": _mrn(),
            "medical_record_number": _mrn(),
            "attending_physician_npi": _npi(),
            "attending_physician_name": physician["physician_name"],
            "operating_physician_name": physician["physician_name"],
            "treatment_authorization": "AUTH" + "".join(random.choices(string.digits, k=8)),
        })

    return base
