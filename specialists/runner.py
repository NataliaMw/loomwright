"""@LoopRunner — kicks off the loop and finalizes it.

The Runner no longer does QA or review itself. Its job is to start the loop (hand
revision 0 to @CodeAuthor) and to FINALIZE when @RivalReviewer hands a turn back —
either the checks passed (ship, or pause for the human gate on a high-stakes loop)
or the room ran out of revisions (escalate to a human). Everything in between is a
real conversation between @CodeAuthor, @QA, and @RivalReviewer, turn after turn,
all on the Band transcript.
"""

from __future__ import annotations

from loopspec import LoopSpec


HANDLE = "LoopRunner"
ROLE = "loop runner — starts the loop and finalizes it once the exit condition is met"
HANDS_OFF_TO = ["CodeAuthor", "TechLead"]


async def _kickoff(room, p: dict) -> None:
    await room.post(
        sender=HANDLE,
        text=("loop approved — starting it. @CodeAuthor draft revision 0; "
              "@QA will run the checks and @RivalReviewer will judge each turn."),
        mentions=["CodeAuthor"],
        payload={**p, "revision_no": 0, "defects": []},
    )


async def _finalize(room, p: dict) -> None:
    spec: LoopSpec = p["loop_spec"]
    outcome = p.get("outcome")
    final_rev = p.get("final_revision", 0)
    record = {"revisions": final_rev, "gate": "n/a", "status": "in_progress",
              "fingerprint": spec.fingerprint()}

    if outcome == "exhausted":
        record["status"] = "needs-human"
        await room.post(
            sender=HANDLE,
            text=f"loop exhausted after {final_rev} revision(s) — handing to @TechLead.",
            mentions=["TechLead"], payload={"loop_record": record, "loop_spec": spec},
        )
        return

    if spec.human_gate:
        decision = await room.await_human(
            spec.human_gate,
            f"High-stakes loop for '{spec.task.title}' converged after {final_rev} "
            f"revision(s), all checks green. Reply APPROVE to ship or REJECT to hold.",
        )
        approved = "approve" in decision.text.lower() and "reject" not in decision.text.lower()
        record["gate"] = f"{spec.human_gate}: {'approved' if approved else 'held'}"
        record["status"] = "shipped" if approved else "held-by-human"
    else:
        record["status"] = "shipped"

    await room.post(
        sender=HANDLE,
        text=(f"loop complete: {record['revisions']} revision(s), gate "
              f"[{record['gate']}], status {record['status']}. shipping code + the "
              f"loop that produced it."),
        mentions=["TechLead"],
        payload={"loop_record": record, "loop_spec": spec},
    )


async def handle(room, message) -> None:
    p = message.payload
    # Two entry points: the Critic approves the loop (kickoff), or the Reviewer
    # hands a finished/exhausted turn back (finalize).
    if "outcome" in p:
        await _finalize(room, p)
    else:
        await _kickoff(room, p)


def specialist():
    from band_harness import Specialist

    def adapter_factory():
        from pydantic_ai import Agent as PydanticAgent
        from band.adapters.pydantic_ai import PydanticAIAdapter

        return PydanticAIAdapter(PydanticAgent("openai:gpt-4o"))

    return Specialist(
        handle=HANDLE, role=ROLE, adapter_factory=adapter_factory,
        hands_off_to=HANDS_OFF_TO, config_key="runner",
    )
