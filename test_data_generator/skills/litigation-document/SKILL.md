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
`causes_of_action` is `random.sample(k=2 or 3)` from exactly this pool - do not invent causes
outside it, and do not assume a specific scenario maps to a specific cause (the sample is not
scenario-conditioned):
- Negligence
- Breach of Duty of Care
- Premises Liability
- Negligent Infliction of Emotional Distress
- Strict Product Liability

## Prayer Amount
- $50,000 to $1,000,000
