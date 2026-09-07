# Auto Accident Report IDP Test Scenarios

## Scenario coverage

auto-accident-report only appears in the auto-accident packet, so it is always called with one
of `rear_end_collision` / `intersection_accident` / `hit_and_run`. Each gets a dedicated
"Details" section (`scenario_facts_title` + `scenario_facts`, from `synthetic_data.py`'s
`_auto_scenario_facts()`) rendered as a tabbed row before the footer note:
- `rear_end_collision`: following distance estimated, brake lights observed, road grade.
- `intersection_accident`: traffic control device, right-of-way violation alleged, turning movement involved.
- `hit_and_run`: fleeing vehicle description, direction of travel, BOLO issued.

Any other scenario omits the section entirely rather than rendering an empty heading.
