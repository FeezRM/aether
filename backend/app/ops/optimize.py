"""Optimize / Compress PDF: downsample images, subset fonts, drop unused objects."""

from __future__ import annotations

from typing import Literal

import pymupdf as fitz

from . import Ctx, OpResult, op

PRESETS = {
    # (dpi threshold, dpi target, jpeg quality)
    "low": (300, 200, 85),
    "medium": (200, 150, 75),
    "high": (150, 96, 60),
}


@op("optimize", "optimize", "Reduce file size: downsample images, subset fonts, remove unused objects")
def optimize(doc: fitz.Document, ctx: Ctx, level: Literal["low", "medium", "high"] = "medium",
             subset_fonts: bool = True, remove_thumbnails: bool = True,
             remove_metadata: bool = False):
    before = len(ctx.entry.data)
    threshold, target, quality = PRESETS[level]
    doc.rewrite_images(dpi_threshold=threshold, dpi_target=target, quality=quality)
    if subset_fonts:
        doc.subset_fonts(fallback=True)
    if remove_thumbnails or remove_metadata:
        doc.scrub(attached_files=False, clean_pages=False, embedded_files=False, hidden_text=False,
                  javascript=False, metadata=remove_metadata, redactions=False, remove_links=False,
                  reset_fields=False, reset_responses=False, thumbnails=remove_thumbnails,
                  xml_metadata=remove_metadata)
    data = doc.tobytes(garbage=4, deflate=True, deflate_images=True, deflate_fonts=True,
                       clean=True, use_objstms=1)
    if len(data) >= before:
        # Never make the file bigger; keep the structural clean-up only if it helps.
        return OpResult(data={"before": before, "after": before, "saved_percent": 0.0})
    return OpResult(replace_bytes=data, data={
        "before": before, "after": len(data),
        "saved_percent": round(100 * (before - len(data)) / before, 1)})
