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

import qa


HANDLE = "LoopRunner"
ROLE = "loop runner — executes the assembled generate/critique/revise loop to its exit condition"
HANDS_OFF_TO = ["TechLead"]


def _live_fix(task_title: str, buggy: str, defects: list[str], tests: dict) -> str | None:
    """Ask the AI/ML API to repair the code given the REAL test failures. One
    focused call — not a chain. Returns None if no key/model or anything goes wrong,
    so the loop always falls back to the deterministic fix and never breaks on video."""
    try:
        from models import get_client
    except ImportError:
        return None
    client = get_client("runner")
    if client is None or client.__class__.__name__ == "CannedClient":
        return None
    prompt = (
        "You are fixing Python code so a failing test passes. Return ONLY the corrected "
        "code, no prose, no fences.\n\n"
        f"Task: {task_title}\n\nCurrent code:\n{buggy}\n\n"
        f"The tests that must pass:\n{tests.get('unit','')}\n{tests.get('repro','')}{tests.get('acceptance','')}\n\n"
        f"Failing checks to address:\n" + "\n".join(f"- {d}" for d in defects)
    )
    try:
        out = client.complete(prompt).strip()
    except Exception:
        return None
    if out.startswith("```"):
        out = out.strip("`")
        out = out[out.find("\n") + 1:] if "\n" in out else out
    return out or None


def _generate(spec: LoopSpec, revision: int, open_defects: list[str], code_attempts: dict) -> dict:
    """Produce a revision's actual code. Revision 0 is the first (buggy) attempt.
    On a revision that must fix things, try a LIVE model (AI/ML API) first; whatever
    it returns is then gated by the REAL QA subprocess below, so a hallucinated fix
    that doesn't pass the tests simply doesn't end the loop. Falls back to the task's
    known-good fix when no key is set — so the demo is reproducible with zero creds."""
    addressed = list(open_defects)
    if revision == 0:
        return {"revision": revision, "code": code_attempts["buggy"], "addressed": addressed,
                "source": "first-attempt"}
    live = _live_fix(spec.task.title, code_attempts.get("buggy", ""), open_defects,
                     code_attempts.get("tests", {}))
    if live:
        return {"revision": revision, "code": live, "addressed": addressed, "source": "AI/ML API"}
    return {"revision": revision, "code": code_attempts["fixed"], "addressed": addressed,
            "source": "deterministic"}


def _run_checks(spec: LoopSpec, code: str, tests: dict) -> tuple[list[str], list[qa.CheckResult]]:
    """REALLY run every required check against the candidate code. A failure here
    is a real interpreter failure, not a fixture — that's what gates the loop."""
    failures: list[str] = []
    results: list[qa.CheckResult] = []
    for check in spec.required_checks():
        res = qa.evaluate(check.name, code, tests)
        results.append(res)
        if not res.passed:
            failures.append(f"{check.name} failing — {res.detail.splitlines()[-1] if res.detail else check.why}")
    return failures, results


def _critic_objections(spec: LoopSpec, revision: int) -> list[str]:
    """Each critic gets a vote per revision. They drop their objection once the
    loop has addressed it (here, after the first revision)."""
    if revision >= 1:
        return []
    objs = []
    for critic in spec.critics:
        objs.append(f"@{critic.handle} ({critic.lens}) wants another pass")
    return objs


async def _step(room, spec: LoopSpec, revision: int, defects: list[str],
                code_attempts: dict, tests: dict) -> dict:
    rev = _generate(spec, revision, defects, {**code_attempts, "tests": tests})
    src = rev.get("source", "")
    src_note = f" [{src}]" if src and src != "first-attempt" else ""
    await room.post(
        sender=HANDLE,
        text=f"revision {revision}: drafted a change{src_note}" +
             (f" addressing {len(defects)} defect(s)" if defects else ""),
        mentions=[c.handle for c in spec.critics] or ["RivalReviewer"],
        payload={"revision": rev, "loop_spec": spec},
    )
    # REAL QA: run the required checks against this revision's actual code.
    # Posted with no dispatching @mention — QA runs inside the runner's own turn,
    # so re-triggering the runner here would recurse.
    failures, results = _run_checks(spec, rev["code"], tests)
    report = "  ".join(f"{r.name} {r.icon}" for r in results)
    await room.post(
        sender="QA",
        text=f"ran the checks on revision {revision} (real subprocess): {report}",
        mentions=[],
        payload={"qa_results": [(r.name, r.passed, r.detail) for r in results]},
    )
    objections = _critic_objections(spec, revision)
    return {"failures": failures, "objections": objections, "rev": rev, "results": results}


async def run_loop(room, spec: LoopSpec, code_attempts: dict, tests: dict) -> dict:
    """The loop. Returns the final record (revisions taken, gate outcome, status)."""
    defects: list[str] = []
    revision = 0
    record = {"revisions": 0, "gate": "n/a", "status": "in_progress",
              "fingerprint": spec.fingerprint(), "qa": []}

    while revision <= spec.max_revisions:
        result = await _step(room, spec, revision, defects, code_attempts, tests)
        failures, objections = result["failures"], result["objections"]
        record["revisions"] = revision
        record["qa"] = [(r.name, r.passed) for r in result["results"]]

        if not failures and not objections:
            break  # exit condition satisfied — REAL checks passed

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
    code_attempts = message.payload.get("code_attempts", {"buggy": "", "fixed": ""})
    tests = message.payload.get("tests", {})
    await run_loop(room, spec, code_attempts, tests)


def specialist():
    from band_harness import Specialist

    def adapter_factory():
        from pydantic_ai import Agent as PydanticAgent
        from band.adapters.pydantic_ai import PydanticAIAdapter

        agent = PydanticAgent("openai:gpt-4o")
        return PydanticAIAdapter(agent)

    return Specialist(
        handle=HANDLE,
        role=ROLE,
        adapter_factory=adapter_factory,
        hands_off_to=HANDS_OFF_TO,
        config_key="runner",
    )
