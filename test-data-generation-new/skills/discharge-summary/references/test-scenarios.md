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

The "Reason for Discharge" checkboxes, visit counts, and transition plan are independent of
scenario (they model the home-health discharge process itself, not the underlying admission
type). DRG code and length-of-stay are computed (legacy fields) but not printed by the current
template.
