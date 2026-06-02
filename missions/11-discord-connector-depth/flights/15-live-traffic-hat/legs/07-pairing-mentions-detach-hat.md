# Leg: pairing-mentions-detach-hat

**Status**: completed — interactive HAT PASS (2026-06-02). Closes #9; closes the deferred DM-isolation half of #5; re-verifies pairing UX + mentions-aware live. Surfaced a mission Known Issue (pairing→peers-narrowing lock-out).
**Flight**: [Live-Traffic HAT Capability](../flight.md)

## Results (2026-06-02, FD-guided + operator)

- **#9 Detach — PASS** (Chrome MCP on Studio connector detail): "Detach" on Connector Agent 2 removed it from ATTACHED AGENTS in place (no reload); grid badge 2→1; agent `connector_ids` cleared; **persisted across container restart**. Re-attached to restore.
- **DM-isolation (#5 deferred half) — PASS**: a real human DM (thenardier) resolved to its OWN session (`5d8e350c…`, DM channel `1511367089691033723`), distinct from the guild test-channel-1 session (`57df1bd3…`). "Channel of 1" confirmed.
- **Pairing UX — PASS**: unknown DM surfaced as a Chat-UI pending-approval banner (thenardier · "hello" · Approve/Dismiss); one-click **Approve** flipped the banner to an APPROVED badge in place; `pending_approvals` row → `approved`; peer added to `allowlist.peers`.
- **Mentions-aware re-verify (#12, live, UI-selected model) — PASS**: with `always_listen=true` + the per-connector inference model (`qwen2.5:7b`, selected via the F13 L4 UI dropdown), a substantive non-mention → `stepped` (inference-yes/engage); a trivial "lol" non-mention → `policy-silent`/`inference-no`. First live exercise of the UI-selected-model path since F13 L4.
- **FINDING → mission Known Issue (operator-confirmed filed):** approving thenardier appended them to `allowlist.peers`, which (empty→non-empty) flipped the peers axis from unrestricted to "only thenardier," denying the burner bots (and would deny all other users, channels included). Also the approval sets `dm_allowed=False` (F12 L3), so the approved peer's own DMs stay gated. Net over-restrict + under-grant. Removed thenardier (operator-confirmed) → `peers=[]` open.
- **Connector end state:** `ingest_bots=true`, `always_listen=false`, `dm_admission=admin-approved`, `peers=[]`, `routing=null`, both agents attached. thenardier removed.

## Objective

The interactive (FD-guided) HAT pass for the surfaces the automated bot driver cannot reach: close mission **#9** (detach an attached agent from the Connectors screen, end-to-end), verify the **DM-isolated session** ("channel of 1") deferred from L3/L4 (a Discord bot can't DM another bot, so a real human DM is required), exercise the **Discord-native pairing-approval** flow (unknown human DM → pending approval → one-click approve → admitted), and **re-verify mentions-aware** engagement under real traffic. Driven via Chrome MCP on the-one's own UI (localhost, no captcha) + a real human Discord account for the DM halves.

## Type

**Interactive HAT leg** — no autonomous Developer/Reviewer cycle. The FD drives the-one's UI via Chrome MCP and observes via the HTTP API / `docker logs`; the operator performs the human-Discord actions (DM from a real account, one-click approve). Steps are walked one at a time; failures are diagnosed + fixed inline, then re-verified. Committed when all steps pass.

## Environment

- Connector `58f1fe5a833f` ("Discord Constellation"), guild `1447766672441348150`, Connector Agent 1 + 2 attached. the-one UI at `http://localhost:8484`. Bot user id `1506767486002135280`.
- For pairing: `dm_admission` must be `admin-approved` (so an unknown DM surfaces as a pending approval rather than auto-admitting). It is currently `all` (set for the deferred L3 DM-topology test) — the FD flips it to `admin-approved` for the pairing steps and restores the connector to a sensible end state.
- For mentions-aware re-verify: `always_listen` true + the per-connector inference provider (Ollama `qwen2.5:7b`, already on the connector row) — the FD sets this for the mentions step and restores after.
- The operator has a **real human Discord account** (not a bot) that can DM the GleepGlorp bot.

## Verification Steps (walked one at a time)

| # | Surface | Action | Expected |
|---|---------|--------|----------|
| 1 | **Detach (#9)** | FD (Chrome MCP) opens the Connectors screen, opens the connector detail, clicks **detach** on Connector Agent 2. | The agent is removed from the connector's attached list WITHOUT a page reload; the grid/badge count drops 2→1. `[api]` `GET /api/connectors/58f1fe5a833f/attached-agents` no longer lists Connector Agent 2; the agent's `connector_ids` no longer contains the account. |
| 2 | **Detach — access revoked** | FD: a driver bot `@mention`s in a channel where ONLY the detached agent would have routed; OR confirm via API the detached agent is no longer eligible. | The detached agent no longer receives traffic (not in `eligible_attached_agents`); routing reflects only the remaining attached agent. |
| 3 | **Detach — persists across restart** | FD restarts the container; re-checks attached-agents. | Connector Agent 2 stays detached after restart (persisted to `agents.connector_ids`). |
| 4 | **Re-attach (restore)** | FD re-attaches Connector Agent 2 (so the connector returns to its pre-L7 2-agent state). | Both agents attached again. |
| 5 | **DM-isolation (deferred #5 half)** | Operator DMs the GleepGlorp bot from their human account (set `dm_admission` appropriately so the DM is admitted). | `[api]` The DM resolves to its OWN session — a distinct `channel_id` (the DM channel id), separate from any guild-channel session ("channel of 1", `_discord_translate.py:99`). |
| 6 | **Pairing-approval (Discord-native)** | FD sets `dm_admission=admin-approved`; operator DMs from an UNPAIRED/unknown human account. FD observes the Chat UI / pending-approvals surface. | The unknown DM surfaces as a **pending approval** (not auto-admitted). |
| 7 | **Pairing-approval — approve** | Operator (or FD via UI) one-click **approves** the pending peer. | The peer is admitted; a subsequent DM from that peer is delivered/engaged; the approval persists. |
| 8 | **Mentions-aware re-verify (#12, live)** | FD sets `always_listen=true`; a driver bot posts a substantive NON-mention question, then a trivial non-mention; (inference via Ollama). | The substantive message engages (`stepped`, inference-yes) and the trivial one stays silent (`policy-silent`, inference-no) — the F13 policy gate under real traffic. |
| 9 | **Restore** | FD restores the connector to a clean end state (re-attach done in #4; `dm_admission` + `always_listen` set to the operator's preferred daily-driver values). | Connector left in a sensible, operator-confirmed state. |

## Notes

- Steps 1–4 (detach) and 8 (mentions) the FD can largely drive alone (Chrome MCP on the-one UI + the bot driver). Steps 5–7 (DM-isolation + pairing) REQUIRE the operator's human Discord account (bots can't DM bots — Discord 50007).
- This leg closes mission **#9** and the deferred DM-isolation half of **#5**, and contributes the pairing + mentions-aware coverage toward **#11**. Pairing (#8) and mentions-aware (#12) were already closed earlier in M11; L7 re-verifies their live UX.
- Findings/bugs surfaced are fixed inline (spawn a Developer for code changes) then re-verified, per the interactive-HAT protocol.

## Post-Completion

- [ ] All steps pass (or deferred with rationale)
- [ ] Connector restored to a clean operator-confirmed state
- [ ] Update flight-log.md L7 entry with the run results
- [ ] Set status `completed`; check off in flight.md; close mission #9 (+ DM-isolation note on #5)
- [ ] Commit (interactive-HAT commits at leg end, per the workflow)
