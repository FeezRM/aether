import pymupdf as fitz

from conftest import current, make_text_pdf, op, upload


def page_titles(doc):
    return [p.get_text().splitlines()[0] for p in doc]


def test_delete_rotate_reorder(client, doc_id):
    op(client, doc_id, "rotate_pages", angle=90, pages=[0])
    assert current(client, doc_id)[0].rotation == 90
    op(client, doc_id, "reorder_pages", order=[2, 0, 1])
    assert page_titles(current(client, doc_id)) == ["Chapter 3", "Chapter 1", "Chapter 2"]
    op(client, doc_id, "delete_pages", pages=[0])
    assert page_titles(current(client, doc_id)) == ["Chapter 1", "Chapter 2"]


def test_cannot_delete_all_pages(client, doc_id):
    r = client.post(f"/api/documents/{doc_id}/ops/delete_pages", json={"pages": [0, 1, 2]})
    assert r.status_code == 400
    assert "every page" in r.json()["detail"]


def test_move_duplicate_insert_blank(client, doc_id):
    op(client, doc_id, "move_page", page=2, to=0)
    assert page_titles(current(client, doc_id))[0] == "Chapter 3"
    op(client, doc_id, "duplicate_pages", pages=[0])
    assert current(client, doc_id).page_count == 4
    op(client, doc_id, "insert_blank", at=4, count=2)
    doc = current(client, doc_id)
    assert doc.page_count == 6 and doc[5].get_text().strip() == ""


def test_insert_and_replace_from_upload(client, doc_id):
    other = fitz.open()
    other.new_page().insert_text((72, 72), "Inserted page")
    blob = upload(client, "other.pdf", other.tobytes())
    op(client, doc_id, "insert_pdf", blob_id=blob, at=1)
    assert "Inserted page" in current(client, doc_id)[1].get_text()
    op(client, doc_id, "replace_pages", start=3, blob_id=blob)
    doc = current(client, doc_id)
    assert doc.page_count == 4
    assert "Inserted page" in doc[3].get_text()


def test_crop_and_labels(client, doc_id):
    op(client, doc_id, "crop_pages", pages=[0], margins=[36, 36, 36, 36])
    assert current(client, doc_id)[0].cropbox == fitz.Rect(36, 36, 576, 756)
    op(client, doc_id, "set_page_labels", rules=[{"startpage": 0, "style": "r"},
                                                  {"startpage": 1, "style": "D", "firstpagenum": 1}])
    info = client.get(f"/api/documents/{doc_id}").json()
    assert [p["label"] for p in info["pages"]] == ["i", "1", "2"]


def test_undo_redo(client, doc_id):
    op(client, doc_id, "delete_pages", pages=[0])
    assert client.post(f"/api/documents/{doc_id}/undo").json()["page_count"] == 3
    assert client.post(f"/api/documents/{doc_id}/redo").json()["page_count"] == 2


def test_extract_split_combine(client, doc_id):
    r = client.post(f"/api/documents/{doc_id}/extract", json={"pages": [1, 2]})
    assert fitz.open(stream=r.content, filetype="pdf").page_count == 2
    import io, zipfile
    r = client.post(f"/api/documents/{doc_id}/split", json={"mode": "every", "every": 1})
    assert len(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == 3
    r = client.post(f"/api/documents/{doc_id}/split", json={"mode": "ranges", "ranges": "1-2, 3"})
    assert len(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == 2
    blob = upload(client, "two.pdf", make_text_pdf(2))
    info = client.post("/api/combine", json={"doc_ids": [doc_id], "blob_ids": [blob]}).json()
    assert info["page_count"] == 5
    assert [o["title"] for o in info["outline"] if o["level"] == 1] == ["sample", "two"]
