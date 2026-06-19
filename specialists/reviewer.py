"""@RivalReviewer — the independent voice that closes each loop turn.

Reads @QA's real results and decides the turn:
  * checks still failing, and revisions left  -> bounce back to @CodeAuthor with the
    exact defects (a real next revision happens).
  * checks pass                               -> hand to @LoopRunner to finalize
    (human gate if the loop demands one, else ship).
  * out of revisions, still failing           -> escalate to @LoopRunner as needs-human.

Live, this agent runs a Featherless OSS model — a different provider from the Author —
so the reviewer is genuinely a second opinion, not the author grading itself. The
back-and-forth is real Band @mention traffic: Author <-> QA <-> Reviewer, turn after
turn, until the exit condition the room designed is actually met.
"""

from __future__ import annotations

from loopspec import LoopSpec


HANDLE = "RivalReviewer"
ROLE = "adversarial reviewer (rival model) — bounces failing revisions back, advances passing ones"
HANDS_OFF_TO = ["CodeAuthor", "LoopRunner"]


async def handle(room, message) -> None:
    p = message.payload
    spec: LoopSpec = p["loop_spec"]
    candidate = p["candidate"]
    failures = p.get("failures", [])
    revision = candidate["revision"]

    if not failures:
        await room.post(
            sender=HANDLE,
            text=("I tried to break it and couldn't — every required check passes. "
                  "@LoopRunner the exit condition is met; finalize it."),
            mentions=["LoopRunner"],
            payload={**p, "outcome": "passed", "final_revision": revision},
        )
        return

    if revision >= spec.max_revisions:
        bullet = "\n".join(f"  • {d}" for d in failures)
        await room.post(
            sender=HANDLE,
            text=(f"still failing after {revision} revision(s) and we're out of budget:\n"
                  f"{bullet}\n@LoopRunner this needs a human."),
            mentions=["LoopRunner"],
            payload={**p, "outcome": "exhausted", "final_revision": revision},
        )
        return

    bullet = "\n".join(f"  • {d}" for d in failures)
    await room.post(
        sender=HANDLE,
        text=(f"not signing off (round {revision}). I broke it:\n{bullet}\n"
              f"@CodeAuthor revise and resubmit."),
        mentions=["CodeAuthor"],
        payload={**p, "defects": failures, "revision_no": revision + 1},
    )


def specialist():
    from band_harness import Specialist

    def adapter_factory():
        from band.adapters.pydantic_ai import PydanticAIAdapter

        # Deliberately a DIFFERENT model from the Author's gpt-4o-mini, so the
        # reviewer is a genuine second opinion rather than the author grading itself.
        return PydanticAIAdapter(model="openai-chat:gpt-4o")

    return Specialist(
        handle=HANDLE, role=ROLE, adapter_factory=adapter_factory,
        hands_off_to=HANDS_OFF_TO, config_key="reviewer",
    )
