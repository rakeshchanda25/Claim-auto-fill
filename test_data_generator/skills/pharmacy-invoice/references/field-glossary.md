# Pharmacy Invoice Field Glossary

- `company_name`, `company_name_line1`, `company_name_line2`, `company_legal_name`: pharmacy
  identity (line1/line2 print stacked in the logo block; legal_name is the "For {legal_name}"
  signature line, defaults to `company_name` if omitted)
- `company_address`, `company_phone`, `company_gstin`: header
- `tagline`: printed under the header
- `show_promo` (bool), `promo_text`: right-side promo banner, only shown when `show_promo`
- `document_title`: defaults to `"TAX INVOICE"`
- `copy_label`: defaults to `"ORIGINAL FOR RECIPIENT"`
- `customer_name`, `contact_person`, `customer_address`, `customer_phone`, `customer_gstin`,
  `place_of_supply`: customer detail box
- `invoice_number`, `invoice_date`: invoice meta box
- `items`: list of `{name, batch_no, mfg_date, expiry_date, hsn_sac, qty, unit, mrp, rate,
  discount_pct, taxable_value}`
- `subtotal_taxable_value`, `igst_pct`, `igst_amount`, `total_qty`, `total_rate`, `grand_total`:
  items-table totals row - see "Tax Model" in SKILL.md
- `total_in_words`: `grand_total` spelled out
- `hsn_summary`: list of `{hsn_sac, taxable_value, igst_pct, igst_amount, total}`, one per
  distinct HSN/SAC code in `items`
- `hsn_total_taxable_value`, `hsn_total_igst_amount`, `hsn_total`: HSN table totals row (equal
  to `subtotal_taxable_value`/`igst_amount`/`grand_total`)
- `tax_in_words`: `igst_amount` spelled out
- `bank_name`, `bank_branch`, `bank_account_number`, `bank_ifsc`, `upi_id`: payment block
- `terms`: list of Terms and Conditions strings
- `footer_note`: has a template default
- `logo_url`, `promo_image_url`, `qr_code_url`: all have real embedded-image template
  defaults - only supply these if you want to override the printed artwork
