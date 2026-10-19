"""A scripted stand-in for the local model, so the assistant can be tested without model files."""

from __future__ import annotations

import hashlib
import json
import math


class FakeLLM:
    """Replies with the scripted outputs in order; dicts are sent as JSON.

    Each call is recorded (messages and whether a schema constrained it).
    """

    def __init__(self, *replies, n_ctx: int = 8192) -> None:
        self.replies = list(replies)
        self.n_ctx = n_ctx
        self.calls: list[dict] = []

    def stream(self, messages, schema=None, max_tokens=512):
        self.calls.append({"messages": messages, "schema": schema})
        if not self.replies:
            raise AssertionError("FakeLLM ran out of scripted replies")
        reply = self.replies.pop(0)
        text = json.dumps(reply) if isinstance(reply, dict) else reply
        for i in range(0, len(text), 7):
            yield text[i:i + 7]

    def embed(self, texts):
        """Bag-of-words vectors hashed into 64 dimensions."""
        out = []
        for t in texts:
            v = [0.0] * 64
            for w in t.lower().split():
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out
