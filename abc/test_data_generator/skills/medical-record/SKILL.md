---
name: medical-record
description: >
  Generate realistic SOAP-format clinical visit notes and medical records for IDP testing.
  Use when the document type is physician note, clinical note, or general medical record.
metadata:
  owner: idp-test-team
  version: "1"
  page-size: letter-portrait
  template: medical_record
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Medical Record Generation Skill

## Required Sections
1. Patient Header — Name, DOB, MRN, Insurance ID, DOS, Encounter Type
2. Chief Complaint — 1-3 sentences
3. HPI — History of Present Illness (OPQRST format)
4. Allergies and Current Medications — "NKDA" is a valid, common allergy value
5. Vital Signs — BP, HR, Temp, RR, SpO2, Weight, Height
6. Physical Examination — system-by-system findings
7. Assessment — ICD-10 codes (2-4 codes, clinically plausible)
8. Plan — CPT codes, Rx, follow-up schedule
8a. Scenario Details Section — present for every registered scenario across every packet
    (13 total), omitted only for `general` — see "IDP Test Scenarios" below
9. Physician Signature Block — Name, NPI, DEA if applicable, signed date

## Synthetic Data Rules
- MRN: 7-digit numeric
- ICD-10 codes must be plausible for the declared scenario
- DOS within past 2 years
- All names, DOB, addresses from Faker

## IDP Test Scenarios
See references/test-scenarios.md for edge cases and full scenario coverage (medical-record is
reused by every packet, so it is called with 13 different scenario names, not just 4).

## Document composition
Like every doc type, this template is decomposed into named Jinja macros ("components") in
`renderers/templates/medical_record.html`, assembled by `renderers/components.py`'s
`COMPONENT_COMPOSITION["medical-record"]`. Unlike police-report (which has two structurally
different shapes depending on scenario), every registered scenario for this doc type resolves
to the SAME component list - a real clinical visit note doesn't restructure by scenario in the real
world, only its content does (see the scenario-specific data-generation notes above). The
mechanism exists uniformly across every doc type for architectural consistency, even where
it isn't exercised to produce different shapes.
