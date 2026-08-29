# Police Report IDP Test Scenarios

- `rear_end_collision`: `collision_type` is always `"Rear-end"`, `primary_factor` is always
  `"Following too closely"`.
- `intersection_accident`: `collision_type` is `"Angle"` or `"Head-on"`, `primary_factor` is
  always `"Failure to yield right of way"`.
- `hit_and_run`: `hit_and_run` is `"Yes"` in ~85% of generations (vs. ~5% baseline for the
  other two scenarios - it is still randomized, never assume it is forced `"Yes"` on every
  single generation). A confirmed hit-and-run also makes `citation_issued` more likely.

Narrative text and party/vehicle identities remain independently randomized regardless of
scenario - only `collision_type`/`primary_factor`/`hit_and_run` (and, downstream,
`citation_issued`) are scenario-correlated. See `synthetic_data.py`'s police-report branch.
