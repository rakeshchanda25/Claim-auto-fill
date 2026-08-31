# UB-04 IDP Test Scenarios

- `hospital_admission`: Inpatient hospital stay - admission/discharge dates typically span
  1-5 days apart.
- `surgery`, `emergency_visit`, `outpatient_procedure`: same revenue-code structure and box
  layout as `hospital_admission` - the scenario currently affects only which ICD-10/CPT codes
  are drawn for `principal_diagnosis`/`principal_procedure_code`, not the bill's structure.

The 5 revenue-code lines (0110 Room & Board, 0250 Pharmacy, 0300 Laboratory, 0450 Emergency
Room, 0710 Recovery Room) and their charge amounts are the same set for every scenario - only
the charges are randomized per line. `total_charges` is always the exact sum of those 5 lines.

## Scenario coverage

Like CMS-1500, UB-04 is a fixed-layout federal form (CMS-1450) and can't grow a new section for
a scenario. The Remarks box (FL80) is populated with a one-line summary of the same facts the
medical-record family shows for that scenario (`synthetic_data.py`'s `_facts_line()` over
`_medical_scenario_facts()`) - e.g. `hospital_admission` prints "Admission Type: Emergency;
Length of Stay: 3 day(s); Attending Service: Hospitalist" in Remarks.
