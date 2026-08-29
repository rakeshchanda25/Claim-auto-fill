---
name: property-loss-notice
description: >
  Generate property loss notice forms for IDP testing. Covers fire, water, theft, wind, and
  structural damage claims with insured, loss, and adjuster sections. Each scenario also adds
  its own structural "Details" section - see "Scenario-Specific Details Section" below.
metadata:
  owner: idp-test-team
  version: "2"
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
5. Scenario-Specific Details Section (present for fire_damage/water_damage/theft/wind_damage,
   omitted for any other scenario) — see below
6. Mortgage / Lienholder — Mortgagee name and loan number
7. Coverage Type — Dwelling / Contents / Both
8. Deductible Amount
9. Adjuster Assignment — Name and phone
10. Insured Signature Block

## Scenario-Specific Details Section
Not just a different `cause_of_loss` string - each of these 4 scenarios adds a genuinely
different section (`scenario_facts_title` + `scenario_facts` list), computed by
`_property_scenario_facts()` in synthetic_data.py:
- `fire_damage` → "Fire Details": fire department notified, responding department, fire
  report #, suspected cause of ignition
- `water_damage` → "Water Details": water source, mitigation company, moisture reading, mold
  remediation flag
- `theft` → "Theft Details": police report #, evidence of forced entry, items stolen,
  recovery status
- `wind_damage` → "Storm Details": storm/event name, peak wind gust, NWS advisory #,
  tree/debris damage flag

Any other scenario (e.g. `general`) gets `scenario_facts = []` and the section is omitted
entirely by the template's own `{% if scenario_facts %}` guard - never render an empty
heading. Adding a NEW scenario to one of these 4 families, or a whole new family, only needs
a new branch in `_property_scenario_facts()` - the template never needs to change.

## Cause of Loss Values
`cause_of_loss` is `scenario.replace("_", " ").title()` - e.g. `fire_damage` → "Fire Damage",
`wind_damage` → "Wind Damage" (title-cased, underscores become spaces; not a hand-picked
label per scenario).

## Financial Rules
- Estimated loss: $5,000 to $150,000
- Deductible: $500 to $5,000
- Mortgagee should be a bank name

## Loss Location
- Should be different from insured's mailing address

## Document composition
Like every doc type, this template is decomposed into named Jinja macros ("components") in
`renderers/templates/property_loss_notice.html`, assembled by `renderers/components.py`'s
`COMPONENT_COMPOSITION["property-loss-notice"]`. Unlike police-report (which has two structurally
different shapes depending on scenario), every registered scenario for this doc type resolves
to the SAME component list - a real property loss notice doesn't restructure by scenario in the real
world, only its content does (see the scenario-specific data-generation notes above). The
mechanism exists uniformly across every doc type for architectural consistency, even where
it isn't exercised to produce different shapes.
