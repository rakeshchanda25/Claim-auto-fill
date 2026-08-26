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
