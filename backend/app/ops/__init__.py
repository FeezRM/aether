"""Operation registry.

Every editing feature is a named operation that mutates an open document.
The HTTP API, batch "Action Wizard" recipes and (later) the local AI assistant
all go through this one registry, so they can only do what the editor can do.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pymupdf as fitz
from pydantic import validate_call

from ..store import DocEntry, DocumentStore


@dataclass
class Ctx:
    store: DocumentStore
    entry: DocEntry

    def blob(self, blob_id: str) -> tuple[str, bytes]:
        return self.store.blob(blob_id)


@dataclass
class OpResult:
    """Return from an op to report data and/or replace the saved bytes."""
    data: dict[str, Any] | None = None
    replace_bytes: bytes | None = None
    # Passwords that open replace_bytes, remembered so later edits can re-encrypt.
    new_passwords: list[str] = field(default_factory=list)


@dataclass
class OpSpec:
    name: str
    category: str
    description: str
    fn: Callable[..., Any]


OPS: dict[str, OpSpec] = {}


def op(name: str, category: str, description: str):
    def decorate(fn):
        validated = validate_call(fn, config={"arbitrary_types_allowed": True})
        OPS[name] = OpSpec(name, category, description, validated)
        return fn
    return decorate


def page_list(doc: fitz.Document, pages: list[int] | None) -> list[int]:
    """Validate 0-based page indices; None means every page."""
    if pages is None:
        return list(range(doc.page_count))
    bad = [p for p in pages if p < 0 or p >= doc.page_count]
    if bad:
        raise ValueError(f"Page index out of range: {bad}")
    return list(dict.fromkeys(pages))


# Import modules for their registration side effects.
from . import (  # noqa: E402,F401
    bookmarks, certs, comment, edit, enhance, forms, ocr, optimize, pages, protect,
)
