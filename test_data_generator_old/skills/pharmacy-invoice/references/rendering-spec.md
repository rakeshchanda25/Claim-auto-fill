# Pharmacy Invoice Rendering Specification

- Page Size: A4 Portrait, 0.4-0.45in margins
- Typography: Arial/Helvetica 9pt
- Color Theme: Green (`#3fa044` / `#2f7d34` dark / `#eef8ee` pale), 2px green border around the
  whole invoice
- Header: logo mark + stacked company name lines + address/phone, optional right-side promo
  banner, centered tagline bar
- GSTIN/title row: GSTIN left, large green "TAX INVOICE" title center, copy label right
- Customer detail (left) + invoice meta (right) two-column box
- Items table: green header row (white text), 11 columns (Sr./Name/Batch/MFG/Expiry/HSN/Qty/
  MRP/Rate/Disc/Taxable Value), subtotal + IGST + bold total row
- HSN/SAC summary table: pale-green header, grouped by HSN code
- Bank/UPI block (left) with embedded QR code image, Terms and Conditions, customer signature;
  certification text + "Authorised Signatory" (right)
