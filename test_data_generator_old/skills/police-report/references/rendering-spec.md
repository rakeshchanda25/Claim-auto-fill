# Police Report Rendering Specification

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
