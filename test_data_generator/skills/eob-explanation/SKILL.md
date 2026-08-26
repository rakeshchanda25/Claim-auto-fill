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
- Member Name and ID
- Group Number
- Claim Number and Date of Service
- Provider Name
- Service line items with: billed, allowed, plan paid, patient responsibility
- Summary: deductible applied, copay, coinsurance, total plan paid, total patient responsibility
- Denial reason (if any)

## Financial Calculation Rules
- Allowed = Billed × 0.80 (contractual reduction)
- Plan Paid = Allowed × 0.80 (coinsurance after deductible)
- Patient Responsibility = Allowed − Plan Paid
- Copay: $20-$60
- Deductible Applied: $0-$500

## EOB Remark Codes (for denial testing)
- CO-97: Service included in global surgical package
- PR-1: Deductible amount
- CO-45: Charge exceeds fee schedule
- OA-23: Payment adjusted per the Prior Payment
