# 🧵 Loomwright

### the room that engineers the loop, then runs it

> **Live demo:** https://nataliamw.github.io/loomwright/ — two tasks, two different loops, side by side.
> **Run it offline in 10 seconds (no keys):** `python demo.py`
>
> **Band of Agents Hackathon · Track 2 — Multi-Agent Software Development**

---

## The shift this is built on

In June 2026, Addy Osmani and Boris Cherny (the creator of Claude Code) put a name
to where agentic coding is going: **loop engineering**. The skill is no longer
writing the perfect prompt — it's designing the *loop* the agent runs inside:
generate → check → revise, until a real exit condition holds. As Peter Steinberger
put it in a post that hit 6.5M views eleven days before this hackathon's deadline:

> *"You shouldn't be prompting coding agents anymore. You should be designing loops
> that prompt your agents."*

There's a catch nobody's solved yet: **building the loop is still manual, expert
work** — and every coding-agent tool ships the *same* loop for everything. A CSS
tweak and a database migration get the identical Planner→Coder→Reviewer pipeline.
That's vibe coding with extra steps.

**Loomwright closes that gap.** It's a Band room where agents *engineer the loop for
the specific task*, then *run it* — and pull in the specialists that task needs, on
demand. Loop engineering, done by a band of agents instead of by hand.

And the loop is **real**: the checks don't fake pass/fail from a fixture — they
execute the generated Python in a sandboxed subprocess. A buggy revision genuinely
fails with an `AssertionError`, the loop genuinely bounces, and the fix (written by a
live AI/ML API model when keys are present, or a deterministic fallback when they're
not) only ships once it *actually passes the tests*.

## What it does (in one run)

`python demo.py` feeds the room two different tasks and you watch it build two
different loops:

| | **Task A — bugfix** (pure function) | **Task B — auth change** (high-stakes) |
|---|---|---|
| signature gate | a **repro-test** (fails before, passes after) | an **acceptance-test**, end to end |
| critics | one standing rival reviewer | rival reviewer **+ a SecurityCritic recruited on demand** |
| max revisions | 2 (tight) | 3 |
| human gate | none | **a TechLead must sign before it ships** |

Same room. Same agents. **Different loop** — because the loop is engineered for the
task, not copy-pasted. That difference is the entire point.

## How Band is the coordination layer (not a wrapper)

Three agents, two phases, all on one Band room transcript:

**Phase 1 — design the loop**
- **@LoopArchitect** (Pydantic AI) reads the task and proposes a loop: which checks
  gate it, which critics vote, when it may stop, whether a human must sign.
- **@LoopCritic** (LangGraph) *attacks the proposed exit condition* before any code
  is written — "this is gameable", "this surface needs a security critic" — and
  **recruits that specialist into the room on demand** via Band's add-participant
  tool (`band_add_participant`). This is the most Band-native moment in the system:
  the room decides, at runtime, that it needs a voice nobody added up front, and
  adds it.

**Phase 2 — run the loop**
- **@LoopRunner** (Pydantic AI) executes the assembled loop: generate a revision
  (live via **AI/ML API** when keyed), let every critic (including the recruited one)
  attack it, **really run the required checks in a subprocess** (`qa.py`), and decide
  — stop, revise again, or pause for the human gate. Each revision is a real
  `@mention` bounce in the room, and **@QA posts the real ✅/❌ results** into it.

Take Band out and this is impossible: the loop's *design* and its *execution* live
on the **same audit trail**, so you can read the loop a room built before you trust
the code it produced. The transcript *is* the record of both.

```
user ──"new task"──▶ @LoopArchitect ──proposes loop──▶ @LoopCritic
                                                          │
                              band_add_participant ◀──────┤ (recruits @SecurityCritic
                                                          │  when the task is high-stakes)
                                                          ▼
                                                     @LoopRunner
                                          generate → critics attack → revise → re-check
                                                          │
                                              ⛔ human gate (high-stakes only)
                                                          ▼
                                       verified code + the LoopSpec that produced it
```

## Why it fits the rubric

- **Application of Technology** — Band is load-bearing in two distinct ways: dynamic
  **recruitment** (the room grows its own membership to fit the task) and a visible
  **design-then-execute** handoff chain, all as `@mention` routing on one trail.
- **Originality** — nobody else turns *loop engineering itself* into the multi-agent
  product. Every other Track-2 entry runs a fixed pipeline; Loomwright **synthesizes
  the pipeline per task**. The thing it generates is the artifact (`LoopSpec`).
- **Business Value** — the failure mode of agentic coding is confident-but-wrong code
  shipping because the loop's exit condition was too weak. Loomwright makes the loop
  *inspectable and task-appropriate*, with a human gate where the stakes demand one.
- **Presentation** — the whole thesis is one screen: two tasks, two loops, side by
  side, with the difference highlighted. Open the transcript to see it happen.

## Architecture

| File | Role |
|---|---|
| `loopspec.py` | the `Task` and `LoopSpec` — the inspectable loop artifact |
| `qa.py` | **real QA** — executes generated code + tests in a sandboxed subprocess |
| `tasks.py` | concrete tasks with real buggy/fixed code + tests the loop runs |
| `specialists/architect.py` | **@LoopArchitect** — proposes a loop for the task |
| `specialists/critic.py` | **@LoopCritic** — attacks it, recruits specialists on demand |
| `specialists/runner.py` | **@LoopRunner** — runs generate→(real QA)→revise to the exit condition |
| `shared/band_harness.py` | thin Band wrapper + offline `LocalRoom` with `recruit()` |
| `demo.py` | deterministic two-task demo (zero credentials) |
| `band_agents.py` | live Band path (`thenvoi` SDK + credentials) |
| `docs/` | the self-contained web viewer (GitHub Pages) |

## Run it

**Offline, deterministic, no credentials** (this is what's on video):
```bash
python demo.py
```

**Rebuild the web view from a real run:**
```bash
python docs/build_data.py   # regenerates docs/data.json + docs/index.html
```

**Live, on Band** (cross-framework agents over real rooms — *verified working*):
```bash
cp .env.example .env                      # add AIMLAPI_API_KEY + FEATHERLESS_API_KEY
cp agent_config.example.yaml agent_config.yaml   # add Band agent_id/api_key per agent
pip install "band-sdk[pydantic-ai,langgraph]" python-dotenv pyyaml
python band_agents.py                     # connects all 6 agents to Band over WebSocket
```
Then in a Band room, add the six agents and `@mention @LoopArchitect` with a task.
This has been run for real: the six agents register on the Band platform, connect
over WebSocket, and coordinate a task end-to-end through `@mention` handoffs in a
live room — LoopArchitect → LoopCritic → LoopRunner → CodeAuthor → QAEngineer →
RivalReviewer, all on the Band transcript.

## Tech

- **Band** (`thenvoi`) — the coordination layer: rooms, `@mention` routing, on-demand
  recruitment.
- **Cross-framework agents** — Pydantic AI (Architect, Runner) + LangGraph (Critic).
- **AI/ML API** — orchestration/reasoning roles. **Featherless** — the rival OSS model
  behind the critics, deliberately a different provider so critique isn't theater.
- **No build step for the demo** — the loop's control flow is deterministic, so the
  recording is byte-for-byte reproducible and doesn't depend on a live model.

---

MIT. Built by [Natalia Mawyin](https://github.com/NataliaMw) — because the loop
deserves to be engineered, not copy-pasted.
