"""US insurance domain knowledge: which documents a given claim actually generates.

This is the reference the model reads before choosing a document set. It is
deliberately data, not logic - the decision stays with the model, this only
gives it the domain grounding it does not reliably have on its own.

Everything here describes what a real US claim FILE typically contains. It is
practice guidance for generating realistic test data, not legal advice and not
a statement of statutory requirement.
"""

# The single most important distinction in a US claim file, and the one a model
# gets wrong most often if it is not told: WHO is paying decides which
# documents exist at all.
COVERAGE_BASICS = """\
FIRST PARTY vs THIRD PARTY - this decides the document set more than anything else.

- FIRST PARTY: the insured claims against their OWN policy (collision,
  comprehensive, homeowners, PIP/med-pay). There is no adversary. The file is
  built from the carrier's own loss notice, proof of loss, estimates and
  payment records. There is NO demand letter and NO lawsuit, because nobody is
  demanding anything from anybody - the insured is simply claiming a benefit.

- THIRD PARTY (liability): a claimant demands payment from SOMEONE ELSE's
  insurer, because that person is alleged to be at fault. Liability has to be
  proven, and damages have to be proven separately. This is what produces
  police reports (to establish fault), medical records and bills (to prove
  injury and its cost), a demand letter (the claimant's settlement demand),
  and - if the demand is not met - a filed complaint.

A first-party collision claim and a third-party bodily-injury claim on the SAME
crash contain very different documents. Do not treat "auto accident" as one
thing.
"""

# claim shape -> what the file realistically holds. Keys are descriptive, not
# system identifiers; the model matches the claim narrative against these.
CLAIM_PLAYBOOK = [
    {
        "claim_type": "Auto - third-party bodily injury (BI) liability",
        "signals": "another party is at fault; injury claimed; attorney involved; "
                   "'claimant' distinct from 'insured'; demand or settlement mentioned",
        "core": ["police-report", "medical-record", "medical-bill", "demand-letter"],
        "often": ["cms-1500", "ub-04", "discharge-summary", "eob-explanation",
                  "litigation-document", "acord-25"],
        "notes": "Police report establishes liability. Medical records prove causation, "
                 "bills prove the money. The EOB matters because the health plan that "
                 "already paid holds a lien / subrogation interest against the "
                 "settlement. A demand letter appears once treatment is complete; a "
                 "complaint only if the demand fails.",
    },
    {
        "claim_type": "Auto - third-party property damage (PD) liability",
        "signals": "vehicle or property damage caused by an at-fault third party, no injury",
        "core": ["police-report", "auto-accident-report"],
        "often": ["acord-25", "demand-letter"],
        "notes": "No medical documents at all when there is no injury. Adding medical "
                 "records to a pure PD claim is a common and obvious error.",
    },
    {
        "claim_type": "Auto - first-party collision / comprehensive",
        "signals": "insured's own vehicle damage; theft, fire, hail, glass, animal strike; "
                   "no third party being pursued",
        "core": ["auto-accident-report"],
        "often": ["police-report", "acord-25"],
        "notes": "A police report is effectively mandatory for THEFT and vandalism - a "
                 "carrier will not pay a theft claim without a police case number. It is "
                 "optional for hail or an animal strike. No demand letter, no complaint: "
                 "this is the insured's own policy.",
    },
    {
        "claim_type": "Auto - first-party injury (PIP / med-pay)",
        "signals": "no-fault state; PIP; med-pay; insured's own injury under own policy",
        "core": ["medical-record", "medical-bill"],
        "often": ["auto-accident-report", "police-report", "cms-1500", "eob-explanation"],
        "notes": "Medical documents without a liability fight. Still first-party, so no "
                 "demand letter.",
    },
    {
        "claim_type": "Property - homeowners / commercial (fire, water, wind, theft)",
        "signals": "structure or contents damage; fire, smoke, burst pipe, storm, hail, "
                   "burglary, vandalism",
        "core": ["property-loss-notice"],
        "often": ["police-report", "acord-25"],
        "notes": "The loss notice is the first-party FNOL and is always present. Police "
                 "report is required for theft/vandalism, and common for fire (arson "
                 "investigation). NO medical documents unless a person was injured. "
                 "NO auto documents.",
    },
    {
        "claim_type": "Premises liability (slip and fall)",
        "signals": "injury on someone else's property; store, sidewalk, stairwell; "
                   "negligence alleged",
        "core": ["medical-record", "medical-bill", "demand-letter"],
        "often": ["police-report", "discharge-summary", "eob-explanation",
                  "litigation-document", "cms-1500"],
        "notes": "Third-party liability, so it looks like a BI claim - but there is no "
                 "vehicle. Never add auto-accident-report here. An incident report may "
                 "stand in for a police report.",
    },
    {
        "claim_type": "Product liability",
        "signals": "defective product caused injury; manufacturer or retailer named",
        "core": ["medical-record", "medical-bill", "demand-letter", "litigation-document"],
        "often": ["discharge-summary", "eob-explanation", "ub-04"],
        "notes": "Almost always reaches litigation, so the complaint is expected rather "
                 "than optional.",
    },
    {
        "claim_type": "Medical / health benefit claim",
        "signals": "treatment billed to a health plan; adjudication, allowed amount, "
                   "member responsibility",
        "core": ["medical-record", "medical-bill", "eob-explanation"],
        "often": ["cms-1500", "ub-04", "discharge-summary", "pharmacy-invoice"],
        "notes": "See BILLING_FORMS below - CMS-1500 and UB-04 are not interchangeable.",
    },
    {
        "claim_type": "Pharmacy benefit claim",
        "signals": "prescription drug; NDC; days supply; specialty or compounded drug",
        "core": ["pharmacy-invoice"],
        "often": ["medical-record", "eob-explanation"],
        "notes": "The medical record is the prescribing note that justifies the drug. "
                 "No hospital forms unless the drug was administered inpatient.",
    },
    {
        "claim_type": "Litigated claim (any line, suit filed)",
        "signals": "complaint filed; case number; court named; plaintiff and defendant; "
                   "discovery",
        "core": ["litigation-document", "demand-letter", "medical-record", "medical-bill"],
        "often": ["eob-explanation", "police-report", "ub-04"],
        "notes": "The demand letter usually predates the complaint and stays in the file. "
                 "Damages documentation is what the suit is actually about.",
    },
]

