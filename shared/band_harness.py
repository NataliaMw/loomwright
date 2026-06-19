"""
band_harness — a thin, batteries-included wrapper over the Band SDK (`band`,
v1.0.0; the old `thenvoi` package/import is deprecated).

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
    from band import Agent
    from band.config import load_agent_config
    _HAS_BAND = True
except ImportError:
    Agent = None
    load_agent_config = None
    _HAS_BAND = False


# v1.0.0 reads BAND_*; we still honor the old THENVOI_* names as a fallback.
REST_URL = os.getenv("BAND_REST_URL") or os.getenv("THENVOI_REST_URL", "https://app.band.ai/")
WS_URL = (os.getenv("BAND_WS_URL") or os.getenv("THENVOI_WS_URL")
          or "wss://app.band.ai/api/v1/socket/websocket")


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
            primary = self.hands_off_to[0]
            targets = ", ".join(f"@natalia/{h.lower()}" for h in self.hands_off_to)
            handoff = (
                f"\n\nHANDOFF RULE (critical): you are one step in a chain. Do your "
                f"step in 1–2 short sentences, then on the SAME message END with an "
                f"@mention of the next agent: {targets}. Default next agent is "
                f"@natalia/{primary.lower()}. Do NOT reply to the human and do NOT try "
                f"to do the whole task yourself — your only job is your step plus the "
                f"@mention handoff. The message is not done until it ends with that "
                f"@mention."
            )
        return (
            f"You are @{self.handle}, the {self.role}.\n\n{mission}\n\n"
            f"You collaborate with other agents inside a shared Band room. Keep "
            f"responses tight — the room transcript is the audit trail.{handoff}"
        )


def make_band_agent(spec: Specialist, mission: str):
    """Create a live Band-connected agent for a specialist. Requires `band`."""
    if not _HAS_BAND:
        raise RuntimeError(
            "Band SDK not installed. Run `uv add band-sdk[<adapter>]` (import root "
            "is `band` as of v1.0.0), or use the offline LocalRoom demo."
        )
    config_key = spec.config_key or spec.handle.lower()
    agent_id, api_key = load_agent_config(config_key)
    adapter = spec.adapter_factory()
    # Always inject our choreography so the live agent actually hands off, instead
    # of replying to the human with a generic auto-generated prompt.
    if hasattr(adapter, "custom_section"):
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
        self.recruited: list[str] = []
        self._recruiters: dict[str, Callable[[str], Callable[["LocalRoom", RoomMessage], Awaitable[None]]]] = {}
        self._auto_human: dict[str, str] = {}

    def join(self, handle: str, handler: Callable[["LocalRoom", RoomMessage], Awaitable[None]]) -> None:
        self._handlers[handle] = handler

    def register_recruitable(self, handle: str,
                             factory: Callable[[str], Callable[["LocalRoom", RoomMessage], Awaitable[None]]]) -> None:
        """Make a specialist available to be pulled in later via recruit() — the
        local stand-in for Band's band_add_participant platform tool."""
        self._recruiters[handle] = factory

    async def recruit(self, handle: str, lens: str = "") -> None:
        """Pull a specialist into the room at runtime (models band_add_participant).

        This is coordination the room decides on its own: an agent realizes the
        task needs a voice nobody added up front, and adds it. Only registered
        recruitable specialists can be summoned; the act is logged to the trail."""
        if handle not in self.recruited:
            self.recruited.append(handle)
        factory = self._recruiters.get(handle)
        if factory and handle not in self._handlers:
            self._handlers[handle] = factory(lens)
        self.transcript.append(
            RoomMessage(sender="system", mentions=[handle],
                        text=f"➕ recruited @{handle} into the room on demand "
                             f"({lens or 'specialist'}) — band_add_participant")
        )
        self._render(self.transcript[-1])

    def join_human(self, handle: str, auto_reply: Optional[str] = None) -> None:
        """Add a human participant. In a live Band room the human replies in chat;
        for a deterministic demo, pass auto_reply and the gate resolves with it."""
        self._humans.add(handle)
        if auto_reply is not None:
            self._auto_human[handle] = auto_reply

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
        if handle in self._auto_human:
            reply = RoomMessage(sender=handle, mentions=[], text=self._auto_human[handle],
                                payload={"decision": "auto"})
            self.transcript.append(reply)
            self._render(reply)
            return reply
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
