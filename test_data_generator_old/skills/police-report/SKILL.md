---
name: police-report
description: >
  Generate a specimen-style police traffic-collision report for IDP testing - department
  letterhead + seal, sectioned incident/party/injury/witness/enforcement/evidence grid,
  narrative, field sketch, officer + supervisor signatures, records certification.
metadata:
  owner: idp-test-team
  version: "3"
  page-size: letter-portrait
  template: police_report
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Police Report Generation Skill

## Sections covered by the template (3 pages)
1. Letterhead — Department name/address/phone, ORI, NCIC agency number, records unit contact
2. Incident Information — Case/local report numbers, CAD incident number, date, dispatch/
   arrival/cleared times, location, city/county, collision type, weather/lighting/road/traffic
   conditions, speed limit, primary/other collision factors, hit-and-run flag
3. Per-Party Detail (exactly 2 parties) — name, DOB, sex, DL number/state/class, address,
   phone, injury status, full vehicle (year/make/model/plate/VIN), registered owner, insurer,
   policy number, damage severity/description, towed, citation number
4. Injuries and Medical Transport — one row per party (seat position, restraint, transport
   destination)
5. Property Damage (Other Than Vehicles) — item, owner, estimated value, reference number
6. Witnesses — name, address, phone, statement
7. Enforcement Action — party cited, citation number, court date/name, chemical test, arrest
8. Evidence and Attachments — numbered evidence items
9. Narrative — 3-paragraph officer narrative plus a standalone summary paragraph
10. Field Sketch — illustrative diagram (not data-driven; same generic sketch every time)
11. Reporting Officer + Reviewing Supervisor signatures, Records Division certification

## Incident Number Format
- RPT + 8 digits (e.g., RPT20481039)

## Narrative Guidelines
- Write in third-person, past tense
- Include: where officer was dispatched, what was observed, parties' statements summary
- Do not include legal conclusions

## Party Roles
- `parties_involved` is always exactly two entries: Driver 1 (non-culpable) and Driver 2
  (at-fault). `party.at_fault` (bool) drives which one gets the injury/citation/damage-severity
  weighting.

## Scenario coverage
`rear_end_collision`, `intersection_accident`, `hit_and_run` currently all produce the SAME
report structure with independently randomized content - the scenario name does not yet drive
anything scenario-specific (see `references/test-scenarios.md`). Do not assume a
`hit_and_run`-scenario generation actually has the `hit_and_run` field set to `"Yes"`; check
the field itself.
