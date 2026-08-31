# Pharmacy Invoice IDP Test Scenarios

- `chronic_medication`: items drawn from the standard maintenance-drug pool (Lisinopril,
  Atorvastatin, Metformin, etc.), $50-800/unit, 2-4 items.
- `specialty_drug`: items drawn from a biologics pool (Humira, Enbrel, Ozempic, Ocrevus),
  $1,500-6,500/unit, 1-2 items, unit is a syringe/vial/auto-injector (not Strip/Bottle/Box).
- `compounded_medication`: items drawn from a "Compounded ..." custom-formula pool,
  $300-1,200/unit, 2-4 items, HSN 3003 (not mixed/dosed) instead of 3004.

Each scenario's item pool is disjoint from the others (no drug name appears in more than one
pool) - see `synthetic_data.py`'s pharmacy-invoice branch. Any other scenario falls back to
the `chronic_medication` pool/pricing.
