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

## Sections covered by the template (6 pages)
1. Firm Letterhead Cover Letter — firm name/tagline/attorneys/address, addressed to opposing
   counsel, referencing the enclosed complaint
2. Filed Stamp — court name/county, filing date/time, deputy clerk
3. Case Caption — Plaintiff v. Defendant, Court name, Case number, causes of action listed,
   demand for jury trial
4. Section I: Parties — Plaintiff and Defendant descriptions
5. Section II: Jurisdiction and Venue
6. Section III: General Allegations — 3 numbered paragraphs, then factual narrative
7. One numbered "CAUSE OF ACTION" subsection per entry in `causes_of_action`
8. Prayer for Relief — `prayer_items` list, one numbered paragraph each (not just a dollar
   figure), plus attorney signature block
9. Verification page — verifier declaration under penalty of perjury
10. Notary Certificate of Acknowledgment — notary name, commission number/expiration, seal

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
