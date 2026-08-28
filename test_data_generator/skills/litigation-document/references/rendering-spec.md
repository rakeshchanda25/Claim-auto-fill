# Litigation Document Rendering Specification

- Page Size: Letter Portrait, 6 pages (`page-break-after` per `.page` div)
- Typography: FreeSerif/DejaVu Serif body (letter + pleading text), DejaVu Sans for small print
  (letterhead contact block, footers, filed stamp)
- Diagonal "SPECIMEN" watermark on every page (`rgba(150,40,40,0.085)`, rotated -31deg)
- Page 1: firm letterhead cover letter (SVG scale/gavel mark, two-column attorney/address block,
  hand-drawn-style SVG signature)
- Pages 2-6: pleading paper - three vertical rules + numbered lines 1-28 down the left margin
  (`.lineno`), all content offset to sit on those ruled lines; page 2 has a rotated "FILED"
  stamp box (navy `#1f3f7a` border) and the case-caption table (party block | `)` brace column |
  case-number/causes-of-action block)
- Page 6: verification + notary acknowledgment with a circular SVG notary seal
- Every pleading page's footer: "VERIFIED COMPLAINT FOR DAMAGES — CASE NO. {{ case_number }}"
  plus a centered page number (`— N —`)
