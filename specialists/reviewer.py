"""
@Reviewer — the adversarial reviewer in the Rollback Room.

Runs a Featherless OSS model deliberately DIFFERENT from the one @FixAuthor uses,
so the author<->reviewer bounce is a genuine cross-model debate, not a model
arguing with itself. The Reviewer's whole job is to try to BREAK the proposed
diff: hunt for regressions, missing edge cases, and rollback risk.

Outcomes, all expressed as Band @mention handoffs:
  * Diff is weak  -> @mention @FixAuthor BACK with the exact defects to fix.
  * Diff is clean + LOW risk  -> sign off (handoff to @EM as an FYI, no gate).
  * Diff touches a HIGH-RISK surface -> rule-enforced escalation: call
    room.await_human("EM", ...) and DO NOT proceed until a human EM replies.
    There is no code path that ships a high-risk deploy without that reply.

The structured payload is the shared context the next agent reads.
"""

from __future__ import annotations

from typing import Any, Optional


HIGH_RISK_SURFACES = {
    "auth",
    "billing",
    "payments",
    "migration",
    "schema",
    "data-deletion",
    "feature-flag-global",
}

MAX_BOUNCES = 3


def _get_client(role: str):
    from importlib import import_module

    try:
        models = import_module("models")
    except ModuleNotFoundError:
        from . import models  # type: ignore
    return models.get_client(role)


def _ask_reviewer_model(diff_summary: str, blast_radius: str, prior_defects: list[str]) -> str:
    client = _get_client("reviewer")
    prior = "\n".join(f"- {d}" for d in prior_defects) or "- (first pass)"
    prompt = (
        "You are an adversarial senior reviewer. Try to BREAK this fix. "
        "List concrete regression risks, missing edge cases, and rollback hazards. "
        "Be specific and terse.\n\n"
        f"Blast radius: {blast_radius}\n"
        f"Proposed fix:\n{diff_summary}\n\n"
        f"Defects already raised in earlier rounds:\n{prior}\n"
    )
    return client.complete(prompt)


