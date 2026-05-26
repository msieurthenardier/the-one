# Behavior Test: Discord Engagement Policy Gate (F7)

**Slug**: `discord-engagement`
**Status**: draft
**Created**: 2026-05-25
**Last Run**: never

## Intent

Verify the F7 policy gate decides engaged-vs-silent correctly across its decision-tree paths from the perspective of a Discord user and a Studio operator. Both surfaces are exercised: Studio for toggle configuration, Discord for the runtime engagement decision. The test is intentionally written in the user's frame — what an operator and a Discord poster can see with their own eyes. Where the system's behavior collapses two distinct internal decisions to the same user-facing outcome (e.g., "bot is silent"), the spec calls out the gap as observability debt and uses a justified cross-frame observable to keep the test discriminating.

## Preconditions

- the-one container is running on `http://localhost:8484` and the Studio loads at that URL.
- The Discord bot (GleepGlorp) is online and its connector account `58f1fe5a833f` is listed in Studio with `#gleepglorp-text` on the allowlist.
- Cave Man Bot is attached to the Discord connector account; Sonos Agent is not.
- Inference provider is set to a local Ollama (e.g. `qwen2.5:7b`) so the inference path runs without external API rate limits.
- Operator is logged in to Discord in the Chrome MCP browser session, with `#gleepglorp-text` open in a tab.
- Account-level Always Listen toggle starts OFF (verifiable in Studio's Access and Routing tab).
- Per-agent Always Listen toggle for Cave Man Bot on the Discord account starts unset (verifiable in the agent's Connectors tab).

## Observables Required

- browser (Studio DOM + Discord channel UI, measured via chrome-devtools MCP)
- filesystem (the-one SQLite database, measured via `docker exec` — used only in `[mixed-frame]` rows where the user-facing outcome can't distinguish two internal policy decisions)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Open Studio at the Discord connector account editor and select the Access and Routing tab. | The Session section is visible near the bottom of the tab. An "Always Listen" toggle is present and unchecked. The Additional Config table contains no row keyed `always_listen`. |
| 2 | Open the Cave Man Bot agent's Connectors tab. | Each attached connector account tile shows a per-agent "Always Listen" toggle. The Discord Constellation account's toggle is greyed out (disabled because the account-level toggle is OFF) and unchecked. |
| 3 | In Discord, post a message in `#gleepglorp-text` containing GleepGlorp's @-mention and a simple question. | Within 10 seconds, a message from GleepGlorp App appears in the channel. The reply addresses the question and identifies itself as Cave Man Bot (e.g., the text contains "Cave Man Bot" or a recognizable Cave Man persona). |
| 4 | In Discord, post a message with no @-mention (e.g., a casual greeting). | GleepGlorp App does not post a reply within 10 seconds. `[mixed-frame]` The latest routing audit entry (SQLite `chat_sessions.session_metadata`) shows `disposition: policy-silent`, `policy.outcome: always-listen-off`. Justification: the user only sees silence; the audit log is the only place that distinguishes "silent because always-listen-off" from "silent because inference-no". This is system observability debt — the distinction should eventually surface in a Studio "Recent decisions" panel. |
| 5 | Return to Studio's Access and Routing tab for the Discord connector account. Click the Always Listen toggle (on), click Save, reload the page (hard reload to defeat SPA cache), and reopen the Access and Routing tab. | The Always Listen toggle is checked. The Additional Config table still contains no `always_listen` row (the L11 hotfix keeps the kv-table clean across saves). |
| 6 | Open the Cave Man Bot agent's Connectors tab. Click the per-agent Always Listen toggle for the Discord Constellation account (on). Click Save. | The per-agent toggle is no longer greyed out (account-level being ON enables it). After save, the toggle is checked. |
| 7 | In Discord, post a substantive non-mention question that any reasonable agent should engage with (e.g., "can someone explain how typescript generics work in simple terms?"). | Within 30 seconds (allowing for the local inference call), GleepGlorp App posts a substantive reply that addresses the question and identifies as Cave Man Bot. |
| 8 | In Discord, post a trivially low-content non-mention message (e.g., "lol"). | GleepGlorp App does not post a reply within 30 seconds. `[mixed-frame]` The latest routing audit entry shows `disposition: policy-silent`, `policy.outcome: inference-no`. Justification: the user only sees silence; the audit log distinguishes "silent because inference-no" from the always-listen-off path tested in step 4. Same observability debt as step 4. |
| 9 | In Discord, post a mention asking the bot what channels it has access to (e.g., `@GleepGlorp what channels do you have access to?`). | Within 30 seconds, GleepGlorp App posts a reply that names `#gleepglorp-text` (the only allowlisted channel) as part of its answer. The reply demonstrates the bot used a channel-context tool — i.e., the answer is grounded in actual visible channels, not a hallucinated list. |

## Out of Scope

- Slash command intercept (DM `/help`) — covered by a future `discord-slash-commands` spec.
- Multi-user routing — requires burner Discord accounts not yet available.
- Multi-channel routing — only `#gleepglorp-text` is allowlisted; expand when more channels are added.
- Audit-log inspector UI surface — when that lands, steps 4 and 8 should be rewritten to read it instead of querying SQLite directly, eliminating the `[mixed-frame]` markers.
- Mission-level "daily-driver" criterion — pinned to mission completion, not a per-flight regression test.

## Variants (optional)

None for this initial dogfood. Future variants could parameterize the channel, the agent under test, or the LLM provider.
