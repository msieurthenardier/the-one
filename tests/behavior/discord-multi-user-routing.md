# Behavior Test: Discord Multi-User Routing + Peer-Name Attribution (F15)

**Slug**: `discord-multi-user-routing`
**Status**: draft
**Created**: 2026-06-01
**Last Run**: never

## Intent

Verify that when ≥3 distinct Discord senders post into one channel served by the-one's bot, they all resolve to ONE shared channel-scoped session (sessions key on the `(platform, connector_id, channel_id, thread_id)` 4-tuple — `peer_id` is excluded — so a shared channel is one conversation), the F6 per-user ACL overlays admit/deny correctly under real traffic, each reply routes to the right agent, and the Chat UI renders each message attributed to the right `discord-username` rather than an anonymous "peer message" (mission criteria #5 and #13). A DM from a sender, by contrast, resolves to its OWN session — a "channel of 1" (`channel_id = message.channel.id`, unique per user-pair). This needs a behavior test, not a unit test, because it exercises the live multi-sender path end-to-end: real gateway events from distinct authors, the dispatcher resolving the shared session, the ACL resolver intersecting account-scope and per-agent overlays against real peer ids, and the operator-console attribution rendering — no unit can stand in for concurrent real senders plus the human-perceivable attribution surface. The "who said what" attribution within the shared session is itself the observable.

The three senders are driven by the committed `tests/live/discord_hat/` multi-bot driver (three burner bot tokens; the target connector runs with `ingest_bots=true`; distinct burner author ids → distinct peers). The operator-console attribution is observed via Chrome MCP. A `[mixed-frame]` session-detail probe distinguishes correct routing from coincidentally-correct replies where the channel surface alone can't.

## Preconditions

- The the-one container is running; the connector worker is up; L1's stdout connector logging is active (so a failed routing step is diagnosable from `docker logs`).
- A dedicated test connector is configured with `ingest_bots=true`, the test guild on `allowlist.guilds`, and the test channel allowlisted. `always_listen=true` (account + per-agent) is set as a fallback, but the driver engages the bot via `@mention` (see below) so the engagement-inference is NOT in the path — routing, not the policy gate, is the variable under test.
- **Engagement mechanism:** every routing-scenario message from a burner bot `@mentions` the-one's bot. The mention path engages the agent deterministically (outcome=`mention`) with NO inference call — `is_mention` checks the bot's id in `message.mentions` independent of author, so a burner-bot mention registers. This avoids the engagement-inference (strongly biased to silence) confounding a routing test. If the L3 smoke shows bot-authored mentions don't register, fall back to `always_listen=true` + substantive direct messages crafted to clear the inference "yes" bar.
- Three burner Discord bot applications are provisioned, their tokens available to the driver via env, all three invited to the test guild with the **Message Content privileged intent** (without it their posts arrive empty-text). The burner bots are posting-only and never auto-reply (prevents an `ingest_bots` feedback loop).
- At least two agents are attached to the test connector, with per-user ACL overlays configured such that the three burner-bot peers have a known, distinct admit/deny matrix (so the test can assert an overlay denies at least one (agent, peer) pair).
- A local Ollama inference provider is configured (so any inference path runs without external rate limits).
- The operator is logged into the-one's Chat UI in the Chrome MCP browser session, viewing the connector-attached session(s).
- The bot-peer-equivalence premise (L3) has been confirmed — burner bots resolve to peers identically to human senders.

## Observables Required

