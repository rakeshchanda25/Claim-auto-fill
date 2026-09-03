# ACORD 25 Field Glossary

- `certificate_date`: DATE (MM/DD/YYYY) box, top right - today's date
- `producer_name` / `producer_address` / `producer_phone` / `producer_email`: Agency identity
- `insured_name` / `insured_address`: Business entity being certified
- `insurer_a` / `insurer_a_naic`: Carrier name and NAIC number
- `gl_policy_number` / `auto_policy_number` / `umb_policy_number` / `wc_policy_number`: one
  policy ID per coverage line, prefixed GL/CA/UMB/WC + 8 digits - never a single shared
  `policy_number`, each coverage has its own
- `effective_date` / `expiration_date`: shared by all four coverage lines on one certificate
- `gl_each_occurrence` / `gl_damage_rented_premises` / `gl_med_exp` / `gl_personal_injury` /
  `gl_general_aggregate` / `gl_products_agg`: CGL limits, drawn together from one tier (range
  $500,000 to $2,000,000/$4,000,000 - see SKILL.md's Coverage Limits section, never a fixed number)
- `auto_combined_single_limit`: $500,000 to $2,000,000
- `umb_each_occurrence` / `umb_aggregate`: same value, $1,000,000 to $10,000,000
- `wc_el_each_accident` / `wc_el_disease_employee` / `wc_el_disease_policy`: $100,000 to
  $1,000,000, drawn from one standard combo
- `general_liability_limit` / `umbrella_limit` / `workers_comp_limit`: legacy aliases mirroring
  `gl_each_occurrence` / `umb_each_occurrence` / `wc_el_each_accident` - keep them equal
- `certificate_holder` / `certificate_holder_address`: Holder name and mailing address
- `authorized_representative`: signature line name
- `description_of_operations`: free text, ACORD 101 boilerplate is fine

## Checkbox mark fields (`☑`/`☐` glyphs - see "Checkbox fields" in SKILL.md)
- `gl_occurrence_mark` / `gl_claims_made_mark`: GL claims basis (mutually exclusive pair)
- `gl_agg_policy_mark` / `gl_agg_project_mark` / `gl_agg_loc_mark`: GL aggregate basis (3-way,
  exactly one ticked)
- `auto_any_auto_mark`: ticked when the auto coverage is "Any Auto"; when NOT ticked, all four
  of `auto_all_owned_mark` / `auto_scheduled_mark` / `auto_hired_mark` / `auto_non_owned_mark`
  are ticked instead (never a mix)
- `umb_umbrella_mark` / `umb_excess_mark`: umbrella-vs-excess form (mutually exclusive)
- `umb_occur_mark` / `umb_claims_made_mark`: umbrella claims basis (mutually exclusive)
- `umb_ded_mark` / `umb_retention_mark`: deductible-vs-retention (mutually exclusive)
- `wc_officer_excluded_y_mark` / `wc_officer_excluded_n_mark`: WC officer-excluded Y/N
- `wc_statutory_mark` / `wc_other_mark`: WC limits basis (mutually exclusive)
