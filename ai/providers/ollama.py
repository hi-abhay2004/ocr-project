"""
Local Ollama provider — a free, no-API-key fallback for LLM/VLM calls if a
NIM key isn't available. Ollama exposes an OpenAI-compatible endpoint
(`/v1`) as of recent versions, so this reuses the same `openai` client
ai/providers/nim.py does rather than hand-rolling Ollama's native REST shape.

Selected via LLM_PROVIDER=ollama. No embedding class here — sbert.py
(local, no server) is this project's non-NIM embedding fallback instead;
Ollama's embedding-capable models are a much smaller, less reliable set.
"""

import os

from .base import LLMProvider, VLMProvider

DEFAULT_LLM_MODEL = "llama3.1"
DEFAULT_VLM_MODEL = "llama3.2-vision"


REQUEST_TIMEOUT_SECONDS = (
    45  # see ai/providers/nim.py's _client() for why this isn't the SDK default
)


def _client():
    from openai import OpenAI  # local import: keeps `openai` off ai/'s always-import path

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    return OpenAI(
        api_key="ollama", base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=1
    )


class OllamaLLMProvider(LLMProvider):
    """See ai/providers/nim.py's NIMLLMProvider docstring — same reasoning:
    every real call site needs strict JSON back, so `response_format` is
    requested unconditionally rather than made optional."""

    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("OLLAMA_LLM_MODEL", DEFAULT_LLM_MODEL)
        self.call_count = 0

    def chat(self, prompt: str, *, system: str | None = None, json_mode: bool = True) -> str:
        self.call_count += 1
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        response = _client().chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.0,
            **kwargs,
        )
        return response.choices[0].message.content or ""


class OllamaVLMProvider(VLMProvider):
    def __init__(self, model: str | None = None):
        self.model = model or os.environ.get("OLLAMA_VLM_MODEL", DEFAULT_VLM_MODEL)
        self.call_count = 0

    def describe_image(self, image_bytes: bytes, prompt: str) -> str:
        import base64

        self.call_count += 1
        b64 = base64.b64encode(image_bytes).decode()
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
        )
        return response.choices[0].message.content or ""
