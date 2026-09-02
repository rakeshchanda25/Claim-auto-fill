# Plan — port the AI document generation solution into MainRepo

## Where we are

`MainRepo/ET-Test-Document-Generation-TEST/` is the clean pre-AI baseline: 9 files, ~1,700 lines.
It does text-replace, scan-simulation and PDF-combine, with a vanilla-JS frontend. No AI, no
renderers, no Guidewire.

The mature solution living in `ClaimDocuGen/test_data_generator/` adds ~13,000 lines across 90
files: three generation modes (generate / recreate / packet), 13 document types, 5 packets,
a Guidewire claim lookup, an Andromeda agent, and a skills tree.

The job is to bring that capability into MainRepo **as a clean implementation** — not a copy.
Everything ported has to justify itself.

## Principles applied

1. **Ported ≠ copied.** Every module is reviewed on the way in; dead paths and speculative
   parameters are dropped, not carried.
2. **One source of truth for config.** Andromeda's `WorkspaceAgentConfig.load_from_file()`
   supports YAML with `${VAR:default}` interpolation — so agent settings live in
   `.andromeda/agents/doc-generator.yaml` only, not duplicated in Python.
3. **Structural correctness over prompt instructions.** Where the prompt currently *tells* the
   model not to do something, remove the parameter that lets it.
4. **Comments earn their length.** The hard-won "why" stays; the 30-line essays become 3 lines.
5. **One runnable check** covering the logic that actually broke before.

## What gets cut, and why

| Cut | Lines | Reason |
|---|---|---|
| `ai_doc_generator/guardrail_diagnostics.py` | 104 | Monkey-patches three shared Andromeda framework classes at runtime to log guardrail matches. The bug it was written to diagnose is already fixed by the `data_patterns` override in the agent config. Patching a shared package's internals from an app is the opposite of a best practice. |
| `app.py` legacy base64-JSON result path | ~57 | Unreachable. Every mode now stages its output server-side (`get_staged_artifact` / `get_staged_packet`), and both are checked before this branch. It parses `pdf_bytes_b64` / `docx_bytes_b64` out of model text that the model is explicitly told never to produce. |
| `guidewire.py` — 13 unused methods | ~450 | `activities`, `history_events`, `exposures`, `vehicle_incidents`, `reserves`, `payments`, `checks`, `get_group_summary`, `get_claim_identity_summary`, `compute_claim_state_hash`, `search_claim_documents_summary`, `get_claim_state_payload`, `_transaction_amounts`. Only `claim_details`, `policy_details`, `notes`, `contacts` and `document_searches` feed `fetch_claim_facts`. **This also removes 7 serial HTTP round-trips from every claim lookup.** |
| `data=` param on `render_document_to_pdf` / `validate_document_structure` | — | The system prompt spends four sentences telling the model never to pass these. Deleting the parameter enforces it structurally and shortens the prompt. |
| `count` form field on `/api/ai-generate` | — | Accepted, parsed, threaded into `GenerationRequest`, never read. |
| `reportlab` dependency | — | Not imported anywhere. |

## What gets improved

- **Guidewire lookup goes concurrent.** The five summaries it needs are independent HTTP calls
  currently made serially inside `get_claim_background_context`. A `ThreadPoolExecutor` turns
  five sequential round-trips into one wall-clock round-trip. Combined with the seven calls
  removed above, claim lookup drops from 12 serial requests to 5 parallel ones.
- **Model config becomes environment-driven** (`${DOC_AGENT_MODEL:openai/qwen3.6:27b}`) instead
  of hardcoded in two places that already disagree with each other.
- **`.env.example`** documents every variable the app reads.

## What gets ported as-is

These are already correct and complete; rewriting them would only add risk:

- `renderers/templates/*.html` (13) — the component-macro decomposition is fully wired: every
  template defines named macros and dispatches through a `component_map`.
- `renderers/components.py`, `renderers/synthetic_data.py`, `renderers/docx_parser.py`
- `skills/` (13 doc types × SKILL.md + 3 reference files)
- `ai_doc_generator/packets.py`
- `pdf_manager.py`, `scanner_simulator.py` (already in the baseline, unchanged)

## Target structure

```
ET-Test-Document-Generation-TEST/
├── .env.example
├── README.md
└── test_data_generator/
    ├── .andromeda/
    │   ├── andromeda.yaml
    │   └── agents/doc-generator.yaml     # single source of agent config
    ├── app.py                            # baseline routes + 3 AI routes
    ├── guidewire.py                      # trimmed client + concurrent fetch
    ├── run_server.py
    ├── pdf_manager.py                    # unchanged from baseline
    ├── scanner_simulator.py              # unchanged from baseline
    ├── requirements.txt
    ├── ai_doc_generator/
    │   ├── agent_factory.py              # YAML-driven, no inline config
    │   ├── config.py
    │   ├── packets.py
    │   ├── prompt_builder.py
    │   └── tools.py
    ├── renderers/
    │   ├── components.py
    │   ├── docx_parser.py
    │   ├── html_renderer.py
    │   ├── synthetic_data.py
    │   └── templates/*.html              # 13
    ├── skills/                           # 13 × 4 files
    ├── frontend/                         # baseline UI + AI Generator tab
    └── tests/
        ├── fixtures/guidewire_claim.json
        └── test_documents.py
```

## Build order

1. Scaffolding — dirs, `requirements.txt`, `.env.example`, `.andromeda/` YAML.
2. `renderers/` — synthetic_data, components, html_renderer, docx_parser, 13 templates.
3. `ai_doc_generator/` — config, packets, tools, prompt_builder, agent_factory.
4. `guidewire.py` — trimmed, concurrent.
5. `app.py` — extend the baseline with the three AI routes.
6. `frontend/` — add the AI Generator tab to the existing UI.
7. `skills/`.
8. `tests/`.
9. README.

## Verification

- `python -m pytest tests/ -q` — every `(doc_type, scenario)` pair builds and renders through
  the real Jinja templates under `StrictUndefined`; packet identity/date consistency asserted.
- `python -m pyflakes .` — clean.
- Import-and-route check: app imports, all routes registered, `/api/ai-doc-types` returns the
  full registry.
- **Not verifiable here:** WeasyPrint cannot import on this Windows machine, so PDF bytes are
  never produced locally — tests render to HTML through the same Jinja environment instead.
  Final PDF confirmation stays on the Linux VM, as with every prior change to this project.
