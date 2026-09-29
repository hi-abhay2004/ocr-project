"""
NVIDIA NIM provider — OpenAI-compatible endpoint (https://build.nvidia.com).

Real network calls. Selected via LLM_PROVIDER=nim; needs NIM_API_KEY set
(.env / .env.example). `ai/` has no Django imports, so config is read
straight from os.environ, same as ai/providers/factory.py.

Every test that exercises this module is marked `slow` (pyproject.toml's
`addopts = "-m 'not slow'"` deselects it by default) and skips itself if
NIM_API_KEY isn't set. config/settings/test.py also hard-forces
LLM_PROVIDER=mock regardless, so `pytest` never touches the network even if
a stray .env sets LLM_PROVIDER=nim.
"""

import base64
import os
import threading
import time
from collections import deque

from .base import EmbeddingProvider, LLMProvider, VLMProvider

# nv-embedqa-e5-v5 was 1024-dim, matching ai.config.EMBEDDING_DIM — until
# NVIDIA retired it (confirmed 2026-08-26: real calls started returning
# HTTP 410 Gone, "reached its end of life on 2026-08-25T09:00:00Z"). Of the
# embedding models NIM's /v1/models catalogue lists, most 404 on this
# account's actual (free-tier) entitlements despite being listed — verified
# by calling each one directly, not just checking the catalogue — leaving
# nemotron-3-embed-1b as the one that actually worked that day. It's
# 2048-dim, not 1024, which is why EMBEDDING_DIM changed to 2048 (see
# ai/config.py and apps/exams/migrations/0002-0003) — that migration
# stands regardless of which specific 2048-dim model ends up here.
#
# nemotron-3-embed-1b itself then started failing the very next day
# (2026-08-27: real calls returned HTTP 400 "DEGRADED function cannot be
# invoked", and a follow-up direct check got a plain client-side timeout
# instead — consistent across 3 retries a few seconds apart, so a real
# NIM-side outage for that specific model, not a one-off blip).
# llama-nemotron-embed-vl-1b-v2 is the replacement verified working right
# after (also 2048-dim — no second migration needed). Given two embedding
# models have now failed within 24 hours of each other, treat NIM's
# free-tier hosted models as inherently short-lived: if this one also
# starts erroring, re-run the same check (call every /v1/models entry
# whose id contains "embed" directly, since most 404 despite being
# listed) rather than assuming the account or the code is at fault.
#
# meta/llama-3.1-8b-instruct (chosen 2026-08-17 for being 14x faster than
# the 70b variant at equivalent quality on this project's short structured
# tasks) was retired by NVIDIA on 2026-08-26 (HTTP 410 Gone at its exact
# end-of-life timestamp, 09:00:00Z that day) — same day as nv-embedqa-e5-v5
# above. By that point NIM's catalogue had dropped every plain meta/llama-3.*
# text model entirely, and of the remaining candidates, most still 404 on
# this account's free-tier entitlements (verified by calling each
# directly). nemotron-3-nano-30b-a3b is the one that actually works, and is
# fast (sub-5s on every real prompt shape this project sends). One real
# quirk: with response_format={"type":"json_object"} forced on, it returns
# a trivially-valid-but-EMPTY `{"concepts": []}` for ai/concepts.py's
# open-ended list-extraction prompt specifically — coverage/feedback's
# fixed-shape JSON objects are unaffected. See LLMProvider.chat's
# `json_mode` param (ai/providers/base.py): ai/concepts.py passes
# json_mode=False for exactly this reason. Override with NIM_LLM_MODEL in
# .env if NVIDIA's hosting changes again.
DEFAULT_LLM_MODEL = "nvidia/nemotron-3-super-120b-a12b"
# The 90b vision variant is listed in NIM's catalogue but was verified
# (2026-08-17) to hang indefinitely on every request — not a model-name typo,
# an availability/capacity problem with that specific hosted model. The 11b
# variant is confirmed working (fast, correct replies against real test
# images). Override with NIM_VLM_MODEL in .env if NVIDIA's hosting changes.
DEFAULT_VLM_MODEL = "meta/llama-3.2-11b-vision-instruct"
DEFAULT_EMBED_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2"


# The openai SDK's own default (10 minutes) is far too long for a call
# sitting inside a Celery task — CELERY_TASK_SOFT_TIME_LIMIT (120s,
# config/settings/base.py) is the real backstop for the whole task, but a
# single hung HTTP call eating that entire budget still means every other
# question on the sheet never gets a chance to run before the hard limit
# kills the task outright. An explicit, much shorter client-level timeout
# turns "NIM is unreachable/overloaded" into a fast, readable failure
# instead of a slow one.
REQUEST_TIMEOUT_SECONDS = 45


