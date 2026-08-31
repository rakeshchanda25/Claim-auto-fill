---
name: ub-04
description: >
  Generate a UB-04/CMS-1450 institutional claim form for IDP testing, recreating the real
  specimen's dense edge-to-edge box grid with box-number superscripts - inpatient hospital
  stays with revenue codes, occurrence/value codes, DRG code, and full payer/insured
  information (FL1-FL81). Output is a plain (non-fillable) PDF - values are painted directly
  into the page content, not into AcroForm fields.
metadata:
  owner: idp-test-team
  version: "4"
  page-size: letter-portrait
  template: ub_04
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# UB-04 Generation Skill

## Form locators covered by the template
- FL1: Provider Name/Address/Phone · FL2: Pay-To Name/Address
- FL3a: Patient Control No. · FL3b: Medical Record No.
- FL4: Type of Bill (3-digit: 111=inpatient, 131=outpatient) · FL5: Federal Tax No.
- FL6: Statement Covers Period (From-Through) · FL8: Patient Name · FL9: Patient Address
- FL10: Birthdate · FL11: Sex
- FL12-15: Admission Date/Hour/Type/Source · FL16: Discharge Date · FL17: Patient (Discharge)
  Status · FL29: Accident State
- FL31: Occurrence Code/Date · FL39: Value Code/Amount
- FL42-48: Revenue Code lines (code, description, HCPCS/rate, service date, units, total
  charges, non-covered charges)
- FL50: Payer Name · FL51: Health Plan ID · FL53: Assignment of Benefits (Y/N)
- FL54: Prior Payments · FL55: Estimated Amount Due
- FL58: Insured's Name · FL59: Patient Relationship Code
- FL61: Group Name · FL62: Insurance Group No. · FL63: Treatment Authorization
- FL64: Document Control Number · FL65: Employer Name
- FL67: Principal Diagnosis Code · FL69: Admitting Diagnosis · FL70: Patient Reason Diagnosis
- FL71: PPS Code · FL74: Principal Procedure Code/Date · DRG code
- FL73: Attending — qualifier + NPI + last/first name split (`attending_last_name` /
  `attending_first_name`, parsed from `attending_physician_name`)
- FL77: Operating Physician · FL80: Remarks · FL81: Condition Code (CC)

## Revenue Codes (common)
- 0110 = Room & Board – Medical/Surgical · 0250 = Pharmacy · 0300 = Laboratory
- 0310 = Hematology · 0450 = Emergency Room · 0710 = Recovery Room
- 0636 = Drugs Requiring Detailed Coding

## Synthetic Data Rules
- `total_charges` must equal the sum of every listed revenue-code line's charge - never state a
  total that doesn't match the itemized lines above it.
- Admission date ≤ discharge date; occurrence-code date should fall within that window.
- Discharge status "30 Still Patient" is inconsistent with a populated discharge_date - if the
  scenario implies an ongoing stay, use a real discharged status instead.
- `est_amount_due` is 15% of `total_charges` when `assignment_of_benefits == "Y"` (payer pays
  the rest), otherwise the full `total_charges` (patient is billed directly) - keep these two
  fields consistent if you revise either one.
- `federal_tax_id` is a real 9-digit number, separate from `provider_npi` - do not conflate them.
- FL80 (Remarks) is populated with a one-line scenario-facts summary, since UB-04's fixed box
  layout can't grow a new section - see references/test-scenarios.md.

## Document composition
Like every doc type, this template is decomposed into named Jinja macros ("components") in
`renderers/templates/ub_04.html`, assembled by `renderers/components.py`'s
`COMPONENT_COMPOSITION["ub-04"]`. Unlike police-report (which has two structurally
different shapes depending on scenario), every registered scenario for this doc type resolves
to the SAME component list - a real federal institutional claim form doesn't restructure by scenario in the real
world, only its content does (see the scenario-specific data-generation notes above). The
mechanism exists uniformly across every doc type for architectural consistency, even where
it isn't exercised to produce different shapes.
