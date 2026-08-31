# Discharge Summary IDP Test Scenarios

- `hospital_admission`, `surgery`, `emergency_visit`, `outpatient_procedure`: all four currently
  produce the SAME report structure with independently randomized content - the scenario name
  affects only which ICD-10 code is drawn for `diagnosis`, not the document's structure. DRG
  code and length-of-stay are computed (legacy fields) but not printed by the current template.
