# EOB IDP Test Scenarios

- `general`: produces the claims-table structure with independently randomized allowed/
  coinsurance rates and deductible - see "Financial Calculation Rules" in SKILL.md for the
  actual ranges (not a fixed 80%/$20 copay).

## Scenario coverage

eob-explanation is reused by two packets and can be called with 6 real scenario names:
litigation (`slip_and_fall` / `medical_malpractice` / `product_liability`) and pharmacy
(`chronic_medication` / `specialty_drug` / `compounded_medication`). Each renders a
scenario-specific note box (`scenario_facts_title` + `scenario_facts`, from
`synthetic_data.py`'s `_medical_scenario_facts()`) above the Patient Benefit Summary, reusing
the same content the medical-record family shows for that scenario name (e.g. `specialty_drug`
prints prior-authorization status and dispensing pharmacy). `general` and any other unmapped
scenario omit the box entirely. The claims-table financials themselves (allowed/paid rates,
deductible waterfall) are NOT scenario-driven - only this note box is.
