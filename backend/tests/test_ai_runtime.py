"""The real llama.cpp runtime, on a tiny random-weight model built for the test."""

import json

import pytest

pytest.importorskip("llama_cpp")
pytest.importorskip("gguf")

from app.ai import agent, models  # noqa: E402
from app.ai.runtime import LlamaLLM, Runtime  # noqa: E402
from app.ai.tools import CATEGORIES, tools_for  # noqa: E402
from tiny_gguf import write_tiny_llama  # noqa: E402

pytestmark = pytest.mark.usefixtures("no_network")


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    return write_tiny_llama(tmp_path_factory.mktemp("model") / "tiny.gguf")


@pytest.fixture
def lite_installed(tiny, tmp_path, monkeypatch):
    monkeypatch.setattr(models, "MODELS_DIR", tmp_path)
    for f in models.TIERS["lite"].files:
        f.path.write_bytes(tiny.read_bytes())


def test_runtime_loads_the_active_tier_from_disk(lite_installed):
    rt = Runtime()
    llm = rt.get()
    assert isinstance(llm, LlamaLLM) and llm.tier.id == "lite" and rt.get() is llm
    rt.unload()


def test_grammar_constrains_output_to_the_schema(lite_installed):
    llm = Runtime().get()
    for _ in range(3):
        assert agent.route(llm, "rotate page two", []) in CATEGORIES


def test_embeddings_are_unit_vectors(lite_installed):
    vectors = Runtime().get().embed(["the deposit is due", "rotate the page"])
    assert len(vectors) == 2
    assert all(abs(sum(x * x for x in v) - 1) < 1e-4 for v in vectors)


def test_every_step_grammar_loads_in_llama_cpp():
    from llama_cpp import LlamaGrammar

    for category in CATEGORIES:
        if category != "question":
            LlamaGrammar.from_json_schema(json.dumps(agent.step_schema(tools_for(category))), verbose=False)
