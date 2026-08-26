# Medical Bill Field Glossary

- `account_number`: Billing Account ID (`^ACC\d{8}$`)
- `statement_date`: Statement Date (`MM/DD/YYYY`)
- `due_date`: Payment Due Date (`MM/DD/YYYY`)
- `patient_name`: Patient Name
- `service_date`: Encounter Date (`MM/DD/YYYY`)
- `line_items`: Array of CPT items (`cpt, description, units, charge`)
- `total_amount`: Gross Billed (`Currency`)
- `adjustments`: Insurance Discount (`Currency`, ~15%)
- `amount_paid`: Previous Payments (`Currency`)
- `balance`: Net Balance Due (`Currency`)