# The single most common technical error a model makes on US medical claims.
BILLING_FORMS = """\
BILLING FORM RULES - these are not interchangeable:

- CMS-1500: PROFESSIONAL claims. Physicians, therapists, independent labs,
  ambulance, any non-institutional provider.
- UB-04 (CMS-1450): INSTITUTIONAL claims. Hospitals, facilities, SNFs, hospices,
  emergency departments billing facility charges.
- A hospital admission usually produces BOTH: a UB-04 for the facility charge
  AND a CMS-1500 for the attending physician's professional charge.
- discharge-summary belongs to an INPATIENT ADMISSION only. Do not include it
  for an ER-only visit, an outpatient procedure, or a claim with no admission.
- eob-explanation is the payer's adjudication of a bill. It only makes sense
  when a bill exists - never include an EOB with no corresponding bill.
- acord-25 is a CERTIFICATE OF INSURANCE: proof that coverage exists. It is
  exchanged between carriers, or demanded by a third party. It is not part of a
  purely internal medical claim.
"""

SELECTION_RULES = """\
HOW TO CHOOSE:

1. Decide first party or third party (see above). This eliminates whole
   document categories immediately.
2. Include every document the claim would REALISTICALLY have generated. A real
   BI file is not one document - it is typically 4 to 8.
3. Do not include a document the claim gives no basis for. No injury means no
   medical records. No vehicle means no auto report. No admission means no
   discharge summary. No bill means no EOB.
4. Prefer being complete over being minimal, but every document must be
   justifiable from the claim narrative. Adding the entire menu regardless of
   relevance is as wrong as returning a single document.
5. Match the scenario to what actually happened, not to the document list.
"""


def playbook_text() -> str:
    """The full domain reference, rendered for the prompt."""
    blocks = [COVERAGE_BASICS, "CLAIM TYPES AND THE DOCUMENTS THEY GENERATE:"]
    for entry in CLAIM_PLAYBOOK:
        blocks.append(
            f"\n* {entry['claim_type']}\n"
            f"  Recognise it by: {entry['signals']}\n"
            f"  Nearly always: {', '.join(entry['core'])}\n"
            f"  Often also: {', '.join(entry['often'])}\n"
            f"  {entry['notes']}"
        )
    blocks.append("\n" + BILLING_FORMS)
    blocks.append(SELECTION_RULES)
    return "\n".join(blocks)
