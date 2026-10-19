"""HTTP API for the assistant and its models, under /api/ai."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..store import DocumentStore, StoreError
from . import agent, models
from .runtime import runtime, runtime_installed


class Chat(BaseModel):
    doc_id: str
    message: str
    history: list[dict[str, Any]] = []


class Decision(BaseModel):
    approve: bool


def same_origin(request: Request) -> None:
    """Refuse requests a web page on another site sends to this local server.

    CORS stops other sites reading responses, but a body-less POST still arrives; without this a
    page could start a model download or a turn. Browsers always send Origin on such requests.
    """
    origin = request.headers.get("origin")
    if request.method != "GET" and origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise StoreError("Cross-site request refused", 403)


def build_router(store: DocumentStore) -> APIRouter:
    router = APIRouter(prefix="/api/ai", dependencies=[Depends(same_origin)])

    @router.get("/models")
    def list_models():
        return {**models.status(), "runtime": runtime_installed()}

    @router.post("/models/{tier}/download")
    def download_model(tier: str):
        models.downloads.start(tier)
        return models.status()

    @router.post("/models/{tier}/cancel")
    def cancel_download(tier: str):
        models.downloads.cancel(tier)
        return models.status()

    @router.post("/models/{tier}/activate")
    def activate_model(tier: str):
        models.set_active(tier)
        runtime.unload()
        return models.status()

    @router.delete("/models/{tier}")
    def delete_model(tier: str):
        if tier not in models.TIERS:
            raise StoreError(f"Unknown model tier {tier!r}", 404)
        runtime.unload()
        models.delete(tier)
        return models.status()

    @router.post("/chat")
    def chat(body: Chat):
        store.get(body.doc_id)  # 404 before the stream starts
        events = agent.run_turn(runtime.get, store, body.doc_id, body.message, body.history)
        lines = (f"data: {json.dumps(e, default=str)}\n\n" for e in events)
        return StreamingResponse(lines, media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store"})

    @router.post("/chat/{turn_id}/confirm")
    def confirm(turn_id: str, body: Decision):
        turn = agent.turns.get(turn_id)
        if turn is None:
            raise StoreError("That request has already finished", 404)
        turn.decide(body.approve)
        return {"ok": True}

    return router
