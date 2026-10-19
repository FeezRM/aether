"""Comment: text markup, sticky notes, text boxes, drawing tools, stamps, replies."""

from __future__ import annotations

from typing import Literal

import pymupdf as fitz

from ..coords import parse_color, to_mu_point, to_mu_rect
from . import Ctx, op, page_list

DEFAULT_AUTHOR = "LocalPDF User"

STAMPS = ["Approved", "AsIs", "Confidential", "Departmental", "Experimental", "Expired",
          "Final", "ForComment", "ForPublicRelease", "NotApproved", "NotForPublicRelease",
          "Sold", "TopSecret", "Draft"]


def _page(doc: fitz.Document, page: int) -> fitz.Page:
    page_list(doc, [page])
    return doc[page]


def _finish(annot: fitz.Annot, contents: str | None, author: str | None,
            opacity: float | None = None) -> dict:
    info = {"content": contents or annot.info.get("content", ""), "title": author or DEFAULT_AUTHOR}
    annot.set_info(info)
    if opacity is not None:
        annot.set_opacity(opacity)
    annot.update()
    return {"xref": annot.xref}


def _annot(page: fitz.Page, xref: int) -> fitz.Annot:
    annot = page.load_annot(xref)
    if annot is None:
        raise ValueError(f"No annotation {xref} on this page")
    return annot


@op("add_markup", "comment", "Highlight, underline, strike out or squiggly-underline text areas")
def add_markup(doc: fitz.Document, ctx: Ctx, page: int, rects: list[list[float]],
               kind: Literal["highlight", "underline", "strikeout", "squiggly"] = "highlight",
               color: str | None = None, contents: str | None = None,
               author: str | None = None):
    pg = _page(doc, page)
    if not rects:
        raise ValueError("No text area given")
    quads = [to_mu_rect(pg, r).quad for r in rects]
    adder = {"highlight": pg.add_highlight_annot, "underline": pg.add_underline_annot,
             "strikeout": pg.add_strikeout_annot, "squiggly": pg.add_squiggly_annot}[kind]
    annot = adder(quads=quads)
    default = {"highlight": "#ffd400", "underline": "#2a7fff",
               "strikeout": "#e0302d", "squiggly": "#2fae4e"}[kind]
    annot.set_colors(stroke=parse_color(color or default))
    return _finish(annot, contents, author)


@op("highlight_text", "comment", "Highlight every occurrence of a phrase")
def highlight_text(doc: fitz.Document, ctx: Ctx, text: str, pages: list[int] | None = None,
                   color: str | None = None, contents: str | None = None):
    count = 0
    for i in page_list(doc, pages):
        pg = doc[i]
        for quad in pg.search_for(text, quads=True):
            annot = pg.add_highlight_annot(quad)
            annot.set_colors(stroke=parse_color(color or "#ffd400"))
            _finish(annot, contents, None)
            count += 1
    return {"count": count}


@op("add_note", "comment", "Add a sticky note")
def add_note(doc: fitz.Document, ctx: Ctx, page: int, point: list[float], contents: str,
             icon: Literal["Note", "Comment", "Help", "Insert", "Key", "NewParagraph",
                           "Paragraph"] = "Comment",
             color: str = "#ffd400", author: str | None = None):
    pg = _page(doc, page)
    p = to_mu_point(pg, point)
    annot = pg.add_text_annot(p, contents, icon=icon)
    annot.set_colors(stroke=parse_color(color))
    return _finish(annot, contents, author)


@op("add_text_box", "comment", "Add a text box comment (FreeText), optionally with a callout")
def add_text_box(doc: fitz.Document, ctx: Ctx, page: int, rect: list[float], text: str,
                 fontsize: float = 12, color: str = "#000000", fill: str | None = None,
                 border_color: str | None = None, callout: list[list[float]] | None = None,
                 author: str | None = None):
    pg = _page(doc, page)
    kw = dict(fontsize=fontsize, text_color=parse_color(color),
              fill_color=parse_color(fill, None), border_color=parse_color(border_color, None))
    if callout:
        kw["callout"] = [to_mu_point(pg, p) for p in callout]
        kw["line_end"] = fitz.PDF_ANNOT_LE_OPEN_ARROW
    annot = pg.add_freetext_annot(to_mu_rect(pg, rect), text, **kw)
    return _finish(annot, text, author)


