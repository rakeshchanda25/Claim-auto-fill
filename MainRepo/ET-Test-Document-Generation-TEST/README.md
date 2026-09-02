# IDP Test Data Generator

Creates realistic insurance and medical documents for testing **Intelligent Document Processing**
systems — either generated from scratch by an AI agent, or built by editing and degrading PDFs you
already have.

---

## What it does

### AI Document Generator

Three modes, all driven by an [Andromeda](../../../andromeda) agent:

| Mode | What it does |
|---|---|
| **Generate** | Builds a new document of a chosen type and scenario from scratch. |
| **Recreate** | Takes a document you upload and retells it under a different scenario — same people and identifiers, new clinical/legal/financial content. |
| **Packet** | Builds a whole set of related documents that all describe one claim, delivered as a ZIP. |

**13 document types**: medical record, medical bill, discharge summary, CMS-1500, UB-04, EOB,
ACORD 25, police report, demand letter, litigation document, pharmacy invoice, property loss
notice, auto accident report.

**5 packets**: medical, auto accident, property claim, litigation, pharmacy.

**Live claim data.** Paste a claim number (e.g. `000-00-053109`) into the input box and the real
claim is pulled from Guidewire ClaimCenter: the insured, loss date, location, policy details, the
adjuster's notes, and excerpts from documents already attached to the claim. Real values take
priority; anything the claim does not cover is still generated. If the lookup fails, generation
continues with synthetic data.

### PDF utilities

- **Text Replacer** — find-and-replace values in any digital PDF.
- **Scanner Simulator** — skew, blur, sensor noise, low DPI, rotation and overlays, to make a clean
  PDF look like it came off a physical scanner.
- **Combiner** — merge PDFs with per-file page ranges, reordering and preview.

---

## Setup

```bash
cd test_data_generator
pip install -r requirements.txt
```

The agent framework is installed separately, from the Andromeda repository:

```bash
pip install -e path/to/andromeda
```

WeasyPrint needs system libraries (Pango, cairo, GDK-PixBuf). They are present on most Linux
distributions; on Windows and macOS see the
[WeasyPrint install guide](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation).
Only PDF rendering needs them — everything else, including the test suite, runs without.

There is no `.env` file — configuration is hardcoded. Agent settings (model, sandbox,
guardrails, prompt) live in `test_data_generator/.andromeda/agents/doc-generator.yaml`;
the Guidewire host and credentials are constants at the top of `test_data_generator/app.py`.

```bash
python run_server.py
```

Then open <http://127.0.0.1:8420>.

---

## How generation works

```
Browser ──▶ /api/ai-generate ──▶ Guidewire lookup (if a claim number was given)
                                        │
                                        ▼
                          claim facts staged server-side
                                        │
                                        ▼
                    Andromeda agent ──▶ tools ──▶ Jinja template ──▶ WeasyPrint ──▶ PDF
```

Claim facts and the uploaded reference are **staged before the agent starts**, not passed through
the prompt. A prompt is text a model interprets rather than code it executes, so a large dict
embedded in one can be dropped or truncated. The tools read the staged context directly, so the
data applies regardless of what the model puts in its tool calls. Tool arguments for the same
values still exist as an additive safety net — anything the model passes merges on top.

Two details that are easy to get wrong, and are handled centrally:

- **Every document names the claimant differently** — `patient_name`, `claimant_name`,
  `plaintiff_name`, `customer_name`, or nested under `employee` / `parties_involved`. One alias
  table in `ai_doc_generator/tools.py` maps them, so a packet's documents agree with each other.
- **Dates are anchored before generation, not patched after.** The claim's loss date seeds the
  generator, so every derived date — report date, service dates, the year inside a case number —
  moves with it. A report can never predate the loss it reports.

---

## Layout

```
test_data_generator/
├── .andromeda/agents/doc-generator.yaml   # all agent settings live here
├── app.py                                 # FastAPI routes
├── guidewire.py                           # ClaimCenter client
├── run_server.py
├── pdf_manager.py                         # text replace + combine
├── scanner_simulator.py                   # scan degradation
├── ai_doc_generator/
│   ├── agent_factory.py                   # builds the agent, owns the run lifecycle
│   ├── tools.py                           # the 8 tools the agent calls
│   ├── prompt_builder.py                  # per-mode prompts
│   ├── registry.py                        # document types, packets, scenarios
│   └── config.py
├── renderers/
│   ├── synthetic_data.py                  # the data behind every document
│   ├── components.py                      # which sections each scenario uses
│   ├── html_renderer.py
│   ├── docx_parser.py
│   └── templates/                         # 13 Jinja templates
├── skills/                                # per-type field glossaries the agent loads
├── frontend/
└── tests/
```

### Adding a document type

Touch these six places, in order:

1. `renderers/templates/<name>.html` — the template, as named macros.
2. `renderers/components.py` — which macros each scenario assembles.
3. `renderers/synthetic_data.py` — a data branch producing its fields.
4. `ai_doc_generator/tools.py` — its entry in `_REQUIRED_FIELDS`.
5. `ai_doc_generator/registry.py` — its entry in `DOC_TYPES`.
6. `skills/<name>/SKILL.md` — the field glossary the agent reads.

The test suite checks 1, 4, 5 and 6 exist for every registered type, so a half-finished addition
fails rather than producing a blank document.

---

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/ai-generate` | Generate, recreate, or build a packet. Returns a PDF or a ZIP. |
| `POST` | `/api/ai-analyze-reference` | Inspect an uploaded PDF/DOCX's structure. |
| `GET` | `/api/ai-doc-types` | Document types, packets and scenarios. |
| `POST` | `/api/replace` | Replace text in a PDF. |
| `POST` | `/api/simulate-scan` | Apply scan degradation. |
| `POST` | `/api/combine` | Combine PDFs with page selection. |
| `GET` | `/api/health` | Health check. |

---

## Tests

```bash
cd test_data_generator
python -m pytest tests/ -q
```

292 checks. Every document type renders through its real template with
`StrictUndefined`, so a field the template reads and the data layer never sets fails the build
rather than leaving a blank space in a PDF. Packets are checked for internal agreement, claim data
is checked end-to-end against a captured API response, and the agent config is checked to load
and to resolve its sandbox backend to one the framework actually accepts.

PDF generation itself is not covered — WeasyPrint is the one step with no project logic in it, and
requiring its system libraries would make the suite unrunnable on most dev machines.
