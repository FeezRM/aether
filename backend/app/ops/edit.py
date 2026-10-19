"""Edit PDF: edit text in place, add text and images, links, attachments, metadata."""

from __future__ import annotations

from typing import Literal

import pymupdf as fitz

from ..coords import parse_color, to_mu_point, to_mu_rect
from . import Ctx, op, page_list

ALIGN = {"left": 0, "center": 1, "right": 2, "justify": 3}

# Base-14 font names understood by PyMuPDF, keyed by (family, bold, italic).
BASE14 = {
    ("sans", False, False): "helv", ("sans", True, False): "hebo",
    ("sans", False, True): "heit", ("sans", True, True): "hebi",
    ("serif", False, False): "tiro", ("serif", True, False): "tibo",
    ("serif", False, True): "tiit", ("serif", True, True): "tibi",
    ("mono", False, False): "cour", ("mono", True, False): "cobo",
    ("mono", False, True): "coit", ("mono", True, True): "cobi",
}

Family = Literal["sans", "serif", "mono"]


def _check_page(doc: fitz.Document, page: int) -> fitz.Page:
    page_list(doc, [page])
    return doc[page]


def _fit_textbox(page: fitz.Page, rect: fitz.Rect, text: str, **kw) -> None:
    """Insert text into rect, growing the box downward until it fits."""
    box = fitz.Rect(rect)
    for _ in range(40):
        if page.insert_textbox(box, text, **kw) >= 0:
            return
        box.y1 += max(kw.get("fontsize", 11), 4)
        if box.y1 > page.mediabox.height + 2000:
            break
    raise ValueError("Text does not fit on the page")


@op("add_text", "edit", "Add a new text block to the page content")
def add_text(doc: fitz.Document, ctx: Ctx, page: int, rect: list[float], text: str,
             fontsize: float = 12, family: Family = "sans", bold: bool = False,
             italic: bool = False, color: str = "#000000",
             align: Literal["left", "center", "right", "justify"] = "left"):
    pg = _check_page(doc, page)
    box = to_mu_rect(pg, rect)
    if box.width < 4:
        box.x1 = box.x0 + max(_text_width(text, fontsize, family, bold, italic) + 4, 40)
    if box.height < fontsize * 1.4:
        box.y1 = box.y0 + fontsize * 1.4
    _fit_textbox(pg, box, text, fontsize=fontsize,
                 fontname=BASE14[(family, bold, italic)], color=parse_color(color),
                 align=ALIGN[align])


def _text_width(text: str, size: float, family: str, bold: bool, italic: bool) -> float:
    longest = max(text.splitlines() or [""], key=len)
    return fitz.Font(BASE14[(family, bold, italic)]).text_length(longest, fontsize=size)


def _lines_in(page: fitz.Page, box: fitz.Rect) -> list[list[dict]]:
    """Text lines (as span lists) whose spans have their centre inside box.

    Line boxes of neighbouring lines usually overlap by a few points, so a plain
    intersection test would also pick up the line above or below.
    """
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip() and box.contains(_center(s["bbox"]))]
            if spans:
                out.append(spans)
    return out


