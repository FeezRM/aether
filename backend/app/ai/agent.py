"""One assistant turn: answer a question, or edit the document through tools.

A turn is a generator of events, which the API streams to the UI:
  start, route, token, tool_call, tool_result, confirm, doc_changed, citations, done, error

Small models stay reliable because each step is narrow: first route the
request to one category, then pick among that category's handful of tools,
with output constrained by a grammar to a valid call or a final answer.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

from pydantic import ValidationError

from ..inspect_doc import doc_info
from ..store import DocumentStore, StoreError
from . import index
from .runtime import LLM
from .tools import CATEGORIES, Tool, ToolCtx, tools_for

MAX_STEPS = 6
HISTORY_TURNS = 6
CONFIRM_TIMEOUT = 600
CITE = re.compile(r"\[p\.?\s?(\d+)\]", re.I)


@dataclass
class Turn:
    id: str
    doc_id: str
    decided: threading.Event = field(default_factory=threading.Event)
    approved: bool = False

    def decide(self, approve: bool) -> None:
        self.approved = approve
        self.decided.set()


turns: dict[str, Turn] = {}
_busy: set[str] = set()
_busy_lock = threading.Lock()


def _history(history: list[dict]) -> list[dict]:
    keep = [h for h in history if h.get("role") in ("user", "assistant") and h.get("content")]
    return [{"role": h["role"], "content": str(h["content"])[:2000]} for h in keep[-HISTORY_TURNS:]]


def _json(llm: LLM, messages: list[dict], schema: dict, max_tokens: int = 600) -> dict:
    text = "".join(llm.stream(messages, schema=schema, max_tokens=max_tokens))
    try:
        value = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"The model returned malformed output: {text[:200]!r}") from exc
    if not isinstance(value, dict):
        raise ValueError("The model returned malformed output")
    return value


# --------------------------------------------------------------- routing --

def route(llm: LLM, message: str, history: list[dict]) -> str:
    listing = "\n".join(f"- {name}: {desc}" for name, desc in CATEGORIES.items())
    messages = [
        {"role": "system", "content": "Classify what the user wants to do with their PDF. "
                                      f"Categories:\n{listing}\nReply with JSON."},
        *history[-2:],
        {"role": "user", "content": message},
    ]
    schema = {"type": "object", "properties": {"category": {"enum": list(CATEGORIES)}},
              "required": ["category"]}
    category = _json(llm, messages, schema, max_tokens=40).get("category")
    return category if category in CATEGORIES else "question"


# -------------------------------------------------------------- question --

def _cite_targets(answer: str, chunks: list[index.Chunk]) -> list[dict]:
    words = set(index.tokens(answer))
    out = []
    for n in dict.fromkeys(int(m) for m in CITE.findall(answer)):
        on_page = [c for c in chunks if c.page == n - 1]
        if not on_page:
            continue
        best = max(on_page, key=lambda c: len(words & set(index.tokens(c.text))))
        out.append({"page": best.page, "rect": best.rect, "context": best.text[:200]})
    return out


def answer_question(llm: LLM, store: DocumentStore, doc_id: str, message: str,
                    history: list[dict]) -> Iterator[dict]:
    entry = store.get(doc_id)
    info = doc_info(entry)
    idx = index.index_for(entry, info["page_count"])
    if not idx.chunks:
        yield {"type": "token", "text": "This document has no text I can read. It looks scanned: run "
                                        "Recognize Text (OCR) first, then ask again."}
        return
    chunks = index.context_chunks(idx, message, llm, llm.n_ctx)
    excerpts = "\n\n".join(f"[p{c.page + 1}] {c.text}" for c in chunks)
    messages = [
        {"role": "system", "content":
            f"You answer questions about the PDF “{info['name']}” ({info['page_count']} pages). "
            "Use only the excerpts below. After each fact, cite its page like [p3]. If the excerpts "
            "do not contain the answer, say you could not find it in the document.\n\n"
            f"Excerpts:\n{excerpts}"},
        *history,
        {"role": "user", "content": message},
    ]
    answer = ""
    for piece in llm.stream(messages, max_tokens=700):
        answer += piece
        yield {"type": "token", "text": piece}
    targets = _cite_targets(answer, chunks)
    if targets:
        yield {"type": "citations", "citations": targets}


# ----------------------------------------------------------------- edits --

def _arg_line(name: str, prop: dict, required: bool) -> str:
    kind = prop.get("type") or "/".join(p.get("type", "") for p in prop.get("anyOf", []) if p.get("type") != "null")
    if "enum" in prop:
        kind = " | ".join(map(str, prop["enum"]))
    elif prop.get("items", {}).get("enum"):
        kind = "list of " + " | ".join(prop["items"]["enum"])
    note = f" — {prop['description']}" if prop.get("description") else ""
    return f"    {name}: {kind}{' (required)' if required else ''}{note}"


def tool_listing(tools: list[Tool]) -> str:
    lines = []
    for t in tools:
        s = t.schema()
        req = set(s.get("required", []))
        lines.append(f"- {t.name}: {t.description}")
        lines += [_arg_line(k, v, k in req) for k, v in s.get("properties", {}).items()]
    return "\n".join(lines)


def step_schema(tools: list[Tool]) -> dict:
    calls = [{"type": "object", "properties": {"tool": {"const": t.name}, "args": t.schema()},
              "required": ["tool", "args"]} for t in tools]
    return {"anyOf": [*calls, {"type": "object", "properties": {"answer": {"type": "string"}},
                               "required": ["answer"]}]}


def _doc_summary(info: dict) -> str:
    parts = [f"The open document is “{info['name']}”, {info['page_count']} pages."]
    if info["fields"]:
        parts.append(f"It has {len(info['fields'])} form fields.")
    if info["annotations"]:
        parts.append(f"It has {len(info['annotations'])} comments.")
    return " ".join(parts)


def edit(llm: LLM, store: DocumentStore, turn: Turn, category: str, message: str,
         history: list[dict]) -> Iterator[dict]:
    ctx = ToolCtx(store, turn.doc_id)
    tools = tools_for(category)
    by_name = {t.name: t for t in tools}
    messages = [
        {"role": "system", "content":
            "You are the assistant inside Aether, a PDF editor, and you change the open document by "
            "calling tools. Reply with one JSON object: {\"tool\": name, \"args\": {...}} to call a tool, "
            "or {\"answer\": text} when you are finished, briefly telling the user what you did. "
            "Pages are numbered from 1. Do only what the user asked; if the tools cannot do it, say so "
            f"in the answer.\n{_doc_summary(doc_info(ctx.entry))}\n\nTools:\n{tool_listing(tools)}"},
        *history,
        {"role": "user", "content": message},
    ]
    schema = step_schema(tools)
    done: list[str] = []
    last_call = None
    for _ in range(MAX_STEPS):
        try:
            step = _json(llm, messages, schema)
        except ValueError:
            break  # ran out of tokens mid-call; report what was done
        if "answer" in step:
            yield {"type": "token", "text": step["answer"]}
            return
        tool = by_name.get(step.get("tool", ""))
        if tool is None:
            break
        raw = step.get("args") or {}
        call = (tool.name, json.dumps(raw, sort_keys=True))
        if call == last_call:
            break  # the model is repeating itself
        last_call = call
        messages.append({"role": "assistant", "content": json.dumps(step)})
        try:
            args = tool.args.model_validate(raw).model_dump(exclude_unset=True)
        except ValidationError as exc:
            messages.append({"role": "user", "content": f"Tool error: {exc.errors()[0]['msg']}"})
            continue
        text = tool.describe(args)
        if tool.confirm:
            yield {"type": "confirm", "turn": turn.id, "text": text, "tool": tool.name, "args": args}
            approved = turn.decided.wait(CONFIRM_TIMEOUT) and turn.approved
            turn.decided.clear()
            if not approved:
                yield {"type": "tool_result", "tool": tool.name, "ok": False, "text": "Cancelled"}
                yield {"type": "token", "text": "OK, I didn't make that change."
                       + (f" Earlier in this request I did: {'; '.join(done)}." if done else "")}
                return
        yield {"type": "tool_call", "tool": tool.name, "args": args, "text": text}
        try:
            result = tool.run(ctx, **args)
        except (ValueError, StoreError) as exc:
            yield {"type": "tool_result", "tool": tool.name, "ok": False, "text": str(exc)}
            messages.append({"role": "user", "content": f"Tool error: {exc}"})
            continue
        yield {"type": "tool_result", "tool": tool.name, "ok": True, "result": result}
        if tool.mutates:
            done.append(text)
            yield {"type": "doc_changed", "info": doc_info(ctx.entry)}
        messages.append({"role": "user", "content": f"Tool result: {json.dumps(result, default=str)[:3000]}"})
    yield {"type": "token", "text": ("Done: " + "; ".join(done) + ".") if done
           else "Sorry, I couldn't work out how to do that. Try rephrasing, or use the tools panel."}


# ------------------------------------------------------------------ turn --

def run_turn(llm_factory, store: DocumentStore, doc_id: str, message: str,
             history: list[dict]) -> Iterator[dict]:
    entry = store.get(doc_id)
    with _busy_lock:
        if doc_id in _busy:
            # A turn left waiting for approval (say the tab was closed) is cancelled, not waited out.
            for t in list(turns.values()):
                if t.doc_id == doc_id:
                    t.decide(False)
            yield {"type": "error", "text": "The assistant is still finishing the previous request. "
                                            "Try again in a moment."}
            return
        _busy.add(doc_id)
    turn = Turn(uuid.uuid4().hex[:12], doc_id)
    turns[turn.id] = turn
    start_version = entry.version
    entry.begin_group()
    try:
        yield {"type": "start", "turn": turn.id}
        llm = llm_factory()
        history = _history(history)
        category = route(llm, message, history)
        yield {"type": "route", "category": category}
        if category == "question":
            yield from answer_question(llm, store, doc_id, message, history)
        else:
            yield from edit(llm, store, turn, category, message, history)
    except Exception as exc:  # report every failure to the chat instead of dropping the stream
        yield {"type": "error", "text": str(exc) or exc.__class__.__name__}
    finally:
        entry.end_group()
        turns.pop(turn.id, None)
        with _busy_lock:
            _busy.discard(doc_id)
    changed = entry.version != start_version
    if changed:
        yield {"type": "doc_changed", "info": doc_info(entry)}
    yield {"type": "done", "changed": changed}
