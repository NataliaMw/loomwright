# Running Loomwright on the real Band platform

The offline `python demo.py` proves the choreography. This guide takes Loomwright onto the live Band platform so the agents connect over WebSocket and coordinate in a real Band room — which is what you'll record for the "live" portion of a demo and what a judge sees if they inspect `band_agents.py`.

> Time budget: ~20–30 min.
>
> **Loomwright agents:** `LoopArchitect`, `LoopCritic`, `LoopRunner` (Remote Agents), plus `SecurityCritic` / `A11yCritic` which the room recruits on demand, and a human `TechLead` (you) for the high-stakes gate.

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
2. Name it exactly the specialist handle (`LoopArchitect`, `LoopCritic`, `LoopRunner`, and the recruitable `SecurityCritic` / `A11yCritic`) and give it the one-line role from the README.
3. On creation, **copy the API Key immediately** (shown once) and the **Agent UUID** (bottom-right of the agent settings page).
4. Repeat for every specialist. The human participant (`TechLead`) is **you** — no agent needed; you'll join the room as yourself for the high-stakes gate.

## 2. Fill credentials (per project)

```bash
cd loomwright
cp .env.example .env
cp agent_config.example.yaml agent_config.yaml
```

Edit `.env`:
```
THENVOI_REST_URL=https://app.band.ai/
THENVOI_WS_URL=wss://app.band.ai/api/v1/socket/websocket
AIMLAPI_API_KEY=...          # @LoopArchitect + @LoopRunner reasoning seats
FEATHERLESS_API_KEY=...      # the rival OSS-model seat behind the critics
OPENAI_API_KEY=...           # if any adapter defaults to an OpenAI client
```

Edit `agent_config.yaml` — one block per specialist handle (lowercased), matching the `config_key` in each `specialists/<name>.py`:
```yaml
architect:
  agent_id: "<uuid-from-band>"
  api_key: "<key-from-band>"
critic:
  agent_id: "..."
  api_key: "..."
runner:
  agent_id: "..."
  api_key: "..."
# ...plus securitycritic / a11ycritic for the recruitable seats
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

1. Band dashboard → create a **new chat room** (the room IS the task's record).
2. Add `LoopArchitect`, `LoopCritic`, `LoopRunner` as participants (under **Remote**); you are in the room as `TechLead`. Leave `SecurityCritic` / `A11yCritic` out — the room recruits them itself.
3. Post a task that @mentions the first agent, e.g.:
   - `@LoopArchitect new task: Add SSO token refresh to the login flow — rotate refresh tokens; touches auth and sessions.`
4. Watch the loop get built then run: the Architect proposes, the Critic attacks it and **recruits `@SecurityCritic` into the room** because the task touches auth, the Runner bounces revisions past the critics, and the high-stakes gate escalates to you (`@TechLead`) — reply `APPROVE` inline.

## 5. What to show on camera

The single beat that proves Band is the coordination layer (not a wrapper):

**Run two tasks back to back and show the loops differ.** First a bugfix
(`@LoopArchitect fix off-by-one in pagination offset`) — a tight loop, no human gate.
Then the auth task above — and on camera, the moment `@LoopCritic` says *"no security
critic on a sensitive surface"* and **recruits `@SecurityCritic` into the room at
runtime** (`band_add_participant`), followed by the `@TechLead` gate you approve
inline. Same room, same agents, **two different loops** — the loop was engineered for
the task, live, through Band. (The live demo page shows the same two loops side by
side: https://nataliamw.github.io/loomwright/)

## Troubleshooting

- **Agent doesn't respond** → it only wakes on an @mention; check the handle spelling matches the registered agent name exactly.
- **Auth/connection error** → re-check `agent_config.yaml` UUID/key pairing and that `.env` URLs are exact.
- **Want SDK debug logs** → set `logging.getLogger("thenvoi").setLevel(logging.DEBUG)` in `band_agents.py`; look for `[STREAM] on_tool_start: thenvoi_send_message` to confirm an agent is replying through Band.
- Docs: https://docs.band.ai (append `.md` to any page for clean markdown).
