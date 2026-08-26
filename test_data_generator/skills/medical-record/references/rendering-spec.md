# Medical Record Rendering Specification

## Typography & Page Geometry
- Page Size: Letter (8.5in x 11in), Portrait
- Margins: Top 1.0in, Bottom 1.0in, Left 0.85in, Right 0.85in
- Primary Font: Arial, Helvetica, sans-serif (10pt, line-height 1.5)
- Section Headers: 11pt bold, white text on navy banner (`#1a3a6b`)

## Layout Architecture
- Header: Facility title in 16pt bold navy text with thin horizontal rule divider
- Patient Info: 2-column key-value grid with light blue label headers
- Vitals Container: Shaded box (`#f5f8ff`) with 1px border (`#c0d0e8`)
- Diagnoses & Procedures: Standard CSS tables with alternating light grey/blue row fills
- Signature Block: Lower left with horizontal signature rule, NPI, and date

## Watermarks & Annotations
- Top-Right Margin Header: "CONFIDENTIAL – MEDICAL RECORD" in 8pt muted grey
- Bottom Footer: MRN + Page Numbering ("Page X of Y")
