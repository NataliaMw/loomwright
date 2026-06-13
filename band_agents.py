"""Live Band path for the Rollback Room.

Run: `python band_agents.py`

Builds every specialist as a real Band-connected agent via
`band_harness.make_band_agent` and starts them with `run_band_room`. Each agent
reads its `agent_id` / `api_key` from `agent_config.yaml` (+ `.env`) using the
specialist's `config_key`, then joins the shared Band room and waits to be
@mentioned. Coordination is the conversation: drive the workflow by @mentioning
@Triage in the room and the agents hand off down the chain on their own.

Requires the `thenvoi` SDK and credentials. With no creds, use `demo.py` instead.
"""

from __future__ import annotations

import asyncio
import os
import sys

_here = os.path.dirname(__file__)
for _cand in (os.path.join(_here, "shared"), os.path.join(_here, "..", "shared")):
    if os.path.isdir(_cand):
        sys.path.insert(0, _cand)
sys.path.insert(0, os.path.dirname(__file__))

from band_harness import run_band_room

from specialists import triage, rootcause, fixauthor, reviewer


MISSION = (
    "Production just broke. As a room, find the root cause, draft a fix, have a "
    "RIVAL model adversarially review it, and never ship a high-risk deploy "
    "without a human EM sign-off. The transcript is the incident audit trail."
)


def build_specialists():
    return [
        triage.specialist(),
        rootcause.specialist(),
        fixauthor.specialist(),
        reviewer.specialist(),
    ]


async def main() -> None:
    await run_band_room(build_specialists(), MISSION)


if __name__ == "__main__":
    asyncio.run(main())
