---
name: cms-1500
description: >
  Generate CMS-1500 (HCFA 02/12) professional claim forms for IDP testing - physician office,
  outpatient, and specialist claims. Template covers boxes 1a-33a with a real service-line grid
  (24A-J). Rendered the same way as every other template - see render_document_to_pdf -
  a flat print of the form, not a fillable AcroForm PDF.
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
- Box 10 (employment/auto/other accident related) is driven by `scenario`: `rear_end_collision`/
  `intersection_accident`/`slip_and_fall` set Box 10b to YES (10b also gets a state for the two
  auto scenarios); everything else defaults to NO.
- Keep dates in a sensible order: date of illness ≤ date of service ≤ signature date.
- Box 19 (Additional Claim Info) is populated with a one-line scenario-facts summary, since
  CMS-1500's fixed box layout can't grow a new section - see references/test-scenarios.md.

## Document composition
Like every doc type, this template is decomposed into named Jinja macros ("components") in
`renderers/templates/cms_1500.html`, assembled by `renderers/components.py`'s
`COMPONENT_COMPOSITION["cms-1500"]`. Unlike police-report (which has two structurally
different shapes depending on scenario), every registered scenario for this doc type resolves
to the SAME component list - a real federal claim form doesn't restructure by scenario in the real
world, only its content does (see the scenario-specific data-generation notes above). The
mechanism exists uniformly across every doc type for architectural consistency, even where
it isn't exercised to produce different shapes.
