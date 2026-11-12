# Leg: widgets-in-chat

**Status**: completed (behavior test `widget-escape` passed 9/9, 2026-11-10)
**Flight**: [Live Visuals](../flight.md)

## Objective
Wire widgets into chat:
- a ```` ```widget ```` block in an assistant reply renders as a managed `App.ui.widget` card, with the "Rendering widget" placeholder while it streams;
- every card is torn down when the log is cleared;
- the format document, the security model section and the operator-facing docs are written;
- the end-to-end `widget-escape` behavior test is authored and passes.

## Context
- **Flight DDs:** DD1 (the tag), DD12 (streaming, cut-off, the format doc), DD7 (teardown via `sweep()`), DD9 (keys), DD17 and DD18 (the behavior test and flow tests).
- **The mitigations chosen at the leg 1 gate are already built** (legs 3a and 5): the focus gate, the link blocking, pause, the lifecycle and the hang guard.
- **The DD13 bridge switch-off and the DD9 next-launch key check** are desktop-shell work. They move to the desktop leg, `desktop-engine-pass`, which already runs the real shells on Linux, Windows and macOS. Recorded in the flight log.
- **Chat today** (after leg 2), in `areas/chat/`:
  - `transcript.js:69-72`: `drawChart(source, meta)` and `mdOpts()` returning `{copyLiveEl, codeBlockRenderers: {chart: drawChart}}`;
  - `:95`: assistant bubbles render through `App.markdown.render(text, mdOpts())`;
  - `:149-157`: `clearLog()` ends in `messagesEl.replaceChildren()`;
  - `:177`, `:182`: `renderHistory(history, agentName)`, with `agentLabel = agentName || 'agent'`;
  - `:555`: the streaming attribution.
- **`stream-commit.js`:**
  - `ctx.tags` (`['chart']` today, `:9`);
  - the hold builds `App.ui.chart.placeholder({type:null, testid:'chat-chart-placeholder'})` (`:80`) and feeds `setSource`/`setType` (`:91-94`) from `App.chat.visualStream.typeOf`.
- **Leg 2's placeholder options:** `label`, `sourceLabel`, `shape:'generic'`.
- **Leg 4/5's card:** `App.ui.widget({source, closed, agentName, testid, key, paused, managed})`. Managed is the default. It returns `null`, a notice handle, or a card handle.

## Acceptance Criteria
- [ ] **AC1 — Rendering.**
  - `mdOpts()` adds `codeBlockRenderers.widget = drawWidget`.
  - `drawWidget(source, meta)` returns `App.ui.widget({source, closed: meta.closed, agentName, testid: 'chat-widget', key})` `.el` (or `null`, so the markdown renderer falls back to a code block).
  - `agentName` is the reply's attribution name: the chat's agent, or "the agent" for none.
  - **The key** is `(ctx.chatState.boundId() || ctx.chatState.activeId() || '') + ':' + fnv1a(source) + ':' + n` (accessors in `session-state.js:102`; the socket enters `joined` before `renderHistory`, so live and reloaded keys agree).
    - `n` counts earlier **closed** widgets with the same hash in this log, in an `Object.create(null)` map that resets in `clearLog`. A cut-off block (`meta.closed === false`) does not increment it.
    - The card exposes its key as `data-widget-key` on the figure, which the flow tests read.
    - A comment in `drawWidget` states the invariant: it is never called from a render whose fragment is thrown away. The review found no double render: history renders once, streaming commits render only new prefixes, and `finalize` renders only the tail.
  - Only assistant replies render widgets: user messages, routine-run messages, tool output and the thinking disclosure stay text.
  - **Flow tests:**
    - a non-streamed reply with a widget shows the card with "Widget by {agent}", runs it (an in-frame counter advances), and View source holds the exact source;
    - a reply with a widget and a chart shows both;
    - `html` and `javascript` blocks stay code blocks;
    - a user message containing ```` ```widget ```` stays text;
    - Copy reply copies the raw markdown, including the widget source.
