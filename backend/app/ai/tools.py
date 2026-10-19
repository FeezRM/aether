"""What the assistant can do: a curated subset of the operation registry.

The model never handles coordinates. It names text ("the paragraph that
mentions the deposit") and these wrappers resolve that to a page and rect
with the editor's own search before calling the op. Pages are 1-based here,
as people say them, and converted for the 0-based ops.

Argument schemas are generated from the op signatures, so the grammar that
constrains the model always matches what the op accepts.
"""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model

from ..inspect_doc import doc_info, page_detail, search
from ..ops import OPS, run_op
from ..ops.comment import STAMPS
from ..ops.protect import PATTERNS
from ..store import DocEntry, DocumentStore

PAGE_KEYS = {"page", "pages", "at", "to"}
PAGE_HELP = {
    "page": "Page number, starting at 1",
    "pages": "Page numbers, starting at 1; leave out for every page",
    "at": "Insert before this page number (one more than the page count appends at the end)",
    "to": "New position as a page number, starting at 1",
}

CATEGORIES: dict[str, str] = {
    "question": "Answer a question about the document's content without changing it",
    "text": "Change the document's own text: replace words, rewrite a paragraph",
    "comments": "Highlight text, add sticky notes or stamps, remove comments",
    "pages": "Delete, rotate, move, duplicate or insert pages",
    "layout": "Watermarks, headers and footers, page numbers, Bates numbers, bookmarks, properties, file size, OCR",
    "forms": "Read or fill form fields, clear the form",
    "protect": "Redact sensitive information, passwords and encryption, remove hidden data, flatten",
}


@dataclass
class ToolCtx:
    store: DocumentStore
    doc_id: str

    @property
    def entry(self) -> DocEntry:
        return self.store.get(self.doc_id)

    def op(self, name: str, **params) -> Any:
        return run_op(self.store, self.doc_id, name, params)


@dataclass
class Tool:
    name: str
    categories: tuple[str, ...]
    description: str
    args: type[BaseModel]
    run: Callable[..., Any]
    mutates: bool = True
    # Ask the user before running: the change destroys content or is hard to see.
    confirm: bool = False
    summary: Callable[[dict], str] | None = field(default=None, repr=False)

    def schema(self) -> dict:
        return inline_refs(self.args.model_json_schema())

    def describe(self, args: dict) -> str:
        if self.summary:
            return self.summary(args)
        shown = ", ".join(f"{k}={v!r}" for k, v in args.items() if v not in (None, [], ""))
        return f"{self.name}({shown})"


