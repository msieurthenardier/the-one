# Behavior Test: Discord Live Round-Trip

**Slug**: `discord-live-round-trip`
**Status**: draft
**Created**: 2026-09-01
**Last Run**: never

## Intent
Proves the Mission 23 channel contract against REAL Discord infrastructure — the hand-rolled Gateway v10 + REST client, not the stub: a driver bot's @mention in the test channel reaches the attached agent and the reply lands back in the same channel; the always-listen channel answers unprompted messages; an untracked channel stays silent; the agent can speak first into a channel via the send tool (baseline-visible per mission RQ8 — this spec carries NO tool-use nudge, which is itself the mechanical-fallback proof); and the connection resumes after a forced disconnect. The DM/pairing half of the mission criterion is NOT here (bots cannot DM bots) — it belongs to the flight's guided HAT leg.

## Preconditions
*(Draft — env-var names follow the old `discord_hat` conventions; leg 3 finalizes exact names/ids against the replacement HAT config.)*
- Dev instance: Flight 2 conventions (`THE_ONE_PORT=8485`, scratch data dir, `dev_mode`; never 8484). Network egress to `discord.com`/`gateway.discord.gg`.
- MAIN bot: application + token with Message Content intent, joined to the operator's test guild; a Discord connector row created for it (Studio) with `default_agent: test-agent`, the test channel in `always_listen` OR relying on @mentions per step, and the driver bot's user id on `allowlist.peers`.
- DRIVER bot: second token, same guild, `.env.hat`-style config with guild id, test-channel id, always-listen-channel id, untracked-channel id.
- `test-agent` bound to a working provider; `send_to_platform_channel` enabled (visible via the Tools tab's Connectors category); an ORDINARY system prompt — no tool-discipline nudge (deliberate: DD-5's carve-out must make the tool callable without one).
- Browser apparatus for the Chat-UI observations; `curl` for app-API observations; the driver bot's REST access is the platform-side act+observe apparatus.

## Observables Required
- http (driver-bot Discord REST: create message, get channel messages — act AND platform-side observe; app API `GET /api/chat/sessions`; the controlled-disconnect mechanism leg 3 designs)
- browser (Chat UI unified history for the connector session — visibility/attribution as proven in Flight 2)

## Steps

*(Draft — key observables and rough count fixed; exact payloads/ids finalized in leg 3 once the client exists.)*

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Verify the connector's doctor reports healthy (gateway connected, agent bound, tool enabled). | Doctor green; no binding warnings. |
| 2 | Driver bot posts `@MainBot what is 3+3?` in the TEST channel (not always-listen). | Within 90s the main bot replies in the same channel (driver-bot REST read shows a bot-authored message containing `6`); the app shows one session keyed to that channel with the peer message + reply. |
| 3 | Driver bot posts a message WITHOUT a mention in the UNTRACKED channel. | 60s of silence — no bot reply in that channel; no new session for it. |
| 4 | Driver bot posts (no mention) in the ALWAYS-LISTEN channel. | Within 90s the bot replies there — always-listen answers unprompted. |
| 5 | Via the app, instruct the agent (operator chat message in the always-listen session): `send the word "beacon" to this channel using your send tool.` | Within 90s the driver bot's REST read shows a main-bot message `beacon` in the channel; the Chat UI shows the `[platform-send-ok]` result as a top-level peer-visible bubble. NO tool-discipline text was ever injected — the send tool was baseline-visible. |
| 6 | Force a gateway disconnect (mechanism per leg 3's design — controlled, not a production kill switch). Wait for reconnect/resume. Then driver bot @mentions the bot again in the TEST channel. | The bot reconnects (resume or re-identify) without operator action and answers the new mention within 90s — the mission's resume criterion observed live. |

## Out of Scope
- DMs and pairing-code admission from a human account (guided HAT leg — bots cannot DM bots).
- Telegram (Flight 4); load/rate-limit stress; sharding/compression (mission scope).
- Small-model tool-call reliability via `search_tools` (superseded by the RQ8 carve-out this spec proves).
