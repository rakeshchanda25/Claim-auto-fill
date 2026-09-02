# ACORD 25 IDP Test Scenarios

ACORD-25's data generation does not branch on `scenario` at all - every coverage limit, mark,
and identity field is independent of which scenario name is passed. Any registered scenario
works; these are the ones the packet registry actually pairs it with:

- `general`: Standalone certificate, no specific claim context.
- `rear_end_collision`, `intersection_accident`, `hit_and_run` (via `auto-accident-packet`):
  certificate accompanies a police report and auto loss notice.
- `fire_damage`, `water_damage`, `theft`, `wind_damage` (via `property-claim-packet`):
  certificate accompanies a property loss notice and incident report.
