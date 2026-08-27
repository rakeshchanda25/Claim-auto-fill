---
name: eob-explanation
description: >
  Generate Explanation of Benefits (EOB) documents for IDP testing. Covers member, provider,
  claim details, billed/allowed/paid breakdown, patient responsibility, and denial reasons.
metadata:
  owner: idp-test-team
  version: "1"
  page-size: letter-portrait
  template: eob_explanation
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# EOB Generation Skill

## Required Fields
- Member Name and ID, Group Number
- Claim Number and Date of Service
- Provider Name
- Network Status, Processed Date, Check/EFT Number
- Per-line claim summary (`eob_lines`): CPT code, billed, allowed, plan paid, patient owes,
  reason code - each line's amounts are reconciled so they SUM EXACTLY to the claim totals
  below (a real EOB's line items must foot to its stated total; do not recompute per-line
  amounts independently of the totals)
- Summary: deductible applied, copay, coinsurance, total plan paid, total patient responsibility
- Denial reason (if any)

## Financial Calculation Rules
- Allowed = Billed × a rate between 0.60 and 0.90 (contractual reduction - varies by
  plan/network, randomized once per claim and reused for every line so the breakdown stays
  internally consistent)
- Plan Paid = Allowed × a rate between 0.70 and 0.95 (coinsurance after deductible - same
  per-claim randomization approach)
- Patient Responsibility = Allowed − Plan Paid
- Copay: $20-$60
- Deductible Applied: $0-$500
- Network Status: In-Network in most cases, occasionally Out-of-Network

## EOB Remark Codes (for denial testing)
- CO-97: Service included in global surgical package
- PR-1: Deductible amount
- CO-45: Charge exceeds fee schedule
- OA-23: Payment adjusted per the Prior Payment
