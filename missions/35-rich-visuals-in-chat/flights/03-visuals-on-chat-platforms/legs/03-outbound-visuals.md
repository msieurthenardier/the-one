# Leg: outbound-visuals

**Status**: completed
**Flight**: [Visuals on Chat Platforms](../flight.md)

## Objective
Both connector send paths (the automatic reply and `send_to_platform_channel`) turn a reply's top-level chart and widget blocks into marker lines, widget notes and drawn images through one shared helper. A client without `send_visual` gets the text fallback, the stub records the images, and a reply with no visual block is sent byte-for-byte as today.

## Context
- **Flight design decisions:** DD1 (block finder, the parity test, the segment plan, the helper, drawing in `to_thread`, the nested-block residual), DD3 (what converts), DD6 (marker, widget note, numbering, cap), DD7 (fallbacks: 4xx-only resend, logging, success rule), DD8 (`OutboundImage`, `VisualUploadError`, the optional `send_visual`) and DD9 (the stub's `StubVisualRecord` and the route's `images` key).
- **Leg 1** (committed `ba547e29`) gives:
  - `the_one/visuals/chart_image.py::render_png(spec: ChartSpec) -> RenderedChart(data, width, height)`, which raises `ChartImageError` and holds a process lock (`render_png` at `:1076`);
  - `chart_spec.parse_chart(source) -> ChartSpec | ChartError`.
- **Leg 4** adds `send_visual` to Discord and Telegram. Until then those clients have none, so after this leg they receive `fallback_text`: charts as code, as today, and widgets as the note. That is the designed fallback (DD7, "a client without `send_visual`").
- **Refinement of DD8/DD10, decided at leg design:** DD10 requires the `fallback_text` resend after a `VisualUploadError` to run under the clamped per-call 429 policy, but `ConnectorClient.send(target, content)` has no policy parameter. So the helper resends through `getattr(client, "send_visual_fallback", None) or client.send`. It is a second optional method, found the same way as `send_visual`. Leg 4 implements it on Discord and Telegram with the clamp. Without it (the stub, or any other client), a plain `send` is used.
- **High risk:** this is a shared-interface change with existing consumers. It touches `deliver_final_reply`, the send tool, the stub (whose `outbound_records` is read by unpacking in 35 places in tests and behavior specs) and the stub route, which has an exact-dict pin.

## Inputs
- `the_one/connectors/delivery.py`: `deliver_final_reply`, which sends with `await client.send(target, final.content)` and flips `final.visibility = None` on success. The module must not import `inbound.py`, `app.py` or `tools/` (its docstring).
- `the_one/tools/connector_send.py` `SendToPlatformChannelTool.execute`: `result = await client.send(send_target, content)`, catching `ConnectorClientError` only, and returning `f"{PLATFORM_SEND_OK_PREFIX} sent to {dest}: {content!r} (msg_id={msg_id})"`.
- `the_one/connectors/base.py`:
  - `ConnectorClient` Protocol (`is_alive`, `send`);
  - `SendResult(platform_message_id, details)`;
  - `ConnectorClientError`.
- `the_one/connectors/stub.py`: `StubClient.send` honours `StubPlugin.send_should_raise` and appends `(target, content)` to the class-level `outbound_records`; `reset_for_test`.
- `the_one/interfaces/web/api.py` `stub_test_outbound` (at about `:5238`): one four-key dict per record. `tests/test_connector_routes.py:586-593` checks it exactly.
- `evals/checks.py:_top_level_blocks(reply, tag)` (`:310`). It is frozen by SHA-256 (`tests/test_evals_freeze.py`) and must not be touched.

## Outputs
- **`the_one/visuals/blocks.py`** (new, standard library only): `Block(tag, body, closed, start, end)`, a frozen dataclass, and `find_blocks(text) -> list[Block]`, which returns the top-level fenced blocks of *every* tag in one pass, under DD1's fence rule. `start` is the index of the opener line's first character. `end` is just past the closer line, including its newline when there is one, or `len(text)` for an unterminated block.
- **`the_one/visuals/outbound.py`** (new, standard library only; it imports only `chart_spec` and `blocks`):
  - `OutboundImage(filename, data, title, width, height, fallback)`, a frozen dataclass.
  - `CHART_MARKER` / `CHART_MARKER_UNTITLED` / `WIDGET_NOTE` text and `MAX_IMAGES = 10`.
  - `ChartCandidate(index, number, title, spec, source)`, with `alt` = the title or `Chart {number}`.
  - `OutboundPlan` with:
    - `segments`;
    - `candidates`;
    - `render(drawn: set[int]) -> str`;
    - `fallback_text`, a property equal to `render(set())`.
  - `plan_outbound(text) -> OutboundPlan | None`. It returns `None` when the text has no top-level widget block and no candidate chart, so the caller sends the original text unchanged.
