# Pharmacy Invoice Field Glossary

- `rx_number`: Prescription fill identifier (`^RX\d{8}$`)
- `fill_date`: Date the prescription was prepared (`MM/DD/YYYY`)
- `drug_name`: Brand or generic name of drug
- `ndc_code`: National Drug Code (`^\d{5}-\d{4}-\d{2}$`)
- `form`: Dosage form (e.g. tablet, capsule)
- `quantity`: Amount dispensed (e.g. 30, 60, 90)
- `days_supply`: Intended duration in days
- `unit_price`: Base price per unit
- `total_charge`: Calculated drug cost before copay
- `dispensing_fee`: Professional service fee
- `copay`: Patient share paid at counter
- `pharmacy_name`: Dispensing pharmacy brand
- `pharmacy_npi`: Pharmacy NPI identifier (`^\d{10}$`)
- `prescriber_name`: Ordering provider name
- `prescriber_npi`: Prescriber NPI (`^\d{10}$`)
