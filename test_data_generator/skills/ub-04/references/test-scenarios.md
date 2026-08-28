# UB-04 IDP Test Scenarios

- `hospital_admission`: Inpatient hospital stay - admission/discharge dates typically span
  1-5 days apart.
- `surgery`, `emergency_visit`, `outpatient_procedure`: same revenue-code structure and box
  layout as `hospital_admission` - the scenario currently affects only which ICD-10/CPT codes
  are drawn for `principal_diagnosis`/`principal_procedure_code`, not the bill's structure.

The 5 revenue-code lines (0110 Room & Board, 0250 Pharmacy, 0300 Laboratory, 0450 Emergency
Room, 0710 Recovery Room) and their charge amounts are the same set for every scenario - only
the charges are randomized per line. `total_charges` is always the exact sum of those 5 lines.