- **`the_one/connectors/base.py`:**
  - `class VisualUploadError(ConnectorClientError)`;
  - a re-export of `OutboundImage` (canonical import + convenience re-export);
  - Protocol comments documenting the optional `send_visual(target, content, images) -> SendResult` and `send_visual_fallback(target, content) -> SendResult`.
  - The error contract, stated in those comments and in the README: `send_visual` raises `VisualUploadError` **only when nothing of the reply was posted** (the platform answered 4xx before anything went out). Once the text has been posted, a failed image is the client's own per-image fallback (DD7 Telegram), never a `VisualUploadError`. Otherwise the helper's resend would duplicate the text.
- **`the_one/connectors/delivery.py`:** the shared helper, `async def send_reply(client, target, content, *, connector_id: str = "") -> tuple[SendResult | None, int]`. It returns the client's result and `images_sent`.
  - The result is `SendResult | None` because existing fake clients return `None` from `send` (`tests/test_connector_delivery.py:26-33`, `tests/test_routine_turn_path.py:77-82`). The helper dereferences a result only after `send_visual` returns.
  - `deliver_final_reply` and the tool pass their `connector_id` in.
- **`the_one/tools/connector_send.py`:** the tool calls the helper. The success string gains ` (N image(s))` when `images_sent > 0`, written as `(1 image)` or `(N images)`; prefix and form are otherwise unchanged.
- **`the_one/connectors/stub.py`:**
  - `StubVisualRecord(tuple)` with `.images`;
  - `StubClient.send_visual`, which honours `send_should_raise` and the new class-level `send_visual_should_raise`, reset by `reset_for_test`;
  - `outbound_records` keeps its type annotation, widened to the tuple union.
- **`the_one/interfaces/web/api.py`:** the stub outbound route adds `images: [{filename, title, width, height, size, sha256}]` **only** for records that carry images.
- **Fixtures:** `tests/fixtures/visual-blocks/replies.json` (new), the parity corpus.
- **Tests:** `tests/test_visual_blocks.py`, `tests/test_outbound_plan.py` and `tests/test_delivery_visuals.py` (new), plus additions to `tests/test_connector_send_tool.py`, `tests/test_connector_routes.py` and the stub tests.
- **Docs:**
  - `docs/chart-format.md` and `docs/widget-format.md`: a short "On chat platforms" note, including the nested-block residual.
  - `the_one/connectors/README.md`: a "Visuals on platforms" section with the helper, both optional methods, the error contract, `VisualUploadError`, the stub record and the route's `images` key, the nested-block residual, and the 10-image cap.
  - `the_one/agents.md`: a short pointer in the connectors section.

