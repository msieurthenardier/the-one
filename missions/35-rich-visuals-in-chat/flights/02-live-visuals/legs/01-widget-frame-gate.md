# Leg: widget-frame-gate

**Status**: completed (the gate decided 2026-11-09: go with mitigations)
**Flight**: [Live Visuals](../flight.md)

## Objective
Build the widget frame core: a sandboxed `srcdoc` iframe whose fixed prelude and policy come before any model bytes, plus the page-level `frame-src 'none'` header. Prove the frame against the escape battery in Playwright Chromium and WebKit, in real WebKitGTK and in real WebView2, and measure runaway and focus behaviour per engine. The leg ends at the operator's go/no-go.

## Context
- Flight DDs this leg implements:
  - **DD2:** the frame, the policy, `srcdoc` set before insertion, and the sink guard.
  - **DD3:** the `/` header, and a second `load` as the escape signal.
  - **DD4:** the size-only channel, the heartbeat, coalescing, and identifying the sender by `event.source`.
  - **DD5:** theme variables at mount, and theme pushes.
  - **DD6:** the prelude as a pinned constant (capture, neutering, an **empty pause slot**, handlers), plus the WebKit `preconnect` path.
  - **DD17:** the escape battery and its sink.
- **Measured here** (results feed DD6, DD9, DD10, DD13 and the gate): the WebKit `preconnect` path in real WebKitGTK; whether pywebview's GTK bridge (`webkit.messageHandlers.jsBridge`) is visible and reachable from a sandboxed subframe; the runaway freeze per engine; the WebView2 runtime version and whether WebView2 isolates the frame; focus-steal behaviour and the DD10 discriminator candidates.
- **Not here:** the card, header, lifecycle, pause gate, hang guard, focus guard (leg 3) and chat wiring (leg 4).
  - The next-launch `localStorage` key measurement on real quit paths (DD9) and the real-shell bridge confirmation on Linux move to **leg 4**. They need a seeded chat with a widget, which needs leg 4's wiring.
  - On Linux the real pywebview page cannot be scripted, so leg 1 answers the bridge question with a faithful replica (below). Windows is checked in the real shell over CDP.
- **Planning probes to reuse**, in the session scratchpad (`/tmp/claude-1000/-home-cprch-projects-the-one/da169ac8-75fe-44c8-8380-7ab56e91e088/scratchpad/`): `probe/` (the Flight Director's), `arch/` and `arch2/` (the Architect's). They show working patterns: a local `http.server` sink; full Chromium via `channel="chromium"`; WebKit via `tests.browser._ui_engines._webkit_launch_kwargs`; the UDP listener; `preconnect`; focus steal.
- **Flight 1 lessons:**
  - run the real engine on a premise, never reason from source;
  - pace streams slower than the 16 ms tick (not relevant here);
  - falsify new tests.

## Inputs
- `main` at `3dc20800` plus the planning commit `251c4d24` on `flight/02-live-visuals`.
- No widget code exists. No `<iframe>`, `srcdoc`, CSP or `IntersectionObserver` exists anywhere in `the_one/` or `static/`.
- `the_one/interfaces/web/app.py` `index()` returns `HTMLResponse(content=_cache_busted_index_html(), headers={"Cache-Control": "no-store"})`.
- `tests/_ui_guard_helpers.py:337-341` detects `innerHTML`, `outerHTML` and `insertAdjacentHTML` only.
- `tests/browser/_ui_engines.py::load_harness` builds the contract page by `page.set_content` on a blank page. It has no page CSP, and the frame-navigation tests need one (see guidance 5).

## Outputs
- `the_one/interfaces/web/static/js/ui/widget-frame.js`: **`App.ui.widgetFrame = function (opts) {…}`**, a library factory. It must be a function: the inventory guard fails on a catalogue row that cites a non-factory `App.ui.X` (`check_inventory`), and every row needs `library: App.ui.X` (design review). Leg 3's `App.ui.widget` wraps it.
  - Calling `App.ui.widgetFrame(opts)` returns a handle `{iframe, destroy(), postTheme(theme), loads()}`. Options: `slot`, `source`, `title`, `theme`, and the callbacks `onSize(h)`, `onHeartbeat()` and `onEscape()`.
  - Properties on the function: `App.ui.widgetFrame.buildDocument(source, opts) -> string`, the prelude constant(s), and the limits.
  - Module level: one `message` listener, a `Map` from `contentWindow` to handle, and size coalescing.
