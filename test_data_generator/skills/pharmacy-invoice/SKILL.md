---
name: pharmacy-invoice
description: >
  Generate pharmacy invoices for prescription drug claims for IDP testing. Covers retail,
  mail-order, and specialty pharmacy transactions with NDC codes and billing details.
metadata:
  owner: idp-test-team
  version: "1"
  page-size: letter-portrait
  template: pharmacy_invoice
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Pharmacy Invoice Generation Skill

## Required Sections
1. Pharmacy Header — Name, address, NPI
2. Invoice Header — Rx number, fill date
3. Patient Information — Name, DOB, Insurance ID, Group Number, Insurer, Claim Number
4. Prescription Details — Drug name, NDC code, form, quantity, days supply
5. Prescriber — Name, NPI, DEA number
6. Charges Table — Drug charge, dispensing fee, copay, insurance billed
7. Totals Summary Box

## NDC Code Format
- 11 digits: 5-4-2 labeler-product-package (e.g., 00093-7278-98)

## Financial Rules
- Unit price: $1.50 to $25.00
- Dispensing fee: $2.00 to $5.00
- Copay: $5.00 to $50.00
- Insurance billed = (unit_price × qty + dispensing_fee) - copay

## Quantity Standards
- Short course: 10-14 days
- Monthly supply: 30 days
- 90-day supply: 90 days (mail-order)
