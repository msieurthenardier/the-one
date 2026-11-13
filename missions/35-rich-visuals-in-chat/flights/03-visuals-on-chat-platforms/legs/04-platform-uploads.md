# Leg: platform-uploads

**Status**: completed
**Flight**: [Visuals on Chat Platforms](../flight.md)

## Objective
The Discord and Telegram clients implement `send_visual` and `send_visual_fallback`. Discord posts one multipart message with every image attached. Telegram posts the text, then one captioned `sendPhoto` per image within a 45 s budget. Every DD7 fallback path, the DD10 retry clamp and the DD11 request shapes are pinned by mock-transport tests.

## Context
- **Flight design decisions:** DD6 (layout: one Discord message with `files[n]` plus `attachments[n]`; Telegram text then photos, caption up to 1024), DD7 (4xx-only resend, 5xx/transport never re-sent, Telegram per-photo fallback, logging), DD10 (per-call 429 policy: once, clamped to 10 s; Telegram 45 s photo budget against its 110 s liveness window; existing text sends unchanged) and DD11 (request shapes, transport mapping, factored Telegram 429 retry).
- **Leg 3 contract** (in `the_one/connectors/base.py` and the connectors README):
  - The helper calls `send_visual(target, content, images)` with the text already rendered (markers in place) and the drawn `OutboundImage`s, each with `filename`, `data`, `title`, `width`, `height` and `fallback` (the block source).
  - `send_visual` raises `VisualUploadError` **only when nothing of the reply was posted**. The helper then resends `plan.fallback_text` through `send_visual_fallback(target, content)` when the client has it.
  - Any other `ConnectorClientError` propagates with no resend.
  - Success returns `SendResult(…, details={"images_sent": n, "images_failed": m})`.
- **Transport errors must not trigger Telegram's existing plain-text retry.** `TelegramClient.send` retries once as plain text on *any* `TelegramApiError`, on the assumption that a formatted send was rejected. If a timeout became a `TelegramApiError`, a reply that may already be posted would be posted again. So transport errors (`httpx.HTTPError` raised while sending) map to new **sibling** classes:
  - `TelegramTransportError(base.ConnectorClientError)`;
  - `DiscordTransportError(ConnectorClientError)`.
  
  Neither is a subclass of `TelegramApiError` or `DiscordRestError`. Both platforms get the mapping in their one request method, so every call is covered. The Telegram poll loop and the manager already treat any non-permanent exception the same way, so their behaviour is unchanged.
- **Status on errors:** an error built from a response carries `.status` (the HTTP status). That covers `DiscordRestError`, `TelegramApiError` and the `PermanentConnectorFailure` that Telegram's `_handle_response` raises for 401/404/409. The fallback rules classify on `getattr(exc, "status", None)`: a 4xx is "not posted"; a 5xx, or no status (transport), is "maybe posted".
- **High risk:** this leg changes the error mapping on existing send paths and refactors Telegram's 429 retry, which `send_message` uses today.

## Inputs
- Leg 3, landed: `VisualUploadError`, `OutboundImage`, the helper and the optional-method contract.
- `the_one/connectors/discord/_rest.py`:
  - `RestClient._request(method, path, *, json=None, params=None)`: a per-bucket lock, `_MAX_RETRIES = 3` with unclamped `retry_after`, and `DiscordRestError` on a status of 400 or more;
  - `create_message(channel_id, content)`;
  - `create_dm(user_id)`.
- `the_one/connectors/discord/plugin.py` `DiscordClient`: `_resolve_channel_id` (a `PeerTarget` goes through `create_dm`) and `send`.
- `the_one/connectors/telegram/_api.py`:
  - `TelegramApiClient._post(method, payload, *, timeout)`, JSON only;
  - `_handle_response`: `PermanentConnectorFailure` for 401/404/409, else `TelegramApiError`;
  - `send_message`: one 429 retry with a 60 s clamp, `_MAX_RETRY_AFTER_SECONDS`.
