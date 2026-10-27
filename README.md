<div align="center">

# Sky-DI

**A mini Document Intelligence Studio, built on Azure AI Document Intelligence.**

Pick a model, give it a document, and see exactly what Azure read.

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.40+-FF4B4B?logo=streamlit&logoColor=white)
![Azure](https://img.shields.io/badge/Azure-Document%20Intelligence-0078D4?logo=microsoftazure&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)

</div>

---

## Overview

Sky-DI shows the page on the left with a box around every detected item, and tabs on the right for
fields, key-value pairs, tables, text and the raw JSON. Click a row in any table and its box lights up on
the page. It looks like Sky-RAG, and nothing on screen says Streamlit.

### Features

- **Five analysis modes** covering OCR, layout, invoices, receipts and general documents
- **Interactive viewer**: click any result row to jump to its page and highlight its box
- **Three ways in**: bundled samples, file upload (PDF, JPG, PNG, TIFF, BMP up to 20 MB), or a public link
- **Cached results** per file and model, so clicking around never calls Azure twice
- **Custom studio UI** with the Streamlit menu, header, toolbar and footer hidden
- **Container-ready** with a slim, non-root Docker image

### Models

| Dropdown | Azure model |
|---|---|
| OCR / Read | `prebuilt-read` |
| Layout | `prebuilt-layout` |
| Invoices | `prebuilt-invoice` |
| Receipts | `prebuilt-receipt` |
| General documents | `prebuilt-layout` with key-value pairs, since Azure retired `prebuilt-document` in API v4 |

## How it works

```mermaid
flowchart LR
    A[Pick a model] --> B[Choose a document]
    B -->|sample, upload or link| C[Analyze]
    C --> D{Already analyzed?}
    D -->|yes| F[Use cached result]
    D -->|no| E[Azure Document Intelligence]
    E --> F
    F --> G[Page with boxes]
    F --> H[Tabs: fields, tables, text, JSON]
```

Clicking a row redraws the page without calling Azure again:

```mermaid
sequenceDiagram
    participant U as User
    participant T as Results table
    participant V as Page viewer
    U->>T: Click a row
    T->>V: Selected item and its page
    V->>V: Jump to that page
    V->>V: Draw the item solid, dim the rest
```

Each model decides which tabs show up:

```mermaid
flowchart TD
    M[Model] --> R[OCR / Read] --> RT[Text, JSON]
    M --> L[Layout] --> LT[Text, tables, JSON]
    M --> I[Invoices] --> IT[Fields, tables, text, JSON]
    M --> C[Receipts] --> CT[Fields, tables, text, JSON]
    M --> G[General documents] --> GT[Key-value pairs, tables, text, JSON]
```

## Getting started

### Prerequisites

- An [Azure AI Document Intelligence](https://learn.microsoft.com/azure/ai-services/document-intelligence/) resource (endpoint and key)
- Either **Docker**, or **Python 3.13+**

### Configuration

Copy `.env.example` to `.env` and fill it in:

| Variable | Description |
|---|---|
| `AZURE_DOCINTEL_ENDPOINT` | Your resource endpoint, e.g. `https://<your-resource>.cognitiveservices.azure.com/` |
| `AZURE_DOCINTEL_KEY` | One of the resource's API keys |

### Run with Docker

```bash
docker build -t sky-di .
docker run --rm -p 8501:8501 --env-file .env sky-di
```

Then open <http://localhost:8501>. The container listens on `$PORT` (default `8501`).

### Run locally

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
streamlit run app.py
```

## Deploy

The `Dockerfile` works on any container host: Render, Railway, Fly.io, Azure Container Apps and so on.
Set `AZURE_DOCINTEL_ENDPOINT` and `AZURE_DOCINTEL_KEY` as environment variables. Hosts that inject their
own `PORT` are picked up automatically.

## Project structure

```
sky-di/
├── app.py              # Streamlit entry point
├── skydi/
│   ├── analyzer.py     # Azure call and result-to-table-row helpers
│   ├── render.py       # Page images and bounding-box overlays
│   └── ui.py           # Small HTML builders for the studio look
├── assets/             # CSS (studio, style, motion) and favicon
├── samples/            # Bundled invoice, layout and receipt documents
├── tests/              # Unit tests, no Azure needed
├── .streamlit/         # Streamlit config
└── Dockerfile
```

## Tests

```bash
python -m pytest tests
```

The tests don't need Azure.

## Notes

- Styles live in `assets/`. `studio.css` hides the menu, header, toolbar, footer and deploy button.
- Streamlit serves a blank page with its own title for a split second before the CSS loads. CSS can't
  change that moment.
