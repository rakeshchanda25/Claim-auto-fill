---
name: litigation-document
description: >
  Generate a specimen-style civil complaint for IDP testing - law-firm letterhead cover
  letter, then pleading paper (line numbers, vertical rules, filed stamp, caption block,
  general allegations, one subsection per cause of action, prayer for relief, verification,
  and a notary acknowledgment page). Covers personal injury, medical malpractice, slip-and-fall,
  and product liability complaints.
metadata:
  owner: idp-test-team
  version: "3"
  page-size: letter-portrait
  template: litigation_document
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Litigation Document Generation Skill

## Sections covered by the template (5 + N pages, N = len(causes_of_action))
1. Firm Letterhead Cover Letter — firm name/tagline/attorneys/address, addressed to opposing
   counsel, referencing the enclosed complaint (not numbered - a real filed pleading doesn't
   number its cover letter)
2. Filed Stamp — court name/county, filing date/time, deputy clerk
3. Case Caption — Plaintiff v. Defendant, Court name, Case number, causes of action listed,
   demand for jury trial
4. Section I: Parties — Plaintiff and Defendant descriptions
5. Section II: Jurisdiction and Venue
6. Section III: General Allegations — 3 numbered paragraphs, then factual narrative
7. One numbered "CAUSE OF ACTION" subsection per entry in `causes_of_action` - **each cause
   gets its OWN physical page**, not all of them crammed onto one (see "Page count" below)
8. Prayer for Relief — `prayer_items` list, one numbered paragraph each (not just a dollar
   figure), plus attorney signature block
9. Verification page — verifier declaration under penalty of perjury
10. Notary Certificate of Acknowledgment — notary name, commission number/expiration, seal

## Page count
`causes_of_action` is a random 2-3 items (see `synthetic_data.py`'s litigation-document
branch) - the complaint used to always be exactly 6 physical pages regardless, because all
causes were packed onto ONE fixed 8.5x11in `overflow:hidden` page (`renderers/templates/
litigation_document.html`'s old `causes_of_action_page`), which silently CLIPS anything that
doesn't fit rather than adding a page. The macro now loops - one physical page per cause -
so the document is `4 + len(causes_of_action)` numbered pleading pages plus the unnumbered
cover letter (6-7 total). Page numbering ("— N —" in the footer) is a CSS counter
(`.pleading` class + `counter-increment: pleadingpage`, displayed via a `.pagenum::after`
pseudo-element - not literal text in the HTML), so it stays correct regardless of how many
pages the causes-of-action section ends up needing. `test_document_components.py`'s
`test_litigation_document_page_count_tracks_causes_of_action_count` is the regression test.

## Case Number Format
- CV-{YEAR}-{5 digits} (e.g., CV-2025-48291)

## Court Names
- Superior Court of [State]

## Causes of Action Pool
`causes_of_action` is drawn from exactly this pool - do not invent causes outside it:
- Negligence
- Breach of Duty of Care
- Premises Liability
- Negligent Infliction of Emotional Distress
- Strict Product Liability

For `slip_and_fall`/`medical_malpractice`/`product_liability`, one specific cause from this
pool is GUARANTEED present (the scenario's "anchor" - see `references/test-scenarios.md`);
the remaining 1-2 causes are randomly sampled from the rest of the pool. Any other scenario
samples 2-3 causes with no anchor.

## Prayer Amount
- $50,000 to $1,000,000

## Facts / General Allegations narrative
`facts` and `general_allegations` (`_litigation_narrative()` in synthetic_data.py) recount the
actual anchored cause of action - e.g. slip_and_fall describes a hazardous walking surface,
medical_malpractice describes a deviation from the standard of care, product_liability
describes a design/manufacturing defect - rather than generic Faker prose unrelated to
`causes_of_action`. `letter_reference` on the cover letter also names the scenario and
incident date.

## Document composition
Like every doc type, this template is decomposed into named Jinja macros ("components") in
`renderers/templates/litigation_document.html`, assembled by `renderers/components.py`'s
`COMPONENT_COMPOSITION["litigation-document"]`. Every registered scenario resolves to the SAME
6 component NAMES (a real civil complaint doesn't restructure its sections by injury type) -
but unlike every other non-police-report doc type, one of those components
(`causes_of_action_page`) is not a single fixed page: it emits one physical page per entry in
`causes_of_action`, so total page count genuinely varies (see "Page count" above). This is the
lower-risk alternative to police-report's natural-CSS-flow approach - it keeps this file's
existing fixed-8.5x11in-page-per-physical-page mechanism (proven, unchanged everywhere else in
this file) and just varies HOW MANY such pages get emitted, rather than switching the whole
document to reflowing content.
