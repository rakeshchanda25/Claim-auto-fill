# EOB Field Glossary

- `document_title`: has a template default ("Explanation of Health Care Benefits")
- `subscriber_name`, `patient_name`: claim info box
- `claim_ref_number`, `claim_ref_date`: top-right reference block
- `disclaimer_text`: "THIS IS NOT A BILL" paragraph (has a template default)
- `claim_number`, `patient_id`, `patient_control_number`, `group_number`, `group_name`,
  `provider_name`: claim meta row
- `claims`: list of per-line dicts - `dates_of_service`, `description`, `charges`,
  `provider_responsibility`, `allowed_amount`, `patient_noncovered`, `paid_by_other_ins`,
  `deductible`, `copay`, `coinsurance`, `paid_amount`, `amount_you_owe`, `notes_id`
- `totals`: dict with the SAME keys as a `claims` line (minus `dates_of_service`/`description`/
  `notes_id`) - each value is `sum(claims[*][key])`
- `notes`: list of `{code, description}`
- `benefit_patient_name`: defaults to `patient_name` if omitted
- `benefit_period_start`, `benefit_period_end`: `MM/DD/YYYY`
- `deductible_satisfied`, `deductible_limit`, `oop_applied`, `oop_limit`: Patient Benefit
  Summary numbers - see "Patient Benefit Summary" in SKILL.md
- `benefit_summary_note`: closing paragraph (has a template default)

## Legacy fields
`member_id`, `billed_amount`, `allowed_amount`, `plan_paid`, `patient_responsibility`,
`deductible_applied`, `copay`, `coinsurance`, `denial_reason`, `network_status`,
`processed_date`, `check_number`, `reason_code_legend`, `eob_lines` are still generated (kept
for backward-compat) but the current template does not render any of them.
