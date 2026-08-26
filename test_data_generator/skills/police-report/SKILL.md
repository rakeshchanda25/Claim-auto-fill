---
name: police-report
description: >
  Generate police incident reports for IDP testing. Covers auto accidents, slip-and-fall,
  property damage, and theft incidents with officer narrative, parties, and location.
metadata:
  owner: idp-test-team
  version: "1"
  page-size: letter-portrait
  template: police_report
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Police Report Generation Skill

## Required Sections
1. Department Header — Department name (city + "Police Department")
2. Incident Information — Report number, date, time, location, case status, citation issued,
   weather and road conditions
3. Officer Information — Name and badge number
4. Parties Involved Table — Role, Name, DOB, driver's license number for each party
5. Witnesses Table — Name and phone
6. Narrative — 4-6 sentence factual description of incident
7. Officer Signature Block

## Incident Number Format
- RPT + 8 digits (e.g., RPT20481039)

## Narrative Guidelines
- Write in third-person, past tense
- Include: where officer was dispatched, what was observed, parties' statements summary
- Do not include legal conclusions
- Appropriate for scenarios: auto accident, theft, property damage, slip-and-fall

## Party Roles
- Driver 1 / Driver 2 (auto accidents)
- Complainant / Suspect (property crimes)
- Victim / Witness (personal injury)
