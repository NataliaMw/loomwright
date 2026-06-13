"""Model client factory for the Rollback Room.

Two partner backends, one uniform surface (`.complete(prompt) -> str`):

  * Orchestration / general reasoning roles (Triage, RootCause, FixAuthor) talk
    to the AI/ML API — an OpenAI-compatible gateway at api.aimlapi.com, keyed by
    AIMLAPI_API_KEY.
  * The lone adversarial Reviewer runs a *rival* OSS model on Featherless —
    OpenAI-compatible at api.featherless.ai, keyed by FEATHERLESS_API_KEY. Using
    a different provider AND a different model is the whole point: author and
    reviewer must not be the same brain arguing with itself.

When the relevant key is missing, `get_client` returns a deterministic canned
client whose `.complete(prompt)` replays fixture text keyed by role. That keeps
`python demo.py` fully offline and byte-for-byte reproducible on video.
"""

from __future__ import annotations

import os
from typing import Optional

from fixtures import canned_model_output


AIMLAPI_BASE_URL = "https://api.aimlapi.com/v1"
FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"

AIMLAPI_MODEL = os.getenv("ROLLBACK_AIMLAPI_MODEL", "gpt-4o-mini")
FEATHERLESS_MODEL = os.getenv("ROLLBACK_FEATHERLESS_MODEL", "Qwen/Qwen2.5-72B-Instruct")

REVIEWER_ROLES = {"reviewer", "adversarial reviewer"}


def _normalize(role: str) -> str:
    key = (role or "").strip().lower()
    if key in REVIEWER_ROLES or "review" in key:
        return "reviewer"
    if "triage" in key:
        return "triage"
    if "rootcause" in key or "root-cause" in key or "root cause" in key:
        return "rootcause"
    if "fixauthor" in key or "patch" in key or "author" in key:
        return "fixauthor"
    return "triage"


class CannedClient:
    """Offline stand-in: replays a fixed response for the given role."""

    def __init__(self, role: str) -> None:
        self.role = role

    def complete(self, prompt: str) -> str:
        return canned_model_output(self.role, prompt)


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

    if normalized == "reviewer":
        key = os.getenv("FEATHERLESS_API_KEY")
        if not key:
            return CannedClient(normalized)
        return OpenAICompatibleClient(FEATHERLESS_BASE_URL, key, FEATHERLESS_MODEL)

    key = os.getenv("AIMLAPI_API_KEY")
    if not key:
        return CannedClient(normalized)
    return OpenAICompatibleClient(AIMLAPI_BASE_URL, key, AIMLAPI_MODEL)
