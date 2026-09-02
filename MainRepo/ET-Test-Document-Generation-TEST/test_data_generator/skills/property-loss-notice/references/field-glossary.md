# Property Loss Notice Field Glossary

- `insured_name`: Named policyholder
- `policy_number`: Property policy number (`^POL[A-Z0-9]{9}$`)
- `phone`: Insured's contact phone number
- `loss_date`: Date incident occurred (`MM/DD/YYYY`)
- `coverage_type`: Insured interest (e.g. Dwelling, Contents, Both)
- `deductible`: Policy deductible amount
- `loss_location`: Property address where damage occurred
- `cause_of_loss`: Peril (e.g. Fire, Water, Wind, Theft)
- `property_description`: Description of damaged property
- `estimated_loss`: Initial damage estimate cost
- `mortgagee_name`: Lender holding mortgage on property
- `loan_number`: Mortgage loan number (`^LN\d{10}$`)
- `adjuster_name`: Assigned claims adjuster
- `adjuster_phone`: Adjuster contact number
- `scenario_facts_title`: section heading (`"Fire Details"` etc.), `""` when the scenario has
  no facts defined
- `scenario_facts`: list of `{label, value}` - see "Scenario-Specific Details Section" in
  SKILL.md for what each scenario supplies