- `the_one/connectors/telegram/plugin.py` `TelegramClient.send`: HTML render, then a one-shot plain-text retry on `TelegramApiError`. Liveness `2 * _POLL_TIMEOUT + _LIVENESS_GRACE_SECONDS` is 110 s.
- Existing tests: `tests/test_discord_rest.py`, `test_discord_plugin.py`, `test_telegram_api.py`, `test_telegram_plugin.py`, and the fixtures `tests/_discord_gateway_fixture.py` and `tests/_telegram_api_fixture.py`.

## Outputs
- **`discord/_rest.py`:**
  - `DiscordRestError` gains `status`.
  - New `DiscordTransportError`.
  - `_request` gains `files=None` (multipart: `data={"payload_json": …}` plus `files=[("files[i]", (filename, bytes, "image/png")), …]`) and a per-call policy: keyword `max_retries` (default `_MAX_RETRIES`) and `max_retry_after` (default `None`, meaning unclamped, today's behaviour).
  - `httpx.HTTPError` becomes `DiscordTransportError`.
  - New `create_message_with_files(channel_id, content, attachments)` (retry once, clamp 10 s) and `create_message(…, *, clamped=False)`, where `clamped=True` means once and 10 s.
- **`discord/plugin.py`:**
  - `DiscordClient.send_visual`: resolve the channel, then one multipart message. A 4xx raises `VisualUploadError`; a 5xx raises `DiscordRestError`; a transport failure raises `DiscordTransportError`.
  - `DiscordClient.send_visual_fallback`: resolve the channel, then `create_message(…, clamped=True)`.
- **`telegram/_api.py`:**
  - `TelegramApiError` gains `status`, and `_handle_response` sets `status` on both raises.
  - New `TelegramTransportError`.
  - `_post` gains a multipart mode (`data=` and `files=`), and `httpx.HTTPError` becomes `TelegramTransportError`.
  - New `_post_with_429_retry(method, *, payload=None, data=None, files=None, timeout, max_retry_after)`. `send_message` uses it with the existing 60 s clamp, unchanged.
  - New `send_photo(*, chat_id, photo: bytes, filename, caption, message_thread_id=None, timeout, max_retry_after=10.0)`.
  - `send_message` gains keyword `max_retry_after` (default 60, today's value).
- **`telegram/plugin.py`:**
  - `TelegramClient.send_visual(target, content, images)`: the text through the existing `send` path, then the photos under a 45 s budget, with per-photo fallbacks.
  - `TelegramClient.send_visual_fallback(target, content)`: the same HTML-then-plain path as `send`, with `max_retry_after=10`.
  - Constant `_PHOTO_BUDGET_SECONDS = 45.0`.
- **Tests** (new or extended): `tests/test_discord_rest.py`, `test_discord_plugin.py`, `test_telegram_api.py` and `test_telegram_plugin.py`, all through `httpx.MockTransport`. A small multipart parser for tests, `tests/_multipart.py`, uses the standard library's `email.parser.BytesParser`.
- **Docs:** `the_one/connectors/README.md`, in the Discord and Telegram sections:
  - each platform's visual send and its fallbacks;
  - the 10 s clamp;
  - the 45 s photo budget against the 110 s liveness window;
  - the transport-error classes.

## Acceptance Criteria
- [ ] **AC1, Discord shape (DD11).** `send_visual` makes exactly one `POST /channels/{id}/messages` as `multipart/form-data`. The test parses the body and asserts:
  - a `payload_json` part, whose JSON is `{"content": <content>, "attachments": [{"id": i, "filename": "chart-N.png", "description": <title, cut to 1024>}, …]}` in image order;
  - one `files[i]` part per image, with `filename`, `Content-Type: image/png` and the exact bytes.
  
  `payload_json` is sent as its own multipart part with `Content-Type: application/json`: `files=[("payload_json", (None, <json>, "application/json")), ("files[0]", …), …]`. AC1 pins that part's content type.

  It returns `SendResult(<message id>, {"images_sent": len(images), "images_failed": 0})`. A `PeerTarget` resolves through `create_dm` first, as `send` does. A retried 429 POST carries byte-identical parts (tested).
- [ ] **AC2, Discord failures (DD7).** Each of these has its own test:
  - A 4xx (400, 413, or a 429 after its one clamped retry) on the multipart POST raises `VisualUploadError`, with the status in the message (`-> 429 (rate limited)` for the 429 case) and on `.status`.
  - A 5xx raises `DiscordRestError` (not `VisualUploadError`), with no second POST.
  - A transport error (`httpx.ConnectError` or `ReadTimeout` from the mock transport) raises `DiscordTransportError`, with no second POST.
  - A `create_dm` failure propagates unchanged.
- [ ] **AC3, Discord retry policy (DD10).**
  - The multipart POST and `send_visual_fallback`'s POST retry a 429 at most once, sleeping `min(retry_after, 10)`. The test monkeypatches `asyncio.sleep` in the module and records the delays.
  - A 429 with `retry_after: 30` sleeps 10.
  - `create_message` without `clamped` keeps today's three retries with an unclamped `retry_after`, and its existing tests are unchanged.
  - A `global: true` 429 still records the global gate on every path.
- [ ] **AC4, Telegram shapes (DD11).**
  - `send_photo` posts `multipart/form-data` to `/bot{token}/sendPhoto` with `chat_id`, `photo` (filename, `image/png`, the exact bytes) and `caption`, plus `message_thread_id` only when given.
  - `send_visual` first sends the text exactly as `send` does: the `sendMessage` HTML attempt, then the plain retry on rejection. Then it makes one `sendPhoto` per image, in order, to the same `chat_id` and thread.
  - A caption is the image title, cut to 1024 characters (code points; an ellipsis when cut), with no `parse_mode`.
- [ ] **AC5, Telegram failures (DD7).** Each has its own test:
  - **(a)** The text send fails: the error propagates (a `ConnectorClientError`, never `VisualUploadError`), and no photo is attempted.
  - **(b)** A photo gets a 4xx (400, 413, or a 429 after its one clamped retry): that image's `fallback` goes out as a follow-up text message through the `send_visual_fallback` path, straight after the failed photo, which keeps the order. It counts as failed.
  - **(c)** A photo gets a 5xx or a transport error: it is logged and skipped, with no fallback text, and counts as failed.
  - **(d)** The remaining photos are still attempted after (b) or (c).
  - **(e)** A follow-up text that itself fails is logged, not raised, because the reply's text already went.
  - **(f)** The result has the text message's id and `{"images_sent", "images_failed"}` with the right counts.
- [ ] **AC6, Telegram budget (DD10).**
  - **The deadline:** the photos and their per-photo fallback texts share a 45 s budget. `deadline = monotonic() + 45`, taken just before the first photo, with `time.monotonic` monkeypatchable.
  - **Enforcement:** every photo attempt, including the retry after a 429, is wrapped in `asyncio.wait_for(…, remaining)`, with `remaining` recomputed from the deadline before each attempt. httpx's `timeout=` limits each phase separately, not the whole request, so `wait_for` is what holds the total. Each request also passes `timeout=min(15, remaining)`.
  - **A `wait_for` timeout:** the photo may have been posted, so it is logged and skipped as `budget`, with no fallback for that image. Every image still unattempted then goes to `pending`.
  - **The 429 rule for a photo:** sleep `s = min(retry_after, 10)`, then retry once, but only when `s < remaining`. Otherwise give up at once, with no sleep, as a 429 (a 4xx), which sends that image's per-photo fallback. For example:
    - `retry_after` 7 s with 3 s remaining gives up and sends the fallback;
    - `retry_after` 30 s with 40 s remaining sleeps 10 s, then retries once;
    - a second 429 sends the fallback.
    
    Both cases are tested.
  - **Running out:** images not attempted when the budget runs out go as **one** follow-up text message, their `fallback`s joined with a blank line, sent through the fallback path. That message is sent after the deadline and is bounded by its own 10 s clamp. They count as failed.
  - **Tests:** one drives a fake clock past the budget mid-sequence; another uses a slow mock handler that exceeds `remaining`, to prove `wait_for` ends the attempt.
- [ ] **AC7, Telegram retry factoring (DD10, DD11).**
  - `send_message`'s 429 behaviour is unchanged (one retry, 60 s clamp, the warning on clamp), and every existing `tests/test_telegram_api.py` test passes unchanged.
  - `send_photo` and the fallback text path clamp at 10 s.
  - One function implements the retry, and both callers use it.
- [ ] **AC8, transport mapping (DD7).**
  - On both platforms an `httpx.HTTPError` during any request becomes the platform's transport error, a `ConnectorClientError` sibling, not a subclass of `DiscordRestError` or `TelegramApiError`.
  - A test proves `TelegramClient.send` does **not** run its plain-text retry after a transport error on the HTML attempt: one request only, and the error propagates.
  - The existing poll-loop, gateway and manager tests pass unchanged.
  - **Side effects of the mapping** (improvements, documented in the README):
    - The connector `doctor` on both platforms catches `ConnectorClientError`, so a transport failure now gives a "failed" report instead of a raw exception. One test per platform covers it.
    - `SendToPlatformChannelTool` now returns an `[error] DiscordTransportError: …` or `[error] TelegramTransportError: …` string.
  - **Token safety:** the Telegram transport mapping raises `from None`, because the bot token is in the URL path and a chained `__cause__` traceback could print it. A `caplog` test asserts that the token is absent after a transport error on `send` and on `send_visual`.
- [ ] **AC9, logging (DD7).** Every fallback, skip or budget event logs one warning with the image index or indices, the platform, the HTTP status (or `transport`, or `budget`) and the chat or channel id. It never logs the image bytes, the title, the caption or the fallback text. `caplog` tests assert that the title, the caption and the fallback source are absent from every record, on both the Discord path and the Telegram fallback-text path.
- [ ] **AC10, the end-to-end shape through the helper.** A Discord client and a Telegram client, each built in-process on a `MockTransport`, receive one reply with two charts and a widget through `deliver_final_reply`, with `render_png` real. The Discord mock sees one multipart message with 2 files; the Telegram mock sees `sendMessage` then 2 `sendPhoto`.
- [ ] **AC11:** the connectors README documents both platforms' visual sends and every number above: 10 images, 1024 characters, the 10 s clamp, and 45 s against the 110 s liveness window.
  - **The whole send runs inside the Telegram poll task** (`on_inbound` is awaited in the poll loop). So the README states what the 45 s covers: the photos and their per-photo fallbacks. The text send's own worst case (an HTML attempt and a plain retry, each with up to a 60 s 429 clamp) predates this flight and can already exceed 110 s. The final pending-fallback message adds at most one clamped request. This is recorded as a residual, not changed here.
  - The README also notes that each platform's own upload limits (Discord's per-message size, Telegram's 10 MB and its dimension limits) surface as a 4xx and so take the fallbacks.
  
  `THE_ONE_TEST_NETNS=1 make test-unit` passes with the expected skip count, and `ruff check` and `ruff format --check` are clean. `THE_ONE_TEST_NETNS=1 make test-unit` passes with the expected skip count, and `ruff check` and `ruff format --check` are clean.

## Verification Steps
- AC1-AC3: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_discord_rest.py tests/test_discord_plugin.py -x --timeout 30`.
- AC4-AC8: `… tests/test_telegram_api.py tests/test_telegram_plugin.py tests/test_telegram_logging.py -x --timeout 30`.
- AC9, AC10: the new tests above, plus `tests/test_delivery_visuals.py`.
- AC11: `THE_ONE_TEST_NETNS=1 make test-unit` (in the background); `ruff`.

## Implementation Guidance
1. **Errors first.**
   - Add `status: int | None = None` to `DiscordRestError` and `TelegramApiError`, as a keyword in `__init__`, keeping the message the first argument so existing `str(exc)` assertions hold.
   - For the `PermanentConnectorFailure` that `_handle_response` raises, set the attribute after construction (`exc.status = resp.status_code`) and do not change the base class.
   - Add the two transport classes.
   - Wrap the actual `self._client.request(...)` and `self._client.post(...)` calls in `try/except httpx.HTTPError as exc: raise <Transport>(f"... {type(exc).__name__}") from exc`.
2. **Discord `_request`.**
   - Add the `files` and policy keywords. On multipart, pass `data={"payload_json": json.dumps(payload)}` and `files=[…]`, and no `json=`.
   - With the policy, the loop runs `max_retries + 1` times (`max_retries=1` is 2 attempts), and `retry_after` is `min(retry_after, max_retry_after)` when one is set. The exhausted-retries message ("after N retries") stays.
   - The error raised after the last 429 keeps `status=429`.
   - Classify in `send_visual`: catch `DiscordRestError`, and when `400 <= status < 500` raise `VisualUploadError(str(exc))` with `.status` set, chained with `from`.
3. **Telegram.**
   - Factor `_post_with_429_retry` from `send_message`'s body. Keep the exact warning text and the clamp logic, parameterised by `max_retry_after`.
     - It gains an optional `deadline: float | None`. When set, it gives up on a 429 (raising `TelegramApiError(…, status=429)`) whenever the clamped sleep is not under the remaining time. It wraps each attempt in `asyncio.wait_for(…, remaining)`, recomputing `remaining` before each attempt.
     - `send_message` passes no deadline, so it is unchanged.
   - `send_photo` builds `data={"chat_id": …, "caption": …}` (plus `message_thread_id`) and `files={"photo": (filename, bytes, "image/png")}`.
   - In `TelegramClient`, factor `send`'s body into `_send_text(target, content, *, max_retry_after)`. Then:
     - `send` calls it with 60;
     - `send_visual_fallback` calls it with 10;
     - `send_visual` calls `send` for the text (60, unchanged), then runs the photo loop.
4. **The budget loop.** `deadline = monotonic() + _PHOTO_BUDGET_SECONDS`, taken just before the first photo. For each image:
   - If `deadline - monotonic() <= 0`, add the image to `pending`.
   - Otherwise call `send_photo(…, max_retry_after=10.0, deadline=deadline)`, which applies AC6's 429 rule and `wait_for`.
     - `asyncio.TimeoutError` means skipped as `budget`, and the rest go to `pending`.
     - A 4xx means the per-photo fallback text, sent through the fallback path with a `wait_for` on the remaining budget. If none remains, it joins `pending` instead.
     - A 5xx or a transport error means logged and skipped.
   - After the loop, if `pending` is not empty, send one fallback text (clamped at 10 s, with no deadline).
   - `PermanentConnectorFailure` (401/404/409) is a `ConnectorClientError` subclass (`base.py`). On a photo it is a 4xx, so the fallback is sent, and its likely failure is logged per AC5(e). The poll loop surfaces a bad token on its own.
5. **Tests.**
   - Add `tests/_multipart.py`: `parse(request) -> dict[name, (filename | None, content_type | None, bytes)]` via `email.parser.BytesParser(policy=email.policy.HTTP)` on `b"Content-Type: " + header + b"\r\n\r\n" + body`. Design review verified this against httpx 0.28.1, including `\r\n` inside the PNG bytes.
   - `tests/_telegram_api_fixture.py` cannot serve the new tests. Its handler `json.loads` every body, it has no `sendPhoto` branch (so a call falls through to a 404), and it scripts errors per method, not per call. So the new Telegram visual tests use a **purpose-built `MockTransport` handler**, defined in the new test file, with a per-call script (for example `photo_script=[200, 413, 500, "raise", "slow"]`) that records every request parsed through `tests/_multipart.py`. The existing fixture stays unchanged.
   - Read the Discord fixture's transport style first, and reuse it where it fits.
6. **README,** then run the gates, with `make test-unit` once at the end, in the background.

## Edge Cases
- **A title longer than 1024 characters:** the format caps titles at 120 (`MAX_TITLE`), so this cannot happen. Truncate defensively all the same, and test it with a hand-built `OutboundImage`.
- **`message_thread_id`:** a `ChannelTarget` thread goes to every photo and follow-up text; a `PeerTarget` has none.
- **Discord content over 2000 characters:** Discord answers 400, so `VisualUploadError`, then the fallback resend, which is also over 2000 and fails with `DiscordRestError`, which propagates. That is today's outcome for long text. Message splitting is out of scope (mission).
- **Empty `images`:** the helper never calls `send_visual` with no images (Leg 3 branch d). Raise `ValueError` defensively, and test it.
- **A `PermanentConnectorFailure` (401/404/409) on a photo:** it is a 4xx, so the per-photo fallback is sent. That will likely fail too, and the failure is logged per (e).
- **Rate-limit bucket:** the multipart POST uses the same `route_key` as `create_message`, so the per-bucket lock serialises them.

## Files Affected
- `the_one/connectors/discord/_rest.py`, `the_one/connectors/discord/plugin.py`
- `the_one/connectors/telegram/_api.py`, `the_one/connectors/telegram/plugin.py`
- `tests/_multipart.py` (new), `tests/test_discord_rest.py`, `tests/test_discord_plugin.py`, `tests/test_telegram_api.py`, `tests/test_telegram_plugin.py`, and a new end-to-end shape test file (for example `tests/test_platform_visuals_e2e.py`)
- `the_one/connectors/README.md`

## Citation Audit
Checked 2026-11-12 against `ba547e29`. Leg 3's uncommitted edits do not touch these files.
- `discord/_rest.py` — `_MAX_RETRIES = 3`; `DiscordRestError(ConnectorClientError)`; `_request(method, path, *, json=None, params=None)` with the per-bucket lock, `retry_after` from the 429 body, the `record_global` path and `>= 400` raise; `create_message(channel_id, content)`; `create_dm(user_id)` — verified
- `discord/plugin.py:209-241` — `DiscordClient`, `_resolve_channel_id` (`PeerTarget` → `create_dm`), `send` → `create_message`, `SendResult(platform_message_id=str(message.get("id", "")), details={})` — verified
- `telegram/_api.py` — `_PERMANENT_STATUSES = {401, 404, 409}`; `_MAX_RETRY_AFTER_SECONDS = 60.0`; `_post(method, payload, *, timeout)` JSON only; `_handle_response`; `send_message` one 429 retry with clamp and warning — verified
- `telegram/plugin.py:122-189` — `TelegramClient` dataclass; `is_alive` window `2 * _POLL_TIMEOUT + _LIVENESS_GRACE_SECONDS` (110 s; `_LIVENESS_GRACE_SECONDS = 10.0` at `:23`); `send` HTML render, then plain retry on `TelegramApiError` — verified
- `telegram/plugin.py:220-245` — the poll loop catches `BaseException` and re-raises only `PermanentConnectorFailure` — verified
- `manager.py:194`, `:236-257` — `PermanentConnectorFailure` special-cased, otherwise `except Exception` — verified
- Design review cycle 1 (Developer, Sonnet) verified:
  - httpx 0.28.1 multipart via `data=` and `files=`, and `email.parser` round-tripping it;
  - no test pins raw httpx exceptions, `str()` or the construction of `DiscordRestError` or `TelegramApiError` (`test_discord_rest.py:134,170,183`, `test_telegram_api.py:97` use bare `raises`);
  - no test introspects `TelegramClient.send` internals (only `render_telegram_html` is monkeypatched, by module path, so keep that import in `plugin.py`);
  - Leg 3's `VisualUploadError`, `OutboundImage` and the `send_visual_fallback` lookup are present in the working tree.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
