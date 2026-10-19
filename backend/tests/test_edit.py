import pymupdf as fitz

from conftest import current, op, png_bytes, upload


def pdf_rect(page, r):
    """Convert a PyMuPDF rect into PDF user space as the UI would send it."""
    q = fitz.Rect(r) * ~page.transformation_matrix
    q.normalize()
    return list(q)


def test_edit_text_in_place_keeps_baseline(client, doc_id):
    doc = current(client, doc_id)
    page = doc[0]
    hit = page.search_for("This is page 1 of the sample contract.")[0]
    res = op(client, doc_id, "edit_text", page=0, rect=pdf_rect(page, hit),
             text="This is page one of the amended contract.")
    assert res["result"]["fontsize"] == 11
    text = current(client, doc_id)[0].get_text()
    assert "amended contract" in text and "sample contract" not in text
    new_hit = current(client, doc_id)[0].search_for("amended")[0]
    assert abs(new_hit.y1 - hit.y1) < 2  # same line position


def test_edit_text_requires_text_under_rect(client, doc_id):
    r = client.post(f"/api/documents/{doc_id}/ops/edit_text",
                    json={"page": 0, "rect": [400, 10, 500, 20], "text": "x"})
    assert r.status_code == 400 and "No text" in r.json()["detail"]


def test_add_text_and_replace_text(client, doc_id):
    op(client, doc_id, "add_text", page=0, rect=[72, 400, 400, 440], text="Added paragraph", fontsize=14,
       family="serif", bold=True, color="#ff0000")
    assert "Added paragraph" in current(client, doc_id)[0].get_text()
    res = op(client, doc_id, "replace_text", find="sample contract", replace="final agreement")
    assert res["result"]["replaced"] == 3
    assert "final agreement" in current(client, doc_id)[2].get_text()


def test_images_links_attachments_metadata(client, doc_id):
    blob = upload(client, "logo.png", png_bytes())
    op(client, doc_id, "add_image", page=0, rect=[400, 600, 520, 660], blob_id=blob)
    page_info = client.get(f"/api/documents/{doc_id}/pages/0").json()
    assert len(page_info["images"]) == 1
    xref = page_info["images"][0]["xref"]
    op(client, doc_id, "replace_image", page=0, xref=xref, blob_id=upload(client, "b.png", png_bytes((0, 0, 200))))
    op(client, doc_id, "add_link", page=0, rect=[72, 100, 200, 120], uri="https://example.com")
    op(client, doc_id, "add_link", page=0, rect=[72, 300, 200, 320], target_page=2)
    links = client.get(f"/api/documents/{doc_id}/pages/0").json()["links"]
    assert {l["uri"] for l in links} >= {"https://example.com"}
    assert any(l["page"] == 2 for l in links)
    op(client, doc_id, "delete_link", page=0, index=0)
    assert len(client.get(f"/api/documents/{doc_id}/pages/0").json()["links"]) == 1
    r = client.post(f"/api/documents/{doc_id}/ops/add_link", json={"page": 0, "rect": [1, 1, 2, 2], "uri": "javascript:alert(1)"})
    assert r.status_code == 400
    op(client, doc_id, "add_attachment", blob_id=upload(client, "notes.txt", b"hello"))
    op(client, doc_id, "set_metadata", title="Contract", author="Faiz")
    info = client.get(f"/api/documents/{doc_id}").json()
    assert info["attachments"] == ["notes.txt"]
    assert info["metadata"]["title"] == "Contract"
    op(client, doc_id, "delete_attachment", name="notes.txt")
    op(client, doc_id, "delete_area_content", page=0, rect=[390, 590, 530, 670])
    assert client.get(f"/api/documents/{doc_id}/pages/0").json()["images"] == []


def test_bookmarks(client, doc_id):
    res = op(client, doc_id, "auto_bookmarks")
    assert [o["title"] for o in res["info"]["outline"]] == ["Chapter 1", "Chapter 2", "Chapter 3"]
    op(client, doc_id, "add_bookmark", title="Appendix", page=2, level=2)
    op(client, doc_id, "rename_bookmark", index=0, title="Intro")
    op(client, doc_id, "delete_bookmark", index=1)
    outline = client.get(f"/api/documents/{doc_id}").json()["outline"]
    assert [o["title"] for o in outline] == ["Intro", "Chapter 3", "Appendix"]


def _paragraph_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    html = ("<p style='font-size:11pt'>First paragraph line that is fairly long and wraps onto a second "
            "line because it keeps going for quite a while longer.</p><p>Next paragraph stays put.</p>")
    page.insert_htmlbox(fitz.Rect(72, 72, 400, 300), html)
    return doc.tobytes()


def test_edit_paragraph_reflows_and_keeps_neighbours(client):
    doc_id = client.post("/api/documents", files={"file": ("p.pdf", _paragraph_pdf())}).json()["id"]
    detail = client.get(f"/api/documents/{doc_id}/pages/0").json()
    para = detail["blocks"][0]
    assert para["line_count"] >= 2 and "\n" not in para["text"]
    new = "Rewritten paragraph text that is also long enough that it needs to wrap within the box width."
    op(client, doc_id, "edit_text", page=0, rect=para["rect"], text=new)
    text = " ".join(current(client, doc_id)[0].get_text().split())
    assert new in text
    assert "Next paragraph stays put." in text
    assert "First paragraph" not in text


def test_edit_single_line_does_not_touch_line_below(client):
    doc_id = client.post("/api/documents", files={"file": ("p.pdf", _paragraph_pdf())}).json()["id"]
    lines = client.get(f"/api/documents/{doc_id}/pages/0").json()["lines"]
    op(client, doc_id, "edit_text", page=0, rect=lines[0]["rect"], text="Short replacement")
    text = " ".join(current(client, doc_id)[0].get_text().split())
    assert "Short replacement" in text
    assert lines[1]["text"] in text  # the wrapped second line survives
