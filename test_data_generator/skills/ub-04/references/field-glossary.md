# UB-04 Field Glossary

- `provider_name`: Hospital / Institution Name
- `type_of_bill`: 3-digit Code (`111` Inpatient, `131` Outpatient)
- `statement_from`: Billing Period Start (`MM/DD/YYYY`)
- `statement_through`: Billing Period End (`MM/DD/YYYY`)
- `patient_name`: Patient Name
- `drg_code`: Diagnosis Related Group (`^\d{3}$`)
- `revenue_codes`: Array of `(Code, Description, HCPCS, Service Date, Units, Charges)`
- `total_charges`: Total Inpatient Amount (`Currency`)
- `payer_name`: Primary Insurer
- `principal_diagnosis`: Primary ICD-10 Diagnosis Code
