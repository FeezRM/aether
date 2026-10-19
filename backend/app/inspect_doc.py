"""Read-only views of a document for the UI (and later the AI assistant)."""

from __future__ import annotations

import pymupdf as fitz

from .coords import to_pdf_rect
from .store import DocEntry

WIDGET_NAMES = {
    fitz.PDF_WIDGET_TYPE_TEXT: "text", fitz.PDF_WIDGET_TYPE_CHECKBOX: "checkbox",
    fitz.PDF_WIDGET_TYPE_RADIOBUTTON: "radio", fitz.PDF_WIDGET_TYPE_COMBOBOX: "combobox",
    fitz.PDF_WIDGET_TYPE_LISTBOX: "listbox", fitz.PDF_WIDGET_TYPE_SIGNATURE: "signature",
    fitz.PDF_WIDGET_TYPE_BUTTON: "button",
}


def _hex(rgb) -> str | None:
    if not rgb:
        return None
    return "#" + "".join(f"{round(c * 255):02x}" for c in rgb[:3])


def _permissions(doc: fitz.Document) -> dict[str, bool]:
    p = doc.permissions
    return {
        "print": bool(p & fitz.PDF_PERM_PRINT), "copy": bool(p & fitz.PDF_PERM_COPY),
        "modify": bool(p & fitz.PDF_PERM_MODIFY), "annotate": bool(p & fitz.PDF_PERM_ANNOTATE),
        "fill_forms": bool(p & fitz.PDF_PERM_FORM), "assemble": bool(p & fitz.PDF_PERM_ASSEMBLE),
    }


def doc_info(entry: DocEntry) -> dict:
    doc = entry.open()
    try:
        pages, annots, fields = [], [], []
        labels_present = bool(doc.get_page_labels())
        for page in doc:
            pages.append({
                "index": page.number, "width": round(page.mediabox.width, 2),
                "height": round(page.mediabox.height, 2), "rotation": page.rotation,
                "label": page.get_label() if labels_present else str(page.number + 1),
            })
            for a in page.annots():
                kind = a.type[1]
                if kind in ("Popup",):
                    continue
                info = a.info
                annots.append({
                    "page": page.number, "xref": a.xref, "type": kind,
                    "rect": to_pdf_rect(page, a.rect), "contents": info.get("content", ""),
                    "author": info.get("title", ""), "modified": info.get("modDate", ""),
                    "color": _hex(a.colors.get("stroke") or a.colors.get("fill")),
                    "reply_to": a.irt_xref or None,
                })
            for w in page.widgets():
                fields.append({
                    "name": w.field_name, "type": WIDGET_NAMES.get(w.field_type, "unknown"),
                    "value": w.field_value, "page": page.number, "rect": to_pdf_rect(page, w.rect),
                    "options": w.choice_values or [], "xref": w.xref,
                    "on_state": w.on_state() if w.field_type in (
                        fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON) else None,
                    "required": bool(w.field_flags & fitz.PDF_FIELD_IS_REQUIRED),
                    "readonly": bool(w.field_flags & fitz.PDF_FIELD_IS_READ_ONLY),
                    "multiline": bool(w.field_type == fitz.PDF_WIDGET_TYPE_TEXT
                                      and w.field_flags & fitz.PDF_TX_FIELD_IS_MULTILINE),
                    "tooltip": w.field_label or "",
                })
        return {
            "id": entry.id, "name": entry.name, "version": entry.version, "dirty": entry.dirty,
            "can_undo": bool(entry.undo), "can_redo": bool(entry.redo),
            "encrypted": entry.is_encrypted(),
            "permissions": _permissions(doc),
            "page_count": doc.page_count, "pages": pages,
            "metadata": {k: v for k, v in (doc.metadata or {}).items() if v},
            "outline": [{"level": l, "title": t, "page": p - 1} for l, t, p in doc.get_toc(simple=True)],
            "annotations": annots, "fields": fields,
            "attachments": doc.embfile_names(),
            "file_size": len(entry.data),
            "has_signatures": doc.get_sigflags() > 0,
            "source_path": str(entry.source_path) if entry.source_path else None,
        }
    finally:
        doc.close()


def page_detail(entry: DocEntry, index: int) -> dict:
    """Text lines (for click-to-edit), images and links on one page, in PDF space."""
    doc = entry.open()
    try:
        if not 0 <= index < doc.page_count:
            raise ValueError("Page index out of range")
        page = doc[index]
        lines = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                s0 = spans[0]
                lines.append({
                    "rect": to_pdf_rect(page, fitz.Rect(line["bbox"])),
                    "text": "".join(s["text"] for s in line["spans"]).strip(),
                    "font": s0["font"], "size": round(s0["size"], 2),
                    "color": "#%06x" % s0["color"],
                    "bold": bool(s0["flags"] & 16), "italic": bool(s0["flags"] & 2),
                })
        blocks = []
        for block in page.get_text("dict")["blocks"]:
            block_lines = [ln for ln in block.get("lines", []) if any(sp["text"].strip() for sp in ln["spans"])]
            if not block_lines:
                continue
            texts = ["".join(sp["text"] for sp in ln["spans"]).strip() for ln in block_lines]
            width = block["bbox"][2] - block["bbox"][0]
            joined = texts[0]
            for prev_ln, nxt in zip(block_lines, texts[1:]):
                # Lines that run close to the block's right edge are wrapped prose.
                wrapped = prev_ln["bbox"][2] - block["bbox"][0] > 0.7 * width
                joined += (" " if wrapped else "\n") + nxt
            s0 = next(sp for sp in block_lines[0]["spans"] if sp["text"].strip())
            blocks.append({
                "rect": to_pdf_rect(page, fitz.Rect(block["bbox"])), "text": joined,
                "font": s0["font"], "size": round(s0["size"], 2), "color": "#%06x" % s0["color"],
                "bold": bool(s0["flags"] & 16), "italic": bool(s0["flags"] & 2),
                "line_count": len(block_lines),
            })
        images = [{"xref": im["xref"], "rect": to_pdf_rect(page, fitz.Rect(im["bbox"]))}
                  for im in page.get_image_info(xrefs=True) if im.get("xref")]
        links = []
        for i, ln in enumerate(page.get_links()):
            links.append({"index": i, "rect": to_pdf_rect(page, ln["from"]),
                          "uri": ln.get("uri"), "page": ln.get("page")})
        return {"index": index, "lines": lines, "blocks": blocks, "images": images, "links": links}
    finally:
        doc.close()


def search(entry: DocEntry, query: str, limit: int = 500) -> list[dict]:
    doc = entry.open()
    try:
        hits = []
        for page in doc:
            for r in page.search_for(query):
                context = page.get_textbox(fitz.Rect(page.rect.x0, r.y0 - 1, page.rect.x1, r.y1 + 1))
                hits.append({"page": page.number, "rect": to_pdf_rect(page, r),
                             "context": " ".join(context.split())[:200]})
                if len(hits) >= limit:
                    return hits
        return hits
    finally:
        doc.close()


def page_text(entry: DocEntry) -> list[str]:
    doc = entry.open()
    try:
        return [p.get_text("text") for p in doc]
    finally:
        doc.close()

