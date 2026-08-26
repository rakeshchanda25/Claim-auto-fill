# Discharge Summary Field Glossary

## Patient & Encounter Metadata
- `patient_name`: Full Name (`String`)
- `dob`: Date of Birth (`Date`, `MM/DD/YYYY`)
- `gender`: Gender (`String`)
- `mrn`: Medical Record Number (`^\d{7}$`)
- `admission_date`: Hospital Admission Date (`Date`, `MM/DD/YYYY`)
- `discharge_date`: Hospital Discharge Date (`Date`, `MM/DD/YYYY`)
- `length_of_stay`: Inpatient Days (`Integer`, 1 to 30)
- `drg_code`: Diagnosis Related Group (`^\d{3}$`)

## Clinical Content
- `admission_diagnosis`: Initial admitting diagnosis (`Text`)
- `discharge_diagnosis`: Final discharge diagnosis (`Text` + ICD-10 list)
- `hospital_course`: Narrative summary of inpatient care (`Text`)
- `discharge_condition`: Condition status (`Enum: Stable|Improved|Good|Guarded`)
- `medications_at_discharge`: List of `(Medication Name, Dose, Frequency)`
- `discharge_instructions`: Patient care instructions (`Text`)
- `follow_up`: Follow-up appointment instructions (`Text`)
- `physician_name`: Attending Physician Name & NPI
