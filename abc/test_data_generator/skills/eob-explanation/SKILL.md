---
name: eob-explanation
description: >
  Generate a full multi-column claims-table Explanation of Benefits for IDP testing - one row
  per service line (Charges / Provider Responsibility / Allowed / Patient Non-covered / Paid
  by Other Ins / Deductible / Co-pay / Co-Insurance / Paid / Amount You Owe), a totals row, a
  notes legend, and a Patient Benefit Summary tracking deductible and out-of-pocket progress.
metadata:
  owner: idp-test-team
  version: "2"
  page-size: letter-landscape
  template: eob_explanation
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# EOB Generation Skill

## Required Fields
- Claim Information — Subscriber Name, Patient Name, claim reference number/date
- Claim Meta — Claim Number, Patient ID, Patient Control Number, Group Number, Group Name,
  Provider
- `claims`: list of per-line dicts (see Financial Calculation Rules below) - each line's
  columns are reconciled so they foot to `totals`, which is itself a column-wise sum of
  `claims` (never state a totals row that doesn't match the itemized lines above it)
- `notes`: list of `{code, description}` referenced by a line's `notes_id`
- Patient Benefit Summary — benefit period, deductible satisfied/limit, out-of-pocket
  applied/limit

## Financial Calculation Rules (adjudication order: deductible, then co-pay, then coinsurance)
Per claim line:
- `allowed_amount` = `charges` × a rate between 0.60 and 0.90 (contractual reduction)
- `provider_responsibility` = `charges` − `allowed_amount`
- `patient_noncovered`: usually `0`, occasionally 5% of `allowed_amount` (non-covered service)
- `paid_by_other_ins`: always `0` - no coordination-of-benefits is modeled
- `deductible`: drawn down from one claim-level `deductible_limit` (one of $250/$500/$1000/
  $1500), applied to the EARLIEST lines first until exhausted
- `copay`: a single flat amount, charged on the FIRST line only (typical of an office-visit
  EOB - copay is per-visit, not per-CPT-line)
- `coinsurance` = remaining covered amount after deductible/copay × one claim-level
  coinsurance rate (0.10-0.30)
- `paid_amount` = whatever is left after non-covered/deductible/copay/coinsurance are
  subtracted from `allowed_amount`
- `amount_you_owe` = `patient_noncovered` + `deductible` + `copay` + `coinsurance`

Every column of `totals` must equal `sum(claims[*][that column])` exactly - compute totals by
summing the constructed lines, never by an independent formula.

## Patient Benefit Summary
- `deductible_satisfied` = `deductible_limit` − whatever remained undrawn after all lines
- `oop_applied`: this claim's own `totals.amount_you_owe` (no other-claims history is modeled,
  so do not imply a larger year-to-date figure)
- `oop_limit`: one of $3,000 / $5,000 / $8,000

## Scenario coverage
Reused by two packets - called with 6 real scenario names (litigation's slip_and_fall/
medical_malpractice/product_liability, pharmacy's chronic_medication/specialty_drug/
compounded_medication), each rendering a scenario-specific note box above the Patient Benefit
Summary; see `references/test-scenarios.md`. The claims-table financials above are not
scenario-driven.

## Legacy fields
`eob_lines`, `billed_amount`, `allowed_amount`, `plan_paid`, `paid_amount`,
`patient_responsibility`, `deductible_applied`, `copay`, `coinsurance`, `denial_reason` are
still generated (kept for backward-compat, an earlier single-ratio version of this document
used them) but the current template does not render any of them.

## Document composition
Like every doc type, this template is decomposed into named Jinja macros ("components") in
`renderers/templates/eob_explanation.html`, assembled by `renderers/components.py`'s
`COMPONENT_COMPOSITION["eob-explanation"]`. Unlike police-report (which has two structurally
different shapes depending on scenario), every registered scenario for this doc type resolves
to the SAME component list - a real explanation of benefits doesn't restructure by scenario in the real
world, only its content does (see the scenario-specific data-generation notes above). The
mechanism exists uniformly across every doc type for architectural consistency, even where
it isn't exercised to produce different shapes.
