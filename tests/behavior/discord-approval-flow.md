# Behavior Test: Discord unknown-DM → approve → respond flow

**Slug**: `discord-approval-flow`
**Status**: active
**Created**: 2026-06-03
**Last Run**: 2026-06-03-16-03-44 (pass — flow validated end-to-end; step 7 inconclusive on a UI-freshness gap (F4), fixed + re-run pass)

## Intent

Validate the F17 DM/approval cluster (Legs **D** dm-allowlist-simplify, **E** approval-pending-signaling, **F** respond-on-approval) end-to-end against the real Discord platform + the the-one UI. An unknown user (Chuck R) DMs the bot → gets a "you're pending" auto-reply (E) → the operator sees a nav badge + a left-panel pending entry (E) → approves in one step, no `dm_allowed` toggle (D) → the bot proactively **answers Chuck R's original question** (F). This is a multi-component, real-environment flow (Discord ↔ the-one ↔ agent) that unit tests can't cover; it needs two live surfaces driven by an agent.

## Preconditions

- the-one running; the "Discord Constellation" connector **connected/warm** with the Sonos agent attached. **Which instance**: a warm Discord gateway session is tied to whichever the-one instance the operator's bot token is configured on — this is infrastructure the operator controls, not something this run spins up fresh. If that happens to be the operator's persistent `:8484` instance, that is an explicit operator decision made with full awareness (this spec mutates real Discord state regardless), never a default this spec assumes. Prefer a dedicated non-default-port instance with its own bot/connector configuration where one exists.
- The connector's Direct Messages policy = **"Only these people"** (`dm_admission=admin-approved`), and **Chuck R is NOT currently in the Direct Messages list** (so he is an unknown sender). *(Operator removes him first if present.)*
- Chrome MCP available, driving BOTH: (a) the the-one Studio/Chat UI (base URL per the operator's stated instance above — this spec's Steps literally write `http://localhost:8484`; treat that as a placeholder for the actual instance, not a literal instruction), and (b) a Discord **web client logged in as Chuck R** (operator keeps that session live).
- Chuck R can reach the bot's DM (has DM'd it before / shares a server).
- **Credential**: the the-one instance is gated (Mission 20 Flight 1). Reach it per
  CLAUDE.md's "Behavior-test credential convention" — a handoff-authenticated navigation
  for the browser session (single-use; re-mint per navigation).

## Observables Required

- browser (the-one UI DOM + the Discord web-client DOM — both measured via chrome-devtools).

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | (Setup) Confirm Chuck R is removed from the connector's Direct Messages list and the policy is "Only these people". | (setup row — no judgment) |
| 2 | In the Discord web client (as Chuck R), open the bot's DM and send a real question, e.g. "hey, what can you help me with?". | Within ~25s, Chuck R receives an **auto-reply** in the DM indicating his message is **awaiting the operator's approval** (e.g. "…waiting for the operator to approve you…"). The bot does **NOT** answer the question yet. [E] |
| 3 | (Setup) Wait ~3s for the the-one badge poll. | (setup — allow the 10s poll to fire) |
| 4 | In the the-one UI (any screen), observe the top-nav **Chat** button (`nav-chat-btn` / `nav-pending-badge`); then open Chat and observe the left panel. | The Chat nav button shows a **notification badge** with a count ≥1 [E]; the Chat **left panel shows a "Pending approvals" section** (`pending-approvals-section`) listing Chuck R [E]. |
| 5 | In the the-one UI, **approve** Chuck R's pending approval (click Approve on his pending entry/banner). | Approval succeeds; the pending badge **decrements / clears**; Chuck R is added to the Direct Messages list. [E/D] |
| 6 | (Wait) Allow ~30s for the approve→re-dispatch→agent.step→Discord send. | (wait point) |
| 7 | In the Discord web client (as Chuck R), observe the DM. | Within ~30s of approval, the bot **proactively sends a substantive reply that ANSWERS Chuck R's original question** (not just a greeting) — closing the loop. [F] |
| 8 | In the the-one UI, open the connector editor → the **Direct Messages** section. | The section is labeled **"Direct Messages"**; Chuck R is listed; there is **NO per-peer "DM allowed" checkbox** [D]; the policy control offers **No one / Only these people / Anyone**. |

**Row conventions:** Discord-side steps (2, 7) read the Discord web DOM as Chuck R; the-one-side steps (4, 5, 8) read the the-one DOM. Steps 3, 6 are wait points.

## Out of Scope

- The editor-cluster surfaces (live status, intents, Additional Config) — see `connector-editor-ux`.
- Guild-channel admission (F16) and per-agent routing (F15 L4) — unrelated to this DM flow.
- Apparatus risk: driving the Discord **web** DOM can be finicky (dynamic DOM); if Chrome MCP can't reliably read/drive the Discord web client, the mission permits a `discord.py`-as-Chuck-R fallback (Chuck R must be a real *user* account — bots can't DM bots).
