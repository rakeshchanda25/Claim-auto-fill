# Discharge Summary IDP Test Scenarios

discharge-summary only appears in the medical packet, so it is always called with one of
`hospital_admission` / `surgery` / `emergency_visit` / `outpatient_procedure`.

## Scenario coverage

Each of the 4 scenarios gets a dedicated facts section (`scenario_facts_title` +
`scenario_facts`, from `synthetic_data.py`'s `_medical_scenario_facts()`) rendered as its own
boxed section before the clinician-signature table:
- `hospital_admission`: admission type, length of stay, attending service.
- `surgery`: anesthesia type, OR time, ASA class.
- `emergency_visit`: triage level (ESI), arrival mode, ED disposition.
- `outpatient_procedure`: facility type, same-day discharge, pre-procedure clearance.

The "Reason for Discharge" checkboxes and visit counts are independent of scenario (they model
the home-health discharge process itself, not the underlying admission type). DRG code and
length-of-stay are computed (legacy fields) but not printed by the current template.

## Summary of Care narrative

`summary_of_care_plan`/`goals_achieved_summary`/`care_plan_notes`/`assessment_notes`/
`discharge_instructions` (from `synthetic_data.py`'s `_discharge_narrative()`) are scenario-
driven for all 4 registered scenarios. Before this, `synthetic_data.py` never set
`summary_of_care_plan`/`goals_achieved_summary` at all, so `discharge_summary.html`'s own Jinja
`| default(...)` fallback printed the SAME hardcoded pregnancy/antepartum boilerplate on every
single discharge summary regardless of scenario - the worst instance of the static-content bug
in this app, since it wasn't even scenario-blind Faker filler, just literally identical text.
Any other scenario (`general`) leaves these keys unset, so the template's own default text
still applies unchanged.
