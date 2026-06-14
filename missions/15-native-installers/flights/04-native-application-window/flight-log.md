# Flight Log: Native Application Window

**Flight**: [flight.md](flight.md)
**Started**: — (planning)

## Summary

_Pending execution._

## Reconnaissance Report

Planning-time recon (2026-06-14), two parallel passes:

### App launch + web-serving surface (what the launcher integrates with)
- **Launch today:** `the-one serve` → **blocking `uvicorn.run(app, host, port)`**
  (`main.py:21`). `chat` → CLI; `version` → prints. The web UI is a no-build
  vanilla-JS SPA served at `/` (`app.py:1629`), static mounted at `/static`
  (`app.py:320`). The window just points at `http://127.0.0.1:<port>/`.
- **Lifespan drain is strict-ordered** (`app.py:221-308`): session reaper → daily
  purge → PTY registry → MCP pool → connector pool → save-warm → OAuth sweep →
  DB close. The windowed launcher MUST let this run on shutdown (drive
  `server.should_exit`, join the thread) — not SIGKILL.
- **Missing today (all net-new):** port selection (8484 hardcoded, hard-fails if
  taken — `config.py:28-30`), single-instance guard (none), clean-shutdown wiring
  (none), webview dep (none). The browser tests get free ports via
  `_free_port()` (`tests/browser/conftest.py`) — not usable for a single-instance
  desktop app.
- **Platform pattern:** the F3 `pty.py` split-module dispatcher is the project's
  per-OS template — BUT pywebview already abstracts the three WebViews, so the
  launcher needs **no** equivalent split (one module). Dep convention: F3's
  `pywinpty; sys_platform == "win32"` env marker.

### pywebview / native-window mechanism
- **pywebview is the confirmed choice** — wraps WebView2 / WKWebView / WebKitGTK,
  no Chromium, takes a plain URL. `pywebview>=5,<6`; Linux `[gtk]` extra.
- **Threading (load-bearing):** `uvicorn.Server` on a daemon thread (NOT
  `uvicorn.run()`), `webview.start()` on the main thread (blocks); poll
  `server.started` before opening the window; `closed` event → `should_exit`.
  Don't rely on uvicorn's own signal handlers off-main-thread — own shutdown via
  `should_exit`. No `reload`/`workers`.
- **Linux is the hard platform:** WebKitGTK + PyGObject are *system* packages
  (apt), often absent → the fallback trigger. Windows WebView2 ships on Win11/
  most Win10; macOS WKWebView built-in.
- **Fallback:** probe backend (Linux `gi`/`WebKit2` import); absent →
  `webbrowser.open` + keep uvicorn alive (distinct stop path).
- **Testability:** launcher logic unit-testable with the window mocked; the
  rendered window is real-display/per-OS acceptance (Xvfb+WebKitGTK is flaky,
  Linux-only — not worth it). **Operator-stated:** the next mission's gated MCP
  is the programmatic UI-testing apparatus → no heavy behavior test here.
- **Freeze (F5 forward):** Windows/macOS clean; Linux WebKitGTK is AppImage-
  hostile → prefer a `.deb`/`.rpm` system-dependency over bundling; browser
  fallback is the safety net.

### Operator steering (2026-06-14)
- Windows installer = a regular installer that installs an executable; **how it
  opens is the architect's technical call** (→ DD1/DD2, validated at Phase 5b).
- The **next mission (gated-MCP API)** will provide programmatic access to the UI
  + all functionality, **covering UI testing** → keep this flight's verification
  light (DD6); the browser suite is transitional (light dedup only, DD7).
- **"Web-underneath is transparent to the user"** → chromeless native window,
  no URL bar (DD8); browser fallback is degradation only.

## Design Review (Phase 5b)

Two Architect review cycles (2026-06-14), both "approve with changes"; all
incorporated. The architect verified the load-bearing facts against the
installed code, not just the docs.

- **Round 1** (2 high, 4 med/low): [high] DD2 shutdown had a real drain-cutoff
  race → spelled out the `should_exit`→main-thread-`join(timeout=30)`→drain→exit
  sequence (the join is what keeps the daemon alive for the lifespan
  `__aexit__`); verified uvicorn's `capture_signals` is a no-op off the main
  thread (no signal conflict). [high] DD4's `/api/info` returns only
  `{version,base_prompt}` (static per build) → resolved to the no-app-change
  option (any the-one 200+version = "our instance"; second-window onto the
  running instance; single-instances against `the-one serve` too, documented;
  cross-process focus dropped — Wayland disallows it). [med] DD5 fallback
  stop-path made concrete (SIGINT→should_exit→join, reusing the DD2 helper);
  DD7 path-filter mechanism named (`dorny/paths-filter` first-step + per-step
  `if:` gating — `paths:` is workflow-level not per-job) and scoped to the
  browser job only (the Windows DD7 curation already landed in test.yml); DD3
  → `the-one app` subcommand + lazy-import. Suggestions folded: `/ws` preserved
  for free, the `/api/info` readiness poll, the DD6 mock surface, the Leg-1
  shared-shutdown helper.
- **Round 2** (1 med, 2 low): [med] DD4 case (b) is a window-only client with no
  local server → the shared shutdown helper must no-op `should_exit`+join when
  this process owns no server (else Leg 1's helper and Leg 2's case-b
  contradict). Simplified DD2 to "set should_exit after `start()` returns" (no
  `closed` handler needed; verified `start()` blocks then returns on the main
  thread; the uvicorn-background-thread-never-calls-into-webview direction
  avoids pywebview's known close deadlocks). DD7 neutral-emit wording corrected
  (gated inner steps → job goes green on skip; no shim needed) + the push-lane
  base/ref note. Max 2 cycles; spec locked.

## Crew Sign-off (Phase 6)

Operator approved the spec → **ready** (2026-06-14). Confirmed: (1) single-
instance default stands — **one the-one per port** (a `the-one serve` daemon and
the window won't double-bind 8484; the window opens onto the running instance;
no app change); (2) the **optional HAT is included** (operator opts in to the
rendered-window manual smoke in Leg 4). No spec changes required by the sign-off.

## Decisions

_Pending execution — planning-time decisions live in flight.md Design Decisions._

## Flight Director Notes

**2026-06-14 — Flight execution started (`/agentic-workflow`).**
- Branch `flight/04-native-application-window` **stacked on `flight/03`** (operator
  is cascading all M15 PRs after this flight). Crew file valid.
- **Crew-file test-command override (same as F3):** the Implement prompt says
  `docker exec the-one pytest …` — stale (Docker retired in F1). FD issues
  host-native `.venv/bin/python -m pytest …` directly per spawn.
- **Cadence: NORMAL batch model** (not CI-platform-gated — the launcher logic is
  Linux-testable with the window mocked, DD6). Defer code review + commit to
  Phase 2d (one review, one commit), unlike F3's per-leg-push CI-gating cadence.
- **Reviewer scaling:** Sonnet for the launcher legs (1, 2 — threading + the
  shutdown-drain-join is delicate); Haiku-default acceptable for the CI leg (3)
  and docs (4). No security surface.
- **Leg 4 HAT is interactive** (operator opts in) — guided manually, not spawned.
- Flight `ready` → `in-flight`. Starting Leg 1 design.

## Deviations

_None yet._

## Anomalies

_None yet._

## Leg Progress

_Pending leg design._
