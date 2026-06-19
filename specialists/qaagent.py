"""@QA — the agent that actually runs the tests.

@QA is not a rubber stamp and not a fixture: it takes the candidate code from
@CodeAuthor and EXECUTES the loop's required checks in a sandboxed subprocess
(`qa.py`). It reports the real ✅/❌ back into the room and hands off to
@RivalReviewer, who decides what to do with a passing or failing run. A failure
here is a real interpreter failure — that's what makes the loop honest.
"""

from __future__ import annotations

from loopspec import LoopSpec

import qa


HANDLE = "QA"
ROLE = "QA engineer — really executes the loop's checks against the candidate code"
HANDS_OFF_TO = ["RivalReviewer"]


def run_checks(spec: LoopSpec, code: str, tests: dict):
    failures, results = [], []
    for check in spec.required_checks():
        res = qa.evaluate(check.name, code, tests)
        results.append(res)
        if not res.passed:
            detail = res.detail.splitlines()[-1] if res.detail else check.why
            failures.append(f"{check.name} failing — {detail}")
    return failures, results


async def handle(room, message) -> None:
    p = message.payload
    spec: LoopSpec = p["loop_spec"]
    candidate = p["candidate"]
    tests = p.get("tests", {})

    failures, results = run_checks(spec, candidate["code"], tests)
    report = "  ".join(f"{r.name} {r.icon}" for r in results)
    verdict = "all checks pass" if not failures else f"{len(failures)} check(s) failing"
    await room.post(
        sender=HANDLE,
        text=f"ran the checks on revision {candidate['revision']} (real subprocess): "
             f"{report} — {verdict}. @RivalReviewer over to you.",
        mentions=["RivalReviewer"],
        payload={**p, "failures": failures,
                 "qa_results": [(r.name, r.passed, r.detail) for r in results]},
    )


def specialist():
    from band_harness import Specialist

    def adapter_factory():
        from pydantic_ai import Agent as PydanticAgent
        from band.adapters.pydantic_ai import PydanticAIAdapter

        return PydanticAIAdapter(PydanticAgent("openai:gpt-4o"))

    return Specialist(
        handle=HANDLE, role=ROLE, adapter_factory=adapter_factory,
        hands_off_to=HANDS_OFF_TO, config_key="qa",
    )
