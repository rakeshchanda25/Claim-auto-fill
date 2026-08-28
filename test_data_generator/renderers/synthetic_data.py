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

# Real insurance limits cluster on round, standard tiers - the realism is in
# varying WHICH tier lands on a given certificate, not in avoiding round
# numbers altogether. Each GL tier keeps its own sub-limits internally
# consistent (aggregate tracks occurrence, products-comp/op agg = general
# aggregate), matching how these are actually sold as a package.
_GL_LIMIT_TIERS = [
    # (each_occurrence, damage_rented_premises, med_exp, personal_adv_injury, general_aggregate, products_comp_op_agg)
    (500_000, 100_000, 5_000, 500_000, 1_000_000, 1_000_000),
    (1_000_000, 100_000, 5_000, 1_000_000, 2_000_000, 2_000_000),
    (1_000_000, 300_000, 10_000, 1_000_000, 2_000_000, 2_000_000),
    (2_000_000, 300_000, 10_000, 2_000_000, 4_000_000, 4_000_000),
]
_AUTO_CSL_TIERS = [500_000, 1_000_000, 2_000_000]
_UMBRELLA_TIERS = [1_000_000, 2_000_000, 5_000_000, 10_000_000]
_WC_EL_TIERS = [
    # (each_accident, disease_ea_employee, disease_policy_limit)
    (100_000, 500_000, 500_000),
    (500_000, 500_000, 500_000),
    (1_000_000, 1_000_000, 1_000_000),
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


# A template that is a visual redesign/variant of another form reads exactly
# the same fields as its parent, so it must resolve to the parent's data
# contract. Without this, build_synthetic_data falls through every branch
# below and returns only `base` - every form-specific field then renders
# blank, which is precisely how a brand-new template silently produces an
# empty document. Add one line here when adding a variant template.
_DOC_TYPE_ALIASES = {
    "acord-new": "acord-25",
    "acord_new": "acord-25",
    "police-report-new": "police-report",
    "police_report_new": "police-report",
    "litigation-document-new": "litigation-document",
    "litigation_document_new": "litigation-document",
    "ub-04-new": "ub-04",
    "ub_04_new": "ub-04",
}


def resolve_doc_type(doc_type: str) -> str:
    """Maps a variant template's doc_type onto the parent form whose data
    contract it shares. Every consumer that keys off doc_type must go
    through this, or a variant silently gets the 'unknown doc type' path."""
    return _DOC_TYPE_ALIASES.get(doc_type, doc_type)


def build_synthetic_data(doc_type: str, scenario: str = "general") -> dict:
    doc_type = resolve_doc_type(doc_type)
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
        # Adjustment (contractual write-off) rate varies by payer/negotiated
        # rate in reality - was pinned to 15% on every bill, so "balance" was
        # always exactly 85% of the charge no matter what.
        adjustments = round(total * random.uniform(0.05, 0.30), 2)
        base.update({
            "account_number": "ACC" + "".join(random.choices(string.digits, k=8)),
            "statement_date": date.today().strftime("%m/%d/%Y"),
            "due_date": (date.today() + timedelta(days=30)).strftime("%m/%d/%Y"),
            "amount_due": total,
            "amount_paid": 0.00,
            "adjustments": adjustments,
            "balance": round(total - adjustments, 2),
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
        # Allowed-of-billed and paid-of-allowed rates depend on the specific
        # plan/network - both were pinned to 80% on every EOB, so the ratio
        # between billed/allowed/paid never actually varied between claims.
        # Computed once and reused for both the claim total and each line, so
        # the per-line breakdown still reconciles exactly to the totals.
        allowed_rate = round(random.uniform(0.60, 0.90), 2)
        paid_rate = round(random.uniform(0.70, 0.95), 2)
        allowed = round(total * allowed_rate, 2)
        paid = round(allowed * paid_rate, 2)
        eob_lines = []
        remaining_allowed, remaining_paid = allowed, paid
        for i, item in enumerate(line_items):
            is_last = i == len(line_items) - 1
            line_allowed = remaining_allowed if is_last else round(item["charge"] * allowed_rate, 2)
            line_paid = remaining_paid if is_last else round(line_allowed * paid_rate, 2)
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
            "network_status": random.choices(["In-Network", "Out-of-Network"], weights=[85, 15])[0],
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
        gl_occ, gl_rented, gl_med, gl_pers, gl_agg, gl_prod = random.choice(_GL_LIMIT_TIERS)
        auto_csl = random.choice(_AUTO_CSL_TIERS)
        umb_limit = random.choice(_UMBRELLA_TIERS)
        wc_accident, wc_disease_ee, wc_disease_policy = random.choice(_WC_EL_TIERS)
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
            "gl_each_occurrence": f"{gl_occ:,}",
            "gl_damage_rented_premises": f"{gl_rented:,}",
            "gl_med_exp": f"{gl_med:,}",
            "gl_personal_injury": f"{gl_pers:,}",
            "gl_general_aggregate": f"{gl_agg:,}",
            "gl_products_agg": f"{gl_prod:,}",
            "gl_occurrence_mark": _mark(gl_claims_basis == "occurrence"),
            "gl_claims_made_mark": _mark(gl_claims_basis == "claims_made"),
            "gl_agg_policy_mark": _mark(gl_aggregate_applies_per == "policy"),
            "gl_agg_project_mark": _mark(gl_aggregate_applies_per == "project"),
            "gl_agg_loc_mark": _mark(gl_aggregate_applies_per == "loc"),
            # Automobile Liability
            "auto_policy_number": "CA" + "".join(random.choices(string.digits, k=8)),
            "auto_combined_single_limit": f"{auto_csl:,}",
            "auto_any_auto_mark": _mark(auto_any_auto),
            "auto_all_owned_mark": _mark(not auto_any_auto),
            "auto_scheduled_mark": _mark(not auto_any_auto),
            "auto_hired_mark": _mark(not auto_any_auto),
            "auto_non_owned_mark": _mark(not auto_any_auto),
            # Umbrella Liability
            "umb_policy_number": "UMB" + "".join(random.choices(string.digits, k=8)),
            "umb_each_occurrence": f"{umb_limit:,}",
            "umb_aggregate": f"{umb_limit:,}",
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
            "wc_el_each_accident": f"{wc_accident:,}",
            "wc_el_disease_employee": f"{wc_disease_ee:,}",
            "wc_el_disease_policy": f"{wc_disease_policy:,}",
            "general_liability_limit": f"{gl_occ:,}",
            "umbrella_limit": f"{umb_limit:,}",
            "workers_comp_limit": f"{wc_accident:,}",
            "description_of_operations": (
                "Certificate holder is named as additional insured with respect to General Liability, "
                "per attached endorsement, in connection with work performed by the insured."
            ),
            "certificate_holder": _fake.company(),
            "certificate_holder_address": _address(),
            "authorized_representative": _fake.name(),
        })

    elif doc_type == "police-report":
        report_city = _fake.city()
        report_state = random.choice(_STATES)
        dispatch_t = f"{random.randint(6,22):02d}:{random.randint(0,59):02d}"
        arrival_t = f"{random.randint(6,22):02d}:{random.randint(0,59):02d}"
        cleared_t = f"{random.randint(6,22):02d}:{random.randint(0,59):02d}"
        hit_and_run_flag = random.random() < 0.08
        cited = random.random() < 0.6

        def _party(role: str, at_fault: bool) -> dict:
            year = random.randint(2012, 2024)
            make, model = random.choice([
                ("Toyota", "Camry"), ("Honda", "Accord"), ("Ford", "F-150"),
                ("Chevrolet", "Malibu"), ("Nissan", "Altima"), ("BMW", "3 Series"),
            ])
            severity = random.choice(["None", "Minor", "Moderate", "Major"]) if not at_fault else random.choice(["Moderate", "Major"])
            injured = random.choice(["No", "Yes - Complaint of pain", "Yes - Visible injury"]) if at_fault else "No"
            return {
                "name": _fake.name(),
                "role": role,
                "dob": _fake.date_of_birth(minimum_age=18, maximum_age=75).strftime("%m/%d/%Y"),
                "sex": random.choice(["M", "F"]),
                "license_number": _fake.bothify("?#######").upper(),
                "license_state": random.choice(_STATES),
                "license_class": random.choice(["A", "B", "C"]),
                "address": _fake.street_address() + ", " + _fake.city() + ", " + random.choice(_STATES),
                "phone": _fake.phone_number(),
                "injured": injured,
                "vehicle_year": str(year),
                "vehicle_make": make,
                "vehicle_model": model,
                "vehicle_plate": "".join(random.choices(string.ascii_uppercase, k=3)) + "".join(random.choices(string.digits, k=4)),
                "vehicle_plate_state": random.choice(_STATES),
                "vehicle_vin": "".join(random.choices(string.ascii_uppercase + string.digits, k=17)),
                "registered_owner": _fake.name() if random.random() < 0.7 else _fake.company(),
                "insurer": random.choice(_INSURERS),
                "policy_number": _policy_number(),
                "damage_severity": severity,
                "damage_description": _fake.sentence(nb_words=10),
                "towed": "Yes" if severity == "Major" else "No",
                "citation_number": ("CIT" + "".join(random.choices(string.digits, k=8))) if (at_fault and cited) else "None",
                "at_fault": at_fault,
                "seat_position": "Driver",
                "restraint": "Lap/Shoulder",
                "transported_to": (_fake.company() + " Medical Center") if injured != "No" else "-",
            }

        party1 = _party("Driver 1", at_fault=False)
        party2 = _party("Driver 2", at_fault=True)

        base.update({
            "incident_number": "RPT" + "".join(random.choices(string.digits, k=8)),
            "local_report_number": "TC-" + str(dos.year) + "-" + "".join(random.choices(string.digits, k=5)),
            "cad_incident_number": f"{random.randint(20,29)}-CH-{random.randint(100000,999999)}",
            "incident_date": dos.strftime("%m/%d/%Y"),
            "incident_time": f"{random.randint(0,23):02d}:{random.randint(0,59):02d}",
            "report_date": dos.strftime("%m/%d/%Y"),
            "dispatch_time": dispatch_t,
            "arrival_time": arrival_t,
            "cleared_time": cleared_t,
            "location": _fake.street_address() + ", " + report_city + ", " + report_state,
            "city": report_city,
            "county": _fake.city() + " County",
            "officer_name": "Officer " + _fake.last_name(),
            "badge_number": str(random.randint(1000, 9999)),
            "department": report_city + " Police Department",
            "department_address": _fake.street_address() + ", " + report_city + ", " + report_state + " " + _fake.zipcode(),
            "department_phone": _fake.phone_number(),
            "department_records_phone": _fake.phone_number(),
            "department_records_email": "records@" + report_city.lower().replace(" ", "") + "pd.example",
            "department_ori": report_state + str(random.randint(100000, 999999)),
            "department_ncic": str(random.randint(100000, 999999)),
            "case_status": random.choice(["Open", "Closed", "Under Investigation"]),
            "citation_issued": "Yes" if cited else "No",
            "weather_conditions": random.choice(["Clear", "Rain", "Fog", "Snow", "Overcast"]),
            "lighting_conditions": random.choice(["Daylight", "Dusk", "Dark - Street Lights", "Dark - No Street Lights"]),
            "road_conditions": random.choice(["Dry", "Wet", "Icy", "Under Construction"]),
            "traffic_control": random.choice(["Signal - functioning", "Stop Sign", "None", "Officer/Flagger"]),
            "speed_limit": str(random.choice([25, 35, 45, 55, 65])) + " MPH",
            "collision_type": random.choice(["Rear-end", "Sideswipe", "Head-on", "Angle", "Single Vehicle"]),
            "num_vehicles": "2",
            "hit_and_run": "Yes" if hit_and_run_flag else "No",
            "primary_factor": random.choice([
                "Unsafe speed for conditions", "Following too closely", "Failure to yield right of way",
                "Improper turn", "Driver inattention",
            ]),
            "other_factors": random.choice(["None noted", "Stop-and-go congestion", "Wet roadway", "Sun glare"]),
            "narrative": _fake.paragraph(nb_sentences=5),
            "narrative_paragraphs": [_fake.paragraph(nb_sentences=4) for _ in range(3)],
            "parties_involved": [party1, party2],
            "property_damage_items": [
                {
                    "item": random.choice(["Guardrail section", "Street sign", "Fence"]),
                    "owner": random.choice(["City Public Works", "Private property owner", "State DOT"]),
                    "est_value": round(random.uniform(500, 5000), 2),
                    "reference": "PW-" + "".join(random.choices(string.digits, k=6)),
                }
            ],
            "cargo_involved": "No cargo involved.",
            "hazmat": "No",
            "witnesses": [
                {
                    "name": _fake.name(), "address": _fake.street_address() + ", " + report_city + ", " + report_state,
                    "phone": _fake.phone_number(), "statement": _fake.sentence(nb_words=16),
                }
            ],
            "enforcement_party_cited": "Party 2" if cited else "None",
            "enforcement_citation_number": party2["citation_number"],
            "enforcement_sections_charged": "Traffic code violation" if cited else "N/A",
            "enforcement_court_date": (dos + timedelta(days=60)).strftime("%m/%d/%Y") if cited else "N/A",
            "enforcement_court_name": f"{report_state} Superior Court, Traffic Division" if cited else "N/A",
            "chemical_test": "Declined - no objective signs of impairment observed.",
            "arrest_made": "No",
            "evidence_items": [
                {"item_no": "001", "description": "Digital photographs, scene and vehicle damage."},
                {"item_no": "002", "description": "Field sketch and measurements."},
            ],
            "reporting_officer_badge": str(random.randint(1000, 9999)),
            "reporting_officer_unit": f"TRF-{random.randint(1,20)}",
            "reporting_officer_date": dos.strftime("%m/%d/%Y"),
            "reporting_officer_time": f"{random.randint(15,23):02d}:{random.randint(0,59):02d}",
            "report_status": "Approved",
            "supervisor_name": "Sgt. " + _fake.last_name(),
            "supervisor_badge": str(random.randint(1000, 9999)),
            "supervisor_approval_date": (dos + timedelta(days=1)).strftime("%m/%d/%Y"),
            "records_custodian": _fake.name(),
            "records_release_date": (dos + timedelta(days=7)).strftime("%m/%d/%Y"),
            "records_request_number": "R-" + str(dos.year) + "-" + "".join(random.choices(string.digits, k=4)),
            "page_count": "3",
        })

    elif doc_type == "demand-letter":
        demand_amt = round(random.uniform(25000, 500000), 2)
        # Special-vs-general damages split depends on the case's own medical
        # specials, not a fixed formula - was pinned to a 40/60 split on every
        # letter. special_damages computed first, general_damages takes the
        # remainder so the two still sum exactly to demand_amt.
        special_damages = round(demand_amt * random.uniform(0.25, 0.55), 2)
        base.update({
            "claimant_name": patient["patient_name"],
            "claimant_attorney": "Law Offices of " + _fake.last_name() + " & " + _fake.last_name(),
            "attorney_address": _address(),
            "bar_number": "BAR" + "".join(random.choices(string.digits, k=6)),
            "incident_date": dos.strftime("%m/%d/%Y"),
            "demand_amount": demand_amt,
            "special_damages": special_damages,
            "general_damages": round(demand_amt - special_damages, 2),
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
        plaintiff_state = _fake.state()
        forum_state = _fake.state()
        forum_county = _fake.city() + " County"
        filing_date_val = date.today()
        prayer_amount = round(random.uniform(50000, 1000000), 0)
        causes = random.sample([
            "Negligence", "Breach of Duty of Care", "Premises Liability",
            "Negligent Infliction of Emotional Distress", "Strict Product Liability",
        ], k=random.choice([2, 3]))

        def _attorney(role: str = "") -> dict:
            return {
                "name": _fake.name(),
                "bar_number": str(random.randint(100000, 299999)),
                "role": role,
            }

        lead_attorney = _attorney("Managing Partner")
        firm_attorneys = [lead_attorney] + [_attorney() for _ in range(random.randint(2, 4))]
        firm_last_names = [a["name"].split()[-1] for a in firm_attorneys[:3]]

        base.update({
            "plaintiff_name": patient["patient_name"],
            "plaintiff_state_of_incorporation": plaintiff_state,
            "defendant_name": _fake.company(),
            "defendant_state": _fake.state(),
            "case_number": f"CV-{dos.year}-{random.randint(10000, 99999)}",
            "court_name": f"Superior Court of {forum_state}",
            "court_county": forum_county,
            "court_dept": f"Dept. {random.randint(1, 40)}",
            "judge_name": "Hon. " + _fake.name(),
            "jurisdiction": forum_state,
            "incident_date": dos.strftime("%m/%d/%Y"),
            "filing_date": filing_date_val.strftime("%m/%d/%Y"),
            "filing_time": f"{random.randint(8,16):02d}:{random.randint(0,59):02d} {'a.m.' if random.random()<0.5 else 'p.m.'}",
            "filing_clerk": _fake.name(),
            "case_management_date": (filing_date_val + timedelta(days=90)).strftime("%m/%d/%Y"),
            "causes_of_action": causes,
            "prayer_for_relief": f"${prayer_amount:,.0f}",
            "prayer_amount_numeric": prayer_amount,
            "attorney_name": "Esq. " + lead_attorney["name"],
            "bar_number": "BAR" + "".join(random.choices(string.digits, k=6)),
            "facts": _fake.paragraph(nb_sentences=6),
            "general_allegations": [_fake.paragraph(nb_sentences=3) for _ in range(3)],
            # --- law firm letterhead / recreate-style visual template ---
            "firm_name": ", ".join(firm_last_names) + " LLP",
            "firm_tagline": "Attorneys at Law",
            "firm_practice_areas": "Civil Litigation · Personal Injury · Appellate Practice",
            "firm_attorneys": firm_attorneys,
            "firm_address": _fake.street_address() + ", Suite " + str(random.randint(200, 2400)),
            "firm_city_state_zip": _fake.city() + ", " + plaintiff_state + " " + _fake.zipcode(),
            "firm_phone": _fake.phone_number(),
            "firm_fax": _fake.phone_number(),
            "firm_email": lead_attorney["name"].split()[-1].lower() + "@" + "".join(firm_last_names).lower()[:12] + "law.example",
            "opposing_counsel_name": _fake.name() + ", Esq.",
            "opposing_firm_name": _fake.last_name() + " & " + _fake.last_name() + " PC",
            "opposing_firm_address": _fake.street_address() + ", " + _fake.city() + ", " + _fake.state() + " " + _fake.zipcode(),
            "letter_recipient_note": "Via Certified Mail — Return Receipt Requested",
            "letter_reference": _fake.paragraph(nb_sentences=2),
            "prayer_items": [
                f"For general and compensatory damages in the sum of {prayer_amount:,.0f} dollars, or according to proof at trial",
                "For costs of suit incurred herein",
                "For such other and further relief as the Court may deem just and proper",
            ],
            "verifier_name": _fake.name(),
            "verifier_title": "Authorized Representative",
            "verification_date": filing_date_val.strftime("%m/%d/%Y"),
            "notary_name": _fake.name(),
            "notary_commission_number": str(random.randint(1000000, 9999999)),
            "notary_commission_expires": (filing_date_val + timedelta(days=365 * random.randint(1, 4))).strftime("%m/%d/%Y"),
        })

    elif doc_type == "ub-04":
        adm_date = dos - timedelta(days=random.randint(1, 5))
        rev_codes = [
            {"code": "0110", "description": "Room & Board – Medical/Surgical", "hcpcs": "", "units": 3, "charge": round(random.uniform(1500, 4000), 2), "non_covered": 0.00},
            {"code": "0250", "description": "Pharmacy", "hcpcs": "", "units": 1, "charge": round(random.uniform(100, 600), 2), "non_covered": 0.00},
            {"code": "0300", "description": "Laboratory", "hcpcs": "80053", "units": 1, "charge": round(random.uniform(200, 800), 2), "non_covered": 0.00},
            {"code": "0450", "description": "Emergency Room", "hcpcs": "99284", "units": 1, "charge": round(random.uniform(800, 2500), 2), "non_covered": 0.00},
            {"code": "0710", "description": "Recovery Room", "hcpcs": "", "units": 1, "charge": round(random.uniform(300, 900), 2), "non_covered": 0.00},
        ]
        ub_total = round(sum(r["charge"] for r in rev_codes), 2)
        attending_parts = physician["physician_name"].replace("Dr. ", "").split()
        assigned_benefits = random.random() < 0.9
        base.update({
            "provider_name": physician["hospital"],
            "provider_address": _address(),
            "provider_npi": _npi(),
            # FL1 prints provider name/address/TELEPHONE - the phone was never
            # supplied for ub-04 (only cms-1500 had it), so that line rendered
            # blank on every UB-04.
            "billing_provider_phone": physician["phone"],
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
            "attending_physician_qualifier": "G2",
            "attending_last_name": attending_parts[-1] if attending_parts else "",
            "attending_first_name": attending_parts[0] if attending_parts else "",
            "operating_physician_name": physician["physician_name"],
            "treatment_authorization": "AUTH" + "".join(random.choices(string.digits, k=8)),
            # Remaining CMS-1450 boxes (FL2, FL5, FL29, FL50-65, FL70-71, FL80-81) -
            # a real UB-04 fills every one of these; leaving them out of the data
            # is what made the earlier plain-grid template look sparse next to a
            # genuine specimen.
            "pay_to_name": physician["hospital"],
            "pay_to_address": _address(),
            "federal_tax_id": "".join(random.choices(string.digits, k=9)),
            "acdt_state": random.choice(_STATES),
            "health_plan_id": "".join(random.choices(string.digits, k=9)),
            "assignment_of_benefits": "Y" if assigned_benefits else "N",
            "est_amount_due": round(ub_total * (0.15 if assigned_benefits else 1.0), 2),
            "insured_relationship_code": "18",
            "group_name": physician["hospital"] + " Group Health Plan",
            "insurance_group_no": "".join(random.choices(string.digits, k=4)),
            "document_control_number": "".join(random.choices(string.digits, k=6)),
            "employer_name": _fake.company(),
            "patient_reason_dx": icd_codes[0][0] if icd_codes else "",
            "pps_code": "",
            "remarks": "",
            "condition_code": random.choice(["", "", "A0"]),
            "creation_date": date.today().strftime("%m/%d/%y"),
        })

    return base
