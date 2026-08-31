# Litigation Document IDP Test Scenarios

- `slip_and_fall`: Premises liability complaint - `causes_of_action` always includes
  "Premises Liability".
- `medical_malpractice`: Provider negligence complaint - `causes_of_action` always includes
  "Negligence" (the pool has no "Medical Malpractice" label; "Negligence" is the malpractice-
  appropriate cause here).
- `product_liability`: Defective-product complaint - `causes_of_action` always includes
  "Strict Product Liability".

Each scenario's anchor cause is guaranteed present; the remaining 1-2 causes in the 2-3-item
list are still randomly sampled from the rest of the pool for variety. See "Causes of Action
Pool" in SKILL.md.