- browser (the-one Chat UI rendered state — attribution in the unified history; measured via chrome-devtools MCP)
- filesystem / API (`[mixed-frame]` — the-one session detail via `GET /api/chat/sessions/{id}` including `session_metadata["routing"]`, or the routing-audit panel; used where the channel/UI surface alone can't distinguish which peer routed to which session)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Run the driver's `smoke` scenario: burner bot A posts a message that `@mentions` the-one's bot in the test channel; await the-one bot's reply. | Within the driver's timeout, the-one's bot replies in the channel. A `[mixed-frame]` session-detail query shows exactly one session anchored to the test channel with a `routing` entry whose `disposition` is `stepped` and a policy `outcome: mention` (confirming the bot-authored mention registered — no inference). Confirms a single bot-peer round-trips (and the topology + mention baseline) before multi-user load is applied. |
| 2 | Run the `three-users-one-channel` scenario: bots A, B, and C each post a distinguishable `@mention` message (e.g. each asks the bot to echo its own sender label) into the same channel, in sequence. | The-one's bot replies to each. `[mixed-frame]` Exactly ONE session exists for the channel (shared by A, B, C — NOT three sessions; session keys on the channel 4-tuple, not peer). The session's `routing` entries (one per inbound) each show `disposition: stepped` (outcome=`mention`) with the correct resolved agent, and each carries the correct `peer_id` for its sender. |
| 3 | In the Chat UI (Chrome MCP), open the connector-attached shared session history and take a screenshot. | Each inbound message in the shared session renders attributed to its sender's `discord-username` (A, B, C shown distinctly) in the form `username: message` — NOT anonymous "peer message" entries. This is the user-perceivable proof of criterion #13 under multi-peer traffic in one session. |
| 4 | Inspect each reply's content (driver assertion + Chrome MCP). | Each reply corresponds to the correct sender's request (the echo/label matches the sender) — i.e. replies are not cross-wired between peers within the shared session. Response correctness is observable from the console. |
| 5 | Run the `dm-isolation` scenario: burner bot A sends a DM to the-one's bot. | `[mixed-frame]` A NEW, separate session exists, distinct from the channel session — its `channel_id` is the DM channel id (unique per user-pair). Confirms the DM "channel of 1" isolates per-peer automatically while the shared channel does not. (The DM admission itself depends on `dm_admission` config; precondition admits peer A.) |
| 6 | Run the `acl-overlay-deny` scenario: a burner-bot peer that a per-agent ACL overlay is configured to DENY for a specific agent posts an `@mention` message in a channel where only that agent is eligible. | The-one's bot does NOT engage that (agent, peer) pair. `[mixed-frame]` The session's `routing` entry shows `disposition: no-eligible` — an ACL-denied agent yields `decision.agent=None` and collapses to `no-eligible` at the routing layer (step 9), which runs BEFORE the policy gate (step 11), so the deny is unambiguously the ACL overlay, not policy silence. Confirms the F6 per-user overlay denies under real traffic, not just in the structural unit tests. |
| 7 | Run the `acl-overlay-admit` counterpart: the same peer posts where the overlay ADMITS the agent. | The-one's bot engages and replies; the `routing` entry shows `disposition: stepped` with the admitted agent. The admit/deny pair together prove the overlay is doing real work (not blanket-allow or blanket-deny). |
| 8 | Re-open the Chat UI history after steps 6–7 and screenshot; then have the driver emit its per-criterion report rows for #5 and #13. | Attribution remains correct across the admit/deny mix; denied-peer messages that produced no reply still render attributed to the correct sender (silence is not anonymity). The report records PASS/FAIL for multi-user routing (#5: shared-session topology + routing + ACL + DM isolation) and attribution (#13) with the session ids + peer ids as evidence; reproducible on re-run. |

Sequencing note: the smoke round-trip (step 1) gates the multi-user load (step 2) so a single-peer failure isn't misread as a routing-fan-out bug. DM isolation (step 5) runs after the shared-channel proof so the topology contrast is explicit. The admit/deny pair (steps 6–7) runs last so an overlay denial is unambiguously the overlay, not a baseline routing failure.

> **Disposition-vocabulary note (verify at run time):** the dispositions are `stepped` | `command-intercepted` | `no-eligible` | `policy-silent`; engaged routes are `stepped`, ACL-denied routes are `no-eligible`, and an engagement-silence is `policy-silent` carrying a `policy` sub-dict. This spec engages via `@mention` precisely so the inference (`policy-silent`) path is OUT of the routing tests — therefore a `policy-silent` in steps 1/2/4/7 indicates an engagement/mention MISS (the mention didn't register), NOT a routing fault, and is distinct from the *intended* `no-eligible` in step 6. Confirm the exact field names against the live `session_metadata["routing"]` shape when the driver is built (L4) and reconcile with the `audit-log-inspector` panel.

## Out of Scope

- Multi-channel routing (#6) and multi-agent `/talk_to` override (#7) — covered by `discord-multi-channel-routing` and `discord-multi-agent-routing`.
- Pairing approval and detach (#9) — covered by `discord-detach-and-pairing` (human-sender Chrome-MCP pass).
- Mentions-aware engagement decision — covered by `discord-engagement`; this spec keeps all three peers ACL-admitted-and-engaging so routing, not the policy gate, is the variable under test.
- Wire-level gateway mechanics (intents, reconnect) — substrate-tested, not re-verified here.
- Whether a burner *bot* is a perfect human stand-in — the apparatus DD accepts the bot-peer path as identical post-`ingest_bots`-gate; the genuinely human-only attribution-as-a-human-reads-it is covered by the Chrome MCP screenshot rows (3, 7).

## Variants (optional)

- `n_users` — number of distinct burner bots (default 3). Raise to stress session fan-out.
- `channel` — the test channel id.
- `deny_pair` — the (agent, peer) pair the overlay denies in step 5, parameterized for re-run against a different overlay configuration.
