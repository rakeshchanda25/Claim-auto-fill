# Medical Record IDP Test Scenarios

## Benchmark Test Cases

### Scenario 1: Emergency Visit (`emergency_visit`)
- Chief Complaint: Acute chest pain, shortness of breath
- Diagnoses: `R07.9` (Chest pain, unspecified), `I21.9` (Acute myocardial infarction)
- Procedures: CPT `99284` (ED Visit Level 4), CPT `93000` (Electrocardiogram)
- Expected IDP Extraction: Confirm critical triage diagnosis `R07.9` extracted from table.

### Scenario 2: Orthopedic Injury / Slip and Fall (`slip_and_fall`)
- Chief Complaint: Right wrist deformity after tripping on wet floor
- Diagnoses: `S52.501A` (Fracture of lower end of right radius)
- Procedures: CPT `25600` (Closed treatment of distal radial fracture)
- Expected IDP Extraction: Ensure lateralization ("right radius") is captured correctly.

### Scenario 3: Motor Vehicle Collision (`rear_end_collision`)
- Chief Complaint: Neck stiffness, headache following rear-end impact
- Diagnoses: `S14.0XXA` (Concussion of cervical spinal cord), `M54.2` (Cervicalgia)
- Expected IDP Extraction: Validate multi-diagnosis extraction across 2-column ICD table.

## Scenario coverage

medical-record is reused by every packet (`ai_doc_generator/packets.py`), so it can be called
with 13 different scenario names: the 4 "medical" ones (`hospital_admission`/`surgery`/
`emergency_visit`/`outpatient_procedure`) plus every other packet's own scenario names
(`rear_end_collision`/`intersection_accident`/`hit_and_run`, `slip_and_fall`/
`medical_malpractice`/`product_liability`, `chronic_medication`/`specialty_drug`/
`compounded_medication`). All 13 get a dedicated facts section (`scenario_facts_title` +
`scenario_facts`, from `synthetic_data.py`'s `_medical_scenario_facts()`) rendered above the
signature block - e.g. `hospital_admission` prints admission type/length of stay/attending
service, `slip_and_fall` prints fall mechanism/ambulatory status/pre-existing condition. The
3 auto-collision scenarios intentionally share one section heading ("Mechanism of Injury")
with different fields underneath, since a chart note groups them under the same clinical
heading. This same function/section is also wired into medical-bill, discharge-summary, and
(via the fixed-form free-text boxes instead of a new section) cms-1500 and ub-04 - see those
skills' own test-scenarios.md.

`chief_complaint`/`hpi`/`physical_exam`/`plan` (the actual clinical-note prose, distinct from
the scenario_facts section above) are likewise scenario-driven, from `_CLINICAL_NOTE_TEXT` in
`synthetic_data.py`'s `_clinical_note_fields(scenario, icd_codes)` - all 13 scenario names get
real prose naming the mechanism/reason for the visit and referencing the actual diagnosis code
description generated for this document (not the same text for every scenario, and not Faker
Lorem-Ipsum filler). The benchmark examples above are illustrative targets for what a scenario's
content should evoke, not a literal string match against the generated text. `assessment` is
always the diagnosis code's description directly.
