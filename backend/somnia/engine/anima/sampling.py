from __future__ import annotations

import math
from typing import Callable

import numpy as np
import torch

SAMPLERS = ["er_sde", "euler", "euler_a", "dpmpp_2m", "res_multistep"]
SCHEDULERS = ["simple", "normal", "beta", "beta57", "sgm_uniform", "linear_quadratic"]


class FlowSchedule:
    def __init__(self, shift: float = 3.0, timesteps: int = 1000):
        self.shift = shift
        self.sigmas = self.sigma(torch.arange(1, timesteps + 1, dtype=torch.float32) / timesteps)

    def sigma(self, t):
        if self.shift == 1.0:
            return t
        return self.shift * t / (1 + (self.shift - 1) * t)

    @property
    def sigma_min(self):
        return float(self.sigmas[0])

    @property
    def sigma_max(self):
        return float(self.sigmas[-1])

    def percent_to_sigma(self, p: float) -> float:
        if p <= 0:
            return 1.0
        if p >= 1:
            return 0.0
        return float(self.sigma(torch.tensor(1.0 - p)))


def _beta_ppf(q: np.ndarray, a: float, b: float) -> np.ndarray:
    s = np.linspace(0.0, 1.0, 200001)
    x = 0.5 * (1 - np.cos(np.pi * s))
    dx = 0.5 * np.pi * np.sin(np.pi * s)
    with np.errstate(divide="ignore", invalid="ignore"):
        f = np.where((x > 0) & (x < 1), x ** (a - 1) * (1 - x) ** (b - 1) * dx, 0.0)
    cdf = np.concatenate([[0.0], np.cumsum((f[1:] + f[:-1]) * 0.5 * np.diff(s))])
    cdf /= cdf[-1]
    return np.interp(q, cdf, x)


def get_sigmas(sched: FlowSchedule, scheduler: str, steps: int) -> torch.Tensor:
    if scheduler in ("normal", "sgm_uniform"):
        start, end = sched.sigma_max, sched.sigma_min
        if scheduler == "sgm_uniform":
            ts = torch.linspace(start, end, steps + 1)[:-1]
            sigs = [float(sched.sigma(t)) for t in ts] + [0.0]
        else:
            ts = torch.linspace(start, end, steps)
            sigs = [float(sched.sigma(t)) for t in ts] + [0.0]
        return torch.tensor(sigs)
    if scheduler in ("beta", "beta57"):
        a, b = (0.5, 0.7) if scheduler == "beta57" else (0.6, 0.6)
        total = len(sched.sigmas) - 1
        ts = 1 - np.linspace(0, 1, steps, endpoint=False)
        ts = np.rint(_beta_ppf(ts, a, b) * total)
        sigs, last = [], -1
        for t in ts:
            if t != last:
                sigs.append(float(sched.sigmas[int(t)]))
            last = t
        return torch.tensor(sigs + [0.0])
    if scheduler == "linear_quadratic":
        return _linear_quadratic(steps) * sched.sigma_max
    ss = len(sched.sigmas) / steps
    sigs = [float(sched.sigmas[-(1 + int(x * ss))]) for x in range(steps)]
    return torch.tensor(sigs + [0.0])


def _linear_quadratic(steps: int, threshold: float = 0.025) -> torch.Tensor:
    # mochi schedule as in comfy: linear first half, quadratic tail, ignores the shift
    if steps == 1:
        return torch.tensor([1.0, 0.0])
    lin = steps // 2
    quad = steps - lin
    diff = lin - threshold * steps
    qc = diff / (lin * quad**2)
    lc = threshold / lin - 2 * diff / quad**2
    const = qc * lin**2
    sched = [i * threshold / lin for i in range(lin)] + [qc * i**2 + lc * i + const for i in range(lin, steps)] + [1.0]
    return torch.tensor([1.0 - x for x in sched])


def sigmas_for(sched: FlowSchedule, scheduler: str, steps: int, denoise: float) -> torch.Tensor:
    if denoise >= 0.9999:
        return get_sigmas(sched, scheduler, steps)
    if denoise <= 0:
        return torch.tensor([])
    total = int(steps / denoise)
    return get_sigmas(sched, scheduler, total)[-(steps + 1):]


Denoiser = Callable[[torch.Tensor, float, int], torch.Tensor]


def _noise_fn(x: torch.Tensor, seed: int):
    g = torch.Generator(device=x.device)
    g.manual_seed(seed + 1 if x.device.type == "cpu" else seed)
    return lambda: torch.randn(x.shape, dtype=x.dtype, device=x.device, generator=g)


