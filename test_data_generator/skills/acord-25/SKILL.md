---
name: acord-25
description: >
  Generate ACORD 25 Certificate of Liability Insurance for IDP testing. Covers CGL, workers
  compensation, and umbrella coverages with producer, insured, and certificate holder sections.
metadata:
  owner: idp-test-team
  version: "1"
  page-size: letter-portrait
  template: acord_25
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# ACORD 25 Generation Skill

## Required Sections
1. Producer (Agency) — Name and address
2. Insured — Name and address (typically a business entity)
3. Coverages:
   - Commercial General Liability (occurrence form)
   - Workers Compensation & Employers Liability
   - Umbrella / Excess Liability (optional)
4. Policy Numbers — one per coverage line
5. Effective and Expiration Dates
6. Limits — Each Occurrence, General Aggregate, EL per Employee
7. Certificate Holder — Name and address
8. Authorized Representative signature line

## Coverage Limits
- CGL Each Occurrence: $1,000,000
- CGL General Aggregate: $2,000,000
- Workers Comp EL: $500,000
- Umbrella: $2,000,000

## Synthetic Data Rules
- Insured should be a company name (Faker.company)
- Policy Number: POL + 9 alphanumeric characters
- Certificate holder is a different company from insured
