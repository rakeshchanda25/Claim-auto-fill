# Plan — per-jurisdiction / per-issuer document layouts

## The problem, stated precisely

Today every police report we generate is visually identical. So is every medical record. For an
IDP test set that is a real defect: an extractor trained or evaluated against it will look far
more robust than it is, because it only ever sees one layout per document type.

But "make it vary" is not one problem. There are **three different axes**, and they need
opposite treatment:

| Tier | Document types | Varies by | Should it vary? |
|---|---|---|---|
| **1. National standard forms** | ACORD 25, CMS-1500, UB-04 | nothing | **No — must stay fixed** |
| **2. Jurisdictional forms** | police report, accident report, property loss notice | **US state** | Yes |
| **3. Issuer house style** | medical record, medical bill, discharge summary | **hospital / EHR vendor** | Yes |

### Tier 1 is already correct, and must be protected

A CMS-1500 is a fixed OMB form. A UB-04 is defined by the NUBC. An ACORD 25 is an ACORD
standard. Their box positions are the same in all 50 states — that is the entire point of them.

So the current fixed template is not a limitation there, it is correct. Worth making explicit:
**this plan must not let these vary**, and there should be a test asserting it. Varying a
CMS-1500 would produce invalid test data, not diverse test data.

### Tier 2 is bounded, not infinite

This is the important correction to "50 states, 50 unknowns". Each state has **one** official
crash report form, with a real name and form number — for example CA's CHP 555, TX's CR-3,
NY's MV-104A. So Tier 2 is not open-ended creativity: it is ~50 *specific, knowable* forms.

That means we can get the field names, section ordering and form numbers genuinely right, which
matters if this test data is ever used to evaluate a real extractor.

> **Verify before shipping:** I am working from general knowledge for the form numbers above. Each
> one should be checked against the state's actual published form before it goes into a profile,
> or we will be generating confidently-wrong test data.

### Tier 3 is genuinely open-ended

There is no official "medical record" form. Layout follows the hospital and its EHR — an Epic
chart note, a Cerner note and a Meditech note look visibly different. Here the variation axis is
the **issuer**, not the state, and the space really is unbounded.

---

## The constraint that shapes everything: ground truth

This is a test-data generator. Its output is only useful if we know **exactly what each document
contains**, so extraction can be scored against it.

So the non-negotiable rule:

> **Data is generated deterministically. Only layout varies. The model never invents a field value.**

Today `synthetic_data.py` produces the values and `StrictUndefined` guarantees the template can't
reference a field that doesn't exist. If we let a model write documents freely, we lose both
guarantees at once — it could silently omit `claim_number`, or invent a second patient name, and
nothing would catch it.

Everything below is built to keep data and layout strictly separate.

---

## Recommended design: the agent authors a **template**, not a document

Your instinct — let the agent write the HTML — is right. One refinement makes it much stronger:

**The agent writes a reusable Jinja template, which we cache — not a finished document.**

```mermaid
flowchart TD
    REQ["police report, state = TX"] --> CACHE{"cached layout<br/>for TX?"}
    CACHE -->|yes| RENDER
    CACHE -->|no| GEN["agent authors a Jinja template<br/>for the TX CR-3 form"]
    GEN --> GATE{"validation gate"}
    GATE -->|fails| FB["fall back to the<br/>generic template"]
    GATE -->|passes| SAVE["cache as layouts/police-report/TX.html"]
    SAVE --> RENDER["render with THIS claim's data"]
    FB --> RENDER
    RENDER --> PDF["PDF"]

    style GEN fill:#5a4a1a,color:#fff
    style GATE fill:#1a4f6f,color:#fff
    style SAVE fill:#1a5f3f,color:#fff
```

Why a template rather than a finished document:

| | Agent writes finished HTML per document | Agent writes a cached template per state |
|---|---|---|
| Cost | one LLM call **per document** | one call **per state, ever** |
| Reproducible with a seed | no | **yes** |
| Ground truth | must re-derive from output | **unchanged — data layer still owns it** |
| Reviewable / hand-editable | no | **yes, it is a file** |
| Packet of 5 docs | 5 authoring calls | 0 (all cached) |
| Variety across states | high | **high — same thing** |

You get the same visual diversity, because the diversity lives in the layout, and each state gets
its own. You just stop paying for it on every single document.

The cache is a plain directory of `.html` files. Anyone can open `layouts/police-report/TX.html`,
fix a heading, and commit it. Over time the good ones become hand-maintained assets and the agent
is only invoked for states nobody has done yet.

---

## The validation gate (this is what makes it safe)

A generated template is **not trusted** until it passes, in this order:

1. **Renders** — Jinja parses it and it renders under `StrictUndefined` against a probe data dict.
   Catches references to fields that don't exist.
2. **Field audit** — every value in `_REQUIRED_FIELDS[doc_type]` must appear in the rendered
   output. This is the replacement for the guarantee we'd otherwise lose: a layout that silently
   drops the claim number is **rejected**, not cached.
