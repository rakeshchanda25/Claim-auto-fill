# Police Report Field Glossary

- `incident_number`: Official report identifier (`^RPT\d{8}$`)
- `incident_date`: Date incident occurred (`MM/DD/YYYY`)
- `incident_time`: Time incident occurred (`HH:MM`)
- `location`: Incident address
- `officer_name`: Reporting officer name
- `badge_number`: Officer badge number (`^\d{4}$`)
- `department`: Issuing police department name
- `case_status`: `Open` / `Closed` / `Under Investigation`
- `citation_issued`: `Yes` / `No`
- `weather_conditions` / `road_conditions`: printed conditions text
- `narrative`: Factual chronological statement of incident details
- `parties_involved`: list of exactly 2 dicts (Driver 1, Driver 2) - see "Party Roles" in SKILL.md
  for the shape of each party
- `witnesses`: list of `{name, phone, address, statement}`
- `local_report_number`, `cad_incident_number`: secondary report identifiers
- `report_date`, `dispatch_time`, `arrival_time`, `cleared_time`: letterhead timestamps
- `city`, `county`: printed alongside `location`
- `department_address`, `department_phone`, `department_records_phone`,
  `department_records_email`, `department_ori`, `department_ncic`: letterhead contact block
- `lighting_conditions`, `traffic_control`, `speed_limit`, `collision_type`, `num_vehicles`,
  `hit_and_run`, `primary_factor`, `other_factors`: Section 1 incident-data fields
- `narrative_paragraphs`: list of 3 paragraphs split across pages 2-3 (in addition to `narrative`)
- Each `parties_involved[i]` also carries: `sex`, `license_state`, `license_class`, `address`,
  `phone`, `injured`, `vehicle_year`/`vehicle_make`/`vehicle_model`/`vehicle_plate`/
  `vehicle_plate_state`/`vehicle_vin`, `registered_owner`, `insurer`, `policy_number`,
  `damage_severity`, `damage_description`, `towed`, `citation_number`, `at_fault` (bool),
  `seat_position`, `restraint`, `transported_to`
- `property_damage_items`: list of `{item, owner, est_value, reference}`
- `cargo_involved`, `hazmat`: free text / Yes-No
- `enforcement_party_cited`, `enforcement_citation_number`, `enforcement_sections_charged`,
  `enforcement_court_date`, `enforcement_court_name`, `chemical_test`, `arrest_made`
- `evidence_items`: list of `{item_no, description}`
- `reporting_officer_badge`, `reporting_officer_unit`, `reporting_officer_date`,
  `reporting_officer_time`, `report_status`
- `supervisor_name`, `supervisor_badge`, `supervisor_approval_date`
- `records_custodian`, `records_release_date`, `records_request_number`, `page_count`
