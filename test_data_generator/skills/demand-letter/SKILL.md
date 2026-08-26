---
name: demand-letter
description: >
  Generate legal demand letters for insurance claims settlement. Covers personal injury,
  auto accident, slip-and-fall, and medical malpractice pre-litigation demands.
metadata:
  owner: idp-test-team
  version: "1"
  page-size: letter-portrait
  template: demand_letter
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Demand Letter Generation Skill

## Required Sections
1. Attorney/Firm Letterhead — Firm name, address, state bar number
2. Date of Letter
3. Recipient — Insurer name and Claims Department
4. RE Line — "DEMAND FOR SETTLEMENT" with claimant vs. respondent, incident date
5. Salutation and Opening Paragraph
6. Facts Summary — 4-6 sentences describing the incident and injuries
7. Damages Breakdown — Special damages (medical/economic) and General damages (pain/suffering)
8. Total Demand Amount — Prominently boxed
9. Settlement Deadline — 30 days from letter date
10. Closing and Attorney Signature

## Financial Rules
- Demand amount: $25,000 to $500,000
- Special damages: ~40% of demand
- General damages: ~60% of demand
- Settlement deadline: letter date + 30 days

## Tone and Format
- Formal legal prose, Times New Roman 11pt
- Double-spaced body paragraphs
- State "reserves all rights" to litigate if demand rejected
