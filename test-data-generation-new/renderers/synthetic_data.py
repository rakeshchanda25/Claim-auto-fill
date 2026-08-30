import random
import string
from datetime import date, timedelta
from faker import Faker

from renderers.components import get_components

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


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
         "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
         "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _int_to_words(n: int) -> str:
    """Plain English integer-to-words, Indian digit grouping (Lakh/Crore) - GST invoices
    print amounts in this grouping, not the Western thousand/million one."""
    if n == 0:
        return "Zero"

    def three_digit(x: int) -> str:
        parts = []
        if x >= 100:
            parts.append(_ONES[x // 100] + " Hundred")
            x %= 100
        if x >= 20:
            parts.append(_TENS[x // 10] + (f" {_ONES[x % 10]}" if x % 10 else ""))
        elif x > 0:
            parts.append(_ONES[x])
        return " ".join(parts)

    crore, rem = divmod(n, 10_000_000)
    lakh, rem = divmod(rem, 100_000)
    thousand, rem = divmod(rem, 1_000)
    hundreds = rem

    parts = []
    if crore:
        parts.append(three_digit(crore) + " Crore")
    if lakh:
        parts.append(three_digit(lakh) + " Lakh")
    if thousand:
        parts.append(three_digit(thousand) + " Thousand")
    if hundreds:
        parts.append(three_digit(hundreds))
    return " ".join(parts)


def _amount_in_words(amount: float, unit: str = "Rupees") -> str:
    rupees = int(amount)
    paise = round((amount - rupees) * 100)
    words = f"{unit} {_int_to_words(rupees)} Only"
    if paise:
        words = f"{unit} {_int_to_words(rupees)} and {_int_to_words(paise)} Paise Only"
    return words


def _gstin() -> str:
    """Synthetic 15-char GSTIN shape (2-digit state code + 10-char PAN-like + entity + Z +
    checksum) - plausible-looking, not a real checksum-valid number."""
    state_code = f"{random.randint(1, 37):02d}"
    pan = "".join(random.choices(string.ascii_uppercase, k=5)) + "".join(random.choices(string.digits, k=4)) + random.choice(string.ascii_uppercase)
    return f"{state_code}{pan}1Z{random.choice(string.digits + string.ascii_uppercase)}"


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


_CLINICAL_NOTE_TEXT = {
    "hospital_admission": (
        "Admitted for further evaluation and management of {diag}.",
        "Patient presented with worsening symptoms prompting admission for inpatient monitoring "
        "and treatment. Initial workup was notable for {diag}, and the decision was made to admit "
        "for further management.",
        "General: acute distress noted on admission, improving with treatment. Cardiovascular: "
        "regular rate and rhythm. Pulmonary: clear to auscultation bilaterally, no respiratory "
        "distress at time of exam.",
        "Continue inpatient monitoring, serial labs, and treatment per admitting team; reassess "
        "for discharge readiness daily.",
    ),
    "surgery": (
        "Pre-operative evaluation for scheduled surgical procedure related to {diag}.",
        "Patient scheduled for surgical intervention following workup confirming the need for "
        "operative management of {diag}. Pre-operative clearance obtained; patient tolerated the "
        "procedure well.",
        "Post-operative: incision site clean, dry, and intact without signs of infection. Vital "
        "signs stable. No acute distress.",
        "Post-operative pain management, wound care instructions, and follow-up with surgical "
        "team in 1-2 weeks.",
    ),
    "emergency_visit": (
        "Acute onset of symptoms prompting emergency department visit.",
        "Patient presented to the emergency department with acute symptom onset. Triage "
        "assessment and workup performed; findings consistent with {diag}.",
        "Vital signs reviewed on arrival; focused exam performed per presenting complaint, "
        "findings documented above under Vital Signs.",
        "Emergency department treatment administered; patient stabilized and disposition "
        "determined per ED protocol.",
    ),
    "outpatient_procedure": (
        "Scheduled outpatient procedure related to {diag}.",
        "Patient presented for a scheduled outpatient procedure following prior workup. Procedure "
        "was performed without complication and patient was monitored per facility protocol prior "
        "to discharge same day.",
        "Procedure site examined post-procedure, no acute abnormality noted. Patient alert, vital "
        "signs within normal limits.",
        "Same-day discharge with standard post-procedure instructions; follow-up as scheduled.",
    ),
    "rear_end_collision": (
        "Neck and back pain following motor vehicle collision (rear-end impact).",
        "Patient reports being the restrained driver of a vehicle struck from behind by another "
        "vehicle. Since the collision, patient has experienced neck stiffness and low back pain, "
        "worsening over the following 24-48 hours, consistent with a whiplash-type mechanism.",
        "Musculoskeletal: tenderness to palpation over cervical/lumbar paraspinal musculature, "
        "decreased range of motion secondary to pain. No focal neurological deficit on exam.",
        "Conservative management with analgesics, activity modification, and physical therapy "
        "referral; follow-up in 1-2 weeks to reassess.",
    ),
    "intersection_accident": (
        "Pain following motor vehicle collision (intersection impact).",
        "Patient reports involvement in a motor vehicle collision at an intersection, struck by "
        "another vehicle. Patient denies loss of consciousness; reports pain onset shortly after "
        "the collision.",
        "Musculoskeletal: tenderness to palpation over cervical/lumbar paraspinal musculature, "
        "decreased range of motion secondary to pain. No focal neurological deficit on exam.",
        "Conservative management with analgesics, activity modification, and physical therapy "
        "referral; follow-up in 1-2 weeks to reassess.",
    ),
    "hit_and_run": (
        "Injuries following motor vehicle collision; striking vehicle fled the scene.",
        "Patient reports being struck by another vehicle whose driver fled the scene prior to law "
        "enforcement arrival. Patient was evaluated on scene and referred for further care.",
        "Musculoskeletal: tenderness to palpation over cervical/lumbar paraspinal musculature, "
        "decreased range of motion secondary to pain. No focal neurological deficit on exam.",
        "Conservative management with analgesics, activity modification, and physical therapy "
        "referral; follow-up in 1-2 weeks to reassess.",
    ),
    "slip_and_fall": (
        "Pain following a fall on a hazardous walking surface.",
        "Patient reports slipping and falling on a hazardous walking surface, sustaining injury on "
        "impact. Patient was evaluated for the resulting injury.",
        "Musculoskeletal: tenderness and swelling at the site of injury, decreased range of "
        "motion. Skin intact, no open wound noted.",
        "Immobilization/bracing as indicated, analgesics, and follow-up with orthopedics as "
        "needed.",
    ),
    "medical_malpractice": (
        "Follow-up evaluation related to complications from prior treatment.",
        "Patient presents for evaluation of complications arising from prior medical treatment. "
        "Clinical course and findings are being documented for care coordination and case review.",
        "Exam focused on the affected system per the complication under evaluation; findings "
        "documented above.",
        "Coordinate care with treating specialists; document findings for ongoing case review and "
        "further management.",
    ),
    "product_liability": (
        "Injury sustained while using a consumer product.",
        "Patient reports sustaining injury while using a product in its intended manner, when the "
        "product reportedly failed or malfunctioned. Patient was evaluated and treated for the "
        "resulting injury.",
        "Exam findings consistent with the reported injury mechanism; site of injury examined and "
        "documented.",
        "Wound/injury care as indicated, pain management, and follow-up to monitor healing.",
    ),
    "chronic_medication": (
        "Routine follow-up for chronic condition management ({diag}).",
        "Patient presents for a scheduled follow-up visit to manage an ongoing chronic condition. "
        "Medication regimen reviewed; patient reports overall stability with current treatment "
        "plan.",
        "General: well-appearing, no acute distress. Exam findings consistent with stable chronic "
        "condition management.",
        "Continue current medication regimen with routine monitoring; refill prescriptions as "
        "needed and schedule next follow-up.",
    ),
    "specialty_drug": (
        "Follow-up for specialty medication therapy.",
        "Patient presents for follow-up while on specialty biologic therapy. Response to treatment "
        "and any adverse effects reviewed.",
        "General: no acute distress. Injection/infusion site (if applicable) examined, no signs of "
        "local reaction.",
        "Continue specialty therapy per protocol; monitor response and coordinate with specialty "
        "pharmacy for continued authorization/dispensing.",
    ),
    "compounded_medication": (
        "Follow-up regarding compounded medication therapy.",
        "Patient presents for follow-up on a compounded medication formulation, prescribed due to "
        "a need not met by commercially available products. Tolerability and effectiveness "
        "reviewed.",
        "General: no acute distress; no adverse reaction to compounded formulation noted on exam.",
        "Continue compounded medication as prescribed; reassess at next visit and adjust "
        "formulation if needed.",
    ),
}


def _clinical_note_fields(scenario: str = "general", icd_codes=None) -> dict:
    """Chief complaint / HPI / vitals / exam / assessment / plan - the encounter-note fields
    shared by medical-record and medical-bill (the latter is a "superbill", the common
    real-world combined clinical-note-plus-itemized-charges document).

    chief_complaint/hpi/physical_exam/plan used to be pure Faker Lorem-Ipsum-style text
    regardless of scenario - _CLINICAL_NOTE_TEXT covers all 13 scenario names this doc-type
    family can be called with (see PACKET_REGISTRY - it's reused by every packet), same
    coverage as _medical_scenario_facts(). An unrecognised scenario (e.g. "general") falls
    back to generic-but-real prose rather than Faker gibberish."""
    diag = icd_codes[0][1] if icd_codes else "the presenting condition"
    entry = _CLINICAL_NOTE_TEXT.get(scenario)
    if entry:
        chief_complaint, hpi, physical_exam, plan = entry
        chief_complaint = chief_complaint.format(diag=diag)
        hpi = hpi.format(diag=diag)
    else:
        chief_complaint = "Patient presents for evaluation."
        hpi = f"Patient reports symptom onset prompting today's visit, consistent with {diag}. History reviewed and documented."
        physical_exam = ("General exam performed; findings documented above under Vital Signs, "
                          "with no acute abnormality noted otherwise.")
        plan = "Continue monitoring, treat symptomatically, and follow up as needed."
    return {
        "chief_complaint": chief_complaint,
        "hpi": hpi,
        "vitals": {
            "bp": f"{random.randint(100,140)}/{random.randint(60,90)}",
            "hr": str(random.randint(60, 100)),
            "temp": f"{round(random.uniform(97.5, 99.5), 1)}°F",
            "rr": str(random.randint(14, 20)),
            "spo2": f"{random.randint(95, 100)}%",
            "weight": f"{random.randint(120, 280)} lbs",
            "height": f"{random.randint(60, 74)} in",
        },
        "physical_exam": physical_exam,
        "assessment": diag,
        "plan": plan,
    }


# --- scenario-driven structural facts ---------------------------------
# Several doc types register 3-4 scenarios that used to render through the
# exact same template with only cosmetic value differences (a fire, a flood,
# and a theft all produced the identical "Loss Information" box, just with a
# different `cause_of_loss` string) - the scenario name never changed the
# document's STRUCTURE. Each function below returns (section_title, facts)
# for one doc-type family; the template renders whatever it gets back
# generically (one heading + a label/value loop), so it never needs to know
# the scenario names or grow a new {% if %} branch. Adding a scenario to an
# EXISTING family, or a whole new family, is a Python-only change - add one
# branch here, nothing in the .html ever changes. An unrecognised scenario
# (e.g. "general") returns ("", []), which the template's own {% if
# scenario_facts %} guard turns into "section omitted", not a blank box.

def _property_scenario_facts(scenario: str) -> tuple[str, list[dict]]:
    if scenario == "fire_damage":
        return "Fire Details", [
            {"label": "Fire Department Notified", "value": random.choice(["Yes", "Yes", "No"])},
            {"label": "Responding Fire Department", "value": _fake.city() + " Fire Department"},
            {"label": "Fire Report Number", "value": "FD" + "".join(random.choices(string.digits, k=6))},
            {"label": "Suspected Cause of Ignition", "value": random.choice(
                ["Electrical fault", "Unattended cooking", "Lightning strike", "Undetermined"])},
        ]
    if scenario == "water_damage":
        return "Water Details", [
            {"label": "Water Source", "value": random.choice(
                ["Burst supply pipe", "Roof leak during storm", "Water heater failure", "Sump pump failure"])},
            {"label": "Water Mitigation Company", "value": _fake.company() + " Restoration"},
            {"label": "Moisture Reading at Inspection", "value": f"{random.randint(18, 60)}%"},
            {"label": "Mold Remediation Required", "value": random.choice(["Yes", "No", "No"])},
        ]
    if scenario == "theft":
        return "Theft Details", [
            {"label": "Police Report Number", "value": "RPT" + "".join(random.choices(string.digits, k=8))},
            {"label": "Evidence of Forced Entry", "value": random.choice(["Yes", "No"])},
            {"label": "Items Reported Stolen", "value": ", ".join(random.sample(
                ["television", "laptop computer", "jewelry", "power tools", "bicycle",
                 "camera equipment", "gaming console", "firearms (registered)"], k=random.randint(2, 3)
            ))},
            {"label": "Estimated Recovery", "value": random.choice(["None to date", "Partial recovery", "Fully recovered"])},
        ]
    if scenario == "wind_damage":
        return "Storm Details", [
            {"label": "Storm / Event Name", "value": random.choice(["", "", "Winter Storm " + _fake.first_name()])},
            {"label": "Peak Wind Gust", "value": f"{random.randint(45, 110)} mph"},
            {"label": "National Weather Service Advisory #", "value": "NWS-" + "".join(random.choices(string.digits, k=5))},
            {"label": "Tree/Debris Damage", "value": random.choice(["Yes", "No"])},
        ]
    return "", []


def _auto_scenario_facts(scenario: str) -> tuple[str, list[dict]]:
    if scenario == "rear_end_collision":
        return "Rear-End Collision Details", [
            {"label": "Following Distance Estimated", "value": f"{random.randint(1, 3)} car length(s)"},
            {"label": "Brake Lights Observed", "value": random.choice(["Yes, functioning", "No / not observed"])},
            {"label": "Road Grade", "value": random.choice(["Level", "Downhill approach", "Uphill approach"])},
        ]
    if scenario == "intersection_accident":
        return "Intersection Details", [
            {"label": "Traffic Control Device", "value": random.choice(["Traffic signal", "Stop sign", "Yield sign", "Uncontrolled"])},
            {"label": "Right-of-Way Violation Alleged", "value": random.choice(["Yes", "Disputed"])},
            {"label": "Turning Movement Involved", "value": random.choice(["Left turn", "Right turn", "None - through traffic"])},
        ]
    if scenario == "hit_and_run":
        return "Hit and Run Details", [
            {"label": "Fleeing Vehicle Description", "value": random.choice([
                "Dark sedan, partial plate only", "Pickup truck, no plate observed", "SUV, color unconfirmed"])},
            {"label": "Direction of Travel", "value": random.choice(["Northbound", "Southbound", "Eastbound", "Westbound"])},
            {"label": "BOLO Issued", "value": random.choice(["Yes", "No"])},
        ]
    return "", []


def _medical_scenario_facts(scenario: str) -> tuple[str, list[dict]]:
    # Shared across every medical-family doc type (medical-record, medical-bill,
    # discharge-summary, cms-1500, ub-04). These doc types get reused across every
    # packet (see PACKET_REGISTRY) so this covers all 13 non-property scenario
    # names they can actually be called with, not just the 4 "medical" ones -
    # a chart note for a slip-and-fall ER visit should read differently from
    # one for a chronic-medication refill visit.
    if scenario == "hospital_admission":
        return "Admission Details", [
            {"label": "Admission Type", "value": random.choice(["Emergency", "Elective", "Urgent"])},
            {"label": "Length of Stay", "value": f"{random.randint(1, 6)} day(s)"},
            {"label": "Attending Service", "value": random.choice(["Internal Medicine", "Hospitalist", "General Surgery"])},
        ]
    if scenario == "surgery":
        return "Surgical Details", [
            {"label": "Anesthesia Type", "value": random.choice(["General", "Regional", "MAC/Sedation"])},
            {"label": "OR Time", "value": f"{random.randint(45, 210)} minutes"},
            {"label": "ASA Class", "value": random.choice(["I", "II", "III"])},
        ]
    if scenario == "emergency_visit":
        return "Emergency Visit Details", [
            {"label": "Triage Level (ESI)", "value": str(random.randint(2, 4))},
            {"label": "Arrival Mode", "value": random.choice(["Ambulance", "Walk-in", "Private Vehicle"])},
            {"label": "ED Disposition", "value": random.choice(["Discharged home", "Admitted", "Transferred"])},
        ]
    if scenario == "outpatient_procedure":
        return "Outpatient Procedure Details", [
            {"label": "Facility Type", "value": random.choice(["Ambulatory Surgery Center", "Hospital Outpatient Department"])},
            {"label": "Same-Day Discharge", "value": "Yes"},
            {"label": "Pre-Procedure Clearance", "value": random.choice(["Not required", "PCP clearance obtained"])},
        ]
    if scenario == "rear_end_collision":
        return "Mechanism of Injury", [
            {"label": "Mechanism", "value": "Motor vehicle collision - rear-end impact"},
            {"label": "Restraint Use", "value": random.choice(["Seatbelt worn", "Seatbelt worn, shoulder only"])},
            {"label": "Reported Symptoms", "value": random.choice(["Neck pain/stiffness", "Low back pain", "Headache"])},
        ]
    if scenario == "intersection_accident":
        return "Mechanism of Injury", [
            {"label": "Mechanism", "value": random.choice(["Motor vehicle collision - T-bone/angle impact", "Motor vehicle collision - head-on impact"])},
            {"label": "Loss of Consciousness", "value": random.choice(["Denied", "Brief, <1 minute"])},
            {"label": "Restraint Use", "value": random.choice(["Seatbelt worn", "Unrestrained"])},
        ]
    if scenario == "hit_and_run":
        return "Mechanism of Injury", [
            {"label": "Mechanism", "value": "Motor vehicle collision - striking vehicle fled scene"},
            {"label": "Reported to Law Enforcement", "value": "Yes"},
            {"label": "Restraint Use", "value": random.choice(["Seatbelt worn", "Unrestrained"])},
        ]
    if scenario == "slip_and_fall":
        return "Mechanism of Injury", [
            {"label": "Mechanism", "value": random.choice(["Fall on wet/slippery surface", "Fall on uneven walking surface", "Fall down stairs"])},
            {"label": "Ambulatory Status Post-Fall", "value": random.choice(["Ambulatory with assistance", "Unable to bear weight"])},
            {"label": "Pre-existing Condition Aggravated", "value": random.choice(["None reported", "Prior joint condition"])},
        ]
    if scenario == "medical_malpractice":
        return "Related Treatment History", [
            {"label": "Alleged Deviation from Standard of Care", "value": random.choice(["Delayed diagnosis", "Surgical complication", "Medication error"])},
            {"label": "Prior Treating Facility", "value": _fake.company() + " Medical Center"},
            {"label": "Second Opinion Obtained", "value": random.choice(["Yes", "No"])},
        ]
    if scenario == "product_liability":
        return "Product-Related Injury Details", [
            {"label": "Product Involved", "value": random.choice(["Household appliance", "Power tool", "Consumer electronics device", "Furniture"])},
            {"label": "Injury Mechanism", "value": random.choice(["Thermal/burn injury", "Laceration", "Impact/crush injury"])},
            {"label": "Product Retained as Evidence", "value": random.choice(["Yes", "No"])},
        ]
    if scenario == "chronic_medication":
        return "Chronic Condition Management", [
            {"label": "Condition Being Managed", "value": random.choice(["Hypertension", "Type 2 Diabetes", "Hyperlipidemia"])},
            {"label": "Medication Adherence", "value": random.choice(["Compliant", "Occasionally misses doses"])},
            {"label": "Refill Frequency", "value": random.choice(["30-day supply", "90-day supply"])},
        ]
    if scenario == "specialty_drug":
        return "Specialty Drug Therapy Details", [
            {"label": "Prior Authorization Status", "value": random.choice(["Approved", "Pending renewal"])},
            {"label": "Dispensing Pharmacy", "value": "Specialty pharmacy (limited distribution)"},
            {"label": "Response Monitoring", "value": random.choice(["Lab monitoring per protocol", "Clinical response assessed at follow-up"])},
        ]
    if scenario == "compounded_medication":
        return "Compounded Medication Details", [
            {"label": "Reason for Compounding", "value": random.choice(["Dosage strength unavailable commercially", "Allergy to standard inactive ingredient", "Alternate delivery form required"])},
            {"label": "Compounding Pharmacy", "value": _fake.company() + " Compounding Pharmacy"},
            {"label": "Formulation", "value": random.choice(["Topical cream", "Oral suspension", "Capsule"])},
        ]
    return "", []


def _vehicle_damage_descriptions(scenario) -> tuple[str, str]:
    """(state vehicle's damage, other vehicle's damage) - was two independent
    _fake.sentence() calls, so a rear_end_collision report could just as
    easily describe front-end damage on the state vehicle as rear-end."""
    if scenario == "rear_end_collision":
        return (
            random.choice(["Rear bumper and trunk crumpled from impact.", "Rear-end damage to bumper and taillight assembly."]),
            random.choice(["Front bumper and hood damage consistent with striking vehicle ahead.", "Front-end damage, radiator support bent."]),
        )
    if scenario == "intersection_accident":
        return (
            random.choice(["Driver-side door and quarter panel damage from T-bone impact.", "Front-end damage from intersection collision."]),
            random.choice(["Front-end damage from intersection collision.", "Passenger-side damage from impact within intersection."]),
        )
    if scenario == "hit_and_run":
        return (
            random.choice(["Side panel scraped and dented; paint transfer observed.", "Rear quarter panel damage with paint transfer from fleeing vehicle."]),
            "Not inspected - fleeing vehicle not recovered at time of report.",
        )
    return (
        random.choice(["Minor body damage, cosmetic only.", "Moderate damage to exterior panel."]),
        random.choice(["Minor body damage, cosmetic only.", "Moderate damage to exterior panel."]),
    )


def _litigation_narrative(scenario, plaintiff_name, defendant_name, incident_date):
    """(facts paragraph, [3 general-allegation paragraphs]) - was pure Faker
    Lorem-Ipsum-style prose regardless of scenario, so a product_liability
    complaint read no differently from a slip_and_fall one even though
    causes_of_action was already anchored to the scenario. This makes the
    prose actually recount the anchored cause."""
    if scenario == "slip_and_fall":
        facts = (
            f"On or about {incident_date}, Plaintiff {plaintiff_name} was lawfully present on premises "
            f"owned, operated, and/or maintained by Defendant {defendant_name} when Plaintiff slipped and "
            f"fell due to a hazardous condition on the walking surface that Defendant knew or should have "
            f"known about and failed to remedy or warn against. As a direct and proximate result, "
            f"Plaintiff sustained bodily injury requiring ongoing medical treatment."
        )
        allegations = [
            "Defendant owed a duty to Plaintiff, a lawful invitee on the premises, to maintain the "
            "property in a reasonably safe condition and to warn of known hazards.",
            "Defendant breached that duty by allowing a hazardous condition on the walking surface to "
            "exist and persist without adequate warning, inspection, or remediation.",
            "As a direct and proximate result of Defendant's breach, Plaintiff fell and sustained "
            "injuries, incurring medical expenses, lost wages, and pain and suffering.",
        ]
    elif scenario == "medical_malpractice":
        facts = (
            f"On or about {incident_date}, Plaintiff {plaintiff_name} received medical treatment from "
            f"Defendant {defendant_name}. Defendant's treatment fell below the applicable standard of "
            f"care ordinarily exercised by practitioners in the same field under similar circumstances, "
            f"proximately causing Plaintiff to suffer injury that competent care would have avoided."
        )
        allegations = [
            "Defendant owed Plaintiff a duty to provide medical care consistent with the applicable "
            "standard of care for a practitioner of the same specialty.",
            "Defendant breached that duty by deviating from the applicable standard of care in the "
            "diagnosis, treatment, and/or management of Plaintiff's condition.",
            "As a direct and proximate result of Defendant's breach, Plaintiff suffered injury, "
            "additional medical expenses, and other damages that competent care would have avoided.",
        ]
    elif scenario == "product_liability":
        facts = (
            f"On or about {incident_date}, Plaintiff {plaintiff_name} was using a product designed, "
            f"manufactured, and/or sold by Defendant {defendant_name} in a manner reasonably foreseeable "
            f"to Defendant when the product failed and/or malfunctioned due to a defect in its design "
            f"and/or manufacture, proximately causing Plaintiff to suffer bodily injury."
        )
        allegations = [
            "Defendant designed, manufactured, and/or sold the product at issue and placed it into "
            "the stream of commerce in a defective and unreasonably dangerous condition.",
            "The product's defect existed at the time it left Defendant's control and was not "
            "substantially altered before it reached Plaintiff.",
            "As a direct and proximate result of the product's defect, Plaintiff sustained bodily "
            "injury, medical expenses, and other damages while using the product as intended.",
        ]
    else:
        facts = (
            f"On or about {incident_date}, Plaintiff {plaintiff_name} was injured due to the negligent "
            f"conduct of Defendant {defendant_name}, giving rise to the causes of action set forth below."
        )
        allegations = [
            "Defendant owed Plaintiff a duty of reasonable care under the circumstances.",
            "Defendant breached that duty through the negligent conduct described above.",
            "As a direct and proximate result of Defendant's breach, Plaintiff sustained damages.",
        ]
    return facts, allegations


def _discharge_narrative(scenario: str, diag: str) -> dict:
    """summary_of_care_plan/goals_achieved_summary/care_plan_notes/assessment_notes/
    discharge_instructions for discharge-summary. Before this, synthetic_data.py never set
    summary_of_care_plan or goals_achieved_summary at all - discharge_summary.html's own
    Jinja `| default(...)` fallback then printed the SAME hardcoded pregnancy/antepartum
    boilerplate on every single discharge summary regardless of scenario ("Antepartum
    assessment with vital signs..."), which is the single worst instance of the static-
    content bug: not even scenario-blind Faker filler, just literally identical text. This
    doc type is only ever called with the 4 medical scenarios (see PACKET_REGISTRY)."""
    entries = {
        "hospital_admission": (
            f"Skilled nursing visits initiated following inpatient hospital admission for "
            f"{diag}. Patient monitored for stability, medication management reviewed, and "
            f"caregiver educated on post-admission care needs.",
            "Patient demonstrates improved stability since admission; caregiver verbalizes "
            "understanding of the post-admission care plan and follow-up requirements.",
            ["Vital signs stable across visits.", "Medication compliance reviewed and reinforced."],
            ["No new acute findings since last visit.", "Patient tolerating current care plan well."],
            f"Continue prescribed home care regimen for {diag}. Attend all scheduled follow-up "
            f"appointments, monitor for any worsening symptoms, and contact physician with any "
            f"new or worsening concerns.",
        ),
        "surgery": (
            f"Skilled nursing visits initiated following surgical procedure for {diag}. Wound/"
            f"incision care provided, pain management reviewed, and patient monitored for "
            f"post-operative complications.",
            "Incision healing well with no signs of infection; patient and caregiver verbalize "
            "understanding of post-operative care instructions.",
            ["Incision site clean, dry, and intact at each visit.", "Pain adequately managed with current regimen."],
            ["No signs of surgical site infection observed.", "Mobility improving per post-op plan."],
            "Continue post-operative wound care as instructed, take pain medication as directed, "
            "avoid strenuous activity per surgeon's restrictions, and attend the post-operative "
            "follow-up appointment.",
        ),
        "emergency_visit": (
            f"Skilled nursing visits initiated following an emergency department visit for "
            f"{diag}. Patient monitored for symptom resolution and medication compliance "
            f"reviewed.",
            "Patient's condition has stabilized since the emergency visit; caregiver verbalizes "
            "understanding of the follow-up care plan.",
            ["Symptoms trending toward resolution.", "No return ED visits since discharge."],
            ["Vital signs within expected range at each visit.", "Medication regimen tolerated well."],
            "Monitor for recurrence of presenting symptoms, take medications as prescribed, "
            "follow up with primary care provider, and return to the emergency department if "
            "symptoms worsen.",
        ),
        "outpatient_procedure": (
            f"Skilled nursing visits initiated following an outpatient procedure for {diag}. "
            f"Procedure site monitored and patient educated on post-procedure care.",
            "Procedure site healing appropriately; patient verbalizes understanding of "
            "post-procedure instructions and follow-up schedule.",
            ["Procedure site without signs of complication.", "Patient ambulating without difficulty."],
            ["No adverse reaction to procedure noted.", "Patient adherent to post-procedure precautions."],
            "Follow post-procedure care instructions provided at discharge, keep the procedure "
            "site clean and dry as directed, and attend the scheduled follow-up visit.",
        ),
    }
    entry = entries.get(scenario)
    if not entry:
        return {}
    care_plan, goals, care_notes, assess_notes, instructions = entry
    return {
        "summary_of_care_plan": care_plan,
        "goals_achieved_summary": goals,
        "care_plan_notes": care_notes,
        "assessment_notes": assess_notes,
        "discharge_instructions": instructions,
    }


def _facts_line(facts: list[dict]) -> str:
    # CMS-1500 and UB-04 are standardized federal forms with a fixed box
    # layout - unlike the other templates, they can't grow a new section for
    # scenario_facts without breaking that real-world layout. Their existing
    # free-text boxes (19. Additional Claim Information / UB-04 Remarks) are
    # the form-correct place for this, so collapse facts to one line instead.
    return "; ".join(f"{f['label']}: {f['value']}" for f in facts)


def _witness_statement(scenario, hit_and_run_flag, party2):
    if hit_and_run_flag:
        return random.choice([
            "I saw the other car hit them and just take off, didn't even slow down.",
            "The vehicle that caused it sped away right after impact, I got a partial plate but that's it.",
        ])
    if scenario == "rear_end_collision":
        return "I saw the car behind just plow right into the back of the other one, they never braked."
    if scenario == "intersection_accident":
        return "One of them ran the light/sign and they collided right in the middle of the intersection."
    return f"I heard the impact and saw both vehicles come to a stop; {party2['name']}'s car looked like it took the worse damage."


def _police_narrative(scenario, incident_date, location, weather, road_cond, speed_limit, party1, party2,
                       collision_type, primary_factor, hit_and_run_flag, property_facts):
    """3 narrative paragraphs + a 1-line summary. Faker filler here used to be
    the same random Lorem-Ipsum-style sentences regardless of scenario - a
    hit_and_run report read no differently from a rear-end one. This builds
    the actual account from the fields already generated for this report
    (parties, collision_type, primary_factor, weather/road conditions), so
    the story it tells is the one collision_type/primary_factor/hit_and_run
    already claim happened, not a disconnected paragraph of prose next to
    them. property_facts (from _property_scenario_facts) does the same job
    when this doc type is serving as the property-packet's Incident Report."""
    # Two openers exist per shape so the report doesn't read identically every time -
    # each is worded correctly for its own shape from the start (a post-hoc .replace()
    # on a collision-worded opener only matches the ONE of the two sentences that
    # contains that exact substring, silently leaving the other's "traffic collision"
    # wording in a fire/water/theft/wind report - the bug this replaced).
    if property_facts:
        p1_open = random.choice([
            f"On {incident_date}, officers were dispatched to {location} in reference to a property damage incident.",
            f"Officers responded to a reported property damage incident at {location} on {incident_date}.",
        ])
    else:
        p1_open = random.choice([
            f"On {incident_date}, officers were dispatched to {location} in reference to a motor vehicle collision.",
            f"Officers responded to a reported traffic collision at {location} on {incident_date}.",
        ])
    # hit_and_run_flag is checked FIRST, before the scenario branches - it is only
    # ~85% likely even for scenario == "hit_and_run" (see the police-report branch
    # above), so branching on the scenario string alone would have this paragraph
    # claim a fleeing vehicle even on the ~15% of "hit_and_run"-scenario reports
    # where the flag actually landed False (and vice versa: any other scenario's
    # 5% base rate can still produce a real hit-and-run that needs this account,
    # not the generic fallback). Matches the same fix applied to collision_type/
    # primary_factor above - both are keyed off the actual outcome, not the
    # requested scenario name. `and not property_facts` matters too: that same 5%
    # base rate can land True for a fire/water/theft/wind report, which has no
    # Driver 1/Driver 2 vehicles at all - without this guard the narrative would
    # tell a two-vehicle hit-and-run story directly contradicting the property-
    # incident fields the rest of the document actually renders.
    if hit_and_run_flag and not property_facts:
        p1 = p1_open + (
            f" The {party1['vehicle_year']} {party1['vehicle_make']} {party1['vehicle_model']} (Driver 1, "
            f"{party1['name']}) was struck by a second vehicle, subsequently identified as the "
            f"{party2['vehicle_year']} {party2['vehicle_make']} {party2['vehicle_model']} registered to "
            f"{party2['registered_owner']}, whose operator fled the scene prior to officer arrival without "
            f"exchanging information."
        )
        p2 = (
            f"A witness canvass and vehicle registration check subsequently identified the fleeing vehicle "
            f"and its registered owner, {party2['name']}, who was later located and identified as Driver 2 "
            f"for purposes of this report. Primary contributing factor: {primary_factor.lower()}."
        )
    elif scenario == "rear_end_collision":
        p1 = p1_open + (
            f" Preliminary investigation determined that {party2['vehicle_year']} {party2['vehicle_make']} "
            f"{party2['vehicle_model']} (Driver 2, {party2['name']}) struck the rear of the "
            f"{party1['vehicle_year']} {party1['vehicle_make']} {party1['vehicle_model']} (Driver 1, "
            f"{party1['name']}) while Vehicle 1 was stopped or slowing for traffic ahead. "
            f"Posted speed limit in the area is {speed_limit} MPH; road conditions were reported as "
            f"{road_cond.lower()} under {weather.lower()} weather."
        )
        p2 = (
            f"Driver 2 stated they did not have adequate time to stop and struck Vehicle 1's rear bumper. "
            f"The primary contributing factor was determined to be {primary_factor.lower()}. Damage to "
            f"Vehicle 1 was concentrated to the rear; damage to Vehicle 2 was concentrated to the front end."
        )
    elif scenario == "intersection_accident":
        p1 = p1_open + (
            f" Investigation determined the collision occurred within the intersection between the "
            f"{party1['vehicle_year']} {party1['vehicle_make']} {party1['vehicle_model']} (Driver 1, "
            f"{party1['name']}) and the {party2['vehicle_year']} {party2['vehicle_make']} "
            f"{party2['vehicle_model']} (Driver 2, {party2['name']}), producing a {collision_type.lower()} "
            f"impact pattern. Road conditions were reported as {road_cond.lower()} under {weather.lower()} "
            f"weather, posted speed limit {speed_limit} MPH."
        )
        p2 = (
            f"Investigation determined the primary contributing factor to be {primary_factor.lower()} on "
            f"the part of Driver 2. Both vehicles sustained damage consistent with an intersection impact; "
            f"see Section 4/5 for vehicle-specific damage detail."
        )
    elif property_facts:
        fact_str = "; ".join(f"{f['label'].lower()}: {f['value']}" for f in property_facts if f["value"])
        p1 = p1_open + (
            f" Reporting party {party1['name']} advised responding officers of the extent of the damage "
            f"on scene. {fact_str}."
        )
        p2 = (
            f"Officers documented the scene and coordinated with the responding agencies noted above. "
            f"Weather at the time was {weather.lower()}; the property was secured pending insurance "
            f"adjuster inspection."
        )
    else:
        p1 = p1_open + (
            f" Driver 1, {party1['name']}, and Driver 2, {party2['name']}, were both present on scene. "
            f"Collision type was recorded as {collision_type}; primary contributing factor: "
            f"{primary_factor.lower()}."
        )
        p2 = "Both vehicles were documented and photographed on scene; see Section 4/5 for damage detail."

    p3 = (
        ("The reporting party and available witnesses were interviewed on scene and statements were "
         "obtained (see Section 6). " if property_facts else
         "Both parties were interviewed on scene and statements were obtained (see Section 6). ")
        + ("Driver 2 was cited for a traffic code violation; a citation was issued and a court date "
           "assigned (see Section 7). " if (not property_facts and party2["citation_number"] != "None") else "")
        + "This report was completed and forwarded for records processing per department policy."
    )
    paragraphs = [p1, p2, p3]
    summary = (
        f"{'Two-vehicle ' + collision_type.lower() + ' collision' if not property_facts else scenario.replace('_', ' ')} "
        f"at {location}"
        + ("; hit and run, driver of Vehicle 2 fled the scene prior to officer arrival." if hit_and_run_flag and not property_facts
           else f"; primary factor {primary_factor.lower()}." if not property_facts else ".")
    )
    return paragraphs, summary


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
# empty document. Add one line here when adding a variant template file
# (renderers/templates/<name>.html) that is NOT also registered in
# app.py's /api/ai-doc-types - an alias with no matching .html file makes
# generate_synthetic_data succeed while render_document_to_pdf 404s, which
# is exactly what happened to acord-new/police-report-new/litigation-
# document-new/ub-04-new once those variant files were merged into their
# base templates and deleted; the (now empty) aliases below are that
# lesson, not speculative infrastructure - keep this dict, but only ever
# populate it alongside a real template file on disk.
_DOC_TYPE_ALIASES: dict[str, str] = {}


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
        # which named Jinja component macros this document assembles, and in what order -
        # see renderers/components.py. Set once here for every doc type; a doc-type branch
        # below may still add scenario-specific DATA a component needs (e.g. police-report's
        # property_incident component), but the composition list itself always comes from
        # the registry, not ad-hoc per-branch logic.
        "components": get_components(doc_type, scenario),
    }

    if doc_type == "medical-record":
        # medical-record is reused across every packet (medical/auto-accident/
        # litigation/pharmacy) - see PACKET_REGISTRY - so it can be called with
        # any of 13 different scenario names, not just the 4 "medical" ones.
        facts_title, facts = _medical_scenario_facts(scenario)
        base.update(_clinical_note_fields(scenario, icd_codes))
        base.update({
            "encounter_type": random.choice(["Office Visit", "Emergency Visit", "Follow-Up", "Consultation"]),
            "allergies": random.choice(["NKDA (No Known Drug Allergies)", "Penicillin", "Sulfa drugs", "Latex"]),
            "current_medications": [d[0] for d in random.sample(_NDC_DRUGS, 2)],
            "signed_by": physician["physician_name"],
            "signed_date": dos.strftime("%m/%d/%Y"),
            "scenario_facts_title": facts_title,
            "scenario_facts": facts,
        })

    elif doc_type == "discharge-summary":
        # Template is a home-health/skilled-nursing discharge summary (Reason for Discharge
        # checkboxes: goals achieved / admitted to acute care / ECF-SNF / transferred /
        # refused care / expired / other; visit counts; plan for transition) - a different
        # document from an inpatient hospital discharge, so this branch generates that shape
        # rather than reusing the old admission/DRG/length-of-stay fields (kept below for
        # anything that still reads them, but nothing in the template does any more).
        admission_date = dos - timedelta(days=random.randint(1, 7))
        discharge_date = dos
        first_visit_date = admission_date + timedelta(days=random.randint(0, 1))
        last_visit_date = discharge_date - timedelta(days=random.randint(0, 2))
        num_visits = random.randint(3, 14)

        reason_key = random.choices(
            ["goals_achieved", "admitted_acute_care", "admitted_ecf_snf",
             "transferred_other_service", "refused_further_care", "expired", "other"],
            weights=[55, 15, 10, 8, 5, 2, 5],
        )[0]
        reason = {k: False for k in (
            "goals_achieved", "admitted_acute_care", "admitted_ecf_snf",
            "transferred_other_service", "refused_further_care", "expired", "other",
        )}
        reason[reason_key] = True
        reason["expired_date"] = discharge_date.strftime("%m/%d/%Y") if reason_key == "expired" else ""
        reason["other_detail"] = "Patient relocated out of service area" if reason_key == "other" else ""
        facts_title, facts = _medical_scenario_facts(scenario)
        discharge_diag = icd_codes[0][1] if icd_codes else "the presenting condition"
        discharge_narrative = _discharge_narrative(scenario, discharge_diag)

        base.update({
            # legacy inpatient-hospital fields - unused by the current template, kept for
            # callers that might still reference them (validate_document_structure no longer
            # requires these)
            "attending_physician": physician["physician_name"],
            "admission_diagnosis": icd_codes[0][1] if icd_codes else "Acute illness",
            "discharge_diagnosis": icd_codes[0][1] if icd_codes else "Resolved",
            "hospital_course": (
                f"Patient's hospital course related to {discharge_diag} was reviewed prior to "
                f"transition to home health services." if discharge_narrative else _fake.paragraph(nb_sentences=5)
            ),
            "discharge_condition": random.choice(["Stable", "Improved", "Good"]),
            "follow_up": f"Follow up with {physician['physician_name']} in {random.randint(7, 21)} days",
            "medications_at_discharge": [
                {"name": d[0], "dose": "As directed", "frequency": "Daily"}
                for d in random.sample(_NDC_DRUGS, 3)
            ],
            "drg_code": str(random.randint(100, 999)),
            "length_of_stay": str((discharge_date - admission_date).days),
            # home-health discharge summary fields
            "org_name": _fake.company() + " Home Health Care",
            "document_title": "Discharge Summary",
            "patient_address": patient["address"]["street"],
            "patient_address_line2": "",
            "city_state": f"{patient['address']['city']}, {patient['address']['state']}",
            "zip_code": patient["address"]["zip"],
            "date_of_admission": admission_date.strftime("%m/%d/%Y"),
            "date_of_discharge": discharge_date.strftime("%m/%d/%Y"),
            "date_of_first_visit": first_visit_date.strftime("%m/%d/%Y"),
            "last_visit_made": last_visit_date.strftime("%m/%d/%Y"),
            "number_of_visits": str(num_visits),
            "diagnosis": icd_codes[0][1] if icd_codes else "Resolved",
            "reason": reason,
            "reason_comments": [] if reason_key == "goals_achieved" else [
                f"Discharge reason: {reason_key.replace('_', ' ')}, related to ongoing management of {discharge_diag}."
            ],
            "assessment_of_patient_condition": random.choice(["Stable", "Improved", "Guarded"]),
            "transition_plan": [
                f"Transitioning care for {discharge_diag} to the next level of service; records and "
                f"care plan forwarded to receiving provider."
            ] if reason_key not in ("goals_achieved", "expired") else [],
            "discharge_instruction_notes": [],
            "clinician_signature": physician["physician_name"],
            "signature_date": discharge_date.strftime("%m/%d/%Y"),
            "scenario_facts_title": facts_title,
            "scenario_facts": facts,
        })
        # summary_of_care_plan/goals_achieved_summary/care_plan_notes/assessment_notes/
        # discharge_instructions: only set for the 4 registered scenarios (see
        # _discharge_narrative) - anything else leaves these keys unset, so the
        # template's own `| default(...)` fallback text applies (unchanged behavior for
        # "general"/an unrecognized scenario).
        if discharge_narrative:
            base.update(discharge_narrative)
        else:
            base.setdefault("care_plan_notes", [])
            base.setdefault("assessment_notes", [])

    elif doc_type == "medical-bill":
        # Adjustment (contractual write-off) rate varies by payer/negotiated
        # rate in reality - was pinned to 15% on every bill, so "balance" was
        # always exactly 85% of the charge no matter what.
        adjustments = round(total * random.uniform(0.05, 0.30), 2)
        facts_title, facts = _medical_scenario_facts(scenario)
        base.update(_clinical_note_fields(scenario, icd_codes))
        base.update({
            "account_number": "ACC" + "".join(random.choices(string.digits, k=8)),
            "statement_date": date.today().strftime("%m/%d/%Y"),
            "due_date": (date.today() + timedelta(days=30)).strftime("%m/%d/%Y"),
            "amount_due": total,
            "amount_paid": 0.00,
            "adjustments": adjustments,
            "balance": round(total - adjustments, 2),
            "scenario_facts_title": facts_title,
            "scenario_facts": facts,
        })

    elif doc_type == "cms-1500":
        insurance_type = random.choice(
            ["Medicare", "Medicaid", "TRICARE", "CHAMPVA", "Group Health Plan", "FECA Blk Lung", "Other"]
        )
        illness_date = dos - timedelta(days=random.randint(0, 14))
        facts_title, facts = _medical_scenario_facts(scenario)
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
            "additional_claim_info": _facts_line(facts),
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
        # The template is a full multi-column claims-table EOB (Charges / Provider
        # Responsibility / Allowed / Patient Non-covered / Paid by Other Ins / Deductible /
        # Co-pay / Co-Insurance / Paid / Amount You Owe per line, with a totals row and a
        # Patient Benefit Summary tracking deductible/OOP) - a different, more detailed
        # document than the old single-ratio eob_lines model (kept below, unused by the
        # template now, for anything that still reads it). Every column is built so the
        # totals row is a literal column-wise sum of the claim lines, and each line's own
        # Charges/Allowed/Paid/Amount-You-Owe reconcile internally (see the running deductible
        # below - the standard "deductible first, then coinsurance" adjudication order).
        deductible_limit = random.choice([250.0, 500.0, 1000.0, 1500.0])
        coinsurance_rate = round(random.uniform(0.10, 0.30), 2)
        copay_amt = round(random.uniform(20, 50), 2)
        remaining_deductible = deductible_limit
        claims = []
        for i, item in enumerate(line_items):
            charges = item["charge"]
            allowed_amount = round(charges * random.uniform(0.60, 0.90), 2)
            provider_responsibility = round(charges - allowed_amount, 2)
            patient_noncovered = round(allowed_amount * 0.05, 2) if random.random() < 0.15 else 0.0
            covered_amount = round(allowed_amount - patient_noncovered, 2)

            deductible_amt = round(min(remaining_deductible, covered_amount), 2)
            remaining_deductible = round(remaining_deductible - deductible_amt, 2)
            after_deductible = round(covered_amount - deductible_amt, 2)
            copay_this_line = copay_amt if i == 0 else 0.0
            coinsurance_amt = round(max(after_deductible - copay_this_line, 0) * coinsurance_rate, 2)
            paid_amount = round(after_deductible - copay_this_line - coinsurance_amt, 2)
            amount_you_owe = round(patient_noncovered + deductible_amt + copay_this_line + coinsurance_amt, 2)

            claims.append({
                "dates_of_service": dos.strftime("%m/%d/%Y"),
                "description": f"{item['description']} (CPT {item['cpt']})",
                "charges": charges,
                "provider_responsibility": provider_responsibility,
                "allowed_amount": allowed_amount,
                "patient_noncovered": patient_noncovered,
                "paid_by_other_ins": 0.0,
                "deductible": deductible_amt,
                "copay": copay_this_line,
                "coinsurance": coinsurance_amt,
                "paid_amount": paid_amount,
                "amount_you_owe": amount_you_owe,
                "notes_id": "1" if patient_noncovered else "",
            })

        totals = {
            key: round(sum(c[key] for c in claims), 2)
            for key in ("charges", "provider_responsibility", "allowed_amount", "patient_noncovered",
                        "paid_by_other_ins", "deductible", "copay", "coinsurance", "paid_amount", "amount_you_owe")
        }
        deductible_satisfied = deductible_limit - remaining_deductible
        # eob-explanation is reused by both the litigation packet (slip_and_fall/
        # medical_malpractice/product_liability) and the pharmacy packet
        # (chronic_medication/specialty_drug/compounded_medication) - the shared
        # medical-family facts function already covers exactly those 6 names.
        facts_title, facts = _medical_scenario_facts(scenario)

        # Legacy single-ratio fields - unused by the current template, kept for callers that
        # might still reference them (validate_document_structure no longer requires these).
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
            # full claims-table EOB fields
            "document_title": "Explanation of Health Care Benefits",
            "subscriber_name": patient["patient_name"],
            "claim_ref_number": claim_num,
            "claim_ref_date": date.today().strftime("%m/%d/%Y"),
            "disclaimer_text": (
                "This is an explanation of the claim processed based on your plan benefits in "
                "effect when the service was performed. Please keep this form for your tax records."
            ),
            "patient_id": patient["insurance_id"],
            "patient_control_number": _mrn(),
            "group_name": physician["hospital"] + " Group Health Plan",
            "claims": claims,
            "totals": totals,
            "notes": [{"code": "1", "description": "Non-covered charge - see plan benefit booklet for exclusions."}],
            "benefit_patient_name": patient["patient_name"],
            "benefit_period_start": date(date.today().year, 1, 1).strftime("%m/%d/%Y"),
            "benefit_period_end": date(date.today().year, 12, 31).strftime("%m/%d/%Y"),
            "deductible_satisfied": deductible_satisfied,
            "deductible_limit": deductible_limit,
            "oop_applied": totals["amount_you_owe"],
            "oop_limit": random.choice([3000.0, 5000.0, 8000.0]),
            "benefit_summary_note": (
                "Please refer to your benefit booklet or agreement for further information. "
                "Amount(s) shown may include totals from claims which are still being processed "
                "and for which you have not been notified."
            ),
            "scenario_facts_title": facts_title,
            "scenario_facts": facts,
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
        # dispatch/arrival/cleared used to be 3 independently random times with no
        # ordering guarantee, so a report could show arrival before dispatch, or a
        # multi-hour dispatch-to-arrival gap for a routine traffic stop. Chained as
        # dispatch -> +minutes -> arrival -> +minutes -> cleared instead.
        dispatch_minutes = random.randint(6 * 60, 22 * 60)
        arrival_minutes = dispatch_minutes + random.randint(4, 25)
        cleared_minutes = arrival_minutes + random.randint(20, 90)
        dispatch_t = f"{dispatch_minutes // 60:02d}:{dispatch_minutes % 60:02d}"
        arrival_t = f"{arrival_minutes // 60:02d}:{arrival_minutes % 60:02d}"
        cleared_t = f"{cleared_minutes // 60:02d}:{cleared_minutes % 60:02d}"
        # collision_type/hit_and_run/primary_factor used to be independently
        # random regardless of which scenario was requested - a
        # "hit_and_run"-scenario report was no more likely to actually BE a
        # hit and run than any other scenario. Correlating them here is a
        # pure data change (no template touch) - see _property_scenario_facts
        # above for the same principle applied to a doc type that had no
        # scenario-varying field to correlate at all.
        hit_and_run_flag = random.random() < (0.85 if scenario == "hit_and_run" else 0.05)
        # collision_type/primary_factor MUST be branched on hit_and_run_flag first, not on
        # scenario - hit_and_run_flag can land True by its 5% base rate for ANY scenario
        # string (including one totally unrelated to police-report, e.g. a caller passing
        # "surgery"), and when that happens collision_type must still never be "Single
        # Vehicle" (a fleeing second vehicle contradicts "single vehicle" by definition).
        # Branching on scenario alone (the previous approach) only closed this hole for the
        # literal "hit_and_run" scenario name and left it open for every other one - this is
        # what produced a real report with COLLISION TYPE: Single Vehicle and HIT & RUN: Yes
        # side by side.
        if hit_and_run_flag:
            collision_type = random.choice(["Rear-end", "Sideswipe", "Angle"])
            primary_factor = random.choice(["Unsafe speed for conditions", "Driver inattention"])
        elif scenario == "rear_end_collision":
            collision_type = "Rear-end"
            primary_factor = "Following too closely"
        elif scenario == "intersection_accident":
            collision_type = random.choice(["Angle", "Head-on"])
            primary_factor = "Failure to yield right of way"
        else:
            collision_type = random.choice(["Rear-end", "Sideswipe", "Head-on", "Angle", "Single Vehicle"])
            primary_factor = random.choice([
                "Unsafe speed for conditions", "Following too closely", "Failure to yield right of way",
                "Improper turn", "Driver inattention",
            ])
        cited = True if hit_and_run_flag else random.random() < 0.6
        # police-report also serves as the "Incident Report" in the property-claim
        # packet (fire_damage/water_damage/theft/wind_damage) - reuse the same
        # facts function property-loss-notice uses. Returns ("", []) for the auto
        # scenarios above, which already have their own dedicated fields.
        facts_title, facts = _property_scenario_facts(scenario)
        _party1_damage_desc, _party2_damage_desc = _vehicle_damage_descriptions(scenario)
        if scenario == "hit_and_run":
            # In police-report (unlike auto-accident-report) the fleeing vehicle
            # IS eventually identified per the narrative's witness/registration
            # canvass, so its damage gets inspected rather than left unknown.
            _party2_damage_desc = random.choice([
                "Front-end damage consistent with striking another vehicle, later inspected upon identification.",
                "Paint transfer and front bumper damage matching the collision, documented upon vehicle recovery.",
            ])

        def _party(role: str, at_fault: bool, damage_desc: str) -> dict:
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
                "damage_description": damage_desc,
                "towed": "Yes" if severity == "Major" else "No",
                "citation_number": ("CIT" + "".join(random.choices(string.digits, k=8))) if (at_fault and cited) else "None",
                "at_fault": at_fault,
                "seat_position": "Driver",
                "restraint": "Lap/Shoulder",
                "transported_to": (_fake.company() + " Medical Center") if injured != "No" else "-",
            }

        party1 = _party("Driver 1", at_fault=False, damage_desc=_party1_damage_desc)
        party2 = _party("Driver 2", at_fault=True, damage_desc=_party2_damage_desc)
        location = _fake.street_address() + ", " + report_city + ", " + report_state
        weather = random.choice(["Clear", "Rain", "Fog", "Snow", "Overcast"])
        road_cond = random.choice(["Dry", "Wet", "Icy", "Under Construction"])
        speed_limit_val = random.choice([25, 35, 45, 55, 65])
        narrative_paragraphs, narrative_summary = _police_narrative(
            scenario, dos.strftime("%m/%d/%Y"), location, weather, road_cond, speed_limit_val,
            party1, party2, collision_type, primary_factor, hit_and_run_flag, facts,
        )

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
            "location": location,
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
            "weather_conditions": weather,
            "lighting_conditions": random.choice(["Daylight", "Dusk", "Dark - Street Lights", "Dark - No Street Lights"]),
            "road_conditions": road_cond,
            "traffic_control": random.choice(["Signal - functioning", "Stop Sign", "None", "Officer/Flagger"]),
            "speed_limit": str(speed_limit_val) + " MPH",
            "collision_type": collision_type,
            "num_vehicles": "2",
            "hit_and_run": "Yes" if hit_and_run_flag else "No",
            "primary_factor": primary_factor,
            "other_factors": random.choice(["None noted", "Stop-and-go congestion", "Wet roadway", "Sun glare"]),
            "narrative": narrative_summary,
            "narrative_paragraphs": narrative_paragraphs,
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
                    "phone": _fake.phone_number(), "statement": _witness_statement(scenario, hit_and_run_flag, party2),
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
            "scenario_facts_title": facts_title,
            "scenario_facts": facts,
        })

    elif doc_type == "demand-letter":
        demand_amt = round(random.uniform(25000, 500000), 2)
        # Special-vs-general damages split depends on the case's own medical
        # specials, not a fixed formula - was pinned to a 40/60 split on every
        # letter. special_damages computed first, general_damages takes the
        # remainder so the two still sum exactly to demand_amt.
        special_damages = round(demand_amt * random.uniform(0.25, 0.55), 2)
        # demand-letter only ever appears in the litigation packet
        # (slip_and_fall/medical_malpractice/product_liability) - the shared
        # medical-family facts function already covers those 3 names.
        facts_title, facts = _medical_scenario_facts(scenario)
        demand_facts_para, _ = _litigation_narrative(
            scenario, patient["patient_name"], "the responsible party", dos.strftime("%m/%d/%Y")
        )
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
            "facts_summary": demand_facts_para,
            "scenario_facts_title": facts_title,
            "scenario_facts": facts,
        })

    elif doc_type == "pharmacy-invoice":
        # Template is an Indian GST tax invoice (GSTIN/HSN/IGST/UPI throughout) - a different
        # domain from a US pharmacy dispensing receipt, so this branch computes a real GST
        # invoice rather than reusing the old rx-fill fields (kept below for anything that
        # still reads them, but nothing in the template does any more).
        drug = random.choice(_NDC_DRUGS)
        pharmacy_legal_name = _fake.company() + " PHARMA PRIVATE LIMITED"
        pharmacy_short_name = pharmacy_legal_name.split()[0].upper() + " PHARMA"
        company_gstin = _gstin()
        # The template only ever prints IGST (no CGST/SGST split), so intra- vs inter-state
        # supply is not modeled here - customer_gstin varies only whether the sale is B2B.
        customer_gstin = _gstin() if random.random() < 0.3 else ""

        # Item pool/pricing used to be the same fixed maintenance-drug list
        # (_NDC_DRUGS) and the same $50-800 price band regardless of scenario,
        # so a "specialty_drug" invoice looked identical to a routine refill.
        # Real specialty drugs (biologics) run far higher per fill than a
        # chronic maintenance med, and a compounded prescription is a custom
        # mix, not an off-the-shelf NDC product - both are worth a distinct
        # item pool and price band, not just a different cause_of_loss-style
        # label on the same numbers.
        _SPECIALTY_DRUGS = [
            ("Humira (Adalimumab) 40mg/0.4mL", "SPEC-HUM40"),
            ("Enbrel (Etanercept) 50mg", "SPEC-ENB50"),
            ("Ozempic (Semaglutide) 1mg", "SPEC-OZE01"),
            ("Ocrevus (Ocrelizumab) 300mg", "SPEC-OCR300"),
        ]
        _COMPOUNDED_ITEMS = [
            ("Compounded Testosterone Cream 2%", "CMP-TRT2"),
            ("Compounded Pain Relief Cream - Custom Formula", "CMP-PAIN"),
            ("Compounded Pediatric Suspension - Custom Flavor", "CMP-PEDS"),
            ("Compounded Bio-Identical Hormone Capsules", "CMP-HRT"),
        ]
        if scenario == "specialty_drug":
            _item_pool = _SPECIALTY_DRUGS
            _hsn_pool, _qty_choices, _price_range = ["3004"], [1, 1, 2], (1500, 6500)
        elif scenario == "compounded_medication":
            _item_pool = _COMPOUNDED_ITEMS
            _hsn_pool, _qty_choices, _price_range = ["3003"], [1, 2], (300, 1200)
        else:
            _item_pool = [(d[0], d[1]) for d in _NDC_DRUGS]
            _hsn_pool, _qty_choices, _price_range = ["3004", "3003", "3005", "2106"], [1, 2, 5, 10], (50, 800)

        num_items = random.randint(2, 4) if scenario != "specialty_drug" else random.randint(1, 2)
        items = []
        for _ in range(num_items):
            drug_i = random.choice(_item_pool)
            qty = random.choice(_qty_choices)
            mrp = round(random.uniform(*_price_range), 2)
            rate = round(mrp * random.uniform(0.7, 0.95), 2)
            discount_pct = round(random.choice([0, 0, 5, 10]), 2)
            taxable_value = round(qty * rate * (1 - discount_pct / 100), 2)
            mfg = _rand_date_recent(years_back=1)
            items.append({
                "name": drug_i[0],
                "batch_no": "B" + "".join(random.choices(string.digits, k=6)),
                "mfg_date": mfg.strftime("%m/%Y"),
                "expiry_date": (mfg.replace(year=mfg.year + 2)).strftime("%m/%Y"),
                "hsn_sac": random.choice(_hsn_pool),
                "qty": qty,
                "unit": random.choice(["Strip", "Bottle", "Box"]) if scenario != "specialty_drug" else random.choice(["Prefilled Syringe", "Vial", "Auto-Injector"]),
                "mrp": mrp,
                "rate": rate,
                "discount_pct": discount_pct,
                "taxable_value": taxable_value,
            })

        subtotal_taxable_value = round(sum(i["taxable_value"] for i in items), 2)
        igst_pct = random.choice([5.0, 12.0, 18.0])
        igst_amount = round(subtotal_taxable_value * igst_pct / 100, 2)
        grand_total = round(subtotal_taxable_value + igst_amount, 2)

        hsn_groups: dict[str, dict] = {}
        for i in items:
            g = hsn_groups.setdefault(i["hsn_sac"], {"hsn_sac": i["hsn_sac"], "taxable_value": 0.0})
            g["taxable_value"] = round(g["taxable_value"] + i["taxable_value"], 2)
        hsn_summary = []
        for g in hsn_groups.values():
            g_igst = round(g["taxable_value"] * igst_pct / 100, 2)
            hsn_summary.append({
                "hsn_sac": g["hsn_sac"], "taxable_value": g["taxable_value"],
                "igst_pct": igst_pct, "igst_amount": g_igst, "total": round(g["taxable_value"] + g_igst, 2),
            })

        base.update({
            # legacy rx-fill fields - unused by the current template, kept for callers that
            # might still reference them (validate_document_structure no longer requires these)
            "rx_number": _rx_number(),
            "fill_date": dos.strftime("%m/%d/%Y"),
            "drug_name": drug[0],
            "ndc_code": drug[1],
            "form": drug[2],
            "prescriber_name": physician["physician_name"],
            "prescriber_dea": physician["dea"],
            "prescriber_npi": physician["npi"],
            # GST tax invoice fields
            "company_name": pharmacy_short_name,
            "company_name_line1": pharmacy_short_name,
            "company_name_line2": "MEDICALS & GENERAL STORE",
            "company_legal_name": pharmacy_legal_name,
            "company_address": _fake.street_address() + ", " + _fake.city() + " - " + _fake.postcode(),
            "company_phone": _fake.phone_number(),
            "company_gstin": company_gstin,
            "tagline": "Your Trusted Neighbourhood Pharmacy",
            "show_promo": False,
            "promo_text": "",
            "document_title": "TAX INVOICE",
            "copy_label": random.choice(["ORIGINAL FOR RECIPIENT", "DUPLICATE FOR TRANSPORTER", "TRIPLICATE FOR SUPPLIER"]),
            "customer_name": patient["patient_name"],
            "contact_person": patient["patient_name"],
            "customer_address": _fake.street_address() + ", " + _fake.city() + " - " + _fake.postcode(),
            "customer_phone": patient["phone"],
            "customer_gstin": customer_gstin,
            "place_of_supply": _fake.state() + f" ({random.randint(1, 37):02d})",
            "invoice_number": "INV" + "".join(random.choices(string.digits, k=8)),
            "invoice_date": dos.strftime("%d/%m/%Y"),
            "items": items,
            "subtotal_taxable_value": subtotal_taxable_value,
            "igst_pct": igst_pct,
            "igst_amount": igst_amount,
            "total_qty": sum(i["qty"] for i in items),
            "total_rate": round(sum(i["rate"] for i in items), 2),
            "grand_total": grand_total,
            "total_in_words": _amount_in_words(grand_total),
            "hsn_summary": hsn_summary,
            "hsn_total_taxable_value": subtotal_taxable_value,
            "hsn_total_igst_amount": igst_amount,
            "hsn_total": grand_total,
            "tax_in_words": _amount_in_words(igst_amount),
            "bank_name": random.choice(["State Bank of India", "HDFC Bank", "ICICI Bank", "Axis Bank"]),
            "bank_branch": _fake.city() + " Branch",
            "bank_account_number": "".join(random.choices(string.digits, k=12)),
            "bank_ifsc": "".join(random.choices(string.ascii_uppercase, k=4)) + "0" + "".join(random.choices(string.digits, k=6)),
            "upi_id": pharmacy_short_name.lower().replace(" ", "") + "@upi",
            "terms": [
                "Goods once sold will not be taken back or exchanged.",
                "All disputes are subject to local jurisdiction only.",
                "Interest @18% p.a. will be charged if the bill is not paid within the due date.",
            ],
            "footer_note": "Thanks for your order! We look forward to working with you again soon.",
        })

    elif doc_type == "property-loss-notice":
        facts_title, facts = _property_scenario_facts(scenario)
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
            "scenario_facts_title": facts_title,
            "scenario_facts": facts,
        })

    elif doc_type == "auto-accident-report":
        # Template is a real state-agency "Employee Vehicle Accident Report" (Washington
        # S.F. 97 style): the reporting party is a STATE EMPLOYEE driving a state vehicle,
        # with up to 2 other vehicles, an "other property" section, and injured-parties/
        # witness tables. This branch builds that full shape; the old flat fields below are
        # kept (nothing else reads them any more, but they're harmless) and vehicle1/employee
        # are built FROM them so both stay consistent with each other.
        make1, model1 = random.choice([("Toyota", "Camry"), ("Honda", "Accord"), ("Ford", "F-150"),
                                        ("Chevrolet", "Malibu"), ("BMW", "3 Series"), ("Tesla", "Model 3")])
        make2, model2 = random.choice([("Nissan", "Altima"), ("Hyundai", "Elantra"), ("Jeep", "Wrangler"),
                                        ("Subaru", "Outback"), ("Mazda", "CX-5")])
        vehicle1_year = str(random.randint(2010, 2024))
        vehicle1_plate = "".join(random.choices(string.ascii_uppercase, k=3)) + "".join(random.choices(string.digits, k=4))
        vehicle1_vin = "".join(random.choices(string.ascii_uppercase + string.digits, k=17))
        other_vehicle_year = str(random.randint(2010, 2024))
        other_vehicle_plate = "".join(random.choices(string.ascii_uppercase, k=3)) + "".join(random.choices(string.digits, k=4))
        other_driver_name_val = _fake.name()
        other_driver_insurer_val = random.choice(_INSURERS)
        other_driver_policy_val = _policy_number()
        damage_desc, other_damage_desc = _vehicle_damage_descriptions(scenario)
        est_damage = round(random.uniform(1500, 25000), 2)
        towed = random.choice(["Yes", "No"])
        has_injury = random.random() < 0.3
        cited = random.random() < 0.4
        facts_title, facts = _auto_scenario_facts(scenario)

        base.update({
            # legacy flat fields - unused by the current template, kept for callers that
            # might still reference them (validate_document_structure no longer requires these)
            "insured_name": patient["patient_name"],
            "accident_location": _fake.street_address() + ", " + _fake.city() + ", " + random.choice(_STATES),
            "vehicle_info": {"year": vehicle1_year, "make": make1, "model": model1, "vin": vehicle1_vin, "license_plate": vehicle1_plate},
            "driver_name": patient["patient_name"],
            "driver_license_number": _fake.bothify("??#######").upper(),
            "other_vehicle": {"year": other_vehicle_year, "make": make2, "model": model2, "license_plate": other_vehicle_plate},
            "other_driver_name": other_driver_name_val,
            "other_driver_insurer": other_driver_insurer_val,
            "other_driver_policy_number": other_driver_policy_val,
            "damage_description": damage_desc,
            "estimated_damage": est_damage,
            "airbags_deployed": random.choice(["Yes", "No"]),
            "vehicle_towed": towed,
            "police_report_number": "RPT" + "".join(random.choices(string.digits, k=8)),
            "at_fault": random.choice(["Yes", "No", "Disputed"]),
            "bodily_injury": "Yes" if has_injury else "No",
            "witnesses": [{"name": _fake.name(), "phone": _fake.phone_number(),
                           "address": _fake.street_address(), "city": _fake.city()}],
            # state accident-report form fields
            "accident_date": dos.strftime("%m/%d/%Y"),
            "accident_time": f"{random.randint(0,23):02d}:{random.randint(0,59):02d}",
            "accident_time_ampm": random.choice(["AM", "PM"]),
            "employee": {
                "business_address": _fake.street_address(),
                "zip": _fake.zipcode(),
                "business_phone": _fake.phone_number(),
                "email": patient["patient_name"].lower().replace(" ", ".") + "@agency.wa.gov",
                "license_no": _fake.bothify("??#######").upper(),
                "license_restrictions": random.choice(["None", "Corrective Lenses"]),
                "if_yes_indicate": "",
                "official_business": True,
            },
            "vehicle1": {
                "license_no": vehicle1_plate,
                "year": vehicle1_year,
                "make": make1,
                "body_type": random.choice(["Sedan", "SUV", "Pickup", "Van"]),
                "where_located": "State motor pool",
                "no_of_passengers": str(random.randint(0, 2)),
                "est_repair_cost": f"{est_damage:,.2f}",
                "prior_accident": False,
                "owning_agency": physician["hospital"],
                "damage_description": damage_desc,
                "private_owner_or_equipment_no": "EQ" + "".join(random.choices(string.digits, k=6)),
                "insurer": "Self-Insured (State Risk Management)",
            },
            "vehicle2": {
                "owner_name": other_driver_name_val,
                "owner_phone": _fake.phone_number(),
                "owner_address": _fake.street_address(),
                "owner_city": _fake.city(),
                "owner_zip": _fake.zipcode(),
                "driver_name": other_driver_name_val,
                "driver_age": str(random.randint(19, 70)),
                "driver_phone": _fake.phone_number(),
                "driver_address": _fake.street_address(),
                "driver_city": _fake.city(),
                "driver_zip": _fake.zipcode(),
                "driver_license_no": _fake.bothify("??#######").upper(),
                "vehicle_license_no": other_vehicle_plate,
                "vehicle_make": make2,
                "vehicle_year": other_vehicle_year,
                "body_type": random.choice(["Sedan", "SUV", "Pickup", "Van"]),
                "passengers": "",
                "repair_cost": f"{round(est_damage * random.uniform(0.4, 0.9), 2):,.2f}",
                "damage_description": other_damage_desc,
                "insurance_company": other_driver_insurer_val,
                "policy_no": other_driver_policy_val,
            },
            # single-other-vehicle scenario is the norm - vehicle3 stays empty rather than
            # inventing a third party that was never in the collision.
            "vehicle3": {k: "" for k in (
                "owner_name", "owner_phone", "owner_address", "owner_city", "owner_zip",
                "driver_name", "driver_age", "driver_phone", "driver_address", "driver_city",
                "driver_zip", "driver_license_no", "vehicle_license_no", "vehicle_make",
                "vehicle_year", "body_type", "passengers", "repair_cost", "damage_description",
                "insurance_company", "policy_no",
            )},
            "other_property": {k: "" for k in ("what_was_damaged", "repair_cost", "owner_name_address", "city", "zip", "phone")},
            "injured_parties": [
                {"name_address": f"{other_driver_name_val}, {_fake.street_address()}",
                 "extent_of_injury": random.choice(["Minor - complaint of pain", "Moderate - treated and released"]),
                 "age": str(random.randint(19, 70)), "vehicle": 2, "pedestrian": False}
            ] if has_injury else [],
            "other": {
                "police_investigated": cited,
                "police_division": random.choice(["City Police", "County Sheriff", "State Patrol"]) if cited else "",
                "citation_issued": cited,
                "citation_issued_to": "Veh. 2" if cited else "",
                "collision_report_filed": cited,
            },
            "scenario_facts_title": facts_title,
            "scenario_facts": facts,
        })

    elif doc_type == "litigation-document":
        plaintiff_state = _fake.state()
        forum_state = _fake.state()
        forum_county = _fake.city() + " County"
        filing_date_val = date.today()
        prayer_amount = round(random.uniform(50000, 1000000), 0)
        # causes_of_action used to be a pure random.sample regardless of
        # scenario, so a product_liability complaint could come back with no
        # products-liability cause at all. Anchor one cause to the scenario,
        # then fill out the rest of the sample from what is left - keeps the
        # variety (2-3 causes) while guaranteeing the scenario is represented.
        # The extra causes are drawn from a per-scenario COMPATIBLE pool, not
        # the full list - the full list mixes theories that don't co-occur in
        # one fact pattern (a fall on a property has no product to be
        # defective; a botched medical procedure isn't a premises condition),
        # so sampling it unrestricted could pad a medical-malpractice
        # complaint with "Strict Product Liability" and "Premises Liability" -
        # causes of action a real complaint alleging that incident never
        # would plead together.
        _anchor = {
            "slip_and_fall": "Premises Liability",
            "medical_malpractice": "Negligence",
            "product_liability": "Strict Product Liability",
        }.get(scenario)
        _compatible_extras = {
            "slip_and_fall": ["Negligence", "Breach of Duty of Care",
                               "Negligent Infliction of Emotional Distress"],
            "medical_malpractice": ["Breach of Duty of Care",
                                     "Negligent Infliction of Emotional Distress"],
            "product_liability": ["Negligence", "Breach of Duty of Care",
                                    "Negligent Infliction of Emotional Distress"],
        }.get(scenario)
        if _anchor:
            causes = [_anchor] + random.sample(
                _compatible_extras, k=min(len(_compatible_extras), random.choice([1, 2]))
            )
        else:
            _cause_pool = ["Negligence", "Breach of Duty of Care", "Premises Liability",
                           "Negligent Infliction of Emotional Distress", "Strict Product Liability"]
            causes = random.sample(_cause_pool, k=random.choice([2, 3]))

        def _attorney(role: str = "") -> dict:
            return {
                "name": _fake.name(),
                "bar_number": str(random.randint(100000, 299999)),
                "role": role,
            }

        lead_attorney = _attorney("Managing Partner")
        firm_attorneys = [lead_attorney] + [_attorney() for _ in range(random.randint(2, 4))]
        firm_last_names = [a["name"].split()[-1] for a in firm_attorneys[:3]]
        defendant_name_val = _fake.company()
        facts_para, general_allegations = _litigation_narrative(
            scenario, patient["patient_name"], defendant_name_val, dos.strftime("%m/%d/%Y")
        )

        base.update({
            "plaintiff_name": patient["patient_name"],
            "plaintiff_state_of_incorporation": plaintiff_state,
            "defendant_name": defendant_name_val,
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
            "facts": facts_para,
            "general_allegations": general_allegations,
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
            "letter_reference": f"This firm represents {patient['patient_name']} in connection with the "
                                 f"{scenario.replace('_', ' ')} incident of {dos.strftime('%m/%d/%Y')} "
                                 f"described in the enclosed complaint.",
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
        facts_title, facts = _medical_scenario_facts(scenario)
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
            "remarks": _facts_line(facts),
            "condition_code": random.choice(["", "", "A0"]),
            "creation_date": date.today().strftime("%m/%d/%y"),
        })

    return base
