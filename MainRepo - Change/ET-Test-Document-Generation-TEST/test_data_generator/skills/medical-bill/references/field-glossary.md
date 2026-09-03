# Medical Bill Field Glossary

- `account_number`: Billing Account ID (`^ACC\d{8}$`)
- `statement_date`: Statement Date (`MM/DD/YYYY`)
- `due_date`: Payment Due Date (`MM/DD/YYYY`)
- `patient_name`: Patient Name
- `service_date`: Encounter Date (`MM/DD/YYYY`)
- `line_items`: Array of CPT items (`cpt, description, units, charge`)
- `total_amount`: Gross Billed (`Currency`)
- `adjustments`: Insurance Discount (`Currency`, 5% to 30% of total_amount, randomized)
- `amount_paid`: Previous Payments (`Currency`)
- `balance`: Net Balance Due (`Currency`)
- `chief_complaint`, `hpi`, `physical_exam`, `assessment`, `plan`: encounter-note narrative text
- `vitals`: dict - `bp`, `hr`, `temp`, `rr`, `spo2`, `weight`, `height`
