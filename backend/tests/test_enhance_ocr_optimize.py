import io

import pymupdf as fitz

from conftest import current, make_image_pdf, op, png_bytes, upload


def test_watermark_header_footer_bates_background(client, doc_id):
    op(client, doc_id, "add_watermark", text="DRAFT", opacity=0.2)
    op(client, doc_id, "header_footer", footer_center="Page <<page>> of <<pages>>", header_right="<<date>>")
    doc = current(client, doc_id)
    assert "DRAFT" in doc[0].get_text()
    assert "Page 2 of 3" in doc[1].get_text()
    res = op(client, doc_id, "bates_number", prefix="ABC", start=7, digits=5)
    assert res["result"] == {"first": "ABC00007", "last": "ABC00009"}
    assert "ABC00008" in current(client, doc_id)[1].get_text()
    op(client, doc_id, "set_background", color="#fff8e0")
    op(client, doc_id, "add_watermark", blob_id=upload(client, "w.png", png_bytes()), behind=True)


def test_header_on_rotated_page_is_upright(client, doc_id):
    op(client, doc_id, "rotate_pages", angle=90, pages=[0])
    op(client, doc_id, "header_footer", footer_left="ROTFOOT", pages=[0])
    page = current(client, doc_id)[0]
    hit = page.search_for("ROTFOOT")[0] * page.rotation_matrix
    # In the visible (rotated) page the footer sits near the bottom edge.
    assert hit.y0 > page.rect.height - 80


def test_ocr_makes_scan_searchable(client):
    r = client.post("/api/documents", files={"file": ("scan.pdf", make_image_pdf())})
    doc_id = r.json()["id"]
    assert current(client, doc_id)[0].get_text().strip() == ""
    res = op(client, doc_id, "ocr_pages")
    assert res["result"]["ocr_pages"] == [0]
    page = current(client, doc_id)[0]
    assert "invoice" in page.get_text().lower()
    assert page.search_for("4471")


def test_optimize_reduces_large_images(client):
    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 2400, 2400), False)
    import random
    random.seed(1)
    pix.set_rect(pix.irect, (120, 160, 200))
    for _ in range(4000):
        x, y = random.randrange(2390), random.randrange(2390)
        pix.set_rect(fitz.IRect(x, y, x + 10, y + 10), (random.randrange(255),) * 3)
    page.insert_image(fitz.Rect(72, 72, 300, 300), stream=pix.tobytes("png"))
    doc_id = client.post("/api/documents", files={"file": ("big.pdf", doc.tobytes())}).json()["id"]
    res = op(client, doc_id, "optimize", level="high")["result"]
    assert res["after"] < res["before"] * 0.5


def test_watermark_is_centred_and_rises_left_to_right(client, doc_id):
    op(client, doc_id, "rotate_pages", angle=90, pages=[1])
    op(client, doc_id, "add_watermark", text="DRAFT", pages=[0, 1])
    doc = current(client, doc_id)
    for page in (doc[0], doc[1]):
        trace = next(t for t in page.get_texttrace() if t["font"].startswith("Helvetica-Bold") and len(t["chars"]) == 5)
        box = fitz.Rect(trace["bbox"])
        mb = page.mediabox
        assert abs((box.x0 + box.x1) / 2 - mb.width / 2) < 30
        assert abs((box.y0 + box.y1) / 2 - mb.height / 2) < 30
        first = fitz.Point(trace["chars"][0][2]) * page.rotation_matrix
        last = fitz.Point(trace["chars"][-1][2]) * page.rotation_matrix
        assert last.x > first.x and last.y < first.y  # visibly bottom-left to top-right
