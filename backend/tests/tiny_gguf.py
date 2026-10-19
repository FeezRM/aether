"""Write a tiny random-weight llama GGUF, to exercise the real llama.cpp path without model files.

Its output is gibberish, but grammar-constrained output must still be valid JSON,
and embeddings must come back as one unit vector per text.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

CHAT_TEMPLATE = ("{% for m in messages %}<|{{ m['role'] }}|>{{ m['content'] }}\n{% endfor %}"
                 "{% if add_generation_prompt %}<|assistant|>{% endif %}")


def write_tiny_llama(path: Path, n_embd: int = 32, n_ff: int = 64, n_head: int = 2) -> Path:
    import gguf

    tokens = ["<unk>", "<s>", "</s>"] + [f"<0x{b:02X}>" for b in range(256)]
    types = [gguf.TokenType.UNKNOWN, gguf.TokenType.CONTROL, gguf.TokenType.CONTROL] \
        + [gguf.TokenType.BYTE] * 256
    printable = [chr(c) for c in range(32, 127)] + ["▁"]
    tokens += printable
    types += [gguf.TokenType.NORMAL] * len(printable)
    vocab = len(tokens)

    w = gguf.GGUFWriter(str(path), "llama")
    w.add_name("tiny-test")
    w.add_context_length(1024)
    w.add_embedding_length(n_embd)
    w.add_block_count(1)
    w.add_feed_forward_length(n_ff)
    w.add_head_count(n_head)
    w.add_head_count_kv(n_head)
    w.add_rope_dimension_count(n_embd // n_head)
    w.add_layer_norm_rms_eps(1e-5)
    w.add_file_type(gguf.LlamaFileType.ALL_F32)
    w.add_pooling_type(gguf.PoolingType.MEAN)
    w.add_tokenizer_model("llama")
    w.add_tokenizer_pre("default")
    w.add_token_list(tokens)
    w.add_token_scores([0.0] * vocab)
    w.add_token_types(types)
    w.add_bos_token_id(1)
    w.add_eos_token_id(2)
    w.add_unk_token_id(0)
    w.add_chat_template(CHAT_TEMPLATE)

    rng = np.random.default_rng(0)

    def t(name, *shape):
        w.add_tensor(name, (rng.standard_normal(shape) * 0.02).astype(np.float32))

    t("token_embd.weight", vocab, n_embd)
    w.add_tensor("blk.0.attn_norm.weight", np.ones(n_embd, dtype=np.float32))
    for name in ("attn_q", "attn_k", "attn_v", "attn_output"):
        t(f"blk.0.{name}.weight", n_embd, n_embd)
    w.add_tensor("blk.0.ffn_norm.weight", np.ones(n_embd, dtype=np.float32))
    t("blk.0.ffn_gate.weight", n_ff, n_embd)
    t("blk.0.ffn_up.weight", n_ff, n_embd)
    t("blk.0.ffn_down.weight", n_embd, n_ff)
    w.add_tensor("output_norm.weight", np.ones(n_embd, dtype=np.float32))
    t("output.weight", vocab, n_embd)

    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()
    return path
