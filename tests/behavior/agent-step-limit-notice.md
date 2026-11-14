# Behavior Test: Agent Step-Limit Notice

**Slug**: `agent-step-limit-notice`
**Status**: active
**Updated**: 2026-11-14 (sortie 16: steps 1, 1b and 4 read the turn's work group state instead of "tool activity")
**Created**: 2026-10-27
**Last Run**: 2026-10-28-14-36-06 — pass (7/7; re-run after the M31 F6 L10 HAT re-author: Continue button, button-aware copy; port 8497; [run log](agent-step-limit-notice/runs/2026-10-28-14-36-06.md)). Previous: 2026-10-28-02-28-33 — pass (6/6; first run, M31 F6 close sweep, port 8498; draft → active)

## Intent

Verifies Mission 31 Flight 6's F2 end to end (DD8): when an agent stops because it ran out of steps (`max_iterations`), every interface says so, and the notice is a projection that is never stored. The web chat shows a muted notice line after the reply, with "Max iterations" linking to the agent's settings; a connector chat gets one neutral plain line on the platform; a reload, a second browser context and the stored session (`GET /api/chat/sessions/{id}`) show no notice. This turns on real-environment observables (the live WebSocket `step_limit` frame, the DOM, the stub connector's outbound record, the stored history) across the agent loop, the web app and the connector pipeline, which no unit test witnesses in one piece. The unit tests (`tests/test_agent_step_limit.py`, `tests/test_step_limit_web.py`, `tests/test_connectors_inbound.py`) prove the mechanics with scripted models; this spec proves the live wiring. Run in Flight 6 leg 09b.

## Preconditions

- **Dev instance**, per CLAUDE.md "Behavior-test credential convention" (never port 8484 or the default data directory): a scratch working directory, a dedicated port of 8490 or higher (not 8485, the Flight Director's preview port) and a scratch `THE_ONE_DATA_DIR` and working directory under `$HOME`, started with `THE_ONE_DEV_MODE=true THE_ONE_STUB_TEST_ENDPOINT=1`. A fresh data directory has no `api-credential` (`serve` does not create it): run `THE_ONE_DATA_DIR=<data_dir> the-one rotate-api-credential` once before the first start, then read the credential from `<data_dir>/api-credential`; a browser context goes in through `POST /api/session/handoff` (one mint per fresh context).
- **The seed** (through the REST API, no real model). **Order matters: create the provider first, then the agent with the returned provider `id` as `provider_config_id`** (an empty or unknown id is a 422, squawk 0277), then the connector:
  - a `mock` provider (`"type":"mock"`, `"base_url":""`) whose `config.response` is `{"tool_calls": [{"id": "t1", "name": "current_time", "arguments": {}}]}`, so every reply asks for the `current_time` tool again (the same call id each time is fine for two iterations);
  - an agent `limit-agent` on that provider with `max_iterations` 2;
  - a `stub` connector `bt-limit` whose `default_agent` is `limit-agent`, with peer `peer-1` admitted. Set it up through the REST API (every call with `Authorization: Bearer <credential>`): `POST /api/connectors` with `{"name":"bt-limit","type":"stub","config":{"enabled":true,"default_agent":"limit-agent"},"secrets":{"token":"dummy"}}` (record the returned `id` as `{ID}`; the `stub` type exists only with `THE_ONE_DEV_MODE=true` and `THE_ONE_STUB_TEST_ENDPOINT=1`); `POST /api/connectors/{ID}/pairing-code` (record the code as `{CODE}`); `POST /api/_test/stub/inbound` with `{"connector_id":"{ID}","peer_id":"peer-1","peer_name":"peer-1","text":"{CODE}","is_dm":true}`; then `GET /api/connectors/{ID}` must show `config.allowlist.peers == ["peer-1"]`.

## Observables Required

- browser (DOM: the notice `[data-testid="chat-step-limit"]`, its link `[data-testid="chat-step-limit-link"]`, the log's children; the live WebSocket frames, read through the page's frame record if the apparatus offers one)
- http (`GET /api/_test/stub/outbound` after `POST /api/_test/stub/inbound`; `GET /api/chat/sessions/{id}` for the stored `messages`; `POST /api/chat` for the REST result)
- shell (curl, the scratch data directory)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Seed the provider, agent and connector as in Preconditions. Open the app in a browser context, go to **Chats**, start a chat with `limit-agent` (New chat, pick it) and send `hello`. Wait for the turn to settle (the send button enabled again). | The turn's work group (`turn-work`, `data-state="step-limit"`) reads "Paused at the step limit · N tool calls" with no reply bubble after it, and after the group the log's last child is a muted notice (`chat-step-limit`, class `ui-notice--muted`) whose text reads "Stopped: this agent used its 2 steps for this message. Click Continue or raise max iterations in its settings." with a "Continue" button (`chat-step-limit-continue`) on its own line below it, centred. "max iterations" is a link (`chat-step-limit-link`). No `chat-agent-error` notice and no system bubble. |
| 1b | Click **Continue**. | Exactly one new user bubble reads `continue` and is stored; focus is in the message box; the old button is gone (a DOM capture showing the first notice's `chat-step-limit-continue` absent, or a mid-turn screenshot of it gone, is accepted evidence), and the new turn gets its own work group (the first group stays "Paused at the step limit"); when the turn ends at the limit again a fresh notice with its own Continue button is the last child. (Re-authored in M31 F6 L10d: the notice gained this button; step 1's text assertion changed to match. Re-authored again at the L10 HAT: the button-aware copy and the button below the sentence; a notice with no button, for a blocked composer or a held message, reads "Send another message to continue, or raise max iterations in its settings.") |
| 2 | Click the "max iterations" link. | The hash becomes `#agents/limit-agent` (a `/general` suffix, `#agents/limit-agent/general`, is accepted) and the agent's editor opens. |
| 3 | Via the seam, inject an inbound DM from `peer-1`: `POST /api/_test/stub/inbound` with `{"connector_id":"{ID}","peer_id":"peer-1","peer_name":"peer-1","text":"go","is_dm":true}`. First `GET /api/_test/stub/outbound` and record the baseline (the records already present, normally none) before injecting. Poll it every ~2s for up to 30s, and keep polling for at least 3 further polls after the first new record appears. | Against that baseline, the outbound records hold exactly one new entry for this turn: `connector_id=="{ID}"`, `peer_id=="peer-1"`, `content == "(Stopped: reached its step limit for this message.)"`. No second copy appears on any of the further polls. |
| 4 | In the first browser context, reload the page (the chat re-joins). Then open a second browser context (a fresh handoff mint), go to **Chats** and open the same session from the list. | Both show the rendered conversation (the user bubbles and the replies are present: at least one user bubble reading `hello`, so a count of 0 cannot pass on an empty log) with no step-limit notice (`chat-step-limit` count 0): it was broadcast only. (The server stores no reason a turn ended, so after a reload each turn's group reads "Work · N tool calls", not "Paused at the step limit": an accepted reload difference, not a failure.) |
| 5 | `GET /api/chat/sessions/{id}` for the web chat's session (the id from `#chats/{id}`), then for the connector chat's session (`GET /api/chat/sessions?agent_name=limit-agent`). | In both, no message in `messages` contains "step limit" or "Stopped:": the notice and the connector line are not stored. |
| 6 | `POST /api/chat` with `{"message": "go", "agent_name": "limit-agent"}`; then `POST /api/chat` with a plain message on an agent with the default step budget (`max_iterations` 20, so create it without that field) and a mock reply of plain text (create a second agent and provider for it). | The first result JSON has `"step_limit": true`. The second has no `step_limit` key. |

## Out of Scope

- A connector chat opened in the web UI: it gets only `session_updated` and a re-join, so it shows no notice (DD8, by design).
- The CLI line (covered by `tests/test_cli_step_limit.py`).
- The Copy button and the other chat-transcript surfaces (`stub-connector-round-trip.md`, the chat browser lanes).
