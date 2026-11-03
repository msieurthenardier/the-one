# Behavior Test: Directory Lookup Send

**Slug**: `directory-lookup-send`
**Status**: active
**Created**: 2026-09-02
**Last Run**: 2026-09-02-20-22-46 (pass — see runs/)
**Updated**: 2026-10-05 (M25 F4 leg 8: step 2 names how a new chat starts: New chat and the agent picker, created by the first send)

## Intent
Proves the Flight 4 name-directory two-call chain with a REAL model and no live platform: the system passively records an observed peer's names into `connector_directory`, and an operator instruction addressed by NAME — with no ids, no target JSON, no tool-discipline nudge — makes the agent chain the `find_platform_destination` lookup tool (candidates with ids) into the existing `send_to_platform_channel` tool (explicit target), landing the content on the platform side. This is the mechanical gate for mission criterion "name-addressed sends across connectors" (RQ11), run before the live HAT so model-policy findings surface cheaply (RQ8's lesson applied up front). The multi-connector half of the criterion (Discord + Telegram live) belongs to the flight's HAT leg.

## Preconditions
- Dev instance per Flight 2/3 conventions: `THE_ONE_PORT=8485`, `THE_ONE_DATA_DIR=$HOME/the-one-behavior-test-scratch/data` (create the credential first with `the-one rotate-api-credential` against it), `THE_ONE_DEV_MODE=true`, `THE_ONE_STUB_TEST_ENDPOINT=1` (never 8484). Start it from a scratch working directory, not the repo root (CLAUDE.md "SAFETY RULE"). Credential convention per CLAUDE.md.
- A `stub`-typed connector with `default_agent: test-agent` and peer id `peer-7` already on `allowlist.peers` — the seeding envelope must be ADMITTED or no directory entry exists (three-axis apparatus audit: the act path's output must clear admission).
- `test-agent` bound to a `supports_tools()` model at the mission's floor (gpt-oss:20b-class); ORDINARY system prompt — no tool-discipline nudge (the chain must work on carve-out visibility alone); `send_to_platform_channel` AND `find_platform_destination` both enabled for `test-agent`.
- Browser apparatus for Chat UI observations; `curl` for the stub seams and app API.

## Observables Required
- http (stub seams `POST /_test/stub/inbound` act + `GET /_test/stub/outbound` observe; `GET /api/chat/sessions`)
- browser (Chat UI: the two tool results and the final state, rendered — including the lookup tool's own result, which step 2 uses as the directory-population proof; no separate DB/API read is needed)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | `POST /_test/stub/inbound` with `{"connector_id": "<stub-connector-id>", "peer_id": "peer-7", "peer_name": "Marisol Vega", "peer_username": "marisolv", "is_dm": true, "text": "hello there"}`. | Within 60s, the Chat UI shows a `DM: Marisol Vega` session whose transcript contains the peer message `hello there`. (Row-judgeable at a browser-observable session claim only — the directory-population proof is deferred to step 2, where it is judgeable in that row.) |
| 2 | In the Chat UI, open a NEW unbound operator chat with `test-agent` (deliberately not the DM session from step 1 — the send cannot lean on session-default targets): on Chats, click the Chats list's **New chat** (`chats-new-btn`), type `test-agent` in the agent picker's search and press Enter; the pending chat becomes a session with this step's first send. Instruct EXACTLY: `send the message "harbor lights" to Marisol on the stub connector.` | Within 300s *(re-authored 2026-09-02, run 20-22-46, operator-sanctioned: 120s was calibrated to the two-call happy path; a floor-model's organic recovery loops — false starts steered back by the tools' own `[error]`/`[no-match]` messages — are legitimate behavior this test deliberately leaves un-nudged)*: the agent calls `find_platform_destination` and its result (visible in the turn's tool activity) lists a candidate with `display_name` "Marisol Vega" and `peer_id` "peer-7" — this candidate's PRESENCE IS the evidence the directory was populated by step 1. The agent then calls `send_to_platform_channel` with an explicit peer target built from that candidate's ids. FINAL-STATE outbound assertion *(re-authored, same run: "exactly one" was brittle against in-turn self-correction — a model that elides an argument, notices, and re-sends is behaving well; the load-bearing guarantees are delivery and targeting)*: `GET /_test/stub/outbound` contains at least one new record for `peer-7` with content exactly `harbor lights`, and ZERO new records to any other target (self-corrective duplicates to the SAME correct target are recorded in the run log, not failures). Confirmation surface *(re-authored, same run — the original "top-level [platform-send-ok] bubble" clause was a spec-authoring error: top-level promotion is deliberately gated on platform-bound sessions per Flight 2's reply-visibility design; unbound chats do not promote)*: the `[platform-send-ok]` result is present in the turn's tool activity AND a visible assistant confirmation bubble renders. NO nudge text was ever injected. |
| 3 | Instruct in the same chat: `send "second beacon" to Zephyrine on the stub connector.` (No such name observed.) | Within 90s: no send occurs (`GET /_test/stub/outbound` count unchanged from step 2); the agent's reply surfaces the lookup's no-match outcome (names the failed query "Zephyrine" rather than inventing a target). |

## Out of Scope
- Live platforms (Discord/Telegram name sends — the flight's HAT leg) and cross-connector disambiguation with multiple live connectors (HAT).
- Ambiguous-candidate behavior with colliding names (unit-tested at the tool level; a live-variant may be added if the HAT motivates it).
- Retro-renaming of existing session titles (DD-7 trade-off, stated).
