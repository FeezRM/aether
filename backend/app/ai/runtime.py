"""The local language model: llama.cpp running inside this process.

Models load only from files in MODELS_DIR, never from a hub. The rest of the
assistant talks to the `LLM` protocol, so tests can substitute a scripted model.
"""

from __future__ import annotations

import json
import math
import threading
import time
from collections.abc import Iterator
from typing import Protocol

from . import models

IDLE_UNLOAD_SECONDS = 300


class RuntimeUnavailable(Exception):
    pass


class LLM(Protocol):
    n_ctx: int

    def stream(self, messages: list[dict], schema: dict | None = None,
               max_tokens: int = 512) -> Iterator[str]:
        """Generate a reply; with `schema`, output is constrained to JSON matching it."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Unit-length embedding vectors, one per text."""
        ...


def runtime_installed() -> bool:
    try:
        import llama_cpp  # noqa: F401
    except ImportError:
        return False
    return True


def _normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class LlamaLLM:
    def __init__(self, tier: models.Tier) -> None:
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeUnavailable("The AI runtime (llama-cpp-python) is not installed") from exc
        self.tier = tier
        self.n_ctx = tier.n_ctx
        self._chat = Llama(model_path=str(tier.chat.path), n_ctx=tier.n_ctx, n_gpu_layers=-1, verbose=False)
        self._embedder = Llama(model_path=str(tier.embed.path), embedding=True, n_ctx=512, verbose=False)
        self._lock = threading.Lock()

    def stream(self, messages: list[dict], schema: dict | None = None,
               max_tokens: int = 512) -> Iterator[str]:
        from llama_cpp import LlamaGrammar

        grammar = LlamaGrammar.from_json_schema(json.dumps(schema), verbose=False) if schema else None
        with self._lock:
            chunks = self._chat.create_chat_completion(
                messages=messages, grammar=grammar, stream=True, temperature=0.2, max_tokens=max_tokens)
            for chunk in chunks:
                piece = chunk["choices"][0]["delta"].get("content")
                if piece:
                    yield piece

    def embed(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            return [_normalize(list(v)) for v in self._embedder.embed(texts)]


class Runtime:
    """Holds at most one loaded tier and unloads it after a while unused."""

    def __init__(self) -> None:
        self._llm: LLM | None = None
        self._tier: str | None = None
        self._override: LLM | None = None
        self._lock = threading.Lock()
        self._last_used = 0.0
        self._timer: threading.Timer | None = None

    def use(self, llm: LLM | None) -> None:
        """Substitute a model (tests); None restores the real one."""
        self._override = llm

    def get(self) -> LLM:
        if self._override is not None:
            return self._override
        tier_id = models.active_tier()
        if tier_id is None:
            raise RuntimeUnavailable("No AI model is downloaded yet")
        with self._lock:
            if self._llm is None or self._tier != tier_id:
                self._llm = None
                self._llm = LlamaLLM(models.TIERS[tier_id])
                self._tier = tier_id
            self._last_used = time.monotonic()
            self._schedule_unload()
            return self._llm

    def unload(self) -> None:
        with self._lock:
            self._llm, self._tier = None, None

    def _schedule_unload(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(IDLE_UNLOAD_SECONDS, self._unload_if_idle)
        self._timer.daemon = True
        self._timer.start()

    def _unload_if_idle(self) -> None:
        if time.monotonic() - self._last_used >= IDLE_UNLOAD_SECONDS:
            self.unload()


runtime = Runtime()
