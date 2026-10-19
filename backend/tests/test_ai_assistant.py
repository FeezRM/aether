import json

import pytest

from app.ai import agent, index
from app.ai.runtime import runtime
from app.ai.tools import CATEGORIES, TOOLS, ToolCtx, tools_for
from app.main import store
from conftest import current, make_image_pdf
from fake_llm import FakeLLM

pytestmark = pytest.mark.usefixtures("no_network")


@pytest.fixture
def llm():
    def make(*replies, **kw):
        fake = FakeLLM(*replies, **kw)
        runtime.use(fake)
        return fake
    yield make
    runtime.use(None)


def chat(client, doc_id, message, history=()):
    r = client.post("/api/ai/chat", json={"doc_id": doc_id, "message": message, "history": list(history)})
    assert r.status_code == 200, r.text
    return [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]


def said(events):
    return "".join(e["text"] for e in events if e["type"] == "token")


def kinds(events):
    return [e["type"] for e in events]


def run_direct(fake, doc_id, message, decide=None):
    """Run a turn without HTTP so a confirmation can be answered mid-stream."""
    events = []
    for e in agent.run_turn(lambda: fake, store, doc_id, message, []):
        events.append(e)
        if e["type"] == "confirm":
            agent.turns[e["turn"]].decide(decide(e))
    return events


# -------------------------------------------------------------- questions --

def test_question_is_answered_from_the_document_with_citations(client, doc_id, llm):
    fake = llm({"category": "question"}, "The contact email is jane.doe@example.com [p2].")
    events = chat(client, doc_id, "What's the contact email?")
    assert {"type": "route", "category": "question"} in events
    assert said(events) == "The contact email is jane.doe@example.com [p2]."
    cites = next(e for e in events if e["type"] == "citations")["citations"]
    assert cites[0]["page"] == 1 and len(cites[0]["rect"]) == 4
    prompt = fake.calls[1]["messages"][0]["content"]
    assert "[p1]" in prompt and "jane.doe@example.com" in prompt
    assert fake.calls[1]["schema"] is None  # free text, streamed
    assert events[-1] == {"type": "done", "changed": False}