- **The `/` header:** `Content-Security-Policy: frame-src 'none'; child-src 'none'`, from one Python constant, absent on `/api/oauth/callback`.
- **The srcdoc sink guard:** `.srcdoc =` and `setAttribute('srcdoc'` detected, with the one allowed site in `widget-frame.js`, falsified.
- `tests/fixtures/widgets/escape.html`, the escape battery, plus a sink helper module for tests and probes (HTTP, UDP and TCP-accept counting; it also serves a harness page with the page header).
- `tests/browser/test_ui_widget_frame_contract.py` (Chromium + WebKit), added to `contracts-chat` through the `contracts_chat_pat` list in `scripts/run-tests.sh` (`test_ui_widget*`).
- A catalogue row in `docs/ui-control-inventory.md` for `App.ui.widgetFrame` (frame core; owned classes such as `ui-widget-frame`). The testid registry is updated if any testid is emitted.
- Probe scripts: WebKitGTK escape and replica-bridge runs through `scripts/webkitgtk_probe.py`, extended with a message-handler replica option if needed; WebView2 runs through `scripts/windows_test_copy.py` plus Playwright CDP.
- A flight-log entry with every measurement in a table, and a go/no-go recommendation.

## Acceptance Criteria

**Part A (autonomous)**

- [ ] **AC1 — Document builder.** `buildDocument(source)` returns exactly, in order:
  1. `<!doctype html>`;
  2. `<meta charset="utf-8">`;
  3. the DD2 policy `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; media-src 'none'; font-src 'none'; connect-src 'none'; frame-src 'none'; child-src 'none'; worker-src 'none'; object-src 'none'; manifest-src 'none'; form-action 'none'; base-uri 'none'">`;
  4. a viewport meta;
  5. the base `<style>` (DD5 variables from the arguments, `margin: 0`, `color-scheme`, `data-theme` on the root);
  6. the prelude `<script>`;
  7. then `source` verbatim.
  
  **The pin test runs `node`**, following the precedents `tests/test_format_bytes_static.py`, `test_doctor.py` and `test_ui_capture_safety.py`, which shell out to node. It loads `widget-frame.js` with a stub `var App={ui:{}}` (and the minimal stubs it needs), calls `App.ui.widgetFrame.buildDocument('X', opts)`, and compares the result with a literal expected string. It also asserts the section order through `indexOf` of four markers. The sections, in order:
  1. capture timers, plus `clearTimeout`/`clearInterval` refusing the heartbeat id;
  2. neuter;
  3. an empty pause-gate slot marked by a comment;
  4. the size and theme handlers.
- [ ] **AC2 — Frame attributes and order.** `App.ui.widgetFrame(opts)` builds `iframe` with:
  - `sandbox="allow-scripts"` (exactly that token);
  - `referrerpolicy="no-referrer"`;
  - `allow=""`;
  - a `title` from options;
  - `srcdoc` **set before the iframe is inserted** into the document.
  
  The contract test asserts the attributes, and asserts that the iframe's `load` count is exactly 1 after a benign widget loads, in both engines.
- [ ] **AC3 — Neutering (DD6).** Before any model script runs, the prelude defines non-configurable, non-writable own properties:
  - `window.RTCPeerConnection`, `window.webkitRTCPeerConnection` and `window.RTCDataChannel` as `undefined`;
  - `History.prototype.back`, `.forward`, `.go`, `.pushState` and `.replaceState` as no-ops;
  - `Document.prototype.execCommand` returning `false`.
  
  Contract test, both engines: the neutered values hold after the widget tries `delete` and `Object.defineProperty`. `window.constructor.RTCPeerConnection` is also undefined.
