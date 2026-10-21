from __future__ import annotations

import math

import torch
import torch.nn.functional as F
from torch import nn

from ..stepcache import StepCache


def _fma(base: torch.Tensor, a: torch.Tensor, b: torch.Tensor, dtype: torch.dtype) -> torch.Tensor:
    # base + a * b in fp32 opmath, stored as dtype. cuda does it in one mixed dtype pass,
    # other backends get plain same dtype ops
    if base.device.type == "cuda":
        shape = torch.broadcast_shapes(base.shape, a.shape, b.shape)
        return torch.addcmul(base, a, b, out=torch.empty(shape, dtype=dtype, device=base.device))
    return (base.float() + a.float() * b.float()).to(dtype)


def _residual(x: torch.Tensor, g: torch.Tensor, r: torch.Tensor) -> torch.Tensor:
    if x.device.type == "cuda":
        return x.addcmul_(g.to(x.dtype), r)
    return x.add_(g.to(x.dtype) * r.to(x.dtype))


def _rope_apply(t: torch.Tensor, rope: tuple[torch.Tensor, torch.Tensor]) -> torch.Tensor:
    # rotate half form of comfy's 2x2 rotation, same fp32 math in a third of the memory passes
    cos, sin = rope
    half = t.shape[-1] // 2
    return _fma(t * cos, torch.cat([t[..., half:], t[..., :half]], dim=-1), sin, t.dtype)


class Attention(nn.Module):
    def __init__(self, dim: int, context_dim: int | None, heads: int, head_dim: int):
        super().__init__()
        self.is_self = context_dim is None
        context_dim = dim if context_dim is None else context_dim
        inner = heads * head_dim
        self.heads = heads
        self.head_dim = head_dim
        self.q_proj = nn.Linear(dim, inner, bias=False)
        self.q_norm = nn.RMSNorm(head_dim, eps=1e-6)
        self.k_proj = nn.Linear(context_dim, inner, bias=False)
        self.k_norm = nn.RMSNorm(head_dim, eps=1e-6)
        self.v_proj = nn.Linear(context_dim, inner, bias=False)
        self.output_proj = nn.Linear(inner, dim, bias=False)

    def forward(self, x, context=None, rope=None):
        ctx = x if context is None else context
        b = x.shape[0]
        q = self.q_norm(self.q_proj(x).view(b, -1, self.heads, self.head_dim))
        k = self.k_norm(self.k_proj(ctx).view(b, -1, self.heads, self.head_dim))
        v = self.v_proj(ctx).view(b, -1, self.heads, self.head_dim)
        if self.is_self and rope is not None:
            q = _rope_apply(q, rope)
            k = _rope_apply(k, rope)
        o = F.scaled_dot_product_attention(q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2))
        return self.output_proj(o.transpose(1, 2).reshape(b, -1, self.heads * self.head_dim))


class FeedForward(nn.Module):
    def __init__(self, dim: int, hidden: int):
        super().__init__()
        self.layer1 = nn.Linear(dim, hidden, bias=False)
        self.layer2 = nn.Linear(hidden, dim, bias=False)

    def forward(self, x):
        return self.layer2(F.gelu(self.layer1(x)))


def _adaln(dim: int, lora_dim: int, chunks: int) -> nn.Sequential:
    return nn.Sequential(nn.SiLU(), nn.Linear(dim, lora_dim, bias=False), nn.Linear(lora_dim, chunks * dim, bias=False))


