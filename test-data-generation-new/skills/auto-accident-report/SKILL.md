---
name: auto-accident-report
description: >
  Generate a state-agency "Employee Vehicle Accident Report" (Washington S.F. 97 style) for
  IDP testing - a state employee driving a state vehicle, up to 2 other vehicles, an "other
  property" section, injured-parties and witness tables, and a police-investigation section.
metadata:
  owner: idp-test-team
  version: "2"
  page-size: letter-portrait
  template: auto_accident_report
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Auto Accident Report Generation Skill

## Required Sections
1. Header — state seal, form number/revision, reporting-offices instructions, date/time of
   accident
2. State Employee — business address/phone/email, operator's license, whether the vehicle was
   being used on official state business
3. Vehicle No. 1 (the state vehicle) — license/year/make/body type, where located, passengers,
   estimated repair cost, prior-accident flag, owning agency, damage description, owner/
   equipment number, insurer
4. Other Vehicles (up to 2: `vehicle2`, `vehicle3`) — owner and driver name/address/phone/age,
   license numbers, vehicle make/year/body type, passengers, repair cost, damage description,
   insurance company, policy number
5. Other Property — what was damaged, repair cost, owner name/address/city/zip/phone
6. Injured Parties Table — name/address, extent of injury, age, which vehicle (1/2/3) or
   pedestrian
7. Witnesses Table — name, address, city, phone
8. Other — was it police-investigated, which division, was a citation issued and to whom, was
   a collision report (Form SF-97a) filed

Note: `employee` (the reporting state employee/driver) is the policyholder-equivalent identity;
keep it consistent with `vehicle1`'s described driver.

## Vehicle Generation Rules
- Year: 2010 to current year
- Makes: Toyota, Honda, Ford, Chevrolet, BMW, Tesla (vehicle 1) / Nissan, Hyundai, Jeep, Subaru,
  Mazda (vehicle 2)
- License Plate: 3 letters + 4 digits

## Scenario coverage
`vehicle3` and `other_property` are currently always left blank (a two-vehicle collision with
no other property damage is the modeled default) - do not assume every scenario populates a
third vehicle just because the section exists in the template.

Each of the 3 registered scenarios (rear_end_collision/intersection_accident/hit_and_run - the
only ones this doc type is ever called with) additionally renders a dedicated "Details" section
before the footer note (`scenario_facts_title` + `scenario_facts`, from `_auto_scenario_facts()`
in synthetic_data.py); see `references/test-scenarios.md`.

`vehicle1.damage_description`/`vehicle2.damage_description` (`_vehicle_damage_descriptions()`)
match the collision type - e.g. rear_end_collision gives the state vehicle rear-end damage and
the other vehicle front-end damage, not two independent random sentences.

## Legacy fields
`insured_name`, `vehicle_info`, `driver_name`, `other_vehicle`, `other_driver_name`,
`estimated_damage`, `at_fault`, `bodily_injury`, etc. are still generated (kept for
backward-compat) but the current template does not render any of them - see
`references/field-glossary.md` for what the template actually uses.

## Document composition
Like every doc type, this template is decomposed into named Jinja macros ("components") in
`renderers/templates/auto_accident_report.html`, assembled by `renderers/components.py`'s
`COMPONENT_COMPOSITION["auto-accident-report"]`. Unlike police-report (which has two structurally
different shapes depending on scenario), every registered scenario for this doc type resolves
to the SAME component list - a real state accident-report form doesn't restructure by scenario in the real
world, only its content does (see the scenario-specific data-generation notes above). The
mechanism exists uniformly across every doc type for architectural consistency, even where
it isn't exercised to produce different shapes.
