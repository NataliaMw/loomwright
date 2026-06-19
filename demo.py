"""Loomwright — offline demo. Zero credentials, fully deterministic.

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
from specialists import architect, critic, runner
from tasks import REGISTRY


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


async def main() -> None:
    fp_a = await _run_task(REGISTRY["a"], "TASK A")
    fp_b = await _run_task(REGISTRY["b"], "TASK B")

    _banner("PROOF: two tasks, two DIFFERENT loops")
    print(f"  loop A: {fp_a}")
    print(f"  loop B: {fp_b}")
    print(f"\n  same room, same agents — different loop. "
          f"{'DIFFERENT ✅' if fp_a != fp_b else 'IDENTICAL ❌'}")
    print("  that difference is the whole point: the loop is engineered for the task,\n"
          "  not copy-pasted. loop engineering, run by a band of agents.\n")


if __name__ == "__main__":
    asyncio.run(main())
