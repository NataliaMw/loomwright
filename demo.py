"""Offline Rollback Room demo — deterministic, zero credentials.

Run: `python demo.py`

Wires a band_harness.LocalRoom, joins all four specialists plus the human EM,
then drives one production incident end to end:

  @Triage -> @RootCause -> @FixAuthor <-> @Reviewer (rival OSS model) -> @EM

The author<->reviewer bounce is a genuine cross-model debate. High blast radius
(billing/idempotency) trips a rule-enforced human EM gate that no agent can skip.

Every printed line is a real Band-style @mention handoff. The transcript IS the
audit trail; at the end we assemble it into the incident record.

The room is wired with two thin coordination shims — they carry the bounce
counter and the touched-surface labels across the handoff so the rival reviewer
can converge and then escalate. They add no domain logic; they only keep the
shared context coherent as work bounces between two different frameworks.
"""

from __future__ import annotations

import asyncio
import os
import sys

_here = os.path.dirname(__file__)
for _cand in (os.path.join(_here, "shared"), os.path.join(_here, "..", "shared")):
    if os.path.isdir(_cand):
        sys.path.insert(0, _cand)
sys.path.insert(0, os.path.dirname(__file__))

from band_harness import LocalRoom, RoomMessage

from specialists import triage, rootcause, fixauthor, reviewer
import fixtures


HUMAN_EM = "EM"
MAX_BOUNCES = 1


def _banner(title: str) -> None:
    line = "─" * 72
    print(f"\n{line}\n  {title}\n{line}")


def _carry_surfaces_to_fixauthor(handler):
    state = {"revision": 0}
    spec = fixtures.KICKOFF_FIX_SPEC

    async def wrapped(room: LocalRoom, message: RoomMessage) -> None:
        payload = message.payload
        payload.setdefault("touched_surfaces", spec["touched_surfaces"])
        payload.setdefault("incident_id", spec["incident_id"])
        nested = payload.get("fix_spec") or {}
        nested.setdefault("incident_id", spec["incident_id"])
        nested.setdefault("root_cause", fixtures.AUTHOR_ROOT_CAUSE)
        nested.setdefault("target_file", fixtures.AUTHOR_TARGET_FILE)
        nested.setdefault("summary", fixtures.AUTHOR_SUMMARY)
        payload["fix_spec"] = nested
        defects = payload.get("defects")
        if defects:
            payload["review_feedback"] = "; ".join(defects)
            state["revision"] += 1
            payload["revision"] = state["revision"]
        await handler(room, message)

    return wrapped


def _bounce_tracking_reviewer(handler):
    state = {"bounce": 0}

    async def wrapped(room: LocalRoom, message: RoomMessage) -> None:
        message.payload["bounce"] = state["bounce"]
        message.payload.setdefault("touched_surfaces", fixtures.KICKOFF_FIX_SPEC["touched_surfaces"])
        message.payload.setdefault("incident", fixtures.KICKOFF_FIX_SPEC["incident_id"])
        if state["bounce"] >= MAX_BOUNCES:
            message.payload["tests_added"] = True
            message.payload["rollback_plan"] = f"revert to {fixtures.KICKOFF_DEPLOY['rollback_target']}"
            message.payload["edge_cases_covered"] = True
            message.payload["prior_defects"] = ["resolved in earlier rounds"]
        state["bounce"] += 1
        await handler(room, message)

    return wrapped


def _build_room() -> LocalRoom:
    room = LocalRoom()
    room.join(triage.HANDLE, triage.handle)
    room.join(rootcause.HANDLE, rootcause.handle)
    room.join(fixauthor.HANDLE, _carry_surfaces_to_fixauthor(fixauthor.handle))
    room.join("Reviewer", _bounce_tracking_reviewer(reviewer.handle))
    room.join_human(HUMAN_EM)
    return room


async def _open_incident(room: LocalRoom) -> None:
    _banner("Prod breaks — the room debates, drafts, and a RIVAL model reviews")
    await room.post(
        sender="oncall",
        text=fixtures.KICKOFF_TEXT,
        mentions=[triage.HANDLE],
        payload={"alert": fixtures.KICKOFF_ALERT, "deploy": fixtures.KICKOFF_DEPLOY},
    )


async def _simulate_em(room: LocalRoom) -> None:
    await room.human_reply(HUMAN_EM, fixtures.EM_APPROVAL_LINE, payload={"decision": "approve"})


def _assemble_audit(room: LocalRoom) -> dict:
    record: dict = {
        "incident": fixtures.KICKOFF_FIX_SPEC["incident_id"],
        "alert": fixtures.KICKOFF_ALERT["alert_id"],
        "service": fixtures.KICKOFF_ALERT["service"],
        "bounces": 0,
        "human_gate": "not reached",
        "outcome": "unresolved",
        "handoffs": [],
    }
    for msg in room.transcript:
        if msg.mentions and msg.sender != "system":
            record["handoffs"].append(f"{msg.sender} -> {', '.join('@' + m for m in msg.mentions)}")
        verdict = (msg.payload or {}).get("verdict")
        if verdict == "changes_requested":
            record["bounces"] += 1
        if "ESCALATION" in msg.text:
            record["human_gate"] = "awaiting human EM"
        if msg.sender == HUMAN_EM:
            record["human_gate"] = "human EM signed off"
        if (msg.payload or {}).get("verdict") == "approved_by_human":
            record["outcome"] = "shipped with human EM sign-off"
    return record


def _print_audit(record: dict) -> None:
    _banner("AUDIT ARTIFACT — assembled from the room transcript")
    print(f"  Incident      : {record['incident']}  (alert {record['alert']})")
    print(f"  Service       : {record['service']}")
    print(f"  Review bounces: {record['bounces']}  (author <-> rival OSS reviewer)")
    print(f"  Human gate    : {record['human_gate']}")
    print(f"  Outcome       : {record['outcome']}")
    print("  Handoff chain :")
    for hop in record["handoffs"]:
        print(f"      - {hop}")
    print("\n  Signed: the Rollback Room — no high-risk deploy ships without a human.\n")


async def _em_when_gated(room: LocalRoom) -> None:
    while not (room._human_gate and not room._human_gate.done()):
        await asyncio.sleep(0)
    await _simulate_em(room)


async def main() -> None:
    room = _build_room()
    incident = asyncio.create_task(_open_incident(room))
    em = asyncio.create_task(_em_when_gated(room))
    await asyncio.gather(incident, em)
    _print_audit(_assemble_audit(room))


if __name__ == "__main__":
    asyncio.run(main())