@op("add_typewriter", "comment", "Add typewriter text (borderless text box)")
def add_typewriter(doc: fitz.Document, ctx: Ctx, page: int, point: list[float], text: str,
                   fontsize: float = 12, color: str = "#000000", author: str | None = None):
    pg = _page(doc, page)
    p = to_mu_point(pg, point)
    width = fitz.get_text_length(max(text.splitlines() or [""], key=len), fontsize=fontsize) + 8
    height = fontsize * 1.3 * max(1, len(text.splitlines())) + 4
    rect = fitz.Rect(p.x, p.y, p.x + width, p.y + height)
    annot = pg.add_freetext_annot(rect, text, fontsize=fontsize, text_color=parse_color(color))
    return _finish(annot, text, author)


@op("add_shape", "comment", "Draw a rectangle, ellipse, line, arrow, polygon, polyline or cloud")
def add_shape(doc: fitz.Document, ctx: Ctx, page: int,
              kind: Literal["rect", "circle", "line", "arrow", "polygon", "polyline", "cloud"],
              rect: list[float] | None = None, points: list[list[float]] | None = None,
              color: str = "#e0302d", fill: str | None = None, width: float = 1.5,
              contents: str | None = None, author: str | None = None,
              opacity: float | None = None):
    pg = _page(doc, page)
    if kind in ("rect", "circle"):
        if rect is None:
            raise ValueError("rect is required")
        box = to_mu_rect(pg, rect)
        annot = pg.add_rect_annot(box) if kind == "rect" else pg.add_circle_annot(box)
    else:
        if not points or len(points) < 2:
            raise ValueError("At least two points are required")
        pts = [to_mu_point(pg, p) for p in points]
        if kind in ("line", "arrow"):
            annot = pg.add_line_annot(pts[0], pts[-1])
            if kind == "arrow":
                annot.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_CLOSED_ARROW)
        elif kind == "polyline":
            annot = pg.add_polyline_annot(pts)
        else:
            annot = pg.add_polygon_annot(pts)
            if kind == "cloud":
                annot.set_border(clouds=2)
    annot.set_colors(stroke=parse_color(color), fill=parse_color(fill, None))
    annot.set_border(width=width)
    return _finish(annot, contents, author, opacity)


@op("add_ink", "comment", "Freehand drawing from one or more strokes")
def add_ink(doc: fitz.Document, ctx: Ctx, page: int, strokes: list[list[list[float]]],
            color: str = "#2a7fff", width: float = 2, author: str | None = None):
    pg = _page(doc, page)
    paths = [[tuple(to_mu_point(pg, p)) for p in s] for s in strokes if len(s) >= 2]
    if not paths:
        raise ValueError("No stroke with at least two points")
    annot = pg.add_ink_annot(paths)
    annot.set_colors(stroke=parse_color(color))
    annot.set_border(width=width)
    return _finish(annot, None, author)


@op("erase_ink", "comment", "Delete ink drawings that intersect a rectangle")
def erase_ink(doc: fitz.Document, ctx: Ctx, page: int, rect: list[float]):
    pg = _page(doc, page)
    box = to_mu_rect(pg, rect)
    removed = 0
    for annot in list(pg.annots(types=[fitz.PDF_ANNOT_INK])):
        if annot.rect.intersects(box):
            pg.delete_annot(annot)
            removed += 1
    return {"removed": removed}


