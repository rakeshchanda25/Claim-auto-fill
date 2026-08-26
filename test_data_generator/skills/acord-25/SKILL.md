---
name: acord-25
description: >
  Generate ACORD 25 (2016/03) Certificate of Liability Insurance for IDP testing - CGL,
  automobile liability, umbrella, and workers compensation coverages with producer, insured,
  and certificate holder sections. Rendered through the placeholder-then-fill pipeline (see
  render_document_to_pdf), so the output is a genuine fillable AcroForm PDF.
metadata:
  owner: idp-test-team
  version: "2"
  page-size: letter-portrait
  template: acord_25
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# ACORD 25 Generation Skill

## Sections covered by the template
1. Producer — agency name, address, phone, email
2. Insured — company name and address
3. Insurer(s) Affording Coverage — Insurer A name + NAIC number
4. Coverages table (4 fixed rows, each with its own policy number/dates/limits):
   - A. Commercial General Liability: Each Occurrence, Damage to Rented Premises, Med Exp,
     Personal & Adv Injury, General Aggregate, Products-Comp/Op Agg
   - A. Automobile Liability: Combined Single Limit
   - A. Umbrella Liab (Occurrence): Each Occurrence, Aggregate
   - A. Workers Compensation & Employers' Liability: E.L. Each Accident, E.L. Disease-Ea
     Employee, E.L. Disease-Policy Limit
5. Description of Operations / Locations / Vehicles
6. Certificate Holder — name and address
7. Cancellation clause (fixed boilerplate text)
8. Authorized Representative

## Coverage Limits (standard defaults used across all generated certificates)
- CGL Each Occurrence: $1,000,000 · General Aggregate: $2,000,000
- Auto Combined Single Limit: $1,000,000
- Umbrella Each Occurrence / Aggregate: $2,000,000
- Workers Comp E.L.: $500,000 (each accident / disease-employee / disease-policy)

## Synthetic Data Rules
- Insured and certificate holder should be different company names (Faker.company)
- Policy numbers are prefixed by coverage type: GL/CA/UMB/WC + 8 digits
- All four coverage lines share the same effective/expiration dates on a given certificate
