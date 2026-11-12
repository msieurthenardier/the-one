# Flight: Visuals on Chat Platforms

**Status**: in-flight
**Mission**: [Rich Visuals in Chat](../../mission.md)

## Contributing to Criteria
- [ ] **Charts reach chat platforms as images** (all of it). The connector round trip runs against fake Discord and Telegram servers, not live bots (operator decision 2026-11-11, DD2; mission amended).
- [ ] **Chart images work on every install** (all of it: Pillow as a base dependency, a bundled font, and a doctor gate run in the Windows, Linux and macOS packaged builds)

---

## Pre-Flight

### Objective
When an agent's reply goes out through Discord or Telegram, each chart in it arrives as a PNG image and the rest of the text arrives as before. This applies to the automatic reply and to the agent's own `send_to_platform_channel`.
- **The text** keeps its order. Each chart block is replaced by a marker line ("📊 Chart: {title} (below)"), and each widget block by a short note that points to the app.
- **The images** follow in order, captioned with the chart's title.
- **On failure:** a chart the server cannot draw, or whose upload fails, falls back to its source as a code block, which is today's behaviour. Nothing is lost.
- **The stored chat is never rewritten.**

The server draws charts with Pillow, now a base dependency:
- in the light theme;
- with a bundled TrueType font;
- under a pinned text layout engine, so text measures the same on every platform;
- following `docs/chart-format.md`, tested against the same sample specs as the browser, plus a new shared corpus of expected axis ticks.

Both platforms are proved end to end against local fake Discord and Telegram servers that record what the app sends; no live bot is involved. A new `the-one doctor` gate proves that every packaged build draws the same chart text, and it runs on all three platforms straight after the renderer lands.

