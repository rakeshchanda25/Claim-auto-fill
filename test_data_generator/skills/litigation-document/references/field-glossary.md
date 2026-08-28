# Litigation Document Field Glossary

- `plaintiff_name`: Initiating party name
- `defendant_name`: Opposing party name
- `case_number`: Court docket case number (`^CV-\d{4}-\d{5}$`)
- `court_name`: Presiding court name
- `jurisdiction`: Filing state/district jurisdiction
- `incident_date`: Loss / Injury Date (`MM/DD/YYYY`)
- `filing_date`: Case initiation date (`MM/DD/YYYY`)
- `causes_of_action`: Array of 2-3 claims sampled from the Causes of Action Pool in SKILL.md
- `prayer_for_relief`: Monetary damages award sought, formatted (`"$431,503"`)
- `attorney_name`: Counsel for plaintiff
- `bar_number`: Attorney state bar number (`^BAR\d{6}$`)
- `facts`: Factual allegations text paragraph
- `plaintiff_state_of_incorporation`, `defendant_state`: printed in the parties section
- `court_county`, `court_dept`, `judge_name`: caption block
- `filing_time`, `filing_clerk`: filed stamp
- `case_management_date`: referenced in the cover letter
- `prayer_amount_numeric`: the same amount as `prayer_for_relief`, as a float (not `"$"`-prefixed)
- `general_allegations`: list of 3 paragraphs
- `firm_name`, `firm_tagline`, `firm_practice_areas`: letterhead
- `firm_attorneys`: list of `{name, bar_number, role}` - `firm_attorneys[0]` is the signing
  attorney (always has `role="Managing Partner"`)
- `firm_address`, `firm_city_state_zip`, `firm_phone`, `firm_fax`, `firm_email`: letterhead
  contact block
- `opposing_counsel_name`, `opposing_firm_name`, `opposing_firm_address`: cover-letter recipient
- `letter_recipient_note`, `letter_reference`: cover-letter body text
- `prayer_items`: list of prayer paragraphs (already includes the dollar amount inline - do not
  also prepend `prayer_for_relief` separately)
- `verifier_name`, `verifier_title`, `verification_date`: verification page
- `notary_name`, `notary_commission_number`, `notary_commission_expires`: notary acknowledgment
