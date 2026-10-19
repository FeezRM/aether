"""Bookmarks (document outline): add, rename, delete, replace, and auto-generate."""

from __future__ import annotations

from collections import Counter

import pymupdf as fitz
from pydantic import BaseModel

from . import Ctx, op, page_list


class Bookmark(BaseModel):
    level: int
    title: str
    page: int  # 0-based


def _toc(doc: fitz.Document) -> list[list]:
    return doc.get_toc(simple=True)


def _set(doc: fitz.Document, toc: list[list]) -> None:
    # Levels must start at 1 and never jump by more than one.
    fixed, prev = [], 0
    for level, title, page in toc:
        level = max(1, min(level, prev + 1))
        fixed.append([level, title, page])
        prev = level
    doc.set_toc(fixed)


@op("set_bookmarks", "bookmarks", "Replace the whole outline")
def set_bookmarks(doc: fitz.Document, ctx: Ctx, bookmarks: list[Bookmark]):
    for b in bookmarks:
        page_list(doc, [b.page])
    _set(doc, [[b.level, b.title, b.page + 1] for b in bookmarks])


@op("add_bookmark", "bookmarks", "Add a bookmark pointing at a page")
def add_bookmark(doc: fitz.Document, ctx: Ctx, title: str, page: int, level: int = 1,
                 index: int | None = None):
    page_list(doc, [page])
    toc = _toc(doc)
    entry = [level, title, page + 1]
    if index is None:
        toc.append(entry)
    else:
        toc.insert(max(0, min(index, len(toc))), entry)
    _set(doc, toc)


@op("rename_bookmark", "bookmarks", "Rename the bookmark at an outline index")
def rename_bookmark(doc: fitz.Document, ctx: Ctx, index: int, title: str):
    toc = _toc(doc)
    if not 0 <= index < len(toc):
        raise ValueError("Bookmark index out of range")
    toc[index][1] = title
    _set(doc, toc)


@op("delete_bookmark", "bookmarks", "Delete a bookmark and its children")
def delete_bookmark(doc: fitz.Document, ctx: Ctx, index: int):
    toc = _toc(doc)
    if not 0 <= index < len(toc):
        raise ValueError("Bookmark index out of range")
    level = toc[index][0]
    end = index + 1
    while end < len(toc) and toc[end][0] > level:
        end += 1
    del toc[index:end]
    _set(doc, toc)


@op("auto_bookmarks", "bookmarks", "Build bookmarks from headings detected by font size and weight")
def auto_bookmarks(doc: fitz.Document, ctx: Ctx, max_levels: int = 3, replace: bool = True):
    lines = []
    sizes = Counter()
    for pno, page in enumerate(doc):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = " ".join(s["text"].strip() for s in spans)
                size = round(max(s["size"] for s in spans), 1)
                bold = any(s["flags"] & 16 or "bold" in s["font"].lower() for s in spans)
                sizes[size] += len(text)
                lines.append((pno, size, bold, text, line["bbox"][1]))
    if not lines:
        raise ValueError("No text found; run OCR first on scanned documents")
    body = sizes.most_common(1)[0][0]
    heading_sizes = sorted({s for _p, s, b, t, _y in lines if s > body * 1.15 and len(t) < 120},
                           reverse=True)[:max_levels]
    toc = []
    for pno, size, bold, text, _y in lines:
        if size in heading_sizes and 2 <= len(text) < 120:
            toc.append([heading_sizes.index(size) + 1, text, pno + 1])
    if not toc:
        raise ValueError("No headings detected")
    if not replace:
        toc = _toc(doc) + toc
    _set(doc, toc)
    return {"count": len(toc)}
