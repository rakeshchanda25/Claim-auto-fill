# Auto Accident Report Rendering Specification

- Page Size: Letter Portrait, 0.35in margins, single page
- Typography: Arial/Helvetica, 7.6pt body (dense, state-form style)
- Header: state seal image + form number/revision box, centered state name + "VEHICLE ACCIDENT
  REPORT" title, a bordered date/time box with AM/PM checkboxes
- Layout: a bordered "sheet" with left-side rotated section tabs (`.tab`, `-90deg` text) -
  STATE EMPLOYEE / VEHICLE NO. 1 / OTHER VEHICLES / OTHER PROPERTY / INJURED PARTIES /
  WITNESSES / OTHER - each section is its own stack of single-row `table.ftable` grids so
  differently-shaped rows never fight over shared `<col>` widths
- Injured Parties and Witnesses use a plain `table.list-table` (header row + one row per entry)
  instead of the tab/field layout
- Checkboxes (`{% if val == target %}☒{% else %}☐{% endif %}` macro) throughout for Yes/No and
  which-vehicle fields
