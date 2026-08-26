---
name: ub-04
description: >
  Generate UB-04 institutional claim forms (CMS-1450) for IDP testing - inpatient hospital
  stays with revenue codes, occurrence/value codes, DRG code, and payer information. Rendered
  through the placeholder-then-fill pipeline (see render_document_to_pdf), so the output is a
  genuine fillable AcroForm PDF, not a flat image.
metadata:
  owner: idp-test-team
  version: "2"
  page-size: letter-portrait
  template: ub_04
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# UB-04 Generation Skill

## Form locators covered by the template
- FL1: Provider Name/Address/Phone · FL3a: Patient Control No. · FL3b: Medical Record No.
- FL4: Type of Bill (3-digit: 111=inpatient, 131=outpatient) · FL5: Federal Tax No.
- FL6: Statement Covers Period (From-Through) · FL8: Patient Name · FL9: Patient Address
- FL10: Birthdate · FL11: Sex
- FL12-15: Admission Date/Hour/Type/Source · FL16: Discharge Date · FL17: Patient (Discharge) Status
- FL31: Occurrence Code/Date · FL39: Value Code/Amount
- FL42-47: Revenue Code lines (code, description, HCPCS/rate, service date, units, total charges)
- FL50: Payer Name · FL54: Prior Payments · FL58: Insured's Name · FL63: Treatment Authorization
- FL67: Principal Diagnosis Code · FL69: Admitting Diagnosis
- FL74: Principal Procedure Code/Date · DRG code
- FL76: Attending Provider Name/NPI · FL77: Operating Physician

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
