"""LocalPDF Studio API. Serves only 127.0.0.1; documents never leave this process."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pymupdf as fitz
from fastapi import Body, FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from . import convert
from .inspect_doc import doc_info, page_detail, search
from .ops import OPS, Ctx, OpResult
from .ops.certs import create_digital_id, validate_signatures
from .store import DocumentStore, StoreError

PORT = int(os.environ.get("LOCALPDF_PORT", "8765"))
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}", "127.0.0.1", "localhost",
                 "testserver", "127.0.0.1:5173", "localhost:5173"}

app = FastAPI(title="LocalPDF Studio", version="0.1.0")
store = DocumentStore()

app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def local_only(request: Request, call_next):
    # Reject requests whose Host header is not local (blocks DNS-rebinding pages).
    if request.headers.get("host", "") not in ALLOWED_HOSTS:
        return JSONResponse({"detail": "Forbidden host"}, status_code=403)
    return await call_next(request)


@app.exception_handler(StoreError)
async def store_error(_req, exc: StoreError):
    return JSONResponse({"detail": str(exc)}, status_code=exc.status)


@app.exception_handler(ValueError)
async def value_error(_req, exc: ValueError):
    if isinstance(exc, ValidationError):
        msgs = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        return JSONResponse({"detail": msgs}, status_code=400)
    return JSONResponse({"detail": str(exc)}, status_code=400)


def file_response(data: bytes, filename: str, media: str) -> Response:
    safe = filename.replace('"', "")
    return Response(data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{safe}"'})


def stem(name: str) -> str:
    return name.rsplit(".", 1)[0]


# ------------------------------------------------------------- documents --

@app.get("/api/health")
def health():
    return {"ok": True, "documents": len(store.list())}


@app.get("/api/ops")
def list_ops():
    return [{"name": s.name, "category": s.category, "description": s.description}
            for s in OPS.values()]


@app.get("/api/documents")
def list_documents():
    return [{"id": e.id, "name": e.name, "dirty": e.dirty} for e in store.list()]


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...), password: str | None = Form(None)):
    data = await file.read()
    entry = store.add(file.filename or "document.pdf", data, password)
    return doc_info(entry)


class OpenPath(BaseModel):
    path: str
    password: str | None = None


@app.post("/api/documents/open-path")
def open_path(body: OpenPath):
    path = Path(body.path).expanduser()
    if not path.is_file():
        raise StoreError(f"File not found: {path}", 404)
    entry = store.add(path.name, path.read_bytes(), body.password, source_path=path.resolve())
    return doc_info(entry)


class NewDoc(BaseModel):
    pages: int = 1
    size: str = "letter"


@app.post("/api/documents/blank")
def new_blank(body: NewDoc):
    entry = store.add("Untitled.pdf", convert.blank_pdf(body.pages, body.size))
    return doc_info(entry)


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    return doc_info(store.get(doc_id))


@app.delete("/api/documents/{doc_id}")
def close_document(doc_id: str):
    store.close(doc_id)
    return {"ok": True}


@app.get("/api/documents/{doc_id}/file")
def document_file(doc_id: str):
    """Current bytes for the local viewer (decrypted, since it never leaves this machine)."""
    entry = store.get(doc_id)
    return Response(entry.plain_bytes(), media_type="application/pdf",
                    headers={"Cache-Control": "no-store"})


@app.get("/api/documents/{doc_id}/download")
def download(doc_id: str):
    entry = store.get(doc_id)
    return file_response(entry.data, entry.name, "application/pdf")


class SaveBody(BaseModel):
    path: str | None = None


@app.post("/api/documents/{doc_id}/save")
def save(doc_id: str, body: SaveBody = Body(SaveBody())):
    entry = store.get(doc_id)
    target = Path(body.path).expanduser() if body.path else entry.source_path
    if target is None:
        raise StoreError("No file path yet; use Save As with a path or Download")
    if target.suffix.lower() != ".pdf":
        raise StoreError("Path must end in .pdf")
    if not target.parent.is_dir():
        raise StoreError(f"Folder does not exist: {target.parent}")
    target.write_bytes(entry.data)
    entry.source_path = target.resolve()
    entry.name = target.name
    entry.dirty = False
    return doc_info(entry)


class Unlock(BaseModel):
    password: str


@app.post("/api/documents/{doc_id}/unlock")
def unlock(doc_id: str, body: Unlock):
    """Remember a password: the open password, or the permissions password to allow edits."""
    entry = store.get(doc_id)
    probe = fitz.open(stream=entry.data, filetype="pdf")
    try:
        ok = probe.authenticate(body.password)
    finally:
        probe.close()
    if not ok:
        raise StoreError("Wrong password", 401)
    if body.password not in entry.passwords:
        entry.passwords.append(body.password)
    return doc_info(entry)


@app.get("/api/documents/{doc_id}/pages/{index}")
def get_page(doc_id: str, index: int):
    return page_detail(store.get(doc_id), index)


@app.get("/api/documents/{doc_id}/search")
def search_document(doc_id: str, q: str):
    if not q.strip():
        return []
    return search(store.get(doc_id), q)


@app.post("/api/documents/{doc_id}/undo")
def undo(doc_id: str):
    return doc_info(store.undo(doc_id))


@app.post("/api/documents/{doc_id}/redo")
def redo(doc_id: str):
    return doc_info(store.redo(doc_id))


def run_op(doc_id: str, name: str, params: dict[str, Any]) -> Any:
    spec = OPS.get(name)
    if spec is None:
        raise StoreError(f"Unknown operation {name!r}", 404)
    entry = store.get(doc_id)
    with entry.lock:
        doc = entry.open()
        try:
            result = spec.fn(doc, Ctx(store, entry), **params)
            new_passwords: list[str] = []
            if isinstance(result, OpResult):
                data, new_bytes, new_passwords = result.data, result.replace_bytes, result.new_passwords
            else:
                data, new_bytes = result, None
            if new_bytes is None:
                new_bytes = entry.serialize(doc)
        finally:
            doc.close()
        entry.commit(new_bytes)
        entry.passwords.extend(p for p in new_passwords if p not in entry.passwords)
    return data


@app.post("/api/documents/{doc_id}/ops/{name}")
def apply_op(doc_id: str, name: str, params: dict[str, Any] = Body(default_factory=dict)):
    result = run_op(doc_id, name, params)
    return {"result": result, "info": doc_info(store.get(doc_id))}


class BatchStep(BaseModel):
    op: str
    params: dict[str, Any] = {}


class Batch(BaseModel):
    doc_ids: list[str]
    steps: list[BatchStep]


@app.post("/api/batch")
def batch(body: Batch):
    """Action Wizard: run the same sequence of operations on several documents."""
    report = []
    for doc_id in body.doc_ids:
        entry = store.get(doc_id)
        results = []
        try:
            for step in body.steps:
                results.append(run_op(doc_id, step.op, step.params))
            report.append({"id": doc_id, "name": entry.name, "ok": True, "results": results})
        except (ValueError, StoreError) as exc:
            report.append({"id": doc_id, "name": entry.name, "ok": False, "error": str(exc),
                           "completed_steps": len(results)})
    return report


# ----------------------------------------------------------------- blobs --

@app.post("/api/blobs")
async def upload_blob(file: UploadFile = File(...)):
    data = await file.read()
    return {"id": store.add_blob(file.filename or "upload", data), "name": file.filename,
            "size": len(data)}


# ------------------------------------------------------- export / create --

EXPORTS = {
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
    "pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "pptx"),
    "txt": ("text/plain; charset=utf-8", "txt"),
    "html": ("text/html; charset=utf-8", "html"),
    "md": ("text/markdown; charset=utf-8", "md"),
    "png": ("application/zip", "png.zip"),
    "jpg": ("application/zip", "jpg.zip"),
}


@app.get("/api/documents/{doc_id}/export/{kind}")
def export(doc_id: str, kind: str, dpi: int = 150):
    entry = store.get(doc_id)
    if kind not in EXPORTS:
        raise StoreError(f"Unknown export format {kind!r}")
    media, ext = EXPORTS[kind]
    if kind == "docx":
        data = convert.export_docx(entry)
    elif kind == "xlsx":
        data = convert.export_xlsx(entry)
    elif kind == "pptx":
        data = convert.export_pptx(entry)
    elif kind in ("png", "jpg"):
        data = convert.export_images(entry, kind, dpi)
    else:
        data = convert.export_text(entry, kind)
    return file_response(data, f"{stem(entry.name)}.{ext}", media)


@app.get("/api/documents/{doc_id}/form-data")
def form_data(doc_id: str, fmt: str = "json"):
    entry = store.get(doc_id)
    media = "application/json" if fmt == "json" else "text/csv"
    return file_response(convert.export_form_data(entry, fmt), f"{stem(entry.name)}-data.{fmt}", media)


@app.get("/api/documents/{doc_id}/comments")
def comments_export(doc_id: str, fmt: str = "csv"):
    entry = store.get(doc_id)
    media = "application/json" if fmt == "json" else "text/csv"
    return file_response(convert.export_comments(entry, fmt), f"{stem(entry.name)}-comments.{fmt}", media)


class PagesBody(BaseModel):
    pages: list[int]
    open_as_new: bool = False


@app.post("/api/documents/{doc_id}/extract")
def extract(doc_id: str, body: PagesBody):
    entry = store.get(doc_id)
    data = convert.extract_pages(entry, body.pages)
    if body.open_as_new:
        return doc_info(store.add(f"{stem(entry.name)}-extract.pdf", data))
    return file_response(data, f"{stem(entry.name)}-extract.pdf", "application/pdf")


class SplitBody(BaseModel):
    mode: str
    every: int = 1
    ranges: str = ""
    max_mb: float = 0


@app.post("/api/documents/{doc_id}/split")
def split(doc_id: str, body: SplitBody):
    entry = store.get(doc_id)
    data = convert.split(entry, body.mode, body.every, body.ranges, body.max_mb)
    return file_response(data, f"{stem(entry.name)}-split.zip", "application/zip")


class CombineBody(BaseModel):
    doc_ids: list[str] = []
    blob_ids: list[str] = []
    name: str = "Combined.pdf"
    bookmarks: bool = True


@app.post("/api/combine")
def combine(body: CombineBody):
    parts = [(store.get(d).name, store.get(d).plain_bytes()) for d in body.doc_ids]
    parts += [store.blob(b) for b in body.blob_ids]
    if len(parts) < 2:
        raise StoreError("Choose at least two files to combine")
    return doc_info(store.add(body.name, convert.combine(parts, body.bookmarks)))


class CreateBody(BaseModel):
    blob_ids: list[str]


@app.post("/api/create")
def create(body: CreateBody):
    """Create PDF from images, text, Markdown, HTML, EPUB, XPS and other readable files."""
    if not body.blob_ids:
        raise StoreError("No files given")
    parts = [store.blob(b) for b in body.blob_ids]
    if len(parts) == 1:
        name, data = parts[0]
        return doc_info(store.add(f"{stem(name)}.pdf", convert.create_from(name, data)))
    pdfs = [(n, convert.create_from(n, d)) for n, d in parts]
    return doc_info(store.add("Created.pdf", convert.combine([(f"{stem(n)}.pdf", d) for n, d in pdfs])))


class CompareBody(BaseModel):
    old_id: str
    new_id: str


@app.post("/api/compare")
def compare(body: CompareBody):
    old, new = store.get(body.old_id), store.get(body.new_id)
    report, annotated = convert.compare(old, new)
    entry = store.add(f"Compare - {stem(new.name)}.pdf", annotated)
    return {"report": report, "info": doc_info(entry)}


@app.get("/api/documents/{doc_id}/accessibility")
def accessibility(doc_id: str):
    return convert.accessibility_check(store.get(doc_id))


@app.get("/api/documents/{doc_id}/signatures")
def signatures(doc_id: str):
    return validate_signatures(store.get(doc_id).data)


class DigitalIdBody(BaseModel):
    name: str
    email: str = ""
    organization: str = ""
    passphrase: str


@app.post("/api/digital-id")
def digital_id(body: DigitalIdBody):
    """Create a self-signed digital ID; returned as a .p12 file and also kept as an upload."""
    p12 = create_digital_id(body.name, body.email, body.organization, body.passphrase)
    blob_id = store.add_blob(f"{body.name}.p12", p12)
    return Response(p12, media_type="application/x-pkcs12", headers={
        "Content-Disposition": f'attachment; filename="{body.name.replace(chr(34), "")}.p12"',
        "X-Blob-Id": blob_id, "Access-Control-Expose-Headers": "X-Blob-Id"})


# --------------------------------------------------------------- frontend --

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="ui")


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, reload=False)


if __name__ == "__main__":
    run()
