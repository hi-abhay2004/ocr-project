import logging
import os
import time
import threading
from collections import deque
from typing import Any
import google.genai.errors
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests

from ai.config import EMBEDDING_DIM

from .base import EmbeddingProvider, LLMProvider, VLMProvider

logger = logging.getLogger(__name__)


class _TransientEmbedError(RuntimeError):
    """Raised only for retry-worthy failures (rate limit / server error) so
    `embed()`'s retry decorator doesn't burn 8 exponential-backoff attempts
    (worst case ~4 minutes) on a permanent failure like a missing/invalid
    API key or a malformed request — those should fail on the first try."""

class _SlidingWindowRateLimiter:
    def __init__(self, max_per_minute: int, *, window_seconds: float = 60.0):
        self._max = max_per_minute
        self._window_seconds = window_seconds
        self._call_times = deque()
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

GEMINI_RATE_LIMITER = _SlidingWindowRateLimiter(14)

DEFAULT_LLM_MODEL = "gemini-flash-lite-latest"
DEFAULT_VLM_MODEL = "gemini-flash-lite-latest"
DEFAULT_EMBED_MODEL = "gemini-embedding-2"

def _client():
    from google import genai
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set — set it in .env")
    return genai.Client(api_key=api_key)


class GeminiLLMProvider(LLMProvider):
    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("GEMINI_LLM_MODEL", DEFAULT_LLM_MODEL)
        self.call_count = 0

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=1, min=2, max=60), retry=retry_if_exception_type(google.genai.errors.APIError))
    def chat(self, prompt: str, system: str | None = None, json_mode: bool = False) -> str:
        self.call_count += 1
        GEMINI_RATE_LIMITER.acquire()
        client = _client()
        from google.genai import types
        
        config_kwargs = {"temperature": 0.0, "system_instruction": system} if system else {"temperature": 0.0}
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"
            
        config = types.GenerateContentConfig(**config_kwargs)
        
        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return response.text or ""


class GeminiVLMProvider(VLMProvider):
    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("GEMINI_VLM_MODEL", DEFAULT_VLM_MODEL)
        self.call_count = 0

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=1, min=2, max=60), retry=retry_if_exception_type(google.genai.errors.APIError))
    def describe_image(self, image_bytes: bytes, prompt: str) -> str:
        self.call_count += 1
        GEMINI_RATE_LIMITER.acquire()
        client = _client()
        from google.genai import types
        
        response = client.models.generate_content(
            model=self.model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            )
        )
        return response.text or ""


class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("GEMINI_EMBED_MODEL", DEFAULT_EMBED_MODEL)
        self.call_count = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1

        # Fails immediately, outside the retry — a missing key never
        # becomes valid between attempt 1 and attempt 8.
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set — set it in .env")

        return self._embed_with_retry(texts, api_key)

    @retry(
        stop=stop_after_attempt(8),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type(_TransientEmbedError),
    )
    def _embed_with_retry(self, texts: list[str], api_key: str) -> list[list[float]]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:batchEmbedContents?key={api_key}"

        embeddings = []
        for i in range(0, len(texts), 100):
            batch_texts = texts[i:i+100]
            GEMINI_RATE_LIMITER.acquire()
            payload = {
                "requests": [
                    {
                        "model": f"models/{self.model}",
                        "content": {"parts": [{"text": text}]},
                        # Ask Gemini to return exactly EMBEDDING_DIM floats
                        # instead of truncating/padding whatever size it
                        # feels like sending back — pgvector's column and
                        # every stored embedding are fixed at this width,
                        # and silently reshaping a mismatched vector after
                        # the fact corrupts cosine similarity without ever
                        # raising an error.
                        "outputDimensionality": EMBEDDING_DIM,
                    }
                    for text in batch_texts
                ]
            }
            try:
                res = requests.post(url, json=payload, timeout=30)
            except (requests.ConnectionError, requests.Timeout) as exc:
                raise _TransientEmbedError(f"Batch embed request failed: {exc}") from exc

            if res.status_code == 429 or res.status_code >= 500:
                raise _TransientEmbedError(f"Batch embed failed ({res.status_code}): {res.text}")
            if res.status_code != 200:
                # A 4xx other than 429 (bad request, invalid key, quota
                # denied, ...) will not fix itself on retry.
                raise RuntimeError(f"Batch embed failed ({res.status_code}): {res.text}")

            data = res.json()
            for item in data.get("embeddings", []):
                emb = item["values"]
                if len(emb) != EMBEDDING_DIM:
                    logger.warning(
                        "Gemini returned a %d-dim embedding, expected %d — reshaping.",
                        len(emb),
                        EMBEDDING_DIM,
                    )
                    if len(emb) > EMBEDDING_DIM:
                        emb = emb[:EMBEDDING_DIM]
                    else:
                        emb = emb + [0.0] * (EMBEDDING_DIM - len(emb))
                embeddings.append(emb)
        return embeddings
