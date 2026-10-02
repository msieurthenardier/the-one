# Behavior Test: Discord Live Round-Trip

**Slug**: `discord-live-round-trip`
**Status**: active
**Created**: 2026-09-01
**Last Run**: 2026-09-01-19-19-17 (pass — see runs/)
**Updated**: 2026-10-02 (M25 F3 surface rename; not re-run)

## Intent
Proves the Mission 23 channel contract against REAL Discord infrastructure — the hand-rolled Gateway v10 + REST client, not the stub: a driver bot's @mention in the test channel reaches the attached agent and the reply lands back in the same channel; the always-listen channel answers unprompted messages; an untracked channel stays silent; the agent can speak first into a channel via the send tool (baseline-visible per mission RQ8 — this spec carries NO tool-use nudge, which is itself the mechanical-fallback proof); and the connection resumes after a forced disconnect. The DM/pairing half of the mission criterion is NOT here (bots cannot DM bots) — it belongs to the flight's guided HAT leg.

## Preconditions

- **Dev instance boot** — from the project root, with BOTH gates open (the sever seam in step 6 needs `THE_ONE_DISCORD_TEST_ENDPOINT=1`; `THE_ONE_DEV_MODE=true` is the standing dev-instance requirement, not a stub-connector gate — no `THE_ONE_STUB_TEST_ENDPOINT` here, this test drives a REAL Discord connector):
  ```bash
  THE_ONE_PORT=8485 THE_ONE_DATA_DIR=/tmp/the-one-behavior-test-scratch \
    THE_ONE_DEV_MODE=true THE_ONE_DISCORD_TEST_ENDPOINT=1 make up
  ```
  Use a fresh scratch `THE_ONE_DATA_DIR` (not the operator's default) and port `8485`
  (never `8484`, the operator's production instance — see CLAUDE.md's "SAFETY RULE").
  Verify liveness: `curl http://127.0.0.1:8485/api/live` → HTTP 200. Tear down after
  the run with `THE_ONE_PORT=8485 make down`.
- **Env contract** — read from the operator's `tests/behavior/.env.hat` (copied from the
  committed `.env.hat.example` and filled with real values; see that file's provisioning
  notes for bot creation):
  - `THE_ONE_HAT_DRIVER_TOKEN` — the second (driver) bot's token; the act+observe apparatus.
    *(Precondition amended in place 2026-09-01, run 19-19-17, per the rerun-checkpoint
    discipline: the DRIVER bot **DOES need Message Content intent enabled** — the old
    `discord_hat` advice that senders don't need it assumed assertions via the-one's API;
    THIS spec's observe path reads the main bot's replies via the driver's own REST
    `GET /channels/{id}/messages`, and Discord returns `content: ""` to a bot lacking the
    intent — the run's first attempt at step 2 observed exactly that empty-content
    redaction on an otherwise-delivered reply.)*
  - `THE_ONE_HAT_GUILD_ID` — the shared test guild id.
  - `THE_ONE_HAT_TEST_CHANNEL_ID` — the channel the driver @mentions the main bot in (steps 2, 6).
  - `THE_ONE_HAT_ALWAYS_LISTEN_CHANNEL_ID` — the channel the connector's `always_listen`
    config names (step 4).
  - `THE_ONE_HAT_UNTRACKED_CHANNEL_ID` — a channel the connector does NOT track (step 3).
- **MAIN bot**: application + token with Message Content intent, joined to the operator's
  test guild; a Discord connector row created for it (Library › Connectors) with `default_agent:
  test-agent`, `config.always_listen` containing `THE_ONE_HAT_ALWAYS_LISTEN_CHANNEL_ID`, and
  the driver bot's Discord user id on `allowlist.peers` (the driver posts as itself, not as
  the operator, so it needs admission the same way any peer does).
