---
name: auto-accident-report
description: >
  Generate auto accident claim reports for IDP testing. Covers collision, hit-and-run,
  and intersection accidents with vehicle details, bodily injury, and damage descriptions.
metadata:
  owner: idp-test-team
  version: "1"
  page-size: letter-portrait
  template: auto_accident_report
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Auto Accident Report Generation Skill

## Required Sections
1. Insurer/Policy Header — Insurer, Claim #, Policy #
2. Policyholder Information — Insured Name, DOB, Phone
3. Accident Details — Date, time, location, police report #, bodily injury, at-fault, airbags
   deployed, vehicle towed
4. Insured's Vehicle — Year, Make, Model, VIN, License Plate, Driver Name, Driver License Number
5. Other Vehicle — Year, Make, Model, License Plate, Other Driver Name, Other Driver's Insurer
   and Policy Number (the other party is never the same insurer/policy as the insured)
6. Damage Description — 1-2 sentences, plus Estimated Damage amount
7. Witnesses Table — Name and phone
8. Claimant Signature Block

Note: `insured_name` is the policyholder filing the claim - keep it consistent with
`driver_name` unless the scenario explicitly involves someone else driving the insured vehicle.

## Vehicle Generation Rules
- Year: 2010 to current year
- Makes: Toyota, Honda, Ford, Chevrolet, BMW, Tesla, Nissan, Hyundai
- VIN: 17 alphanumeric characters (uppercase A-Z, 0-9, no I/O/Q)
- License Plate: 3 letters + 4 digits

## Accident Location Format
- Full street address + city + state abbreviation

## At Fault Values
- "Yes", "No", or "Disputed"
