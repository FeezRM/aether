"""Operation registry.

Every editing feature is a named operation that mutates an open document.
The HTTP API, batch "Action Wizard" recipes and the local AI assistant
all go through this one registry, so they can only do what the editor can do.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pymupdf as fitz
from pydantic import validate_call

from ..store import DocEntry, DocumentStore, StoreError


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


def run_op(store: DocumentStore, doc_id: str, name: str, params: dict[str, Any]) -> Any:
    """Apply one operation to an open document and commit the result as an undo step."""
    spec = OPS.get(name)
    if spec is None:
        raise StoreError(f"Unknown operation {name!r}", 404)
    entry = store.get(doc_id)
    with entry.lock:
        doc = entry.open()
        try:
            result = spec.fn(doc, Ctx(store, entry), **params)
            new_passwords: list[str] = []
            if isinstance(result, OpResult):
                data, new_bytes, new_passwords = result.data, result.replace_bytes, result.new_passwords
            else:
                data, new_bytes = result, None
            if new_bytes is None:
                new_bytes = entry.serialize(doc)
        finally:
            doc.close()
        entry.commit(new_bytes)
        entry.passwords.extend(p for p in new_passwords if p not in entry.passwords)
    return data


# Import modules for their registration side effects.
from . import (  # noqa: E402,F401
    bookmarks, certs, comment, edit, enhance, forms, ocr, optimize, pages, protect,
)