def test_history_reaches_the_model(client, doc_id, llm):
    fake = llm({"category": "question"}, "Page 3 [p3].")
    chat(client, doc_id, "And the last one?", history=[
        {"role": "user", "content": "Which page mentions chapter 2?"},
        {"role": "assistant", "content": "Page 2 [p2]."}])
    roles = [m["role"] for m in fake.calls[1]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


def test_scanned_document_suggests_ocr(client, llm):
    r = client.post("/api/documents", files={"file": ("scan.pdf", make_image_pdf(), "application/pdf")})
    llm({"category": "question"})
    events = chat(client, r.json()["id"], "What is the invoice number?")
    assert "OCR" in said(events)


def test_long_documents_are_searched_not_sent_whole(client):
    import pymupdf as fitz

    doc = fitz.open()
    for i in range(40):
        page = doc.new_page()
        topic = "The refundable security deposit is 2400 dollars." if i == 27 else f"Filler clause {i} about delivery."
        page.insert_textbox(fitz.Rect(72, 72, 540, 720), (topic + " ") * 30, fontsize=10)
    doc_id = client.post("/api/documents", files={"file": ("long.pdf", doc.tobytes(), "application/pdf")}).json()["id"]
    entry = store.get(doc_id)
    idx = index.index_for(entry, 40)
    picked = index.context_chunks(idx, "How much is the security deposit?", FakeLLM(), n_ctx=2048)
    assert len(picked) == index.TOP_K
    assert picked[0].page == 27 or any(c.page == 27 for c in picked)
    assert index.context_chunks(idx, "deposit", FakeLLM(), n_ctx=10 ** 6) == idx.chunks


def test_bm25_prefers_rare_matching_terms():
    bm = index.BM25([index.tokens(t) for t in ["the cat sat", "the dog sat", "the deposit is due"]])
    scores = bm.scores(index.tokens("when is the deposit due"))
    assert scores.index(max(scores)) == 2


# ------------------------------------------------------------------ edits --

def test_edit_turn_changes_the_document_and_undoes_in_one_step(client, doc_id, llm):
    llm({"category": "text"},
        {"tool": "replace_text", "args": {"find": "sample contract", "replace": "final agreement"}},
        {"answer": "Replaced it on all 3 pages."})
    events = chat(client, doc_id, "Call it the final agreement instead of the sample contract")
    assert kinds(events)[:3] == ["start", "route", "tool_call"]
    assert "doc_changed" in kinds(events) and events[-1] == {"type": "done", "changed": True}
    assert said(events) == "Replaced it on all 3 pages."
    assert "final agreement" in current(client, doc_id)[2].get_text()
    client.post(f"/api/documents/{doc_id}/undo")
    assert "sample contract" in current(client, doc_id)[2].get_text()


def test_several_edits_in_one_turn_are_one_undo_step(client, doc_id, llm):
    llm({"category": "comments"},
        {"tool": "highlight_text", "args": {"text": "SSN"}},
        {"tool": "add_note", "args": {"near": "I agree", "note": "Check this", "page": 2}},
        {"tool": "add_stamp", "args": {"page": 1, "stamp": "Draft"}},
        {"answer": "Highlighted, noted and stamped."})
    chat(client, doc_id, "highlight the SSNs, add a note on page 2 and stamp it draft")
    info = client.get(f"/api/documents/{doc_id}").json()
    assert sorted(a["type"] for a in info["annotations"]) == ["Highlight"] * 3 + ["Stamp", "Text"]
    assert next(a for a in info["annotations"] if a["type"] == "Text")["page"] == 1
    info = client.post(f"/api/documents/{doc_id}/undo").json()
    assert info["annotations"] == [] and not info["can_undo"]


def test_steps_only_offer_the_routed_categorys_tools(client, doc_id, llm):
    fake = llm({"category": "pages"}, {"answer": "Nothing to do."})
    chat(client, doc_id, "rotate page 2")
    offered = [alt["properties"]["tool"]["const"] for alt in fake.calls[1]["schema"]["anyOf"][:-1]]
    assert offered == [t.name for t in tools_for("pages")]
    assert "delete_pages" in fake.calls[1]["messages"][0]["content"]


def test_tool_errors_are_reported_back_to_the_model(client, doc_id, llm):
    fake = llm({"category": "text"},
               {"tool": "rewrite_paragraph", "args": {"contains": "no such words", "new_text": "x"}},
               {"tool": "replace_text", "args": {"find": "only"}},
               {"answer": "I couldn't find that paragraph."})
    events = chat(client, doc_id, "rewrite the paragraph about pets")
    failed = [e for e in events if e["type"] == "tool_result" and not e["ok"]]
    assert "No paragraph contains" in failed[0]["text"]
    assert "Tool error" in fake.calls[2]["messages"][-1]["content"]
    assert "Tool error" in fake.calls[3]["messages"][-1]["content"]  # missing required argument
    assert events[-1]["changed"] is False


def test_a_repeated_call_ends_the_turn(client, doc_id, llm):
    step = {"tool": "rotate_pages", "args": {"angle": 90, "pages": [1]}}
    llm({"category": "pages"}, step, step)
    events = chat(client, doc_id, "rotate the first page")
    assert said(events).startswith("Done: rotate_pages(")
    assert client.get(f"/api/documents/{doc_id}").json()["pages"][0]["rotation"] == 90


def test_destructive_changes_wait_for_approval(client, doc_id):
    fake = FakeLLM({"category": "pages"}, {"tool": "delete_pages", "args": {"pages": [3]}},
                   {"answer": "Deleted page 3."})
    asked = []
    events = run_direct(fake, doc_id, "delete the last page", lambda e: asked.append(e["text"]) or True)
    assert asked == ["Delete page 3"]
    assert kinds(events).index("confirm") < kinds(events).index("tool_call")
    assert client.get(f"/api/documents/{doc_id}").json()["page_count"] == 2


def test_declining_leaves_the_document_untouched(client, doc_id):
    fake = FakeLLM({"category": "protect"}, {"tool": "mark_redactions", "args": {"patterns": ["ssn"]}},
                   {"tool": "apply_redactions", "args": {}})
    version = store.get(doc_id).version
    events = run_direct(fake, doc_id, "redact the SSNs", lambda e: False)
    assert "didn't make that change" in said(events)
    assert "Earlier in this request I did: mark_redactions" in said(events)
    # The marks were made (and are one undo step); nothing was permanently removed.
    assert "123-45-6789" in current(client, doc_id)[0].get_text()
    assert store.get(doc_id).version == version + 1


def test_without_a_model_the_chat_says_so(client, doc_id, tmp_path, monkeypatch):
    from app.ai import models
    monkeypatch.setattr(models, "MODELS_DIR", tmp_path)
    events = chat(client, doc_id, "hello")
    assert events[-2] == {"type": "error", "text": "No AI model is downloaded yet"}


def test_confirm_for_a_finished_turn_is_404(client):
    assert client.post("/api/ai/chat/nope/confirm", json={"approve": True}).status_code == 404


# ------------------------------------------------------------------ tools --

def test_pages_are_one_based_for_the_model(client, doc_id):
    ctx = ToolCtx(store, doc_id)
    TOOLS["delete_pages"].run(ctx, pages=[1])
    assert "Chapter 1" not in current(client, doc_id)[0].get_text()
    TOOLS["insert_blank"].run(ctx, at=3)
    doc = current(client, doc_id)
    assert doc.page_count == 3 and doc[2].get_text() == ""


def test_rewrite_paragraph_finds_text_without_coordinates(client, doc_id):
    res = TOOLS["rewrite_paragraph"].run(ToolCtx(store, doc_id), contains="page 2 of the SAMPLE",
                                         new_text="The second page, rewritten.")
    assert res == {"page": 2, "old_text": "This is page 2 of the sample contract."}
    text = current(client, doc_id)[1].get_text()
    assert "The second page, rewritten." in text and "page 2 of the sample" not in text


def test_mark_redactions_uses_built_in_patterns(client, doc_id):
    res = TOOLS["mark_redactions"].run(ToolCtx(store, doc_id), patterns=["ssn"], pages=[2])
    assert res["marked"] == 1
    info = client.get(f"/api/documents/{doc_id}").json()
    assert [a["page"] for a in info["annotations"]] == [1]


def test_every_tool_schema_compiles_to_a_grammar():
    gbnf = pytest.importorskip("llama_cpp.llama_grammar")
    for category in CATEGORIES:
        if category != "question":
            gbnf.json_schema_to_gbnf(json.dumps(agent.step_schema(tools_for(category))))


def test_hidden_parameters_keep_their_op_defaults():
    props = TOOLS["add_watermark"].schema()["properties"]
    assert "blob_id" not in props and TOOLS["add_watermark"].schema()["required"] == ["text"]
    assert props["pages"]["description"].startswith("Page numbers, starting at 1")


def test_other_sites_cannot_drive_the_assistant(client, doc_id):
    evil = {"Origin": "https://example.com"}
    assert client.post("/api/ai/models/lite/download", headers=evil).status_code == 403
    assert client.post("/api/ai/chat", headers=evil, json={"doc_id": doc_id, "message": "hi"}).status_code == 403
    ok = client.post("/api/ai/models/nope/download", headers={"Origin": "http://testserver"})
    assert ok.status_code == 400  # same origin passes the check (and then fails on the bad tier)
    assert client.get("/api/ai/models", headers=evil).status_code == 200


def test_a_new_request_cancels_a_turn_stuck_waiting_for_approval(client, doc_id):
    fake = FakeLLM({"category": "pages"}, {"tool": "delete_pages", "args": {"pages": [1]}})
    stuck = agent.run_turn(lambda: fake, store, doc_id, "delete page 1", [])
    assert [next(stuck)["type"] for _ in range(3)] == ["start", "route", "confirm"]
    retry = list(agent.run_turn(lambda: FakeLLM(), store, doc_id, "again", []))
    assert retry[0]["type"] == "error"
    rest = list(stuck)  # the waiting turn resumes as declined
    assert "didn't make that change" in said(rest)
    assert client.get(f"/api/documents/{doc_id}").json()["page_count"] == 3
