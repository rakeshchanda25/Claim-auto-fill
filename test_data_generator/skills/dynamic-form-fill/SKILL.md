---
name: dynamic-form-fill
description: >
  Fill ANY fillable (AcroForm) PDF claim form with coherent synthetic data, without
  knowing the form in advance. Works on templates never seen before: discovers the
  form's own structure at runtime, decides what each field means, then fills and
  verifies. Use for mode=fill, "fill this blank form", uploaded claim forms, or any
  template with no pre-built HTML template of its own.
metadata:
  owner: idp-test-team
  version: "1"
  template: none-required
allowed-tools: inspect_pdf_form_structure inspect_region_image flow_text_into_widgets fit_grid_row fill_pdf_widgets verify_pdf_fill generate_synthetic_data
---
# Dynamic Form Fill Skill

Fill a fillable PDF you have never seen before. There is no per-template layout
map, no hardcoded field list, and no assumption about which insurer or country
the form comes from. You discover the form's structure with tools, decide what
each part means, and fill it.

## Absolute rules

1. **Never guess a field's purpose from its internal name.** Names like
   `Text Field0` / `Check Box3` are auto-generated and meaningless. Use the
   harvested `label` on each run, the `question_text` on each Yes/No pair, and
   the `section` each belongs to.
2. **Never invent widget names, coordinates, or font sizes.** Widget names come
   only from `inspect_pdf_form_structure`. Font sizing comes only from
   `flow_text_into_widgets` / `fit_grid_row`. Geometry is exactly computable, so
   it is computed for you - guessing it is always wrong.
3. **Never report success without `verify_pdf_fill`.** A fill that silently did
   not take is the failure mode this whole skill exists to prevent.
4. All data is SYNTHETIC. Never use a real person, company, or identifier.

## Workflow

### 1. Discover the structure

Call `inspect_pdf_form_structure(pdf_bytes)`. You get back:

- `runs` - one logical text answer each, possibly spanning several stacked
  widgets, with the harvested `label`, `total_capacity`, and `multiline_box`.
- `bool_pairs` - detected Yes/No checkbox pairs with the `question_text`, the
  `on_state` to use when ticking, and whether they are a radio group or two
  independent checkboxes.
- `grids` - detected repeating tables, with a `widget_matrix` (row-major) and
  `column_rects` so you can find each column's printed header.
- `sections` - the form's own printed headings, to group related answers.
- `unclassified_widgets` - anything the geometry pass could not place.

If `stats.structural_coverage_pct` is low, or a `label` is empty/ambiguous, call
`inspect_region_image` on that widget's rect and read the page yourself before
deciding. That is exactly what it is for - looking is always better than guessing.

### 2. Decide what the form is asking for

For each run / pair / grid column, decide from its label and section what it
means and what kind of value belongs there (a name, a date, money, a phone
number, a narrative explanation, an identifier, ...). The form tells you - read it.

Nothing about the answer is predetermined. Two forms asking "Postcode" and
"PIN Code" want the same kind of value; a form asking "Please describe how the
loss occurred" wants several sentences, not a word.

### 3. Choose the values

**If the user supplied values, those win.** The request may pin any subset -
a claimant name, a policy number, an amount, a date, a scenario. Use the
supplied value verbatim wherever it fits a field, and only invent the rest.
Never overwrite something the user explicitly asked for.

For everything else, generate synthetic values. You may call
`generate_synthetic_data` for a coherent starting set, but you are not limited
to its keys - a form asking for something it does not cover is normal, and you
should invent a plausible value for that field.

**Keep one coherent identity across the whole form.** Decide the claimant,
company, address, dates, and policy/claim numbers ONCE, then answer every field
consistently from that. Independently generated per-field values are what make
a filled form look obviously machine-produced: three different addresses, a
signature date before the loss date, a total that does not match the line items.

Specifically keep these coherent:
- the same person/company everywhere they are asked for;
- dates in a sensible order (loss before discovery before report before signature);
- any stated total equal to the sum of the line items above it;
- a Yes/No answer consistent with its follow-up field - if you tick "Yes, I have
  claimed before", the "give details" run must contain those details; if you tick
  "No", it should say `N/A` rather than being left blank.

Match the form's own conventions for format: if the printed text or existing
values use `DD/MM/YYYY`, use that, not `MM/DD/YYYY`.

### 4. Fit the text

- Multi-widget run, or any text that might not fit:
  `flow_text_into_widgets(pdf_bytes, widget_names=run["widgets"], text=...)`.
- One grid row: `fit_grid_row(pdf_bytes, widget_names=[...], cell_texts=[...])`
  - it returns one font size for the whole row, which is what you want.
- Short value in a wide box: put it straight in `widget_values` with no font.

Merge every returned `values` / `fonts` into two accumulating dicts. Surface any
returned `warnings` in your final answer rather than dropping them.

### 5. Answer the Yes/No pairs

For each pair, set the ticked widget to the pair's `on_state` (NOT the string
`"Yes"` - the real on-state is whatever the form's author used) and explicitly
set the other to `/Off`. Setting only one leaves the other in an undefined state.

### 6. Fill, verify, report

```
filled = fill_pdf_widgets(pdf_bytes, widget_values, widget_fonts, watermark=...)
result = verify_pdf_fill(filled, widget_values)
```

If `result["ok"]` is false, fix the mismatched widgets and fill again. Do not
return a PDF whose verification failed without saying so explicitly.

## When this skill does not apply

`inspect_pdf_form_structure` raises if the PDF has no `/AcroForm`. A flat
digital or scanned PDF has no fillable widgets at all, so there is nothing to
fill - say so plainly rather than producing an unchanged file. Those need a
different strategy (coordinate overlay or regeneration), which this skill does
not implement.
