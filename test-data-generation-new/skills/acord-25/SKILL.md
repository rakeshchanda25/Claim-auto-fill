---
name: acord-25
description: >
  Generate an ACORD 25 Certificate of Liability Insurance for IDP testing - CGL, automobile
  liability, umbrella, and workers compensation coverages, a full checkbox set for every
  coverage type, producer/insured/certificate-holder sections. Output is a plain
  (non-fillable) PDF - values are painted directly into the page content, not into AcroForm
  fields.
metadata:
  owner: idp-test-team
  version: "4"
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

## Checkbox fields
Every checkbox's ticked state is DECIDED IN PYTHON (`synthetic_data.py`'s `_mark()` helper) and
handed to the template as a plain `☑`/`☐` string field - the template only ever
plain-substitutes it (`{{ gl_occurrence_mark }}`), it never decides which glyph to show itself.
Keep new checkboxes the same way: compute the mark in Python, not with a template `{% if %}` -
it keeps every "which box is ticked" decision in one place (`_mark()`'s callers) instead of
scattered across template files. Each pair is mutually exclusive (exactly one glyph in the
pair is `☑`): GL claims basis (`gl_occurrence_mark`/`gl_claims_made_mark`), GL aggregate basis
(3-way: `gl_agg_policy_mark`/`gl_agg_project_mark`/`gl_agg_loc_mark`), auto liability type
(`auto_any_auto_mark` vs. the 4 granular marks), umbrella-vs-excess and its basis, deductible-
vs-retention, WC officer-excluded Y/N, WC statutory-vs-other.

## Coverage Limits (randomized per certificate from standard real-world tiers)
- CGL Each Occurrence / General Aggregate: one of $500K/$1M, $1M/$2M, $1M/$2M, $2M/$4M
  (sub-limits - damage to rented premises, med exp, personal & adv injury, products-comp/op
  agg - scale with the chosen tier, not independently random)
- Auto Combined Single Limit: $500,000 to $2,000,000
- Umbrella Each Occurrence / Aggregate (same value): $1,000,000 to $10,000,000
- Workers Comp E.L. (each accident / disease-ea-employee / disease-policy): $100,000 to
  $1,000,000, drawn from standard combos - never invent an in-between number
- Every certificate should land on a different tier than the last one you generated;
  don't default to $1,000,000/$2,000,000 out of habit

## Synthetic Data Rules
- Insured and certificate holder should be different company names (Faker.company)
- Policy numbers are prefixed by coverage type: GL/CA/UMB/WC + 8 digits
- All four coverage lines share the same effective/expiration dates on a given certificate

## Document composition
Like every doc type, this template is decomposed into named Jinja macros ("components") in
`renderers/templates/acord_25.html`, assembled by `renderers/components.py`'s
`COMPONENT_COMPOSITION["acord-25"]`. Unlike police-report (which has two structurally
different shapes depending on scenario), every registered scenario for this doc type resolves
to the SAME component list - a real certificate of insurance doesn't restructure by scenario in the real
world, only its content does (see the scenario-specific data-generation notes above). The
mechanism exists uniformly across every doc type for architectural consistency, even where
it isn't exercised to produce different shapes.
