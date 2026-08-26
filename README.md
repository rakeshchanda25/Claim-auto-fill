# PDF Test Data Generator

A powerful web-based tool to create realistic test documents for **Intelligent Document Processing (IDP)** AI systems. Generate, degrade, and combine PDFs with full control -all from a clean browser interface.

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

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+, FastAPI, Uvicorn |
| PDF Processing | PyMuPDF |
| Image Processing | OpenCV (`opencv-python-headless`), NumPy |
| Frontend | HTML5, Vanilla CSS, Vanilla JavaScript |

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

### 3. Run the server

```bash
uvicorn app:app --reload
```
or
```bash
python app.py
```

### 4. Open in browser

```
http://localhost:8000
```

---

## Project Structure

```
test-data/
├── test_data_generator/
│   ├── app.py                    # FastAPI backend (all API endpoints)
│   ├── pdf_manager.py            # PDF text replacement & combining logic
│   ├── scanner_simulator.py      # scan degradation engine
│   ├── requirements.txt          # Python dependencies
│   └── frontend/
│       ├── index.html            # Main UI
│       ├── style.css             # Styling
│       └── main.js               # Frontend logic
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/replace` | Replace text in a PDF |
| `POST` | `/api/simulate-scan` | Apply scan degradations to a PDF |
| `POST` | `/api/combine` | Combine multiple PDFs with page selection |

---

