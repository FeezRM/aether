import io

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient

from app.main import app, store


def make_text_pdf(pages: int = 3) -> bytes:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 80), f"Chapter {i + 1}", fontsize=24, fontname="hebo")
        page.insert_text((72, 120), f"This is page {i + 1} of the sample contract.", fontsize=11)
        page.insert_text((72, 140), "Contact: jane.doe@example.com or 555-123-4567.", fontsize=11)
        page.insert_text((72, 160), "SSN 123-45-6789 must stay private.", fontsize=11)
        page.insert_text((72, 200), "Name: ______________", fontsize=11)
        page.draw_rect(fitz.Rect(72, 220, 84, 232), color=(0, 0, 0), width=0.8)
        page.insert_text((90, 230), "I agree", fontsize=11)
    return doc.tobytes()


def make_image_pdf() -> bytes:
    """A 'scanned' page: text rendered to an image, no text layer."""
    src = fitz.open()
    p = src.new_page(width=612, height=792)
    p.insert_text((72, 120), "Scanned invoice number 4471", fontsize=28)
    pix = p.get_pixmap(dpi=200)
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_image(page.rect, stream=pix.tobytes("png"))
    return doc.tobytes()


def png_bytes(color=(200, 30, 30)) -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 30), False)
    pix.set_rect(pix.irect, color)
    return pix.tobytes("png")


@pytest.fixture
def client():
    store._docs.clear()
    store._blobs.clear()
    return TestClient(app)


@pytest.fixture
def doc_id(client):
    r = client.post("/api/documents", files={"file": ("sample.pdf", make_text_pdf(), "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def upload(client, name: str, data: bytes) -> str:
    r = client.post("/api/blobs", files={"file": (name, io.BytesIO(data))})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def op(client, doc_id, name, /, **params):
    r = client.post(f"/api/documents/{doc_id}/ops/{name}", json=params)
    assert r.status_code == 200, f"{name}: {r.text}"
    return r.json()


def current(client, doc_id) -> fitz.Document:
    r = client.get(f"/api/documents/{doc_id}/file")
    return fitz.open(stream=r.content, filetype="pdf")
