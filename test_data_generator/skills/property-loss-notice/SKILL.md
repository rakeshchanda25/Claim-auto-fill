---
name: property-loss-notice
description: >
  Generate property loss notice forms for IDP testing. Covers fire, water, theft, wind, and
  structural damage claims with insured, loss, and adjuster sections.
metadata:
  owner: idp-test-team
  version: "1"
  page-size: letter-portrait
  template: property_loss_notice
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Property Loss Notice Generation Skill

## Required Sections
1. Insurer Header — Company name
2. Insured Information — Name, policy number, phone
3. Loss Information — Loss date, location, cause of loss, property description
4. Estimated Loss Amount
5. Mortgage / Lienholder — Mortgagee name and loan number
6. Coverage Type — Dwelling / Contents / Both
7. Deductible Amount
8. Adjuster Assignment — Name and phone
9. Insured Signature Block

## Cause of Loss Values (match scenario)
- fire_damage → "Fire"
- water_damage → "Water / Flood"
- theft → "Theft / Burglary"
- wind_damage → "Wind / Storm"

## Financial Rules
- Estimated loss: $5,000 to $150,000
- Deductible: $500 to $5,000
- Mortgagee should be a bank name

## Loss Location
- Should be different from insured's mailing address