- [ ] **AC2 — Streaming.**
  - `stream-commit.js` passes `tags: ['chart', 'widget']`.
  - For a `widget` hold it builds `App.ui.chart.placeholder({type:null, label:'Rendering widget', sourceLabel:'Widget source', shape:'generic', testid:'chat-widget-placeholder'})`, feeds `setSource`, and never calls `setType`.
  - On the closing fence the card replaces the placeholder at once.
  - A Stop mid-block yields the muted cut-off notice, and the source never runs.
  - **Flow tests** use mock streams **paced slower than the 16 ms tick** (a few characters every 100 ms through `delay_ms`; Flight 1's lesson). They cover:
    - the placeholder appearing with its label and Show source;
    - no raw widget text flashing in the bubble (the Flight 1 `WATCH_JS` pattern);
    - the swap to the card;
    - the cut-off on Stop;
    - a chart and a widget streaming in one reply.
- [ ] **AC3 — Teardown.**
  - **The transcript keeps every handle `drawWidget` returns**, in a list. `clearLog()` destroys each one explicitly, then calls `App.ui.widget.sweep()` after `replaceChildren()` as a backstop. Design review: `sweep()` alone leaks a card that was never seen, built in a fragment and cleared before its first observer callback.
  - **Race test:** join a chat with widgets and switch away in the same task → `_counts().cards` is 0.
  - Flow tests: open a chat with 2 widgets, then switch to another chat → no widget frames remain (`document.querySelectorAll('iframe')` is empty in the log), and the manager's `_counts()` shows 0 cards.
  - Reopen the first chat → the widgets render again, keyed identically.
- [ ] **AC4 — History and the lifecycle in chat.**
  - A chat with 5 widgets reopened at the bottom: only in-view widgets run (the cap of 3 applies).
  - Scrolling up pauses the bottom ones (`paused-auto`) and runs the ones that come into view.
  - This is a flow test, kept short; leg 5's contract tests cover the rules.
- [ ] **AC5 — The page header and the OAuth listener.**
  - A flow test asserts `GET /` carries `frame-src 'none'; child-src 'none'` in the running test app.
  - **OAuth listener:** a real widget in a chat calls `parent.postMessage({type:'mcp-oauth-result', status:'failed'}, '*')`. A page-level test listener captures the event, and the test asserts `event.origin === 'null'` and `!== location.origin`. With the check at `areas/studio/mcp-oauth-consent.js:187` (`evt.origin !== window.location.origin` → return), that closes the claim. The OAuth listener is attached only during a consent flow in the Library, so a live collision cannot be staged in Chats. First check that legs 1-5 did not already assert a widget's `"null"` origin; if one did, cite it instead of adding a duplicate.
- [ ] **AC6 — Docs.**
  - **`docs/widget-format.md`** (new, language-neutral):
    - the tag;
    - the body (HTML, inline style and script; fragment or document);
    - the theme variables and the `themechange` event;
    - pause behaviour and its limits (`MessageChannel`, busy loops, `element.animate()` after a pause, `requestVideoFrameCallback`);
    - focus rules (programmatic focus only within about 1 s of the user's gesture inside the widget);
    - `<link>` tags rewritten to `<x-link>` (including inside script strings);
    - `document.write` after load is a no-op;
    - what is blocked;
    - the limits (64 KiB; 3 running; 8 loaded; height 48-720).
  - **`SECURITY-MODEL.md`** gains a "Live visuals" section after Authentication, covering:
    - the boundary (sandbox, policy, page `frame-src`, the prelude);
    - what a widget cannot do;
    - the measured engine matrix, linking to the flight log;
    - the residual risks: the WebKit freeze once per bad widget (the hang guard bounds it); preconnect and DNS blocking being best-effort; the 1 s focus window; `<title>` text in chrome; Tab trapping; the crash record's false positives; the bridge (switched off on Linux and macOS in the desktop leg).
  - **`the_one/agents.md`** gets a "Widgets in chat" section:
    - the module map (`widget-frame.js`, `widget.js`, `widget-lifecycle.js`);
    - the chat wiring;
    - keys;
    - teardown;
    - the test lanes;
    - the streaming-test pacing rule.
    
    This also closes squawk 0342's first note.
  - **CLAUDE.md** gets a short operator-facing note beside "Charts in chat".
  - **`docs/ui-testid-registry.md`** gets rows for `chat-widget`, `chat-widget-placeholder` and the derived `chat-widget-*` family, now that a source literal exists.
- [ ] **AC7 — The `widget-escape` behavior test** (DD18) is authored at `tests/behavior/widget-escape.md` in the project format (`.flightops/ARTIFACTS.md` behavior-test template; `tests/behavior/start-a-chat.md` as the model).
  - **Preconditions:**
    - a scratch dev instance started from a scratch cwd (port ≥ 8490, never 8484/8485; data dir under `$HOME`; `THE_ONE_DEV_MODE=true`; PID from `ss -ltnp`, stopped by that PID), per CLAUDE.md "Behavior-test credential convention";
    - a mock provider whose `config.response.content` holds the escape-battery reply: the fixture `tests/fixtures/widgets/escape.html` inside a ```` ```widget ```` fence with the sink ports filled in. It is not streamed;
    - the sink, a **new CLI**, `scripts/widget_sink.py`:
      - it starts the HTTP, UDP and TCP listeners on `127.0.0.1` and prints the ports as JSON on its first line;
      - it serves `GET /__sink/counts` (requests, UDP datagrams, TCP accepts) and `GET /__sink/fixture` (the escape fixture with the ports filled in);
      - it refuses non-loopback binds and stops on SIGTERM;
      - it reuses `tests/browser/_widget_sink.py`'s logic where practical;
      - unit test: it starts, counts one hit per channel, and refuses a non-loopback bind; it is ruff-clean;
    - Playwright CDP with real input.
  - **A baseline step** reads the sink counts as zero before the chat opens, so "empty" afterwards means something.
  - **Steps:**
    - open the chat;
    - the widget runs;
    - read the frame grid;
    - click its escape controls;
    - type into the composer while the widget tries to take focus;
    - press the browser's Back.
  - **Expected results:**
    - the sink is empty;
    - the URL, route and `popstate` count are unchanged;
    - focus and typed text stay in the composer;
    - the DOM outside the card is unchanged;
    - no new page or dialog;
    - `GET /api/agents` is unchanged.
  - **The run:** the Flight Director runs it with `/mission-control:behavior-test widget-escape` before the leg lands. The run log is committed beside the spec; evidence stays outside the repo.
- [ ] **AC8 — Lanes.**
  - `tests/browser/test_flow_chat_widgets.py` goes in **a new explicit lane, `chats-widgets`** (`chats_widgets_pat`). It is excluded from `chats` (whose `test_flow_chat_*` glob would otherwise take it), and is kept out of `chats-transcript`, which sat at 430 s of 540 s at Flight 1.
  - Update the `scripts/run-tests.sh` budget table (provisionally 240 s), the `chat` alias (`chats` + `chats-transcript` + `chats-widgets`), `--help`, `tests/test_run_tests_lanes.py` (lane count, disjointness, union, budgets) and CLAUDE.md's lane prose and table.
  - Run `chats-widgets`, `chats-transcript`, `chats`, `contracts-widget`, `contracts-widget-lifecycle` and `contracts-chat` (at most 3 at a time), then the unit tier. Record the times.
  - Re-budget only from the closing gate's quiet run.
  - **Test shape:** import the paced-stream helpers from `test_flow_chat_charts.py` (`_open`, `_chunks`, `WATCH_JS`), or factor them into `tests/browser/_chats.py` or a small `_chat_streams.py`, without changing their behaviour for the chart tests. Keep the paced tests short (200-400 characters of widget). For AC4, use fixed-height (300 px) widgets and a fixed viewport, and assert counts of `running` states rather than order.

## Verification Steps
- **Browser:** `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats-transcript -x`, and `--lane chats`; the three contract lanes with `THE_ONE_REQUIRE_WEBKIT=1`.
- **Unit and static:** the guard set plus `make test-unit`.
- **Behavior:** `/mission-control:behavior-test widget-escape` (Flight Director).
- **Falsification:** remove the explicit handle destroy from `clearLog` (keeping `sweep()`) → AC3's race test fails; restore by editing. Also test that the same source twice in one reply gives keys `…:0` and `…:1` (via `data-widget-key`), and that a routine-run bubble (`addUserEvent`, text only) containing a widget fence stays text.

## Implementation Guidance
1. **`drawWidget` in `transcript.js`:**
   - keep the file under 800 lines (608 now);
   - the per-log hash counter lives in the transcript's state and resets in `clearLog`;
   - the session id comes from the chat context the transcript already uses (find the session state accessor, e.g. `ctx.sessionId()` or the state module);
   - the hash is a short non-cryptographic hash (FNV-1a over code units) in the transcript, or reused from `widget.js` if it exposes one under `App.ui.util`.
2. **The hold in `stream-commit.js`:**
   - Make the placeholder factory a small per-tag table (`chart` → today's call with `chat-chart-placeholder`, `widget` → the generic one), and call `setType` only for `chart`.
   - The `lang !== 'chart'` check (about `:73`) becomes `tags.indexOf(lang) < 0`.
   - `typeOf` stays chart-only.
   - Rename `chartHold`/`dropChartHold` to `visualHold`/`dropVisualHold`, and update the header comment's `['chart']`.
   - The transcript passes `tags: ['chart', 'widget']` (about `transcript.js:253`).
   - `open.lang` is already reported by `visual-stream.js` (leg 2).
3. **Docs:** write `docs/widget-format.md` from the DDs and the as-built code (read `widget-frame.js` for the exact variable names and limits). The `SECURITY-MODEL.md` section cites the flight log's measurement tables rather than repeating them.
4. **The behavior test spec:** the action/observe columns must be executable by an Executor with Playwright CDP, and judgeable by a Validator from observables. Give the exact sink start command (reuse `tests/browser/_widget_sink.py` as a module, or a small CLI around it under `scripts/`, if the spec needs one; if so, it gets a unit test).

## Edge Cases
- **A widget inside a list item:** it streams raw (top-level only for the placeholder), and is drawn at commit like charts.
- **A reply with only a widget and no text:** the bubble holds the card.
- **The same widget source twice in one reply:** keys `:0` and `:1`.
- **The agent renamed between visits:** the label follows the attribution as rendered. The key does not include the name.
- **A routine-run chat:** routine messages render as user-side bubbles (text), and the agent's replies to them render widgets.

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat/transcript.js`, `stream-commit.js`
- `tests/browser/test_flow_chat_widgets.py` - new
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py` - the new `chats-widgets` lane
- `scripts/widget_sink.py` - new, with a unit test (for example `tests/test_widget_sink_cli.py`)
- `the_one/interfaces/web/static/js/ui/widget.js` - `data-widget-key` on the figure
- `docs/widget-format.md` - new; `docs/ui-testid-registry.md`
- `SECURITY-MODEL.md`, `the_one/agents.md`, `CLAUDE.md`
- `tests/behavior/widget-escape.md` - new, plus its run log
- `missions/35-rich-visuals-in-chat/flights/02-live-visuals/flight-log.md`

## Citation Audit
Verified on 2026-11-09 against the working tree (legs 1-4 landed, leg 5 in progress):
- `areas/chat/transcript.js:69-72`, `:95`, `:149-157`, `:177-182`, `:555` - verified
- `areas/chat/stream-commit.js:9`, `:36`, `:80`, `:84`, `:91-94` - verified
- `areas/studio/mcp-oauth-consent.js:187` - the origin check - verified
- Leg 5 (landed): `managed` defaults to true (a managed card starts `waiting` and registers); `js/ui/widget-lifecycle.js` (501 lines) holds `App.ui.util.widgetReconcile`, the observer, tick, `visibilitychange` and `pagehide`, and the seams `App.ui.widget._clock`/`_tick`/`_counts`/`_stale`/`_pageId`/`_manager`; the stale-record scan runs once at library load; `widget.js` is 439 lines - verified from the leg 5 report (re-read at leg start)
