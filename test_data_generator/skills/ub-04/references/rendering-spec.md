# UB-04 Rendering Specification

- Page Size: Letter Portrait, 0.3in margins, single page
- Typography: Arial/Helvetica, 6.6pt body (dense, to fit the full FL1-FL81 box count)
- Layout: edge-to-edge `table.box` grid, 0.8pt borders, EVERY cell carries a small bold
  `.bn` box-number superscript (matching the real form's printed field numbers) above a `.bl`
  label and `.bv` value - this is what makes it read as an authentic CMS-1450 rather than a
  generic labeled table
- Revenue-code table (`table.lines`) includes 6 trailing blank ruled lines after the actual
  entries, matching the real form's many-blank-lines convention, before the PAGE/CREATION
  DATE/TOTALS row
- Footer: "UB-04 CMS-1450" certification line, then a legend row (large page-sequence digit +
  boxed "Red = Required / Black = Situational" key) mirroring the real form's bottom margin
