"""
band_harness — a thin, batteries-included wrapper over the Band SDK (`thenvoi`)
shared by every project in this hackathon.

Band is the coordination layer: agents live in chat rooms and hand work off to
each other by @mentioning the next specialist. This module gives every project
one consistent way to:

  * spin up a Band-connected agent from any framework adapter,
  * write a specialist's system prompt so it reliably @mentions the next agent,
  * fall back to a fully local "simulator" room when no Band credentials are
    present, so the system is demoable and testable offline.

Nothing here hides Band — it makes the @mention handoff the obvious thing to do.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

try:
    from thenvoi import Agent
    from thenvoi.config import load_agent_config
    _HAS_BAND = True
except ImportError:
    Agent = None
    load_agent_config = None
    _HAS_BAND = False


REST_URL = os.getenv("THENVOI_REST_URL", "https://app.band.ai/")
WS_URL = os.getenv("THENVOI_WS_URL", "wss://app.band.ai/api/v1/socket/websocket")


@dataclass
class Specialist:
    """One agent in a Band room: a name, the role it plays, and who it hands off to."""

    handle: str
    role: str
    adapter_factory: Callable[[], Any]
    hands_off_to: list[str] = field(default_factory=list)
    config_key: Optional[str] = None

    def system_prompt(self, mission: str) -> str:
        handoff = ""
        if self.hands_off_to:
            targets = ", ".join(f"@{h}" for h in self.hands_off_to)
            handoff = (
                f"\n\nWhen your part is done, hand off by @mentioning the next "
                f"specialist ({targets}) in the room with the structured result "
                f"they need. Do not do their job — pass them the context and let "
                f"them own their step. If you need work redone, @mention the "
                f"agent who produced it and say exactly what to fix."
            )
        return (
            f"You are @{self.handle}, the {self.role}.\n\n{mission}\n\n"
            f"You collaborate with other agents inside a shared Band room. You only "
            f"see messages that @mention you. Keep responses tight and structured — "
            f"the room transcript is the audit trail.{handoff}"
        )


def make_band_agent(spec: Specialist, mission: str):
    """Create a live Band-connected agent for a specialist. Requires `thenvoi`."""
    if not _HAS_BAND:
        raise RuntimeError(
            "thenvoi SDK not installed. Run `uv add band-sdk[<adapter>]`, or use "
            "run_local_room() for an offline demo."
        )
    config_key = spec.config_key or spec.handle.lower()
    agent_id, api_key = load_agent_config(config_key)
    adapter = spec.adapter_factory()
    if hasattr(adapter, "custom_section") and not getattr(adapter, "custom_section", None):
        adapter.custom_section = spec.system_prompt(mission)
    return Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=WS_URL,
        rest_url=REST_URL,
    )


async def run_band_room(specialists: list[Specialist], mission: str) -> None:
    """Connect every specialist to Band and run them until interrupted.

    In a real Band room you add these agents as participants from the Band UI (or
    via the recruit platform-tool) and drive the workflow by @mentioning the first
    agent. Each agent then @mentions the next one — coordination IS the conversation.
    """
    agents = [make_band_agent(s, mission) for s in specialists]
    await asyncio.gather(*(a.run() for a in agents))


# --------------------------------------------------------------------------- #
# Offline simulator: same @mention handoff semantics, no network. This is what
# makes every project runnable + testable without Band credentials, and lets the
# demo script replay a deterministic transcript on camera.
# --------------------------------------------------------------------------- #

@dataclass
class RoomMessage:
    sender: str
    mentions: list[str]
    text: str
    payload: dict[str, Any] = field(default_factory=dict)


class LocalRoom:
    """A faithful local stand-in for a Band chat room.

    Messages carry @mentions; only mentioned specialists are woken. Each specialist
    is an async handler `(room, message) -> None` that reads the message and posts
    its own (which may @mention the next specialist, or @mention a human and pause).
    The transcript is the audit trail — the same property the real Band room has.
    """

    def __init__(self) -> None:
        self.transcript: list[RoomMessage] = []
        self._handlers: dict[str, Callable[["LocalRoom", RoomMessage], Awaitable[None]]] = {}
        self._humans: set[str] = set()
        self._human_gate: Optional[asyncio.Future] = None

    def join(self, handle: str, handler: Callable[["LocalRoom", RoomMessage], Awaitable[None]]) -> None:
        self._handlers[handle] = handler

    def join_human(self, handle: str) -> None:
        self._humans.add(handle)

    async def post(self, sender: str, text: str, mentions: Optional[list[str]] = None,
                   payload: Optional[dict] = None) -> None:
        msg = RoomMessage(sender=sender, mentions=mentions or [], text=text, payload=payload or {})
        self.transcript.append(msg)
        self._render(msg)
        for target in msg.mentions:
            if target in self._humans:
                continue  # humans reply via human_reply(), not auto-dispatch
            handler = self._handlers.get(target)
            if handler:
                await handler(self, msg)

    async def await_human(self, handle: str, prompt_text: str) -> "RoomMessage":
        """A rule-enforced escalation: pause until the named human replies in-room."""
        self.transcript.append(
            RoomMessage(sender="system", mentions=[handle],
                        text=f"⛔ ESCALATION — awaiting @{handle}: {prompt_text}")
        )
        self._render(self.transcript[-1])
        self._human_gate = asyncio.get_event_loop().create_future()
        return await self._human_gate

    async def human_reply(self, handle: str, text: str, payload: Optional[dict] = None) -> None:
        msg = RoomMessage(sender=handle, mentions=[], text=text, payload=payload or {})
        self.transcript.append(msg)
        self._render(msg)
        if self._human_gate and not self._human_gate.done():
            self._human_gate.set_result(msg)

    def _render(self, msg: RoomMessage) -> None:
        mention_str = " ".join(f"@{m}" for m in msg.mentions)
        prefix = f"  {mention_str}" if mention_str else ""
        print(f"┃ {msg.sender:>18} ▸{prefix} {msg.text}")
