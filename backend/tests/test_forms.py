from conftest import current, op, png_bytes, upload


def fields(client, doc_id):
    return {f["name"]: f for f in client.get(f"/api/documents/{doc_id}").json()["fields"]}


def test_create_fill_clear_fields(client, doc_id):
    op(client, doc_id, "add_field", page=0, rect=[200, 400, 400, 420], type="text", name="full_name",
       required=True, tooltip="Your full name")
    op(client, doc_id, "add_field", page=0, rect=[200, 370, 212, 382], type="checkbox", name="agree")
    op(client, doc_id, "add_field", page=0, rect=[200, 340, 320, 358], type="combobox", name="country",
       options=["Canada", "India", "USA"])
    op(client, doc_id, "add_field", page=0, rect=[200, 260, 320, 320], type="listbox", name="langs",
       options=["English", "French"])
    op(client, doc_id, "add_field", page=0, rect=[200, 200, 360, 240], type="signature", name="sig")
    f = fields(client, doc_id)
    assert f["full_name"]["required"] and f["full_name"]["tooltip"] == "Your full name"
    assert f["country"]["options"] == ["Canada", "India", "USA"]
    op(client, doc_id, "fill_fields", values={"full_name": "Jane Doe", "agree": True, "country": "India"})
    f = fields(client, doc_id)
    assert f["full_name"]["value"] == "Jane Doe"
    assert f["agree"]["value"] == f["agree"]["on_state"]
    assert f["country"]["value"] == "India"
    data = client.get(f"/api/documents/{doc_id}/form-data?fmt=json").json()
    assert data["full_name"] == "Jane Doe"
    op(client, doc_id, "update_field", name="full_name", new_name="name", readonly=True)
    assert fields(client, doc_id)["name"]["readonly"]
    op(client, doc_id, "clear_form")
    f = fields(client, doc_id)
    assert f["agree"]["value"] == "Off"
    assert f["name"]["value"] == "Jane Doe"  # read-only fields keep their value
    op(client, doc_id, "delete_field", name="langs")
    assert "langs" not in fields(client, doc_id)


def test_unknown_field_rejected(client, doc_id):
    r = client.post(f"/api/documents/{doc_id}/ops/fill_fields", json={"values": {"nope": "x"}})
    assert r.status_code == 400 and "nope" in r.json()["detail"]


def test_detect_fields(client, doc_id):
    added = op(client, doc_id, "detect_fields", pages=[0])["result"]["added"]
    kinds = sorted(a["type"] for a in added)
    assert "text" in kinds and "checkbox" in kinds
    # Running again does not duplicate fields.
    assert op(client, doc_id, "detect_fields", pages=[0])["result"]["added"] == []


def test_fill_and_sign(client, doc_id):
    for mark in ("check", "cross", "dot", "circle", "line"):
        op(client, doc_id, "place_mark", page=0, point=[300, 300], mark=mark)
    op(client, doc_id, "add_signature", page=0, rect=[72, 50, 250, 90], text="Jane Doe")
    op(client, doc_id, "add_signature", page=1, rect=[72, 50, 250, 90],
       strokes=[[[0, 20], [30, 0], [60, 30], [90, 5]]], stroke_box=[100, 40])
    op(client, doc_id, "add_signature", page=2, rect=[72, 50, 250, 90], blob_id=upload(client, "s.png", png_bytes()))
    doc = current(client, doc_id)
    assert "Jane Doe" in doc[0].get_text()
    assert doc[1].get_drawings()
    assert doc[2].get_images()
