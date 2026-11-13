# Leg: fake-platforms

**Status**: completed
**Flight**: [Visuals on Chat Platforms](../flight.md)

## Objective
`scripts/fake_platforms.py` is a standalone, loopback-only fake of the Discord REST API and gateway and the Telegram Bot API. It records every request the app sends (JSON bodies, multipart fields, and per file the size, SHA-256 and PNG dimensions), can inject inbound messages and fail chosen uploads, and is proved by unit tests that run the real Discord and Telegram plugins against it in-process.

## Context
- **Flight design decision DD2** (operator choice 2026-11-11): the platforms are faked, never live. The fake proves what the app sends, not what Discord or Telegram show. This leg is the fake itself. Leg 6 wires the app to it (the lifespan seam) and runs the `charts-reach-platforms` behavior test against it.
- **It models the existing in-process fixtures**, which already capture what the clients need:
  - `tests/_discord_gateway_fixture.py` (a `websockets.serve` double: HELLO, READY with `user.id`, dispatch);
  - `tests/_telegram_api_fixture.py` (real `getUpdates` offset semantics, where an update at or below the offset is never redelivered).
- **It follows the widget sink's conventions** (`scripts/widget_sink.py`, used by the `widget-escape` behavior test):
  - a module docstring with usage;
  - `--host`, loopback only, else exit 2;
  - the first stdout line is JSON (`{"port": P, "pid": N}`);
  - it stops cleanly on SIGTERM or SIGINT;
  - `tests/test_widget_sink_cli.py` is the CLI-test model.
- **Discord client facts** (verified at leg design):
  - The gateway URL is used as given (`DiscordPlugin(gateway_url=…)`, `plugin.py` `_gateway_url_override or await rest.get_gateway_url()`), with `GATEWAY_QUERY = "/?v=10&encoding=json"` appended. So the client connects to `…/discord/gateway/?v=10&encoding=json`, and the websocket route must accept the trailing slash.
  - READY sets `session_id` and `resume_gateway_url` (`_gateway.py:200-201`). A RESUME is attempted only when both are set (`:235`). The fake's READY carries **no** `resume_gateway_url`, so the client always re-IDENTIFYs on reconnect. An op 6 RESUME, if one ever arrives, gets op 9 with `d: false`.
  - Every `MESSAGE_CREATE` on a channel-cache miss calls `GET /channels/{id}` for `type` (`_resolve_channel_type`); type 1 is a DM. A DM has no `name`, so the directory upsert is skipped.
  - `MESSAGE_CREATE` is dropped before READY's `user.id` is set, and dropped when its author is the bot.
- **Telegram client facts:**
  - `getMe`, then a loop of `getUpdates(offset, timeout)` with no sleep. `connect()` resolves after the first `getUpdates` returns.
  - A `message` needs `text`, `from.id`, `chat.id` and `chat.type`; `"private"` is a DM.
- **Dependencies:** FastAPI, uvicorn and `python-multipart` (base dependencies, so FastAPI multipart forms work). FastAPI websockets run on uvicorn's websockets backend. No new dependency.
- **Low risk:** additive, single surface, a developer tool that `the_one/` never imports. No leg design review (Flight Director call, recorded in the flight log). The flight-end review covers it.

## Inputs
- Leg 4, landed or landing: the real `DiscordClient.send_visual` and `TelegramClient.send_visual`. This leg's in-process tests exercise them, and Leg 4 must have landed before this leg's tests run.
- `tests/_discord_gateway_fixture.py`, `tests/_telegram_api_fixture.py`, `scripts/widget_sink.py`, `tests/test_widget_sink_cli.py`.
- `tests/test_discord_plugin.py:23-29`, `:129-136` and `tests/test_telegram_plugin.py:43-53`: how tests build a `Connector` and call `plugin.connect(account, encryptor, on_inbound)`.

