---
name: dynamic-docx-fill
description: >
  Fill ANY .docx that has real Word content-control form fields (w:sdt) with
  coherent synthetic data, without knowing the template in advance. Discovers
  the document's own controls at runtime, decides what each one means, then
  fills and verifies. Use for mode=fill with a .docx reference file, "fill
  this Word form", or any uploaded .docx with fillable content controls.
metadata:
  owner: idp-test-team
  version: "1"
  template: none-required
allowed-tools: inspect_docx_form_structure fill_docx_form_controls verify_docx_fill generate_synthetic_data
---
# Dynamic Docx Fill Skill

Fill a Word document you have never seen before. There is no per-template
field list. You discover the document's real content controls with tools,
decide what each one means, then fill it.

This is the docx counterpart of `dynamic-form-fill` (which handles PDF
AcroForm widgets). The split is the same: structure discovery is exact and
deterministic, so it's a tool; meaning is yours to decide. The one real
difference is that docx is a flow document, not fixed boxes - Word grows the
paragraph to fit whatever text you put in, so there is no font-fitting step
here at all.

## Absolute rules

1. **Never guess a control's purpose from its raw `tag`.** Use the harvested
   `label` (the control's own `alias` if the template author set one - that
   IS the human-readable name they gave the field - else nearby paragraph or
   table-cell text).
2. **Never invent control names or dropdown/comboBox options.** Names come
   only from `inspect_docx_form_structure`. For a dropdown/comboBox, the
   value you pick MUST be exactly one of that control's own `choices[].display`
   - `fill_docx_form_controls` raises if it isn't. Never offer an option the
   template doesn't have.
3. **Never report success without `verify_docx_fill`.** A fill that silently
   did not take is the failure mode this skill exists to prevent.
4. All data is SYNTHETIC. Never use a real person, company, or identifier.

## Workflow

### 1. Discover the structure

Call `inspect_docx_form_structure(docx_bytes)`. You get back a `controls`
list, each with:

- `type` - one of `text`, `richText`, `date`, `checkbox`, `dropdown`, `combobox`.
- `label` - the harvested context (the control's `alias`, or nearby text).
- `choices` - for dropdown/comboBox only: the exact selectable list.
- `current_text` / `checked` - what the control holds right now (usually a
  placeholder or blank).

If `stats.controls` is 0, the document has no content controls at all - see
"When this skill does not apply" below.

### 2. Decide what each control is asking for

Read `label` (and `alias`/`tag` if `label` is thin) the same way you'd read a
form: a name, a date, money, a narrative, an identifier. The document tells
you what it wants.

### 3. Choose the values

**If the user supplied values, those win** - use them verbatim wherever they
fit a control, and only invent the rest.

Otherwise generate synthetic values (`generate_synthetic_data` is a good
starting set, but you're not limited to its keys). **Keep one coherent
identity across the whole document**: same person/company everywhere, dates
in a sensible order, any stated total matching its line items, a checkbox
consistent with its neighboring text control (if "Yes" is checked, the
"details" control should have details; if "No", `N/A` rather than blank).

For a dropdown/comboBox, pick one of `choices[].display` - not the internal
`value`, the `display` text is what actually gets written.

### 4. Fill, verify, report

```
filled = fill_docx_form_controls(docx_bytes, values={...}, checks={...}, choices={...})
result = verify_docx_fill(filled, {**values, **checks, **choices})
```

`values` is name -> text (text/richText/date controls). `checks` is name ->
bool (checkbox controls - the actual checked glyph and font come from the
control's own definition, never assume "X"). `choices` is name -> the chosen
`display` string (dropdown/comboBox controls).

If `result["ok"]` is false, fix the mismatched controls and fill again. Do
not return a docx whose verification failed without saying so explicitly.

## When this skill does not apply

A `.docx` with zero content controls (plain prose, or a table meant to be
read/typed into manually with no real form fields) has nothing this skill can
address - `inspect_docx_form_structure` reports `stats.controls == 0` rather
than erroring. Say so plainly. That document needs a different strategy
(e.g. `analyze_reference_document` to extract its layout/style and regenerate
a new document from scratch), which this skill does not implement.
