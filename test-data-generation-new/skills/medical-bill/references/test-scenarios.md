# Medical Bill IDP Test Scenarios

- `general`: Outpatient visit bill with 3 CPT items.
- `emergency_visit`: Emergency room facility bill with high line charges.

## Scenario coverage

medical-bill is reused by every packet, so it can be called with the same 13 scenario names as
medical-record (see that skill's test-scenarios.md). Each gets the same dedicated facts section
(`scenario_facts_title` + `scenario_facts`, from `synthetic_data.py`'s
`_medical_scenario_facts()`) rendered before the signature block. The itemized charges/
adjustments/balance math is NOT scenario-driven - only this section is.
