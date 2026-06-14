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

### Leg 4 — docs implemented + Phase 2d review

- **Docs** (Developer/Sonnet): README "Desktop window" section; agents.md +
  CLAUDE.md launcher developer note (CLAUDE.md guard did NOT trigger). Full
  suite 3074 passed; 17 launcher tests pass.
- **Phase 2d batched review** (Reviewer/Sonnet over all Legs 1-4):
  `[HANDOFF:confirmed]`. Deep-checked the delicate surface — `_graceful_shutdown`
  no-op contract, the daemon-thread + try/finally drain sequence (incl. the
  exception + SIGINT-race paths), `_select_port`'s connect-probe + 3 cases,
  `_webview_available`'s typelib-only probe, the fallback SIGINT wiring, Linux
  import-safety (webview/gi absent), the path-filter, docs accuracy, no
  regressions. **One non-blocking finding fixed by FD:** `create_window` now
  passes `frameless=False` explicitly (DD8 — guards against a pywebview default
  change) + the test asserts it. 17 tests still pass; lint clean.
- All 4 legs → completed. Committing (2d) + opening the draft PR; then the
  operator HAT.

## Deviations

_None yet._

## Anomalies

_None yet._

## Leg Progress

### Leg 1 — windowed-launcher-core

- **Status**: landed (2026-06-13).
- **Two flight refinements (recorded; surface at 2d):**
  - **DD1 base-dep → optional `[gui]` extra.** `pywebview[gtk]` on Linux pulls
    PyGObject (needs system GTK build headers the CI runner may lack) → a base
    dep would risk breaking `pip install -e ".[all-llms,dev]"`. pywebview is now
    an optional `[gui]` extra, lazy-imported; tests mock `webview`; the installer
    (F5) pulls `[gui]`. Sound — keeps the Linux CI install GTK-free.
  - **Test allocation:** each impl leg tests its own surface (Leg 1 ships
    launcher-core unit tests); Leg 4 = docs + verify-integration + HAT (not "all
    launcher tests"). Avoids landing untested code.
- **Design review** (1 cycle, Developer/Sonnet; "approve with changes" — all
  incorporated):
  - Bumped the shutdown **join timeout 30s → 60s** — the drain is ~9 *sequential*
    subsystems (~10s each, worst-case ~90s); 30s undercounted. 60s balances
    teardown vs close-responsiveness (rare worst-case truncation accepted).
  - Tightened `_graceful_shutdown` no-op to `server is None` (both-or-neither),
    not `server or thread is None` (could hide a bug).
  - Lazy `import webview` wrapped → friendly `SystemExit("pip install
    'the-one[gui]'")` instead of a raw ModuleNotFoundError.
  - Test guidance: use a **trivial ASGI app** for the readiness-poll test (the
    full app's DB/factory lifespan is slow/flaky for a unit test); patch
    `_graceful_shutdown` in the `run()` test (don't block on a real 60s join).
  - Usage header bracket updated to include `app`.
  - **New risk recorded:** pywebview's `Origin` header vs the app's
    `OriginAllowlistMiddleware` (GET/WS unaffected; a WebView POST with
    `Origin: null` could be gated) → **validate in the Leg-4 HAT**; fix is an
    allowlist entry if it bites.
- **Implementation (2026-06-13):**
  - Created `the_one/interfaces/app.py` with `run()`, `_graceful_shutdown(server,
    thread, timeout=60.0)`, and `_wait_until_serving(host, port, timeout)` exactly
    per spec.
  - Updated `the_one/main.py`: added `elif args[0] == "app":` branch (lazy-imports
    `run_app`); usage header updated to `[chat|serve|app|version]`; `app` line
    added to usage block. `chat`/`serve`/`version` branches byte-identical.
  - Updated `pyproject.toml`: added `gui` extra under
    `[project.optional-dependencies]` with per-platform pywebview markers.
    `all-llms`, `dev`, and base deps unchanged.
  - Created `tests/test_app_launcher.py`: 6 unit tests (webview mocked via
    `sys.modules` injection). Covers all four acceptance-criteria test surfaces:
    `_wait_until_serving` success (trivial ASGI on ephemeral port) + timeout;
    `_graceful_shutdown` with server and no-op with `server=None`; `run()` asserts
    `create_window` + `start` called and `_graceful_shutdown` called once;
    `run()` raises `SystemExit` when webview missing.
  - Import-clean confirmed: `webview spec: None` on host without `[gui]`.
- **Test counts:**
  - Leg tests: **6 passed** (`.venv/bin/python -m pytest tests/test_app_launcher.py -x --timeout=60 -q`)
  - Full suite: **3063 passed, 10 skipped, 589 deselected** — no regressions.
  - Lint: **clean** (`ruff check` + `ruff format --check` all pass).

### Leg 2 — port-single-instance-and-fallback

- **Status**: ready (design complete). Design review (1 cycle, Developer/Sonnet;
  3 mediums, all incorporated as cleaner designs):
  - `_select_port` → **connect-probe** instead of bind-probe (SO_REUSEADDR gives
    a false-"free" on a TIME_WAIT port → uvicorn would crash on rebind) + a
    **startup-retry** (a the-one mid-startup, port bound but `/api/info` not yet
    200, isn't misclassified as foreign → no spurious second instance).
  - `_webview_available` → probe the **typelib via `gi.require_version` WITHOUT
    importing Gtk/WebKit2** (importing can init GLib / touch a display / hang on
    headless); try 4.1/4.0/6.0 (Ubuntu 22.04 has 4.0).
  - version-mismatch coexist (a different the-one version → 2nd instance on a
    free port, existing untouched) documented as intended; named the webbrowser
    import + the inline SIGINT wiring; flagged the Leg-1
    `test_run_raises_system_exit` needs `_webview_available` patched True post-refactor.
- Next: implement (Phase 2b).
- **Implementation (2026-06-13):**
  - Added `_select_port(host, port, retries=3, delay=0.3) -> tuple[int, bool]` to
    `the_one/interfaces/app.py`: connect-probe (not bind-probe) + startup-retry,
    returning `(port, False)` (free), `(port, True)` (our instance), or
    `(free_port, False)` (foreign process → bind-0 fallback).
  - Added `_webview_available() -> bool`: probes the gi typelib via
    `gi.require_version` without importing Gtk/WebKit2 (avoids GLib init on
    headless); tries versions 4.1/4.0/6.0; True on win32/darwin unconditionally.
  - Refactored `run()`: `_select_port` drives server-or-not; `_webview_available`
    drives window-or-browser. Case (b) starts no server; cases (a)/(c) start
    uvicorn on `sel_port`. Browser-fallback path installs inline SIGINT handler
    (`setattr(server, "should_exit", True)`) then `thread.join()`. Case (b)+no-backend:
    `webbrowser.open(url)` then return. `finally: _graceful_shutdown(server, thread)`
    is a no-op for case (b). Added `import webbrowser` at module top; `import webview`
    stays inside `if _webview_available():` with the Leg-1 friendly-ImportError wrapper.
    The SystemExit message is unchanged (split across two string literals for line-length).
  - Extended `tests/test_app_launcher.py` with 11 new tests (was 6, now 17):
    `_select_port` cases a/b/c; `_webview_available` on win32/darwin/linux-gi-missing/
    linux-typelib-absent/linux-typelib-present; `run()` case (b) no server started;
    fallback calls `webbrowser.open` + installs SIGINT + joins; case (b)+no-backend
    opens browser and returns; existing `test_run_calls_create_window_start_and_graceful_shutdown`
    updated to patch `_select_port` and `_webview_available`; existing
    `test_run_raises_system_exit_when_webview_missing` updated to patch
    `_webview_available → True` (post-refactor the import is only reached when
    `_webview_available` returns True).
  - Import-clean confirmed: `webview spec: None gi spec: None` on host without
    `[gui]`.
- **Test counts:**
  - Leg tests: **17 passed** (`.venv/bin/python -m pytest tests/test_app_launcher.py -x --timeout=60 -q`)
  - Full suite: **3074 passed, 10 skipped, 589 deselected** — 11 net-new tests, no regressions.
  - Lint: **clean** (`ruff check` + `ruff format --check` all pass).

### Leg 3 — browser-ci-path-filter-and-dedup

- **Status**: landed (2026-06-13).
- Design review (1 cycle, Developer/Sonnet; 2 mediums incorporated): added
  **`pyproject.toml`** to the `ui` filter (a Playwright pin bump must re-run
  the suite); clarified that **this flight does NOT touch the web UI** →
  flight/04's own PR browser job correctly **skips** (the filter working —
  that's the FD's primary verification; forcing a positive run is optional).
  Folded: step names, the first-push all-zeros-SHA → runs-all comment,
  dedup-audit-result recorded even if nothing removed.
- Re-scoped after recon: dedup is conservative/optional (test_markdown is 7
  parametrized functions, not 91 redundant) — path-filter is the deliverable.
- **Implementation (2026-06-13):**
  - Edited `.github/workflows/test.yml` — `browser` job only. Inserted a
    `dorny/paths-filter@v3` step (id: `changes`) immediately after `checkout@v5`
    with the `ui` filter on `the_one/interfaces/web/**`, `tests/browser/**`,
    and `pyproject.toml`. Added `if: steps.changes.outputs.ui == 'true'` gate
    to `setup-python@v6`, the new "Install dependencies" step (replaces bare
    `run: pip install …`), "Provision Chromium", and "Run browser tests
    (host-native)". The job now completes green when UI files are unchanged
    (checkout + filter only), satisfying the required-check contract. Added the
    maintenance comment (explaining the ~15-min cost context, surface-addition
    note, and the first-push all-zeros-SHA → runs-all behavior).
  - `windows`, `test`, `bwrap`, `lint` jobs, and top-level triggers are
    **untouched** (diff-verified).
- **Dedup audit (2026-06-13): audit performed, nothing clearly redundant found.**
  Scanned all 63 test files in `tests/browser/`. The big files
  (`test_flow_studio_mcp_editor.py` = 47 functions, `test_flow_dirty_confirm.py`
  = 20, `test_flow_studio_connector_editor.py` = 23) are interaction-flow
  coverage with distinct behaviors per function. Same-named functions across
  files (e.g. `test_beforeunload_listener_prevents_when_dirty` in
  `test_flow_dirty_confirm.py` and `test_flow_provider_dirty_confirm.py`) test
  different UI components (agent editor vs. provider editor) — not duplicates.
  `test_markdown.py`'s "91" are 7 parametrized functions, each a distinct
  markdown scenario. No genuine duplicate test functions found; no tests removed.
  The path-filter is the sole deliverable of this leg.
- **Verification:**
  - YAML parses: `.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml')); print('valid yaml')"` → `valid yaml`.
  - Re-read confirmed: every expensive step carries the `if:` gate; filter paths
    are `the_one/interfaces/web/**`, `tests/browser/**`, `pyproject.toml`.
  - Other jobs confirmed untouched by file review.
  - Lint: `ruff check .github` → `All checks passed!`.

### Leg 4 — docs-verify-and-hat

- **Status**: ready (design complete). **Design-review SKIPPED** (proportionate):
  docs + a manual HAT checklist, no new code logic — the launcher code it
  documents was reviewed in Legs 1-2; the 2d Reviewer covers the docs. Refined
  per Leg 1's test allocation (Legs 1-2 own the launcher tests; Leg 4 = docs +
  verify + HAT).
- Docs (Developer): README desktop section + CLAUDE.md/agents.md launcher note.
  The HAT is operator-guided (their machine + display), the only rendered-window
  check (DD6); validates the Origin-allowlist risk flagged in Leg 1.
- Next: implement docs (2b); then 2d (review all of Legs 1-4, commit, draft PR);
  then guide the operator HAT; then land.
- **Implementation (2026-06-13):**
  - **`README.md`**: added "Desktop window" section between Quickstart and Supported
    LLMs. Covers: `pip install 'the-one[gui]'` + `the-one app`; per-platform WebView
    table (WebView2 / WKWebView / WebKitGTK); Linux system packages (`python3-gi
    gir1.2-webkit2-4.1`, with note on 4.0 fallback); system-browser fallback
    behaviour; single-instance behaviour (one server per port; a second `the-one app`
    or `the-one serve` coexist correctly).
  - **`the_one/agents.md`**: added "Desktop launcher (`the-one app` /
    `the_one/interfaces/app.py`)" section between Architecture Overview and Project
    Conventions. Covers: thread model; `_graceful_shutdown` no-op contract (server is
    None); `_select_port` three cases (free / ours-by-version / foreign→bind-0) +
    connect-probe rationale + startup-retry; `_webview_available` typelib-only probe
    rationale; `[gui]` extra and lazy import; browser-CI path-filter + maintenance rule.
  - **`CLAUDE.md`**: added "Desktop launcher (`the-one app`)" concise section between
    Architecture (orientation) and Configuration. Covers: thread model, shutdown
    no-op, `_select_port` cases, `_webview_available` typelib probe, lazy import,
    pointer to agents.md. CLAUDE.md edit succeeded without triggering a self-modification
    guard (no F1/F3 block encountered on this session — no CLAUDE.md-guard flag needed).
- **Verify:**
  - `.venv/bin/python -m pytest tests/test_app_launcher.py -q` → **17 passed**.
  - `.venv/bin/python -c "import the_one.interfaces.app; import importlib.util as u; print(u.find_spec('webview'))"` → **None** (webview not a base dep; lazy import intact).
  - `.venv/bin/python -m pytest tests/ --timeout=300 -q` → **3074 passed, 10 skipped, 589 deselected** — no regressions.
- **HAT**: operator-run (not spawned). FD to guide separately after 2d review.
- **Status**: landed (2026-06-13).
