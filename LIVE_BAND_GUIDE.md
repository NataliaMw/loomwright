# Running on the real Band platform

The offline `python demo.py` proves the choreography. This guide takes each project onto the live Band platform so the agents connect over WebSocket and coordinate in a real Band room — which is what you'll record for the "live" portion of a demo and what a judge sees if they inspect `band_agents.py`.

> Time budget: ~20–30 min for the first project, ~10 min for each after (the flow is identical).

---

## 0. One-time: account + free Pro month

1. Create a free account at **https://www.band.ai/** and join the [Band Discord](https://discord.com/invite/5YkNXmYfjk).
2. Redeem the hackathon Pro month: **Manage Billing → Pro plan → Add promotion code → `BANDHACK26`** → confirm it shows **100% off**. (Card may be required by the checkout flow; cancel before the next cycle if you don't continue.)
3. Get partner keys:
   - **AI/ML API** — claim $10 credits via the lablab coupon, key → `AIMLAPI_API_KEY`.
   - **Featherless** — follow the setup guide, promo `BOA26`, key → `FEATHERLESS_API_KEY`.

## 1. Register the agents on Band (per project)

Each specialist in a project is one **Remote Agent** on Band. For a project with agents `A, B, C, D`:

1. Band dashboard → **Agents** → **New Agent** → type **Remote Agent**.
2. Name it exactly the specialist handle (e.g. `Triage`, `RootCause`, …) and give it the one-line role from the project README.
3. On creation, **copy the API Key immediately** (shown once) and the **Agent UUID** (bottom-right of the agent settings page).
4. Repeat for every specialist. The human participant (EM / MedicalDirector / SecurityLead) is **you** — no agent needed; you'll join the room as yourself.

## 2. Fill credentials (per project)

```bash
cd <project>                      # e.g. cd rollback-room
cp .env.example .env
cp agent_config.example.yaml agent_config.yaml
```

Edit `.env`:
```
THENVOI_REST_URL=https://app.band.ai/
THENVOI_WS_URL=wss://app.band.ai/api/v1/socket/websocket
AIMLAPI_API_KEY=...          # orchestration / reasoning seats
FEATHERLESS_API_KEY=...      # the specialized OSS-model seat
OPENAI_API_KEY=...           # if any adapter defaults to an OpenAI client
ANTHROPIC_API_KEY=...        # for the Claude SDK / Anthropic adapter seats
```

Edit `agent_config.yaml` — one block per specialist handle (lowercased), matching the `config_key` in each `specialists/<name>.py`:
```yaml
triage:
  agent_id: "<uuid-from-band>"
  api_key: "<key-from-band>"
rootcause:
  agent_id: "..."
  api_key: "..."
# ...one block per agent
```

Both files are git-ignored — they never get committed.

## 3. Install and run

```bash
uv venv && source .venv/bin/activate     # or your usual venv
uv pip install -e .                       # pyproject pulls band-sdk[adapters] + framework deps
python band_agents.py                     # connects every specialist to Band and waits
```

You should see each agent log `Connected as: <name>`. Leave it running.

## 4. Drive the workflow in a Band room

1. Band dashboard → create a **new chat room** (name it the case id, e.g. `INC-4471` / `PA-2026-0613-91` / the offer id — the room IS the case file).
2. Add each registered agent as a participant (under **Remote**), and you are in the room as the human.
3. Post the kickoff message that @mentions the first agent — copy it from the project's `fixtures.py` (`KICKOFF_TEXT`):
   - Rollback Room → `@Triage` with the incident + suspect deploy.
   - PriorAuth Tribunal → `@IntakeAbstractor` with the prior-auth request.
   - Atlas → `@Atlas` with the signed offer.
4. Watch the agents @mention each other down the chain. When the workflow hits the human gate, **you** reply in the room (APPROVE / sign-off) — that's the un-bypassable escalation, live.

## 5. What to show on camera

The single beat per project that proves Band is the coordination layer (not a wrapper):

- **Rollback Room** — the Featherless reviewer model @mentions `@FixAuthor` back with a concrete defect, the author revises, then the high-risk deploy escalates to you (`@EM`) and you approve inline. Two different models argue and converge, then defer to a human.
- **PriorAuth Tribunal** — `@PolicyAnalyst` sends the case BACK to `@IntakeAbstractor` for the missing lab, then the `@Adjudicator` refuses to finalize a denial and forces you (`@MedicalDirector`) to sign off; the sealed record assembles from the thread.
- **Atlas** — `@Atlas` recruits the department agents into the room, `@Otto` publicly blocks on `@Sable`, and the prod-DB grant escalates to you (`@SecurityLead`) before IT/Finance can proceed.

## Troubleshooting

- **Agent doesn't respond** → it only wakes on an @mention; check the handle spelling matches the registered agent name exactly.
- **Auth/connection error** → re-check `agent_config.yaml` UUID/key pairing and that `.env` URLs are exact.
- **Want SDK debug logs** → set `logging.getLogger("thenvoi").setLevel(logging.DEBUG)` in `band_agents.py`; look for `[STREAM] on_tool_start: thenvoi_send_message` to confirm an agent is replying through Band.
- Docs: https://docs.band.ai (append `.md` to any page for clean markdown).
