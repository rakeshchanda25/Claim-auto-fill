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
1. Patient Header — Name, DOB, MRN, Insurance ID, DOS
2. Chief Complaint — 1-3 sentences
3. HPI — History of Present Illness (OPQRST format)
4. Vital Signs — BP, HR, Temp, RR, SpO2, Weight
5. Physical Examination — system-by-system findings
6. Assessment — ICD-10 codes (2-4 codes, clinically plausible)
7. Plan — CPT codes, Rx, follow-up schedule
8. Physician Signature Block — Name, NPI, DEA if applicable, date

## Synthetic Data Rules
- MRN: 7-digit numeric
- ICD-10 codes must be plausible for the declared scenario
- DOS within past 2 years
- All names, DOB, addresses from Faker

## IDP Test Scenarios
See references/test-scenarios.md for edge cases.
