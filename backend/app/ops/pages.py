"""Organize Pages: delete, rotate, reorder, insert, replace, crop, label."""

from __future__ import annotations

from typing import Literal

import pymupdf as fitz
from pydantic import BaseModel

from ..coords import to_mu_rect
from . import Ctx, op, page_list


@op("delete_pages", "organize", "Delete the given pages")
def delete_pages(doc: fitz.Document, ctx: Ctx, pages: list[int]):
    targets = page_list(doc, pages)
    if len(targets) >= doc.page_count:
        raise ValueError("Cannot delete every page")
    doc.delete_pages(targets)


@op("rotate_pages", "organize", "Rotate pages by a multiple of 90 degrees")
def rotate_pages(doc: fitz.Document, ctx: Ctx, angle: Literal[90, -90, 180, 270],
                 pages: list[int] | None = None):
    for i in page_list(doc, pages):
        page = doc[i]
        page.set_rotation((page.rotation + angle) % 360)


@op("reorder_pages", "organize", "Reorder pages; `order` lists every old index in its new position")
def reorder_pages(doc: fitz.Document, ctx: Ctx, order: list[int]):
    if sorted(order) != list(range(doc.page_count)):
        raise ValueError("order must be a permutation of all page indices")
    doc.select(order)


@op("move_page", "organize", "Move one page to a new position")
def move_page(doc: fitz.Document, ctx: Ctx, page: int, to: int):
    page_list(doc, [page])
    if not 0 <= to < doc.page_count:
        raise ValueError("Target position out of range")
    order = [i for i in range(doc.page_count) if i != page]
    order.insert(to, page)
    doc.select(order)


@op("duplicate_pages", "organize", "Duplicate pages, placing each copy right after its original")
def duplicate_pages(doc: fitz.Document, ctx: Ctx, pages: list[int]):
    for i in sorted(page_list(doc, pages), reverse=True):
        doc.fullcopy_page(i, i + 1)


@op("insert_blank", "organize", "Insert blank pages before index `at` (page_count appends)")
def insert_blank(doc: fitz.Document, ctx: Ctx, at: int, count: int = 1,
                 width: float | None = None, height: float | None = None):
    if not 0 <= at <= doc.page_count:
        raise ValueError("Insert position out of range")
    ref = doc[min(at, doc.page_count - 1)].rect if doc.page_count else fitz.paper_rect("letter")
    for _ in range(count):
        doc.new_page(at, width=width or ref.width, height=height or ref.height)


@op("insert_pdf", "organize", "Insert pages from an uploaded PDF or image before index `at`")
def insert_pdf(doc: fitz.Document, ctx: Ctx, blob_id: str, at: int,
               from_page: int = 0, to_page: int = -1):
    if not 0 <= at <= doc.page_count:
        raise ValueError("Insert position out of range")
    name, data = ctx.blob(blob_id)
    src = open_any_as_pdf(name, data)
    doc.insert_pdf(src, from_page=from_page, to_page=to_page, start_at=at)


@op("replace_pages", "organize", "Replace pages starting at `start` with pages from an uploaded PDF")
def replace_pages(doc: fitz.Document, ctx: Ctx, start: int, blob_id: str,
                  from_page: int = 0, to_page: int = -1):
    page_list(doc, [start])
    name, data = ctx.blob(blob_id)
    src = open_any_as_pdf(name, data)
    last = src.page_count - 1 if to_page < 0 else to_page
    count = last - from_page + 1
    end = min(start + count, doc.page_count)
    doc.insert_pdf(src, from_page=from_page, to_page=last, start_at=start)
    doc.delete_pages(list(range(start + count, end + count)))


@op("crop_pages", "organize", "Set the crop box from a rectangle (PDF space) or from margins in points")
def crop_pages(doc: fitz.Document, ctx: Ctx, pages: list[int] | None = None,
               rect: list[float] | None = None,
               margins: list[float] | None = None):
    """margins = [left, top, right, bottom] in points, relative to the media box."""
    if (rect is None) == (margins is None):
        raise ValueError("Give exactly one of rect or margins")
    for i in page_list(doc, pages):
        page = doc[i]
        if rect is not None:
            box = to_mu_rect(page, rect)
        else:
            mb = page.mediabox
            left, top, right, bottom = margins
            box = fitz.Rect(left, top, mb.width - right, mb.height - bottom)
        box = box & fitz.Rect(0, 0, page.mediabox.width, page.mediabox.height)
        if box.is_empty:
            raise ValueError("Crop leaves an empty page")
        page.set_cropbox(box)


class PageLabelRule(BaseModel):
    startpage: int
    style: Literal["D", "r", "R", "a", "A", ""] = "D"
    prefix: str = ""
    firstpagenum: int = 1


@op("set_page_labels", "organize", "Set logical page numbering (e.g. i, ii, iii then 1, 2, 3)")
def set_page_labels(doc: fitz.Document, ctx: Ctx, rules: list[PageLabelRule]):
    doc.set_page_labels([r.model_dump() for r in rules])


def open_any_as_pdf(name: str, data: bytes) -> fitz.Document:
    """Open a PDF, or convert an image / other MuPDF-readable file to PDF."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "pdf"
    src = fitz.open(stream=data, filetype=ext)
    if src.is_pdf:
        return src
    pdf_bytes = src.convert_to_pdf()
    return fitz.open("pdf", pdf_bytes)
