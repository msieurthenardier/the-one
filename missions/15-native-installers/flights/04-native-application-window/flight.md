# Flight: Native Application Window

**Status**: planning
**Mission**: [Native Desktop Installers](../../mission.md)

## Contributing to Criteria

- [ ] Launching the installed app opens the agent UI in a **native application
      window**, falling back to the system browser only when no native web view
      is available. *(the windowed-launch capability — the "installed app" wiring
      is Flight 5; rendered-window acceptance is Flight 7 / the next mission's MCP)*

---

## Pre-Flight

### Objective

Add a **windowed launch path**: start uvicorn in-process on a background thread
and open a **chromeless native system-WebView window** pointed at the local
server, so the user experiences a desktop app with the web-underneath fully
transparent. Handle the app lifecycle the desktop form requires — port
selection, single-instance behaviour, and a clean shutdown that honours the
existing lifespan drain order — and degrade to the **system browser** when no
native WebView backend is available. Also fold in the operator-directed
browser-CI cost reduction (path-filter + targeted dedup). The headless
`the-one serve` and CLI `chat` paths are unchanged.

### Open Questions

- [x] WebView mechanism (bundle a shell vs system WebViews) → **resolved, DD1**
      (pywebview / system WebViews; architect-delegated, validated at review)
- [x] uvicorn lifecycle under a GUI main loop → **resolved, DD2**
- [x] Single-instance / port-conflict (mission Open Question) → **resolved, DD4**
- [x] Verification apparatus for a barely-CI-testable native window →
      **resolved, DD6** (launcher logic unit-tested window-mocked; rendered
      window = acceptance; the **next mission's gated MCP is the programmatic
      UI-testing apparatus** — operator-stated, so no heavy behavior test here)

### Design Decisions

**DD1 — pywebview over the three system WebViews; no bundled Chromium.**
`pywebview` wraps **Edge WebView2** (Windows), **WKWebView** (macOS), and
**WebKitGTK** (Linux) behind one URL-pointed API. Dep: `pywebview>=5,<6`, with
the Linux GTK extra (`pywebview[gtk]>=5,<6; sys_platform == "linux"`); macOS
(`pyobjc`) and Windows (`pythonnet`) glue install as hard deps on those
platforms (env markers, mirroring the F3 `pywinpty` convention).
- Rationale: the mission named "system WebView, not a Rust/Node shell." pywebview
  is the only mature Python library wrapping all three with no Chromium bundle,
  takes a plain URL (no JS bridge / built-in server needed — it just points at
  our live uvicorn), and has documented freeze patterns. QtWebEngine is rejected
  (embeds Chromium); Tauri/Electron rejected (freeze Python under a second shell
  for no benefit). **Launcher mechanism delegated to the architect (operator);
  this DD is the architect's recommendation, stress-tested at Phase-5b review.**
- Trade-off: **Linux is the hard platform** — WebKitGTK + PyGObject are *system*
  packages (apt: `gir1.2-webkit2-4.1`, `python3-gi`…), not pip wheels, and
  frequently absent. That absence is precisely the system-browser fallback
  trigger (DD5). (Windows WebView2 ships on Win11 / most Win10; WKWebView is
  built into macOS.) **Flight-5 note (recorded, not this flight):** WebKitGTK is
  AppImage-hostile — prefer a `.deb`/`.rpm` *system-dependency* on WebKitGTK over
  bundling it; the browser fallback is the safety net.

**DD2 — Launcher architecture: `uvicorn.Server` on a background daemon thread;
`webview.start()` on the main thread; graceful shutdown via `should_exit`.**
Native GUI loops must own the main thread, so uvicorn moves off it. Replace the
blocking `uvicorn.run()` (only on the windowed path — `serve` keeps its blocking
call) with a programmatic `uvicorn.Config`/`Server`, run `server.run()` in a
daemon thread, **gate on readiness before opening the window** — poll
`httpx.get("/api/info")` until 200 (stronger than `server.started` alone: it
proves the app lifespan *startup* ran and the app actually serves; reuses the
`tests/browser/conftest.py:83-106` readiness pattern) — to avoid a
connection-refused flash, open the pywebview window, then
`webview.start()` (blocks until close). **Shutdown sequence (load-bearing — there is a real drain-cutoff race; spell it
out, architect review):** `webview.start()` blocks the main thread until the
window closes, then returns *to the main thread*. (1) After `start()` returns,
set `server.should_exit = True` (no `closed` handler needed — drain happens after
the window is gone; the handler is only where DD6's unit test asserts wiring);
(2) the main thread then
**`server_thread.join(timeout=30)`** — the join is the *mechanism* that keeps the
daemon thread alive long enough for uvicorn to run the lifespan `__aexit__` and
**complete the drain** (session reaper → daily purge → PTY registry → MCP pool →
connector pool → save-warm → OAuth sweep → DB — `app.py:221-308`); without the
join, the daemon is killed at interpreter exit mid-drain. uvicorn drives the
lifespan shutdown inside `Server.serve()`'s coroutine — `should_exit` triggers
it, the join waits for it. (3) After the join returns/times out, exit. The join
(not just `should_exit`) is a Checkpoint assertion. **The shared shutdown helper
takes an optional server/thread and no-ops the `should_exit`+join when this
process owns no local server** — DD4 case (b) is a pure window client (no server
to drain), so its close path is simply `start()` returns → exit. Single in-process
server only
— no `reload`/`workers` (they fork/spawn). No per-OS split module (unlike PTY):
pywebview *is* the cross-platform abstraction, so the launcher is one module.
(Verified: uvicorn's `capture_signals` is a no-op off the main thread, so the
daemon-thread server installs NO signal handlers — `should_exit`-driven shutdown
is correct and conflict-free.)

**DD3 — A windowed-launch entry the installer's shortcut invokes;
`serve`/`chat` unchanged.** Prefer a **`the-one app` subcommand** (a new
`elif args[0] == "app":` branch in `main.py:cli_entry`, `main.py:10-31`) over a
second console-script — one entry point, clean dispatch. Keep the existing
**lazy-import** discipline (the web app / pywebview load only inside the `app`
branch, so `chat`/`version` don't drag in pywebview). If Flight 5's installer
shortcut needs a bare executable, a thin `the-one-app` `[project.scripts]` entry
that calls the *same* launcher function is acceptable — but NOT both-and. The
Windows installer's executable is Flight 5's packaging concern, not this flight's.

**DD4 — Port selection + single-instance (resolves the mission Open Question;
architect-resolved).** `/api/info` (`app.py:1634-1636`) returns
`{version, base_prompt}` — **static per build**, so it can tell "a the-one of
this version is on the port" but NOT distinguish a desktop instance from a
`the-one serve` daemon. The launcher therefore makes the pragmatic, **no-app-
change** call: probe the configured port (8484):
- (a) **free** → bind it, open the window.
- (b) **a the-one (200 from `/api/info` with a matching `version`) already on
  the port** → single-instance: **do NOT start a second server**; **open a
  second chromeless window pointed at the running instance's URL** (cheap,
  cross-platform, no IPC). Cross-process native-window *focus* is deliberately
  NOT attempted — it needs three fragile per-OS paths and Wayland disallows it.
  Note: this also single-instances against a running `the-one serve` on 8484
  (one the-one per port) — **accepted and documented as intended**.
- (c) **a non-the-one process holds the port** (200 absent / wrong shape) →
  select a free port (bind-to-0, the `tests/browser/conftest.py:72-80`
  `_free_port` pattern) for this instance and pass it to both uvicorn and the
  window.
The our-the-one-vs-foreign-process split rests on the `/api/info` 200+version
probe (sufficient for this decision); distinguishing windowed-vs-`serve` would
need an `/api/info` field (a source change → its own leg) and is **not** in
scope.

**DD5 — System-browser fallback when no WebView backend is available.** Probe
backend availability *before* creating the window (on Linux, attempt the
`gi`/`WebKit2` GI import; Windows/macOS assume present, with an optional
WebView2-runtime registry check). If absent (typically headless / minimal Linux
without WebKitGTK), start uvicorn anyway and `webbrowser.open(url)`, then keep
serving. Stop path (concrete, architect review): **install a SIGINT handler on
the main thread that sets `server.should_exit = True`, then
`server_thread.join(timeout=30)`** — symmetric with DD2's window-close path,
reusing the same join-and-drain helper (the main thread is free here since no
GUI loop runs). The fallback is *degradation*, not the primary experience (DD8).
pywebview's no-backend error surfaces only at `start()` on the main thread, so
probe-first is preferred over catching it.

**DD6 — Verification: launcher *logic* in CI (window mocked); rendered window is
acceptance; the next mission's gated MCP is the real UI apparatus.** The native
window cannot be meaningfully unit-tested on headless Linux CI (Xvfb +
WebKitGTK is flaky and Linux-only). So: **unit-test the launcher with
`webview.create_window`/`start` mocked** — assert uvicorn starts on the bg
thread, binds the port, serves (hit it with httpx), the readiness gate works,
after the mocked `start()` returns the helper runs `should_exit`+join and the
**lifespan drain completes**, the no-local-server (case-b) close path no-ops
cleanly, port-selection picks correctly across the three cases, and the
fallback path calls `webbrowser.open` + keeps serving. Make `webview` an
injectable/patchable dependency so tests assert `create_window(..., frameless=
True)` + `start()` are called without a GUI, paired with an httpx probe against
the real bg-thread server (mirrors `conftest`) to prove serving. The **actual
rendered
chromeless window** (renders the UI, is chromeless, closes cleanly, single-
instance) is a **per-OS manual acceptance smoke** (Flight 7) — **no heavy
behavior test authored this flight**, because the operator has stated the
**next mission (gated-MCP API) will provide programmatic access to the UI and
all functionality, covering this testing**. Recorded as the forward apparatus.

**DD7 — Browser-CI cost reduction (operator-directed, folded in here).** Scope:
the **`browser` job only** — the *Windows* curation (the other half of the
earlier DD7) already landed in `test.yml` (the "DD7 revised — 2026-06-13"
curated-subset block from F3); this leg must not re-litigate or collide with it.
(a) **Path-filter** the browser job to UI-touching changes only
(`the_one/interfaces/web/**`, the web-serving API, templates). **GitHub Actions
`paths:` filters are workflow/trigger-level, not per-job** — so use a
**`dorny/paths-filter`-style action as a first step** and gate the expensive
Chromium-install + test steps on its output (keeps one workflow; the runner
still spins up but skips the cost). **Required-check caveat:** a path-skipped
required job reports *no* status and can block a PR — but `main` currently has
**no branch protection / required checks** (operator decision, F3), so this is
moot today; the leg should still emit a neutral/success on skip so it stays safe
if protection is added later. (b) **Targeted, light dedup** of the most
redundant browser tests (e.g. `test_markdown` 91, overlapping editor flows) —
*don't over-polish*: the suite is **transitional** (the next mission's gated-MCP
apparatus supersedes Playwright-Chromium as the UI test surface). The full
browser suite's release-gated tier is **Flight 6**. Renderer note: the native
window uses system WebViews, so Playwright-Chromium is a **logic proxy**;
real-WebView checks are acceptance (DD6).

**DD8 — "Transparent native app" UX principle.** The window is **chromeless** —
no browser chrome, no URL/address bar, native title + app icon, behaves like a
desktop application. The system-browser fallback (DD5) is an explicit
degradation for environments lacking a WebView, not the intended experience.
The web-served-underneath nature is not surfaced to the user.

### Prerequisites

- [x] Flight 1 (host-native runtime; data dir; no Docker) — completed.
- [x] The web UI is a no-build-step vanilla-JS SPA served at `/`
      (`app.py:1630`) — the window just points at `http://127.0.0.1:<port>/`;
      no asset rebuild needed.
- [x] The UI's WebSocket (`/ws`, `app.py:1745`) is served by the same in-process
      uvicorn app the launcher runs — **preserved for free**; the window exercises
      the same ASGI app the browser tests drive. No special handling.
- [x] The FastAPI lifespan drain order is documented (`app.py:221-308`) — the
      launcher must let it run on shutdown.
- [ ] `pywebview` + the Linux GTK system packages available on the dev/CI box
      for the launcher *logic* tests (the tests mock the window, so the GUI stack
      isn't strictly needed; confirm the import surface at Leg 1).
- [ ] **Environment/port conflict check**: confirm nothing else on the dev box
      routinely binds `8484` (the single-instance probe must not misfire against
      an unrelated service). Operator confirms at Leg 2.

### Pre-Flight Checklist

- [x] All open questions resolved (launcher mechanism architect-delegated →
      DD1/DD2; single-instance → DD4; apparatus → DD6)
- [x] Design decisions documented
- [x] Prerequisites verified (two confirm-at-leg items, non-blocking to start)
- [x] Validation approach defined (DD6 — CI logic + acceptance smoke)
- [x] Legs defined

---

## In-Flight

### Technical Approach

A new launcher module (`the_one/interfaces/app/` or similar — not a per-OS split;
pywebview abstracts the platforms) runs `uvicorn.Server` on a daemon thread,
gates on `server.started`, opens a chromeless pywebview window at the local URL,
and on close drives `server.should_exit` so the FastAPI lifespan shutdown drain
completes. Port selection + an `/api/info`-signature single-instance probe handle
the desktop lifecycle; a backend probe selects the system-browser fallback when
no WebView exists. A new windowed entry point (DD3) exposes it; `serve`/`chat`
are untouched. The browser CI job is path-filtered and lightly de-duped (DD7).
Verification is launcher-logic unit tests with the window mocked (DD6); the
rendered window is an acceptance smoke deferred to Flight 7 / the next mission's
MCP.

### Checkpoints

- [ ] Windowed launcher starts uvicorn on a bg thread, serves the UI, and the
      readiness gate prevents a pre-bind window flash (unit, window-mocked)
- [ ] Window-close drives a graceful shutdown — the lifespan drain runs to
      completion, no SIGKILL, no orphaned reaper/pool tasks (unit + asserted drain)
- [ ] Port selection + single-instance behave correctly across the three cases
      (free / our-instance / other-process) — DD4
- [ ] System-browser fallback fires when no WebView backend is present, keeps
      serving, and has a working stop path — DD5
- [ ] `serve` and `chat` paths unchanged (regression)
- [ ] Browser CI job path-filtered (skips on non-UI PRs); targeted dedup applied;
      Linux/test lanes green
- [ ] Manual acceptance smoke (operator, real display): a chromeless native
      window opens, renders the UI, single-instances, and closes cleanly

### Adaptation Criteria

**Divert if**:
- pywebview's threading model fights uvicorn/asyncio in a way that can't be made
  reliable (e.g. signal-handler-off-main-thread or loop conflicts that corrupt
  the lifespan drain) → re-evaluate the two-process (multiprocessing) launcher
  model with operator input before further legs
- the single-instance our-instance-vs-other probe proves unreliable (false
  focus/forks) → simplify to "free-port-per-instance, no single-instance
  guarantee" + document, with operator sign-off (it's a UX nicety, not core)

**Acceptable variations**:
- The windowed entry name/shape (subcommand vs console-script) — architect/F5 call
- The exact single-instance surfacing (focus vs second-window vs exit) within DD4
- Launcher module location/structure (single module; pywebview needs no split)
- Whether port-selection + single-instance + fallback are one leg or two

### Legs

> Tentative breakdown — refined per-leg at design time (`/leg`).

1. **windowed-launcher-core** — the `uvicorn.Server`-on-daemon-thread +
   `/api/info` readiness gate + chromeless pywebview window + window-close →
   `should_exit` → **graceful lifespan-drain** shutdown (DD2/DD8). **Establish
   the `should_exit`+`join(timeout=30)`+drain as a SHARED shutdown helper** —
   Leg 2's fallback stop-path reuses it (the one hidden coupling; avoids two
   drifting shutdown paths). The `pywebview` dependency with platform env markers
   (DD1); the new `the-one app` entry (DD3). Leave `serve`/`chat` byte-identical.
2. **port-single-instance-and-fallback** — free-port selection + the
   `/api/info` 200+version our-the-one probe + single-instance behaviour
   (second-window-onto-running-instance; DD4); the WebView-backend probe +
   `webbrowser.open` fallback whose stop-path **reuses Leg 1's shared shutdown
   helper** (SIGINT→should_exit→join; DD5). Resolves the mission Open Question.
   *(May split into single-instance vs fallback at `/leg` time — they share no
   logic; designer's call.)*
3. **browser-ci-path-filter-and-dedup** — path-filter the `browser` job to
   UI-touching paths; targeted (light) dedup of the most redundant browser tests
   (DD7). No coupling to the launcher; separate surface.
4. **tests-docs-and-verify** — launcher-logic unit tests (window mocked: uvicorn
   start/bind/serve, readiness, close→drain, port cases, fallback path — DD6);
   docs (the new windowed entry, the DD8 transparent-app principle, the Linux
   WebKitGTK system-dep + browser-fallback note for F5, the browser-CI change);
   verify-integration (all lanes green; `serve`/`chat` unchanged). **Optional
   HAT/alignment**: operator opens the real window and confirms chromeless/
   native feel + single-instance + clean close (offer; see Phase-4 question).

### Verification

- **Launcher logic (CI)** — unit tests with `webview` mocked: uvicorn starts on
  the bg thread and serves (httpx probe), the `server.started` gate works, the
  `closed` handler sets `should_exit` and the **lifespan drain completes**, the
  three port-selection cases dispatch correctly, and the no-backend path calls
  `webbrowser.open` while keeping the server alive (DD6).
- **Rendered window (acceptance, deferred)** — a per-OS manual smoke (Flight 7):
  chromeless window renders the UI, single-instances, closes cleanly. The
  **programmatic UI-testing apparatus is the next mission's gated MCP**
  (operator-stated) — so no behavior test is authored this flight.
- **No-regression** — `serve`/`chat` unchanged; the path-filtered browser job +
  Linux/test lanes green.
