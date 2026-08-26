---
name: ub-04
description: >
  Generate UB-04 institutional claim forms (CMS-1450) for IDP testing. Covers inpatient
  hospital stays with revenue codes, DRG codes, and payer information.
metadata:
  owner: idp-test-team
  version: "1"
  page-size: letter-landscape
  template: ub_04
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# UB-04 Generation Skill

## Required Boxes
- FL 1: Provider Name
- FL 4: Type of Bill (3-digit: 111=inpatient, 131=outpatient)
- FL 5: Federal Tax ID
- FL 6: Statement Dates (From/Through)
- FL 8: Patient Name
- FL 10: Birth Date
- FL 11: Sex
- FL 14: Admission Date
- FL 16: Discharge Date
- FL 17: Discharge Status (01=Home, 03=SNF, 20=Expired)
- FL 18: DRG Code
- FL 42-49: Revenue Code lines (code, description, HCPCS, date, units, charges)
- FL 47: Total Charges
- FL 50: Payer Name
- FL 60: Insured ID
- FL 67: Principal Diagnosis Code (ICD-10)
- FL 76: Attending Physician NPI + Name

## Revenue Codes (common)
- 0110 = Room & Board – Medical/Surgical
- 0250 = Pharmacy
- 0300 = Laboratory
- 0310 = Hematology
- 0450 = Emergency Room
- 0636 = Drugs Requiring Detailed Coding
