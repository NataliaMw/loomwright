"""Ouroboros — offline demo. Zero credentials, fully deterministic.

Run: `python demo.py`

The whole pitch in one run: feed the room TWO different tasks and watch it build
TWO different loops. A vibecoding tool (and every fixed Planner->Coder->Reviewer
pipeline) would run the identical loop for both. Loop engineering means the loop
should fit the task — so here it does.

  task A: a bugfix on a pure function   -> a tight loop gated on a repro test
  task B: an auth change (high-stakes)  -> a loop that recruits a security critic
                                           on demand and pauses for a human gate

Every line is a real Band-style @mention handoff. The room first DESIGNS the loop
(@LoopArchitect proposes, @LoopCritic attacks + recruits), then RUNS it
(@LoopRunner: generate -> critique -> revise -> re-check until the exit condition).
Both phases live on the same transcript — the design of the loop is as auditable
as the code it produces.
"""

from __future__ import annotations

import asyncio
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, "shared"))
sys.path.insert(0, _here)

from band_harness import LocalRoom
from loopspec import Task
from specialists import architect, critic, runner, author, qaagent, reviewer
from tasks import REGISTRY, GALLERY, make_task


HUMAN = "TechLead"


def _banner(title: str) -> None:
    line = "═" * 74
    print(f"\n{line}\n  {title}\n{line}")


def _recruitable_critic(handle: str):
    """Build the handler the room installs when it recruits this critic on demand.
    The recruited critic acknowledges it joined and is now voting in the loop."""

    def factory(lens: str):
        announced = {"done": False}

        async def handler(room, message):
            # Cast a vote into the transcript without re-triggering the runner's
            # entry handler — the runner already accounts for this critic's vote.
            # Announce joining once; stay quiet on later revisions.
            if announced["done"]:
                return
            announced["done"] = True
            await room.post(
                sender=handle,
                text=f"joined as the {lens} critic — voting on every revision from here.",
                mentions=[],
                payload={},
            )
        return handler

    return factory


def _build_room() -> LocalRoom:
    room = LocalRoom()
    room.join(architect.HANDLE, architect.handle)
    room.join(critic.HANDLE, critic.handle)
    room.join(runner.HANDLE, runner.handle)
    room.join(author.HANDLE, author.handle)
    room.join(qaagent.HANDLE, qaagent.handle)
    room.join(reviewer.HANDLE, reviewer.handle)
    room.join_human(HUMAN, auto_reply="APPROVE — reviewed the diff and the loop, ship it.")
    for h in ("SecurityCritic", "A11yCritic"):
        room.register_recruitable(h, _recruitable_critic(h))
    return room


async def _drive(room: LocalRoom, entry: dict) -> None:
    task = entry["task"]
    await room.post(
        sender="user",
        text=f"New task: {task.title} — {task.description}",
        mentions=[architect.HANDLE],
        payload={
            "task": task,
            "code_attempts": {"buggy": entry["buggy"], "fixed": entry["fixed"]},
            "tests": entry["tests"],
        },
    )


def _print_loop(room: LocalRoom, label: str) -> str:
    spec = None
    record = None
    for msg in room.transcript:
        if (msg.payload or {}).get("loop_spec") is not None:
            spec = msg.payload["loop_spec"]
        if (msg.payload or {}).get("loop_record") is not None:
            record = msg.payload["loop_record"]
    _banner(f"{label}: THE LOOP THE ROOM BUILT")
    print(spec.render())
    print(f"\n  fingerprint: {spec.fingerprint()}")
    if record:
        print(f"  outcome    : {record['revisions']} revision(s), "
              f"gate [{record['gate']}], status {record['status']}")
    return spec.fingerprint()


async def _run_task(entry: dict, label: str) -> str:
    task = entry["task"]
    _banner(f"{label}: {task.title}  "
            f"[{task.kind}, touches: {', '.join(task.touches) or 'nothing risky'}]")
    room = _build_room()
    await _drive(room, entry)
    return _print_loop(room, label)


def _design_only(task: Task, label: str) -> str:
    """Synthesize and print the loop for any task (no executable code attached).
    This is the generality: feed it anything, it designs the fitting loop."""
    spec = architect.propose(task)
    _banner(f"{label}: {task.title}  "
            f"[{task.kind}, touches: {', '.join(task.touches) or 'nothing risky'}]")
    print(spec.render())
    print(f"\n  fingerprint: {spec.fingerprint()}")
    return spec.fingerprint()


async def _run_gallery() -> None:
    _banner("ANY TASK → THE LOOP IT NEEDS")
    print("  Feed the room any task. It reads the kind and the surfaces it touches,\n"
          "  and synthesizes the verification loop that task needs — different checks,\n"
          "  different critics, different gates. Nothing here is hardcoded per task.\n")
    seen = {}
    # Tasks A and B run for real (the loop executes tests and gates on the result).
    fp_a = await _run_task(REGISTRY["a"], "REAL-QA TASK 1")
    fp_b = await _run_task(REGISTRY["b"], "REAL-QA TASK 2")
    seen["1 " + REGISTRY["a"]["task"].title] = fp_a
    seen["2 " + REGISTRY["b"]["task"].title] = fp_b
    # The rest show synthesis across a wide range of kinds and surfaces.
    for i, task in enumerate(GALLERY[2:], start=3):
        seen[f"{i} {task.title}"] = _design_only(task, f"TASK {i}")

    _banner(f"PROOF: {len(seen)} tasks → {len(set(seen.values()))} DISTINCT loops")
    for name, fp in seen.items():
        print(f"  • {name[2:][:42]:44s} {fp.split(' critics')[0]}")
    distinct = len(set(seen.values()))
    print(f"\n  {distinct} of {len(seen)} loops are unique — the loop is engineered for\n"
          f"  the task, not copy-pasted. that generality is the whole point.\n")


async def _run_freeform(title: str, kind: str, touches: list[str]) -> None:
    task = make_task(title, kind=kind, touches=touches)
    # If it matches a task we have real code for, run it for real; else design it.
    for entry in REGISTRY.values():
        if entry["task"].title.lower() == title.lower():
            await _run_task(entry, "YOUR TASK")
            return
    _banner("YOUR TASK → THE LOOP IT NEEDS")
    _design_only(task, "YOUR TASK")
    print("\n  (attach real buggy/fixed code + tests in tasks.py to have the loop\n"
          "   actually execute and gate on results, like the demo's real-QA tasks.)\n")


async def main() -> None:
    import argparse
    p = argparse.ArgumentParser(
        description="Ouroboros — a Band room that engineers the loop a task needs, then runs it.")
    p.add_argument("title", nargs="?", help="free-form task title; omit to run the gallery")
    p.add_argument("--kind", default="feature",
                   choices=["bugfix", "refactor", "feature", "migration"])
    p.add_argument("--touches", default="",
                   help="comma-separated surfaces, e.g. auth,db,ui,payments,pii,api,concurrency,perf")
    args = p.parse_args()

    if args.title:
        touches = [t.strip() for t in args.touches.split(",") if t.strip()]
        await _run_freeform(args.title, args.kind, touches)
    else:
        await _run_gallery()


if __name__ == "__main__":
    asyncio.run(main())
