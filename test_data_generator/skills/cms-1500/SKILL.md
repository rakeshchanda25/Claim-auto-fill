---
name: cms-1500
description: >
  Generate CMS-1500 (HCFA 02/12) professional claim forms for IDP testing - physician office,
  outpatient, and specialist claims. Template covers boxes 1a-33a with a real service-line grid
  (24A-J). Rendered through the placeholder-then-fill pipeline (see render_document_to_pdf), so
  the output is a genuine fillable AcroForm PDF, not a flat image.
metadata:
  owner: idp-test-team
  version: "2"
  page-size: letter-portrait
  template: cms_1500
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# CMS-1500 Generation Skill

## Boxes covered by the template
- 1a: Insured's I.D. Number · 2: Patient Name · 3: Patient DOB/Sex
- 4: Insured's Name · 5: Patient Address · 6: Relationship to Insured · 7: Insured's Address
- 9: Other Insured's Name (N/A) · 10a-c: Condition related to Employment/Auto/Other Accident
- 11: Insured's Policy Group Number · 11a: Insured's DOB/Sex · 11c: Insurance Plan Name
- 12/13: Signatures (always "Signature on File")
- 14: Date of Current Illness + qualifier · 16: Dates Unable to Work
- 17/17a-b: Referring Provider + NPI · 18: Hospitalization Dates · 19: Additional Claim Info
- 20: Outside Lab? + Charges · 21: Diagnosis Codes (ICD-10-CM, A-D pointers)
- 22: Resubmission Code/Original Ref No. · 23: Prior Authorization Number
- 24A-J: Service line items (Date, POS, EMG, CPT/HCPCS+Modifier, Diag Pointer, Charges, Units, Rendering NPI)
- 25: Federal Tax ID (+ EIN/SSN qualifier) · 26: Patient Account No. · 27: Accept Assignment
- 28/29/30: Total Charge / Amount Paid / Balance Due
- 31: Physician Signature · 32/32a: Service Facility + NPI · 33/33a: Billing Provider + NPI

## Place of Service Codes
- 11 = Office · 21 = Inpatient Hospital · 22 = Outpatient Hospital · 23 = Emergency Room

## Synthetic Data Rules
- NPI: 10 digits · Prior auth: AUTH + 8 digits · Federal Tax ID: 9 digits (no dashes)
- Accept assignment: always YES for test data
- Box 10 (employment/auto/other accident related) is driven by `scenario`: auto-accident
  scenarios (`rear_end_collision`, `intersection_accident`) set Box 10b to YES with a state;
  everything else defaults to NO.
- Keep dates in a sensible order: date of illness ≤ date of service ≤ signature date.
