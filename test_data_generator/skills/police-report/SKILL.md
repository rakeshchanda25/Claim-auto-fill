---
name: police-report
description: >
  Generate a specimen-style police report for IDP testing - department letterhead + seal,
  then a sectioned grid that assembles differently depending on scenario: a full
  traffic-collision report (party/vehicle/injury/enforcement/field-sketch sections) for
  auto scenarios, or a shorter property-incident report (reporting party + loss facts,
  no vehicle sections) for property scenarios - officer certification and records
  signatures either way.
metadata:
  owner: idp-test-team
  version: "4"
  page-size: letter-portrait
  template: police_report
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Police Report Generation Skill

## Two document shapes, one design system

This template used to be a single fixed structure that every scenario's data got poured
into - a fire-damage report still showed empty "Driver 1 / Driver 2" vehicle tables, because
the template had no way to represent anything else. It's now a **component library**
(`renderers/templates/police_report.html`, named Jinja macros) assembled per scenario by
`renderers/components.py`'s `COMPONENT_COMPOSITION["police-report"]`. The page chrome
(letterhead, watermark, typography, `.sechead`/`.lbl`/`.val` conventions, footer/page-number
via CSS `@page` margin boxes) is identical in both shapes - only which components get
assembled differs:

**Auto-collision shape** (rear_end_collision / intersection_accident / hit_and_run, and the
fallback for any other/unrecognized scenario - see "Scenario coverage" below): incident
header → **auto_parties** (per-party driver/vehicle detail, exactly 2 parties) → injuries and
medical transport → property damage (other than vehicles) → witnesses → enforcement action →
evidence → narrative → field sketch (illustrative collision diagram) → officer certification.

**Property-incident shape** (fire_damage / water_damage / theft / wind_damage - this doc type
is also the property-claim packet's "Incident Report"): incident header → **property_incident**
(reporting party + the scenario's loss-detail facts, replacing the driver/vehicle tables
entirely) → witnesses → evidence → narrative → officer certification. No injuries, enforcement
action, or field sketch sections - a fire/water/theft/wind incident has no driver citations or
collision diagram to show.

Section numbering ("Section N — ...") is computed per shape inside each component (not a
generic renumbering engine) - correct for these two registered shapes; adding a third shape
means a new `COMPONENT_COMPOSITION` entry plus, only if it needs content nothing here already
renders, a new macro.

Pagination is natural CSS flow (not a fixed 3-page layout) - the property-incident shape is
genuinely shorter and may print on fewer physical pages than the auto-collision shape; page
numbers come from `@page { @bottom-right { content: counter(page) " of " counter(pages) } }`,
so they're always correct regardless of scenario or content length.

## Incident Number Format
- RPT + 8 digits (e.g., RPT20481039)

## Narrative Guidelines
- Write in third-person, past tense
- Include: where officer was dispatched, what was observed, parties' statements summary
- Do not include legal conclusions

## Party Roles (auto-collision shape only)
- `parties_involved` is always exactly two entries: Driver 1 (non-culpable) and Driver 2
  (at-fault). `party.at_fault` (bool) drives which one gets the injury/citation/damage-severity
  weighting. In the property-incident shape, `parties_involved[0]` is instead the reporting
  party (property owner/occupant) - the same underlying `_party()`-built dict, just read for
  its name/address/phone rather than its vehicle fields.

## Scenario coverage
`collision_type`, `primary_factor`, and `hit_and_run` are correlated to hit_and_run_flag
FIRST, then scenario - see `references/test-scenarios.md` for exactly what each of the 7
registered scenarios (3 auto + 4 property) sets, and for the real bug this fixed (a
`collision_type: "Single Vehicle"` + `hit_and_run: "Yes"` contradiction that could occur for
ANY scenario name, not just the literal `hit_and_run` one - including one that has nothing to
do with this doc type at all, e.g. `scenario="surgery"`).
`hit_and_run` is still randomized even for the `hit_and_run` scenario (~85% likely, not
forced) - check the field itself rather than assuming.

`narrative`/`narrative_paragraphs`/witness `statement` are also scenario-driven
(`_police_narrative()`/`_witness_statement()` in synthetic_data.py) - they recount the actual
mechanism (e.g. "struck the rear of..." for rear_end_collision, "fled the scene" for
hit_and_run) using the report's own parties/collision_type/primary_factor, not generic
Faker prose, and are branched on the actual `hit_and_run_flag` outcome, not the scenario
name (same fix as above). When serving as the property-claim packet's Incident Report
(fire_damage/water_damage/theft/wind_damage), the narrative instead recounts the
`property_incident` component's loss-detail facts.

Any scenario name not in the 7 registered ones (including one from an unrelated packet, e.g.
`scenario="chronic_medication"`) falls back to the auto-collision shape with independently
randomized (but internally consistent) fields - `renderers/components.py`'s `get_components()`
always resolves to a real, complete document, never an empty one.
