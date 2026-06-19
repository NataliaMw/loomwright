"""Live Band path for Loomwright.

Run: `python band_agents.py`

Builds each specialist as a real Band-connected agent via
`band_harness.make_band_agent` and starts them with `run_band_room`. Each agent
reads its `agent_id` / `api_key` from `agent_config.yaml` (+ `.env`) using the
specialist's `config_key`, joins the shared Band room, and waits to be @mentioned.

Coordination is the conversation: drive a task by @mentioning @LoopArchitect in
the room. The Architect proposes a loop, @LoopCritic attacks it (and recruits a
specialist via the Band add-participant tool when the task needs one), and
@LoopRunner runs the loop to its exit condition. The transcript is the record of
both the loop's design and its execution.

Requires the `thenvoi` SDK and credentials. With no creds, use `demo.py` instead.
"""

from __future__ import annotations

import asyncio
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, "shared"))
sys.path.insert(0, _here)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_here, ".env"))
except ImportError:
    pass

from band_harness import run_band_room

from specialists import architect, critic, runner, author, qaagent, reviewer


MISSION = (
    "Loop engineering, as a room. Given a coding task, do NOT run a fixed pipeline. "
    "First DESIGN a verification loop that fits this specific task — the checks that "
    "gate it, the critics that vote, when it's allowed to stop, and whether a human "
    "must sign. Then RUN that loop: generate, let critics attack, revise, re-check "
    "until the exit condition holds. Recruit a specialist into the room when the task "
    "needs a voice nobody added up front. The transcript is the audit trail for both "
    "the loop you built and the code it produced."
)


def build_specialists():
    return [
        architect.specialist(),
        critic.specialist(),
        runner.specialist(),
        author.specialist(),
        qaagent.specialist(),
        reviewer.specialist(),
    ]


async def main() -> None:
    await run_band_room(build_specialists(), MISSION)


if __name__ == "__main__":
    asyncio.run(main())
