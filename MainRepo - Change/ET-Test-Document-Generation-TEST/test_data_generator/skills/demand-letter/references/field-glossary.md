# Demand Letter Field Glossary

- `claimant_name`: Injured Party Name
- `claimant_attorney`: Law Offices / Attorney Name
- `bar_number`: State Bar ID (`^BAR\d{6}$`)
- `insurer_name`: Respondent Insurance Carrier
- `claim_number`: Insurance Claim Number
- `incident_date`: Loss / Injury Date (`MM/DD/YYYY`)
- `demand_amount`: Total Demand Amount (`$25,000` to `$500,000`)
- `special_damages`: Economic Loss / Medical Bills (25% to 55% of demand_amount, randomized)
- `general_damages`: Pain and Suffering (demand_amount minus special_damages)
- `settlement_deadline`: Response Expiration Date (`MM/DD/YYYY`)
- `facts_summary`: Narrative of liability and injury