- `test-agent` bound to a working, non-mock provider; `send_to_platform_channel` enabled
  (visible via the Tools tab's Connectors category); an ORDINARY system prompt — **no
  tool-discipline nudge** (deliberate: DD-5's carve-out must make the tool callable without
  one — this is the mechanical-fallback proof; if a run needs a nudge to pass, that is a
  finding against DD-5, not a spec defect to quietly patch around).
- Browser apparatus for the Chat-UI observations (session keying/visibility, as proven in
  Flight 2); `curl` for app-API observations and the sever seam; the driver bot's own
  Discord REST access (`https://discord.com/api/v10`, `Authorization: Bot
  <THE_ONE_HAT_DRIVER_TOKEN>`) is the platform-side act+observe apparatus for steps 2–6.
- **Credential**: this instance is gated (Mission 20 Flight 1). Follow CLAUDE.md's
  "Behavior-test credential convention" — read
  `/tmp/the-one-behavior-test-scratch/api-credential`, mint a handoff URL for the browser
  navigation (re-mint if a step opens a fresh tab/context), and attach `Authorization:
  Bearer <credential>` to every app-API `curl` call (the sever seam and `GET
  /api/chat/sessions` are ordinary gated routes, not the unauthenticated `/api/live`).
- Network egress to `discord.com` / `gateway.discord.gg` from the machine running the dev
  instance.

## Observables Required
- **http** (driver-bot Discord REST: `POST /channels/{id}/messages` to act, `GET
  /channels/{id}/messages` to read back replies — act AND platform-side observe; app API
  `GET /api/chat/sessions`; `POST /api/_test/discord/sever` — the controlled-disconnect
  mechanism, dual-gated `dev_mode` + `THE_ONE_DISCORD_TEST_ENDPOINT=1`)
- **browser** (Chat UI unified history for the connector session — visibility/attribution as proven in Flight 2)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Verify the connector's doctor reports healthy (gateway connected, agent bound, tool enabled): `POST /api/connectors/{id}/test`. | Doctor `status: "ok"`, `message: "gateway connected"`; no binding warnings. |
| 2 | Driver bot posts `@MainBot what is 3+3?` (the real `<@bot_user_id>` mention syntax) in `THE_ONE_HAT_TEST_CHANNEL_ID` (not always-listen) via `POST /channels/{THE_ONE_HAT_TEST_CHANNEL_ID}/messages`. | Within 90s the main bot replies in the same channel (driver-bot REST read via `GET /channels/{id}/messages` shows a bot-authored message containing `6`); the app's `GET /api/chat/sessions` shows one session keyed to that channel with the peer message + reply. |
| 3 | Driver bot posts a message WITHOUT a mention in `THE_ONE_HAT_UNTRACKED_CHANNEL_ID`. | 60s of silence — no bot reply in that channel; no new session for it in `GET /api/chat/sessions`. |
| 4 | Driver bot posts (no mention) in `THE_ONE_HAT_ALWAYS_LISTEN_CHANNEL_ID`. | Within 90s the bot replies there — always-listen answers unprompted. |
| 5 | Via the app (browser), instruct the agent (operator chat message in the always-listen session): `send the word "beacon" to this channel using your send tool.` | Within 90s the driver bot's REST read shows a main-bot message `beacon` in `THE_ONE_HAT_ALWAYS_LISTEN_CHANNEL_ID`; the Chat UI shows the `[platform-send-ok]` result as a top-level peer-visible bubble. NO tool-discipline text was ever injected — the send tool was baseline-visible. |
| 6 | Force a gateway disconnect: `POST /api/_test/discord/sever` with body `{"connector_id": "<the connector's id>"}` and the credential header. Wait for reconnect/resume (doctor `gateway_connected: true` again, or a fresh `READY`/`RESUMED` in the host log). Then driver bot @mentions the bot again in `THE_ONE_HAT_TEST_CHANNEL_ID`. | The sever call returns `{"status": "ok"}`. The bot reconnects (resume or re-identify) without operator action and answers the new mention within 90s — the mission's resume criterion observed live. |

## Out of Scope
- DMs and pairing-code admission from a human account (guided HAT leg — bots cannot DM bots).
- Telegram (Flight 4); load/rate-limit stress; sharding/compression (mission scope).
- Small-model tool-call reliability via `search_tools` (superseded by the RQ8 carve-out this spec proves).
