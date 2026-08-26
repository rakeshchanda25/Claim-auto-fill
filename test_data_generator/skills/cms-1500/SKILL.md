---
name: cms-1500
description: >
  Generate CMS-1500 (HCFA) professional claim forms for IDP testing. Supports physician office,
  outpatient, and specialist claims. Covers all 33 standard boxes.
metadata:
  owner: idp-test-team
  version: "1"
  page-size: letter-portrait
  template: cms_1500
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# CMS-1500 Generation Skill

## Required Boxes
- Box 1a: Insured's ID Number
- Box 2: Patient Name
- Box 3: Patient DOB and Sex
- Box 4: Insured's Name
- Box 5: Patient Address
- Box 6: Patient Relationship to Insured
- Box 21: Diagnosis Codes (ICD-10-CM, up to 12)
- Box 24A-J: Service line items (Date, POS, Procedure, Diagnosis Pointer, Charges, Days, NPI)
- Box 23: Prior Authorization Number
- Box 25: Federal Tax ID
- Box 28: Total Charge
- Box 29: Amount Paid
- Box 31: Physician Signature
- Box 33a: Billing Provider NPI

## Place of Service Codes
- 11 = Office
- 21 = Inpatient Hospital
- 23 = Emergency Room
- 22 = Outpatient Hospital

## Synthetic Data Rules
- NPI: 10 digits
- Prior auth: AUTH + 8 digits
- Federal Tax ID: 9 digits (no dashes)
- Accept assignment: always YES for test data
