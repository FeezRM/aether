"""Model evals: real requests against a downloaded model, scored on the resulting document.

Opt-in, since they need the model files and take a while:

    AETHER_EVAL_TIER=lite .venv/bin/python -m pytest -q tests/ai_eval
    AETHER_EVAL_TIER=standard .venv/bin/python -m pytest -q tests/ai_eval

Every confirmation is approved. The check looks at what the document became (or
what the answer said), never at the exact wording or tool sequence.
"""

import os

import pymupdf as fitz
import pytest

from app.ai import agent, models
from app.ai.runtime import Runtime
from app.main import store
from conftest import make_text_pdf

TIER = os.environ.get("AETHER_EVAL_TIER")
pytestmark = [
    pytest.mark.usefixtures("no_network"),
    pytest.mark.skipif(not TIER, reason="set AETHER_EVAL_TIER=lite|standard to run model evals"),
]


@pytest.fixture(scope="module")
def llm():
    if not models.installed(TIER):
        pytest.skip(f"{TIER} model is not downloaded")
    rt = Runtime()
    models.set_active(TIER)
    return rt.get()


def doc_of(doc_id) -> fitz.Document:
    return fitz.open(stream=store.get(doc_id).plain_bytes(), filetype="pdf")


def all_text(doc_id) -> str:
    return "\n".join(p.get_text() for p in doc_of(doc_id))


def annots(doc_id, kind):
    return [a for p in doc_of(doc_id) for a in p.annots() if a.type[1] == kind]


# (request, check(doc_id, answer) -> bool)
TASKS = [
    ("What's the contact email?", lambda d, a: "jane.doe@example.com" in a),
    ("What phone number is listed?", lambda d, a: "555-123-4567" in a),
    ("How many chapters does this document have?", lambda d, a: "3" in a or "three" in a.lower()),
    ("Which page is chapter 2 on?", lambda d, a: "2" in a),
    ("Replace “sample contract” with “final agreement” everywhere",
     lambda d, a: "final agreement" in all_text(d) and "sample contract" not in all_text(d)),
    ("Highlight every SSN in the document", lambda d, a: len(annots(d, "Highlight")) >= 3),
    ("Delete page 3", lambda d, a: doc_of(d).page_count == 2 and "Chapter 3" not in all_text(d)),
    ("Rotate page 2 by 90 degrees", lambda d, a: doc_of(d)[1].rotation == 90 and doc_of(d)[0].rotation == 0),
    ("Insert a blank page at the end", lambda d, a: doc_of(d).page_count == 4),
    ("Add a DRAFT watermark to every page", lambda d, a: all("DRAFT" in p.get_text() for p in doc_of(d))),
    ("Put page numbers in the footer", lambda d, a: "2" in doc_of(d)[1].get_text().split("I agree")[-1]),
    ("Redact all the email addresses",
     lambda d, a: "jane.doe@example.com" not in all_text(d) and "SSN" in all_text(d)),
    ("Add a sticky note next to “I agree” on page 1 that says Sign here",
     lambda d, a: any("Sign here" in n.info["content"] for n in annots(d, "Text"))),
    ("Set the document title to Lease Agreement", lambda d, a: doc_of(d).metadata["title"] == "Lease Agreement"),
    ("Stamp the first page as Approved", lambda d, a: any(s.parent.number == 0 for s in annots(d, "Stamp"))),
    ("Change the sentence “This is page 1 of the sample contract.” to “This page is the cover.”",
     lambda d, a: "This page is the cover." in doc_of(d)[0].get_text()),
]


@pytest.mark.parametrize("request_text,check", TASKS, ids=[t[0][:40] for t in TASKS])
def test_task(llm, request_text, check):
    store._docs.clear()
    doc_id = store.add("sample.pdf", make_text_pdf()).id
    events = []
    for e in agent.run_turn(lambda: llm, store, doc_id, request_text, []):
        events.append(e)
        if e["type"] == "confirm":
            agent.turns[e["turn"]].decide(True)
    answer = "".join(e["text"] for e in events if e["type"] == "token")
    errors = [e["text"] for e in events if e["type"] == "error"]
    assert not errors, errors
    assert check(doc_id, answer), f"answer: {answer!r}; steps: {[e for e in events if e['type'] == 'tool_call']}"
