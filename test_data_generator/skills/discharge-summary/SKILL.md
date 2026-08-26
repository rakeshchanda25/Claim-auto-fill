---
name: discharge-summary
description: >
  Generate hospital discharge summary documents for IDP testing. Covers admission/discharge dates,
  attending physician, DRG codes, medication reconciliation, and discharge instructions.
metadata:
  owner: idp-test-team
  version: "1"
  page-size: letter-portrait
  template: discharge_summary
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Discharge Summary Generation Skill

## Required Sections
1. Patient Header — Name, DOB, MRN, Insurance ID
2. Admission and Discharge Dates — both required
3. Length of Stay and DRG Code
4. Attending Physician — Name, Specialty, NPI
5. Diagnosis on Admission — narrative + ICD-10
6. Hospital Course — clinical narrative (4-6 sentences)
7. Discharge Diagnoses — ICD-10 codes
8. Condition at Discharge — Stable/Improved/Good
9. Medications at Discharge — name, dose, frequency
10. Discharge Instructions and Follow-Up
11. Physician Signature

## Synthetic Data Rules
- DRG code: 3-digit numeric (100-999)
- Length of stay: 1-7 days
- Medications: 2-4 at discharge
- Discharge condition: one of Stable, Improved, Good
