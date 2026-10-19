# Local AI assistant

Ask questions about the open PDF, or tell it what to change. The model runs inside Aether's own process
(llama.cpp through `llama-cpp-python`), reading a model file from disk. There is no Ollama, no cloud
service, and no separate app to install.

## Models

Pick a tier in the **Ask AI** panel. Each one is downloaded once and then works offline.

| Tier | Chat model | Embeddings | Download | Memory |
|---|---|---|---|---|
| **Lite** | LFM2-1.2B, Q4_K_M | bge-small-en-v1.5, Q8_0 | about 0.8 GB | runs on 8 GB machines |
| **Standard** | Qwen3-4B-Instruct-2507, Q4_K_M | bge-small-en-v1.5, Q8_0 | about 2.5 GB | recommended from 12–16 GB |

The panel recommends a tier based on the computer's RAM. The manifest is `TIERS` in
`backend/app/ai/models.py`. Files are stored in `~/.aether/models` (override with `AETHER_MODELS_DIR`).

**Checksums.** Every download is checked against a SHA-256 before use. Until the manifest is pinned, the hash
comes from Hugging Face's `X-Linked-Etag` header for the file. To record exact revisions and hashes in the
source, run `.venv/bin/python scripts/pin_models.py` from `backend/` on a machine that can reach
huggingface.co, then commit the result.

## Privacy

- Downloading a model is the only time Aether connects to the internet. It happens only when you click
  **Download**. Documents are never sent anywhere.
- `app/ai/models.py` is the only module allowed to import networking code. A test parses every module under
  `backend/app` and checks this.
- The AI tests run with every non-loopback connection blocked.
- Models load from local paths only. `Llama.from_pretrained`, which downloads from a hub, is never used.

## How it works

Each message is one *turn*, streamed to the panel as server-sent events from `POST /api/ai/chat`.

1. **Route.** The model classifies the request into one category (`question`, `text`, `comments`, `pages`,
   `layout`, `forms`, `protect`). A grammar limits its output to valid JSON naming one of them.
2. **Questions** are answered from the document's text blocks, the same ones the editor uses, so each block
   has a page and a position.
   - Short documents go to the model whole.
   - Longer ones are searched with BM25 keyword ranking fused with embedding similarity.
   - Answers cite pages as `[p3]`. Clicking a citation scrolls to the passage and highlights it.
   - Scanned pages with no text get a suggestion to run OCR.
3. **Edits** pick among only that category's 4–10 tools. Each step is a grammar-constrained JSON
   object: either `{"tool": ..., "args": ...}` or `{"answer": ...}`. A turn takes at most 6 steps.
   - Tools come from the editor's operation registry, with argument schemas generated from the op
     signatures (`app/ai/tools.py`).
   - The model never handles coordinates. It names text ("the paragraph containing …", "next to 'I agree'")
     and the tool finds it.
   - Pages are numbered from 1, as people say them.
   - Destructive changes pause for **Approve / Cancel** in the chat: deleting pages, applying redactions,
     encryption, removing security, sanitizing, flattening, clearing the form, removing all comments,
     and optimizing.
   - Everything a turn changes is **one undo step**. Ctrl+Z, or "Undo these changes" in the chat, reverts
     the whole turn.

Some things the assistant leaves to the tool panels: anything that needs an uploaded file, drawing, or a
digital ID (images, ink, signatures, certificate signing, inserting another PDF).

## Tests

```bash
cd backend
.venv/bin/python -m pytest -q tests/test_ai_*.py
```

These run without model files:
- A scripted `FakeLLM` drives the routing, tools, confirmation, undo grouping, retrieval and citations.
- `tests/tiny_gguf.py` builds a tiny random-weight GGUF so the real llama.cpp path (grammars, embeddings,
  loading a tier from disk) is exercised too.

### Model evals

`tests/ai_eval/test_eval.py` holds 16 real requests scored on what the document became, not on wording.
They are opt-in:

```bash
AETHER_EVAL_TIER=lite .venv/bin/python -m pytest -q tests/ai_eval
AETHER_EVAL_TIER=standard .venv/bin/python -m pytest -q tests/ai_eval
```

| Tier | Passed | Notes |
|---|---|---|
| Lite | not yet run | |
| Standard | not yet run | |

Record the results here when the model choice changes. If Lite scores poorly, the first alternative to try is
Qwen3-1.7B (Apache-2.0, about 1.1 GB); it is a one-line change in the manifest.

## Licences

- llama.cpp and `llama-cpp-python`: MIT.
- bge-small-en-v1.5: MIT.
- Qwen3-4B-Instruct-2507: Apache-2.0.
- **LFM2-1.2B: LFM Open License v1.0.** It allows commercial use below a revenue threshold. Check its terms
  before a commercial release, or switch Lite to Qwen3-1.7B.

The model files are downloaded by the user from Hugging Face and are not distributed with Aether.
