# Demand Letter IDP Test Scenarios

- `general`: Pre-litigation settlement demand letter outlining auto-accident damages, medical bill sum, and general damages totaling $75,000.

## Scenario coverage

demand-letter only ever appears in the litigation packet (`ai_doc_generator/packets.py`), so
the only real scenario names it's called with are `slip_and_fall` / `medical_malpractice` /
`product_liability`. Each gets a dedicated "Related Facts" section (`scenario_facts_title` +
`scenario_facts`, from `synthetic_data.py`'s `_medical_scenario_facts()`) rendered between the
liability paragraph and the damages figures:
- `slip_and_fall`: mechanism of fall, ambulatory status post-fall, pre-existing condition aggravated.
- `medical_malpractice`: alleged deviation from standard of care, prior treating facility, second opinion obtained.
- `product_liability`: product involved, injury mechanism, product retained as evidence.

Any other scenario (including `general`) omits the section entirely rather than rendering an
empty heading.
