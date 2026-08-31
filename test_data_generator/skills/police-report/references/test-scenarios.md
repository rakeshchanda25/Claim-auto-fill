# Police Report IDP Test Scenarios

police-report is used by two packets and is called with 7 real scenario names total, split
into two structurally different document shapes (see SKILL.md's "Two document shapes" section)
via `renderers/components.py`.

## Auto-collision shape (auto-accident packet)

- `rear_end_collision`: whenever `hit_and_run` lands `"No"` (its ~95% case for this scenario),
  `collision_type` is always `"Rear-end"` and `primary_factor` is always
  `"Following too closely"`. `narrative`/`narrative_paragraphs` describe Driver 2 striking
  Vehicle 1's rear bumper while it was stopped/slowing; `vehicle1.damage_description` is
  rear-end damage, `vehicle2.damage_description`-equivalent (party2's) is front-end damage.
- `intersection_accident`: `collision_type` is `"Angle"` or `"Head-on"`, `primary_factor` is
  `"Failure to yield right of way"`. Narrative describes an intersection impact.
- `hit_and_run`: `hit_and_run` is `"Yes"` in ~85% of generations (vs. ~5% baseline for every
  other scenario - it is still randomized, never assume it is forced `"Yes"` on every single
  generation). Whenever `hit_and_run` actually lands `"Yes"` (regardless of which scenario name
  produced it - the ~5% baseline can trigger it for ANY scenario, including out-of-domain ones),
  `collision_type` is drawn from `["Rear-end", "Sideswipe", "Angle"]` (never `"Single Vehicle"` -
  a fleeing second vehicle is a logical contradiction with a single-vehicle collision, the exact
  bug this session's rewrite fixed) and the narrative describes the striking vehicle fleeing the
  scene, later identified via witness/registration canvass.

Any other scenario (including `general` or one from an unrelated packet, e.g. `scenario=
"surgery"`) falls back to this shape with independently randomized (but internally consistent)
`collision_type`/`primary_factor`.

## Property-incident shape (property-claim packet, where this doc type serves as "Incident
Report")

- `fire_damage` / `water_damage` / `theft` / `wind_damage`: reuses
  `_property_scenario_facts()` (the same function property-loss-notice uses) for the loss-detail
  facts shown in the `property_incident` component, and `_property_scenario_facts()`'s title/
  facts also drive the narrative's account of the incident. No vehicle, injury, enforcement, or
  field-sketch content - see SKILL.md for exactly which components this shape omits.

## Structural coverage, not just field coverage

Before this session's rewrite, the ONLY thing that varied by scenario was individual field
values inside one fixed template shape - a fire-damage report showed empty "Driver 1/Driver 2"
vehicle tables it had no data for. `renderers/components.py`'s `COMPONENT_COMPOSITION` now
decides which sections exist at all, not just what's inside them - see `test_document_
components.py` in `testCases/` for the regression tests asserting the auto shape always
contains "Driver 1" and the property shape never does.