- [ ] **AC4 — Size channel (DD4).**
  - The prelude posts `{t:"size", h}` on load, on root resize, and once a second (the heartbeat), using timer references captured before anything else.
  - The heartbeat survives a widget's `clearInterval`/`clearTimeout` on every id from 0 to 10000.
  - The page matches messages by `event.source` only. A message whose source is not a live frame, of the wrong shape, or with a non-finite `h` is ignored.
  - `h` is clamped to 48-720, and the initial height is 240.
  - A flood of 1000 messages in one task causes at most one height write per animation frame.
  
  Contract tests in both engines, including a forged message from the page itself and from a second unrelated frame.
- [ ] **AC5 — Theme (DD5).** At mount the frame's root defines its own variables `--bg`, `--surface`, `--fg`, `--fg-muted`, `--border`, `--accent`, `--danger` and `--chart-1..8` as **literal values**, read from the page's computed tokens. `--danger` maps from the page's `--status-danger`; the page has no `--danger` token. It also carries `data-theme` and `color-scheme`. The JS strings contain no `var(--…)` references, so the JS-string token tripwire (`_ui_guard_helpers.py:491+`) sees nothing undefined. `postTheme()` updates them and dispatches `themechange` on the frame's `window`. Contract test in both themes.
- [ ] **AC6 — Escape battery.**
  - **The fixture.** `tests/fixtures/widgets/escape.html` attempts every path:
    - DD2's: fetch, XHR, image, `sendBeacon`, WebSocket, form POST, `link rel=prefetch`, CSS `url()`, `@import`, a `data:` worker, a `blob:` worker, `EventSource`, `import()`;
    - parent and top DOM, `top.location`, cookies, `localStorage`, `window.open`, `alert`, top navigation, a nested `about:blank` realm;
    - DD3's: self-navigation by `location.href`, meta refresh, link click and `location.reload()`;
    - DD6's: WebRTC STUN to the UDP sink, `history.back()`/`go(-1)`/`pushState`, `execCommand('copy')`, and `link rel=preconnect` to the TCP sink;
    - a forged-message flood.
    
    It draws a pass/fail grid inside itself.
  - **The test pages.** The contract tests load their harness at a real http URL whose response carries **the same `frame-src 'none'; child-src 'none'` header value**, imported from the one Python constant. Two ways are acceptable:
    - `page.route` on **exactly** the harness URL (fulfil with the header and a blank body; every other request continues to the real network and the sink);
    - or the sink helper's HTTP server serving the harness.
    
    Then the normal `load_harness` steps run (inline style and script tags are unaffected by a `frame-src`-only policy). The harness origin is not opaque, so the cookie and `localStorage` checks mean something. The tests then assert:
    - (a) zero HTTP requests, zero UDP datagrams and zero TCP accepts at the sink from the frame;
    - (b) the page URL, hash and `popstate` count are unchanged;
    - (c) no new page or dialog;
    - (d) every self-navigation and reload attempt yields a second `load`, which fires `onEscape` exactly once and removes the frame;
    - (e) the grid reports every in-frame attempt refused.
  - **Engines.** This runs in Chromium and WebKit through the `engine_page` fixture.
  - **The known WebKit `preconnect` result** may fail (a) in Playwright WebKit (DD6). If it does, it is **not** silenced with `xfail` or a skip.
    - The test carries one named allow-list entry: `(engine == "webkit", sink == "tcp", count <= N, "DD6 preconnect")`.
    - The HTTP and UDP sinks must still read 0 for WebKit, and **Chromium must read 0 TCP accepts**, so the entry cannot mask a regression.
    - Any other sink hit fails the test.
    - The fixture uses both a parser-inserted `preconnect` link and a script-created one added after load.
    - The test prints the counts, and the flight log records them per engine.
- [ ] **AC7 — The `/` header.** `GET /` carries `Content-Security-Policy: frame-src 'none'; child-src 'none'`, from one module-level constant in `the_one/interfaces/web/app.py` (or a small module it imports). `GET /api/oauth/callback` carries no CSP header. Unit tests cover both; the existing `index()` cache header is unchanged.
- [ ] **AC8 — srcdoc sink guard.**
  - `tests/_ui_guard_helpers.py` and `tests/test_ui_guards.py` detect `.srcdoc =` (not `==`/`===`) and `setAttribute('srcdoc'`/`setAttribute("srcdoc"` anywhere under `static/js/`.
  - The one allowed site is `js/ui/widget-frame.js`'s document setter, named with a comment.
  - **Falsified:** a temporary second site makes the guard fail. The site is removed by editing afterwards.
