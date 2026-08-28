# Auto Accident Report Field Glossary

- `accident_date`, `accident_time`, `accident_time_ampm` (`AM`/`PM`): header date box
- `employee`: dict - `business_address`, `zip`, `business_phone`, `email`, `license_no`,
  `license_restrictions`, `if_yes_indicate`, `official_business` (bool)
- `vehicle1`: dict - `license_no`, `year`, `make`, `body_type`, `where_located`,
  `no_of_passengers`, `est_repair_cost`, `prior_accident` (bool), `owning_agency`,
  `damage_description`, `private_owner_or_equipment_no`, `insurer`
- `vehicle2`, `vehicle3`: dicts - `owner_name`, `owner_phone`, `owner_address`, `owner_city`,
  `owner_zip`, `driver_name`, `driver_age`, `driver_phone`, `driver_address`, `driver_city`,
  `driver_zip`, `driver_license_no`, `vehicle_license_no`, `vehicle_make`, `vehicle_year`,
  `body_type`, `passengers`, `repair_cost`, `damage_description`, `insurance_company`,
  `policy_no` (`vehicle3` is currently always all-blank strings)
- `other_property`: dict - `what_was_damaged`, `repair_cost`, `owner_name_address`, `city`,
  `zip`, `phone` (currently always all-blank strings)
- `injured_parties`: list of `{name_address, extent_of_injury, age, vehicle (1/2/3), pedestrian
  (bool)}` - empty list when nobody was injured
- `witnesses`: list of `{name, address, city, phone}`
- `other`: dict - `police_investigated` (bool), `police_division`, `citation_issued` (bool),
  `citation_issued_to` (`""`/`"You"`/`"Veh. 2"`/`"Veh. 3"`), `collision_report_filed` (bool)
- `form_number`, `form_revision`, `seal_url`, `office1_*`, `office2_*`, `scan_email`,
  `footer_note`: all have template `| default(...)` fallbacks - only supply these if you want
  to override the printed defaults
