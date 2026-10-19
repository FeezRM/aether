"""Scan & OCR: add an invisible, searchable text layer to scanned pages with Tesseract."""

from __future__ import annotations

import os
import shutil

import pymupdf as fitz

from . import Ctx, op, page_list


def tessdata_dir() -> str | None:
    if os.environ.get("TESSDATA_PREFIX"):
        return os.environ["TESSDATA_PREFIX"]
    exe = shutil.which("tesseract")
    if not exe:
        return None
    prefix = os.path.dirname(os.path.dirname(os.path.realpath(exe)))
    candidate = os.path.join(prefix, "share", "tessdata")
    return candidate if os.path.isdir(candidate) else None


def page_needs_ocr(page: fitz.Page) -> bool:
    """A page with images but (almost) no extractable text is treated as scanned."""
    return len(page.get_text("text").strip()) < 20 and bool(page.get_images())


@op("ocr_pages", "ocr", "Recognize text on scanned pages and add an invisible searchable text layer")
def ocr_pages(doc: fitz.Document, ctx: Ctx, pages: list[int] | None = None, language: str = "eng",
              dpi: int = 300, force: bool = False):
    tessdata = tessdata_dir()
    if tessdata is None:
        raise ValueError("Tesseract is not installed (brew install tesseract)")
    if not 72 <= dpi <= 600:
        raise ValueError("dpi must be between 72 and 600")
    done, skipped, words_added = [], [], 0
    for i in page_list(doc, pages):
        pg = doc[i]
        if not force and not page_needs_ocr(pg):
            skipped.append(i)
            continue
        tp = pg.get_textpage_ocr(language=language, dpi=dpi, full=True, tessdata=tessdata)
        words = pg.get_text("words", textpage=tp)
        writer = fitz.TextWriter(fitz.Rect(0, 0, pg.mediabox.width, pg.mediabox.height))
        font = fitz.Font("helv")
        for x0, y0, x1, y1, word, *_ in words:
            height = y1 - y0
            if height <= 0 or not word.strip():
                continue
            size = height * 0.9
            natural = font.text_length(word, fontsize=size)
            if natural > 0:
                # Shrink so the invisible word spans its box (keeps selection accurate).
                size *= min(1.0, (x1 - x0) / natural)
            writer.append(fitz.Point(x0, y1 - height * 0.2), word, font=font, fontsize=size)
            words_added += 1
        writer.write_text(pg, render_mode=3)
        done.append(i)
    return {"ocr_pages": done, "skipped_pages": skipped, "words": words_added}
