"""@LoopArchitect — reads the task and proposes a loop built FOR that task.

This is the move every other coding-agent system skips: instead of running the
same Planner->Coder->Reviewer pipeline for everything, the Architect looks at
what the task actually is (a bugfix vs a refactor vs an auth change) and assembles
the checks, critics, and exit condition that fit. A CSS tweak and a schema
migration should not get the same loop — here they don't.

It hands the proposed LoopSpec to @LoopCritic via Band, who is allowed to push
back before a single line of code is written.
"""

from __future__ import annotations

from loopspec import Task, Check, Critic, LoopSpec


HANDLE = "LoopArchitect"
ROLE = "loop architect — designs a task-specific verification loop, then defends it"
HANDS_OFF_TO = ["LoopCritic"]


def _base_checks(task: Task) -> list[Check]:
    checks = [
        Check("compiles", "the code has to at least build before anything else matters"),
        Check("unit-tests", "behavior is pinned by tests, not vibes"),
    ]
    if task.kind == "bugfix":
        checks.append(
            Check("repro-test", "a test that fails on the bug and passes on the fix — "
                  "otherwise we never proved we fixed it")
        )
    if task.kind == "refactor":
        checks.append(
            Check("behavior-unchanged", "refactors must not change observable behavior; "
                  "diff the public surface", required=True)
        )
        checks.append(
            Check("perf-no-regress", "a refactor that ships a slowdown is a bug", required=False)
        )
    if task.kind == "feature":
        checks.append(Check("acceptance-test", "the new behavior is demonstrated end to end"))
    if task.kind == "migration":
        checks.append(Check("rollback-plan", "every migration needs a tested way back"))
    return checks


def _critics_for(task: Task) -> list[Critic]:
    critics = [Critic("RivalReviewer", "adversarial correctness")]
    if "ui" in [t.lower() for t in task.touches]:
        critics.append(Critic("A11yCritic", "accessibility", recruited_on_demand=True))
    return critics


def propose(task: Task) -> LoopSpec:
    """Assemble the loop. Pure + deterministic so the demo is reproducible; the
    live path lets a model widen the rationale, but the shape is decided here."""
    checks = _base_checks(task)
    critics = _critics_for(task)
    rationale = [
        f"task kind is '{task.kind}', so the loop centers on "
        + {
            "bugfix": "a reproduction test as the real exit gate",
            "refactor": "behavior-equivalence, not new tests",
            "feature": "an end-to-end acceptance test",
            "migration": "a tested rollback path",
        }.get(task.kind, "the default build+test gates"),
    ]
    max_revisions = 2 if task.kind == "bugfix" else 3
    if task.high_stakes:
        rationale.append(
            f"touches a high-stakes surface ({', '.join(task.touches)}), so a human "
            "gate is proposed and a security critic should be recruited"
        )
    return LoopSpec(
        task=task,
        checks=checks,
        critics=critics,
        max_revisions=max_revisions,
        exit_condition="all required checks pass AND no critic still objects",
        human_gate="TechLead" if task.high_stakes else None,
        rationale=rationale,
    )


def _summary(spec: LoopSpec) -> str:
    req = ", ".join(c.name for c in spec.required_checks())
    critics = ", ".join(f"@{c.handle}" for c in spec.critics)
    gate = spec.human_gate or "none"
    return (
        f"Proposed a loop for '{spec.task.title}'. Required gates: {req}. "
        f"Critics: {critics}. Human gate: {gate}. "
        f"@LoopCritic — try to poke holes in this exit condition before we build."
    )


async def handle(room, message) -> None:
    task: Task = message.payload["task"]
    spec = propose(task)
    await room.post(
        sender=HANDLE,
        text=_summary(spec),
        mentions=["LoopCritic"],
        payload={
            "loop_spec": spec,
            "task": task,
            "code_attempts": message.payload.get("code_attempts", {}),
            "tests": message.payload.get("tests", {}),
        },
    )


def specialist():
    from band_harness import Specialist

    def adapter_factory():
        from band.adapters.pydantic_ai import PydanticAIAdapter

        # Model string; routed to the AI/ML API via OPENAI_BASE_URL + OPENAI_API_KEY.
        return PydanticAIAdapter(model="openai-chat:gpt-4o-mini")

    return Specialist(
        handle=HANDLE,
        role=ROLE,
        adapter_factory=adapter_factory,
        hands_off_to=HANDS_OFF_TO,
        config_key="architect",
    )
