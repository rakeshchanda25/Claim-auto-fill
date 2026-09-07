# Discharge Summary Rendering Specification

- Page Size: Letter Portrait, 0.4in margins
- Typography: Arial/Helvetica 9pt
- Header: logo image + gray "Discharge Summary" title box (`#b3b3b3` background)
- Patient info grid: 2-column bordered table (name/DOB, address, city/state/zip, physician on
  the left; admission/discharge dates on the right)
- Sections: each a bordered box (`.section`) with a gray section-header bar - Reason for
  Discharge (2-column checkbox list via the `box(val, target)` macro), Summary of Care, Status
  of Discharge, Plan for Transition, Summary of Patient Discharge Instructions
- Ruled fill-in lines (`.ruled-line`, via the `ruled(lines, min_count)` macro) pad each notes
  list up to a minimum row count with blank underlined lines, matching a real paper form
- Footer: clinician-signature table, bordered, bold labels
