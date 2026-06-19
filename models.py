"""Model client factory for Loomwright.

Two partner backends, one uniform surface (`.complete(prompt) -> str`):

  * Orchestration / reasoning roles (LoopArchitect, LoopRunner) talk to the
    AI/ML API — an OpenAI-compatible gateway at api.aimlapi.com, keyed by
    AIMLAPI_API_KEY.
  * The critics run a *rival* OSS model on Featherless — OpenAI-compatible at
    api.featherless.ai, keyed by FEATHERLESS_API_KEY. Using a different provider
    AND model for the critics is deliberate: the loop's reviewers should not be
    the same brain that wrote the code, or the critique is theater.

When the relevant key is missing, `get_client` returns a deterministic canned
client. The offline `python demo.py` does not depend on any model at all — its
loop control flow is deterministic — so the canned client only needs to return
something harmless for any live-path code that asks for a model and has no key.
"""

from __future__ import annotations

import os
from typing import Optional


AIMLAPI_BASE_URL = "https://api.aimlapi.com/v1"
FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"

AIMLAPI_MODEL = os.getenv("LOOMWRIGHT_AIMLAPI_MODEL", "gpt-4o-mini")
FEATHERLESS_MODEL = os.getenv("LOOMWRIGHT_FEATHERLESS_MODEL", "Qwen/Qwen2.5-72B-Instruct")


def _normalize(role: str) -> str:
    key = (role or "").strip().lower()
    if "critic" in key or "review" in key:
        return "critic"
    if "architect" in key:
        return "architect"
    if "runner" in key or "run" in key:
        return "runner"
    return "architect"


class CannedClient:
    """Offline stand-in. The deterministic demo never relies on this output."""

    def __init__(self, role: str) -> None:
        self.role = role

    def complete(self, prompt: str) -> str:
        return f"[offline:{self.role}] (run with API keys for live model output)"


class OpenAICompatibleClient:
    """Thin `.complete()` wrapper over any OpenAI-compatible chat endpoint."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    def complete(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return (response.choices[0].message.content or "").strip()


def get_client(role: str) -> Optional[CannedClient | OpenAICompatibleClient]:
    normalized = _normalize(role)

    if normalized == "critic":
        key = os.getenv("FEATHERLESS_API_KEY")
        if not key:
            return CannedClient(normalized)
        return OpenAICompatibleClient(FEATHERLESS_BASE_URL, key, FEATHERLESS_MODEL)

    key = os.getenv("AIMLAPI_API_KEY")
    if not key:
        return CannedClient(normalized)
    return OpenAICompatibleClient(AIMLAPI_BASE_URL, key, AIMLAPI_MODEL)