def _center(bbox) -> fitz.Point:
    return fitz.Point((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def _span_at(page: fitz.Page, hit: fitz.Rect) -> dict | None:
    """The span a search hit falls in, to copy its style."""
    for block in page.get_text("dict", clip=hit)["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["text"].strip() and fitz.Rect(span["bbox"]).intersects(hit):
                    return span
    return None


def _family_from_span(span: dict) -> tuple[str, bool, bool]:
    flags = span["flags"]
    name = span["font"].lower()
    family = "mono" if flags & 8 or "mono" in name or "courier" in name else (
        "serif" if flags & 4 or "times" in name or "serif" in name and "sans" not in name else "sans")
    bold = bool(flags & 16) or "bold" in name or "black" in name
    italic = bool(flags & 2) or "italic" in name or "oblique" in name
    return family, bold, italic


def _reusable_font(doc: fitz.Document, page: fitz.Page, span: dict, text: str):
    """Return (fontname, fontbuffer) for the span's embedded font when it has every glyph."""
    for xref, ext, _type, basefont, refname, _enc in page.get_fonts():
        if basefont.split("+")[-1] != span["font"].split("+")[-1]:
            continue
        try:
            _name, fext, _stype, buffer = doc.extract_font(xref)
        except Exception:
            return None
        if not buffer or fext in ("n/a", "pfa", "pfb"):
            return None
        try:
            font = fitz.Font(fontbuffer=buffer)
        except Exception:
            return None
        if all(font.has_glyph(ord(ch)) for ch in text if not ch.isspace()):
            return f"E{xref}", buffer
        return None
    return None


@op("edit_text", "edit", "Replace the text of a line or paragraph, keeping its font, size and color where possible")
def edit_text(doc: fitz.Document, ctx: Ctx, page: int, rect: list[float], text: str,
              fontsize: float | None = None, color: str | None = None,
              family: Family | None = None, bold: bool | None = None,
              italic: bool | None = None):
    pg = _check_page(doc, page)
    box = to_mu_rect(pg, rect)
    lines = _lines_in(pg, box)
    if not lines:
        raise ValueError("No text found in the selected area")
    spans = [s for line in lines for s in line]
    first = spans[0]
    size = fontsize or first["size"]
    rgb = parse_color(color) if color else fitz.sRGB_to_pdf(first["color"])
    fam, b, it = _family_from_span(first)
    fam = family or fam
    b = b if bold is None else bold
    it = it if italic is None else italic
    text_box = fitz.Rect(spans[0]["bbox"])
    for s in spans:
        text_box |= fitz.Rect(s["bbox"])

    reuse = None
    if family is None and bold is None and italic is None:
        reuse = _reusable_font(doc, pg, first, text)

    # Inset the redaction vertically so glyphs of neighbouring lines stay untouched.
    inset = fitz.Rect(first["bbox"]).height * 0.3
    pg.add_redact_annot(fitz.Rect(text_box.x0, text_box.y0 + inset, text_box.x1, text_box.y1 - inset))
    pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                        graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                        text=fitz.PDF_REDACT_TEXT_REMOVE)
    kw = dict(fontsize=size, color=rgb)
    if reuse:
        name, buffer = reuse
        pg.insert_font(fontname=name, fontbuffer=buffer)
        kw["fontname"] = name
        font = fitz.Font(fontbuffer=buffer)
    else:
        kw["fontname"] = BASE14[(fam, b, it)]
        font = fitz.Font(kw["fontname"])

    origin = fitz.Point(first["origin"])
    # A single line may extend to the right margin (assumed equal to the left one);
    # a paragraph keeps its own width.
    right = text_box.x1 if len(lines) > 1 else max(text_box.x1, pg.mediabox.width - text_box.x0)
    if "\n" not in text and origin.x + font.text_length(text, fontsize=size) <= right:
        # Fits on one line: write at the original baseline so nothing shifts.
        pg.insert_text(origin, text, **kw)
    else:
        if len(lines) > 1:
            spacing = (lines[-1][0]["origin"][1] - lines[0][0]["origin"][1]) / (len(lines) - 1)
            kw["lineheight"] = max(spacing / size, 1.0)
        top = origin.y - size * font.ascender
        _fit_textbox(pg, fitz.Rect(text_box.x0, top, right, text_box.y1), text, **kw)
    return {"font": kw["fontname"], "fontsize": size, "reused_font": bool(reuse)}


@op("replace_text", "edit", "Find text across the document and replace every match")
def replace_text(doc: fitz.Document, ctx: Ctx, find: str, replace: str,
                 pages: list[int] | None = None, case_sensitive: bool = False):
    if not find:
        raise ValueError("Search text is empty")
    count = 0
    for i in page_list(doc, pages):
        pg = doc[i]
        hits = pg.search_for(find)
        if case_sensitive:
            hits = [r for r in hits if pg.get_textbox(r).strip() == find]
        targets = []
        for r in hits:
            span = _span_at(pg, r)
            if span is None:
                continue
            fam, b, it = _family_from_span(span)
            targets.append((r, span["size"], fitz.sRGB_to_pdf(span["color"]), BASE14[(fam, b, it)]))
            pg.add_redact_annot(r)
        if not targets:
            continue
        pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                            graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        for r, size, rgb, font in targets:
            baseline = fitz.Point(r.x0, r.y1 - size * 0.22)
            pg.insert_text(baseline, replace, fontsize=size, color=rgb, fontname=font)
            count += 1
    return {"replaced": count}


@op("add_image", "edit", "Place an uploaded image on a page")
def add_image(doc: fitz.Document, ctx: Ctx, page: int, rect: list[float], blob_id: str,
              keep_proportion: bool = True):
    pg = _check_page(doc, page)
    _name, data = ctx.blob(blob_id)
    pg.insert_image(to_mu_rect(pg, rect), stream=data, keep_proportion=keep_proportion)


@op("replace_image", "edit", "Replace an existing image (by xref) with an uploaded image")
def replace_image(doc: fitz.Document, ctx: Ctx, page: int, xref: int, blob_id: str):
    pg = _check_page(doc, page)
    _name, data = ctx.blob(blob_id)
    pg.replace_image(xref, stream=data)


@op("delete_area_content", "edit", "Remove images, drawings and/or text inside a rectangle")
def delete_area_content(doc: fitz.Document, ctx: Ctx, page: int, rect: list[float],
                        images: bool = True, graphics: bool = True, text: bool = False):
    pg = _check_page(doc, page)
    pg.add_redact_annot(to_mu_rect(pg, rect))
    pg.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_REMOVE if images else fitz.PDF_REDACT_IMAGE_NONE,
        graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED if graphics else fitz.PDF_REDACT_LINE_ART_NONE,
        text=fitz.PDF_REDACT_TEXT_REMOVE if text else fitz.PDF_REDACT_TEXT_NONE)


@op("add_link", "edit", "Add a link to a web address or to a page in this document")
def add_link(doc: fitz.Document, ctx: Ctx, page: int, rect: list[float],
             uri: str | None = None, target_page: int | None = None):
    pg = _check_page(doc, page)
    if (uri is None) == (target_page is None):
        raise ValueError("Give exactly one of uri or target_page")
    link = {"from": to_mu_rect(pg, rect)}
    if uri is not None:
        if not uri.lower().startswith(("http://", "https://", "mailto:")):
            raise ValueError("Link must start with http://, https:// or mailto:")
        link.update(kind=fitz.LINK_URI, uri=uri)
    else:
        page_list(doc, [target_page])
        link.update(kind=fitz.LINK_GOTO, page=target_page, to=fitz.Point(0, 0))
    pg.insert_link(link)


@op("delete_link", "edit", "Delete the n-th link on a page")
def delete_link(doc: fitz.Document, ctx: Ctx, page: int, index: int):
    pg = _check_page(doc, page)
    links = pg.get_links()
    if not 0 <= index < len(links):
        raise ValueError("Link index out of range")
    pg.delete_link(links[index])


@op("add_attachment", "edit", "Embed an uploaded file in the PDF")
def add_attachment(doc: fitz.Document, ctx: Ctx, blob_id: str, description: str = ""):
    name, data = ctx.blob(blob_id)
    existing = set(doc.embfile_names())
    final = name
    n = 1
    while final in existing:
        stem, _, ext = name.rpartition(".")
        final = f"{stem or name} ({n}){'.' + ext if stem else ''}"
        n += 1
    doc.embfile_add(final, data, filename=name, desc=description)
    return {"name": final}


@op("delete_attachment", "edit", "Remove an embedded file")
def delete_attachment(doc: fitz.Document, ctx: Ctx, name: str):
    if name not in doc.embfile_names():
        raise ValueError(f"No attachment named {name!r}")
    doc.embfile_del(name)


@op("set_metadata", "edit", "Set document properties (title, author, subject, keywords)")
def set_metadata(doc: fitz.Document, ctx: Ctx, title: str | None = None,
                 author: str | None = None, subject: str | None = None,
                 keywords: str | None = None, creator: str | None = None):
    meta = dict(doc.metadata or {})
    for key, value in (("title", title), ("author", author), ("subject", subject),
                       ("keywords", keywords), ("creator", creator)):
        if value is not None:
            meta[key] = value
    doc.set_metadata(meta)


@op("add_text_point", "edit", "Add a single line of text at a point (baseline)")
def add_text_point(doc: fitz.Document, ctx: Ctx, page: int, point: list[float], text: str,
                   fontsize: float = 12, family: Family = "sans", bold: bool = False,
                   italic: bool = False, color: str = "#000000"):
    pg = _check_page(doc, page)
    pg.insert_text(to_mu_point(pg, point), text, fontsize=fontsize,
                   fontname=BASE14[(family, bold, italic)], color=parse_color(color))
