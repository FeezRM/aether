from conftest import current, op, png_bytes, upload


def annots(client, doc_id):
    return client.get(f"/api/documents/{doc_id}").json()["annotations"]


def test_markup_note_textbox_shapes(client, doc_id):
    for kind in ("highlight", "underline", "strikeout", "squiggly"):
        op(client, doc_id, "add_markup", page=0, rects=[[72, 668, 300, 684]], kind=kind, contents=kind)
    op(client, doc_id, "add_note", page=0, point=[500, 700], contents="Check this clause")
    op(client, doc_id, "add_text_box", page=0, rect=[300, 500, 500, 540], text="Reviewer note",
       callout=[[250, 450], [300, 520]])
    op(client, doc_id, "add_typewriter", page=1, point=[72, 300], text="Typed")
    for kind in ("rect", "circle"):
        op(client, doc_id, "add_shape", page=1, kind=kind, rect=[100, 100, 200, 160])
    for kind in ("line", "arrow", "polygon", "polyline", "cloud"):
        op(client, doc_id, "add_shape", page=1, kind=kind, points=[[100, 300], [200, 350], [150, 400]])
    op(client, doc_id, "add_ink", page=2, strokes=[[[100, 100], [120, 130], [150, 110]]])
    op(client, doc_id, "add_stamp", page=2, rect=[300, 600, 500, 660], stamp="Confidential")
    op(client, doc_id, "add_image_stamp", page=2, rect=[300, 500, 400, 550], blob_id=upload(client, "s.png", png_bytes()))
    op(client, doc_id, "add_caret", page=2, point=[100, 500], contents="insert word")
    op(client, doc_id, "add_file_annotation", page=2, point=[50, 50], blob_id=upload(client, "a.txt", b"x"))
    types = sorted(a["type"] for a in annots(client, doc_id))
    for t in ("Highlight", "Underline", "StrikeOut", "Squiggly", "Text", "FreeText", "Square", "Circle",
              "Line", "Polygon", "PolyLine", "Ink", "Stamp", "Caret", "FileAttachment"):
        assert t in types, t


def test_highlight_text_update_reply_delete(client, doc_id):
    res = op(client, doc_id, "highlight_text", text="sample contract")
    assert res["result"]["count"] == 3
    a = annots(client, doc_id)[0]
    op(client, doc_id, "update_annotation", page=a["page"], xref=a["xref"], contents="edited", color="#00ff00")
    a2 = next(x for x in annots(client, doc_id) if x["xref"] == a["xref"])
    assert a2["contents"] == "edited" and a2["color"] == "#00ff00"
    op(client, doc_id, "reply_annotation", page=a["page"], xref=a["xref"], text="Agreed")
    assert any(x["reply_to"] == a["xref"] for x in annots(client, doc_id))
    op(client, doc_id, "delete_annotation", page=a["page"], xref=a["xref"])
    # Deleting a comment also removes its replies.
    assert [x for x in annots(client, doc_id) if x["page"] == a["page"]] == []


def test_erase_flatten_and_export(client, doc_id):
    op(client, doc_id, "add_ink", page=0, strokes=[[[100, 100], [150, 150]]])
    assert op(client, doc_id, "erase_ink", page=0, rect=[90, 90, 160, 160])["result"]["removed"] == 1
    op(client, doc_id, "add_note", page=0, point=[300, 300], contents="Keep")
    r = client.get(f"/api/documents/{doc_id}/comments?fmt=csv")
    assert "Keep" in r.text
    op(client, doc_id, "flatten_annotations")
    assert annots(client, doc_id) == []
    assert current(client, doc_id).page_count == 3
