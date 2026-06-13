# Rollback Room

> Prod breaks at 2am. Instead of one model quietly rubber-stamping its own
> hotfix, a *room* of specialist agents debates the root cause, drafts a fix,
> and a **rival model on a different provider** tries to break it. Anything with
> real blast radius can't ship until a human EM signs off — and no agent can
> route around that gate.

Built on **Band** (`band-sdk`, import root `thenvoi`): every specialist lives in
one shared chat room and hands work to the next by `@mention`. Only the
mentioned agent wakes. The `@mention` handoff *is* the workflow — Band is the
coordination layer, never a wrapper around a hidden pipeline.

## The problem — who feels the pain

On-call engineers and EMs. When a deploy starts bleeding 5xx, the temptation is
to let one LLM diagnose, patch, and approve in a single breath. That's exactly
how a confident-but-wrong hotfix ships: a single model agrees with itself, has
no adversary, and quietly skips the part where a human owns the risk on a
money-touching surface.

The bottleneck was never the patch — it's the *coordination*. You need a triage
voice, a root-cause voice, an author, an **independent** reviewer, and a human
with the authority to say "not on billing, not without me." Rollback Room makes
that handoff sequence the literal program, and forces the second opinion to come
from a genuinely different brain.

## Agent roster

| Agent | Framework | Role | Hands off to |
|-------|-----------|------|--------------|
| `@Triage` | Pydantic AI | Frames the firing alert + suspect deploy diff into a structured incident brief (severity, blast radius, hunks to inspect) | `@RootCause` |
| `@RootCause` | LangGraph | Argues exactly ONE root cause with `file:line` evidence and writes a precise fix spec | `@FixAuthor` |
| `@FixAuthor` | Codex (OpenAI-compatible) | Turns the spec into a real unified diff + regression test; revises when bounced | `@Reviewer` |
| `@Reviewer` | **Featherless OSS model** (a *different* model than `@FixAuthor`) | Adversarially tries to BREAK the fix; bounces weak diffs back; escalates high-risk surfaces | `@FixAuthor` / `@EM` |
| `@EM` | **human** | Rule-enforced approval for high-blast-radius deploys — no agent can skip it | — |

## How Band is the coordination layer

The whole incident is one readable thread of `@mention` handoffs. Three things
make Band the substrate and not decoration:

**1. The handoff sequence.** `oncall` opens the incident by `@mention`ing
`@Triage`. Triage frames it and `@mention`s `@RootCause`. RootCause posts one
diagnosis and `@mention`s `@FixAuthor`. FixAuthor posts a diff + test and
`@mention`s `@Reviewer`. Nobody polls; nobody is orchestrated by a parent
process. Each agent only wakes because it was named.

```
oncall ──@Triage──▶ @RootCause ──▶ @FixAuthor ──▶ @Reviewer
                                       ▲              │
                                       └─ bounce back ┘   (revise & re-check)
                                                      │
                                          high-risk surface
                                                      ▼
                                    ⛔ @EM (human gate — no agent can skip it)
                                                      │
                                                approve ──▶ ship
```

**2. The back-and-forth repair loop.** `@Reviewer` is a different model on a
different provider. On its first pass it *fails* the diff and `@mention`s
`@FixAuthor` BACK with concrete defects ("no regression test reproduces the
double-charge under client retry; missing rollback plan; clamp the TTL floor").
`@FixAuthor` revises and re-posts; `@Reviewer` re-checks. The bounce is real
state moving backward through the room, visible line-by-line in the transcript —
not a self-critique buried in one model's chain of thought.

**3. The rule-enforced human escalation.** The fix lands on `billing` /
`payments`. `@Reviewer` classifies that as high-risk and calls
`room.await_human("EM", ...)`, which *blocks the entire room* until a real person
replies. There is no code path that ships a high-risk deploy without that reply —
the gate is enforced by the harness, not by a prompt asking the agent to please
behave.

## The killer demo moment

Two different models argue and converge in one visible thread. `@FixAuthor`
(orchestration model via AI/ML API) writes a confident hotfix. `@Reviewer` (a
rival OSS model on Featherless) `@mention`s it back — *"you dropped the retry
guard / no test reproduces the double-charge"* — the author revises, the reviewer
re-reads and concedes the **logic** is now sound. Only then does it flag the
**blast radius** and auto-escalate to the human `@EM`, Dana, who approves inline:

> *"APPROVE. I own the risk on billing for INC-4471 — the TTL restore is the
> smallest safe change and we're actively double-charging. Ship it behind the
> checkout-idempotency flag and page me if burn rate doesn't drop in 10m. — Dana, EM"*

The room then assembles its own audit artifact from the transcript: incident,
service, number of author↔reviewer bounces, the human gate, and the full handoff
chain. The transcript *is* the post-mortem.

## Partner-prize usage

- **AI/ML API** (OpenAI-compatible, `https://api.aimlapi.com/v1`) drives the
  orchestration / reasoning roles: `@Triage`, `@RootCause`, and `@FixAuthor`.
- **Featherless** (OpenAI-compatible, `https://api.featherless.ai/v1`) runs the
  lone OSS specialist `@Reviewer` on a *deliberately different* model. Using a
  different provider AND a different model is the entire point: the adversarial
  review has to be a real second brain, not the author grading its own homework.

`models.py` returns the right client per role from env keys and falls back to a
deterministic canned client when keys are absent — so the offline demo always
runs with zero credentials.

## Run it

### Offline demo — no credentials, deterministic (this is the video)
```bash
python demo.py
```
Replays the full incident against a local Band room and prints the audit
artifact. Byte-for-byte reproducible, so it replays cleanly on camera.

### Live Band room
```bash
cp .env.example .env
#   AIMLAPI_API_KEY=...        (redeem partner credits with promo code BANDHACK26)
#   FEATHERLESS_API_KEY=...    (redeem partner credits with promo code BANDHACK26)

cp agent_config.example.yaml agent_config.yaml
#   fill agent_id + api_key for each handle (triage / rootcause / fixauthor / reviewer)

python band_agents.py
```
Then drive the room by `@mention`ing `@Triage` from the Band UI. Each agent
hands off down the chain on its own — coordination is the conversation.

## Signature touch — from Natalia Mawyin

I've shipped enough 2am hotfixes to distrust the confident ones. The detail I
care about most here isn't the model — it's that **Dana, the EM, owns the risk by
name**, and the room *cannot* lie to her by skipping the gate. The room signs its
own audit trail: *"the Rollback Room — no high-risk deploy ships without a
human."* Coordination you can read top-to-bottom is the whole point. — N.M.
