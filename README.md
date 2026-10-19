# Aether

A desktop-class PDF editor that matches the everyday Adobe Acrobat Pro toolset and runs entirely on your
computer. Documents never leave the machine: the API binds to `127.0.0.1`, rejects non-local `Host` headers,
and makes no outbound calls. Local AI features (chat with PDF, smart redaction, form autofill) are the next phase.

See [docs/ACROBAT_PARITY.md](docs/ACROBAT_PARITY.md) for the tool-by-tool parity checklist against Acrobat Pro.

## Quick start

Requirements: Python 3.11+, Node 20+, and Tesseract for OCR (`brew install tesseract`).

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

Backend unit and API tests (every operation, encryption, redaction, OCR, signing):

```bash
cd backend && .venv/bin/python -m pytest -q
```

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
e2e/       headless Chrome end-to-end test
docs/      Acrobat parity checklist
```

Every feature is a named operation in `backend/app/ops`. The UI, batch "Action Wizard" runs, and (next) the local
AI assistant all call the same registry, so the assistant can only do what the editor can do, and every change is
undoable.

Coordinates: the UI sends PDF user-space points (from pdf.js); the backend converts them with each page's
transformation matrix, so tools work on rotated and cropped pages.

## Licences

PyMuPDF is AGPL-3.0, so this project is open source under compatible terms; a closed-source release would need an
Artifex commercial licence. pdf2docx, pyHanko, pdf.js and Tesseract use permissive or compatible licences. No
Adobe code or assets are used: the installed Acrobat was inspected only to list its tool names.
