# Auto Accident Report Field Glossary

- `insured_name`: Policyholder driver name
- `policy_number`: Auto policy ID (`^POL[A-Z0-9]{9}$`)
- `claim_number`: Auto insurance claim number (`^CLM\d{10}$`)
- `dob`: Driver Date of Birth (`MM/DD/YYYY`)
- `phone`: Contact phone number
- `accident_date`: Date accident occurred (`MM/DD/YYYY`)
- `accident_location`: Street/Intersection location of collision
- `police_report_number`: Police report ID (`^RPT\d{8}$`)
- `bodily_injury`: Injury flag indicator (`Yes|No`)
- `at_fault`: At fault determination indicator (`Yes|No|Disputed`)
- `airbags_deployed`: Airbag safety check (`Yes|No`)
- `vehicle_info`: Vehicle metadata including `year`, `make`, `model`, `vin` (`^[A-Z0-9]{17}$`), and `license_plate` (`^[A-Z]{3}\d{4}$`)
- `damage_description`: Visual description of vehicle damage locations
