# PDF Test Data Generator

A web-based tool for creating realistic test documents for **Intelligent Document Processing (IDP)** AI systems. Edit and degrade existing PDFs, combine multiple documents, or generate entirely new synthetic insurance documents (single files or full multi-document claim packets) — optionally seeded with a real claim pulled live from **Guidewire ClaimCenter**.

---

## Features

### Generator & Converter
- **Text Replacer** - Upload any digital PDF and replace specific text values (names, claim numbers, dates, policy numbers, etc.) with new values using a simple find-and-replace UI.
- **Scanner Simulator (Converter)** - Apply realistic scan degradations to the edited PDF to simulate physical scanned documents:
  - **Skew** - Random rotation with adjustable angle (0.5°- 5°)
  - **Blur** - Gaussian blur with adjustable strength (1px-15px)
  - **Noise** - ISO sensor noise with adjustable intensity (5- 50)
  - **Low DPI** - Downscale and re-upscale to simulate cheap scanner hardware

### Combiner Utility
- Upload multiple PDFs and combine them into a single document.
- **Page Range Selection** - Choose specific pages per file (e.g., `1-3, 5, 7-9`). Leave blank or type `all` to include all pages.
- **Duplicate Segments** - Add the same PDF multiple times with different page ranges for each occurrence.
- **Reorder Cards** - Use ↑ / ↓ buttons to arrange the combine order before merging.
- **Remove Segments** - Remove any card from the combine queue.
- **PDF Preview** - Click "Preview" on any card to open the full PDF in a modal viewer before combining.

### AI Document Generator
Generates brand-new synthetic insurance documents from scratch, powered by an LLM agent (built on the shared `andromeda` framework) plus deterministic Faker/Jinja2 rendering. Three modes:

