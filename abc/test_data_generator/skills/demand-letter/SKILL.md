---
name: demand-letter
description: >
  Generate legal demand letters for insurance claims settlement. Covers personal injury,
  auto accident, slip-and-fall, and medical malpractice pre-litigation demands.
metadata:
  owner: idp-test-team
  version: "1"
  page-size: letter-portrait
  template: demand_letter
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Demand Letter Generation Skill

## Required Sections
1. Attorney/Firm Letterhead — Firm name, address, state bar number
2. Date of Letter
3. Recipient — Insurer name and Claims Department
4. RE Line — "DEMAND FOR SETTLEMENT" with claimant vs. respondent, incident date
5. Salutation and Opening Paragraph
6. Facts Summary — 4-6 sentences describing the incident and injuries
6a. Scenario Details Section — present for slip_and_fall/medical_malpractice/product_liability,
   omitted for any other scenario — see "Scenario coverage" below
7. Damages Breakdown — Special damages (medical/economic) and General damages (pain/suffering)
8. Total Demand Amount — Prominently boxed
9. Settlement Deadline — 30 days from letter date
10. Closing and Attorney Signature

## Financial Rules
- Demand amount: $25,000 to $500,000
- Special damages: 25% to 55% of demand (randomized per letter, not a fixed split)
- General damages: remainder of demand after special damages
- Settlement deadline: letter date + 30 days

## Scenario coverage
Only ever called with slip_and_fall/medical_malpractice/product_liability (the litigation
packet's scenarios) - each gets its own facts section between the liability paragraph and the
damages figures; see `references/test-scenarios.md`. `facts_summary` (the opening narrative
paragraph) reuses litigation-document's `_litigation_narrative()`, so it recounts the same
scenario-specific mechanism rather than generic Faker prose.

## Tone and Format
- Formal legal prose, Times New Roman 11pt
- Double-spaced body paragraphs
- State "reserves all rights" to litigate if demand rejected

## Document composition
Like every doc type, this template is decomposed into named Jinja macros ("components") in
`renderers/templates/demand_letter.html`, assembled by `renderers/components.py`'s
`COMPONENT_COMPOSITION["demand-letter"]`. Unlike police-report (which has two structurally
different shapes depending on scenario), every registered scenario for this doc type resolves
to the SAME component list - a real attorney demand letter doesn't restructure by scenario in the real
world, only its content does (see the scenario-specific data-generation notes above). The
mechanism exists uniformly across every doc type for architectural consistency, even where
it isn't exercised to produce different shapes.
