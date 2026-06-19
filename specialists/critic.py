"""@LoopCritic — the agent that argues with the loop *before* it runs.

A loop is only as good as its exit condition. If "done" is too weak, the room will
happily converge on confident-but-wrong code. So the Critic's whole job is to attack
the LoopSpec the Architect proposed: is the exit condition gameable? Is a high-stakes
surface missing a human gate? Does the task need a critic nobody recruited yet?

When it finds a gap on a high-stakes surface, it does the most Band-native thing in
the system: it RECRUITS a specialist into the room on demand (band_add_participant)
rather than pretending one generic reviewer covers everything. Then it hands the
hardened loop to @LoopRunner to execute.
"""

from __future__ import annotations

from loopspec import Task, Check, Critic, LoopSpec


HANDLE = "LoopCritic"
ROLE = "loop critic — attacks the proposed exit condition and recruits missing critics"
HANDS_OFF_TO = ["LoopRunner"]


def harden(spec: LoopSpec) -> tuple[LoopSpec, list[str]]:
    """Return a possibly-strengthened spec plus the list of objections raised."""
    objections: list[str] = []
    task = spec.task

    if task.high_stakes and spec.human_gate is None:
        objections.append(
            "high-stakes surface with no human gate — adding a TechLead sign-off"
        )
        spec.human_gate = "TechLead"

    if task.high_stakes and not any(c.lens == "security" for c in spec.critics):
        objections.append(
            "no security critic on a sensitive surface — recruiting @SecurityCritic on demand"
        )
        spec.critics.append(
            Critic("SecurityCritic", "security", recruited_on_demand=True)
        )

    if task.kind == "bugfix" and not any(c.name == "repro-test" for c in spec.checks):
        objections.append(
            "bugfix without a reproduction test — that exit condition is gameable"
        )
        spec.checks.append(
            Check("repro-test", "fails before the fix, passes after — or we didn't fix it")
        )

    if spec.exit_condition.strip().lower() in {"", "looks good", "tests pass"}:
        objections.append("exit condition too vague — tightening to required-checks + no objections")
        spec.exit_condition = "all required checks pass AND no critic still objects"

    return spec, objections


def _recruited_handles(objections: list[str], spec: LoopSpec) -> list[str]:
    return [c.handle for c in spec.critics if c.recruited_on_demand]


async def handle(room, message) -> None:
    spec: LoopSpec = message.payload["loop_spec"]
    task: Task = message.payload["task"]
    spec, objections = harden(spec)

    recruited = [c for c in spec.critics if c.recruited_on_demand]
    for critic in recruited:
        # The Band-native moment: pull a specialist into the room on demand.
        await room.recruit(critic.handle, lens=critic.lens)

    if objections:
        bullet = "\n".join(f"  • {o}" for o in objections)
        verdict = f"Pushed back on the loop and hardened it:\n{bullet}"
    else:
        verdict = "Loop holds up — exit condition is not gameable. Approved."

    await room.post(
        sender=HANDLE,
        text=(
            f"{verdict}\n@LoopRunner — run this loop. Exit: {spec.exit_condition}. "
            f"Human gate: {spec.human_gate or 'none'}."
        ),
        mentions=["LoopRunner"],
        payload={"loop_spec": spec, "task": task, "objections": objections},
    )


def specialist():
    from band_harness import Specialist

    def adapter_factory():
        from langchain_openai import ChatOpenAI
        from langgraph.checkpoint.memory import InMemorySaver
        from thenvoi.adapters import LangGraphAdapter

        return LangGraphAdapter(
            llm=ChatOpenAI(model="gpt-4o"),
            checkpointer=InMemorySaver(),
        )

    return Specialist(
        handle=HANDLE,
        role=ROLE,
        adapter_factory=adapter_factory,
        hands_off_to=HANDS_OFF_TO,
        config_key="critic",
    )