- **Generate** - Pick a document type and scenario; the agent produces internally-consistent synthetic data (dates, names, identifiers, scenario-specific narrative) and renders it to PDF via a component-based Jinja2 template system, so a document's actual *structure* (which sections exist) varies correctly by scenario - not just its values.
- **Recreate** - Upload a reference document (PDF/JPG/PNG/TIFF/DOC/DOCX); the agent analyzes it, carries over the identifying values (claimant, dates, policy/claim numbers), and re-generates everything scenario-specific fresh.
- **Build Packet** - Generates a full multi-document claim packet in one go (e.g. an auto-accident claim's police report + loss notice + ER visit notes + ER bill + ACORD certificate), with the claimant, claim number, incident date, and location kept consistent across every document in the packet.

13 document types (Medical Record, Medical Bill, Discharge Summary, CMS-1500, UB-04, EOB, ACORD 25, Police Report, Demand Letter, Litigation Document, Pharmacy Invoice, Property Loss Notice, Auto Accident Report) across 5 packet types (Medical Claims, Auto Accident, Property Damage, Litigation Support, Pharmacy Claims), each backed by its own skill definition under `skills/`.

**User Input & Guidewire claim lookup** - A free-text box on the AI Generator tab accepts either plain instructions or a claim ID/number. If a claim ID/number is detected, the app looks it up live in Guidewire ClaimCenter (`guidewire.py`) and uses real claim/policy values (claimant name, claim/policy number, loss date/type/cause, location, adjuster, jurisdiction, etc.) wherever a document has a matching field - Guidewire data takes priority, Faker fills in whatever Guidewire doesn't have. A real `loss_date` also anchors every generated date field (report date, service dates, etc.) so nothing lands in the wrong year relative to the real incident. A failed/unreachable Guidewire lookup logs a warning and falls back to full synthetic generation rather than failing the request.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| AI Agent | `andromeda` agent framework (LangChain/LangGraph-based), litellm |
| Document Rendering | Jinja2 (component-based templates), WeasyPrint (HTML → PDF) |
| Synthetic Data | Faker |
| Claim Data Source | Guidewire ClaimCenter REST API (`guidewire.py`) |
| PDF Processing | PyMuPDF |
| Image Processing | OpenCV (`opencv-python-headless`), NumPy |
| Frontend | HTML5, Vanilla CSS, Vanilla JavaScript |

> **Note:** WeasyPrint requires native Pango/cairo libraries that don't install on Windows - PDF rendering (and the full AI agent, which depends on the `andromeda` package) only runs on Linux. On Windows, `renderers/synthetic_data.py`, `app.py`, and most of the backend still import and run fine for development/testing; only the actual PDF-producing calls (`render_document_to_pdf`, `render_packet`) and the LLM agent itself require the Linux environment.

---

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/pdf-test-generator.git
cd pdf-test-generator
```

### 2. Install dependencies

```bash
cd test_data_generator
pip install -r requirements.txt
```

`requirements.txt` covers the Generator/Converter/Combiner tools. The AI Document Generator additionally needs `faker`, `jinja2`, `weasyprint`, `pydantic`, and the `andromeda` agent framework itself - install these separately if you're setting up a fresh environment for that part.

### 3. Configure Guidewire (optional, only needed for the claim-lookup feature)

```bash
export GUIDEWIRE_BASE_URL="https://your-guidewire-instance:443"
export GUIDEWIRE_USERNAME="your-username"
export GUIDEWIRE_PASSWORD="your-password"
export GUIDEWIRE_TIMEOUT=60   # seconds, optional
```

Without these set, `guidewire.py` falls back to the bundled dev-instance defaults in `app.py`. The AI Generator's other modes work fully without any Guidewire configuration.

### 4. Run the server

```bash
python run_server.py
```

This sets the working directory correctly (so `frontend/`, `renderers/templates/`, etc. resolve regardless of where you launch it from) and starts the server on port **8420**.

### 5. Open in browser

```
http://localhost:8420
```

---

## Project Structure

```
ClaimDocuGen/
├── test_data_generator/
│   ├── app.py                       # FastAPI backend - all API endpoints, Guidewire claim lookup
│   ├── run_server.py                # Entry point (sets cwd, launches uvicorn on port 8420)
│   ├── pdf_manager.py                # PDF text replacement & combining logic
│   ├── scanner_simulator.py          # Scan degradation engine
│   ├── guidewire.py                  # Guidewire ClaimCenter REST client
│   ├── response.json                 # Sample Guidewire claim response (reference/testing fixture)
│   ├── requirements.txt              # Python dependencies (Generator/Converter/Combiner)
│   │
│   ├── ai_doc_generator/             # AI Document Generator backend
│   │   ├── agent_factory.py          # Builds the LLM agent (model, tools, guardrails)
│   │   ├── tools.py                  # Agent tools: generate/recreate/build_packet/render/etc.
│   │   ├── prompt_builder.py         # Builds the per-mode prompt sent to the agent
│   │   ├── config.py                 # GenerationRequest model
│   │   ├── packets.py                # PACKET_REGISTRY / SCENARIO_REGISTRY definitions
│   │   └── guardrail_diagnostics.py  # Runtime diagnostics for the shared guardrail middleware
│   │
│   ├── renderers/                    # Synthetic data + PDF rendering
│   │   ├── synthetic_data.py         # build_synthetic_data() - Faker-based data per doc type/scenario
│   │   ├── components.py             # Component-composition registry (which sections per scenario)
│   │   ├── html_renderer.py          # Jinja2 render + WeasyPrint HTML→PDF
│   │   ├── docx_parser.py            # Reference-document layout extraction (Recreate mode)
│   │   └── templates/                # One Jinja2 template per document type (13 total)
│   │
│   ├── skills/                       # One skill definition per document type (field glossaries, etc.)
│   │
│   └── frontend/
│       ├── index.html                # Main UI (Generator & Converter / Combiner / AI Generator tabs)
│       ├── style.css                 # Styling
│       └── main.js                   # Frontend logic
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/replace` | Replace text in a PDF |
| `POST` | `/api/simulate-scan` | Apply scan degradations to a PDF |
| `POST` | `/api/combine` | Combine multiple PDFs with page selection |
| `POST` | `/api/ai-generate` | Generate/Recreate/Build Packet - the AI Document Generator's main endpoint |
| `POST` | `/api/ai-analyze-reference` | Analyze an uploaded reference document (used by Recreate mode) |
| `GET`  | `/api/ai-doc-types` | List available document types, packet types, and scenarios |
| `GET`  | `/api/health` | Health check |

`/api/ai-generate` accepts `doc_type`, `mode` (`generate`/`recreate`/`packet`), `scenario`, `count`, `seed`, `reference_file` (Recreate mode), `custom_fields` (JSON string of field overrides), and `user_input` (free text - plain instructions and/or a Guidewire claim ID/number).

---