### Open Questions
- [x] Which theme does an image use? → DD5 (light, operator choice 2026-11-11)
- [x] How is a reply with charts laid out on the platform? → DD6 (text, then images; mockup A, operator choice 2026-11-11)
- [x] What does the image itself look like? → DD5: an operator-approved sample sheet is Leg 1's exit gate (design review cycle 1)
- [x] What happens when drawing or an upload fails? → DD7 (the block as code, operator choice 2026-11-11)
- [x] Live bots or fakes for the round trip? → DD2 (fakes for both platforms, no real bots, operator choice 2026-11-11)
- [x] `.woff2` or a bundled TrueType font, and where? → DD4 (static TTFs in `the_one/visuals/fonts/`)
- [x] Which text layout engine? → DD4 (`Layout.BASIC`, pinned; design review cycle 1 measured that RAQM depends on the host's FriBiDi)
- [x] Text the font cannot draw (CJK, emoji)? → DD4 (the font's missing-glyph box, a documented residual; the title also goes out as platform text)
- [x] Visual blocks nested in a quote or a list? → DD1 (sent as source, a documented residual, operator choice 2026-11-12)
- [x] How does a connector gain an image send without breaking the contract? → DD8 (an optional `send_visual`, found by `getattr`)
- [x] How do the stub's record readers survive? → DD9
- [x] Does the step-limit line or any other system line carry a visual? → no (DD3)
- [x] HAT? → none (operator choice 2026-11-11); acceptance is the automated tests, the behavior test, the three-platform doctor run and the Leg 1 sample-sheet approval

### Design Decisions

**DD1 — One conversion step, shared by both send paths**
- **The block finder:** `the_one/visuals/blocks.py` finds a reply's top-level visual blocks in one pass over every tag. It returns `Block(tag, body, closed, start, end)` with character spans.
  - **The fence rule** is the browser's top-level rule, which `evals/checks.py:_top_level_blocks` (`:310-341`) already mirrors:
    - column-0 triple backticks;
    - the tag is the first token of the info string;
    - the closer is a column-0 triple-backtick line;
    - an unterminated block runs to the end;
    - `~~~` is not a fence;
    - any other fence swallows what is inside it.
  - **`evals/checks.py` is not touched.** It is frozen by SHA-256 in `tests/test_evals_freeze.py:32-58`, and a wrapper there would move eval scoring into an unfrozen file. A parity test runs `blocks.py` and `checks._top_level_blocks` over one shared corpus of replies (`tests/fixtures/visual-blocks/`) and requires the same blocks (design review cycle 2).
  - **Residual (operator choice 2026-11-12):** the browser also draws a visual nested in a blockquote or list item (`markdown.js:200-211`, `:356-358`; `codeBlockRenderers` applies at any depth, `:925-937`). The platform conversion does not. A nested chart or widget goes out as source, as today. This is recorded in `docs/chart-format.md`, `docs/widget-format.md` and the connectors README. The prompt tells models to write blocks at the top level.
- **The plan:** `the_one/visuals/outbound.py` turns the reply text (a copy) into a segment-based `OutboundPlan`. Segments are text runs, widget notes and charts, in order; each chart carries its index, title, spec and source block.
  - **Rendering text:** `plan.render(drawn: set[int]) -> str` writes a marker for each chart whose index is in `drawn` and the chart's source block for every other chart. Widgets always become the note.
  - **`fallback_text`** is `plan.render(set())`.
  - **The cap:** the plan applies the 10-image cap (DD6). Only the first 10 accepted charts are candidates.
  - The plan is pure and draws nothing. Markers are never searched for by string, so two charts with the same title cannot be confused.
- **The helper:** one async helper in `the_one/connectors/delivery.py`, the envelope-free module both send paths reach, takes `(client, target, content)` and returns `(SendResult, images_sent)`.
  - **No visual block:** it calls `client.send(target, content)`, byte-identical to today, so every existing Discord, Telegram and stub test stays on the same path.
  - **Widgets but no drawable chart:** it calls `client.send(target, plan.text)`.
  - **At least one candidate chart:** it draws the images in `asyncio.to_thread`. `drawn` is the set of charts that drew without error.
    - If `drawn` is empty, it calls `client.send(target, plan.fallback_text)`.
    - Otherwise, if the client has `send_visual`, it calls that with `plan.render(drawn)` and the drawn images.
    - If the client has no `send_visual`, or `send_visual` raises `VisualUploadError` (DD8), it calls `client.send(target, plan.fallback_text)`.
  - **Import direction:** `the_one/tools/connector_send.py` already imports from `the_one/connectors/` (`:42`). Leg 3 confirms `delivery.py` imports nothing from `tools/`; it duplicates the tool's constants inline (`delivery.py:28-29`, pinned equal by `tests/test_connector_send_tool.py::test_shared_constants_pin_inbound_literals`), so there is no cycle.
- **Save timing:** `deliver_final_reply` is awaited before the chat is saved (`inbound.py:457` before `:459-461`), so drawing and upload time delays the save. DD10 bounds both.

**DD2 — The platforms are faked, never live** (operator choice, 2026-11-11: "we can't really control what they see, we can only control what we send")
- **The fake:** `scripts/fake_platforms.py` is a developer tool, never imported by `the_one/`. It is a standalone local server (FastAPI + uvicorn) on `127.0.0.1`, port 8490 or higher. It follows the existing in-process fixtures `tests/_discord_gateway_fixture.py` and `tests/_telegram_api_fixture.py`, which already model the clients' protocol needs.
- **URL layout:** Discord REST at `/discord/api/v10`, the Discord gateway at `ws://…/discord/gateway`, and Telegram at `/telegram` (so `/telegram/bot{token}/{method}`).
- **Discord REST:**
  - `GET /gateway/bot` returns the fake's `ws://` gateway URL.
  - `GET /users/@me` (connector doctor, `discord/plugin.py:377`).
  - `GET /channels/{id}` returns `type` and `name`, which `_translate_message_create` needs on every channel-cache miss (`plugin.py:188`, `:101`; `_rest.py:132`).
  - `POST /users/@me/channels` (create DM).
  - `POST /channels/{id}/messages`, as JSON and as multipart.
- **The Discord gateway:**
  - Plain JSON frames with no zlib or sharding (`_gateway.py:25`); the client appends `/?v=10&encoding=json` (`:247`).
  - HELLO first. READY with `session_id` and `user.id` must follow IDENTIFY, or every `MESSAGE_CREATE` is dropped (`_gateway.py:202-204`, `plugin.py:171-175`).
  - Heartbeat ACKs, or the client closes itself every interval (`_gateway.py:285-295`).
  - RESUMED, or op 9 Invalid Session, for an op 6 RESUME (`_gateway.py:235-240`), if READY carries `resume_gateway_url`.
  - Dispatch of an injected `MESSAGE_CREATE`.
- **Telegram:**
  - `getMe`.
  - `getUpdates`, which honours `offset` (an update at or below it is never redelivered). It holds the request for up to `timeout` seconds and releases early when an update is injected. The client's poll loop has no sleep (`telegram/plugin.py:226-241`), and `connect()` resolves only after the first `getUpdates` returns (`:227-230`).
  - `sendMessage`, and `sendPhoto` as multipart.
- **Control routes** under `/_control/`:
  - `health`;
  - inject a Discord message (DM by default, since admission needs a DM, a mention or `always_listen`, `inbound.py:121-126`);
  - inject a Telegram update;
  - `received`: every received request with its JSON body, multipart fields, and per file the size, SHA-256 and decoded PNG dimensions;
  - save received files to `--save-dir`;
  - fail the next N uploads with a chosen status;
  - reset.
- **The app-side seam:** in the `app.py` lifespan, beside the stub's dual gate (`app.py:451-456`), and read from the process environment only (not `.env`).
  - It applies when `settings.dev_mode` is true and `THE_ONE_FAKE_PLATFORMS_URL` is set. The lifespan then calls `discord.register(rest_base_url=…, gateway_url=…)` and `telegram.register(base_url=…)`. Both `register()` functions gain keyword-only URL parameters, defaulting to the real URLs, and the connector packages read no environment.
  - The constructors already take these: `DiscordPlugin(rest_base_url=…, gateway_url=…)` (`discord/plugin.py:266-290`) and `TelegramPlugin(base_url=…)` (`telegram/plugin.py:195`).
  - The URL's host must be a loopback IP literal (`127.0.0.1` or `::1`; no host names). Anything else is refused with a logged error and the real URLs are used.
  - The Discord gateway URL is passed explicitly as `gateway_url=` (`discord/plugin.py:266`), built from the checked base with a `ws://` scheme (design review cycle 2). The client then never follows a gateway URL the fake returns. The fake's READY carries no `resume_gateway_url`, so a RESUME also stays on the checked URL.
  - The result: a bot token typed into a dev instance never leaves the machine through this seam.
  - Production never reads the variable.
- **Residual** (written into SECURITY-MODEL.md and the connectors README): the fakes prove the app sends what the platform documentation asks for. They cannot prove that Discord or Telegram accept it or show it as intended. A platform-side change shows up as an upload error, which falls back to text (DD7).

**DD3 — What converts, and what does not**
- **Converted:** `delivery.deliver_final_reply` (the automatic reply) and `SendToPlatformChannelTool.execute` (the agent's send). The agent's send is also the only way a routine run reaches a platform: a run gets a fresh web session (`routines/runner.py:249`), and only the tool posts.
- **Not converted:** `send_step_limit_line` (fixed text) and anything the operator types (never forwarded).
- **Charts:**
  - A closed top-level chart block that `parse_chart` accepts becomes an image.
  - A chart that fails `parse_chart`, or is unterminated, stays as it is. The app shows an error or cut-off notice for it.
- **Widgets:** a top-level widget block, closed or not, becomes the widget note.
- **The Rich visuals switch** does not matter. A visual block is converted whether the switch is on or off, because the switch only stops the agent being told about visuals (mission decision).
- **The tool's return string:** the send tool still returns its `[platform-send-ok]` line, with `(N image(s))` added when images went out. The prefix and the no-double-send rule (`delivery.py:92-109`) are unchanged.

**DD4 — The font and the text layout engine**
- **The font files:** two static TTFs, Geist Regular and SemiBold, from the same upstream release as the bundled `.woff2` (vercel/geist-font 1.8.0, SIL OFL 1.1).
  - They are vendored in `the_one/visuals/fonts/` with a copy of the licence. The browser keeps loading its `.woff2`, and the TTFs are not served to it.
  - Packaging:
    - `pyproject.toml` package-data gains `visuals/fonts/*`;
    - each freeze spec gains the `visuals/fonts` data (Windows ~156, Linux ~63, macOS ~81, beside the existing `collect_data_files` calls);
    - a test asserts every spec names it.
  - Leg 1 first checks that both files exist in that release under the OFL. A test pins their SHA-256 values.
- **Why TTF:** reading WOFF2 needs a FreeType built with Brotli, which is unchecked on the Windows and macOS wheels.
- **The layout engine: `ImageFont.Layout.BASIC`, pinned** in `chart_image.py` and in the doctor gate, and asserted by a test.
  - Pillow defaults to RAQM only when raqm can load. The Pillow wheel ships FreeType and HarfBuzz but not FriBiDi, so RAQM is available on this host only because the host has `libfribidi.so.0`. Windows, macOS and some AppImage hosts get BASIC.
  - Design review cycle 1 measured the difference on Geist: `getlength("AV")` is 16.0 under BASIC and 14.75 under RAQM.
  - BASIC draws without kerning on every host. Layout widths come from design units, not from BASIC's hinted advances (see Measurement below).
  - The cost is that server text sits slightly wider than the browser's kerned text. That is acceptable; Flight 4 (alignment) may revisit it.
- **Measurement, in design units** (design review cycle 2):
  - **Why:** hinted BASIC advances depend on the FreeType version and its build options, not only on the Pillow version, and `pip install` resolves `pillow>=13.0`.
  - **How:** layout measures every string from the font's own design units. The font is loaded once at `size = unitsPerEm`, where `getlength` returns the exact integer advances (for example `"0"` = 663 at 1000), and the result is scaled to the drawing size.
  - **Result:** the width is a property of the SHA-pinned font file. It is the same on every platform and every FreeType, and closer to the browser's unhinted measure. This is how `docs/chart-format.md` "Text width" requires a server renderer to measure.
  - **Sizes:** text is laid out in logical pixels (11 for ticks and axis labels, as in `components.css`; title and legend sizes are set in Leg 1) and drawn at 2×.
  - **Drawing:** glyph pixels are still rasterised by FreeType under BASIC, so their exact pixels may vary slightly between FreeType builds. Positions and layout do not.
- **Glyph coverage:** Geist covers Latin, Latin Extended, Greek and Cyrillic, but not CJK or emoji.
  - A missing character is drawn as the font's missing-glyph box. This is a documented residual in `docs/chart-format.md`.
  - The chart's title also goes out as platform text (the marker, the caption, Discord's alt text), drawn by the reader's own fonts.
- **Thread safety:** the font objects are cached at module level, and all drawing runs under one module-level lock. Two concurrent replies draw one after the other.

**DD5 — The image: light theme, fixed size, double density; approved by sample sheet** (theme: operator choice 2026-11-11)
- **Colours:**
  - The light palette from `css/tokens.css` lines 313-321 and the light `--fg`, `--fg-secondary`, `--border`, `--border-strong` and `--surface` values are kept as Python constants. A test parses `tokens.css` and pins them equal, with no runtime CSS read.
  - The card background is `--surface` (`#fafafa`) with a 1px `--border` edge.
- **Size, in logical pixels, drawn at 2×:**
  - Cartesian and pie charts: width 640, the browser's SVG height of 240 (`chart-scale.js:25`, the whole drawing including the axis label), plus a title row and a legend row when the chart has more than one series.
  - Sparklines: 320 × 64.
- **Content:** the image draws the title, axes, ticks, axis labels, the legend, reference lines and the series, following `docs/chart-format.md`:
  - number display;
  - bars include 0;
  - log ticks at powers of 10;
  - colours repeat after 8;
  - dashes on line series 5 and up;
  - `4 3` reference dashes.
- **Layout:** the browser's layout rules are mirrored (`chart-scale.js` `buildAxis`/`niceStep`/`computeStacks`; `chart-layout.js` margins, label thinning and `fitText`), with text measured from the font.
- **The shared tick corpus:** `tests/fixtures/charts/ticks.json` gives, for every valid cartesian spec, the expected y (and y2) tick values. These are width-independent (`buildAxis`, `niceStep`, `chart-scale.js:168`, `:184`).
  - Python asserts it against `chart_image`'s scale code.
  - The browser asserts it in `tests/browser/test_ui_chart_contract.py` (lane `contracts-chat`, both engines).
  - **Not shared:** x-label thinning depends on measured text width, which differs between the renderers and between Chromium and WebKit. Each renderer pins its own (design review cycle 2).
  - This makes "one format, two renderers" a pinned contract for parsing, number display and the value axis.
- **Format:** PNG, RGB with no alpha and no metadata. Tests compare decoded pixels (a hash of `Image.tobytes()`), never PNG bytes, because zlib output can differ across builds.
- **Approval:** Leg 1 ends with a sample sheet, one PNG per valid corpus spec, plus an at-limit spec and a spec with a CJK title (showing the missing-glyph residual), which the operator approves before Leg 3 starts. Adjustments to margins, the legend and the sparkline land in Leg 1.

**DD6 — Platform layout: text, then images** (mockup A, operator choice 2026-11-11)
- **The chart marker:** a drawn chart becomes its own line.
  - With a title: `📊 Chart: {title} (below)`. Runs of whitespace and newlines in the title collapse to one space.
  - Without a title: `📊 Chart {n} (below)`, where `n` counts every top-level chart block in the reply, in order, so numbering does not depend on which charts drew.
- **The widget note:** a widget becomes `🧩 Interactive widget: open this chat in the app to see it.`
- **Discord:**
  - One message, with the text as `content` and every image as an attachment: a `files[n]` part plus a `payload_json.attachments[n]` entry.
  - The attachment's `description` (alt text) is the chart's title, or `Chart {n}`; `filename` is `chart-{n}.png`.
- **Telegram:**
  - The text goes through the existing `sendMessage` path (HTML render, then a plain-text retry).
  - Then one `sendPhoto` per image, in order, captioned with the title (or `Chart {n}`), truncated to 1024 characters. The target's `message_thread_id` applies when it has one.
- **Cap:** at most 10 images per reply, which is Discord's attachment limit. Charts beyond 10 stay as code (DD7). Long text is not split, as today.
- **Mockup** (approved 2026-11-11):
  ```
  DISCORD (one message)                    TELEGRAM (text, then photo)
  Here's the quarter by region.            [msg 1] Here's the quarter by region.
                                                   📊 Chart: Revenue by region (below)
  📊 Chart: Revenue by region (below)              North led, West grew fastest.
                                           [msg 2] <photo>  caption: Revenue by region
  North led, West grew fastest.
  [image: Revenue by region, light card]   WIDGET block → line in the text:
                                             🧩 Interactive widget: open this chat in
                                                the app to see it.
  ```

**DD7 — On failure, the block as code** (operator choice 2026-11-11)
- **A chart `parse_chart` rejects:** it stays as code in the text, with no image (DD3).
- **A chart that raises while drawing:** it is left out of `drawn`, so `plan.render(drawn)` writes its source block in place (DD1). It is logged with its index, never its data.
- **Retrying only what was not delivered:** a re-send happens only when the platform answered with a status that means nothing was posted, which is a 4xx (including a 413, and a 429 after its one retry). The rules below follow from that (design review cycle 2):
  - A 5xx, a timeout or a transport error is "maybe posted". It is never re-sent.
  - Transport errors (`httpx` exceptions) are mapped to `ConnectorClientError` on both platforms. Today `_rest.py:101-110` and `_api.py:45-49` map HTTP statuses only.
- **Discord:**
  - If the multipart upload gets a 4xx, `send_visual` raises `VisualUploadError`, and the helper sends `fallback_text` once through `send`.
  - A 5xx or a transport error raises a plain `ConnectorClientError`, with no re-send. The reply stays operator-only, as a failed text send does today.
- **Telegram:**
  - If the text `sendMessage` fails, `send_visual` raises `ConnectorClientError` and the reply stays operator-only, as today.
  - If a `sendPhoto` gets a 4xx after the text went out, that chart's source block (`OutboundImage.fallback`) is sent as a follow-up text message.
  - On a 5xx or a transport error, the photo is logged and skipped, with no fallback text, because it may have been posted.
  - The remaining photos are still attempted, within the DD10 budget.
- **Logging:** every fallback logs one warning with the chart indices, the platform and the status, never the chart's data.
- **A client without `send_visual`:** `fallback_text` goes through `send`.
- **Success:** the reply turns peer-visible (`delivery.py:144`) when its text reached the platform, whether or not every image did. That matches today's text-only rule.

**DD8 — The connector contract: an optional `send_visual`**
- **Unchanged:** `ConnectorClient` (`base.py:152-165`, a structural Protocol of `is_alive` and `send`).
- **New types, defined in the leaf package and re-exported** (the project's canonical-import + convenience-re-export pattern):
  - `OutboundImage(filename: str, data: bytes, title: str, width: int, height: int, fallback: str)` is a frozen dataclass defined in `the_one/visuals/outbound.py`. `fallback` is the chart's source as a fenced code block.
  - `VisualUploadError(ConnectorClientError)` is defined in `the_one/connectors/base.py`.
  - `connectors/base.py` re-exports `OutboundImage`. `visuals` imports nothing from `connectors`, so the leaf stays a leaf (`visuals/__init__.py:1`).
- **The optional method:** `async def send_visual(self, target, content: str, images: Sequence[OutboundImage]) -> SendResult`.
  - It is found with `getattr(client, "send_visual", None)`, as `history` is (`tools/connector_history.py:96`).
  - Discord, Telegram and the stub implement it.
- **Errors:**
  - It raises `VisualUploadError` when the platform answered with a 4xx, so nothing was posted and a text resend is safe.
  - It raises another `ConnectorClientError` when the send failed in a way that must not be retried.
  - Otherwise it returns `SendResult.details` with `{"images_sent": n, "images_failed": m}`.

**DD9 — The stub's records**
- **The tuple stays:** `StubPlugin.outbound_records` stays `list[tuple[SendTarget, str]]`. It is read by tuple unpacking in `tests/test_connectors_inbound.py`, `test_connector_send_tool.py` and `test_connector_routes.py`, and cleared directly by `test_routines_runner.py:76`.
- **Images:** `StubClient.send_visual` honours `send_should_raise`. It appends a `StubVisualRecord` to `outbound_records`, a `tuple` subclass of `(target, content)` with an `.images` attribute (design review cycle 2).
  - Unpacking, `== [(t, c)]` and `[c for _, c in …]` all work unchanged.
  - The images travel with their record through any `clear()`, append or slice that tests do (`tests/test_routines_runner.py:76`, `test_connector_routes.py:586`).
- **The route:** `GET /api/_test/stub/outbound` (its loop is at `api.py:5249`) reads `getattr(rec, "images", None)`. It adds an `images` key **only** to records that have images: `[{filename, title, width, height, size, sha256}]`, with no bytes.
  - Text-only records keep exactly today's four keys, so `tests/test_connector_routes.py:586-593`'s exact dict check and the 6 behavior specs' key reads are untouched.

**DD10 — Bounds**
- **Drawing work:** bounded by the format's own limits (`MAX_VALUES = 2000`, `MAX_SERIES = 8`, `MAX_CATEGORIES = 200`, `MAX_SLICES = 12`, `MAX_ANNOTATIONS = 5`; `chart_spec.py:19-24`).
- **Drawing time:** a synthetic at-limit spec (2000 values over 8 series, a log axis, 5 annotations) must draw in under 500 ms on this host, pinned by a test with generous headroom for a loaded host and an environment override for the bound. There is no runtime drawing timeout, because a `to_thread` worker cannot be stopped; the format limits are the bound.
- **Upload time** (design review cycle 2):
  - **The per-call retry policy:** every request this flight adds, and the `fallback_text` resend after a `VisualUploadError`, retries a 429 at most once, with `retry_after` clamped to 10 s. The resend's policy is applied on the call, so Discord's existing three-retry, unclamped path (`_rest.py:18`, `:94-104`) does not apply to it.
  - **Existing text sends are unchanged:** Discord's `create_message` keeps its three-retry path, and Telegram's `sendMessage` keeps its 60 s clamp (`_api.py:24`, `:93-104`).
  - **Telegram's photo budget:** the poll loop awaits the whole turn (`telegram/plugin.py:236-238`), and `is_alive` turns false after 110 s without a poll (`plugin.py:22-23`, `:132-137`). So the photos for one reply share a 45 s budget.
    - Photos not uploaded when it runs out go as their source blocks in one follow-up text message (a 4xx-style fallback: nothing was posted for them).
    - The connectors README states this budget against the 110 s liveness window.
- **Size:** a PNG over 8 MB is treated as a drawing failure. That cannot happen at these sizes, but stating it keeps both platforms' 10 MB limits out of play.

**DD11 — Request shapes pinned to the documented API**
- **Discord:** `POST /channels/{id}/messages` as `multipart/form-data`, with a `payload_json` part (`{"content", "attachments": [{"id", "filename", "description"}]}`) and `files[n]` parts (`image/png`).
  - `RestClient._request` (`_rest.py:87`, JSON only) gains a `files=` path on the same rate-limit bucket, plus a per-call retry policy (DD10).
  - Transport errors become `ConnectorClientError` (DD7).
- **Telegram:** `POST /bot{token}/sendPhoto` as `multipart/form-data`, with `chat_id`, `photo` (`image/png`), `caption` and an optional `message_thread_id`.
  - `TelegramApiClient._post` (`_api.py:45-49`, JSON only) gains a multipart path with the same error mapping in `_handle_response`.
  - The 429 retry (today inside `send_message`, `:93-104`) is factored so `send_photo` uses it with DD10's clamp.
- **Tests:** unit tests use an `httpx.MockTransport` that parses the multipart body and asserts each field. The fake server (DD2) parses the same way.

**DD12 — The `chart images` doctor gate (the thirteenth)**
- **The probe:** `_probe_chart_images` in `the_one/diagnostics.py`, run on every host (not frozen-only).
  - It loads both bundled TTFs with `Layout.BASIC`.
  - It measures a fixed reference string in design units (DD4) and requires the exact expected integer width. That is a property of the font file, so it is the same on every platform, Pillow version and FreeType build.
  - It draws a fixed reference chart and checks its pixel dimensions.
  - Its detail line is ASCII-only, since the Windows console needs that (`the_one/agents.md` gate-table note, about `:1927`). It prints the width, the layout engine, `PIL.__version__` and `features.version("freetype2")`.
- **Gate lists to update:**
  - `the_one/diagnostics.py` `run_doctor` (`:1172`, `gates = [` at `:1268`, and the docstring count);
  - `packaging/windows/build.ps1` (`:52`, `:365`) and `packaging/windows/README.md:53`;
  - `scripts/windows_test_copy.py:101`;
  - `tests/test_windows_build_recipe.py:161`;
  - `tests/test_doctor.py` (the order checks);
  - `tests/test_windows_test_copy.py:452` (the doctor-output fixture);
  - `the_one/agents.md` (the gate table, about `:1924`);
  - CLAUDE.md's gate count;
  - the notes in `packaging/macos/checks.sh` (about `:85`) and `packaging/linux/checks/gates-inner.sh` (about `:139`), where those list gates.
- **"Same text rendering on every platform"** means the gate passes, with the same reference width, in the Linux, Windows and macOS packaged builds (Leg 2).

### Citation Audit

Verified against the working tree at `6d22eabc` (re-checked by the Architect, design review cycle 1). Flight 3 branches from `origin/main` `f76efdd3`, which is `6d22eabc`'s tree squashed.

| Citation | Status |
|---|---|
| `the_one/connectors/base.py:153` `class ConnectorClient(Protocol)` with `is_alive` (`:156`) and `async def send(self, target, content: str) -> SendResult` (`:160`) only; `:16-17` import `db.models` and `encryption` | verified |
| `the_one/tools/connector_history.py:96` — `getattr(client, "history", None)` | verified |
| `the_one/connectors/delivery.py:128` — `await client.send(target, final.content)`; `:62` step-limit send; `:144` visibility flip on success; `:28-29` constants duplicated inline; `:92-109` skip rule | verified |
| `the_one/tools/connector_send.py:195` — `result = await client.send(send_target, content)`; only `ConnectorClientError` caught; `:42` imports from `the_one.connectors` | verified |
| `the_one/connectors/inbound.py:457` delivery awaited before `:459-461` persist; `:121-126` admission | verified |
| `the_one/connectors/discord/_rest.py:87` `_request(method, path, *, json=None, params=None)` JSON only; `:101-110` HTTP statuses only raise; `:124` `create_message`; `:132` `get_channel` | verified |
| `the_one/connectors/discord/_gateway.py:25` `GATEWAY_QUERY`; `:202-204` READY `user.id`; `:235-240` resume; `:285-295` heartbeat ACK | verified (Architect) |
| `the_one/connectors/discord/plugin.py:266-290` constructor `gateway_url`, `rest_base_url`, `rest_transport`; `:171-175`, `:188` message translation; `:377` doctor `GET /users/@me` | verified |
| `the_one/connectors/telegram/_api.py:45-49` `_post` JSON only; `:93-104` 429 retry inside `send_message`; `:24` 60 s clamp | verified (Architect) |
| `the_one/connectors/telegram/plugin.py:195` constructor `base_url`, `api_transport`; `:226-241` poll loop with no sleep | verified |
| `the_one/connectors/discord/__init__.py` / `telegram/__init__.py` `register()` builds the plugin with defaults | verified |
| `the_one/connectors/stub.py:41` append; `:53` `outbound_records`; `:63-72` `reset_for_test` | verified |
| `the_one/interfaces/web/api.py:5238` `stub_test_outbound`; `tests/test_connector_routes.py:586-593` exact dict check | verified (Architect) |
| `the_one/interfaces/web/app.py:451-456` stub dual gate in the lifespan | verified |
| `evals/checks.py:310` `_top_level_blocks(reply, tag="chart") -> list[tuple[str, bool]]` | verified |
| `static/js/markdown.js:200-211`, `:356-358`, `:925-937` nested code blocks get `codeBlockRenderers` | verified (Architect, node run) |
| `static/js/ui/chart-scale.js:25` `HEIGHT = 240` (the whole SVG) | verified |
| `the_one/visuals/chart_spec.py:19-24` limits; `visuals/__init__.py:1` "Standard library only" | verified |
| `the_one/diagnostics.py:1172` `run_doctor`; `:1268` `gates = [` (12) | verified |
| `the_one/llm/mock.py:98-106` returns the same `response` on every call | verified (Architect) |
| `pyproject.toml:164` pillow in `[gui]`, `:169` in `[dev]`, not base; `:196` package-data globs | verified |
| Pillow 13.0.0 / FreeType 2.14.3; raqm loads only via the host's `libfribidi.so.0` | verified (Architect, measured) |

### Prerequisites
- [x] PR #365 (Flight 2) merged to `main` (`f76efdd3`, 2026-11-12). Flight 3 branches from `origin/main` as `flight/03-visuals-on-chat-platforms`.
- [ ] Geist 1.8.0 static TTFs available upstream under the OFL (Leg 1 verifies before vendoring).
- [ ] `uv` available to re-lock after moving Pillow to the base dependencies (`uv lock`, then `uv sync --all-extras --frozen`).
- [ ] Leg 2, re-verified at its start: the Linux container gate suite runs locally; the Concourse `platform: windows` worker (or `scripts/windows_test_copy.py freeze` with the operator at the desktop) is available; `gh auth status` is good for a hosted macOS dispatch; each outward dispatch is confirmed by the operator at the time.
- [x] No model calls: no prompt text changes in this flight, and the mock provider scripts every reply.
- [x] The other session's uncommitted `the_one/db/_notes.py`, `tests/test_prompt_layers.py`, `tests/behavior/agent-notes-round-trip.md` and `env.sh` are never staged by this flight.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [ ] Prerequisites verified (Legs 1 and 2 verify theirs at start)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
1. **Draw (Leg 1).**
   - Move Pillow to the base dependencies.
   - Vendor the TTFs.
   - Write `the_one/visuals/chart_image.py` (`render_png(spec) -> OutboundImage`-ready bytes and size). It imports Pillow lazily, runs under BASIC, holds the lock, and takes the palette from constants pinned to `tokens.css`.
   - Add the shared tick corpus, asserted in Python and in the browser contract.
   - Add the doctor gate.
   - Produce the operator's sample sheet.
   - Update `the_one/visuals/__init__.py`'s docstring: `chart_spec.py`, `blocks.py` and `outbound.py` stay standard-library only, and `chart_image.py` uses Pillow lazily.
   - Add an AST guard, extending the one in `tests/test_chart_spec.py:158`: within `the_one/visuals/`, only `chart_image.py` imports `PIL`.
2. **Prove on every platform (Leg 2).** Run the doctor gate in the Linux, Windows and macOS packaged builds before anything is built on the renderer.
3. **Plan and wire (Leg 3).**
   - Write `blocks.py` and `outbound.py`.
   - Add `OutboundImage` and `VisualUploadError`.
   - Write the delivery helper and call it from both send paths.
   - Implement the stub's `send_visual` and records.
4. **Upload (Leg 4).**
   - Discord multipart and Telegram `sendPhoto`, with the DD7 fallbacks and the DD10 retry clamp.
   - Mock-transport shape tests.
5. **Fake (Leg 5).** Write `scripts/fake_platforms.py`, with a unit test of its protocol and multipart parsing.
6. **Seam and round trip (Leg 6).**
   - Add the loopback-only lifespan seam and its gating tests.
   - Update the docs: CLAUDE.md test seams, SECURITY-MODEL.md residual, connectors README.
   - Finalize and run `charts-reach-platforms`.

### Checkpoints
- [ ] Every valid corpus spec and the at-limit spec draw. The tick corpus passes in Python and in both browser engines. The doctor gate passes locally. The operator approves the sample sheet (Leg 1).
- [ ] The doctor gate passes, with the same reference width, in the Linux, Windows and macOS packaged builds (Leg 2).
- [ ] Both send paths convert through one helper. Plain replies are byte-identical to today. The stub records carry images, and no existing stub reader changed (Leg 3).
- [ ] The Discord and Telegram multipart shapes are pinned by mock-transport tests, and every DD7 fallback path is covered (Leg 4).
- [ ] The fake passes its own unit tests and serves both real clients in-process (Leg 5).
- [ ] `charts-reach-platforms` passes against the fakes for both platforms (Leg 6).

### Adaptation Criteria

**Divert if**:
- The Geist static TTFs are not available under the OFL at 1.8.0, or a TTF does not load in a packaged build. Re-plan the font with the operator.
- The design-unit reference width or the reference image dimensions differ between packaged builds (Leg 2). This should be impossible for one SHA-pinned font; investigate the font bundling first, and record the operator's decision.
- The operator does not approve the sample sheet after two revision rounds. Raise it as an alignment question for Flight 4 rather than iterating inside Leg 1.
- The Discord gateway fake needs more than the HELLO, IDENTIFY, READY, heartbeat, RESUME and dispatch subset. Drop Discord's inbound path from the behavior test and drive Discord through the agent's tool instead, with the operator's agreement.

**Acceptable variations**:
- Exact margins, legend placement and the sparkline size, within DD5's envelope, as approved on the sample sheet.
- Telegram `sendMediaGroup` instead of one `sendPhoto` per image, if Leg 4 finds it simpler with the same captions and fallbacks.
- Legs 4 and 5 swapping order, if the fake is useful to Leg 4's development.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `chart-image-renderer` - Pillow to base dependencies (re-lock; move the CVE-floor comment; keep or drop the `[gui]`/`[dev]` entries deliberately; update the `.github/workflows/pr-lint.yml` comment), the vendored Geist TTFs in `the_one/visuals/fonts/` with package-data and the three spec entries, `chart_image.py` (BASIC, lock, lazy import, pinned palette), design-unit text measurement, the shared y-tick corpus asserted in Python and in `test_ui_chart_contract.py`, the at-limit timing test, the `chart images` doctor gate and every gate list, `docs/chart-format.md` "Images" section, ends with the operator-approved sample sheet (DD4, DD5, DD10, DD12)
- [ ] `three-platform-font-check` - the doctor gate in packaged builds: Linux container gates locally, the Windows freeze, a hosted macOS dispatch (operator-confirmed); reference widths compared and recorded (DD12). Depends only on Leg 1.
- [ ] `outbound-visuals` - `blocks.py` with its parity test against the frozen `evals/checks.py:_top_level_blocks` (`checks.py` untouched), `outbound.py` (`OutboundPlan`, `OutboundImage`, markers, the widget note, fallback text), `VisualUploadError` and the re-export in `connectors/base.py`, the delivery helper used by `deliver_final_reply` and `send_to_platform_channel` (plain replies unchanged), the stub's `send_visual` with `StubVisualRecord` and the route's `images` key, the nested-block residual in the docs (DD1, DD3, DD6, DD7, DD8, DD9). High risk: shared interface.
- [ ] `platform-uploads` - Discord multipart in `RestClient` (transport errors mapped, no re-send) and `DiscordClient.send_visual`; Telegram multipart `sendPhoto` with the factored 429 retry and `TelegramClient.send_visual` with per-photo fallback; mock-transport shape tests for every DD7 path (DD6, DD7, DD10, DD11)
- [ ] `fake-platforms` - `scripts/fake_platforms.py` (Discord REST and gateway, Telegram long-poll with offset, `sendPhoto`, control routes), modelled on the two in-process fixtures, with unit tests (bound to port 0) that run the real Discord and Telegram clients against it in-process (DD2)
- [ ] `seam-and-round-trip` - the dev-gated, loopback-only `THE_ONE_FAKE_PLATFORMS_URL` seam in the lifespan with keyword URLs on both `register()` functions and its gating tests, CLAUDE.md test-seams table, SECURITY-MODEL.md residual, connectors README; a start-of-leg check that a connector turn rebuilds the agent and provider per inbound message, so step 9's API changes apply without a restart; `charts-reach-platforms` finalized (step 9 with the agent's `max_iterations` set to 1, expecting the step-limit line) and run (DD2)

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification
- `make test-unit` passes, including:
  - the corpus drawing, tick-corpus, at-limit and font-pin tests;
  - the outbound-plan tests;
  - the multipart shape tests;
  - the unchanged stub reader tests;
  - the fake's tests;
  - the seam gating tests.
- `THE_ONE_REQUIRE_WEBKIT=1` `contracts-chat` passes with the tick corpus in both engines.
- `/mission-control:behavior-test charts-reach-platforms` passes. It covers the Discord auto-reply, the Telegram auto-reply, the agent's tool send, a widget note, the upload-failure fallback and the unchanged stored chat.
- `the-one doctor` shows `chart images` passing, with the same reference width, in the Linux, Windows and macOS packaged builds.
- The operator approved the Leg 1 sample sheet.
