---
name: medical-bill
description: >
  Generate a "superbill" for IDP testing - the itemized CPT-coded charges/adjustments/balance
  statement combined with a clinical encounter note (chief complaint, HPI, vitals, physical
  exam, assessment, plan), the common real-world document combining both on one form.
metadata:
  owner: idp-test-team
  version: "2"
  page-size: letter-portrait
  template: medical_bill
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Medical Bill Generation Skill

## Required Sections
1. Provider Header — Hospital name, address, phone
2. Patient Statement Header — Account number, statement date, due date
3. Patient Information — Name, DOB, service date, insurance, claim number
4. Encounter Note — Chief Complaint, HPI, Vitals (BP/HR/Temp/RR/SpO2/Weight), Physical Exam,
   Assessment, Plan (`_clinical_note_fields()` in synthetic_data.py - the exact same shape
   medical-record uses)
5. Itemized Charges Table — CPT code, description, units, charge per line
5a. Scenario Details Section — same 13-scenario coverage as medical-record (reused across
   every packet) — see references/test-scenarios.md
6. Summary Box — Total charges, adjustments, amount paid, balance due
7. Payment Instructions and Due Date

## Financial Rules
- Line items: 1-5 CPT codes
- Adjustment: 5% to 30% contractual reduction (randomized per bill, not a fixed rate)
- Balance due = total - adjustments - amount_paid
- Amount paid defaults to 0.00

## Synthetic Data Rules
- Account number: ACC + 8 digits
- Charges per CPT: $150 to $2,500
