---
name: pharmacy-invoice
description: >
  Generate an Indian GST tax invoice for a pharmacy sale, for IDP testing - GSTIN/HSN/IGST
  throughout, a multi-item table with batch/MFG/expiry per item, an HSN/SAC tax summary, bank
  and UPI payment details. A different domain from a US pharmacy dispensing receipt.
metadata:
  owner: idp-test-team
  version: "2"
  page-size: A4-portrait
  template: pharmacy_invoice
allowed-tools: generate_synthetic_data render_document_to_pdf validate_document_structure
---
# Pharmacy Invoice Generation Skill

## Required Sections
1. Header — pharmacy logo/name/address/phone, optional promo banner
2. GSTIN / Title row — pharmacy's GSTIN, "TAX INVOICE" title, copy label (Original/Duplicate/
   Triplicate)
3. Customer Detail + Invoice Meta — customer name/contact/address/phone/GSTIN/place of supply;
   invoice number and date
4. Items Table — one row per item: batch no., MFG/expiry date, HSN/SAC code, qty+unit, MRP,
   rate, discount %, taxable value; subtotal, IGST, and grand-total rows
5. Total in Words
6. HSN/SAC Summary Table — taxable value, IGST %/amount, total, grouped by HSN code
7. Total Tax in Words
8. Bank Details + UPI QR — for payment; Terms and Conditions; customer/authorised signatures

## Tax Model
The template only ever prints IGST (no CGST/SGST split) - do not compute a CGST+SGST
alternative even if `customer_gstin` implies an intra-state sale; every invoice this skill
produces is modeled as inter-state supply.
- One `igst_pct` (5%, 12%, or 18%) applies to the WHOLE invoice, not per item
- Per item: `taxable_value` = `qty × rate × (1 − discount_pct/100)`
- `subtotal_taxable_value` = sum of every item's `taxable_value`
- `igst_amount` = `subtotal_taxable_value × igst_pct / 100`
- `grand_total` = `subtotal_taxable_value + igst_amount`
- `hsn_summary` groups items by `hsn_sac`, each group's own taxable value / IGST amount / total
  summing to the invoice totals

## Scenario coverage
`items` is drawn from a scenario-specific pool/price band, not one fixed drug list - see
`references/test-scenarios.md` for the exact pool and price range per scenario
(`chronic_medication` / `specialty_drug` / `compounded_medication`).
- `total_in_words` / `tax_in_words`: Indian digit grouping (Lakh/Crore, not Western
  thousand/million) - see `synthetic_data.py`'s `_amount_in_words()` / `_int_to_words()`

## GSTIN Format
- 15 characters: 2-digit state code + 10-char PAN-like + entity digit + `Z` + checksum char
  (synthetic - not a real checksum-valid number). `customer_gstin` is blank ~70% of the time
  (a B2C retail sale has no customer GSTIN to print).

## HSN Codes (pharmaceutical)
- 3004 = medicaments (mixed/dosed) · 3003 = medicaments (not mixed/dosed) · 3005 = dressings/
  bandages · 2106 = food preparations n.e.s.

## Legacy fields
`rx_number`, `fill_date`, `drug_name`, `ndc_code`, `form`, `prescriber_name`, `prescriber_dea`,
`prescriber_npi` are still generated (kept for backward-compat, an earlier US-style dispensing
receipt used them) but the current template does not render any of them.

## Document composition
Like every doc type, this template is decomposed into named Jinja macros ("components") in
`renderers/templates/pharmacy_invoice.html`, assembled by `renderers/components.py`'s
`COMPONENT_COMPOSITION["pharmacy-invoice"]`. Unlike police-report (which has two structurally
different shapes depending on scenario), every registered scenario for this doc type resolves
to the SAME component list - a real GST tax invoice doesn't restructure by scenario in the real
world, only its content does (see the scenario-specific data-generation notes above). The
mechanism exists uniformly across every doc type for architectural consistency, even where
it isn't exercised to produce different shapes.