class Block(nn.Module):
    def __init__(self, dim: int, context_dim: int, heads: int, mlp_ratio: float = 4.0, lora_dim: int = 256):
        super().__init__()
        self.layer_norm_self_attn = nn.LayerNorm(dim, elementwise_affine=False, eps=1e-6)
        self.self_attn = Attention(dim, None, heads, dim // heads)
        self.layer_norm_cross_attn = nn.LayerNorm(dim, elementwise_affine=False, eps=1e-6)
        self.cross_attn = Attention(dim, context_dim, heads, dim // heads)
        self.layer_norm_mlp = nn.LayerNorm(dim, elementwise_affine=False, eps=1e-6)
        self.mlp = FeedForward(dim, int(dim * mlp_ratio))
        self.adaln_modulation_self_attn = _adaln(dim, lora_dim, 3)
        self.adaln_modulation_cross_attn = _adaln(dim, lora_dim, 3)
        self.adaln_modulation_mlp = _adaln(dim, lora_dim, 3)

    def forward(self, x, emb, context, rope, adaln_lora):
        cdt = emb.dtype
        b, t, h, w, d = x.shape

        def mod(m):
            return [c[:, :, None, None, :] for c in (m(emb) + adaln_lora).chunk(3, dim=-1)]

        def norm(ln, sh, sc):
            # ln(x) * (1 + sc) + sh written straight into the compute dtype
            return _fma(sh, ln(x), 1 + sc, cdt)

        # the residual stream is owned by this forward, so it is updated in place
        sh, sc, g = mod(self.adaln_modulation_self_attn)
        r = self.self_attn(norm(self.layer_norm_self_attn, sh, sc).view(b, -1, d), None, rope).view(b, t, h, w, d)
        _residual(x, g, r)

        sh, sc, g = mod(self.adaln_modulation_cross_attn)
        r = self.cross_attn(norm(self.layer_norm_cross_attn, sh, sc).view(b, -1, d), context).view(b, t, h, w, d)
        _residual(x, g, r)

        sh, sc, g = mod(self.adaln_modulation_mlp)
        r = self.mlp(norm(self.layer_norm_mlp, sh, sc))
        return _residual(x, g, r)


class FinalLayer(nn.Module):
    def __init__(self, dim: int, patch: int, t_patch: int, out_ch: int, lora_dim: int = 256):
        super().__init__()
        self.dim = dim
        self.layer_norm = nn.LayerNorm(dim, elementwise_affine=False, eps=1e-6)
        self.linear = nn.Linear(dim, patch * patch * t_patch * out_ch, bias=False)
        self.adaln_modulation = _adaln(dim, lora_dim, 2)

    def forward(self, x, emb, adaln_lora):
        sh, sc = (self.adaln_modulation(emb) + adaln_lora[:, :, : 2 * self.dim]).chunk(2, dim=-1)
        x = self.layer_norm(x) * (1 + sc[:, :, None, None, :]) + sh[:, :, None, None, :]
        return self.linear(x)


class TimestepEmbedding(nn.Module):
    def __init__(self, dim: int):
        super().__init__()
        self.linear_1 = nn.Linear(dim, dim, bias=False)
        self.linear_2 = nn.Linear(dim, 3 * dim, bias=False)

    def forward(self, s):
        return s, self.linear_2(F.silu(self.linear_1(s)))


class Timesteps(nn.Module):
    def __init__(self, dim: int):
        super().__init__()
        self.dim = dim

    def forward(self, ts):
        b, t = ts.shape
        half = self.dim // 2
        ex = torch.exp(-math.log(10000) * torch.arange(half, dtype=torch.float32, device=ts.device) / half)
        e = ts.flatten().float()[:, None] * ex[None]
        return torch.cat([torch.cos(e), torch.sin(e)], dim=-1).view(b, t, -1)


class Rope3D(nn.Module):
    def __init__(self, head_dim: int, h_ratio: float = 4.0, w_ratio: float = 4.0, t_ratio: float = 1.0):
        super().__init__()
        dim_h = head_dim // 6 * 2
        dim_t = head_dim - 2 * dim_h
        self.dim_h = dim_h
        self.dim_t = dim_t
        self.h_ntk = h_ratio ** (dim_h / (dim_h - 2))
        self.w_ntk = w_ratio ** (dim_h / (dim_h - 2))
        self.t_ntk = t_ratio ** (dim_t / (dim_t - 2))

    def forward(self, T: int, H: int, W: int, device) -> tuple[torch.Tensor, torch.Tensor]:
        sr = torch.arange(0, self.dim_h, 2, device=device)[: self.dim_h // 2].float() / self.dim_h
        tr = torch.arange(0, self.dim_t, 2, device=device)[: self.dim_t // 2].float() / self.dim_t
        hf = 1.0 / ((10000.0 * self.h_ntk) ** sr)
        wf = 1.0 / ((10000.0 * self.w_ntk) ** sr)
        tf = 1.0 / ((10000.0 * self.t_ntk) ** tr)
        seq = torch.arange(max(H, W, T), dtype=torch.float, device=device)

        def rot(e):
            return torch.stack([torch.cos(e), -torch.sin(e), torch.sin(e), torch.cos(e)], dim=-1)

        eh = rot(torch.outer(seq[:H], hf))
        ew = rot(torch.outer(seq[:W], wf))
        et = rot(torch.outer(seq[:T], tf))
        em = torch.cat(
            [
                et[:, None, None].expand(T, H, W, *et.shape[1:]),
                eh[None, :, None].expand(T, H, W, *eh.shape[1:]),
                ew[None, None, :].expand(T, H, W, *ew.shape[1:]),
            ],
            dim=-2,
        )
        em = em.reshape(T * H * W, em.shape[-2], 2, 2).float()
        cos, sin = em[..., 0, 0], em[..., 1, 0]
        return torch.cat([cos, cos], -1), torch.cat([-sin, sin], -1)


class PatchEmbed(nn.Module):
    def __init__(self, patch: int, t_patch: int, in_ch: int, dim: int):
        super().__init__()
        self.patch = patch
        self.t_patch = t_patch
        self.proj = nn.Sequential(nn.Identity(), nn.Linear(in_ch * patch * patch * t_patch, dim, bias=False))

    def forward(self, x):
        b, c, t, h, w = x.shape
        p, r = self.patch, self.t_patch
        x = x.view(b, c, t // r, r, h // p, p, w // p, p).permute(0, 2, 4, 6, 1, 3, 5, 7)
        return self.proj(x.reshape(b, t // r, h // p, w // p, c * r * p * p))


class LLMAdapterRotary(nn.Module):
    def __init__(self, head_dim: int):
        super().__init__()
        self.head_dim = head_dim

    def forward(self, n: int, device, dtype):
        inv = 1.0 / (10000 ** (torch.arange(0, self.head_dim, 2, device=device).float() / self.head_dim))
        pos = torch.arange(n, device=device, dtype=torch.float32)
        f = torch.outer(pos, inv)
        emb = torch.cat((f, f), dim=-1)
        return emb.cos()[None].to(dtype), emb.sin()[None].to(dtype)


def _rot_half(x):
    a, b = x.chunk(2, dim=-1)
    return torch.cat((-b, a), dim=-1)


class AdapterAttention(nn.Module):
    def __init__(self, dim: int, context_dim: int, heads: int, head_dim: int):
        super().__init__()
        inner = heads * head_dim
        self.heads = heads
        self.head_dim = head_dim
        self.q_proj = nn.Linear(dim, inner, bias=False)
        self.q_norm = nn.RMSNorm(head_dim, eps=1e-6)
        self.k_proj = nn.Linear(context_dim, inner, bias=False)
        self.k_norm = nn.RMSNorm(head_dim, eps=1e-6)
        self.v_proj = nn.Linear(context_dim, inner, bias=False)
        self.o_proj = nn.Linear(inner, dim, bias=False)

    def forward(self, x, context, pe_q, pe_k):
        b = x.shape[0]
        q = self.q_norm(self.q_proj(x).view(b, -1, self.heads, self.head_dim)).transpose(1, 2)
        k = self.k_norm(self.k_proj(context).view(b, -1, self.heads, self.head_dim)).transpose(1, 2)
        v = self.v_proj(context).view(b, -1, self.heads, self.head_dim).transpose(1, 2)
        cos, sin = pe_q
        q = q * cos[:, None] + _rot_half(q) * sin[:, None]
        cos, sin = pe_k
        k = k * cos[:, None] + _rot_half(k) * sin[:, None]
        o = F.scaled_dot_product_attention(q, k, v)
        return self.o_proj(o.transpose(1, 2).reshape(b, -1, self.heads * self.head_dim))


class AdapterBlock(nn.Module):
    def __init__(self, source_dim: int, dim: int, heads: int, mlp_ratio: float = 4.0):
        super().__init__()
        self.norm_self_attn = nn.RMSNorm(dim, eps=1e-6)
        self.self_attn = AdapterAttention(dim, dim, heads, dim // heads)
        self.norm_cross_attn = nn.RMSNorm(dim, eps=1e-6)
        self.cross_attn = AdapterAttention(dim, source_dim, heads, dim // heads)
        self.norm_mlp = nn.RMSNorm(dim, eps=1e-6)
        self.mlp = nn.Sequential(nn.Linear(dim, int(dim * mlp_ratio)), nn.GELU(), nn.Linear(int(dim * mlp_ratio), dim))

    def forward(self, x, context, pe, pe_ctx):
        n = self.norm_self_attn(x)
        x = x + self.self_attn(n, n, pe, pe)
        x = x + self.cross_attn(self.norm_cross_attn(x), context, pe, pe_ctx)
        return x + self.mlp(self.norm_mlp(x))


class LLMAdapter(nn.Module):
    def __init__(self, source_dim=1024, target_dim=1024, num_layers=6, heads=16):
        super().__init__()
        self.embed = nn.Embedding(32128, target_dim)
        self.rotary_emb = LLMAdapterRotary(target_dim // heads)
        self.blocks = nn.ModuleList([AdapterBlock(source_dim, target_dim, heads) for _ in range(num_layers)])
        self.out_proj = nn.Linear(target_dim, target_dim)
        self.norm = nn.RMSNorm(target_dim, eps=1e-6)

    def forward(self, hidden, ids):
        x = self.embed(ids).to(hidden.dtype)
        pe = self.rotary_emb(x.shape[1], x.device, x.dtype)
        pe_ctx = self.rotary_emb(hidden.shape[1], x.device, x.dtype)
        for blk in self.blocks:
            x = blk(x, hidden, pe, pe_ctx)
        return self.norm(self.out_proj(x))


class AnimaDiT(nn.Module):
    def __init__(self, in_channels=16, out_channels=16, model_channels=2048, num_blocks=28, num_heads=16, patch=2, t_patch=1, context_dim=1024, rope_ratio=(4.0, 4.0, 1.0)):
        super().__init__()
        self.patch = patch
        self.t_patch = t_patch
        self.out_channels = out_channels
        self.pos_embedder = Rope3D(model_channels // num_heads, *rope_ratio)
        self.t_embedder = nn.Sequential(Timesteps(model_channels), TimestepEmbedding(model_channels))
        self.x_embedder = PatchEmbed(patch, t_patch, in_channels + 1, model_channels)
        self.blocks = nn.ModuleList([Block(model_channels, context_dim, num_heads) for _ in range(num_blocks)])
        self.final_layer = FinalLayer(model_channels, patch, t_patch, out_channels)
        self.t_embedding_norm = nn.RMSNorm(model_channels, eps=1e-6)
        self.llm_adapter = LLMAdapter()
        self._rope: dict[tuple, tuple[torch.Tensor, torch.Tensor]] = {}
        self.cache: StepCache | None = None
        self.cache_rest: torch.Tensor | None = None

    def encode_text(self, hidden: torch.Tensor, t5_ids: torch.Tensor, t5_weights: torch.Tensor | None = None, min_len: int = 512):
        out = self.llm_adapter(hidden, t5_ids)
        if t5_weights is not None:
            out = out * t5_weights[..., None].to(out)
        if out.shape[1] < min_len:
            out = F.pad(out, (0, 0, 0, min_len - out.shape[1]))
        return out

    def forward(self, x: torch.Tensor, timesteps: torch.Tensor, context: torch.Tensor) -> torch.Tensor:
        b, c, T, H, W = x.shape
        ph, pw = (-H) % self.patch, (-W) % self.patch
        if ph or pw:
            x = F.pad(x.reshape(b, c * T, H, W), (0, pw, 0, ph), mode="circular").reshape(b, c, T, H + ph, W + pw)
        pad_mask = torch.zeros(b, 1, *x.shape[2:], dtype=x.dtype, device=x.device)
        h = self.x_embedder(torch.cat([x, pad_mask], dim=1))
        _, t, hh, ww, d = h.shape
        key = (t, hh, ww, x.device)
        rope = self._rope.get(key)
        if rope is None:
            self._rope.clear()
            rope = self._rope[key] = tuple(f[None, :, None] for f in self.pos_embedder(t, hh, ww, x.device))
        if timesteps.ndim == 1:
            timesteps = timesteps[:, None]
        emb, adaln_lora = self.t_embedder[1](self.t_embedder[0](timesteps).to(h.dtype))
        emb = self.t_embedding_norm(emb)
        if h.dtype == torch.float16:
            h = h.float()
        sc = self.cache
        if sc is None:
            for blk in self.blocks:
                h = blk(h, emb, context, rope, adaln_lora)
        else:
            inp = h.clone()
            h = self.blocks[0](h, emb, context, rope, adaln_lora)
            first = h - inp
            del inp
            if sc.check(first):
                h += self.cache_rest
            else:
                start = h.clone()
                for blk in self.blocks[1:]:
                    h = blk(h, emb, context, rope, adaln_lora)
                self.cache_rest = h - start
        out = self.final_layer(h.to(context.dtype), emb, adaln_lora)
        p, r = self.patch, self.t_patch
        out = out.view(b, t, hh, ww, p, p, r, self.out_channels).permute(0, 7, 1, 6, 2, 4, 3, 5)
        out = out.reshape(b, self.out_channels, t * r, hh * p, ww * p)
        return out[:, :, :T, :H, :W]
