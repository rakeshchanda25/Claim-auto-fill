---
name: discharge-summary
description: >
  Generate a home-health/skilled-nursing discharge summary for IDP testing - Reason for
  Discharge checkboxes (goals achieved / admitted to acute care / ECF-SNF / transferred /
  refused care / expired / other), Summary of Care, Status of Discharge with visit counts,
  Plan for Transition, and discharge instructions.
metadata:
  owner: idp-test-team
  version: "2"
  page-size: letter-portrait
  template: discharge_summary
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Discharge Summary Generation Skill

## Required Sections
1. Patient/Physician Header — Name, DOB, address, admission/discharge dates
2. Reason for Discharge — exactly ONE of 7 checkboxes ticked (see `reason` below), with
   comments only shown when the reason is not "goals achieved"
3. Summary of Care — diagnosis, date of first visit, summary of care plan, goals achieved/not
   achieved narrative, care-plan notes (ruled fill-in lines)
4. Status of Discharge — assessment of patient condition, last visit made, number of visits
5. Plan for Transition — ruled fill-in lines (blank when discharge was for goals-achieved or
   expired, since there is nothing to transition)
6. Summary of Patient Discharge Instructions
6a. Scenario Details Section — present for hospital_admission/surgery/emergency_visit/
   outpatient_procedure (the only scenarios this doc type is ever called with) — see
   references/test-scenarios.md
7. Clinician Signature and Date

## `reason` field
A dict with exactly one of these keys `True` (rest `False`): `goals_achieved`,
`admitted_acute_care`, `admitted_ecf_snf`, `transferred_other_service`, `refused_further_care`,
`expired`, `other`. Plus `expired_date` (only meaningful when `expired` is true) and
`other_detail` (only meaningful when `other` is true) - leave both `""` otherwise.
`goals_achieved` should be the most common outcome by far (~55%); `expired` should be rare (~2%).

## Synthetic Data Rules
- `date_of_first_visit` falls within a day of `date_of_admission`; `last_visit_made` falls
  within ~2 days before `date_of_discharge`
- `number_of_visits`: 3-14
- Ruled-line list fields (`reason_comments`, `care_plan_notes`, `assessment_notes`,
  `transition_plan`, `discharge_instruction_notes`) may be empty lists - the template pads
  blank ruled lines itself, do not pad them yourself

## Document composition
Like every doc type, this template is decomposed into named Jinja macros ("components") in
`renderers/templates/discharge_summary.html`, assembled by `renderers/components.py`'s
`COMPONENT_COMPOSITION["discharge-summary"]`. Unlike police-report (which has two structurally
different shapes depending on scenario), every registered scenario for this doc type resolves
to the SAME component list - a real home-health discharge summary doesn't restructure by scenario in the real
world, only its content does (see the scenario-specific data-generation notes above). The
mechanism exists uniformly across every doc type for architectural consistency, even where
it isn't exercised to produce different shapes.