## Acceptance Criteria
- [ ] **AC1:** `find_blocks` implements DD1's fence rule.
  - A parity test runs `find_blocks` and the frozen `evals.checks._top_level_blocks` over every reply in `tests/fixtures/visual-blocks/replies.json`, for tags `chart` and `widget`. For each tag, `[(b.body, b.closed) for b in find_blocks(r) if b.tag == tag]` equals `_top_level_blocks(r, tag)`.
  - The corpus (at least 20 replies) covers:
    - a closed and an unterminated block;
    - a `json` fence swallowing a chart fence;
    - `~~~`;
    - an indented or list-nested fence;
    - a quoted (`> ```chart`) fence;
    - a tag that is not the first token;
    - text before and after;
    - two blocks back to back;
    - CRLF line endings;
    - an empty body;
    - a closer with trailing spaces;
    - a closed block at the end of the text, both with and without a trailing newline;
    - an unterminated block ending in `\n`;
    - a bare, untagged ```` ``` ```` fence swallowing a later chart fence.
  - `evals/checks.py` is unchanged (`tests/test_evals_freeze.py` passes).
- [ ] **AC2:** for every block, `text[b.start:b.end]` is exactly the block's source (opener through closer). A test checks that the original text can be rebuilt from the blocks and the gaps between them.
- [ ] **AC3:** `plan_outbound` returns `None`, and the helper calls `client.send(target, content)` with the identical `content` object and nothing else, in each of these cases:
  - plain text;
  - text with only non-visual fences;
  - text whose only visual blocks are invalid or unterminated charts.
  
  The test checks this with `is`, and checks that `send_visual` is never called when there is no plan.
- [ ] **AC4:** candidates and numbering follow DD3 and DD6.
  - A candidate is a closed, top-level chart block that `parse_chart` accepts.
  - Only the first 10 candidates are kept; any after the 10th stay as their source.
  - `number` counts every top-level chart block in order, valid or not.
  - The marker is `📊 Chart: {title} (below)`, with runs of whitespace (newlines included) collapsed to one space and the result trimmed, or `📊 Chart {number} (below)` when the title is empty.
  - Every top-level widget block, closed or not, becomes `🧩 Interactive widget: open this chat in the app to see it.`
  - Each marker or note replaces its block's span as its own line. A block that ended with a newline is replaced by the line plus `\n`, so the text around it is unchanged.
- [ ] **AC5:** `plan.render(drawn)` writes the marker for each candidate whose index is in `drawn` and the block's original source for every other candidate. `fallback_text == render(set())`. Two candidates with the same title render correctly by index. A test covers a mixed drawn set.
- [ ] **AC6:** the helper's branches (DD1, DD7, DD8), each with its own test using fake clients:
  - **(a)** No plan: `send(target, content)`.
  - **(b)** No candidates but at least one widget: `send(target, plan.fallback_text)`, with 0 images.
  - **(c)** Candidates, none drawn (`render_png` monkeypatched to raise `ChartImageError`): `send(target, plan.fallback_text)`, plus one warning per failed chart naming its index and the connector id, never its data.
  - **(d)** Some drawn, and the client has `send_visual`: called once with `(target, plan.render(drawn), images)`, the images in candidate order. Each `OutboundImage` has `filename=f"chart-{number}.png"`, `title=alt`, the pixel `width` and `height`, `data`, and `fallback` = the block source. The helper returns `images_sent` from `result.details["images_sent"]`, defaulting to `len(images)`. A value that is not an `int` falls back to `len(images)`, and any value is clamped to `0..len(images)`.
  - **(e)** Some drawn, no `send_visual`: `send(target, plan.fallback_text)`, 0 images.
  - **(f)** `send_visual` raises `VisualUploadError`: one resend of `plan.fallback_text` through `send_visual_fallback` when the client has it, else `send`. One warning names the chart indices, the connector id, the client class name (`type(client).__name__`, the platform) and the error message, which the client builds from its status code; the reply text is not logged. The helper returns the resend's result and 0 images.
  - **(g)** `send_visual` raises a plain `ConnectorClientError`: it propagates, with no resend.
  - **(h)** The resend itself raises `ConnectorClientError`: it propagates.
- [ ] **AC7:** drawing runs in `asyncio.to_thread`. A test proves the event loop is not blocked: a concurrent coroutine runs while a slow monkeypatched `render_png` draws. One `to_thread` call draws every candidate.
- [ ] **AC8:** `deliver_final_reply` uses the helper. Visibility flips to `None` exactly when the helper returns, that is, when the text reached the platform (DD7's success rule). Every existing `deliver_final_reply` and inbound test passes unchanged, and so does the skip rule (`delivery.py` no-double-send).
- [ ] **AC9:** `SendToPlatformChannelTool.execute` uses the helper. With images, the success string ends `(msg_id=…) (2 images)`; with none it is byte-identical to today. A `ConnectorClientError` from the helper returns today's `[error] {type}: {msg}` string, including for a `VisualUploadError` whose resend also failed. `test_shared_constants_pin_inbound_literals` still passes.
- [ ] **AC10:** `StubVisualRecord` is a `tuple` subclass of `(target, content)` with `.images`. It is built by `StubVisualRecord(target, content, images)`, whose `__new__` calls `tuple.__new__(cls, (target, content))` and stores `images` as a `tuple[OutboundImage, ...]`. Because `==` ignores `.images`, tests on visual records assert `.images` explicitly. Each of these holds for a visual record, and each is tested:
  - `t, c = rec`;
  - `rec == (t, c)`;
  - `[c for _, c in records]`;
  - `records.clear()`;
  - slicing.
  
  `StubClient.send_visual` raises `send_should_raise` when set, then `send_visual_should_raise` when set, before recording. It returns `SendResult("stub-msg-id", {"images_sent": n, "images_failed": 0})`. `reset_for_test` clears `send_visual_should_raise`.
- [ ] **AC11:** `GET /api/_test/stub/outbound` gives a text-only record exactly today's four keys (`tests/test_connector_routes.py:586-593` unchanged and passing). A visual record also has `images: [{filename, title, width, height, size, sha256}]`, with no bytes. `size` is `len(data)` and `sha256` is `hashlib.sha256(data).hexdigest()`.
- [ ] **AC12:** `connectors/base.py` exports `VisualUploadError` and `OutboundImage`, which is the same object as `the_one.visuals.outbound.OutboundImage`.
  - `the_one/visuals/blocks.py` and `outbound.py` import nothing outside the standard library and `the_one.visuals` (Leg 1's AST guard covers them).
  - `delivery.py` still imports nothing from `inbound.py`, `app.py` or `tools/`.
- [ ] **AC13:** the docs listed in Outputs are updated, and the nested-block residual is stated in `docs/chart-format.md`, `docs/widget-format.md` and the connectors README.
- [ ] **AC14:**
  - `THE_ONE_TEST_NETNS=1 make test-unit` passes with the expected skip count.
  - The 6 behavior specs that read the stub route need no change. They are `directory-lookup-send`, `agent-tells-the-time`, `agent-rules-round-trip`, `agent-schedules-follow-up`, `agent-step-limit-notice` and `stub-connector-round-trip`, and design review verified that they read only the four keys.
  - `ruff check` and `ruff format --check` are clean.

## Verification Steps
- AC1-AC5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_visual_blocks.py tests/test_outbound_plan.py tests/test_evals_freeze.py -x --timeout 30`.
- AC6, AC7: `… tests/test_delivery_visuals.py -x --timeout 30`.
- AC8-AC11: `… tests/test_connectors_inbound.py tests/test_connector_send_tool.py tests/test_connector_routes.py tests/test_routines_runner.py -x --timeout 60`, plus the stub tests.
- AC12: `… tests/test_chart_spec.py -x` (the AST guard); `grep -n "^from\|^import" the_one/connectors/delivery.py`.
- AC14: `THE_ONE_TEST_NETNS=1 make test-unit` (background, wait for the notification); `grep -rn "_test/stub/outbound" tests/behavior/`.

## Implementation Guidance
1. **`blocks.py`.**
   - Port `_top_level_blocks`' line loop, tracking character offsets.
   - Split with `text.split("\n")`, exactly as `checks.py` does, so a `\r` stays at the end of a line and parity holds by construction. Keep running offsets: `line_start += len(line) + 1`.
   - For a closed block, set `end = min(closer_start + len(closer_line) + 1, len(text))`. The `min` matters when the closer is the last line with no trailing newline; without it, `end` would be `len(text) + 1`.
   - `body` is `"\n".join(body_lines) + ("\n" if body_lines else "")`, as `checks.py` builds it.
   - Opener: `re.match(r"```(.*)$", line)`; the tag is the first whitespace token, and any tag is returned. Closer: `re.match(r"```\s*$", line)`.
2. **The parity corpus.** Write `tests/fixtures/visual-blocks/replies.json` (a JSON list of strings) with the Write tool. The test imports `evals.checks` the way the existing `tests/test_evals_*.py` files do.
3. **`outbound.py`.**
   - Segments are `("text", str)`, `("widget",)` and `("chart", ChartCandidate | None, source)`; a non-candidate chart keeps its source verbatim.
   - `render` joins the segments. A replaced segment is the marker or note line, followed by `"\n"` if the block's source ended with `"\n"`.
   - Collapse the title with `" ".join(title.split())`.
   - `fallback` for `OutboundImage` is the block source; fences are already in it, because the span is opener through closer, and a candidate is always closed.
4. **The helper (`delivery.send_reply`).**
   - Draw with `asyncio.to_thread(_draw_all, plan.candidates)`, where `_draw_all` imports `the_one.visuals.chart_image` lazily and returns `{index: RenderedChart}`. It catches `ChartImageError`, and any other `Exception`, per chart.
   - Log a failed draw at warning: `"chart %d could not be drawn for connector %s (%s)"`, with the index, the `connector_id` argument and the exception class name only.
   - Find the optional methods with `getattr`. Never read `.details` from the result of `send` or `send_visual_fallback`.
5. **Callers.**
   - In `deliver_final_reply`, replace `await client.send(target, final.content)` with `await send_reply(client, target, final.content, connector_id=connector_id)`, keeping the existing `except` arms.
   - In the tool, import `send_reply` from `the_one.connectors.delivery`; that is allowed (`connector_send.py:42` already imports from `the_one.connectors`).
6. **Stub and route:** as in Outputs. Keep the route's four keys, built exactly as today, then add `images` only when `getattr(rec, "images", None)` is truthy.
7. **Docs,** then the gates: run `make test-unit` once at the end, in the background.

## Edge Cases
- **A widget block that is unterminated at the end of the text:** it becomes the note, with no trailing newline because the source had none.
- **A chart block directly after text with no blank line:** the marker still goes on its own line, because the block starts at column 0 and so already starts a line.
- **More than 10 valid charts:** the first 10 are candidates, and the 11th onwards stay as code (their source) in every rendering.
- **A candidate whose drawing exceeds 8 MB:** `ChartImageError`, so it is not drawn and stays as its source.
- **Content that is an empty string:** the tool sends today's path; `deliver_final_reply` already skips empty content.
- **Title made only of whitespace:** after collapsing it is empty, so the untitled marker is used.
- **The Rich visuals switch:** it is never consulted (DD3).
- **The tool's success string** still echoes `{content!r}` (today's behaviour), so a reply with a large chart or widget block makes the tool result large. This is unchanged by this leg and recorded as known.
- **Concurrent sends:** the Leg 1 lock serialises drawing. The flight-end review handles `measure()` outside the lock (the checkpoint review's non-blocking item 1). The helper calls only `render_png`, which holds the lock.

## Files Affected
- `the_one/visuals/blocks.py` (new), `the_one/visuals/outbound.py` (new)
- `the_one/connectors/base.py`, `the_one/connectors/delivery.py`, `the_one/connectors/stub.py`, `the_one/tools/connector_send.py`, `the_one/interfaces/web/api.py`
- `tests/fixtures/visual-blocks/replies.json` (new), `tests/test_visual_blocks.py`, `tests/test_outbound_plan.py`, `tests/test_delivery_visuals.py` (new), `tests/test_connector_send_tool.py`, `tests/test_connector_routes.py`, the stub tests
- `docs/chart-format.md`, `docs/widget-format.md`, `the_one/connectors/README.md`, `the_one/agents.md`

## Citation Audit
Checked 2026-11-12 at `ba547e29`.
- `the_one/connectors/delivery.py` — module docstring "must not import `inbound.py`, `app.py` or `tools/`"; `deliver_final_reply` sends `await client.send(target, final.content)`, catches `ConnectorClientError` then `Exception`, and sets `final.visibility = None` after success — verified
- `the_one/connectors/inbound.py:313` — the only `deliver_final_reply` caller; `:272`, `:470` step-limit sends (unchanged) — verified
- `the_one/tools/connector_send.py` `execute` — `result = await client.send(send_target, content)`; `except ConnectorClientError as exc: return f"[error] {type(exc).__name__}: {exc}"`; the success f-string with `{content!r}` and `msg_id` — verified
- `the_one/connectors/base.py:115` `SendResult(platform_message_id, details)`; `ConnectorClientError`; `ConnectorClient` Protocol with `is_alive`, `send` and the `history` OPTIONAL comment — verified
- `the_one/connectors/stub.py` — `StubClient.send` raises `send_should_raise`, appends `(target, content)`; `outbound_records: ClassVar[list[tuple[SendTarget, str]]]`; `reset_for_test` — verified
- `the_one/interfaces/web/api.py` `stub_test_outbound` — `for target, content in StubPlugin.outbound_records:` building four keys — verified
- `evals/checks.py:310-341` `_top_level_blocks` — `reply.split("\n")`, opener `r"```(.*)$"`, closer `r"```\s*$"`, body join plus trailing `"\n"` — verified
- `the_one/visuals/chart_image.py:1076` `render_png(spec) -> RenderedChart`, raises `ChartImageError`, holds `_LOCK` — verified (Leg 1)
- `outbound_records` readers: 35 hits across `tests/*.py` and `tests/behavior/*.md` — counted. Design review cycle 1 verified each reader's shape (unpacking, indexing, `len`, `==`, `.clear()`, `.append` of a plain tuple; none type-checks `tuple` or serializes records).
- Design review cycle 1 also verified:
  - `stub_test_outbound` at `api.py:5238-5258`;
  - fake clients returning `None` from `send` (`tests/test_connector_delivery.py:26-33`, `tests/test_routine_turn_path.py:77-82`);
  - no `send_visual`, `send_visual_fallback` or `__getattr__` under `the_one/connectors/` today;
  - only `startswith` parses `[platform-send-ok]`;
  - `from evals import checks` in the existing tests, with no side effects.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
