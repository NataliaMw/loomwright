"""The LoopSpec — the artifact Loomwright exists to produce.

Loop engineering (Osmani / Cherny, June 2026) says the unit of agentic coding is
no longer the prompt — it's the *loop*: act, observe, decide, repeat until a real
exit condition holds. Today people hand-design those loops. Loomwright has a room
of agents design one per task, on demand, then run it.

A LoopSpec is that design made inspectable: which checks gate the work, which
critics get a vote, when the loop is allowed to stop, and who has to sign before
anything ships. It is deliberately small and declarative — you can read the whole
loop a room built before you trust the code it produced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Task:
    """What the user wants built. The room reads this to decide the loop shape."""

    title: str
    description: str
    touches: list[str] = field(default_factory=list)  # surfaces: auth, ui, db, ...
    kind: str = "feature"  # bugfix | refactor | feature | migration

    @property
    def high_stakes(self) -> bool:
        risky = {"auth", "billing", "payments", "migration", "schema", "pii"}
        return bool({t.lower() for t in self.touches} & risky)


@dataclass
class Check:
    """One gate in the loop. The loop cannot exit while a required check fails."""

    name: str
    why: str
    required: bool = True

    def line(self) -> str:
        tag = "required" if self.required else "advisory"
        return f"{self.name} ({tag}) — {self.why}"


@dataclass
class Critic:
    """An agent voice that reviews each revision. Recruited only if the task needs it."""

    handle: str
    lens: str
    recruited_on_demand: bool = False


@dataclass
class LoopSpec:
    """A task-specific loop the room assembled. This is the headline artifact."""

    task: Task
    checks: list[Check] = field(default_factory=list)
    critics: list[Critic] = field(default_factory=list)
    max_revisions: int = 3
    exit_condition: str = "all required checks pass"
    human_gate: Optional[str] = None  # handle of the human who must sign, or None
    rationale: list[str] = field(default_factory=list)  # why the room chose this shape

    def required_checks(self) -> list[Check]:
        return [c for c in self.checks if c.required]

    def fingerprint(self) -> str:
        """A short signature of the loop's shape — lets a demo prove two tasks
        produced two *different* loops at a glance."""
        checks = ",".join(c.name for c in self.checks)
        critics = ",".join(c.handle for c in self.critics)
        gate = self.human_gate or "none"
        return f"checks=[{checks}] critics=[{critics}] max_rev={self.max_revisions} gate={gate}"

    def render(self) -> str:
        lines = [
            f"LOOP for: {self.task.title}  ({self.task.kind})",
            f"  exit when : {self.exit_condition}  (max {self.max_revisions} revisions)",
            f"  human gate: {self.human_gate or 'none required'}",
            "  checks:",
        ]
        for c in self.checks:
            lines.append(f"    - {c.line()}")
        lines.append("  critics:")
        for c in self.critics:
            how = "recruited on demand" if c.recruited_on_demand else "standing"
            lines.append(f"    - @{c.handle} [{c.lens}] ({how})")
        if self.rationale:
            lines.append("  why this shape:")
            for r in self.rationale:
                lines.append(f"    · {r}")
        return "\n".join(lines)
