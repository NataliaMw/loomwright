"""@LoopRunner — executes the loop the room just designed.

Up to here the room argued about the *shape* of the loop. Now it runs it: generate
a revision, let every critic attack it, evaluate the required checks, and decide —
stop, revise again, or (on a high-stakes surface) pause for a human. The exit
condition is the one the Architect proposed and the Critic hardened; nothing here
ad-libs a new definition of "done".

Each revision is a real @mention bounce in the room, so the loop's execution is on
the same audit trail as its design. The output is the verified code plus the
LoopSpec that produced it — the loop is a first-class deliverable, not scaffolding.
"""

from __future__ import annotations

from loopspec import LoopSpec


HANDLE = "LoopRunner"
ROLE = "loop runner — executes the assembled generate/critique/revise loop to its exit condition"
HANDS_OFF_TO = ["TechLead"]


def _generate(spec: LoopSpec, revision: int, open_defects: list[str]) -> dict:
    """Produce a revision. Deterministic by default so the demo is reproducible;
    a live model can fill the body, but the loop's control flow does not depend on it.

    The model is asked to address exactly the defects critics raised last round —
    one focused call per revision, not a five-call chain."""
    addressed = list(open_defects)
    body = f"// revision {revision} for {spec.task.title}\n"
    if addressed:
        body += "// addresses: " + "; ".join(addressed) + "\n"
    return {"revision": revision, "code": body, "addressed": addressed}


def _run_checks(spec: LoopSpec, revision: int) -> list[str]:
    """Evaluate required checks. Model: early revisions fail the task's signature
    gate, then it passes once the loop has done its job — this is what makes the
    loop *necessary* instead of one-shot."""
    failures: list[str] = []
    signature = {
        "bugfix": "repro-test",
        "refactor": "behavior-unchanged",
        "feature": "acceptance-test",
        "migration": "rollback-plan",
    }.get(spec.task.kind)
    for check in spec.required_checks():
        if check.name == signature and revision == 0:
            failures.append(f"{check.name} failing — {check.why}")
    return failures


def _critic_objections(spec: LoopSpec, revision: int) -> list[str]:
    """Each critic gets a vote per revision. They drop their objection once the
    loop has addressed it (here, after the first revision)."""
    if revision >= 1:
        return []
    objs = []
    for critic in spec.critics:
        objs.append(f"@{critic.handle} ({critic.lens}) wants another pass")
    return objs


async def _step(room, spec: LoopSpec, revision: int, defects: list[str]) -> dict:
    rev = _generate(spec, revision, defects)
    await room.post(
        sender=HANDLE,
        text=f"revision {revision}: drafted a change" +
             (f" addressing {len(defects)} defect(s)" if defects else ""),
        mentions=[c.handle for c in spec.critics] or ["RivalReviewer"],
        payload={"revision": rev, "loop_spec": spec},
    )
    failures = _run_checks(spec, revision)
    objections = _critic_objections(spec, revision)
    return {"failures": failures, "objections": objections, "rev": rev}


async def run_loop(room, spec: LoopSpec) -> dict:
    """The loop. Returns the final record (revisions taken, gate outcome, status)."""
    defects: list[str] = []
    revision = 0
    record = {"revisions": 0, "gate": "n/a", "status": "in_progress",
              "fingerprint": spec.fingerprint()}

    while revision <= spec.max_revisions:
        result = await _step(room, spec, revision, defects)
        failures, objections = result["failures"], result["objections"]
        record["revisions"] = revision

        if not failures and not objections:
            break  # exit condition satisfied

        defects = failures + objections
        bullet = "\n".join(f"  • {d}" for d in defects)
        if revision == spec.max_revisions:
            await room.post(
                sender=HANDLE,
                text=f"hit max revisions ({spec.max_revisions}) with open items:\n{bullet}",
                mentions=["TechLead"], payload={"loop_spec": spec},
            )
            record["status"] = "needs-human"
            break
        await room.post(
            sender=HANDLE,
            text=f"exit condition not met — looping again:\n{bullet}",
            mentions=[c.handle for c in spec.critics] or ["RivalReviewer"],
            payload={"loop_spec": spec},
        )
        revision += 1

    if spec.human_gate:
        decision = await room.await_human(
            spec.human_gate,
            f"High-stakes loop for '{spec.task.title}' converged after "
            f"{record['revisions']} revision(s). Reply APPROVE to ship or REJECT to hold.",
        )
        approved = "approve" in decision.text.lower() and "reject" not in decision.text.lower()
        record["gate"] = f"{spec.human_gate}: {'approved' if approved else 'held'}"
        record["status"] = "shipped" if approved else "held-by-human"
    elif record["status"] == "in_progress":
        record["status"] = "shipped"

    await room.post(
        sender=HANDLE,
        text=(
            f"loop complete: {record['revisions']} revision(s), gate [{record['gate']}], "
            f"status {record['status']}. shipping code + the loop that produced it."
        ),
        mentions=["TechLead"],
        payload={"loop_record": record, "loop_spec": spec},
    )
    return record


async def handle(room, message) -> None:
    spec: LoopSpec = message.payload["loop_spec"]
    await run_loop(room, spec)


def specialist():
    from band_harness import Specialist

    def adapter_factory():
        from pydantic_ai import Agent as PydanticAgent
        from thenvoi.adapters.pydantic_ai import PydanticAIAdapter

        agent = PydanticAgent("openai:gpt-4o")
        return PydanticAIAdapter(agent)

    return Specialist(
        handle=HANDLE,
        role=ROLE,
        adapter_factory=adapter_factory,
        hands_off_to=HANDS_OFF_TO,
        config_key="runner",
    )
