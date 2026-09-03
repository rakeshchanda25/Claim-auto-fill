# Police Report Rendering Specification

## Design invariants — these hold for EVERY layout, including per-state ones

- Page size Letter portrait, margins >= 0.3in
- A diagonal SPECIMEN watermark on every page. The validator rejects a layout without it.
- A footer on every page marking the document as synthetic test data, with the case number
  and page numbering.
- Body text >= 6.5pt so the output stays legible after scan degradation.
- Data comes only from the generated document data. A layout never invents a value.
- The layout honours `components` (see renderers/components.py): vehicle and driver sections
  appear only when `auto_parties` is in the list. A fire, water, theft or wind report must not
  show driver or vehicle boxes.

## Per-state layouts

A state layout lives at `renderers/layouts/police-report/<CODE>.html` and replaces everything
below the invariants: masthead, form number, section order and field labels all follow that
state's real published form. See `references/states/<CODE>.md` for the sourced field list, and
`sourcing/state_forms.yaml` for provenance and fidelity level.

Shape-specific variants may be added as `<CODE>__AUTO.html` / `<CODE>__PROPERTY.html`; the
renderer prefers those and falls back to `<CODE>.html`, then to the generic template below.

## Generic template (used when no state layout exists)

- Page Size: Letter Portrait, ~0.45in margins, 3 pages (`page-break-after` per `.page` div)
- Typography: DejaVu Sans / Arial, 8.2pt body
- Diagonal "SPECIMEN" watermark on every page (`rgba(120,30,30,0.075)`, rotated -30deg)
- Letterhead: SVG badge seal + department name/address/ORI/NCIC/records contact, dark navy
  (`#14304f`) title bar reading "TRAFFIC COLLISION REPORT"
- Body: boxed field grid (`table.f`, 0.7pt borders) grouped under uppercase section headers
  on a light-gray bar (`.sechead`, `#dfe4ea`)
- Page 3: illustrative SVG field sketch (fixed diagram, not scenario-specific), hand-drawn-style
  SVG signature paths for officer + supervisor, records-division certification block
- All-page footer: case number + "SPECIMEN · SYNTHETIC TEST DATA · NOT A GENUINE POLICE RECORD"
