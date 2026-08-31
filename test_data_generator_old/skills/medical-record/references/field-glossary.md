# Medical Record Field Glossary

## Patient Identification
- `patient_name`: Full legal name (`String`, `^[A-Z][a-z]+ [A-Z][a-z]+$`)
- `dob`: Date of Birth (`Date`, `MM/DD/YYYY`)
- `gender`: Gender (`Enum: Male|Female`)
- `mrn`: Medical Record Number (`String`, `^\d{7}$`)
- `insurance_id`: Primary Policy ID (`String`, `^INS\d{9}$`)
- `group_number`: Group Number (`String`, `^GRP\d{6}$`)

## Encounter Metadata
- `dos`: Date of Service (`Date`, `MM/DD/YYYY`)
- `hospital`: Facility / Medical Center (`String`)
- `physician_name`: Attending Physician (`String`, `^Dr\. [A-Z][a-z]+ [A-Z][a-z]+$`)
- `npi`: Provider NPI (`String`, `^\d{10}$`)
- `specialty`: Clinical Specialty (`String`)

## Clinical Sections
- `chief_complaint`: Primary symptom or reason for visit (`Text`)
- `hpi`: History of Present Illness (`Text`, SOAP HPI structure)
- `vitals`: Physical Vitals (`Object: bp, hr, temp, rr, spo2, weight`)
- `physical_exam`: Systematic physical findings (`Text`)
- `assessment`: Clinical diagnosis summary (`Text`)
- `diagnosis_codes`: Array of `(ICD-10 Code, Description)` pairs
- `procedure_codes`: Array of CPT-4 procedure codes (`^\d{5}$`)
- `plan`: Treatment plan and diagnostic orders (`Text`)
