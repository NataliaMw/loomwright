"""@CodeAuthor — writes each revision, then hands the candidate to @QA.

The Author owns code generation only. It does NOT judge its own work — that's the
whole point of the loop. It writes a revision (the first attempt, or a repair that
addresses the exact defects @RivalReviewer bounced back), then @mentions @QA to run
the real checks. Author and reviewer are deliberately different agents (and, live,
different model providers) so the critique is real, not a model grading itself.
"""

from __future__ import annotations

from loopspec import LoopSpec


HANDLE = "CodeAuthor"
ROLE = "code author — writes each revision and hands it to @QAEngineer; never reviews its own work"
HANDS_OFF_TO = ["QAEngineer"]


def _live_fix(task_title: str, buggy: str, defects: list[str], tests: dict) -> str | None:
    try:
        from models import get_client
    except ImportError:
        return None
    client = get_client("author")
    if client is None or client.__class__.__name__ == "CannedClient":
        return None
    prompt = (
        "You are fixing Python code so a failing test passes. Return ONLY the corrected "
        "code, no prose, no fences.\n\n"
        f"Task: {task_title}\n\nCurrent code:\n{buggy}\n\n"
        f"Tests that must pass:\n{tests.get('unit','')}\n{tests.get('repro','')}{tests.get('acceptance','')}\n\n"
        "Failing checks to address:\n" + "\n".join(f"- {d}" for d in defects)
    )
    try:
        out = client.complete(prompt).strip()
    except Exception:
        return None
    if out.startswith("```"):
        out = out.strip("`")
        out = out[out.find("\n") + 1:] if "\n" in out else out
    return out or None


def write_revision(spec: LoopSpec, revision: int, defects: list[str],
                   code_attempts: dict, tests: dict) -> dict:
    if revision == 0:
        return {"revision": revision, "code": code_attempts["buggy"],
                "addressed": [], "source": "first-attempt"}
    live = _live_fix(spec.task.title, code_attempts.get("buggy", ""), defects, tests)
    if live:
        return {"revision": revision, "code": live, "addressed": list(defects),
                "source": "AI/ML API"}
    return {"revision": revision, "code": code_attempts["fixed"],
            "addressed": list(defects), "source": "deterministic"}


async def handle(room, message) -> None:
    p = message.payload
    spec: LoopSpec = p["loop_spec"]
    revision = p.get("revision_no", 0)
    defects = p.get("defects", [])
    code_attempts = p.get("code_attempts", {})
    tests = p.get("tests", {})

    rev = write_revision(spec, revision, defects, code_attempts, tests)
    src = rev.get("source", "")
    note = f" [{src}]" if src and src != "first-attempt" else ""
    await room.post(
        sender=HANDLE,
        text=(f"revision {revision}{note}: "
              + (f"reworked to address {len(defects)} defect(s)." if defects
                 else "first draft.")
              + " @QAEngineer — run the loop's checks on this."),
        mentions=["QAEngineer"],
        payload={**p, "candidate": rev, "revision_no": revision},
    )


def specialist():
    from band_harness import Specialist

    def adapter_factory():
        from band.adapters.pydantic_ai import PydanticAIAdapter

        return PydanticAIAdapter(model="openai-chat:gpt-4o-mini")

    return Specialist(
        handle=HANDLE, role=ROLE, adapter_factory=adapter_factory,
        hands_off_to=HANDS_OFF_TO, config_key="author",
    )
