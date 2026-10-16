from __future__ import annotations

from pathlib import Path

import torch

TOK_DIR = Path(__file__).resolve().parent / "tokenizers"
QWEN_PAD = 151643


def _parse_parentheses(s: str) -> list[str]:
    out, cur, depth = [], "", 0
    for ch in s:
        if ch == "(":
            if depth == 0:
                if cur:
                    out.append(cur)
                cur = "("
            else:
                cur += ch
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                out.append(cur + ")")
                cur = ""
            else:
                cur += ch
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def token_weights(s: str, w: float) -> list[tuple[str, float]]:
    out = []
    for x in _parse_parentheses(s):
        weight = w
        if len(x) >= 2 and x[0] == "(" and x[-1] == ")":
            x = x[1:-1]
            i = x.rfind(":")
            weight *= 1.1
            if i > 0:
                try:
                    weight = float(x[i + 1 :])
                    x = x[:i]
                except ValueError:
                    pass
            out += token_weights(x, weight)
        else:
            out.append((x, w))
    return out


def _escape(t: str) -> str:
    return t.replace("\\)", "\0\1").replace("\\(", "\0\2")


def _unescape(t: str) -> str:
    return t.replace("\0\1", ")").replace("\0\2", "(")


class AnimaTokenizer:
    def __init__(self):
        from transformers import Qwen2Tokenizer, T5TokenizerFast

        self.qwen = Qwen2Tokenizer.from_pretrained(str(TOK_DIR / "qwen25_tokenizer"))
        self.t5 = T5TokenizerFast.from_pretrained(str(TOK_DIR / "t5_tokenizer"))

    def __call__(self, text: str):
        segs = token_weights(_escape(text), 1.0)
        qids: list[int] = []
        tids: list[int] = []
        tw: list[float] = []
        for seg, w in segs:
            seg = _unescape(seg)
            if not seg:
                continue
            qids += self.qwen(seg)["input_ids"]
            ids = self.t5(seg)["input_ids"][:-1]
            tids += ids
            tw += [w] * len(ids)
        tids.append(1)
        tw.append(1.0)
        if not qids:
            qids = [QWEN_PAD]
        return qids, tids, tw


def qwen3_06b_config():
    from transformers import Qwen3Config

    return Qwen3Config(
        vocab_size=151936,
        hidden_size=1024,
        intermediate_size=3072,
        num_hidden_layers=28,
        num_attention_heads=16,
        num_key_value_heads=8,
        head_dim=128,
        max_position_embeddings=32768,
        rms_norm_eps=1e-6,
        rope_theta=1000000.0,
        rope_parameters={"rope_type": "default", "rope_theta": 1000000.0},
        tie_word_embeddings=True,
        attention_bias=False,
    )


def build_qwen3(sd: dict[str, torch.Tensor], dtype: torch.dtype):
    from transformers import Qwen3Model

    sd = {(k[6:] if k.startswith("model.") else k): v for k, v in sd.items() if not k.startswith("lm_head.")}
    cfg = qwen3_06b_config()
    cfg._attn_implementation = "sdpa"
    with torch.device("meta"):
        m = Qwen3Model(cfg)
    missing, unexpected = m.load_state_dict({k: v.to(dtype) for k, v in sd.items()}, strict=False, assign=True)
    missing = [k for k in missing if "rotary" not in k]
    if missing:
        raise RuntimeError(f"qwen3 text encoder missing keys: {missing[:5]}")
    from transformers.models.qwen3.modeling_qwen3 import Qwen3RotaryEmbedding

    with torch.device("cpu"):
        m.rotary_emb = Qwen3RotaryEmbedding(config=cfg)
    return m.eval().requires_grad_(False)


@torch.no_grad()
def encode_qwen(model, ids: list[int], device) -> torch.Tensor:
    x = torch.tensor([ids], device=device)
    return model(input_ids=x).last_hidden_state