## Outputs
- **`scripts/fake_platforms.py`** (new). A FastAPI app built by `create_app(save_dir: Path | None) -> FastAPI`, plus a `main()` CLI.
  - **Discord REST under `/discord/api/v10`:**
    - `GET /gateway/bot` returns `{"url": "ws://<host>:<port>/discord/gateway"}`.
    - `GET /users/@me` returns the bot user.
    - `GET /channels/{id}` returns `{"id", "type"}` (1 for DM channels the fake made, 0 with a `name` otherwise).
    - `POST /users/@me/channels` (`recipient_id`) returns the same DM channel id per recipient.
    - `POST /channels/{id}/messages`, as JSON or multipart, returns `{"id": <seq>, "channel_id"}`.
  - **Discord gateway `ws /discord/gateway` (and with a trailing `/`):**
    - HELLO (`heartbeat_interval` defaults to 30000 ms; `--heartbeat-ms` for tests).
    - IDENTIFY → READY `{session_id, user: {id, username}}`, with no `resume_gateway_url`.
    - Every op 1 heartbeat gets an op 11 ACK; an op 6 RESUME gets op 9 `false`.
    - Injected `MESSAGE_CREATE`s are dispatched with increasing `s`.
  - **Telegram under `/telegram/bot{token}/{method}`:**
    - `getMe`.
    - `getUpdates`: honours `offset` and holds up to `timeout` seconds, released early by an inject.
    - `sendMessage` (JSON) and `sendPhoto` (multipart), each returning `{"ok": true, "result": {"message_id": n}}`.
    - An unknown method returns 404 with `{"ok": false}`.
  - **Control under `/_control/`:**
    - `GET health`.
    - `POST discord/inject` `{author_id, author_name?, content, channel_id?}`. The default is a DM channel for that author, which the fake creates and reports as type 1.
    - `POST telegram/inject` `{from_id, text, chat_id?, chat_type? = "private", first_name?}`.
    - `GET received` returns `{"records": […]}`. Each record has `seq`, `platform`, `method` (the Telegram method, or `METHOD path` for Discord), `path`, `json` (or null), `fields` (non-file multipart fields as strings; `payload_json` included) and `files` (`[{name, filename, content_type, size, sha256, png: {width, height} | null}]`). It holds no file bytes and never records the Telegram token: the token is replaced by `<token>` in `path`.
    - `POST fail-next` `{count, status, kind: "upload" | "any"}`. "upload" is a Discord multipart message POST or a Telegram `sendPhoto`. The failure is a matching status response in each platform's error shape, and a 429 carries `retry_after: 1` in each platform's shape.
    - `POST reset` clears records, injected state and failures; it keeps live sockets and polls.
  - **`--save-dir DIR`:** each received file is written as `DIR/{seq:04d}-{name}-{filename}`. A save dir inside the repository is refused with exit 2.
  - **CLI:**
    - `--host` must be a loopback IP literal or `localhost`, else exit 2;
    - `--port` must be 0 or ≥ 8490, and never 8484 or 8485, else exit 2;
    - the first stdout line is `{"port": P, "pid": N}`;
    - SIGTERM or SIGINT stops it.
- **`tests/test_fake_platforms.py`** (new): the in-process protocol and multipart tests. The fake runs on port 0 under uvicorn in the test's event loop or a thread, and the real plugins connect to it.
- **`tests/test_fake_platforms_cli.py`** (new): the CLI refusals and the first-line JSON, modelled on `tests/test_widget_sink_cli.py`.
- **`the_one/connectors/README.md`:** a short "Fake platforms (developer tool)" paragraph under Test seams, pointing at the script. Leg 6 adds the app seam.

## Acceptance Criteria
- [ ] **AC1, Discord round trip in-process.**
  - A real `DiscordPlugin(rest_base_url=<fake>/discord/api/v10, gateway_url=ws://<fake>/discord/gateway)` connects. `connect()` resolves after READY.
  - An injected DM reaches `on_inbound` as an `InboundEnvelope` with `is_dm=True`, the injected `peer_id` and the injected text.
  - A `client.send` to that DM's `PeerTarget` is recorded as a JSON `POST /channels/{id}/messages` with the content.
- [ ] **AC2, Discord multipart.** `client.send_visual(target, text, [img1, img2])`, with real PNGs from `render_png`, is recorded as one multipart message:
  - `fields.payload_json`'s `attachments` hold `description` and `filename`;
  - `files` has `files[0]` and `files[1]`, each with `content_type` `image/png`, the right `size` and `sha256`, and `png` dimensions equal to the images' `width` and `height`.
- [ ] **AC3, Discord heartbeat.** With `--heartbeat-ms` set low (for example 100), the client stays connected through at least 5 heartbeat intervals: it receives ACKs, so it never closes itself (`_gateway.py:285-295`), and `client.is_alive()` stays true.
- [ ] **AC4, Telegram round trip in-process.**
  - A real `TelegramPlugin(base_url=<fake>/telegram)` connects.
  - An injected private message reaches `on_inbound` while `getUpdates` is held, within 2 s, which proves early release. It is never redelivered after the offset advances, which a test asserts.
  - `send_visual` is recorded as `sendMessage` (JSON) and then one `sendPhoto` per image, with `chat_id`, `caption` and a `photo` file whose `png` dimensions match.
- [ ] **AC5, fail-next.** `fail-next {count: 1, status: 413, kind: "upload"}` makes the next Discord multipart POST answer 413. The client raises `VisualUploadError`, and a following JSON message succeeds. The same on Telegram makes a `sendPhoto` answer 413, and the per-photo fallback text is recorded. `kind: "upload"` never fails a JSON send.
- [ ] **AC6, save dir and privacy.**
  - With `save_dir`, each received file is written with the stated name and its bytes equal what was sent.
  - `received` never contains file bytes, and never contains the Telegram token: a test asserts the token string is absent from the whole JSON.
  - `reset` empties `received`.
- [ ] **AC7, CLI.**
  - `--host 0.0.0.0` exits 2.
  - `--port 8484`, `--port 8485` and `--port 8000` each exit 2.
  - `--save-dir <repo path>` exits 2.
  - A run on `--port 0` prints `{"port": P, "pid": N}` as its first line, answers `GET /_control/health` with 200, and exits 0 on SIGTERM. The test records and kills only its own PID.
