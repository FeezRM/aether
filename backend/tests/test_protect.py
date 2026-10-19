import pymupdf as fitz

from conftest import current, make_text_pdf, op


def test_encrypt_permissions_and_remove(client, doc_id):
    op(client, doc_id, "encrypt", user_password="open-me", owner_password="owner",
       permissions={"print": False, "copy_content": False})
    raw = client.get(f"/api/documents/{doc_id}/download").content
    d = fitz.open(stream=raw, filetype="pdf")
    assert d.needs_pass and not d.authenticate("wrong") and d.authenticate("open-me")
    assert not d.permissions & fitz.PDF_PERM_PRINT
    info = client.get(f"/api/documents/{doc_id}").json()
    assert info["encrypted"]
    # Editing an encrypted document still works and keeps the encryption.
    op(client, doc_id, "add_note", page=0, point=[100, 100], contents="still encrypted")
    assert fitz.open(stream=client.get(f"/api/documents/{doc_id}/download").content, filetype="pdf").needs_pass
    op(client, doc_id, "remove_security")
    assert not fitz.open(stream=client.get(f"/api/documents/{doc_id}/download").content, filetype="pdf").needs_pass
    # Undo back to the encrypted state still opens.
    assert client.post(f"/api/documents/{doc_id}/undo").json()["encrypted"]


def test_open_encrypted_needs_password(client):
    d = fitz.open(stream=make_text_pdf(1), filetype="pdf")
    data = d.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    r = client.post("/api/documents", files={"file": ("e.pdf", data)})
    assert r.status_code == 401
    r = client.post("/api/documents", files={"file": ("e.pdf", data)}, data={"password": "pw"})
    assert r.status_code == 200


def test_search_redact_removes_text(client, doc_id):
    res = op(client, doc_id, "search_redact", patterns=["email", "ssn", "phone"], terms=["contract"])
    assert res["result"]["marked"] >= 9
    assert "jane.doe@example.com" in res["result"]["matches"]
    op(client, doc_id, "apply_redactions")
    text = current(client, doc_id)[0].get_text()
    for secret in ("jane.doe@example.com", "123-45-6789", "555-123-4567", "contract"):
        assert secret not in text
    assert "Chapter 1" in text


def test_mark_area_redaction_and_no_marks_error(client, doc_id):
    r = client.post(f"/api/documents/{doc_id}/ops/apply_redactions", json={})
    assert r.status_code == 400
    op(client, doc_id, "mark_redactions", page=0, rects=[[60, 700, 400, 730]], overlay_text="REDACTED")
    op(client, doc_id, "apply_redactions")
    assert "Chapter 1" not in current(client, doc_id)[0].get_text().replace("REDACTED", "")


def test_sanitize(client, doc_id):
    op(client, doc_id, "set_metadata", title="Secret", author="Someone")
    op(client, doc_id, "sanitize")
    assert client.get(f"/api/documents/{doc_id}").json()["metadata"].get("author") in (None, "")


def test_restricted_document_requires_owner_password(client):
    d = fitz.open(stream=make_text_pdf(1), filetype="pdf")
    data = d.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="", owner_pw="boss",
                     permissions=fitz.PDF_PERM_PRINT)
    doc_id = client.post("/api/documents", files={"file": ("r.pdf", data)}).json()["id"]
    r = client.post(f"/api/documents/{doc_id}/ops/add_note", json={"page": 0, "point": [10, 10], "contents": "x"})
    assert r.status_code == 403
    assert client.post(f"/api/documents/{doc_id}/unlock", json={"password": "wrong"}).status_code == 401
    assert client.post(f"/api/documents/{doc_id}/unlock", json={"password": "boss"}).status_code == 200
    op(client, doc_id, "add_note", page=0, point=[10, 10], contents="x")
    saved = fitz.open(stream=client.get(f"/api/documents/{doc_id}/download").content, filetype="pdf")
    # Restrictions survive the edit (checked before owner login, which lifts them).
    assert saved.metadata["encryption"] and not saved.permissions & fitz.PDF_PERM_MODIFY
    assert saved.authenticate("boss") & 4


def test_redacting_a_line_keeps_the_line_above(client):
    doc = fitz.open()
    page = doc.new_page()
    # Tight line spacing: line boxes overlap their neighbours.
    page.insert_htmlbox(fitz.Rect(72, 72, 500, 300),
                        "<p style='font-size:11pt;line-height:1.1'>Keep this Private Information intact.<br>"
                        "The SSN 123-45-6789 is secret.</p>")
    doc_id = client.post("/api/documents", files={"file": ("t.pdf", doc.tobytes())}).json()["id"]
    op(client, doc_id, "search_redact", patterns=["ssn"])
    op(client, doc_id, "apply_redactions")
    text = " ".join(current(client, doc_id)[0].get_text().split())
    assert "123-45-6789" not in text
    assert "Keep this Private Information intact." in text
