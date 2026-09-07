# CMS-1500 Field Glossary

## NUCC Box Mappings
- `box_1a`: Insured's ID Number (`^INS\d{9}$`)
- `box_2`: Patient's Name (Last, First, Middle)
- `box_3`: Patient Birth Date (`MM/DD/YYYY`) & Sex (`M|F`)
- `box_4`: Insured's Name
- `box_5`: Patient Address (Street, City, State, Zip)
- `box_6`: Patient Relationship to Insured (`Self|Spouse|Child|Other`)
- `box_21`: Diagnosis Codes A-L (`ICD-10-CM`)
- `box_24a_j`: Service Lines (DOS, POS, CPT Code, Diagnosis Pointer, Line Charge, Units, NPI)
- `box_28`: Total Charge (`Currency`)
- `box_29`: Amount Paid (`Currency`)
- `box_31`: Physician Signature on File & Date
- `box_33a`: Billing Provider NPI (`^\d{10}$`)