- [ ] **AC8:** `the_one/` imports nothing from `scripts/` (a guard test, or `grep -rn "fake_platforms" the_one/` showing no import). `THE_ONE_TEST_NETNS=1 make test-unit` passes with the expected skip count, and `ruff check` and `ruff format --check` are clean (`scripts/` is in ruff's scope).

## Verification Steps
- AC1-AC6: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_fake_platforms.py -x --timeout 60`.
- AC7: `… tests/test_fake_platforms_cli.py -x --timeout 60`.
- AC8: `grep -rn "fake_platforms" the_one/`; `THE_ONE_TEST_NETNS=1 make test-unit` (in the background); `ruff`.

## Implementation Guidance
1. **Read the two fixtures and `widget_sink.py`** first, and keep the same protocol subset.
2. **Build `create_app()` with module-level state in one `FakeState` object** held on `app.state`:
   - records;
   - the Discord sockets and their `seq`;
   - the DM channels;
   - the Telegram updates list and an `asyncio.Event` for long-poll release;
   - the fail-next counter;
   - the save dir.
   
   Keep one lock for record appends.
3. **Multipart:** use FastAPI's `await request.form()`. For an `UploadFile`, read the bytes, then compute size, SHA-256 and the PNG IHDR width and height with `struct`: the signature check, then big-endian width and height at offsets 16 and 20. Never keep the bytes in memory after recording and saving.
4. **The Discord gateway:**
   - Register both `/discord/gateway` and `/discord/gateway/` (FastAPI `@app.websocket` on both paths).
   - The server loop handles op 2 IDENTIFY (READY), op 1 (op 11), op 6 (op 9 `false`) and ignores other ops.
   - An inject pushes `MESSAGE_CREATE` to every open socket. READY's `user.id` is the fake bot's id, which must differ from any injected author id.
5. **Telegram `getUpdates`:** filter `update_id >= offset`. If nothing matches, wait on the event for up to `timeout` seconds, then filter again. Updates are never deleted, which matches the real API and the fixture.
6. **Tests:**
   - Run uvicorn with `uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")` and `uvicorn.Server`. Get the bound port from `server.servers[0].sockets[0].getsockname()[1]` after startup, and stop it with `server.should_exit = True` plus await.
   - Build `Connector`s and the encryptor the way `tests/test_discord_plugin.py` and `tests/test_telegram_plugin.py` do, with `tmp_path`.
   - Always `disconnect` the plugin in `finally`.
7. **The README paragraph**, then the gates. Run `make test-unit` once at the end, in the background.

## Edge Cases
- **An inject before any client connects:** Discord queues nothing (a dispatch needs a socket) and the inject returns 409 `{"error": "no gateway client"}`. Telegram keeps the update for the next poll.
- **Two Discord sockets** (the client reconnecting): dispatch goes to the newest IDENTIFY'd socket only.
- **`fail-next` with `status` 500:** a 5xx, so Discord gets no resend and Telegram skips the photo with no fallback (Leg 4). AC5 covers 413. One test covers 500 for Discord (no second POST recorded).
- **Large uploads:** the fake accepts any size and has no limits of its own. It is not a size-limit model.
- **A Telegram token with `:`:** a real token looks like `123:ABC`, so the path parameter must accept `:`. Redact it in `received`.

## Files Affected
- `scripts/fake_platforms.py` (new)
- `tests/test_fake_platforms.py` (new), `tests/test_fake_platforms_cli.py` (new)
- `the_one/connectors/README.md`

## Citation Audit
Checked 2026-11-12 against the working tree (Leg 1 committed, Leg 3 landed, Leg 4 in flight; none touches these Discord gateway or translation lines).
- `discord/_gateway.py:25` `GATEWAY_QUERY = f"/?v={API_VERSION}&encoding=json"`; `:200-201` READY sets `session_id` and `resume_gateway_url`; `:235` resume only when both are set; `:247` `url = (await self._default_url_provider()).rstrip("/") + GATEWAY_QUERY` — verified
- `discord/plugin.py` constructor `gateway_url`/`rest_base_url`; `_gateway_url_override or await rest.get_gateway_url()`; `_translate_message_create` drops before READY and self-authored; `_resolve_channel_type` → `rest.get_channel` — verified
- `telegram/plugin.py:84-110` `_translate_message` needs `text`, `from`, `chat.id`, `chat.type == "private"` for DM; `:220-245` poll loop — verified
- `tests/_discord_gateway_fixture.py` (`websockets` server, HELLO/READY/dispatch helpers); `tests/_telegram_api_fixture.py` (`update_id >= offset`, never deleted) — verified
- `scripts/widget_sink.py` — loopback-only `--host` (exit 2), first-line JSON; `tests/test_widget_sink_cli.py` exists — verified
- `pyproject.toml:18-19,33` fastapi, uvicorn[standard], websockets base deps; `python-multipart` transitive via fastapi (pinned floor comment `:59`) — verified

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
