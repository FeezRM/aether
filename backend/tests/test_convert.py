import io
import zipfile

import pymupdf as fitz

from conftest import make_text_pdf, op, upload


def test_exports(client, doc_id):
    for kind, magic in (("docx", b"PK"), ("xlsx", b"PK"), ("pptx", b"PK"), ("png", b"PK")):
        r = client.get(f"/api/documents/{doc_id}/export/{kind}")
        assert r.status_code == 200 and r.content[:2] == magic, kind
    assert "sample contract" in client.get(f"/api/documents/{doc_id}/export/txt").text
    assert "# Chapter 1" in client.get(f"/api/documents/{doc_id}/export/md").text
    assert len(zipfile.ZipFile(io.BytesIO(client.get(f"/api/documents/{doc_id}/export/png").content)).namelist()) == 3


def test_create_from_files(client):
    md = upload(client, "notes.md", b"# Title\n\nSome **bold** text.\n\n- one\n- two")
    info = client.post("/api/create", json={"blob_ids": [md]}).json()
    assert info["page_count"] == 1
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 50, 50), False)
    img = upload(client, "photo.png", pix.tobytes("png"))
    info = client.post("/api/create", json={"blob_ids": [md, img]}).json()
    assert info["page_count"] == 2
    blank = client.post("/api/documents/blank", json={"pages": 2}).json()
    assert blank["page_count"] == 2


def test_compare(client, doc_id):
    d = fitz.open(stream=make_text_pdf(), filetype="pdf")
    d[1].add_redact_annot(d[1].search_for("sample")[0])
    d[1].apply_redactions()
    d[1].insert_text((72, 300), "A brand new clause appears here.", fontsize=11)
    new_id = client.post("/api/documents", files={"file": ("v2.pdf", d.tobytes())}).json()["id"]
    res = client.post("/api/compare", json={"old_id": doc_id, "new_id": new_id}).json()
    rep = res["report"]
    assert rep["counts"]["inserted"] + rep["counts"]["replaced"] >= 1
    assert rep["counts"]["deleted"] + rep["counts"]["replaced"] >= 1
    assert any("brand new clause" in c["new"] for c in rep["changes"])
    assert len(res["info"]["annotations"]) >= 2


def test_accessibility_check(client, doc_id):
    rep = client.get(f"/api/documents/{doc_id}/accessibility").json()
    rules = {c["rule"]: c["status"] for c in rep["checks"]}
    assert rules["Tagged PDF"] == "failed" and rules["Title"] == "failed"
    op(client, doc_id, "set_metadata", title="Contract")
    rules = {c["rule"]: c["status"] for c in client.get(f"/api/documents/{doc_id}/accessibility").json()["checks"]}
    assert rules["Title"] == "passed"


def test_certificate_sign_and_validate(client, doc_id):
    r = client.post("/api/digital-id", json={"name": "Jane Doe", "passphrase": "s3cret"})
    assert r.status_code == 200
    blob = r.headers["x-blob-id"]
    op(client, doc_id, "sign_certificate", blob_id=blob, passphrase="s3cret", page=0,
       rect=[72, 40, 272, 90], reason="Approval")
    sigs = client.get(f"/api/documents/{doc_id}/signatures").json()
    assert len(sigs) == 1
    assert sigs[0]["intact"] and "Jane Doe" in sigs[0]["signer"]
    assert sigs[0]["trusted"] is False  # self-signed
    bad = client.post(f"/api/documents/{doc_id}/ops/sign_certificate", json={"blob_id": blob, "passphrase": "nope"})
    assert bad.status_code == 400


def test_batch_action_wizard(client, doc_id):
    other = client.post("/api/documents", files={"file": ("b.pdf", make_text_pdf(2))}).json()["id"]
    rep = client.post("/api/batch", json={"doc_ids": [doc_id, other], "steps": [
        {"op": "add_watermark", "params": {"text": "CONFIDENTIAL"}},
        {"op": "set_metadata", "params": {"author": "Legal"}}]}).json()
    assert all(r["ok"] for r in rep)
    assert client.get(f"/api/documents/{other}").json()["metadata"]["author"] == "Legal"


def test_rejects_foreign_host(client):
    r = client.get("/api/health", headers={"host": "evil.example.com"})
    assert r.status_code == 403