# A hung request needs a short client-level timeout (above) so it fails fast
# instead of eating the whole Celery task budget — but a 429 needs the
# opposite: several retries, since ai.pipeline fires up to
# MAX_CONCURRENT_CONCEPTS * COVERAGE_PASS_COUNT requests at once and NIM's
# per-minute rate limit can reject some of that burst outright. The openai
# SDK already retries 429s with backoff honoring the server's `Retry-After`
# header — kept as a safety net, but it's not the primary fix: retries alone
# let independent threads collide into 429s again after backing off, since
# they don't coordinate with each other. NIM_RATE_LIMITER below is the
# primary fix — it paces requests so the account's real quota is never
# exceeded in the first place, making 429s rare instead of routine.
RATE_LIMIT_MAX_RETRIES = 8

# NIM's free-tier quota for this account is 40 requests/minute (confirmed on
# NVIDIA's dashboard, 2026-08-18). Every real call site
# (concepts/coverage/feedback, all triple-pass-voted and run concurrently up
# to MAX_CONCURRENT_CONCEPTS at once — ai/pipeline.py) shares this one
# limiter, since they all draw from the same account quota regardless of
# which Python thread or provider class makes the call. 36, not 40: a small
# safety margin, since NIM's rate-limit window boundary doesn't necessarily
# line up with ours to the millisecond, and a request that's one over the
# line is a slow, wasteful retry instead of a request that never needed to
# be reactively backed off. Override with NIM_RATE_LIMIT_PER_MINUTE in .env
# if your account's quota differs (e.g. a paid tier).
NIM_RATE_LIMIT_PER_MINUTE = int(os.environ.get("NIM_RATE_LIMIT_PER_MINUTE", "20"))


class _SlidingWindowRateLimiter:
    """Blocks callers so no more than `max_per_minute` calls to `acquire()`
    return within any trailing 60-second window, across all threads in this
    process. A token-bucket-style limiter, not per-thread throttling — every
    NIM call in this worker process shares one instance (`NIM_RATE_LIMITER`
    below), because the quota it's protecting is per-account, not per-thread.

    Per-process, not distributed: correct for this project's real usage (one
    Celery worker evaluating one sheet at a time), not multiple worker
    processes hammering NIM's account-wide quota concurrently — that would
    need a shared store (e.g. Redis) instead of an in-memory deque, which
    would be solving a problem this project doesn't have.
    """

    def __init__(self, max_per_minute: int, *, window_seconds: float = 60.0):
        self._max = max_per_minute
        self._window_seconds = window_seconds
        self._call_times: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._call_times and now - self._call_times[0] >= self._window_seconds:
                    self._call_times.popleft()
                if len(self._call_times) < self._max:
                    self._call_times.append(now)
                    return
                wait_seconds = self._window_seconds - (now - self._call_times[0])
            time.sleep(max(wait_seconds, 0.05))


NIM_RATE_LIMITER = _SlidingWindowRateLimiter(NIM_RATE_LIMIT_PER_MINUTE)


def _client():
    from openai import OpenAI  # local import: keeps `openai` off ai/'s always-import path

    api_key = os.environ.get("NIM_API_KEY", "")
    if not api_key:
        raise RuntimeError("NIM_API_KEY is not set — set it in .env or select LLM_PROVIDER=mock")
    base_url = os.environ.get("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=RATE_LIMIT_MAX_RETRIES,
    )


class NIMLLMProvider(LLMProvider):
    """Every real call site in this project (ai/concepts.py, ai/coverage.py,
    ai/feedback.py) goes through ai.providers.retry.call_json, which needs
    strict JSON back — so `response_format` is requested unconditionally
    here, not made optional. Verified (2026-08-17) this is what actually
    matters for latency: without it, the model would often preface its
    JSON with a sentence of prose or wrap it in a markdown fence, failing
    the parser and forcing a repair round-trip — one real call went from
    2.9s (JSON mode) to 78s (three full round-trips without it)."""

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("NIM_LLM_MODEL", DEFAULT_LLM_MODEL)
        self.call_count = 0

    def chat(self, prompt: str, *, system: str | None = None, json_mode: bool = True) -> str:
        self.call_count += 1
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        NIM_RATE_LIMITER.acquire()
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        response = _client().chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.0,
            max_tokens=1024,  # Concept extraction and feedback need up to ~800 tokens
            **kwargs,
        )
        return response.choices[0].message.content or ""


class NIMVLMProvider(VLMProvider):
    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("NIM_VLM_MODEL", DEFAULT_VLM_MODEL)
        self.call_count = 0

    def describe_image(self, image_bytes: bytes, prompt: str) -> str:
        self.call_count += 1
        b64 = base64.b64encode(image_bytes).decode()
        NIM_RATE_LIMITER.acquire()
        response = _client().chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
            temperature=0.0,
            max_tokens=1024,
        )
        return response.choices[0].message.content or ""


class NIMEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("NIM_EMBED_MODEL", DEFAULT_EMBED_MODEL)
        self.call_count = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        NIM_RATE_LIMITER.acquire()
        response = _client().embeddings.create(
            model=self.model,
            input=texts,
            extra_body={"input_type": "query", "truncate": "END"},
        )
        return [item.embedding for item in response.data]
