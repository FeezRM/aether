"""Protect and Redact: passwords, permissions, true redaction, sanitize."""

from __future__ import annotations

import re

import pymupdf as fitz
from pydantic import BaseModel

from ..coords import parse_color, to_mu_rect
from . import Ctx, OpResult, op, page_list

# Built-in sensitive-data patterns for search-and-redact.
PATTERNS = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "phone": r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "credit_card": r"\b(?:\d[ -]?){13,16}\b",
    "date": r"\b(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2})\b",
    "iban": r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b",
    "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "url": r"https?://\S+",
}


class Permissions(BaseModel):
    print: bool = True
    print_high_quality: bool = True
    copy_content: bool = True
    modify: bool = True
    annotate: bool = True
    fill_forms: bool = True
    assemble: bool = True
    accessibility: bool = True

    def flags(self) -> int:
        bits = 0
        for attr, flag in (("print", fitz.PDF_PERM_PRINT), ("print_high_quality", fitz.PDF_PERM_PRINT_HQ),
                           ("copy_content", fitz.PDF_PERM_COPY), ("modify", fitz.PDF_PERM_MODIFY),
                           ("annotate", fitz.PDF_PERM_ANNOTATE), ("fill_forms", fitz.PDF_PERM_FORM),
                           ("assemble", fitz.PDF_PERM_ASSEMBLE),
                           ("accessibility", fitz.PDF_PERM_ACCESSIBILITY)):
            if getattr(self, attr):
                bits |= flag
        return bits


@op("encrypt", "protect", "Encrypt with AES-256: an open password and/or a permissions password")
def encrypt(doc: fitz.Document, ctx: Ctx, user_password: str = "", owner_password: str = "",
            permissions: Permissions = Permissions()):
    if not user_password and not owner_password:
        raise ValueError("Give an open password, a permissions password, or both")
    owner = owner_password or user_password
    data = doc.tobytes(garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_AES_256,
                       owner_pw=owner, user_pw=user_password, permissions=permissions.flags())
    return OpResult(replace_bytes=data, new_passwords=[p for p in (user_password, owner) if p])


@op("remove_security", "protect", "Remove the password and permission restrictions")
def remove_security(doc: fitz.Document, ctx: Ctx):
    known = ctx.entry.known_passwords()
    if known is None:
        raise ValueError("The document is not encrypted")
    if known[1] is None:
        raise ValueError("Enter the permissions (owner) password to remove security")
    data = doc.tobytes(garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE)
    return OpResult(replace_bytes=data)


def tight(rect: fitz.Rect) -> fitz.Rect:
    """Shrink a text line box vertically.

    Line boxes overlap the glyphs of neighbouring lines, and MuPDF redacts every
    glyph a redaction box touches; glyph centres stay inside the tightened box.
    """
    inset = rect.height * 0.22
    return fitz.Rect(rect.x0, rect.y0 + inset, rect.x1, rect.y1 - inset)


@op("mark_redactions", "redact", "Mark areas for redaction (applied later with apply_redactions)")
def mark_redactions(doc: fitz.Document, ctx: Ctx, page: int, rects: list[list[float]],
                    overlay_text: str = "", fill: str = "#000000", from_text: bool = False):
    """from_text: the rects come from a text selection and are tightened to their lines."""
    page_list(doc, [page])
    pg = doc[page]
    for r in rects:
        box = to_mu_rect(pg, r)
        annot = pg.add_redact_annot(tight(box) if from_text else box, text=overlay_text or None,
                                    fill=parse_color(fill), text_color=(1, 1, 1))
        annot.set_info(title="LocalPDF Redaction")
        annot.update()
    return {"marked": len(rects)}


def find_matches(doc: fitz.Document, pages: list[int], terms: list[str],
                 patterns: list[str], regex: list[str]) -> list[tuple[int, fitz.Rect, str]]:
    """Locate words/phrases/regex matches; returns (page, rect in page space, matched text)."""
    found: list[tuple[int, fitz.Rect, str]] = []
    compiled = [re.compile(PATTERNS[p]) for p in patterns] + [re.compile(r) for r in regex]
    for i in pages:
        pg = doc[i]
        for term in terms:
            for r in pg.search_for(term):
                found.append((i, r, term))
        if compiled:
            text_lines = []
            for block in pg.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    text_lines.append("".join(s["text"] for s in line["spans"]))
            for line in text_lines:
                for rx in compiled:
                    for m in rx.finditer(line):
                        hit = m.group(0).strip()
                        if len(hit) < 3:
                            continue
                        for r in pg.search_for(hit):
                            found.append((i, r, hit))
    uniq: dict[tuple, tuple[int, fitz.Rect, str]] = {}
    for i, r, t in found:
        uniq[(i, round(r.x0), round(r.y0), round(r.x1), round(r.y1))] = (i, r, t)
    return list(uniq.values())


@op("search_redact", "redact", "Find words, phrases, built-in patterns or regexes and mark them for redaction")
def search_redact(doc: fitz.Document, ctx: Ctx, terms: list[str] = [], patterns: list[str] = [],
                  regex: list[str] = [], pages: list[int] | None = None,
                  overlay_text: str = "", fill: str = "#000000"):
    unknown = [p for p in patterns if p not in PATTERNS]
    if unknown:
        raise ValueError(f"Unknown patterns {unknown}; choose from {sorted(PATTERNS)}")
    if not (terms or patterns or regex):
        raise ValueError("Nothing to search for")
    hits = find_matches(doc, page_list(doc, pages), terms, patterns, regex)
    for i, r, _t in hits:
        target = doc[i]
        annot = target.add_redact_annot(tight(r), text=overlay_text or None, fill=parse_color(fill),
                                        text_color=(1, 1, 1))
        annot.set_info(title="LocalPDF Redaction")
        annot.update()
    return {"marked": len(hits), "matches": sorted({t for _i, _r, t in hits})}


@op("apply_redactions", "redact", "Permanently remove all content under marked redactions")
def apply_redactions(doc: fitz.Document, ctx: Ctx, remove_images: bool = True,
                     remove_graphics: bool = True):
    applied = 0
    for pg in doc:
        n = len(list(pg.annots(types=[fitz.PDF_ANNOT_REDACT])))
        if n:
            pg.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_PIXELS if remove_images else fitz.PDF_REDACT_IMAGE_NONE,
                graphics=(fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED if remove_graphics
                          else fitz.PDF_REDACT_LINE_ART_NONE))
            applied += n
    if not applied:
        raise ValueError("There are no marked redactions to apply")
    return {"applied": applied}


@op("sanitize", "protect", "Remove hidden information: metadata, JavaScript, attachments, hidden text, links")
def sanitize(doc: fitz.Document, ctx: Ctx, metadata: bool = True, javascript: bool = True,
             attachments: bool = True, hidden_text: bool = True, links: bool = False,
             thumbnails: bool = True, reset_fields: bool = False):
    doc.scrub(attached_files=attachments, embedded_files=attachments, hidden_text=hidden_text,
              javascript=javascript, metadata=metadata, xml_metadata=metadata, remove_links=links,
              thumbnails=thumbnails, reset_fields=reset_fields, redactions=True,
              reset_responses=True, clean_pages=True)