def inline_refs(schema: dict) -> dict:
    """Replace $ref pointers with their definitions; grammar converters handle plain schemas best."""
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].rsplit("/", 1)[-1]])
            return {k: walk(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def _help(pname: str, default: Any) -> str | None:
    if pname == "pages" and default is ...:
        return "Page numbers, starting at 1"
    return PAGE_HELP.get(pname)


def _op_hints(name: str) -> tuple[inspect.Signature, dict[str, Any]]:
    fn = inspect.unwrap(OPS[name].fn)
    return inspect.signature(fn), typing.get_type_hints(fn)


def op_args_model(name: str, hide: tuple[str, ...] = (),
                  override: dict[str, tuple[Any, Any]] | None = None) -> type[BaseModel]:
    """A pydantic model of an op's parameters, minus doc/ctx and hidden ones, pages 1-based.

    `override` maps a parameter to a replacement (type, default); `...` makes it required.
    """
    sig, hints = _op_hints(name)
    fields: dict[str, Any] = {}
    for pname, p in sig.parameters.items():
        if pname in ("doc", "ctx") or pname in hide:
            if pname not in ("doc", "ctx") and p.default is inspect.Parameter.empty:
                raise ValueError(f"Cannot hide required parameter {name}.{pname}")
            continue
        default = ... if p.default is inspect.Parameter.empty else p.default
        hint = hints[pname]
        if pname in (override or {}):
            hint, default = override[pname]
        fields[pname] = (hint, Field(default, description=_help(pname, default)))
    return create_model(f"{name}_args", **fields)


def to_op_pages(args: dict) -> dict:
    out = dict(args)
    for key in PAGE_KEYS & out.keys():
        v = out[key]
        if isinstance(v, int):
            out[key] = v - 1
        elif isinstance(v, list):
            out[key] = [p - 1 for p in v]
    return out


def op_tool(name: str, categories: tuple[str, ...], description: str | None = None,
            hide: tuple[str, ...] = (), override: dict[str, tuple[Any, Any]] | None = None,
            confirm: bool = False, summary: Callable[[dict], str] | None = None) -> Tool:
    def run(ctx: ToolCtx, **args):
        return ctx.op(name, **to_op_pages(args))

    return Tool(name, categories, description or OPS[name].description,
                op_args_model(name, hide, override), run, confirm=confirm, summary=summary)


def custom_tool(categories: tuple[str, ...], description: str, mutates: bool = True,
                confirm: bool = False):
    """Register a hand-written tool; its arguments come from the function's keyword parameters."""
    def decorate(fn):
        sig = inspect.signature(fn)
        hints = typing.get_type_hints(fn)
        fields = {}
        for pname, p in list(sig.parameters.items())[1:]:
            default = ... if p.default is inspect.Parameter.empty else p.default
            fields[pname] = (hints[pname], Field(default, description=_help(pname, default)))
        args = create_model(f"{fn.__name__}_args", **fields)
        TOOLS[fn.__name__] = Tool(fn.__name__, categories, description, args,
                                  lambda ctx, **a: fn(ctx, **a), mutates=mutates, confirm=confirm)
        return fn
    return decorate


def _pages(pages: list[int] | None) -> str:
    return "every page" if not pages else "page " + ", ".join(map(str, pages)) if len(pages) == 1 \
        else "pages " + ", ".join(map(str, pages))


TOOLS: dict[str, Tool] = {}
EVERY = tuple(c for c in CATEGORIES if c != "question")


# ------------------------------------------------------------ read tools --

@custom_tool(EVERY, "Find where a word or phrase appears; returns page numbers and the surrounding line",
             mutates=False)
def search_text(ctx: ToolCtx, query: str):
    hits = search(ctx.entry, query, limit=20)
    return {"matches": len(hits),
            "hits": [{"page": h["page"] + 1, "line": h["context"]} for h in hits[:10]]}


@custom_tool(EVERY, "Read the text of one page, paragraph by paragraph", mutates=False)
def read_page(ctx: ToolCtx, page: int):
    detail = page_detail(ctx.entry, page - 1)
    return {"page": page, "paragraphs": [b["text"] for b in detail["blocks"]][:40]}


@custom_tool(("forms",), "List the form fields with their names, types, current values and options",
             mutates=False)
def list_fields(ctx: ToolCtx):
    fields = doc_info(ctx.entry)["fields"]
    return {"fields": [{"name": f["name"], "type": f["type"], "value": f["value"], "page": f["page"] + 1,
                        **({"options": f["options"]} if f["options"] else {})} for f in fields]}


# ------------------------------------------------------- anchored edits --

def _find_block(entry: DocEntry, contains: str, page: int | None) -> tuple[int, dict]:
    needle = " ".join(contains.lower().split())
    info_pages = range(doc_info(entry)["page_count"]) if page is None else [page - 1]
    for p in info_pages:
        for block in page_detail(entry, p)["blocks"]:
            if needle in " ".join(block["text"].lower().split()):
                return p, block
    raise ValueError(f"No paragraph contains {contains!r}")


@custom_tool(("text",), "Replace the whole text of the paragraph that contains a phrase, keeping its font")
def rewrite_paragraph(ctx: ToolCtx, contains: str, new_text: str, page: int | None = None):
    p, block = _find_block(ctx.entry, contains, page)
    ctx.op("edit_text", page=p, rect=block["rect"], text=new_text)
    return {"page": p + 1, "old_text": block["text"]}


@custom_tool(("comments",), "Attach a sticky note next to the first place a phrase appears")
def add_note(ctx: ToolCtx, near: str, note: str, page: int | None = None):
    hits = search(ctx.entry, near)
    if page is not None:
        hits = [h for h in hits if h["page"] == page - 1]
    if not hits:
        raise ValueError(f"{near!r} does not appear in the document")
    h = hits[0]
    ctx.op("add_note", page=h["page"], point=[h["rect"][2] + 4, h["rect"][3]], contents=note)
    return {"page": h["page"] + 1}


@custom_tool(("comments",), "Put a standard stamp in the top-right corner of a page")
def add_stamp(ctx: ToolCtx, page: int, stamp: Literal[tuple(STAMPS)] = "Approved"):  # type: ignore[valid-type]
    pages = doc_info(ctx.entry)["pages"]
    if not 0 < page <= len(pages):
        raise ValueError(f"There is no page {page}")
    w, h = pages[page - 1]["width"], pages[page - 1]["height"]
    ctx.op("add_stamp", page=page - 1, rect=[w - 216, h - 96, w - 36, h - 36], stamp=stamp)
    return {"page": page, "stamp": stamp}


@custom_tool(("protect",), "Mark text for redaction: exact words or phrases and/or built-in patterns "
             f"({', '.join(PATTERNS)}). Marks are reviewed, then removed with apply_redactions")
def mark_redactions(ctx: ToolCtx, terms: list[str] = [],  # noqa: B006
                    patterns: list[Literal[tuple(PATTERNS)]] = [],  # type: ignore[valid-type]  # noqa: B006
                    pages: list[int] | None = None):
    res = ctx.op("search_redact", terms=terms, patterns=list(patterns),
                 pages=None if pages is None else [p - 1 for p in pages])
    return res


# --------------------------------------------------------- registry ops --

for t in [
    op_tool("replace_text", ("text",), "Find text across the document and replace every match",
            summary=lambda a: f"Replace “{a['find']}” with “{a['replace']}”"),
    op_tool("highlight_text", ("comments",), "Highlight every occurrence of a phrase", hide=("color",)),
    op_tool("delete_all_annotations", ("comments",), "Remove all comments", confirm=True,
            summary=lambda a: f"Remove all comments on {_pages(a.get('pages'))}"),
    op_tool("delete_pages", ("pages",), confirm=True, summary=lambda a: f"Delete {_pages(a['pages'])}"),
    op_tool("rotate_pages", ("pages",)),
    op_tool("move_page", ("pages",)),
    op_tool("duplicate_pages", ("pages",)),
    op_tool("insert_blank", ("pages",), hide=("width", "height")),
    op_tool("add_watermark", ("layout",), "Add a diagonal text watermark",
            hide=("blob_id", "behind", "scale"), override={"text": (str, ...)}),
    op_tool("header_footer", ("layout",), "Add header and/or footer text. Use <<page>> for the page number, "
            "<<pages>> for the page count and <<date>> for today", hide=("margin", "family", "color")),
    op_tool("bates_number", ("layout",), hide=("color",)),
    op_tool("set_metadata", ("layout",), hide=("creator",)),
    op_tool("add_bookmark", ("layout",), hide=("index",)),
    op_tool("auto_bookmarks", ("layout",)),
    op_tool("optimize", ("layout",), confirm=True, hide=("subset_fonts", "remove_thumbnails"),
            summary=lambda a: f"Reduce the file size ({a.get('level', 'medium')} compression)"),
    op_tool("ocr_pages", ("layout",), hide=("dpi", "language")),
    op_tool("fill_fields", ("forms",), "Fill form fields: {field name: value}; use list_fields for the names"),
    op_tool("clear_form", ("forms",), confirm=True, summary=lambda a: "Clear every form field"),
    op_tool("apply_redactions", ("protect",), confirm=True, hide=("remove_images", "remove_graphics"),
            summary=lambda a: "Permanently remove all content under the redaction marks"),
    op_tool("encrypt", ("protect",), "Protect with an open password and/or a permissions password",
            hide=("permissions",), confirm=True,
            summary=lambda a: "Encrypt the document with the password(s) you gave"),
    op_tool("remove_security", ("protect",), confirm=True,
            summary=lambda a: "Remove the password and permission restrictions"),
    op_tool("sanitize", ("protect",), confirm=True, hide=("thumbnails", "reset_fields"),
            summary=lambda a: "Remove hidden information (metadata, scripts, attachments, hidden text)"),
    op_tool("flatten_annotations", ("protect",), confirm=True,
            summary=lambda a: "Burn comments into the pages so they can no longer be edited"),
]:
    TOOLS[t.name] = t


def tools_for(category: str) -> list[Tool]:
    return [t for t in TOOLS.values() if category in t.categories]
