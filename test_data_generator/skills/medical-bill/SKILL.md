---
name: medical-bill
description: >
  Generate itemized medical billing statements for IDP testing. Covers CPT-coded line items,
  adjustments, and balance-due summary for outpatient and inpatient services.
metadata:
  owner: idp-test-team
  version: "1"
  page-size: letter-portrait
  template: medical_bill
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Medical Bill Generation Skill

## Required Sections
1. Provider Header — Hospital name, address, phone
2. Patient Statement Header — Account number, statement date, due date
3. Patient Information — Name, DOB, service date, insurance, claim number
4. Itemized Charges Table — CPT code, description, units, charge per line
5. Summary Box — Total charges, adjustments, amount paid, balance due
6. Payment Instructions and Due Date

## Financial Rules
- Line items: 1-5 CPT codes
- Adjustment: ~15% contractual reduction
- Balance due = total - adjustments - amount_paid
- Amount paid defaults to 0.00

## Synthetic Data Rules
- Account number: ACC + 8 digits
- Charges per CPT: $150 to $2,500
