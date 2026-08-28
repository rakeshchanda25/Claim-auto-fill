# Police Report IDP Test Scenarios

- `rear_end_collision`, `intersection_accident`, `hit_and_run`: all three currently produce
  the SAME report structure with independently randomized content (`collision_type`,
  `hit_and_run`, narrative, etc. are not derived from the scenario name) - the scenario label
  does not yet drive anything scenario-specific in this skill. Do not assume a `hit_and_run`
  generation actually has `hit_and_run == "Yes"`; check the field itself.
