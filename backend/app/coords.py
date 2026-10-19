"""Conversions between PDF user space and PyMuPDF page space.

The UI works in PDF user space (origin bottom-left of the unrotated page,
y up), which is what pdf.js reports. PyMuPDF works in unrotated page space
with the origin at the top-left of the media box and y down. Both ignore
/Rotate, so a single matrix per page converts between them.
"""

from __future__ import annotations

from collections.abc import Sequence

import pymupdf as fitz


def to_mu_point(page: fitz.Page, pt: Sequence[float]) -> fitz.Point:
    return fitz.Point(pt[0], pt[1]) * page.transformation_matrix


def to_mu_rect(page: fitz.Page, r: Sequence[float]) -> fitz.Rect:
    rect = fitz.Rect(r[0], r[1], r[2], r[3]) * page.transformation_matrix
    rect.normalize()
    return rect


def to_pdf_rect(page: fitz.Page, r: fitz.Rect) -> list[float]:
    rect = fitz.Rect(r) * ~page.transformation_matrix
    rect.normalize()
    return [round(v, 2) for v in rect]


def to_pdf_point(page: fitz.Page, p: fitz.Point) -> list[float]:
    q = fitz.Point(p) * ~page.transformation_matrix
    return [round(q.x, 2), round(q.y, 2)]


def parse_color(value: str | Sequence[float] | None,
                default: tuple[float, float, float] | None = (0, 0, 0)):
    """Accept '#rrggbb' or an RGB triple in 0..1; return a float triple."""
    if value is None:
        return default
    if isinstance(value, str):
        h = value.lstrip("#")
        if len(h) != 6:
            raise ValueError(f"Bad color {value!r}")
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    if len(value) != 3:
        raise ValueError(f"Bad color {value!r}")
    return tuple(float(v) for v in value)
