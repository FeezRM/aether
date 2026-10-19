"""In-memory document store with undo/redo snapshots.

Every open document is held as its current PDF bytes. An operation opens those
bytes, mutates the document, and the resulting bytes become the new state; the
previous bytes are pushed onto the undo stack. Nothing is written outside the
local machine.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf as fitz

MAX_HISTORY = 40


class StoreError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class DocEntry:
    id: str
    name: str
    data: bytes
    passwords: list[str] = field(default_factory=list)
    source_path: Path | None = None
    undo: list[bytes] = field(default_factory=list)
    redo: list[bytes] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    version: int = 0
    dirty: bool = False
    # Commits made since begin_group(); None when no group is open.
    group_commits: int | None = None

    def open(self) -> fitz.Document:
        doc = fitz.open(stream=self.data, filetype="pdf")
        if doc.needs_pass and not any(doc.authenticate(pw) for pw in self.passwords):
            doc.close()
            raise StoreError("Password required", 401)
        return doc

    def is_encrypted(self) -> bool:
        doc = fitz.open(stream=self.data, filetype="pdf")
        try:
            return bool(doc.needs_pass or (doc.metadata or {}).get("encryption"))
        finally:
            doc.close()

    def plain_bytes(self) -> bytes:
        """Unencrypted copy, for the local viewer and converters that cannot take passwords."""
        if not self.is_encrypted():
            return self.data
        doc = self.open()
        try:
            return doc.tobytes(encryption=fitz.PDF_ENCRYPT_NONE)
        finally:
            doc.close()

    def known_passwords(self) -> tuple[str | None, str | None, int] | None:
        """(open password, permissions password, permission bits) for the current bytes.

        Returns None if unencrypted.

        An entry is None when it is not known; an empty open password means the
        file opens without one.
        """
        doc = fitz.open(stream=self.data, filetype="pdf")
        try:
            if not (doc.needs_pass or (doc.metadata or {}).get("encryption")):
                return None
            user = None if doc.needs_pass else ""
        finally:
            doc.close()
        owner = None
        for pw in self.passwords:
            probe = fitz.open(stream=self.data, filetype="pdf")
            rc = probe.authenticate(pw)
            probe.close()
            if rc & 2 and user is None:
                user = pw
            if rc & 4 and owner is None:
                owner = pw
        perms = -4
        if user is not None:
            # Permission bits are only reported after authenticating as the user.
            probe = fitz.open(stream=self.data, filetype="pdf")
            probe.authenticate(user)
            perms = probe.permissions
            probe.close()
        return user, owner, perms

    def serialize(self, doc: fitz.Document) -> bytes:
        """Save an edited document, re-applying its encryption.

        MuPDF drops encryption when it re-serializes an in-memory document, so it
        is re-applied here. That needs the permissions password: without it an
        edit would silently strip the file's protection, so the edit is refused.
        """
        known = self.known_passwords()
        if known is None:
            return save_bytes(doc)
        user, owner, perms = known
        if owner is None:
            raise StoreError("This document is protected. Enter its permissions "
                             "(owner) password to edit it.", 403)
        if user is None:
            raise StoreError("Enter the document's open password as well to keep it protected.", 403)
        return doc.tobytes(garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_AES_256,
                           user_pw=user, owner_pw=owner, permissions=perms)

    def commit(self, new_data: bytes) -> None:
        self.undo.append(self.data)
        if len(self.undo) > MAX_HISTORY:
            self.undo.pop(0)
        self.redo.clear()
        self.data = new_data
        self.version += 1
        self.dirty = True
        if self.group_commits is not None:
            self.group_commits += 1

    def begin_group(self) -> None:
        """Start collecting commits into one undo step (an assistant turn)."""
        self.group_commits = 0

    def end_group(self) -> None:
        """Collapse the commits since begin_group() so a single undo reverts them all."""
        n, self.group_commits = self.group_commits, None
        if n and n > 1:
            # The last n undo entries are the states before each commit; keep the oldest.
            n = min(n, len(self.undo))
            del self.undo[len(self.undo) - n + 1:]


class DocumentStore:
    def __init__(self) -> None:
        self._docs: dict[str, DocEntry] = {}
        self._blobs: dict[str, tuple[str, bytes]] = {}

    # documents -----------------------------------------------------------
    def add(self, name: str, data: bytes, password: str | None = None,
            source_path: Path | None = None) -> DocEntry:
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:  # PyMuPDF raises several types for bad input
            raise StoreError(f"Not a readable PDF: {exc}") from exc
        if doc.needs_pass and not doc.authenticate(password or ""):
            doc.close()
            raise StoreError("Password required", 401)
        doc.close()
        entry = DocEntry(id=uuid.uuid4().hex[:12], name=name, data=data,
                         passwords=[password] if password else [], source_path=source_path)
        self._docs[entry.id] = entry
        return entry

    def get(self, doc_id: str) -> DocEntry:
        entry = self._docs.get(doc_id)
        if entry is None:
            raise StoreError("Document not found", 404)
        return entry

    def close(self, doc_id: str) -> None:
        self._docs.pop(doc_id, None)

    def list(self) -> list[DocEntry]:
        return list(self._docs.values())

    def undo(self, doc_id: str) -> DocEntry:
        e = self.get(doc_id)
        with e.lock:
            if not e.undo:
                raise StoreError("Nothing to undo")
            e.redo.append(e.data)
            e.data = e.undo.pop()
            e.version += 1
            e.dirty = True
        return e

    def redo(self, doc_id: str) -> DocEntry:
        e = self.get(doc_id)
        with e.lock:
            if not e.redo:
                raise StoreError("Nothing to redo")
            e.undo.append(e.data)
            e.data = e.redo.pop()
            e.version += 1
            e.dirty = True
        return e

    # blobs: auxiliary uploads (images, other PDFs, certificates) ----------
    def add_blob(self, name: str, data: bytes) -> str:
        blob_id = uuid.uuid4().hex[:12]
        self._blobs[blob_id] = (name, data)
        return blob_id

    def blob(self, blob_id: str) -> tuple[str, bytes]:
        b = self._blobs.get(blob_id)
        if b is None:
            raise StoreError(f"Upload {blob_id} not found", 404)
        return b


def save_bytes(doc: fitz.Document) -> bytes:
    """Serialize a document compactly without changing its encryption."""
    return doc.tobytes(garbage=3, deflate=True)
