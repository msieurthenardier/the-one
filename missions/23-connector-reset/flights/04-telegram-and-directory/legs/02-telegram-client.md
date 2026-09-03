# Leg: telegram-client

**Status**: completed
**Flight**: [Telegram and the Name Directory](../flight.md)

## Objective

Implement the Telegram connector as `the_one/connectors/telegram/` — a long-poll Bot API client on the existing `httpx`, translating to the contract envelope and registered in production — proven entirely against a fake Bot API fixture, plus the per-connector setup help file (DD-9). No live Telegram traffic in this leg.

## Context

- Flight DD-1 (subpackage; leg 1 already delivered every shared touch — this leg adds ONLY the subpackage, one lifespan registration block, the fixture, tests, and docs), DD-2 (the normative long-poll design — read it in full), DD-9 (help file), DD-11 (subpackage ≤350).
- Leg 1's landed surface this leg consumes: `'telegram'` accepted by model + CHECK + `_creatable_connector_types`; `ConnectorDirectoryRepository` for the `chat.title` channel upserts; `InboundEnvelope.peer_username`; `PermanentConnectorFailure` (Flight 3, `connectors/base.py`) REUSED for 401/404/409 — zero new shared code.
- Discord (`connectors/discord/`) is the structural template: type-keyed singleton plugin, account-id-keyed `_AccountState` dict, failure marker + `connect()`-clears-marker lifecycle, `doctor()` short-circuit, manager-owned retry (plugin never retries internally), injectable base URL for tests.
- **Telegram protocol specifics (DD-2 normative, flight-review fact-checked)**:
  - Loop: `getUpdates(offset=last_update_id+1, timeout=50, allowed_updates=["message"])`; offset advanced only after a batch is dispatched (at-least-once redelivery after unclean restart — stated, not dedup'd).
  - `getMe` at `connect()` captures bot id + `@username` into state.
  - Permanent: 401/404 (bad token) and **409 Conflict** (another getUpdates consumer — retrying can't fix a config error) → `PermanentConnectorFailure`; anything else → loop dies → `is_alive()` False → manager backoff.
  - `is_alive()`: poll task alive AND last successful poll within `2*timeout + grace`.
  - Translate: `chat.type == "private"` → `is_dm`; `mentions_bot` from `entities` — `mention` entity whose text slice equals `@botusername` (case-insensitive) OR `text_mention` whose `user.id` == bot id; `peer_name` = `first_name [+ last_name]`; `peer_username` = `from.username` (may be absent); channel key `str(chat.id)`; forum-topic messages carry `message_thread_id` → envelope `thread_id` (and the directory thread shape); bot-authored (`from.is_bot`) dropped UNLESS on `allowlist.peers` (Flight 3's DD-4-as-amended parity); text-less messages (joins, stickers without text) dropped.
  - Directory: every group/supergroup message carries `chat.title` → channel upsert via leg 1's repository (upsert-on-change; deliberately not admission-gated per flight DD-4's cycle-2 ruling — quote it at the call site). Private chats: peer entries come from the leg-1 inbound hook, not the plugin.
  - Outbound `send()`: `sendMessage(chat_id=..., text=...)` — `ChannelTarget` → `chat_id=channel_id` (+ `message_thread_id` when `thread_id` set); `PeerTarget` → `chat_id=peer_id` (Telegram DM chat id == user id — no Create-DM step; state in a code comment). Plain text, no `parse_mode` (no escaping surface).
  - **NO `history` hook** — the Bot API cannot fetch message history; the optional-hook pattern means Telegram simply doesn't implement it (state in the plugin docstring AND the README; the history tool's existing no-hook error path covers it).
  - `/new` arrives as ordinary text and flows to the existing command handling unchanged.
- Fixture: `tests/_telegram_api_fixture.py` at the shared tests root (DD-8-of-Flight-3 pattern) — a scriptable fake Bot API (local HTTP server the httpx client hits via injectable base URL, or httpx `MockTransport`; implementer's choice, no real network either way) scripting getUpdates batches (incl. empty timeouts), sendMessage capture, getMe, and error scenarios (401/409/500/timeout).
- Registration: app lifespan (`interfaces/web/app.py`) — `register("telegram", TelegramPlugin())` in the same guarded block as Discord, symmetric unregistration.
- DD-9 help file: `docs/connector-setup.md` — Discord walkthrough (source: the Flight 3 HAT experience — real-browser requirement, MFA-gated token resets, Message Content intent on MAIN and on any REST-reading test bot, OAuth invite URL, form fields, pairing flow) + Telegram walkthrough (@BotFather token; **`/setprivacy` OFF is REQUIRED for group always-listen** — with privacy on, the bot receives only mentions/replies/commands in groups, stated prominently; form fields; pairing via DM). Linked from `connectors/README.md` and the top-level README. States its verified-against date.

## Inputs
- Leg 1's landed (uncommitted) tree: suite 3,803; v39 live; directory repository available.

## Outputs
- `the_one/connectors/telegram/{__init__,_api,plugin}.py` (suggested split; implementer's within ≤350).
- `interfaces/web/app.py`: telegram registration (one block).
- `tests/_telegram_api_fixture.py` + `tests/test_telegram_*.py`.
- `docs/connector-setup.md` + README links.

## Acceptance Criteria

- [x] **AC-1 Poll loop happy path**: against the fixture — connect → getMe captured → getUpdates loop dispatches a scripted message batch to `on_inbound`; offset advances to `last_update_id+1` on the NEXT poll (fixture asserts the offset parameter value, not just that polling happened); an empty-timeout poll cycles cleanly.
- [x] **AC-2 Offset semantics**: a batch dispatched but not yet re-polled (simulated restart: new connect with fresh in-memory state) is REDELIVERED by the fixture and re-dispatched — the at-least-once behavior asserted and documented, not hidden.
- [x] **AC-3 Permanent failures**: fixture returns 401 → `connect()`/loop raises `PermanentConnectorFailure`; same for 409; manager-level test: the listener task terminates (no backoff) while a 500 keeps the ordinary reconnect path; failure marker set, `doctor()` short-circuits, `connect()` clears it (the Flight 3 lifecycle rule, mirrored).
- [x] **AC-4 Liveness**: `is_alive()` goes False when the poll task dies or the last-success timestamp exceeds the window; manager reconnect proceeds (fixture-driven).
- [x] **AC-5 Translation**: per-field tests — is_dm, mentions via BOTH entity kinds (+ a non-matching mention NOT flagged), peer_name composition, peer_username present/absent, str(chat.id) keys, forum-topic thread_id, bot-drop vs allowlisted-bot admitted, text-less dropped.
- [x] **AC-6 Directory channel capture**: a scripted group message upserts `(chat.id, chat.title)` (thread shape when message_thread_id present); upsert-on-change guard on repeated identical titles; the not-admission-gated comment quotes the flight ruling.
- [x] **AC-7 Outbound**: `send()` shapes for ChannelTarget (with and without thread), PeerTarget; fixture asserts exact sendMessage payloads; `SendResult.platform_message_id` from the response.
- [x] **AC-8 Protocol conformance**: `TelegramPlugin`/client satisfy the runtime-checkable Protocols; `disconnect()` idempotent; NO `history` attribute (asserted — `getattr(client, "history", None) is None` — with the docstring stating why); doctor ok/failed with binding detail.
- [x] **AC-9 Registration**: lifespan registers/unregisters `"telegram"` symmetrically (the `async with lifespan(app)` house pattern, two cycles).
- [x] **AC-10 Help file**: `docs/connector-setup.md` exists with both walkthroughs incl. the `/setprivacy` requirement stated prominently; README links land; no operator-identity leaks.
- [x] **AC-11 Budget + purity**: `wc -l the_one/connectors/telegram/*.py` ≤350 reported; no `pyproject.toml`/`uv.lock` diff; fixture-only networking (no real hosts in tests).
- [x] **AC-12 Suite green**: `make test-unit` foreground, no new failures/warnings (baseline 3,803).

## Verification Steps
- Scoped: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_telegram_*.py -x --timeout 30` foreground.
- AC-12: `make test-unit` once at leg end, foreground, 600000 ms timeout.

## Implementation Guidance
1. Fixture first (scenario-scripted, like the Discord fake gateway). 2. `_api.py` (thin typed calls + error mapping). 3. `plugin.py` (state dict, loop, translate, send, doctor) mirroring Discord's structure and comment density. 4. Registration + lifespan test. 5. Help file (write the Telegram half while implementing — the details are hot). 6. Test discipline: FOREGROUND ONLY, explicit tool timeouts up to 600000 ms, never run_in_background, never end a turn with a command pending; `uv sync` always `--extra dev --extra all-llms --extra gui` (leg 1's deviation: `--extra dev` alone strips the others).

## Edge Cases
- **update types other than message** (edited_message etc.): excluded by allowed_updates; a stray unexpected update type is skipped, never crashes the loop.
- **Entity offsets are UTF-16 code units**: slice accordingly when matching `@botusername` (or match case-insensitively on the raw text containing the mention — implementer's choice, tested either way).
- **Group migrated to supergroup** (chat id changes): out of scope; note in README known-limitations.
- **sendMessage 429**: Bot API returns retry_after — bounded retry mirroring Discord's REST discipline, or surface as ConnectorClientError after one retry; pick one, test it, document it.
- **connect() when getMe fails transiently** (network): ordinary failure → manager backoff, NOT permanent.

## Files Affected
(see Outputs)

## Citation Audit (2026-09-02)
Against the leg-1 tree: `connectors/base.py` `PermanentConnectorFailure` + `InboundEnvelope.peer_username` (leg 1); `connectors/discord/plugin.py` structural template (_AccountState, failure marker, doctor short-circuit); `db/repositories.py` `ConnectorDirectoryRepository` (leg 1); `interfaces/web/app.py` discord registration block; `tests/_discord_gateway_fixture.py` fixture precedent. All live on the branch.

---

## Post-Completion Checklist
**Flight-end commit model — do NOT commit and do NOT signal `[COMPLETE:leg]`:**
- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit` foreground)
- [x] Flight log updated (subpackage count, test numbers, deviations/anomalies)
- [x] Leg status set to `landed`
- [x] Signal `[HANDOFF:review-needed]`
