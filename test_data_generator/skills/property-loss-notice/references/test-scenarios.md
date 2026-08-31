# Property Loss Notice IDP Test Scenarios

- `fire_damage`: Residential structure fire notice, plus a "Fire Details" section (fire
  department notified, responding department, fire report #, suspected cause of ignition).
- `water_damage`: Burst pipe/plumbing water damage, plus a "Water Details" section (water
  source, mitigation company, moisture reading, mold remediation flag).
- `theft`: Burglary property notice, plus a "Theft Details" section (police report #, forced
  entry, items stolen, recovery status).
- `wind_damage`: Storm damage notice, plus a "Storm Details" section (storm name, peak wind
  gust, NWS advisory #, tree/debris damage flag).

Each scenario's section is genuinely structural, not just a different `cause_of_loss` string -
see `_property_scenario_facts()` in `synthetic_data.py`. A scenario not listed here (e.g.
`general`) omits the section entirely rather than rendering an empty heading.
