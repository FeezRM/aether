# Aether

A desktop-class PDF editor that matches the everyday Adobe Acrobat Pro toolset and runs entirely on your
computer. Documents never leave the machine: the API binds to `127.0.0.1`, rejects non-local `Host` headers,
and makes no outbound calls. The one exception is downloading an AI model, which happens only when you click
Download.

**Ask AI** is a built-in assistant that answers questions about the open PDF (with page citations) and makes
edits on request. It runs a small model inside Aether itself, with no Ollama or cloud service, and works offline
once a model is downloaded. Choose **Lite** (about 0.8 GB) or **Standard** (about 2.5 GB). See
[docs/AI.md](docs/AI.md).

See [docs/ACROBAT_PARITY.md](docs/ACROBAT_PARITY.md) for the tool-by-tool parity checklist against Acrobat Pro.

## Quick start

Requirements: Python 3.11+, Node 20+, and Tesseract for OCR (`brew install tesseract`). The AI runtime is
installed as a prebuilt wheel. If none matches your platform, pip builds it from source, which needs CMake
and a C++ compiler.

```bash
./start.sh
```

Then open http://127.0.0.1:8765. The script creates the Python virtualenv and builds the UI on first run.

## Development

Run the API and the Vite dev server (hot reload) in two terminals:

```bash
backend/.venv/bin/python -m uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 8765 --reload
```

```bash
npm --prefix frontend run dev
```

The UI is then at http://127.0.0.1:5173 and proxies `/api` to the backend.

## Tests

Backend unit and API tests (every operation, encryption, redaction, OCR, signing, the assistant):

```bash
cd backend && .venv/bin/python -m pytest -q
```

Evaluations of a downloaded AI model are opt-in: `AETHER_EVAL_TIER=lite .venv/bin/python -m pytest -q tests/ai_eval`.

End-to-end walk through the UI with real mouse and keyboard input in headless Chrome (needs both servers running):

```bash
cd e2e && npm install && node run.mjs
```

Set `LOCALPDF_URL=http://127.0.0.1:8765/` to test the production build instead of the dev server.

## Architecture

```
frontend/  React + TypeScript + pdf.js     viewer, text layer, tool panels, gestures
backend/   FastAPI + PyMuPDF               one operation registry; undo snapshots per document
  app/ops/       edit, comment, pages, forms, protect/redact, enhance, ocr, optimize, bookmarks, certs
  app/convert.py export (Word/Excel/PowerPoint/images/text), split, combine, create, compare, accessibility
  app/store.py   in-memory documents, undo/redo, password handling and re-encryption
  app/ai/        local assistant: model tiers and download, llama.cpp runtime, retrieval, tools, agent loop
e2e/       headless Chrome end-to-end test
docs/      Acrobat parity checklist
```

Every feature is a named operation in `backend/app/ops`. The UI, batch "Action Wizard" runs, and the local AI
assistant all call the same registry, so the assistant can only do what the editor can do, and every change is
undoable. Everything one assistant request changes is a single undo step.

Coordinates: the UI sends PDF user-space points (from pdf.js); the backend converts them with each page's
transformation matrix, so tools work on rotated and cropped pages.

## Licences

PyMuPDF is AGPL-3.0, so this project is open source under compatible terms; a closed-source release would need an
Artifex commercial licence. pdf2docx, pyHanko, pdf.js, Tesseract and llama.cpp use permissive or compatible licences.
The AI models are downloaded by the user, not distributed with Aether. Their licences are listed in
[docs/AI.md](docs/AI.md#licences). No
Adobe code or assets are used: the installed Acrobat was inspected only to list its tool names.
