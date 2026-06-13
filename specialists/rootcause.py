"""
@RootCause — the root-cause analyst of the Rollback Room.

Framework: LangGraph.

When @Triage hands over a failing incident, RootCause walks the suspect code
path, argues ONE specific root cause backed by file/line evidence, and writes a
concrete fix spec. It then @mentions @FixAuthor with the structured payload that
the author needs to write the patch.

If @Reviewer (or anyone) bounces work back to @RootCause because the diagnosis
doesn't hold up, RootCause re-reads the evidence and either revises its theory
or escalates. RootCause never writes the patch itself — that's @FixAuthor's job.

The domain backend (code graph, stack traces, blame) is fixtured: this module
proves the Band @mention handoff, not a real static analyzer.
"""

from __future__ import annotations

import json
import sys
import os
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))

from band_harness import Specialist


HANDLE = "RootCause"
ROLE = "root-cause analyst"
HANDS_OFF_TO = ["FixAuthor"]

MISSION = (
    "Read the failing code path that @Triage flagged, argue exactly ONE root "
    "cause with file:line evidence, and write a fix spec precise enough that "
    "@FixAuthor can patch it without guessing."
)


CODE_PATH_FIXTURE = {
    "service": "checkout-api",
    "incident": "INC-4471",
    "symptom": "5xx spike on POST /v2/checkout/confirm after deploy dpl_9c1f",
    "suspect_path": [
        {
            "file": "src/checkout/idempotency.py",
            "line": 58,
            "code": "cache.set(key, payload)",
            "note": "TTL argument dropped in the write-through switch, so the key expires on next read",
        },
        {
            "file": "src/checkout/idempotency.py",
            "line": 73,
            "code": "record = cache.get(key)",
            "note": "returns None once the key has expired, so the request looks brand-new",
        },
        {
            "file": "src/checkout/handlers.py",
            "line": 31,
            "code": "if not idempotency.seen(key): charge(order)",
            "note": "re-charges under client retry because seen() is now always False",
        },
    ],
    "blame": {
        "commit": "dpl_9c1f",
        "pr": "#2281",
        "author": "deploy-bot",
        "change": "switched idempotency cache to write-through and dropped ttl=PREV_TTL on cache.set",
    },
    "trace_top": "DuplicateChargeError: order already processed within retry window",
}


def _diagnosis_prompt(triage_payload: dict[str, Any]) -> str:
    return (
        "You are a senior incident responder. Given the triage hand-off and the "
        "fixtured suspect code path, name ONE root cause in a single sentence, "
        "cite the exact file:line that breaks, and state the minimal fix.\n\n"
        f"Triage hand-off:\n{json.dumps(triage_payload, indent=2)}\n\n"
        f"Suspect code path:\n{json.dumps(CODE_PATH_FIXTURE, indent=2)}\n\n"
        "Respond as: ROOT CAUSE: ... | EVIDENCE: file:line | FIX: ..."
    )


def _canned_diagnosis() -> str:
    return (
        "ROOT CAUSE: idempotency.py:58 lost its ttl=PREV_TTL when the cache went "
        "write-through, so the dedupe key expires before the retry lands and "
        "handlers.py:31 re-charges the order. | EVIDENCE: src/checkout/idempotency.py:58 "
        "| FIX: restore the explicit ttl=PREV_TTL on cache.set and clamp it to a "
        "non-zero floor so the idempotency guard can never expire instantly."
    )


def _model_complete(prompt: str) -> str:
    try:
        from models import get_client
    except ImportError:
        return _canned_diagnosis()
    client = get_client(HANDLE)
    if hasattr(client, "complete"):
        return client.complete(prompt)
    response = client.chat.completions.create(
        model=os.getenv("ROLLBACK_ROOTCAUSE_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return response.choices[0].message.content


def _build_fix_spec(diagnosis: str, triage_payload: dict[str, Any]) -> dict[str, Any]:
    target = CODE_PATH_FIXTURE["suspect_path"][0]
    return {
        "incident": CODE_PATH_FIXTURE["incident"],
        "root_cause": diagnosis,
        "primary_evidence": f"{target['file']}:{target['line']}",
        "blamed_commit": CODE_PATH_FIXTURE["blame"]["commit"],
        "regression": CODE_PATH_FIXTURE["blame"]["change"],
        "fix_spec": {
            "file": "src/checkout/idempotency.py",
            "line": 58,
            "change": "cache.set(key, payload, ttl=max(PREV_TTL, MIN_IDEMPOTENCY_TTL))",
            "guard": "the idempotency record must outlive the client retry window",
            "tests": [
                "confirm() fired twice under retry -> exactly one charge",
                "key survives past the retry window before expiring",
            ],
        },
        "risk": triage_payload.get("risk", "high"),
        "from": HANDLE,
    }


def _revised_diagnosis(reason: str) -> str:
    return (
        f"REVISED after @Reviewer pushback ({reason}): the dropped TTL is the real "
        "cause, and the durable fix belongs at the source in idempotency.py:58, not "
        "a guard bolted onto handlers.py. Restoring an explicit, floored ttl keeps "
        "the contract that a dedupe key always outlives the client retry window."
    )


async def handle(room, message) -> None:
    payload = message.payload or {}
    bounced_back = HANDLE in message.mentions and message.sender in HANDS_OFF_TO + ["Reviewer"]

    if bounced_back:
        reason = payload.get("reason", payload.get("review", "diagnosis questioned"))
        diagnosis = _revised_diagnosis(str(reason))
    else:
        diagnosis = _model_complete(_diagnosis_prompt(payload)).strip()

    fix_spec = _build_fix_spec(diagnosis, payload)

    text = (
        f"Diagnosed {fix_spec['incident']}. {diagnosis} "
        f"Primary evidence at {fix_spec['primary_evidence']} "
        f"(regression in {fix_spec['blamed_commit']}). "
        f"@FixAuthor — patch per fix_spec and ping @Reviewer when ready."
    )

    await room.post(
        sender=HANDLE,
        text=text,
        mentions=["FixAuthor"],
        payload=fix_spec,
    )


def _adapter_factory():
    from thenvoi.adapters.langgraph import LangGraphAdapter

    return LangGraphAdapter()


def specialist() -> Specialist:
    return Specialist(
        handle=HANDLE,
        role=ROLE,
        adapter_factory=_adapter_factory,
        hands_off_to=HANDS_OFF_TO,
        config_key="rootcause",
    )