3. **Prints** — WeasyPrint produces a PDF over a page-count sanity range. Catches CSS that
   explodes into 400 pages.
4. **Not a copy** — its structural fingerprint differs from the generic template, or we have
   gained nothing.

Fail any check → discard, fall back to today's template, and record why. The system degrades to
current behavior instead of producing a broken document.

---

## Where the skill files fit

You were right that this belongs in the skills. Today:

```
skills/police-report/
├── SKILL.md
└── references/
    ├── field-glossary.md
    ├── rendering-spec.md
    └── test-scenarios.md
```

`rendering-spec.md` currently describes **one** design ("dark navy `#14304f` title bar reading
TRAFFIC COLLISION REPORT"). That is exactly the file that hard-codes the sameness.

The change:

- **`rendering-spec.md`** is reframed from *"this is the design"* to *"these are the design
  invariants"* — page size, the SPECIMEN watermark, the synthetic-data footer, minimum legibility.
  Things that must hold for **every** variant.
- **New `references/jurisdictions.md`** — the per-state knowledge: form name, form number, issuing
  agency, section ordering, notable quirks. This is what the agent reads to author a faithful TX
  form instead of a generic one.
- **`SKILL.md`** gains a short "Layout variants" section pointing at both.

For Tier 3, the same shape but the file is `references/issuers.md` (Epic / Cerner / Meditech
house styles) instead of `jurisdictions.md`.

---

## Code changes

### New: `renderers/layouts.py`
Cache lookup and storage. `get_layout(doc_type, key) -> template_name | None`, plus
`save_layout(...)` gated on validation. Owns the `layouts/` directory.

### New: `renderers/layout_validator.py`
The four checks above. Pure functions, no LLM, fully unit-testable — this is the piece that has
to be trustworthy.

### New tool: `author_layout(doc_type, jurisdiction)`
Only tool that writes HTML. Called by the agent only on a cache miss.

### `renderers/synthetic_data.py`
Promote the variation key to a real field. Police report already picks
`report_state = random.choice(_STATES)` at line 1180 — it just doesn't reach the template. Expose
it as `layout_key` so the renderer can dispatch on it. Medical types get an issuer instead.

### `renderers/html_renderer.py`
`render_html(template_name, data)` first checks for a cached layout matching `data["layout_key"]`
and falls back to the generic template. Roughly a five-line change — this is the only place that
needs to know variants exist.

### `ai_doc_generator/registry.py`
Mark each doc type's tier: `"layout_axis": None | "state" | "issuer"`. `None` means Tier 1 and is
never varied.

### `ai_doc_generator/tools.py`
`_REQUIRED_FIELDS` becomes the contract the field audit enforces. No structural change.

---

## Rollout

1. **Guard Tier 1 first.** Add the test asserting ACORD-25 / CMS-1500 / UB-04 never resolve to a
   variant layout. Do this before anything else exists, so it can't regress.
2. **Build the validator**, with tests, against hand-written good and deliberately broken
   templates. No LLM involved yet.
3. **Cache plumbing + renderer dispatch**, with two hand-written police-report layouts (say CA and
   TX). Still no LLM. At this point the system already produces two visibly different police
   reports — worth confirming that alone looks right before adding generation.
4. **`author_layout` tool + `jurisdictions.md`** for police-report only. Generate a handful of
   states, review the HTML by eye, iterate on the skill text until output is consistently good.
5. **Backfill states** in bulk, then hand-correct.
6. **Tier 3** (medical, issuer axis) reusing the whole mechanism.

Stopping after step 3 already gets you most of the value if the LLM authoring proves fiddly. That
is deliberate — each step is useful on its own.

---

---

## Decisions (locked)

| Question | Decision |
|---|---|
| Coverage | **All 50 states** |
| State selection | **Selectable in the UI** (not random) |
| Fidelity | **Field-level faithful** to the real state form (e.g. TX CR-3) |
| Specimens | None on hand — **source the official forms from the web** |

Field-level fidelity is the decision that reshapes the plan. A model writing a "TX-looking" form
from memory will invent field names and box numbers with total confidence. At field-level
fidelity that is not a cosmetic flaw, it is wrong test data. So the layout can no longer be
authored from the model's memory — **it has to be derived from the real published form.**

That makes sourcing the critical path, not rendering.

---

## Sourcing pipeline (feasibility verified)

Tested end to end against Texas before writing this:

| Step | Verified |
|---|---|
| States publish the forms | ✅ TxDOT publishes CR-3, the CR-3CS code sheet, and CR-100 "Instructions to Police" |
| `WebFetch` can retrieve them | ✅ cannot parse a PDF, but **saves the file to disk**, which is all we need |
| Text is extractable | ✅ `pymupdf` → 177 pages, ~75k chars of clean text |
| Field-level detail is present | ✅ "MANDATORY DATA FIELD" ×41, "Contributing Factor" ×26, "Unit Number" ×16, "VIN" ×17 |

The instructions manual (CR-100) matters more than the form PDF itself: it names and defines every
field in readable prose, whereas the blank form is mostly boxes and rules.

```mermaid
flowchart LR
    M["state_forms.yaml<br/>manifest of 50 source URLs"] --> DL["download PDF"]
    DL --> TX["pymupdf → text"]
    TX --> EX["agent extracts a<br/>structured field spec"]
    EX --> SPEC["skills/police-report/<br/>references/states/TX.md"]
    SPEC --> AUTH["agent authors<br/>layouts/police-report/TX.html"]
    AUTH --> GATE{"validation gate"}
    GATE -->|pass| USE["cached, reused for<br/>every TX document"]
    GATE -->|fail| FB["fall back to generic"]

    style EX fill:#5a4a1a,color:#fff
    style GATE fill:#1a4f6f,color:#fff
    style USE fill:#1a5f3f,color:#fff
```

Two artifacts per state, and they are deliberately separate:

- **`references/states/TX.md`** — the *knowledge*: form number, issuing agency, section order,
  field labels, code lists. Reviewable prose. This is the thing that must be accurate.
- **`layouts/police-report/TX.html`** — the *rendering* of that knowledge. Regenerable from the
  spec at any time, so a bad layout is cheap to redo without re-sourcing.

### Version pinning

TxDOT alone has CR-3 revisions for 2010, 2015, 2017, 2018 and 2023, and they differ. The manifest
must pin **form number + revision date + source URL + retrieval date** per state, or the corpus
becomes unreproducible and nobody will know which revision a document was modelled on.

---

## Answering "can this be config in the skill, or does it need templates?"

Both — they are three different things, and only one of them is config:

| Layer | Where it lives | Config or artifact? |
|---|---|---|
| The 50-state **picker** in the UI | `registry.py` list + a `<select>` | **Pure config.** No templates. |
| The per-state **field spec** | `skills/police-report/references/states/TX.md` | **Config, in the skill** |
| The per-state **layout** | `renderers/layouts/police-report/TX.html` | **Artifact.** Cannot be skill config. |

Why the layout cannot live in the skill — two hard limits in the framework, both checked:

1. `read_skill_file` rejects any path that is not `.md` (`skills.py:445`), so an `.html` layout
   cannot be read through the skills mechanism at all.
2. A skill file is *text the model reads*. It is not something the renderer can execute. Jinja
   templates have to be on the render path.

There is also a context limit that decides the file layout. `load_skill` returns **only SKILL.md**
— it does not auto-load `references/*.md`. So 50 states of field-level detail cannot sit in one
skill file; it would be enormous and loaded on every single call. Splitting it as
`references/states/<CODE>.md` and having the agent `read_skill_file` **only the state it needs**
is what makes 50 states affordable.

---

## Revised rollout

The code is roughly 20% of this. Sourcing and verifying 50 forms is the other 80% — worth being
clear-eyed about that up front.

**Phase 1 — Guard rails (no LLM, no web).**
Tier 1 lock test (ACORD-25 / CMS-1500 / UB-04 never vary). Build `layout_validator.py` with tests
against hand-written good and deliberately broken templates.

**Phase 2 — Plumbing (no LLM, no web).**
`layouts.py` cache + renderer dispatch + `layout_key` on the data + UI picker. Ship with **two
hand-written** states. At this point two visibly different, selectable police reports exist end to
end. Confirm that looks right before automating anything.

**Phase 3 — Sourcing, one state.**
`state_forms.yaml` manifest, a `fetch_state_form` step, and the extraction prompt — for Texas
only, since it is already proven. Hand-check `TX.md` against the real CR-3 line by line. This is
the quality bar every other state is measured against.

**Phase 4 — Authoring, one state.**
`author_layout` produces `TX.html` from `TX.md`. Iterate the skill text until output is
consistently good. Compare side by side with the real form.

**Phase 5 — Scale to 50.**
Work in batches of ~10, newest revision only. Expect roughly: a third clean, a third needing
manual correction, a third with poor source documents needing hand-authoring. Every state's spec
gets human review before it is trusted — the whole point of this tier is fidelity, and an
unreviewed spec has none.

**Phase 6 — Tier 3 (medical, issuer axis)**, reusing the entire mechanism with `issuers.md`.

---

## Two things to hold onto as fidelity rises

- **The SPECIMEN watermark and the synthetic-data footer become more important, not less.** At
  "recognizably Texan" they were courtesy. At field-level fidelity to a real police form they are
  the thing that distinguishes test data from a forged government document. They belong in the
  design invariants that every generated layout must satisfy, and the validator should check for
  them rather than trusting the model to include them.
- **Source documents are public government forms**, which is what makes this sourcing approach
  legitimate. Record the source URL and retrieval date per state in the manifest so the provenance
  of every layout is traceable.
