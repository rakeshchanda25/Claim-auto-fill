# CMS-1500 IDP Test Scenarios

- `outpatient_procedure`: 3 service line items, Place of Service 11 (Office), CPT 99213, 93000, 85025.
- `emergency_visit`: Place of Service 23 (ER), CPT 99284, 71046.

## Scenario coverage

cms-1500 is a fixed-layout federal form (real numbered boxes) - it can't grow a new section for
a scenario without breaking that layout, unlike the free-form doc types. Instead, Box 19
("Additional Claim Information") is populated with a one-line summary of the same facts the
medical-record family shows for that scenario (via `synthetic_data.py`'s `_facts_line()` over
`_medical_scenario_facts()`) - e.g. `surgery` prints "Anesthesia Type: General; OR Time: 120
minutes; ASA Class: II" in Box 19. `auto_accident_related`/`auto_accident_state` (Box 10a/10b)
are also scenario-driven: YES only for `rear_end_collision`/`intersection_accident`/
`slip_and_fall`.
