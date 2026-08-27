# EOB Field Glossary

- `member_id`: Insured Member ID (`^INS\d{9}$`)
- `claim_number`: Claim Number (`^CLM\d{10}$`)
- `dos`: Date of Service (`MM/DD/YYYY`)
- `provider_name`: Rendering Physician/Hospital Name
- `billed_amount`: Gross Billed Charge (`Currency`)
- `allowed_amount`: Contractual Allowed Charge (`Currency`, 60% to 90% of Billed, randomized)
- `plan_paid`: Net Insurance Payment (`Currency`, 70% to 95% of Allowed, randomized)
- `patient_responsibility`: Member Balance Due (`Currency`)
- `deductible_applied`: Deductible Amount (`Currency`)
- `copay`: Fixed Copay Amount (`Currency`)
- `coinsurance`: Coinsurance Share (`Currency`)
- `denial_reason`: Adjustment Reason Code & Description (`CO-97`, `PR-1`, `CO-45`, `OA-23`)