@torch.no_grad()
def sample(name: str, model: Denoiser, x: torch.Tensor, sigmas: torch.Tensor, sched: FlowSchedule, seed: int) -> torch.Tensor:
    sig = [float(s) for s in sigmas]
    n = len(sig) - 1
    if name in ("euler", "euler_flow"):
        for i in range(n):
            d0 = model(x, sig[i], i)
            x = x + (x - d0) / sig[i] * (sig[i + 1] - sig[i])
        return x
    if name in ("euler_a", "euler_ancestral"):
        noise = _noise_fn(x, seed)
        for i in range(n):
            d0 = model(x, sig[i], i)
            if sig[i + 1] == 0:
                x = d0
                continue
            s, sn = sig[i], sig[i + 1]
            sd = sn * (1 + (sn / s - 1))
            a1, ad = 1 - sn, 1 - sd
            renoise = max(sn**2 - sd**2 * a1**2 / ad**2, 0.0) ** 0.5
            r = sd / s
            x = r * x + (1 - r) * d0
            x = (a1 / ad) * x + noise() * renoise
        return x
    if name == "dpmpp_2m":
        def lam(s):
            return math.log((1 - s) / s)

        old = None
        for i in range(n):
            d0 = model(x, sig[i], i)
            s, sn = sig[i], sig[i + 1]
            if sn == 0:
                x = d0
            elif s >= 1:
                x = sn * x + (1 - sn) * d0
            else:
                h = lam(sn) - lam(s)
                dd = d0
                if old is not None and sig[i - 1] < 1:
                    r = (lam(s) - lam(sig[i - 1])) / h
                    dd = (1 + 1 / (2 * r)) * d0 - (1 / (2 * r)) * old
                x = (sn / s) * x - (1 - sn) * math.expm1(-h) * dd
            old = d0
        return x
    if name == "er_sde":
        return _er_sde(model, x, sig, sched, seed)
    if name == "res_multistep":
        return _res_multistep(model, x, sig)
    raise ValueError(f"unknown sampler {name}")


def _res_multistep(model: Denoiser, x, sig):
    old = old_s = None
    for i in range(len(sig) - 1):
        d0 = model(x, sig[i], i)
        s, sn = sig[i], sig[i + 1]
        if sn == 0 or old is None:
            x = x + (x - d0) / s * (sn - s)
        else:
            t, t_old, t_next = -math.log(s), -math.log(old_s), -math.log(sn)
            h = t_next - t
            c2 = (-math.log(sig[i - 1]) - t_old) / h
            phi1 = math.expm1(-h) / -h
            phi2 = (phi1 - 1.0) / -h
            b2 = phi2 / c2 if c2 else 0.0
            x = math.exp(-h) * x + h * ((phi1 - b2) * d0 + b2 * old)
        old, old_s = d0, sn
    return x


def _er_sde(model: Denoiser, x, sig, sched: FlowSchedule, seed: int, max_stage: int = 3):
    noise = _noise_fn(x, seed)

    def scaler(v):
        return v * ((v**0.3).exp() + 10.0)

    sig_t = torch.tensor(sig, dtype=torch.float64)
    if len(sig_t) > 1 and sig_t[0] >= 1:
        sig_t[0] = sched.percent_to_sigma(1e-4)
    lam = sig_t / (1 - sig_t)
    pts = torch.arange(0, 200.0, dtype=torch.float64)
    old = old_d = None
    for i in range(len(sig) - 1):
        d0 = model(x, float(sig_t[i]), i)
        stage = min(max_stage, i + 1)
        if sig[i + 1] == 0:
            x = d0
        else:
            ls, lt = lam[i], lam[i + 1]
            a_s = sig_t[i] / ls
            a_t = sig_t[i + 1] / lt
            r = scaler(lt) / scaler(ls)
            x = float(a_t / a_s * r) * x + float(a_t * (1 - r)) * d0
            if stage >= 2:
                dt = lt - ls
                step = -dt / 200.0
                pos = lt + pts * step
                sp = scaler(pos)
                s = torch.sum(1 / sp) * step
                dd = (d0 - old) / float(ls - lam[i - 1])
                x = x + float(a_t * (dt + s * scaler(lt))) * dd
                if stage >= 3:
                    su = torch.sum((pos - ls) / sp) * step
                    du = (dd - old_d) / float((ls - lam[i - 2]) / 2)
                    x = x + float(a_t * ((dt**2) / 2 + su * scaler(lt))) * du
                old_d = dd
            amp = float(a_t * torch.nan_to_num((lt**2 - ls**2 * r**2).sqrt(), nan=0.0))
            x = x + noise() * amp
        old = d0
    return x
