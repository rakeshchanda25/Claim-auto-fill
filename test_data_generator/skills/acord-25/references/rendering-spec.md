# ACORD 25 Rendering Specification

## `acord-25` (compact)
- Format: Standard ACORD 25-style Certificate of Liability Insurance, condensed to one page
- Page Geometry: Letter Portrait, 0.4in margins
- Font: Arial 7.3pt body / ~5.6pt box labels
- Key Tables: Producer/Insured grid, dark section-bar coverages table, Certificate Holder,
  Authorized Representative signature line
- No AcroForm widgets - values are painted directly into page content (see SKILL.md)

## `acord-new` (2018/09-style specimen)
- Page Geometry: Letter Portrait, 0.35in margins, single page
- Font: Arial 7.2pt body
- Layout: black-circle "A" logo mark + "ACORD" wordmark box, centered bold title, boxed DATE
  field top right, bold "IMPORTANT" clause, INSURER A-D table with NAIC# column, coverages
  table split into `<tbody class="cov-group">` per coverage type with `break-inside: avoid`
  (each coverage type's rowspan'd rows must stay together across a page break - splitting one
  mid-group is what caused the misaligned continuation rows this fix corrects)
- CERTIFICATE HOLDER / CANCELLATION two-column box with an `AUTHORIZED REPRESENTATIVE` line
  styled as a signature (`border-top`, not a boxed cell)