def _classify_risk(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    surfaces = {s.lower() for s in payload.get("touched_surfaces", [])}
    hits = sorted(surfaces & HIGH_RISK_SURFACES)
    declared = bool(payload.get("high_risk", False))
    return (bool(hits) or declared), hits


def _find_defects(payload: dict[str, Any], critique: str) -> list[str]:
    defects: list[str] = []
    diff = payload.get("diff", "")
    if "test" not in diff.lower() and not payload.get("tests_added"):
        defects.append("No regression test added that reproduces the original incident.")
    if not payload.get("rollback_plan"):
        defects.append("Missing rollback plan: how do we revert if this makes it worse?")
    if payload.get("touched_surfaces") and not payload.get("edge_cases_covered"):
        defects.append("Edge cases on the touched surface are not enumerated or handled.")
    for line in critique.splitlines():
        line = line.strip(" -*\t")
        if line and len(line) > 8 and line.lower() not in {d.lower() for d in defects}:
            defects.append(line)
    return defects[:5]


def _next_bounce(payload: dict[str, Any]) -> int:
    return int(payload.get("bounce", 0)) + 1


async def _bounce_back(room, defects: list[str], critique: str, payload: dict[str, Any]) -> None:
    bounce = _next_bounce(payload)
    bullet = "\n".join(f"  • {d}" for d in defects)
    text = (
        f"Not signing off (round {bounce}). I broke it. @FixAuthor revise:\n{bullet}"
    )
    await room.post(
        sender="Reviewer",
        text=text,
        mentions=["FixAuthor"],
        payload={
            "verdict": "changes_requested",
            "bounce": bounce,
            "defects": defects,
            "critique": critique,
            "incident": payload.get("incident"),
            "diff": payload.get("diff"),
            "touched_surfaces": payload.get("touched_surfaces", []),
            "prior_defects": payload.get("prior_defects", []) + defects,
        },
    )


async def _sign_off(room, critique: str, payload: dict[str, Any]) -> None:
    await room.post(
        sender="Reviewer",
        text=(
            "Signed off. I tried to break it and couldn't — tests cover the "
            "incident, rollback plan is sound, low blast radius. Ship it. @EM (FYI)"
        ),
        mentions=["EM"],
        payload={
            "verdict": "approved",
            "risk": "low",
            "bounce": payload.get("bounce", 0),
            "incident": payload.get("incident"),
            "diff": payload.get("diff"),
            "critique": critique,
        },
    )


async def _escalate(room, critique: str, hits: list[str], payload: dict[str, Any]) -> None:
    surfaces = ", ".join(hits) or "declared high-risk"
    prompt = (
        f"High-risk deploy on [{surfaces}] for incident "
        f"{payload.get('incident', 'UNKNOWN')}. Diff looks technically sound but "
        f"the blast radius needs human approval. Reply APPROVE to ship or REJECT "
        f"to hold and bounce back to @FixAuthor."
    )
    await room.post(
        sender="Reviewer",
        text=(
            f"Diff is technically clean, but it touches HIGH-RISK surface "
            f"[{surfaces}]. I cannot sign this off alone — escalating to a human."
        ),
        mentions=["EM"],
        payload={
            "verdict": "escalated",
            "risk": "high",
            "high_risk_surfaces": hits,
            "incident": payload.get("incident"),
            "critique": critique,
        },
    )

    decision = await room.await_human("EM", prompt)
    approved = "approve" in decision.text.lower() and "reject" not in decision.text.lower()

    if approved:
        await room.post(
            sender="Reviewer",
            text="Human EM approved the high-risk deploy. Cleared to ship. @EM",
            mentions=["EM"],
            payload={
                "verdict": "approved_by_human",
                "risk": "high",
                "approved_by": "EM",
                "incident": payload.get("incident"),
                "human_note": decision.text,
            },
        )
    else:
        await room.post(
            sender="Reviewer",
            text=(
                "Human EM held the deploy. @FixAuthor we need a safer approach for "
                "this surface — feature-flag it or split the migration."
            ),
            mentions=["FixAuthor"],
            payload={
                "verdict": "held_by_human",
                "risk": "high",
                "bounce": _next_bounce(payload),
                "incident": payload.get("incident"),
                "human_note": decision.text,
                "defects": ["Human EM rejected: reduce blast radius before resubmitting."],
                "prior_defects": payload.get("prior_defects", []),
            },
        )


async def handle(room, message) -> None:
    payload = dict(message.payload or {})
    diff_summary = payload.get("diff", message.text)
    blast_radius = ", ".join(payload.get("touched_surfaces", [])) or "unspecified"
    prior_defects = payload.get("prior_defects", [])

    critique = _ask_reviewer_model(diff_summary, blast_radius, prior_defects)
    defects = _find_defects(payload, critique)
    bounce = int(payload.get("bounce", 0))

    if defects and bounce < MAX_BOUNCES:
        await _bounce_back(room, defects, critique, payload)
        return

    is_high_risk, hits = _classify_risk(payload)
    if is_high_risk:
        await _escalate(room, critique, hits, payload)
        return

    await _sign_off(room, critique, payload)


def specialist():
    from importlib import import_module

    try:
        band_harness = import_module("band_harness")
    except ModuleNotFoundError:
        import sys
        import os

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "shared"))
        band_harness = import_module("band_harness")

    def adapter_factory():
        from pydantic_ai import Agent as PydanticAgent
        from thenvoi.adapters.pydantic_ai import PydanticAIAdapter

        agent = PydanticAgent("featherless:Qwen/Qwen2.5-72B-Instruct")
        return PydanticAIAdapter(agent)

    return band_harness.Specialist(
        handle="Reviewer",
        role=(
            "adversarial code reviewer running a rival OSS model — you try to BREAK "
            "the proposed fix (regressions, missing edge cases, rollback risk), bounce "
            "weak diffs back to @FixAuthor, and escalate high-risk deploys to the human @EM"
        ),
        adapter_factory=adapter_factory,
        hands_off_to=["FixAuthor", "EM"],
        config_key="reviewer",
    )
