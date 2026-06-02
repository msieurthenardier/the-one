# Behavior Test: Discord Multi-Channel Routing + Channel-Scoped Override (F15)

**Slug**: `discord-multi-channel-routing`
**Status**: draft
**Created**: 2026-06-01
**Last Run**: never

## Intent

Verify that when one Discord sender posts into three different channels served by the-one's bot, each message routes to that channel's configured agent in its OWN separate session, the per-account `default` catches a channel with no matching rule, and a channel-scoped rule override re-routes a channel away from the default — all under real traffic (mission criterion #6). Routing is configured via the connector's `config.routing = {"rules": list[RoutingRule], "default": str | None}` (BOTH keys required when routing is non-None); a `RoutingRule` is `{"scope": "channel"|"thread"|"dm"|"peer", "match": list[str], "agent": str}` with OR-semantics over its `match` LIST. The rule-walk (`_routing.py:resolve_routing` step 2) returns `RoutingDecision(agent=rule["agent"], scope="channel", reason="rule-match")` on a channel match; step 3 (per-account `default`) catches channels with no matching rule (`scope="default"`). Sessions key on the `(platform, connector_id, channel_id, thread_id)` 4-tuple, so distinct channels → distinct sessions — which removes the L4 peer-correlation problem: one bot posting one message per channel uniquely identifies which channel's routing entry to read.

This needs a behavior test, not a unit test, because it exercises the live multi-channel path end-to-end: real gateway events into distinct channels, the dispatcher reloading the account fresh per inbound (`_inbound.py` step 2 — so a routing-rules change takes effect on the NEXT inbound with no restart), `resolve_routing` walking the operator-ordered rules against real channel ids, and the per-channel session isolation — no unit can stand in for distinct real channels each producing its own routed session. The "which channel routed to which agent" mapping (read from each session's routing entry) is itself the observable.

The sender is driven by the committed `tests/live/discord_hat/` multi-bot driver (the target connector runs with `ingest_bots=true`; a single burner bot posts one `@mention` per channel). A `[mixed-frame]` session-detail probe reads each channel's routing entry (`agent`/`scope`/`reason`) to distinguish a rule-match from a default fall-through where the channel surface alone can't.

## Preconditions

- The the-one container is running; the connector worker is up; L1's stdout connector logging is active (so a failed routing step is diagnosable from `docker logs`).
- A dedicated test connector is configured with `ingest_bots=true`, `always_listen=false`, `dm_admission=all`, the test guild on the allowlist, and an account-scope `allowlist.channels = [{guild_id, channel_id: "*"}]` so ALL guild channels are admitted (any test channel passes ACL; the routing rules then pick the agent).
- **Engagement mechanism:** every routing-scenario message from the burner bot `@mentions` the-one's bot. The mention path engages the agent deterministically (outcome=`mention`) with NO inference call — `is_mention` checks the bot's id in `message.mentions` independent of author. `always_listen=false`, so a NON-mention post is `policy-silent` (no routing decision recorded) — every post in this spec MUST `@mention`.
- At least two agents are attached to the test connector (the L4/L5 fixture: **Connector Agent 1** and **Connector Agent 2**), both ACL-admitting all peers/channels (no overlays — restored after L4). The configured channel agent must be an attached, admitting agent or the rule falls through.
- Three test channels exist in the test guild (the L5 fixture: test-channel-1/2/3). The test SETS the connector's `config.routing` it needs at run time and RESTORES the connector's prior `config.routing` (captured before any change — `None` when no routing was configured) in a `finally`. Every connector PUT omits `secrets` so the bot token is preserved (`update_connector` at `api.py:2489` keeps `existing.secrets` when absent).
- A local Ollama inference provider is configured (so any inference path runs without external rate limits).
- The operator is logged into the-one's Chat UI in the Chrome MCP browser session, viewing the connector-attached sessions.
- The bot-peer-equivalence premise (L3) has been confirmed — a burner bot resolves to a peer identically to a human sender.

## Observables Required

- browser (the-one Chat UI rendered state — per-channel session existence + the routed agent; measured via chrome-devtools MCP)
- filesystem / API (`[mixed-frame]` — the-one session detail via `GET /api/chat/sessions/{id}` including `session_metadata["routing"]`; the routing entry's `agent`/`scope`/`reason` is the load-bearing surface distinguishing a channel rule-match from a default fall-through)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Set the connector's `config.routing` to `{"rules": [{"scope":"channel","match":[ch1],"agent":"Connector Agent 1"}, {"scope":"channel","match":[ch2],"agent":"Connector Agent 2"}], "default":"Connector Agent 1"}` (capturing the prior `config.routing` for restore; PUT omits `secrets`). | `[mixed-frame]` A `GET /api/connectors/{id}` confirms `config.routing` now carries the two channel rules + the `default`, and the bot token is preserved (no re-auth needed — the connector stays connected). `match` is a LIST per rule. The change takes effect on the NEXT inbound (the dispatcher reloads the account fresh per dispatch — no restart). |
| 2 | The burner bot posts an `@mention` into **ch1** (PRIME — first contact on a cold channel uses a direct post + wait, NOT a "wait for a NEW entry" helper, which would block on a channel with no pre-existing session); await the agent step. | `[mixed-frame]` A session anchored to ch1 exists with a `routing` entry whose `disposition == stepped`, `agent == "Connector Agent 1"`, `scope == "channel"`, `reason == "rule-match"`. Proves the ch1 channel rule routed to Agent 1. |
| 3 | The burner bot posts an `@mention` into **ch2** (PRIME); await the agent step. | `[mixed-frame]` A SEPARATE session anchored to ch2 exists (distinct `channel_id` → distinct session) with a `routing` entry: `disposition == stepped`, `agent == "Connector Agent 2"`, `scope == "channel"`, `reason == "rule-match"`. The ch2 channel rule routed to Agent 2 — a DIFFERENT agent than ch1, purely by channel. |
| 4 | The burner bot posts an `@mention` into **ch3** (PRIME — ch3 has NO matching rule); await the agent step. | `[mixed-frame]` A THIRD separate session anchored to ch3 exists with a `routing` entry: `disposition == stepped`, `agent == "Connector Agent 1"`, `scope == "default"` (the per-account `default` caught it — NOT a channel rule). This distinguishes a rule-match (`scope=channel`) from a default fall-through (`scope=default`). |
| 5 | Confirm via the lookup seam that ch1/ch2/ch3 resolved to THREE distinct session ids. | `[mixed-frame]` The three session ids are distinct (`len(set) == 3`) — channel-keyed isolation: each `channel_id` produces its own `(platform, connector_id, channel_id, thread_id)` 4-tuple → its own session. |
| 6 | In the Chat UI (Chrome MCP), open the three connector-attached channel sessions and take a screenshot. | Three distinct channel sessions render, each showing its inbound `@mention` attributed to the burner bot's `discord-username`. (Operator-perceivable confirmation that the three channels are three separate conversations.) The committed counterpart asserts the machine-readable surface: three distinct `detail["id"]`s. |
| 7 | Add a channel-scoped override: set `config.routing` to the same rules PLUS `{"scope":"channel","match":[ch3],"agent":"Connector Agent 2"}` (default unchanged). The burner bot re-posts an `@mention` in **ch3** (ch3's session now EXISTS, so a "wait for a NEW routing entry" read is correct here); await the agent step. | `[mixed-frame]` ch3's session has a NEW `routing` entry: `disposition == stepped`, `agent == "Connector Agent 2"`, `scope == "channel"`, `reason == "rule-match"` — the channel-scoped rule OVERRODE the default that previously caught ch3 (step 4). This is the mission's "channel-scoped agent overrides are exercised." Confirms a rules change takes effect on the next inbound with no restart. |
| 8 | Restore the connector's `config.routing` to its captured prior value (in a `finally`); then have the driver emit its per-criterion report rows for #6. | `[mixed-frame]` A `GET /api/connectors/{id}` confirms `config.routing` is back to the pre-test value (e.g. `null` when no routing was configured) and the token is preserved. The report records PASS/FAIL for multi-channel routing (#6: per-channel rule routing + default fall-through + separate sessions + channel-scoped override) with the session ids + routed agents as evidence; reproducible on re-run (the `finally` restores routing so a second run passes without manual cleanup). |

Sequencing note: the priming posts (steps 2–4) establish each channel's session before the override (step 7) re-posts into the now-existing ch3 session — so the "new routing entry" read in step 7 is unambiguously the override's effect, not a cold-channel race. The restore (step 8) runs in a `finally` so a mid-test failure leaves the connector's routing unchanged.

> **Committed counterpart:** `tests/live/discord_hat/test_multi_channel.py` (the `discord_hat`-marked test) is the machine-checked counterpart of steps 1–5 and 7–8: it sets the per-channel routing rules, primes ch1/ch2/ch3 (asserting per-channel routed `agent`/`scope`), asserts three distinct session ids, exercises the ch3 channel-scoped override, and restores the connector's prior `config.routing` in a `finally`. The Chrome-MCP attribution row (6) remains the human pass.

> **Disposition-vocabulary note (proven at L4 run time):** the dispositions are `stepped` | `command-intercepted` | `no-eligible` | `policy-silent`. Engaged routes are `stepped` (and carry NO `policy` sub-dict — `policy.outcome` is populated only on the `policy-silent` path). A routing entry is `{ts, agent, rule_index, scope, match, reason, disposition}`. For an engaged channel-routed message the entry carries `scope == "channel"` + `reason == "rule-match"` (a rule fired) or `scope == "default"` (the per-account default caught it). A `policy-silent` in any step here indicates an engagement/mention MISS (the `@mention` didn't register), NOT a routing fault.

## Out of Scope

- Multi-user routing (#5) + peer-name attribution (#13) — covered by `discord-multi-user-routing`.
- Multi-agent `/talk_to` override (#7) — covered by `discord-multi-agent-routing`.
- Per-user ACL admit/deny differentiation — covered by `discord-multi-user-routing` (the per-agent overlay path); here both agents admit all channels so routing, not the ACL gate, is the variable under test.
- Pairing approval and detach (#9) — covered by `discord-detach-and-pairing` (human-sender Chrome-MCP pass).
- Thread-scope, dm-scope, and peer-scope rules — this spec exercises `channel`-scope routing only.
- Wire-level gateway mechanics (intents, reconnect) — substrate-tested, not re-verified here.

## Variants (optional)

- `n_channels` — number of distinct test channels (default 3). Raise to stress per-channel session fan-out.
- `channels` — the test channel ids (ch1/ch2/ch3).
- `override_agent` — the agent the step-7 channel-scoped override re-routes ch3 to (default Connector Agent 2), parameterized for re-run against a different override target.
