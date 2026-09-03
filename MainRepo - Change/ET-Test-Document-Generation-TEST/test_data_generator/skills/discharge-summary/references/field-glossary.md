# Discharge Summary Field Glossary

- `patient_name`, `dob`: patient header
- `org_name`: home-health agency name
- `patient_address`, `patient_address_line2`, `city_state`, `zip_code`: patient address, split
  into the pieces the template prints (NOT a single `address` dict)
- `date_of_admission`, `date_of_discharge`, `date_of_first_visit`: `MM/DD/YYYY`
- `physician_name`: printed physician name
- `reason`: dict - see "`reason` field" in SKILL.md
- `reason_comments`: list of ruled-line strings (only non-empty when `reason` is not
  `goals_achieved`)
- `diagnosis`: primary diagnosis text
- `summary_of_care_plan`, `goals_achieved_summary`: narrative paragraphs (have template
  defaults - only override for variety)
- `care_plan_notes`: list of ruled-line strings
- `assessment_of_patient_condition`: `Stable` / `Improved` / `Guarded`
- `assessment_notes`: list of ruled-line strings
- `last_visit_made`: `MM/DD/YYYY`
- `number_of_visits`: string, 3-14
- `transition_plan`: list of ruled-line strings (empty when `reason` is `goals_achieved` or
  `expired` - nothing to transition)
- `discharge_instructions`: paragraph (has a template default)
- `discharge_instruction_notes`: list of ruled-line strings
- `clinician_signature`, `signature_date`: signature block

## Legacy fields
`attending_physician`, `admission_diagnosis`, `discharge_diagnosis`, `hospital_course`,
`discharge_condition`, `medications_at_discharge`, `drg_code`, `length_of_stay`, `follow_up`
are still generated (kept for backward-compat, an earlier inpatient-hospital version of this
document used them) but the current template does not render any of them.