- [ ] **AC9 — Library rules.**
  - The catalogue row exists for `App.ui.widgetFrame`, with its owned classes.
  - The emitted-class, ownership, HTML-sink, token-definition and paired-listener guards pass. The `window` `message` listener is module-level, installed once while a frame exists and removed with the last one.
  - `contracts_chat_pat` includes `test_ui_widget*`. **`tests/test_run_tests_lanes.py:97` pins the exact `contracts-chat` file set**, so its name tuple gains `"widget_frame"` and its docstring is updated, as is the comment above `contracts_chat_pat` (`scripts/run-tests.sh:250-252`).
  - `widget-frame.js` (the prelude string and its comments included) contains none of the words `innerHTML`, `outerHTML` or `insertAdjacentHTML`. The zero-token scan `find_ui_dir_sink_tokens` (`_ui_guard_helpers.py:181`) covers every `js/ui` file, comments included.
  - The contract file literally calls `App.ui.widgetFrame(`, which the inventory test requires.
  - `index.html` loads `widget-frame.js` among the `js/ui/` scripts, so `load_harness` sees it.

**Measurements (Part A, autonomous; recorded, not pass/fail except where stated)**

- [ ] **AC10 — Runaway per engine** (Playwright). Measure the parent's maximum timer gap during a 3 s busy loop in the frame, in full Chromium (`channel="chromium"`), the headless shell and WebKit. Record the Chromium and WebKit build versions.
- [ ] **AC11 — Real WebKitGTK** (`scripts/webkitgtk_probe.py`, system `/usr/bin/python3`, a scratch dev instance on a port ≥ 8490 with a scratch data dir under `$HOME`; it refuses 8484 and 8485). A `--setup-script` creates a widget frame from the escape fixture inside the real app page, which carries the real `/` header. Measure:
  - the battery grid and the sink (HTTP, UDP, TCP), with `preconnect` reported **explicitly**;
  - the runaway gap;
  - **the bridge replica:** register a script message handler named `jsBridge` on the probe's `WebKit2.UserContentManager` exactly as pywebview does (`webview/platforms/gtk.py:143-145`, `register_script_message_handler('jsBridge')` and `script-message-received`). From the sandboxed frame, test whether `window.webkit.messageHandlers.jsBridge` exists and whether a `postMessage` reaches the Python callback.
  
  Record the WebKitGTK version (2.52.6 on this host at planning).
- [ ] **AC12 — Focus** (Playwright, full Chromium, the headless shell and WebKit). Measure:
  - whether a widget's `input.focus()` steals focus from a focused page textarea;
  - which parent events fire (`focusout`, `window` `blur`, `focusin`);
  - whether `navigator.userActivation.isActive` and the time since the last parent `keydown` tell a real click into the frame (`page.mouse.click` on the frame) from a steal while typing, and Tab into the frame from a steal.
  
  Recommend a DD10 discriminator with its measured hit and miss behaviour.

**Part B (operator present: the Windows desktop; hands-off waits)**

