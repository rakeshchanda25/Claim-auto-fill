---
name: litigation-document
description: >
  Generate civil litigation complaint documents for IDP testing. Covers personal injury,
  medical malpractice, slip-and-fall, and product liability complaints.
metadata:
  owner: idp-test-team
  version: "1"
  page-size: letter-portrait
  template: litigation_document
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Litigation Document Generation Skill

## Required Sections
1. Case Caption — Plaintiff v. Defendant, Court name, Case number
2. Title — "COMPLAINT FOR DAMAGES"
3. Section I: Parties — Plaintiff and Defendant descriptions
4. Section II: Jurisdiction and Venue
5. Section III: Factual Allegations — 4-6 sentences narrative
6. Section IV: Causes of Action — 1-3 causes (Negligence, Breach of Duty, etc.)
7. Section V: Prayer for Relief — Dollar amount sought
8. Attorney Signature Block — Name, bar number, "Attorney for Plaintiff"

## Case Number Format
- CV-{YEAR}-{5 digits} (e.g., CV-2025-48291)

## Court Names
- Superior Court of [State]
- [State] Circuit Court
- District Court, [State] Division

## Causes of Action Pool
- Negligence
- Breach of Duty of Care
- Medical Malpractice
- Product Liability
- Premises Liability
- Gross Negligence

## Prayer Amount
- $50,000 to $1,000,000