@op("add_stamp", "comment", "Add a standard stamp (Approved, Draft, Confidential, ...)")
def add_stamp(doc: fitz.Document, ctx: Ctx, page: int, rect: list[float], stamp: str = "Approved",
              author: str | None = None):
    if stamp not in STAMPS:
        raise ValueError(f"Unknown stamp. Choose one of: {', '.join(STAMPS)}")
    pg = _page(doc, page)
    annot = pg.add_stamp_annot(to_mu_rect(pg, rect), stamp=STAMPS.index(stamp))
    return _finish(annot, stamp, author)


@op("add_image_stamp", "comment", "Add a custom stamp from an uploaded image")
def add_image_stamp(doc: fitz.Document, ctx: Ctx, page: int, rect: list[float], blob_id: str,
                    author: str | None = None):
    pg = _page(doc, page)
    _name, data = ctx.blob(blob_id)
    annot = pg.add_stamp_annot(to_mu_rect(pg, rect), stamp=data)
    return _finish(annot, "Custom stamp", author)


@op("add_caret", "comment", "Insert-text caret mark")
def add_caret(doc: fitz.Document, ctx: Ctx, page: int, point: list[float], contents: str = "",
              author: str | None = None):
    pg = _page(doc, page)
    annot = pg.add_caret_annot(to_mu_point(pg, point))
    return _finish(annot, contents, author)


@op("add_file_annotation", "comment", "Attach an uploaded file as a pushpin comment")
def add_file_annotation(doc: fitz.Document, ctx: Ctx, page: int, point: list[float], blob_id: str,
                        author: str | None = None):
    pg = _page(doc, page)
    name, data = ctx.blob(blob_id)
    annot = pg.add_file_annot(to_mu_point(pg, point), data, name, icon="PushPin")
    return _finish(annot, name, author)


@op("update_annotation", "comment", "Change an annotation's text, color or opacity")
def update_annotation(doc: fitz.Document, ctx: Ctx, page: int, xref: int,
                      contents: str | None = None, color: str | None = None,
                      opacity: float | None = None, rect: list[float] | None = None):
    pg = _page(doc, page)
    annot = _annot(pg, xref)
    if contents is not None:
        annot.set_info(content=contents)
    if color is not None:
        if annot.type[0] == fitz.PDF_ANNOT_FREE_TEXT:
            annot.update(text_color=parse_color(color))
        else:
            annot.set_colors(stroke=parse_color(color))
    if opacity is not None:
        annot.set_opacity(opacity)
    if rect is not None:
        annot.set_rect(to_mu_rect(pg, rect))
    annot.update()


@op("delete_annotation", "comment", "Delete an annotation")
def delete_annotation(doc: fitz.Document, ctx: Ctx, page: int, xref: int):
    pg = _page(doc, page)
    pg.delete_annot(_annot(pg, xref))


@op("reply_annotation", "comment", "Reply to a comment")
def reply_annotation(doc: fitz.Document, ctx: Ctx, page: int, xref: int, text: str,
                     author: str | None = None):
    pg = _page(doc, page)
    parent = _annot(pg, xref)
    r = parent.rect
    reply = pg.add_text_annot(fitz.Point(r.x0, r.y0), text)
    reply.set_info(content=text, title=author or DEFAULT_AUTHOR)
    reply.set_irt_xref(parent.xref)
    reply.set_flags(fitz.PDF_ANNOT_IS_HIDDEN)
    reply.update()
    return {"xref": reply.xref}


@op("flatten_annotations", "comment", "Burn comments into the page content so they can no longer be edited")
def flatten_annotations(doc: fitz.Document, ctx: Ctx, include_forms: bool = False):
    doc.bake(annots=True, widgets=include_forms)


@op("delete_all_annotations", "comment", "Remove all comments (not form fields or links)")
def delete_all_annotations(doc: fitz.Document, ctx: Ctx, pages: list[int] | None = None):
    removed = 0
    for i in page_list(doc, pages):
        pg = doc[i]
        for annot in list(pg.annots()):
            pg.delete_annot(annot)
            removed += 1
    return {"removed": removed}
