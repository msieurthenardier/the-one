# Flight: Live Visuals

**Status**: landed
**Mission**: [Rich Visuals in Chat](../../mission.md)

## Contributing to Criteria
- [ ] **Live visuals run in the app, walled off** (all of it, including the security model section and the escape behavior test)
- [ ] **A visual appears when it is ready** (for widgets: the streaming placeholder, the cut-off and too-large notices, Copy reply unchanged)
- [ ] **Long chats stay responsive** (all of it, as amended on 2026-11-09: pause in view and off screen, the running cap, the loaded-frame ceiling, the hang guard as the stated limit)
- [ ] **Operators choose per agent** (the switch's prompt section and hint widen to widgets)
- [ ] **The prompt cost is measured and accepted** (the widget addition, compared against a fresh same-prompt baseline)
- [ ] **Visuals work in the desktop app** (charts and widgets in WebKitGTK, WebView2 and WKWebView)

---

## Pre-Flight

### Objective
An agent reply can carry a ```` ```widget ```` block: a small, self-contained HTML document with inline style and script, written by the model. The chat runs it in place inside a visible card that the app draws and marks as made by the agent. The card's header has Pause/Resume and Restart.

The frame is a sandboxed `srcdoc` iframe with an opaque origin and scripts only. A content policy and a reviewed prelude come before any model bytes, and a page-level `frame-src 'none'` stops the frame navigating itself. It cannot reach the network, the app, the credential, other windows, the app's history or the app's focus. Its only message back is its height.

A widget starts when it scrolls into view and pauses when it leaves, resuming where it was. At most three run at once, and at most eight stay loaded. A hang guard keeps a widget that froze the page from freezing it again. While the block streams, the Flight 1 placeholder holds its place as "Rendering widget".

The flight first proves the frame in the desktop engines and stops for a go/no-go. It also pays down Flight 1's debt:
- `chart.js` is split and measures text width;
- the transcript's streaming commit and pacing move to their own module;
- the eval baselines are re-recorded on the shipped prompt before the widget text is measured against them.

### Open Questions
- [x] Block tag → DD1 (`widget`, operator choice 2026-11-09)
- [x] Where the frame's document comes from → DD2 (`srcdoc` with a leading `<meta>` policy; a separate origin buys nothing on WebKit, planning probe)
- [x] Self-navigation as an exfiltration path → DD3 (page header `frame-src 'none'`, planning probe)
- [x] Paths the sandbox and policy do not close (WebRTC, WebKit history, clipboard) → DD6 (the prelude, design review cycle 1)
- [x] The only channel back, and how the page identifies the sender → DD4
- [x] Theme → DD5
- [x] Lifecycle: in view, off screen, the cap, the ceiling → DD7 (pause off screen, operator choice 2026-11-09, amending the mission)
- [x] Pause → DD8 (cooperative, operator choice 2026-11-09)
- [x] A widget that hangs → DD9 (hang guard, operator choice 2026-11-09)
- [x] Frame marking and focus → DD10
- [x] Limits → DD11
- [x] Streaming, cut-off and error display → DD12
- [x] Does a widget render in the operator's own messages? → no; assistant replies only, as charts (`transcript.js` uses `mdOpts` only for `role === 'assistant'`)
- [x] pywebview's native bridge reachable from a frame → DD13 (probe; mitigation at the gate)
- [x] Flight 1 debt → DD14 (all three items, operator choice 2026-11-09)
- [x] Prompt and evals → DD15, DD16 (re-baseline first within the eval leg, operator choice; order fixed at design review)
- [x] Engine checks and their owners → DD17
- [x] Mockups and HAT → both (operator choice); DD18
- [x] Enhancements deferred to mission follow-ups → Expand (in-app pop out), Copy source, Download/save and a separate window (operator choice 2026-11-09)

### Design Decisions

**DD1 — The block tag is `widget`** (operator choice, 2026-11-09)
- A widget is a fenced block whose info string's first token is exactly `widget` (lowercase). The existing tag rule applies (`markdown.js:173-174`, `/^[A-Za-z0-9_+#.-]{1,32}$/`).
- `html`, `svg`, `javascript` and every other language stay code blocks.
- The body is the widget's document content: HTML with inline `<style>` and `<script>`, either a fragment or a full document. The fixed prelude (DD2, DD6) comes first either way.

**DD2 — The frame: a sandboxed `srcdoc` iframe whose policy comes before any model bytes**
- **The iframe:** `<iframe sandbox="allow-scripts">`, with no other sandbox token:
  - no `allow-same-origin`, `allow-popups`, `allow-top-navigation*`, `allow-forms`, `allow-modals` or `allow-downloads`;
  - no `allow-pointer-lock`, `allow-presentation` or `allow-storage-access-by-user-activation`.
  - It also gets `referrerpolicy="no-referrer"`, and `allow=""` (a Permissions Policy that grants nothing: camera, microphone, geolocation, clipboard, fullscreen, payment and the rest).
- **Order matters: `srcdoc` is set before the iframe is inserted.** Then the baseline `load` count is exactly 1 in every engine (design review probe). Appending first and setting `srcdoc` after gives two loads at baseline, which would break DD3's escape signal. A re-parent reloads an iframe, so the control never moves a mounted iframe; it builds a new one.
- **The document** is one string: the fixed prelude, then the model's body verbatim. The prelude, in order:
  1. `<!doctype html>`;
  2. `<meta charset="utf-8">`;
  3. the policy `<meta http-equiv="Content-Security-Policy">`;
  4. a viewport meta;
  5. the base `<style>` (DD5);
  6. the prelude `<script>` (DD6).
- **The policy** closes every fetch directive explicitly (mission constraint): `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; media-src 'none'; font-src 'none'; connect-src 'none'; frame-src 'none'; child-src 'none'; worker-src 'none'; object-src 'none'; manifest-src 'none'; form-action 'none'; base-uri 'none'`.
- **Planning probes (Playwright Chromium and WebKit, 2026-11-09).** Every probe ran against a local sink:
  - **Zero sink requests** from fetch, XHR, image, `sendBeacon`, WebSocket, form POST, prefetch and CSS `url()`, or from `data:`/`blob:` workers.
  - **Refused:**
    - parent DOM, `top.location`, cookies and storage threw `SecurityError` (cookies read as `""` in WebKit);
    - `window.open` returned `null`;
    - `alert` was suppressed;
    - top navigation threw;
    - a fresh realm through a nested `about:blank` frame threw `SecurityError`.
  - **Removing or loosening the `<meta>`** after parse changed nothing.
- **Why not a separate frame route?** A runaway froze WebKit's page even for a cross-site frame, and full Chromium already isolated `srcdoc`. A route would only add an uncredentialed surface.
- **`.srcdoc` is an HTML sink.** The UI guard today detects only `innerHTML`, `outerHTML` and `insertAdjacentHTML` (`tests/_ui_guard_helpers.py:338-341`). It gains `.srcdoc` assignment and `setAttribute('srcdoc', …)`. The one allowed site is the widget control's document builder, named in the guard with a comment; any other site fails.

**DD3 — The main page denies frame navigation: `frame-src 'none'`**
- **The leak:** a sandboxed `srcdoc` frame can navigate *itself*, by `location.href`, a meta refresh or a link click. That sends a URL out. The planning probe saw it reach the sink in both engines with no page policy, and with `frame-src 'self'`.
- **The fix:** the page header `Content-Security-Policy: frame-src 'none'; child-src 'none'` blocks it, and the `srcdoc` document still loads (it is not fetched).
- **Where it goes:** the `/` route (`app.py` `index()`, today `headers={"Cache-Control": "no-store"}`) also sends that header.
  - It names only those two directives, so it does not affect the page's external scripts, its one inline `<style>` (`index.html:12`) or the CSSOM style writes.
  - The OAuth callback page's inline scripts (`api.py:5385-5410`) are on another route and get no header.
  - It applies in dev mode and in production alike, because the header is on the route.
  - The app has no other iframe.
- **An attempt is visible.** Because `srcdoc` is set before insertion (DD2), any `load` after the first is a navigation attempt: blocked self-navigation, `location.reload()` or a meta refresh. On any such load the control removes the frame and shows "This widget tried to leave its frame and was stopped." The widget then waits for the operator's Start anyway. A reload loop counts as an attempt, which is intended.
- **Chromium side effect:** a blocked navigation adds a dead history entry, measured in design review. Leg 1 records whether the router sees it.
- **Tests:** a unit test pins the header on `/` and its absence from `/api/oauth/callback`.

**DD4 — The only message back is the height; the page identifies the frame by its window**
- **What the frame sends:** the prelude posts `{t: "size", h: <integer>}` to `parent` with target `"*"`. It posts on load, on a `ResizeObserver` of the root, and once a second as a heartbeat (DD9). The heartbeat runs on timer references the prelude captures *before* it installs the pause gate (DD8), so pausing never silences it.
- **How the page receives it:** one module-level `window` `message` listener handles every widget.
  - It identifies the sender by `event.source` against a `Map` of live frames' `contentWindow`, and never by `event.origin`, which is `"null"` for all of them.
  - Unknown sources, wrong shapes and non-finite `h` are dropped.
  - Heights are coalesced to one layout per animation frame, so a message flood cannot jank the page.
  - Only `h` is read.
- **Page → frame** messages carry only `{t: "theme", …}` (DD5) and `{t: "pause"}` / `{t: "resume"}` (DD8).
- **The OAuth listener does not collide.** It checks `evt.origin !== window.location.origin` (`areas/studio/mcp-oauth-consent.js:187`), so a widget's `"null"` origin never reaches its success path. Leg 4 adds a test.

**DD5 — The theme is passed in, and a running widget follows a change**
- **At mount:** the base `<style>` defines the current resolved values as variables: `--bg`, `--surface`, `--fg`, `--fg-muted`, `--border`, `--accent`, `--danger` and `--chart-1` … `--chart-8`. It also sets `color-scheme` and a `data-theme` on the root. Values are read from the page's computed style at mount, and the frame's background is the bubble's surface.
- **On a change:** the page posts `{t: "theme", vars, mode}`. The prelude applies it and dispatches `themechange` on `window`. A widget that cached colours keeps them until it restarts.
- **How the page notices:** `theme.js` `apply()` (`:126-129`) is the one place `data-theme` changes. An OS flip in auto mode fires no event (`:139-143`), so the control keeps one module-level `MutationObserver` on `documentElement`'s `data-theme`. It is created with the first instance and disconnected with the last, and it is documented in the catalogue row.

**DD6 — The prelude is a reviewed constant that closes what the sandbox and policy do not**
- The design review probes found three paths that `sandbox="allow-scripts"` plus the policy leave open. All three were tested in full Chromium, the headless shell and WebKit:
  1. **WebRTC.**
     - **The leak:** a STUN request reached a UDP listener on `127.0.0.1` in all three engines. Adding `webrtc 'block'` to the frame's policy did not stop it. A STUN hostname or a TURN username carries data out over DNS and UDP.
     - **Where it is live:** pywebview never enables WebRTC on GTK (WebKitGTK `enable-webrtc` is off by default), so the path exists in WebView2, WKWebView and browsers.
  2. **History, on WebKit.** `history.back()` / `history.go(-1)` inside the frame moved the *page's* hash and fired the page's `popstate`, so the router reacted. Chromium ignored it, and the Navigation API threw.
  3. **Clipboard.** In Chromium, `execCommand('copy')` on a click inside the frame put the widget's text on the clipboard ("pastejacking"). The async Clipboard API was refused.
- **The fix: neuter these in the prelude, before any model script.** Each is redefined as a non-configurable, non-writable own property:
  - `window.RTCPeerConnection`, `window.webkitRTCPeerConnection` and `window.RTCDataChannel` → `undefined`;
  - `History.prototype.back`, `.forward`, `.go`, `.pushState` and `.replaceState` → no-ops;
  - `Document.prototype.execCommand` → a function that returns `false`.
- **Why that holds:** the probe showed a widget cannot undo these, because deleting a property does not restore it and no fresh realm is reachable. It is defence in depth layered on the sandbox. The sandbox stays the boundary for the app, the credential and the page's DOM.
- **The prelude is one constant in the control,** in a fixed order:
  1. capture the timer references (DD4, DD9), and wrap `clearTimeout`/`clearInterval` so they refuse the prelude's own heartbeat ids (a widget that clears every timer would otherwise read as hung);
  2. neuter (above);
  3. install the pause gate (DD8);
  4. install the size and theme handlers.
  
  Leg 1 pins this order with an empty slot for the pause gate; leg 3 fills the slot and re-pins it. A unit test pins the exact text. A contract test asserts that each neutered name stays neutered after the widget tries `delete` and `Object.defineProperty`.
- **Design review cycle 2 found one more path: WebKit `<link rel=preconnect>`.**
  - **What it does:** in Playwright WebKit, a `preconnect` link in a sandboxed `srcdoc` frame opened a TCP connection to an arbitrary host and port. It did so whether the parser or a script inserted the link, including 500 ms after load, in 2 of 2 runs.
  - **What does not stop it:** the frame's CSP, `x-dns-prefetch-control: off`, and a prelude `MutationObserver`. With a hostname, the DNS lookup carries data. Chromium made no connection.
  - **Status:** it is not closed by this design yet. Leg 1 measures it in real WebKitGTK and WKWebView, which may configure prefetching differently from Playwright's build: WebKitGTK's `enable-dns-prefetching` defaults off, and pywebview may expose preconnect through settings or feature flags.
  - **If it is open there, the gate chooses with the operator:**
    - the WebKit setting or feature flag in the desktop shell;
    - and/or best-effort source and DOM neutering in the prelude (link `rel` setters, `setAttribute`, `innerHTML` on link elements), stated as best-effort;
    - or accepting it as a residual (a connection and DNS lookup with no request body).
  - **Gate result (leg 1, 2026-11-09):** open on WebView2 157, WebKitGTK 2.52.6 and Playwright WebKit (Playwright Chromium reads 0).
    - **Operator decision: layered blocking, in leg 3.**
      1. `buildDocument` rewrites every `<link` tag in the source (case-insensitive) to an inert tag.
      2. The prelude applies the same rewrite to every in-frame HTML entry point: `innerHTML`/`outerHTML` setters, `insertAdjacentHTML`, `document.write`/`writeln`, `DOMParser.parseFromString`, `Range.createContextualFragment`, `setHTMLUnsafe`/`Document.parseHTMLUnsafe`. It also maps `createElement`/`createElementNS` of `link` to an inert element.
      3. A `MutationObserver` backstop removes any `HTMLLinkElement`.
      4. An engine switch is added in the desktop shell where one exists.
    - Each path is a battery case.
    - The prelude's sink words are in the frame's own document, so they never trip the page guards, but the zero-token scan of `js/ui` files does apply: leg 3 builds those names without the literal tokens, or records an exact guard allowance.
    - Any unknown path stays a documented residual.
- **Leftover risk (security model):** an engine API not on this list that opens a network path without a fetch, whether a future API or one the probes did not try. The escape battery (DD17) is the regression net; its sink records HTTP requests, UDP datagrams, bare TCP accepts and DNS lookups.

**DD7 — Lifecycle: run in view, pause off screen, three running, eight loaded** (operator choices, 2026-11-09; amends the mission's earlier "stop and restart")
- **States:**
  - `waiting`: not loaded; shows the card with Start, or a placeholder slot;
  - `running`;
  - `paused-auto`: off screen or `document.hidden`;
  - `paused-user`;
  - `stopped-hung` (DD9);
  - `stopped-escape` (DD3);
  - ~~`stopped-focus` (DD10)~~: dropped at leg 3's design review (DD10).
- **Transitions,** driven by one module-level `IntersectionObserver` (threshold about 0.25):
  - **Entering view:**
    - `waiting` mounts if fewer than three are `running`; otherwise it shows "Paused: three widgets are already running." with Start;
    - `paused-auto` resumes under the same cap;
    - `paused-user`, `stopped-hung` and `stopped-escape` stay as they are.
  - **Leaving view:** `running` becomes `paused-auto`; the frame stays loaded.
  - **Start, when three are running:** it pauses (`paused-auto`) the oldest-started running widget (every `running` widget is in view).
  - **A freed running slot,** or a return to visible, fills in-view slots top to bottom. In-view `paused-auto` widgets resume before `waiting` ones start. It never touches `paused-user` or `stopped-*`.
  - **The loaded ceiling is eight** (`running` + `paused-*`). Loading a ninth unloads, in order of preference:
    1. the `paused-auto` widget that has been off screen longest;
    2. otherwise the off-screen `paused-user` widget that has been off screen longest.
    
    An unloaded widget goes back to `waiting` and restarts from the beginning on return. If nothing off screen can be unloaded, the new widget stays `waiting` with Start, and pressing Start unloads the oldest-loaded widget.
  - **The waiting card** is the header over an empty body at the slot's last height (240 px before the first load). It is seen only briefly, as a widget scrolls in and loads.
  - **Leaving the Chats destination** keeps the chat's DOM, so its widgets stay loaded as `paused-auto` (the observer reports them not intersecting). Probe: a frame inside a hidden container keeps its 1 s heartbeat and cannot take focus.
  - **`document.hidden`** (minimised, another tab) puts every running widget into `paused-auto`. Becoming visible resumes the in-view ones under the cap. The `visibilitychange` listener is module-level, one for all widgets (precedent: `areas/studio/routines-tab.js:500`), and is paired for the guard (`tests/test_ui_guards.py:800`).
  - **Reduced motion:** under `prefers-reduced-motion: reduce`, a widget mounts in `paused-user`, shown as board 2's Paused chip and Resume. The prelude starts gated but lets exactly one animation-frame callback round through, so a `requestAnimationFrame`-driven canvas draws its first frame; then the widget waits for Resume.
- **Teardown.** Committed markdown has no destroy path: `clearLog` (`transcript.js:144-153`) ends in `replaceChildren()`. So:
  - `App.ui.widget.sweep()` destroys every instance that was connected once and is no longer; one built inside a detached fragment and not yet attached is never swept;
  - `clearLog` calls `sweep()` after `replaceChildren()`;
  - every observer callback runs the same check as a backstop;
  - the module-level observers and listeners are released with the last instance.

**DD8 — Pause is cooperative: the prelude gates the widget's clock** (operator choice, 2026-11-09)
- **What the gate controls,** installed after neutering and before any model script, with the original functions captured:
  - `requestAnimationFrame` callbacks queue while paused;
  - `setTimeout`/`setInterval` callbacks that come due while paused are deferred until resume;
  - Web Animations are paused through `document.getAnimations()`, and CSS animations through an injected `animation-play-state: paused !important` rule;
  - `AudioContext` instances (wrapped constructor) are suspended;
  - `performance.now()` and the timestamps passed to `requestAnimationFrame` subtract the total paused time, so time-based animations resume without a jump. `Date.now()` and `new Date()` stay the wall clock: offsetting only some clocks breaks mixed use (cycle 2 measured about 1.6 s apart), and a wall clock should read the wall clock.
  - **Cycle 2 probe:** the gate froze a `requestAnimationFrame` counter, a `setInterval` counter, a CSS animation and a Web Animation, and resumed each with no jump, in all engines. The heartbeat continued. Reassigning, redefining and deleting the wrapped functions did not lift the gate.
- **The header's Pause button** (one button, `aria-pressed`, label Pause ↔ Resume) sends `{t: "pause"}` / `{t: "resume"}`. A widget the operator paused stays paused across scrolling, and shows a "Paused" chip (board 2).
- **Limits, stated in the security model and `docs/widget-format.md`:** pause cannot be enforced.
  - A widget that busy-loops keeps running.
  - So does one that schedules work through a path the gate does not wrap: `scheduler.postTask` (bypassed it in Chromium), a `MessageChannel` loop, `requestIdleCallback`, `element.animate()` started after the pause, or `webkitAudioContext`/`OfflineAudioContext`.
  - Removal stays the only real stop: the loaded ceiling (DD7) and the hang guard (DD9) bound such a widget.
- **Contract tests:** a `requestAnimationFrame` counter, a `setInterval` counter and a CSS animation each stop on pause and continue on resume; the clock offset; the gate survives the widget's attempts to reassign the wrapped functions.

**DD9 — The hang guard** (operator choice, 2026-11-09)
- **What the probes measured** (2026-11-09, Playwright builds, scratchpad):
  - **WebKit:** a 3-4 s busy loop in the frame froze the page's timers for the whole loop, for `srcdoc`, same-site and cross-site frames alike. WebKit runs these frames on the page's thread.
  - **Full Chromium:** the page was unaffected (51 ms maximum gap). That depends on the `IsolateSandboxedIframes` feature and the process-limit policy, not on Chromium as such.
  - **Headless shell:** froze.
  - **WebView2:** measured on WebView2 157.0.4341.42 (leg 1): the page was not frozen (22 ms maximum gap); the frame runs out of process. WebKitGTK 2.52.6 froze (3020 ms), like Playwright WebKit.
- **The guard covers every *loaded* widget** (`running` and `paused-*`), because a paused hostile widget can still loop.
  1. **Crash record.**
     - Each page load takes a random page id and keeps `localStorage["widget-running:{pageId}"]` = `{keys, ts}` while any widget is loaded, rewritten on each heartbeat tick (1 s) and cleared on `pagehide`.
     - At load, a record from another page id whose `ts` is older than 10 s means a page that ended without a normal unload. Its widgets come back `stopped-hung`, with "This widget stopped responding last time." and Start anyway; the record is then deleted.
     - A record with a fresh `ts` belongs to a live tab and is ignored. Two `serve` tabs therefore never clear or misread each other's records.
     - Every storage access is in try/catch; with storage unavailable there is no record (residual, documented).
  2. **Stall detection.** A 1 s page timer measures its gap with `performance.now()`. A gap of 5 s or more stops every loaded widget with "This widget stopped responding."
  3. **Heartbeat.** A loaded widget that sends no size heartbeat for 5 s while the page is ticking is stopped the same way. That catches a hung frame on Chromium/WebView2, where the page stays responsive. The heartbeat survives a pause (DD4), and the widget cannot clear it (DD6).
  
  **No false positives from hiding or suspend** (cycle 2):
  - Both checks are suspended while `document.hidden`, because Chromium throttles hidden timers to as little as once a minute.
  - On becoming visible, the page tick and every widget's last heartbeat are reset.
  - System suspend fires no `visibilitychange`, so leg 1 measures a suspend and resume on Windows. If it trips the stall check, a second rule applies: a gap far beyond any freeze measured by then (for example over 60 s) is treated as a suspend, and resets instead of stopping.
- **A widget's key** is the session id, the message's position in the chat, the block's index in the message and a short hash of the source.
- **Leg 1 measures the false-positive paths,** and the fallback is chosen from the measurements:
  - **Is the key gone at the next launch?** That is the test, not merely whether `pagehide` fired, because WebKit flushes `localStorage` asynchronously. Measure it on tray Quit (Linux), `the-one quit`, `POST /api/window/quit` and window close, in the pywebview shell on Linux and Windows. macOS Dock Quit is measured in leg 6.
  - **Fallback where the key survives:** the desktop shell clears every `widget-running:*` key before it destroys the window. It must use a **bounded, non-blocking** call (`run_js`, or `evaluate_js` on a thread with a timeout). pywebview's GTK `evaluate_js` waits unbounded, and against a page frozen by a widget that would hang the tray Quit, the very recovery path this guard relies on. That would be a shell change, recorded as a leg-4 item under the desktop test-patch rule (DD13).
  - **Browser users:** in a browser (`serve`), closing the whole browser never fires `pagehide` (cycle 2's Playwright proxy). The next visit shows loaded widgets as "stopped responding last time" once. That is accepted and documented.
- **Residual risk (security model):** on WebKit engines one hostile or broken widget can freeze the app's page once, until the page reloads. In the desktop app that means quitting from the tray (Linux) or the Dock (macOS) and relaunching. Leg 1 measures that recovery path on WebKitGTK; the tray runs in the UI process, outside the frozen web process. The guard cannot stop the first freeze.

**DD10 — The card marks the widget as the agent's; focus stays the operator's** (mission constraint)
- **Structure:** every widget sits in `figure.ui-widget` > a header strip > the frame > a "View source" disclosure (boards 1-2).
  - **The header** shows a widget icon and "Widget by {agent}" ("Widget by the agent" when there is no name). When the source has a `<title>`, its text follows, read with a bounded regex as plain text, at most 60 code points, through `textContent`. Then Pause/Resume (DD8) and Restart, plus Start in stopped states.
  - **The card's border and header** are the app's chrome, outside the iframe. The iframe's `title` is "Widget by {agent}".
  - **"View source"** is a closed `App.ui.disclosure` holding an `App.ui.codeBlock`.
- **The focus guard** (rewritten at design review cycle 2: the cycle-1 mechanism could not work).
  - **The problem:** in Chromium (WebView2, browsers) a widget's `input.focus()` takes focus from the composer, even with `allow="focus-without-user-activation 'none'"`, so the operator's typing goes to the widget. WebKit refused the steal in every probe.
  - **What the parent page can see** (cycle 2 probes):
    - On a steal, the parent gets no `focusin`, only `focusout` on the element losing focus and `blur` on `window`.
    - A real click inside the frame sends no `pointerdown` to the parent in any engine.
    - `navigator.userActivation.isActive` is true after a click in the frame, but also after the operator types in the composer.
  - **Gate result (leg 1, 2026-11-09): the primary control is frame-side.**
    - Leg 1 found that no page-side signal tells a click or Tab into the frame from a steal.
    - The prelude wraps `HTMLElement.prototype.focus` and `window.focus`, and strips `autofocus`, so a programmatic focus runs only while the frame's own `navigator.userActivation.isActive` is true. Measured: false for every steal attempt until a real gesture, in Chromium and WebView2 157.
    - The operator adopted this as the primary control, with the page-side mechanism below as the backstop.
  - **Superseded at leg 3's design review (operator decision, 2026-11-09):**
    - **The frame-side gate is the only control.** A programmatic focus runs only while `isActive` **and** a trusted gesture inside the frame happened within about 1 s.
    - **Why tighten it:** with `isActive` alone, a widget could steal focus for about 5 s after the operator's last click inside it (transient activation). The probe saw 8 of 40 characters leak.
    - **The page-side backstop below, the `stopped-focus` state and board 6's "kept taking focus" card are dropped.** The backstop's activation report was forgeable, and it would have undone real clicks into the frame.
    - The text below is kept as the record of the earlier design.
  - **(Superseded) The mechanism (backstop):**
    - A module-level `focusout` listener (paired) and a `window` `blur` listener check `document.activeElement`. When it is a widget's iframe and the move is not the operator's, focus goes back to the element that lost it.
    - **The discriminator** tells the operator's own move into a widget (a click, or Tab) from a steal. Leg 1 probes it and decides it before leg 3 builds. The candidates combine a user activation with no parent `keydown` in the last ~300 ms (a click into the frame), and a last parent key of Tab.
  - **(Superseded) The enforcement is removal:** a widget that triggers more than 3 restores in 1 s is stopped (`stopped-focus`) with "This widget kept taking focus and was stopped." and Start anyway (board 6).
  - **Leftover risk (security model):** a widget can take focus only within about 1 s of the operator's own gesture inside it. That is the operator's interaction with that widget, not a steal. The probes found no other route that moves focus. WebKit never showed the steal.
  - **Tests:** contract tests (leg 3) cover a steal loop while typing, a steal loop after a click in the widget then a click away, a real click into the widget, Tab into it, and a button that focuses an input.
- A widget takes clicks and typing at once, with no click-to-activate (mission constraint).
- **Residuals (security model):** the `<title>` text appears in app chrome and could carry misleading words (it is bounded and plain); a widget can trap Tab inside itself with `preventDefault`, and the operator escapes with a pointer click outside it.

**DD11 — Limits**
- **Source:** 64 KiB, counted in UTF-8 bytes of the block body. Above that, a danger notice says "This widget is too large to run (N KB; the limit is 64 KB)." with the source under Technical details.
- **Running at once:** 3. **Loaded at once:** 8 (DD7).
- **Height:** clamped to 48-720 px, 240 px before the first size message. A taller widget scrolls inside its frame.
- **Width:** a preferred `width: 46rem` inside the assistant bubble (the Flight 1 HAT fix), capped at the bubble.
- **An empty block** renders as a code block (the renderer returns nothing).
- **One source of truth:** these values live in one constants block, and `docs/widget-format.md`, the prompt (DD15) and the eval check (DD16) quote the same numbers.

**DD12 — Streaming, cut-off and the format document**
- **Streaming reuses Flight 1's single path.**
  - The scanner (`visual-stream.js`, DD14) is tag-driven over `{chart, widget}`, and its `open` result reports the tag.
  - The transcript's hold records the tag.
  - The placeholder shows "Rendering widget" with the thinking dots, a generic glimmer block in the card's shape and "Show source" (board 4). Its testid is `chat-widget-placeholder`.
  - The chart placeholder keeps its type shapes unchanged.
  - On commit the card replaces the placeholder, and the widget starts when it is in view.
- **A cut-off widget** (`meta.closed === false`) never runs: partial code is not run. It shows the muted "This widget was cut off before it finished." with the source under Technical details (board 5). This differs from charts, where a valid spec with an unclosed fence still draws.
- **No parse errors:** there is no "couldn't parse"; any text is a document. Errors inside the frame stay inside it.
- **`docs/widget-format.md`** covers:
  - the tag and what the body may contain;
  - the prelude's variables and the `themechange` event;
  - pause behaviour and its limits;
  - what is blocked;
  - the limits.
  
  Flight 3's connector note reads it.
- **Copy reply** still copies the stored markdown. A widget nested in a list item streams raw and is drawn when committed.

**DD13 — pywebview's native bridge must not be reachable from a widget** (go/no-go item)
- **What the bridge can do:** pywebview 5.4 injects `window.pywebview` into the main frame, and its native bridge has built-in calls that move the window and open a native message box.
- **Its handlers check no frame:** GTK `on_js_bridge_call` (`webview/platforms/gtk.py:290`), Cocoa `JSBridge` (`cocoa.py:144-148`), WebView2 `on_script_notify` (`edgechromium.py:195`).
- **Where a frame might reach it:** on WebKit it is `webkit.messageHandlers.jsBridge`, which may be visible in subframes; WebView2's `chrome.webview` may be top-level only.
- **Leg 1 probes it** in the real shells: `the-one app` on Linux, and `windows_test_copy.py --cdp-port` on Windows. From a sandboxed widget it looks for the handlers and tries a move. It observes `GET /api/window/state` and a capture, and whether a native dialog appears.
- **Gate result (leg 1, 2026-11-09):**
  - **Measured:** reachable on WebKitGTK (a replica registration: the frame's `postMessage` reached the handler). Not reachable on WebView2 157 (`chrome.webview` exists in the frame, but a move call from it did nothing, while the same call from the page moved the window).
  - **Operator decision:** switch the bridge off. The desktop shell unregisters `jsBridge` on GTK and Cocoa (the page never calls it; `theme.js` only tests for `window.pywebview`). Leg 4 verifies this in the real Linux shell; leg 6's hosted run verifies it on macOS. A regression probe keeps Windows unreachable.
- **If WebKitGTK reaches it,** WKWebView is assumed to as well (the same `messageHandlers` mechanism). The mitigation then applies to both from leg 4, and leg 6's hosted macOS run confirms by window position (`lifecycle.sh` reads `/api/window/state`).
- **Mitigation candidates,** chosen with the operator at the gate:
  - a shell-side wrapper that drops non-main-frame bridge messages (`WKScriptMessage.frameInfo.isMainFrame`; the GTK equivalent is to be verified);
  - or registering the bridge in the main frame's content world only.
  
  Either becomes a leg-4 item with its own test. `scripts/webkitgtk_probe.py` cannot test this: it is plain WebKit2 without pywebview.
- **Any change to pywebview's bridge or shell** (this mitigation, or DD9's bounded `pagehide` fallback) falls under the `the_one/agents.md` "Desktop test-patch rule and the pywebview/PyObjC upgrade checklist":
  - the canary green;
  - a hosted `macos-packages.yml` `mode=lifecycle` dispatch reading 13 PASS;
  - a `boot_policy` flag where the behaviour differs per platform.
  
  Leg 4 implements under that rule; leg 6 runs the hosted check.

**DD14 — Flight 1 debt, folded in** (operator choice, 2026-11-09)
- **`chart.js` split and measured text width.**
  - **The split:** `chart-parse.js` (parse, validation, formatters), `chart-scale.js` (scales, axes), `chart-layout.js` (the per-type layouts) and `chart.js` (the control, tooltip, keyboard, table, `block`).
  - **Guard rules:**
    - the helper files attach under `App.ui.chart` in non-factory form (`App.ui.chart._parse = …`), because the inventory guard scans `App.ui.X = function` (`tests/test_ui_control_inventory.py:18`);
    - the classes they emit stay owned by the chart row;
    - the `index.html` load order changes so that the helpers load before `chart.js`.
  - **The API and the contract tests do not change,** except where they pin text width.
  - **Measurement:** text width is measured with an offscreen SVG `<text>` and `getComputedTextLength()`, cached per string, font and weight. The 6.4 px estimate stays as the fallback (detached, or a zero result). `docs/chart-format.md` says the browser measures, and that Flight 3's server renderer must use font metrics.
  - **Visible change:** labels are no longer mis-truncated. No other change, so the chart boards stand.
- **`areas/chat/stream-commit.js`** (`App.chat.streamCommit`) takes the pacing timer, `pendingChars`, `commitSafeBoundary`, the hold and the finalize drain out of `transcript.js` (710 lines, against the 800-line area rule), with no behaviour change.
- **Shared visual pieces:**
  - the scanner becomes tag-driven and is renamed `areas/chat/visual-stream.js`;
  - the placeholder gains `label`, `sourceLabel` and a generic shape;
  - `errorBlock` is lifted to `App.ui.visualNotice({tone, headline, reason, source, testid})`, with its own catalogue row and a `test_ui_visual_notice*` contract file. Chart error and cut-off output stays identical in the chart contract tests.
- **Lanes:**
  - `contracts_chat_pat` gains `test_ui_widget*` and `test_ui_visual_notice*`;
  - `chats_transcript_pat` gains `test_flow_chat_widgets.py`;
  - `contracts-chat` and `chats-transcript` are re-budgeted at the closing gate (quiet host).

**DD15 — The prompt: widen the visuals section, with a must-mention list** (Flight 1 debrief recommendation 3)
- **The section:** `visuals` (`platform_prompt.py:142-153`, `:195-201`) keeps its id, title and condition and gains the widget text.
- **The switch's hint widens to:** "Tell this agent it can answer with charts and widgets. When it's off, the agent isn't told, but any chart or widget in its replies is still shown." The testid `agent-rich-visuals-toggle` is unchanged.
- **Must-mention list.** The wording may be trimmed by measurement; every item survives, and the reviewer checks the final text against it:
  1. the tag `widget`;
  2. one self-contained HTML document or fragment with inline `<style>` and `<script>`;
  3. no network or external resources: no URLs, CDNs, fonts or images from the web;
  4. the theme variables by name (at least `--bg`, `--fg`, `--accent`, `--chart-1`…);
  5. use `requestAnimationFrame` (it pauses cleanly), never an endless loop;
  6. the 64 KB limit;
  7. a widget for animation or interaction, and a `chart` for plain data.
- **The chart log-scale fix** ("on an axis" is loose; x log is scatter-only) lands earlier, in DD16 step A1, so step B2 measures only the widget text.

**DD16 — Evals: re-baseline first, then the widget text** (operator choice; order fixed at design review)
- The leg runs in four parts, each with a named tree state:
  - **A1 (product code, no prompt growth).** The log-scale clause fix. `evals/checks.py`'s `_chart_blocks` (`:310-338`) becomes a tag-parametrised top-level scanner, with no behaviour change (mirror tests and falsification move with it).
    - This edits `evals/checks.py`, so `tests/test_evals_freeze.py`'s `SCORING_DIGESTS` changes **in A1**. The operator approves the digest update at A1, as in Flight 1.
    - Review, then commit `C1`.
  - **B1 (quota).** On `C1`:
    - `measure-prompt`, whose fingerprint must differ from `9f213ed2` (the log fix).
    - n=20 runs on the default models (haiku, qwen3-4b, lfm3) for the platform, routines and visuals sets.
    - A1 changed platform prompt text, so these same runs are first compared, different-prompt (plain `compare`, not `--same-prompt`), against `m35-platform`, `m35-routines` and `m35-visuals` (CLAUDE.md "Prompt evals"). The pass-rate gates must hold. It costs no extra quota.
    - They are then recorded as same-prompt baselines: `evals/baselines/m35f2-platform.json`, `m35f2-routines.json` and `m35f2-visuals.json`.
    - Point CLAUDE.md and `evals/README.md` at them, and close squawk 0337 against them (sortie 12 is still in `planning`; re-check at leg start).
    - Commit.
  - **A2 (product code).**
    - The widened `visuals` section (DD15) and the hint.
    - `reply_has_valid_widget(turn=)`. It passes when the reply holds a closed top-level ```` ```widget ```` block of at most 64 KiB, containing a `<script>`, `<canvas>` or `<svg>`, with no external URL in a `src`, `href`, `url(` or `fetch(`/`import`. That last condition is a heuristic, stated as one.
    - `SCORING_DIGESTS` updated again (operator-approved, as in Flight 1).
    - Three new scenarios in **their own set**, `evals/widgets/scenarios/`. `scenarios_fingerprint` hashes every `*.toml` in a directory whatever `--scenarios` selects (`evals/fingerprint.py:48-59`), so adding them to `evals/visuals/scenarios/` would make the four-scenario compare in B2 impossible. The visuals set never changes in this flight. The three:
      - `widget-when-asked`: an animation or an interactive thing;
      - `widget-not-for-data`: a table of numbers, where a chart is expected and a widget is not;
      - `no-widget-unasked`.
    - The pins.
    - Review, then commit `C2`.
  - **B2 (quota).** On `C2`:
    1. an n=5 sentinel on the exposed cells;
    2. n=20 runs;
    3. `measure-prompt`;
    4. `compare --baseline evals/baselines/m35f2-platform.json` and `m35f2-routines.json`. The pass-rate gates must hold; the size gates fail by construction;
    5. a different-prompt `compare` (not `--same-prompt`) of the unchanged visuals set (the four chart scenarios) on the widget prompt, against `m35f2-visuals.json`. This is where "answers charts as widgets" would show;
    6. n=20 runs of the new widgets set.
  - **Operator decision:** accept the growth, or cut the text (keeping the must-mention list) and re-run B2. **Only after acceptance** are the widget-prompt baselines recorded: `m35f2w-platform`, `m35f2w-routines`, `m35f2w-visuals` (the four) and `m35f2w-widgets` (the three). CLAUDE.md and `evals/README.md` are then pointed at them.
- The same-prompt, same-scenario-set rule holds throughout: every set keeps one directory and one fingerprint for the whole flight.

**DD17 — Engine checks are owned by legs** (Flight 1 debrief observation 2)
- **The escape battery** is one fixture, `tests/fixtures/widgets/escape.html`: a widget body that tries every path and draws a pass/fail grid inside itself. It covers:
  - every DD2 path;
  - self-navigation, reload and meta refresh (DD3);
  - WebRTC, history and `execCommand` (DD6), plus `delete`/`defineProperty` on the neutered names;
  - focus theft (DD10);
  - a forged message flood (DD4).
  
  Contract tests read the grid through Playwright's frame access. The probes read the sink and a capture.
- **The sink** records HTTP requests, UDP datagrams (WebRTC STUN) and bare TCP accepts (`preconnect`) on `127.0.0.1`, plus DNS lookups of the battery's unique hostnames. DNS is read through a resolver log or a port-53 capture; leg 1 picks whichever this host and the Windows desktop allow. The battery adds `<link rel=preconnect>` and `dns-prefetch` with a hostname.
- **Page-side assertions:** the page's route and `popstate` count are unchanged, focus stays where it was, and `GET /api/agents` is unchanged.
- **Leg 1 (the gate) runs:**
  - Playwright full Chromium, the headless shell and WebKit (contract tests);
  - WebKitGTK (`scripts/webkitgtk_probe.py --setup-script`, via `window.__probeReport`);
  - WebView2 (`windows_test_copy.py launch --cdp-port`, Playwright `connect_over_cdp`), recording its runtime version;
  - the real pywebview shells on Linux and Windows for DD13;
  - the next-launch key measurements of DD9, and a suspend and resume on Windows;
  - the runaway measurement per engine;
  - the WebKitGTK recovery path;
  - the WebKit `preconnect` and DNS path in real WebKitGTK (DD6);
  - the DD10 focus discriminator probe.
  
  **What gates the go/no-go:** network, the app's DOM, history and the bridge. Focus is **measured, not gating** in leg 1: the guard lands in leg 3, so leg 1 records the steal behaviour per engine and decides the discriminator.
- **Leg 6 (desktop engine pass)** runs the final controls, charts and widgets in both themes:
  - WebKitGTK and WebView2, with DOM assertions;
  - WKWebView through a `macos-packages.yml` dispatch extended with a dev-mode seeded chat, judged by `screencapture` and the sink, plus the DD13 bridge check by window position, the Dock Quit next-launch key check and the `preconnect` path.
  - **The release pins:** `release.yml` forwards its own `macos_mode` choice to `macos-packages.yml` (`:43`, `:131-134`), and `tests/test_release_workflow.py` pins `release.yml`. Leg 6 therefore adds the new step without widening `release.yml`'s choices (a new `macos-packages.yml`-only mode, or an extension of `probe`). It keeps the release pins green, and dispatches only when no release is running.

**DD18 — Tests, the behavior test, mockups and the HAT**
- **Contract tests** (Chromium and WebKit), in `contracts-chat`:
  - `tests/browser/test_ui_widget_contract.py`:
    - frame attributes, the insertion order and the prelude text and order;
    - the escape battery, the neutering, the channels, coalescing and forgeries;
    - theme, pause gating;
    - every DD7 transition, the cap and the ceiling;
    - the hang guard's three paths: stall and heartbeat with a fake clock, and the crash record seeded in `localStorage` with fresh and stale records;
    - the focus guard, the notices, `sweep()`.
  - `test_ui_visual_notice_contract.py`.
- **Flow tests:** `tests/browser/test_flow_chat_widgets.py` in `chats-transcript`, with mock streams paced slower than the 16 ms tick. It covers:
  - the placeholder and the commit swap;
  - history re-render;
  - a widget beside a chart;
  - `clearLog` teardown;
  - the page header;
  - the OAuth listener not reacting to a widget.
- **Unit tests:**
  - the `/` header, and its absence on the OAuth callback;
  - the srcdoc sink guard and its falsification;
  - the prelude's pinned text;
  - the prompt pins and the must-mention list;
  - the eval check offline.
- **The `widget-escape` behavior test** (`tests/behavior/widget-escape.md`) is authored in leg 4 and run before leg 4 lands.
  - **Setup:** a scratch dev instance; the mock provider seeds the escape-battery reply; the sink (HTTP + UDP) runs on `127.0.0.1`.
  - **Act:** Playwright (CDP, real input) opens the chat. The widget runs. The Executor clicks the widget's escape controls, types into the composer while the widget tries to take focus, and uses the browser's Back.
  - **Observe:**
    - the sink log, which must be empty;
    - the page URL, the route and the `popstate` count, unchanged;
    - focus;
    - the app's DOM outside the card, unchanged;
    - no new page or dialog;
    - the frame grid;
    - `GET /api/agents`, unchanged.
  - Both axes are audited at planning: the sink is the read path for the network, the frame grid for results inside the frame, and the app API and page state for the app.
- **Mockups:** see the Mockups section.
- **The HAT** includes a usage walk:
  - a real model asked for an animation, a calculator and a simulation;
  - two widgets and a chart in one reply;
  - scroll a long chat with ten or more widgets (the cap and the ceiling);
  - Pause, scroll away and back, then Resume;
  - theme and OS theme changes while a widget runs;
  - a hostile widget (seeded);
  - the hang guard: a seeded infinite loop, recovery, and "stopped responding last time" after the reload;
  - minimise and restore;
  - Copy reply;
  - Rich visuals off.
  
  The apparatus is self-checked before the operator starts (Flight 1 debrief observation 5): blank lines around fences, paced chunks, and the PID from `ss -ltnp`.
- **The contract the HAT may not change without a spec re-author:**
  - the tag `widget`;
  - `docs/widget-format.md`'s variables, events and limits;
  - the page header;
  - the prelude's neutering list;
  - the testids `chat-widget`, `chat-widget-frame`, `chat-widget-pause`, `chat-widget-restart`, `chat-widget-start`, `chat-widget-source`, `chat-widget-notice` and `chat-widget-placeholder`.

### Mockups
Canvas: https://claude.ai/artifact/RarECj12aPxfKNH81o4UAX (private to the operator)
1. A widget in a reply, dark: the card, "Widget by Atlas · Orbit demo", Pause and Restart, the frame, and View source closed. The operator approved it ("looks good to me so far", 2026-11-09) after asking for Pause.
2. Light, paused by the operator (the "Paused" chip, Resume), with View source open. Approved as above.
3. Stopped states: paused by the cap (Start), stopped by the hang guard (Start anyway) and stopped after trying to leave its frame (Start anyway). Approved as above.
4. Streaming: "Rendering widget", glimmer, Show source. Approved as above.
5. Too large (danger) and cut off (muted). Approved as above.
6. Details (design review cycle 1):
   - the stall variant "This widget stopped responding." beside the crash-record variant;
   - the header with no title and "Widget by the agent";
   - focus rings on Pause and Restart;
   - the card at the narrow (overlay-drawer) width.
   
   Approved by the operator ("all good", 2026-11-09). After design review cycle 2, one more card was added to this board: "This widget kept taking focus and was stopped." (DD10). Approved by the operator ("approve", 2026-11-09). **That card was later dropped** with the `stopped-focus` state, at leg 3's design review (operator decision, 2026-11-09).
- **Explicit OKs needed after design review cycle 2, with no board:**
  - the reduced-motion start uses board 2's paused state (Paused chip, Resume);
  - the brief `waiting` card is the header over an empty body (DD7).
  
  Both approved by the operator ("approve", 2026-11-09).
- **Explicit OKs with no board, all given by the operator ("all good", 2026-11-09):**
  - the chart placeholder is unchanged;
  - charts after measured text width look the same, except that labels are no longer mis-truncated;
  - the widened Rich visuals hint (DD15).

### Citation Audit

Verified against the working tree at `3dc20800` by two read-only research passes, the Flight Director's probes and the Architect's cycle-1 spot checks and probes (scratchpad, 2026-11-09).

| Citation | Status |
|---|---|
| `static/js/markdown.js:925-975` — `renderCodeBlock` consults `codeBlockRenderers` (own keys, functions) at `:929-938`, calls `renderer(source, {lang, closed})`, falls back to the code well on a throw or non-Node | verified |
| `static/js/markdown.js:173-174`, `:181-187` — tag rule; `meta.closed = i < endIdx` | verified |
| `static/js/markdown.js:986-993` — `render` restores the previous `renderOptions` in `finally` | verified |
| `static/js/areas/chat/transcript.js:64-67`, `:144-153`, `:266-275`, `:280-320`, `:322-339`, `:355-373` — `drawChart`/`mdOpts`; `clearLog` ends in `replaceChildren()` with no control teardown; `chartHold`/`dropChartHold`; `commitSafeBoundary`; pacing; finalize; 710 lines | verified |
| `static/js/areas/chat/chart-stream.js:28`, `:49`, `:53`, `:91`, `:137-142` — `chart` hard-coded; opener regex generic | verified |
| `static/js/ui/chart.js` section map; `block()` returns `.el` and discards the handle | verified |
| `static/js/ui/chart-placeholder.js:72`, `:82`, `:100` — chart-only labels | verified |
| `static/js/ui/message.js:58-62`, `:129-179` — `setTailHold` and its invariants | verified |
| `static/js/theme.js:126-129`, `:139-143` — `apply()` sets `data-theme`; OS flip fires no event | verified |
| `static/js/areas/studio/mcp-oauth-consent.js:187` — the OAuth listener checks `evt.origin !== window.location.origin` (corrected at design review; was `:209`, the registration) | verified |
| `static/js/areas/studio/routines-tab.js:500` — `visibilitychange` precedent | verified |
| `tests/test_ui_guards.py:800` — paired document-listener guard for `static/js/ui` | verified |
| `tests/test_ui_control_inventory.py:18` — `_FACTORY` scans `App.ui.X = function` | verified |
| No `IntersectionObserver`, `<iframe>`, `srcdoc`, CSP, `X-Frame-Options` or `frame-src` in `the_one/` or `static/` (grep) | verified |
| `the_one/interfaces/web/app.py` `index()` with `Cache-Control: no-store`; middlewares `:778-791`; StaticFiles `:792` | verified |
| `the_one/interfaces/web/static/index.html:12` — one inline `<style>`; all scripts external | verified |
| `the_one/interfaces/web/api.py:5385-5410` — OAuth callback page inline `<script>` | verified |
| `the_one/interfaces/web/middleware.py:210-212`, `:215`, `:273`, `:58`, `:119-133` — exempt paths; cookie `HttpOnly; SameSite=Strict`; GETs not origin-gated; `"null"` not allowlisted | verified |
| `tests/_ui_guard_helpers.py:338-341` — sink guard covers `innerHTML`/`outerHTML`/`insertAdjacentHTML` only | verified |
| pywebview 5.4 bridge: `util.py:162`; `gtk.py:144`, `:290`; `cocoa.py:144-148`, `:575`; `edgechromium.py:195`; `webview.settings['ALLOW_DOWNLOADS'] == False` | verified (source); frame reachability **unverified → leg 1** |
| `the_one/interfaces/desktop/shell.py:676-686`, `:915`, `:1080-1084` — window options; no `js_api` | verified |
| `scripts/webkitgtk_probe.py:144-193`, `:226-235`, `:312`, `:316-319` — flags, setup scripts, `__probeReport`; plain WebKit2 | verified |
| `scripts/windows_test_copy.py:4940`, `:543` — `--cdp-port` | verified |
| `.github/workflows/macos-packages.yml:41-53` — dispatch modes; no DOM access on the hosted run | verified |
| `the_one/agent/platform_prompt.py:43`, `:142-153`, `:195-201` — `Capabilities.visuals`; `_VISUALS`; the section | verified |
| `evals/checks.py:310-338`, `:341-360`, `:609-611` — chart-only scanner; `reply_has_valid_chart`; registry | verified |
| `evals/fingerprint.py:48-59` — `scenarios_fingerprint` hashes every `*.toml` in the directory regardless of `--scenarios` | verified (Architect, cycle 2) |
| `.github/workflows/release.yml:43`, `:131-134` — `macos_mode` forwarded to `macos-packages.yml`; pinned by `tests/test_release_workflow.py` | verified |
| pywebview GTK `evaluate_js` — unbounded `result_semaphore.acquire()` | verified (Architect, cycle 2) |
| `the_one/interfaces/desktop/shell.py:1080-1084` — `private_mode=False`, so `localStorage` persists across launches | verified (Architect, cycle 2) |
| Cycle-2 probes: the pause gate (rAF, interval, CSS, Web Animations; resume without a jump; gate not removable; `scheduler.postTask` and `MessageChannel` bypass); heartbeat off screen and in `display:none`; 19 further network paths closed; WebKit `preconnect` opens TCP; focus-steal signals (no parent `focusin`/`pointerdown`); restore race; `pagehide` per close kind | verified (Playwright full Chromium, headless shell, WebKit; 2026-11-09) |
| `scripts/run-tests.sh:190-195`, `:253` — explicit lane lists | verified |
| Probes: escape battery, self-navigation with and without page `frame-src`, meta removal/loosening, runaway per engine and origin (Flight Director); WebRTC STUN, `webrtc 'block'`, prelude neutering of WebRTC/History, WebKit `history.back()` into the page, focus theft, `execCommand('copy')`, nested `about:blank` realm, `load` counts by insertion order, `location.reload()` loop, worker fetch (Architect) | verified (Playwright full Chromium, headless shell, WebKit; 2026-11-09) |

### Prerequisites
Each external-session item is **re-verified at the start of the leg that uses it**, not ticked once at planning.
- [x] Flight 1 merged (`3dc20800`, PR #363)
- [ ] Every browser leg: WebKit userland provisioned; contract lanes with `THE_ONE_REQUIRE_WEBKIT=1`; browser runs with `THE_ONE_TEST_NETNS=1`
- [ ] Leg 1: the operator's Windows desktop available for a `windows_test_copy.py` session (hands-off waits); the Linux pywebview shell (`the-one app`) runs on this host
- [ ] Leg 5, at its start: the plan token works; Ollama serves `qwen3-4b` and `lfm3`; `.[evals]` is installed; sortie 12's status is re-checked
- [ ] Leg 6, at its start: a hosted `macos-packages.yml` dispatch is acceptable (Actions minutes) and no release is running; the Windows desktop is available again
- [ ] HAT, at its start: a scratch dev instance on a port ≥ 8490 with a scratch data dir under `$HOME`; a real model that writes widgets (haiku via the plan token)

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [ ] Prerequisites verified (per leg, at leg start)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
1. **Leg 1 (`widget-frame-gate`)** builds the frame core: the document builder, the prelude's capture and neutering parts, the size and theme channel, the insertion order and load-count signal, the `/` header and the srcdoc sink guard. It also builds the escape fixture with its HTTP + UDP sink, and the contract tests in both Playwright engines.
   - It then runs the real engines (WebKitGTK, WebView2) and the pywebview bridge probes.
   - It measures the runaway behaviour per engine, `pagehide` on each quit path, and the WebKitGTK recovery path.
   - It ends with an explicit **go/no-go**, including the DD13 mitigation choice.
2. **Leg 2 (`visual-seams`)** pays down Flight 1's debt (DD14), with no behaviour change beyond measured text width. The existing chart tests are the regression net before new code lands.
3. **Leg 3 (`widget-control`)** completes `App.ui.widget`:
   - the card and marking;
   - the DD7 lifecycle with the cap and ceiling;
   - the pause gate;
   - the hang guard;
   - the focus guard;
   - limits and notices;
   - `sweep()`;
   - catalogue and testid rows;
   - contract tests.
4. **Leg 4 (`widgets-in-chat`)** wires the control into chat:
   - streaming and the placeholder;
   - `sweep()` in `clearLog`;
   - the flow tests;
   - `docs/widget-format.md`;
   - the DD13 mitigation if chosen, and the shell `pagehide` fallback if leg 1 needs it;
   - the `SECURITY-MODEL.md` "Live visuals" section;
   - the `widget-escape` behavior test, authored and run.
5. **Leg 5 (`widget-prompt-and-evals`)**: A1, review and commit, B1 re-baseline, A2, review and commit, B2, then the operator's size decision (DD16).
6. **Leg 6 (`desktop-engine-pass`)**: charts and widgets in WebKitGTK, WebView2 and WKWebView (hosted), plus the macOS bridge and Dock Quit checks.
7. **Leg 7 (`hat`)**: the guided HAT with the usage walk.

Seven legs against the usual one to four. Each boundary is a decision or risk seam:
- the go/no-go after leg 1;
- a refactor net before new code;
- the control proven in isolation before it touches chat (legs 3 and 4 were split at design review for size);
- the quota-spending, operator-gated eval leg;
- the outward-cost engine pass;
- the HAT.

### Checkpoints
- [x] Leg 1 go/no-go (go with mitigations, operator 2026-11-09): the escape battery passes (HTTP + UDP sink silent, route and focus unchanged) in Chromium, WebKit, WebKitGTK and WebView2; runaway behaviour and `pagehide` measured; the bridge question answered
- [x] The chart contract and flow tests pass unchanged after the split (text-width pins aside)
- [x] `App.ui.widget` passes its contract tests in both engines: the lifecycle, pause, guard and focus guard
- [x] A mock-streamed widget shows the placeholder, swaps to the card and runs in view; `widget-escape` passes
- [ ] The re-baseline is recorded; the widget prompt's compares are run; the operator has decided on size
- [ ] Charts and widgets pass in the three desktop engines
- [ ] The full gate is green (`make gate`, `THE_ONE_TEST_NETNS=1`)

### Adaptation Criteria

**Divert if**:
- **No-go at leg 1.** Any escape path reaches the network, the app's DOM, history or focus in a desktop engine, and neither the frame policy, the page header nor the prelude closes it. Re-plan with the operator.
- **The pywebview bridge is reachable from a frame, and no DD13 mitigation works on a platform.** That platform may need click-to-run or no widgets (operator decision).
- **WebView2 freezes like WebKit.** The guard still applies, but the residual-risk text and the HAT change. Tell the operator.
- **`pagehide` does not fire on normal quits, and the shell fallback is not feasible.** The crash record would misfire on every normal quit. Bring the trade-off to the operator: drop the crash record, or keep it with the false positives.
- **The haiku `widget-when-asked` rate is below about 0.5, or the old-four chart scenarios regress on the widget prompt.** Return to DD15 with the operator.

**Acceptable variations**:
- The exact split of `chart.js` into files.
- The stall and heartbeat thresholds (3-10 s) and the focus-guard window (300-1000 ms), if tests show flakes.
- The running cap (2-4) and the loaded ceiling (6-12), if the HAT finds the defaults wrong.
- The baseline file names.
- The prompt's final wording, inside the must-mention list and the measured size the operator accepts.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `widget-frame-gate` - Frame core (document builder, prelude capture and neutering with an empty pause slot, `srcdoc`-before-insert, size and theme channel), the `/` header `frame-src 'none'`, the srcdoc sink guard, the escape fixture with an HTTP + UDP + TCP + DNS sink and Chromium + WebKit contract tests, then the WebKitGTK, WebView2 and pywebview-bridge probes, the WebKit `preconnect` path, runaway, next-launch key, suspend and recovery measurements, and the focus discriminator; ends in the operator go/no-go
- [x] `visual-seams` - `chart.js` split with measured text width, `stream-commit.js`, the tag-driven `visual-stream.js`, the shared placeholder and `App.ui.visualNotice`; no other behaviour change
- [-] ~~`widget-control`~~ - aborted before implementation (too large); split at its design review into the next three legs
- [x] `widget-frame-hardening` - Frame-side controls: the gesture-recency focus gate, layered link blocking (every known bypass), the pause gate with an initial state, `postPause`/`postResume`, the prelude re-pin, the exact guard allowance, and the `contracts-widget` lane
- [x] `widget-card` (leg 4) - `App.ui.widget`: the card and marking, limits and notices, theme, `sweep()`, CSS (including the narrow layout), icons, catalogue and testid rows, contract tests
- [x] `widget-lifecycle` (leg 5) - The DD7 manager as a pure `reconcile(facts)`, the cap (3) and ceiling (8), `visibilitychange`, reduced motion, the DD9 hang guard (crash record with `hidden`-aware staleness, stall, heartbeat via `_clock`/`_tick` seams), contract tests
- [x] `widgets-in-chat` (leg 6) - Chat and streaming wiring, keys, `sweep()` in `clearLog`, flow tests, `docs/widget-format.md`, `SECURITY-MODEL.md` "Live visuals", `agents.md`, and the `widget-escape` behavior test authored and run. The DD13 bridge switch-off and the DD9 next-launch key check moved to `desktop-engine-pass`, which runs the real shells (Flight Director, 2026-11-09).
- [x] `widget-prompt-and-evals` - A1 (log fix, scanner refactor, digests) → review and commit → B1 (compare against m35, then the same-prompt re-baseline; closes squawk 0337) → A2 (widened section, hint, `reply_has_valid_widget`, the new `evals/widgets/` set, pins, digests) → review and commit → B2 (sentinel, n=20, compares including the unchanged visuals set) → the operator's size decision → the widget-prompt baselines
- [x] `desktop-engine-pass` - The DD13 bridge switch-off in the desktop shell (GTK, Cocoa) under the desktop test-patch rule; the DD9 next-launch key check on real quit paths (and the bounded shell fallback if needed); charts and widgets in WebKitGTK (the real `the-one app` shell), WebView2 and WKWebView (a hosted dispatch with a capture and sink), with the bridge confirmed unreachable on all three
- [x] `hat` *(optional, opted in)* - The guided HAT with the usage walk and a pre-walk apparatus self-check

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (`make gate` under `THE_ONE_TEST_NETNS=1`; contract lanes with `THE_ONE_REQUIRE_WEBKIT=1`)
- [ ] Documentation updated (`docs/widget-format.md`, `docs/chart-format.md`, `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `SECURITY-MODEL.md`, `the_one/agents.md`, CLAUDE.md where operator-facing, `evals/README.md`)

### Verification
Each item names its owning leg.
- **Unit tier (legs 1, 3, 5):**
  - the `/` header, and its absence on the OAuth callback;
  - the srcdoc sink guard;
  - the prelude's pinned text;
  - the prompt pins and the must-mention list;
  - the widget eval check offline.
- **Contract lanes, Chromium + WebKit (legs 1, 3):** the frame, the escape battery, the neutering, the channels, the lifecycle, pause, the hang guard, the focus guard and the notices.
- **Flow tests in `chats-transcript` (leg 4).**
- **The `widget-escape` behavior test (leg 4).**
- **Engine probes:** the gate (leg 1) and the pass (leg 6).
- **Evals:** the re-baseline, the widget-prompt compares and the operator's decision, recorded in the flight log (leg 5).
- **The HAT walk (leg 7).**
