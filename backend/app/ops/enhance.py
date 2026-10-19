"""Enhance pages: watermark, header & footer, Bates numbering, background."""

from __future__ import annotations

import datetime as dt
import math
from typing import Literal

import pymupdf as fitz

from ..coords import parse_color
from . import Ctx, op, page_list


@op("add_watermark", "enhance", "Add a text or image watermark to pages")
def add_watermark(doc: fitz.Document, ctx: Ctx, text: str | None = None, blob_id: str | None = None,
                  pages: list[int] | None = None, fontsize: float = 60, color: str = "#888888",
                  opacity: float = 0.25, angle: float = 45, behind: bool = False,
                  scale: float = 0.5):
    if (text is None) == (blob_id is None):
        raise ValueError("Give exactly one of text or blob_id")
    image = ctx.blob(blob_id)[1] if blob_id else None
    for i in page_list(doc, pages):
        pg = doc[i]
        # Work in unrotated space but centre on the visible page.
        area = pg.cropbox
        center = fitz.Point((area.x0 + area.x1) / 2, (area.y0 + area.y1) / 2)
        if image is not None:
            w, h = area.width * scale, area.height * scale
            rect = fitz.Rect(center.x - w / 2, center.y - h / 2, center.x + w / 2, center.y + h / 2)
            pg.insert_image(rect, stream=image, keep_proportion=True, overlay=not behind,
                            rotate=-pg.rotation % 360)
            continue
        length = fitz.get_text_length(text, fontname="hebo", fontsize=fontsize)
        visual = angle + pg.rotation
        rad = math.radians(visual)
        start = fitz.Point(center.x - math.cos(rad) * length / 2 + math.sin(rad) * fontsize / 3,
                           center.y + math.sin(rad) * length / 2 + math.cos(rad) * fontsize / 3)
        pg.insert_text(start, text, fontsize=fontsize, fontname="hebo", color=parse_color(color),
                       fill_opacity=opacity, stroke_opacity=opacity, overlay=not behind,
                       morph=(start, fitz.Matrix(visual)))


def _expand(template: str, page_no: int, total: int, date: str) -> str:
    return (template.replace("<<page>>", str(page_no)).replace("<<pages>>", str(total))
            .replace("<<date>>", date))


@op("header_footer", "enhance",
    "Add headers/footers; tokens <<page>>, <<pages>>, <<date>> are replaced per page")
def header_footer(doc: fitz.Document, ctx: Ctx, header_left: str = "", header_center: str = "",
                  header_right: str = "", footer_left: str = "", footer_center: str = "",
                  footer_right: str = "", pages: list[int] | None = None, fontsize: float = 10,
                  color: str = "#000000", margin: float = 30, start_number: int = 1,
                  family: Literal["helv", "tiro", "cour"] = "helv"):
    targets = page_list(doc, pages)
    date = dt.date.today().isoformat()
    rgb = parse_color(color)
    for n, i in enumerate(targets):
        pg = doc[i]
        # Positions are computed on the visible (rotated) page, then derotated.
        vis = pg.rect
        derot = pg.derotation_matrix
        number = start_number + n
        slots = {
            ("h", "l"): header_left, ("h", "c"): header_center, ("h", "r"): header_right,
            ("f", "l"): footer_left, ("f", "c"): footer_center, ("f", "r"): footer_right,
        }
        for (row, col), tmpl in slots.items():
            if not tmpl:
                continue
            txt = _expand(tmpl, number, len(targets) + start_number - 1, date)
            width = fitz.get_text_length(txt, fontname=family, fontsize=fontsize)
            x = {"l": margin, "c": (vis.width - width) / 2, "r": vis.width - margin - width}[col]
            y = margin if row == "h" else vis.height - margin + fontsize
            pt = fitz.Point(x, y) * derot
            pg.insert_text(pt, txt, fontsize=fontsize, fontname=family, color=rgb,
                           rotate=pg.rotation)


@op("bates_number", "enhance", "Apply Bates numbering (prefix + zero-padded number + suffix)")
def bates_number(doc: fitz.Document, ctx: Ctx, prefix: str = "", suffix: str = "", start: int = 1,
                 digits: int = 6, position: Literal["footer_right", "footer_left", "footer_center",
                                                    "header_right", "header_left"] = "footer_right",
                 fontsize: float = 9, color: str = "#000000"):
    if not 3 <= digits <= 15:
        raise ValueError("digits must be between 3 and 15")
    labels = [f"{prefix}{str(start + i).zfill(digits)}{suffix}" for i in range(doc.page_count)]
    for i, label in enumerate(labels):
        header_footer(doc, ctx, pages=[i], fontsize=fontsize, color=color, **{position: label})
    return {"first": labels[0], "last": labels[-1]}


@op("set_background", "enhance", "Set a page background color or image")
def set_background(doc: fitz.Document, ctx: Ctx, color: str | None = None, blob_id: str | None = None,
                   pages: list[int] | None = None, opacity: float = 1.0):
    if (color is None) == (blob_id is None):
        raise ValueError("Give exactly one of color or blob_id")
    image = ctx.blob(blob_id)[1] if blob_id else None
    for i in page_list(doc, pages):
        pg = doc[i]
        area = pg.cropbox
        if image is not None:
            pg.insert_image(area, stream=image, keep_proportion=False, overlay=False)
        else:
            pg.draw_rect(area, color=None, fill=parse_color(color), fill_opacity=opacity,
                         overlay=False)