- [ ] **AC13 — Real WebView2.**
  - **Setup:** `scripts/windows_test_copy.py` setup, freeze or script, then `launch --cdp-port` (app port ≥ 8490, debugging port ≥ 9390, scratch data dir; never 8484 or the operator's data dir), per `tests/behavior/windows-window-chrome.md`'s Preconditions. Playwright `connect_over_cdp` drives the real pywebview WebView2 page.
  - **Measure:**
    - the escape battery and its sink (the sink on WSL `127.0.0.1` is reachable over mirrored networking, or run it on the Windows side; record which);
    - the runaway gap;
    - focus steal;
    - **the bridge:** from a sandboxed widget, is `window.chrome.webview` present? Does a `postMessage` of a pywebview move-window call move the window, observed through `GET /api/window/state` before and after?
  - Record the WebView2 runtime version (`navigator.userAgent` or the registry).
  - **Teardown:** stop by recorded identity; `snapshot --out`/`--compare` bracket the session.
- [ ] **AC14 — Suspend (optional, the operator's choice).** If the operator agrees, sleep and wake the Windows machine with a widget frame loaded, and record the parent timer gap and whether `visibilitychange` fired. Otherwise record "not measured"; DD9's > 60 s suspend rule then applies by default.

**Gate**

- [ ] **AC15 — Go/no-go record** (evaluated after Part B; the WebView2 column exists only then). The flight log holds one table: every path × every engine (Playwright Chromium full and shell, Playwright WebKit, WebKitGTK, WebView2) with the result, plus the runaway, focus and bridge findings. It gives a recommendation:
  - go;
  - go with mitigations, naming the DD6 `preconnect` and DD13 bridge options per platform;
  - or no-go.
  
  The Flight Director brings it to the operator; the leg is `landed` only after the operator's decision is recorded.

## Verification Steps
- **AC1, AC7, AC8:** `.venv/bin/python -m pytest tests/test_widget_frame_prelude.py tests/test_app_frame_policy.py tests/test_ui_guards.py -x --timeout 60` (names indicative), then `make test-unit` once at leg end (`THE_ONE_TEST_NETNS=1`).
- **AC2-AC6, AC9:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts-chat -x`. Also run `contracts-controls` if any shared `js/ui` file changed.
- **The static guards:** `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`, `tests/test_ui_control_inventory.py`, `tests/test_ui_ownership.py`, `tests/test_ui_emitted_classes.py`, `tests/test_run_tests_lanes.py`.
- **Falsification:** AC3 (remove one neutering line → its test fails), AC4 (accept by origin instead of source → the forged-message test fails), AC6(d) (append before setting `srcdoc` → the load-count test fails) and AC8. Each is restored by editing.
- **AC10-AC14:** probe scripts kept under a scratch directory outside the repo (or under `scripts/` if the leg adds a reusable option to `webkitgtk_probe.py`, with a unit test of that option's argument handling). Results go in the flight log with the exact commands.

## Implementation Guidance

1. **The prelude and document builder** (`js/ui/widget-frame.js`, ES5, no HTML-string sinks in the page).
   - The prelude is a string constant that runs **inside the frame**. That is the point, and it is not a page-side sink. The single `iframe.srcdoc = doc` assignment is the allowed sink site (AC8).
   - **Capture first:** `var _st = setTimeout, _si = setInterval, _ct = clearTimeout, _ci = clearInterval, _raf = requestAnimationFrame, _pm = parent.postMessage.bind(parent)` (or equivalent). Then wrap `clearTimeout`/`clearInterval` to ignore the heartbeat id.
   - **Neuter** with `Object.defineProperty(obj, name, {value, writable:false, configurable:false})`. For `History.prototype` methods, define on the prototype (cycle 1 probe: deleting does not restore). Wrap each define in try/catch so a missing name never stops the prelude.
   - **Pause slot:** leave a comment marker only (`/* PAUSE-GATE */`). Leg 3 fills it.
   - **Handlers:** the size reporter (a `ResizeObserver` on `documentElement`, on load, and a heartbeat interval at 1000 ms through the captured `_si`, all posting `{t:'size', h: Math.ceil(documentElement.scrollHeight)}`), and a `message` listener applying `{t:'theme', vars, mode}`, then dispatching `themechange`.
   - The source is appended after the prelude **verbatim**. Never parse or rewrite it.
2. **`App.ui.widgetFrame(opts)`** (the factory call):
   - Build the iframe with `document.createElement` and set its attributes (AC2), then set `srcdoc`, then append it to `opts.slot`.
   - Count `load` events. On a load after the first, call `onEscape` once and remove the frame.
   - Register `contentWindow` in the module `Map`, installing the `window` `message` listener on the first frame and removing it with the last.
   - Coalesce heights with one `requestAnimationFrame`, applying `style.height` with the clamp.
   - `destroy()` removes the frame and the `Map` entry and is idempotent.
   - Read theme values from `getComputedStyle(document.documentElement)` (or the slot) at mount.
3. **The `/` header.** Add one module-level constant, for example `FRAME_POLICY = "frame-src 'none'; child-src 'none'"`, and put `"Content-Security-Policy": FRAME_POLICY` beside `Cache-Control` in `index()`. Do not add it as middleware: the OAuth callback page has inline scripts (`api.py:5385-5410`). Check that dev mode (`THE_ONE_DEV_MODE=true`) still serves through the same `index()` route.
4. **The sink guard.** Extend `_ui_guard_helpers.py`, following the existing sink-classification style (`:337-341`). Add a srcdoc allowance with a single named entry and a comment. Run the falsification.
5. **The test harness and the sink.**
   - Add a helper module (for example `tests/browser/_widget_sink.py`). It runs, on `127.0.0.1` ephemeral ports in a thread:
     - an HTTP server that logs every request;
     - a UDP socket that counts datagrams;
     - a TCP listener that counts accepts.
   - **The harness page** comes from a real http URL with the `FRAME_POLICY` header (imported from the app module): either `page.route` on that one URL only, or the sink's HTTP server. `load_harness` today hard-codes `page.set_content`, so add an optional `url`/`headers` path to it (or a sibling helper in `_ui_engines.py`) **without changing its existing behaviour** for other callers.
   - **Never** let a route match frame traffic: interception would hide real network attempts. Use a strict URL match, and let everything else continue.
   - The escape fixture reads the sink ports from placeholders the test fills in (`{{HTTP}}`, `{{UDP}}`, `{{TCP}}`) **before** calling `buildDocument`. The pinned prelude text is therefore never affected by the fixture; add an assertion for that.
   - Under `THE_ONE_TEST_NETNS=1` all of this is loopback, so it works.
   - For the 1000-message flood (AC4), count height writes with a `MutationObserver` on the iframe's `style` attribute rather than by timing.
6. **Contract tests** go in `tests/browser/test_ui_widget_frame_contract.py`, parametrized through `engine_page`, and read the frame grid with Playwright frame access (`page.frames`).
   - For focus or real input use `page.mouse`/`page.keyboard`.
   - Wait on conditions (`wait_for_function`), never on fixed sleeps longer than needed. The heartbeat test may wait about 2.5 s.
7. **Measurements AC10-AC12.** Scratch scripts are fine (outside the repo).
   - **WebKitGTK:** `scripts/webkitgtk_probe.py` needs `--data-dir` (it reads the credential and mints the handoff).
     - Start the scratch instance per CLAUDE.md "Behavior-test credential convention": a scratch cwd, `THE_ONE_PORT` ≥ 8490, `THE_ONE_DATA_DIR` under `$HOME`, `THE_ONE_DEV_MODE=true`, and `the-one rotate-api-credential` first.
     - Record the server PID from `ss -ltnp`, never `$!` (Flight 1 lesson), and stop it by that PID.
     - If the replica bridge needs a new probe option, add it to `webkitgtk_probe.py` behind a flag (for example `--register-message-handler NAME`), with the callback's received messages reported in the JSON output.
8. **Part B** is run by a separate Developer spawn after the Flight Director confirms the operator is ready at the Windows desktop. Part A ends by recording `Part A landed; Part B pending` in the flight log. Do not start any `windows_test_copy.py` command in Part A.

## Edge Cases
- **A widget whose source contains `</script>`, `<meta http-equiv=...>`, `<base>` or a full `<html><head>` document.** The prelude is still first and in force (the planning probe: a later `<meta>` cannot loosen). Add one contract case with a full-document body.
- **A source with a NUL or invalid UTF-16 surrogates.** `srcdoc` takes the string as is; there is no crash. Add one case.
- **`create()` called on a detached slot,** then attached later. Loads happen only once it is attached; the load count starts then. Test it if cheap, or document it.
- **A theme push to a frame that has not loaded yet.** Queue it or drop it (the frame reads its variables from the document at load anyway). Document the choice.
- **The size heartbeat while the frame sits in a `display:none` container.** It still arrives (cycle 2 probe). There is no assertion here; leg 3 relies on it.
- **WebKit `preconnect`.** Expected open in Playwright WebKit. Whatever the result, record it; never hide it.

## Files Affected
- `the_one/interfaces/web/static/js/ui/widget-frame.js` - new: the frame core
- `the_one/interfaces/web/static/index.html` - load `widget-frame.js`
- `the_one/interfaces/web/static/css/components.css` - minimal frame style (border none, width 100%, display block), if any
- `the_one/interfaces/web/app.py` - the `FRAME_POLICY` constant and the header on `index()`
- `tests/_ui_guard_helpers.py`, `tests/test_ui_guards.py` - the srcdoc sink detection and its allowance
- `tests/fixtures/widgets/escape.html` - new
- `tests/browser/_widget_sink.py` (name indicative) - new
- `tests/browser/test_ui_widget_frame_contract.py` - new
- `tests/test_widget_frame_prelude.py`, `tests/test_app_frame_policy.py` (names indicative) - new
- `scripts/run-tests.sh` - `contracts_chat_pat` gains `test_ui_widget*`
- `tests/test_run_tests_lanes.py` - the `contracts-chat` name tuple at `:97` gains `"widget_frame"` (it pins the exact file set)
- `tests/browser/_ui_engines.py` - an optional url/headers harness path (existing behaviour unchanged)
- `docs/ui-control-inventory.md` - the `App.ui.widgetFrame` row
- `docs/ui-testid-registry.md` - only if a testid is emitted
- `scripts/webkitgtk_probe.py` - optional `--register-message-handler` (with a unit test of the argument handling)
- `missions/35-rich-visuals-in-chat/flights/02-live-visuals/flight-log.md` - the leg entry and measurements

## Citation Audit
Verified against the working tree at `251c4d24` (Flight Director, 2026-11-09).
- `the_one/interfaces/web/app.py::index` - `HTMLResponse(content=_cache_busted_index_html(), headers={"Cache-Control": "no-store"})` at `:3079-3085` - verified
- `the_one/interfaces/web/api.py:5385-5410` - the OAuth callback page with inline `<script>` - verified
- `tests/_ui_guard_helpers.py:337-341` - `_SINK_ASSIGN` (`innerHTML|outerHTML`) and `_SINK_CALL` (`insertAdjacentHTML`) only - verified
- `tests/test_ui_control_inventory.py:18` - `_FACTORY = re.compile(r"^\s*App\.ui\.(?!util\b)(\w+)\s*=\s*function\b")`; `check_inventory` also fails on a row citing a non-factory, so `widgetFrame` is a function factory - verified (design review)
- `tests/test_run_tests_lanes.py:97` - exact `contracts-chat` file-set pin - verified (design review)
- `tests/_ui_guard_helpers.py:181` (`find_ui_dir_sink_tokens`, comments included) and `:491+` (the `var(--x)`-in-JS-string tripwire) - verified (design review)
- `the_one/interfaces/web/static/css/tokens.css` - `--fg-muted` defined; no `--danger` (the page uses `--status-danger`) - verified
- `scripts/webkitgtk_probe.py:281` - `content = WebKit2.UserContentManager()`, so a replica handler can be registered - verified (design review)
- `tests/test_ui_guards.py:800` - the paired-listener guard covers `document` listeners in `static/js/ui` (a `window` listener is outside it; pair it anyway) - verified
- `tests/browser/_ui_engines.py:192-214` - `load_harness` uses `page.set_content` on a blank page with no page CSP - verified
- `webview/platforms/gtk.py:143-145` (pywebview 5.4 in `.venv`) - `UserContentManager()`, `register_script_message_handler('jsBridge')`, `connect('script-message-received', self.on_js_bridge_call)` - verified
- `scripts/webkitgtk_probe.py:144-193`, `:226-235`, `:316-319` - flags incl. `--setup-script`, `--data-dir`; setup scripts must return true; `window.__probeReport` - verified (flight citation audit)
- `scripts/windows_test_copy.py:4940` (`--cdp-port`), `:543`; `tests/behavior/windows-window-chrome.md:40-65` - CDP precedent, ports ≥ 8490/9390, mirrored networking - verified
- `scripts/run-tests.sh:253` - `contracts_chat_pat` explicit list - verified
- Host: WebKitGTK 2.52.6 via system `/usr/bin/python3` `gi`; `DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`; `.venv` pywebview available - verified (2026-11-09)
