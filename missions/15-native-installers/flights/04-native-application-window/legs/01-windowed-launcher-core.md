# Leg: windowed-launcher-core

**Status**: completed
**Flight**: [Native Application Window](../flight.md)

## Objective

Add the core windowed launcher — `uvicorn.Server` on a daemon thread, an
`/api/info` readiness gate, a chromeless pywebview window at the local URL, and
a **shared graceful-shutdown helper** (`should_exit`+join+drain, no-op when this
process owns no server) — exposed via a new `the-one app` subcommand, with
pywebview as an optional `[gui]` extra. `serve`/`chat` stay byte-identical.

## Context

- **DD2 (the load-bearing piece):** GUI loop owns the main thread → run
  `uvicorn.Server` (not `uvicorn.run`) on a daemon thread; gate on readiness;
  `webview.start()` blocks the main thread until the window closes, then returns
  *to the main thread*; **after `start()` returns**, set `server.should_exit =
  True`, then `thread.join(timeout=60)` — the join keeps the daemon alive while
  uvicorn runs the lifespan `__aexit__` (the strict drain `app.py:221-308`,
  ~9 sequential subsystems each ~10s-bounded), then exit. **60s** (not 30s —
  design review: the drain is sequential, worst-case ~90s; 60s covers the normal
  fast path + most slow cases while keeping window-close responsive — a rare
  worst-case teardown truncation is accepted over a 90s hang on close). Verified safe: uvicorn's `capture_signals` is a no-op off the main
  thread (no signal-handler conflict); the bg thread runs only uvicorn and never
  calls into `webview`, avoiding pywebview's close-time deadlocks.
- **Shared shutdown helper (DD4 case-b contract):** the helper must **no-op the
  `should_exit`+join when given no server** (a future window-only client that
  points at an already-running instance owns no local server). Leg 2's fallback
  stop-path reuses this same helper.
- **DD3:** a new `elif args[0] == "app":` branch in `main.py:cli_entry`
  lazy-imports the launcher (so `chat`/`version` never import pywebview).
- **DD1 + CI-install-safety refinement:** the flight's DD1 put pywebview in base
  deps with markers, but `pywebview[gtk]` on Linux pulls **PyGObject**, which
  needs system GTK build headers the CI runner may lack → a base-dep would risk
  breaking the Linux `pip install -e ".[all-llms,dev]"`. **Refinement (this
  leg):** pywebview goes in an **optional `[gui]` extra**, lazy-imported; the
  dev/CI install never pulls it, the launcher tests mock `webview`, and the
  installer (Flight 5) installs `[gui]`. Recorded as a DD1 refinement in the
  flight log.
- **DD8 "chromeless" clarified:** a **native OS window** — native title bar with
  the app name (+ best-effort icon), and **no browser chrome** (no URL/address
  bar — inherent to pywebview; it is not a browser). So `frameless=False`
  (native frame), NOT a borderless window. The "transparent web-underneath" is
  satisfied by the absence of browser chrome, not by hiding the OS title bar.
- **Port = `settings.host`/`settings.port`** (127.0.0.1:8484) directly this leg;
  **port-selection + single-instance + the no-backend fallback are Leg 2** —
  Leg 1 uses the configured port and is allowed to fail if it's taken (Leg 2
  makes it robust). The happy path assumes `[gui]` installed + a WebView backend
  present.
- **Test allocation (refines the flight):** each implementation leg **tests its
  own surface** — Leg 1 ships the launcher-core unit tests (window mocked); Leg
  4 becomes docs + verify-integration + the HAT (not "all launcher tests"). This
  avoids landing untested code; noted in the flight log.

## Inputs

- `the_one/main.py:cli_entry` — `sys.argv` dispatch (`chat`/`serve`/`version`/
  usage). `uvicorn` imported at module top; `serve` does
  `uvicorn.run(app, host=settings.host, port=settings.port)`.
- `the_one/interfaces/web/app.py` — the FastAPI `app` (`:311`), its lifespan with
  the strict shutdown drain (`:221-308`), `/api/info` (`:1634-1636` →
  `{version, base_prompt}`), the SPA index (`:1630-1631`), `/ws` (`:1745`).
- `the_one/config.py` — `settings.host` = `127.0.0.1`, `settings.port` = `8484`.
- `pyproject.toml` — `dependencies` (incl. `httpx>=0.27`, `uvicorn[standard]`,
  the `pywinpty; sys_platform == "win32"` env-marker example),
  `[project.optional-dependencies]`, `[project.scripts] the-one =
  "the_one.main:cli_entry"`.

## Outputs

- `the_one/interfaces/app.py` (new) — the launcher: `run()` (the windowed
  launch), `_graceful_shutdown(server, thread, timeout=60.0)` (shared helper;
  no-op on `server is None`), `_wait_until_serving(host, port, timeout)`
  (httpx `/api/info` readiness poll).
- `the_one/main.py` — `elif args[0] == "app":` branch (lazy-imports the
  launcher) + the usage text gains an `app` line. `chat`/`serve`/`version`
  branches **unchanged**.
- `pyproject.toml` — a new `[project.optional-dependencies]` `gui` extra:
  `pywebview[gtk]>=5,<6; sys_platform == "linux"` and
  `pywebview>=5,<6; sys_platform != "linux"`. (`all-llms` is LLM-only — do NOT fold `gui` into it.)
- `tests/test_app_launcher.py` (new) — launcher-core unit tests (webview mocked).

## Acceptance Criteria

- [ ] `the_one/interfaces/app.py` exists with `run()`,
      `_graceful_shutdown(server, thread, timeout=60.0)`, and
      `_wait_until_serving(...)`. `run()` starts `uvicorn.Server` on a daemon
      thread, waits for readiness, opens a native-framed pywebview window
      (`frameless=False`, title "GleepGlorp AI") at
      `http://{settings.host}:{settings.port}/`, calls `webview.start()`, then
      `_graceful_shutdown(server, thread)`.
- [ ] `_graceful_shutdown` sets `server.should_exit = True` then
      `thread.join(timeout)`, AND **returns immediately (no-op) when
      `server is None`** (the DD4 case-b contract; callers pass both or neither).
- [ ] `the-one app` dispatches to the launcher via a new `cli_entry` branch that
      **lazy-imports** the launcher (no pywebview import on `chat`/`version`);
      the usage text lists `app`.
- [ ] `chat`, `serve`, `version` branches are byte-identical (no behavioral
      change; `serve` still blocks on `uvicorn.run`).
- [ ] `pywebview` is an **optional `[gui]` extra** with the per-platform markers;
      `pip install -e ".[all-llms,dev]"` (no `[gui]`) on Linux still succeeds and
      does NOT pull pywebview/PyGObject.
- [ ] `tests/test_app_launcher.py` (webview mocked) proves: (a) the server starts
      on the daemon thread and serves (httpx GET `/api/info` → 200 against the
      real bg server on an ephemeral port); (b) `_wait_until_serving` returns
      once serving and raises on timeout; (c) `run()` calls
      `webview.create_window(...)` + `webview.start()` (mocked, no GUI) and then
      `_graceful_shutdown`; (d) `_graceful_shutdown` drives `should_exit`+join
      with a server, and **no-ops with `server=None`**.
- [ ] Full default suite green (no regression); lint clean.

## Verification Steps

- `.venv/bin/python -c "import the_one.main; import the_one.interfaces.app"` — imports clean on Linux WITHOUT pywebview installed (the launcher's `import webview` is lazy, inside `run()`).
- `.venv/bin/python -c "from the_one.main import cli_entry"` then exercise dispatch: `the-one version` and `the-one` (chat) behave exactly as before (no pywebview import — confirm via `sys.modules`).
- `.venv/bin/python -m pytest tests/test_app_launcher.py -x --timeout=60 -q` — passes (webview mocked; the bg-thread server serves on an ephemeral port).
- `pip install -e ".[all-llms,dev]"` on Linux succeeds without pulling pywebview: `.venv/bin/python -c "import importlib.util as u; print(u.find_spec('webview'))"` → `None` (unless `[gui]` was explicitly installed).
- Full suite `.venv/bin/python -m pytest tests/ --timeout=300 -q` — green; `serve`/`chat` unaffected.
- `.venv/bin/python -m ruff check the_one/interfaces/app.py the_one/main.py tests/test_app_launcher.py` + `ruff format --check`.

## Implementation Guidance

1. **`the_one/interfaces/app.py`** — the launcher:
   ```python
   from __future__ import annotations
   import threading, time
   import httpx, uvicorn
   from the_one.config import settings

   def _wait_until_serving(host: str, port: int, timeout: float = 15.0) -> None:
       """Poll /api/info until the app actually serves (lifespan startup done)."""
       deadline = time.monotonic() + timeout
       url = f"http://{host}:{port}/api/info"
       while time.monotonic() < deadline:
           try:
               if httpx.get(url, timeout=1.0).status_code == 200:
                   return
           except httpx.HTTPError:
               pass
           time.sleep(0.05)
       raise RuntimeError(f"server did not become ready at {url} within {timeout}s")

   def _graceful_shutdown(server, thread, timeout: float = 60.0) -> None:
       """Drive uvicorn's lifespan shutdown to completion. No-op if no local
       server (a window-only client owns nothing to drain — DD4 case b)."""
       # Callers pass BOTH server+thread, or NEITHER (DD4 case b: a window-only
       # client owns no local server). No-op on `server is None`.
       if server is None:
           return
       server.should_exit = True
       thread.join(timeout=timeout)

   def run() -> None:
       try:
           import webview  # lazy: optional [gui] extra; off chat/version
       except ImportError as exc:
           raise SystemExit(
               "pywebview is not installed. Install the desktop extra: "
               "pip install 'the-one[gui]'"
           ) from exc
       from the_one.interfaces.web.app import app
       host, port = settings.host, settings.port
       config = uvicorn.Config(app, host=host, port=port, log_level="info")
       server = uvicorn.Server(config)
       thread = threading.Thread(target=server.run, daemon=True)
       thread.start()
       try:
           _wait_until_serving(host, port)
           webview.create_window("GleepGlorp AI", f"http://{host}:{port}/")
           webview.start()  # blocks on the main thread until the window closes
       finally:
           _graceful_shutdown(server, thread)
   ```
   - `create_window` default frame (native title bar; no browser chrome) — DD8.
     App icon is best-effort / a Flight-5 concern; don't block on it.
   - Keep `webview` and the web `app` imports **inside `run()`** (lazy).

2. **`the_one/main.py`** — add the branch (keep the existing structure):
   ```python
   elif args[0] == "app":
       from the_one.interfaces.app import run as run_app
       run_app()
   ```
   Add `print("  app    - Open the desktop window (native web view)")` to the
   usage block AND update the header line `"Usage: the-one [chat|serve|version]"`
   → `"...[chat|serve|app|version]"`. Do NOT touch the `chat`/`serve`/`version`
   dispatch branches.

3. **`pyproject.toml`** — add the `gui` extra under
   `[project.optional-dependencies]`:
   ```toml
   gui = [
       "pywebview[gtk]>=5,<6; sys_platform == 'linux'",
       "pywebview>=5,<6; sys_platform != 'linux'",
   ]
   ```
   (If an aggregate `all`/`all-llms` extra exists that's meant to pull
   everything, `all-llms` is LLM-only (openai/anthropic) — do NOT fold `gui` into it; and do
   NOT add pywebview to base `dependencies` or to `dev`, to keep the Linux CI
   install GTK-free.)

4. **`tests/test_app_launcher.py`** — mock `webview` (e.g.
   `monkeypatch.setitem(sys.modules, "webview", MagicMock())` or patch
   `the_one.interfaces.app`'s lazy import) so no GUI is touched. Tests:
   - `_wait_until_serving`: for the **success** case start a **trivial ASGI app**
     (a bare `async def` returning 200 at `/api/info`) on a free port in a
     thread — NOT the full `app` (its DB/factory lifespan is slow/flaky for a
     unit test; the full-app serving is covered separately) — assert it returns;
     for the **timeout** case just pick a free port with nothing listening and a
     short timeout, assert it raises (no server needed).
   - `run()`: **patch `_graceful_shutdown`** (so the test doesn't block on a real
     60s join) and assert it's called once; with `webview` mocked, assert
     `create_window` + `start` were called. Optionally assert `server.started`
     became True before shutdown.
   - `_graceful_shutdown`: with a fake server+thread, asserts `should_exit=True`
     and join called; with `server=None`, asserts it returns without error.
   Pin no sandbox/DB surprises: reuse the conftest `_free_port`-style helper
   (copy the ~5-line bind-to-0 pattern; tests can't import from other tests).

5. **Do NOT** implement port-selection, single-instance, the WebView-backend
   probe, or the browser fallback — those are **Leg 2**. This leg is the
   configured-port happy path + the shared helper Leg 2 builds on.

## Note — pywebview Origin vs OriginAllowlistMiddleware (flag for the Leg-4 HAT)

`app.py:316-319` installs `OriginAllowlistMiddleware` (gates POST/PUT/etc. by
`Origin`; GET + WS-upgrade are NOT gated). The SPA loads via GET and chat goes
over `/ws`, so the **happy path is unaffected**. But the embedded WebView's
`Origin` header for any POST it makes depends on the backend (WebKitGTK /
WebView2) — if it sends `Origin: null` or a non-allowlisted origin, those POSTs
would be blocked. **Validate in the Leg-4 HAT** (the rendered window); if it
blocks, the fix is an allowlist entry for the pywebview origin (a small app
change, its own follow-up). Recorded so it isn't discovered in production.

## Notes for the Flight Director

- This refines two flight decisions (record in the flight log): DD1 base-dep →
  **optional `[gui]` extra** (Linux CI-install safety), and the **test allocation**
  (each leg tests its own surface; Leg 4 = docs + verify + HAT). Both are sound
  and reduce risk; surface them at the 2d review.


## Citation Audit

Citations verified against current code at leg-design time (2026-06-14):
`main.py:cli_entry` (sys.argv dispatch; `uvicorn.run` in `serve`) OK;
`app.py:311` (`app = FastAPI(...)`) OK; `app.py:87-309` (lifespan; strict
shutdown drain ~221-308) OK; `app.py:1634-1636` (`/api/info` →
`{version, base_prompt}`) **repaired** (was :1630-1636); `app.py:1630-1631`
(SPA index) OK; `app.py:1745` (`@app.websocket("/ws")`) OK;
`config.py` `settings.host`/`settings.port` (127.0.0.1:8484) OK;
`pyproject.toml` `[project.scripts] the-one`, `[project.optional-dependencies]`
(`all-llms` is LLM-only) OK; the `pywinpty; sys_platform == "win32"` env-marker
precedent OK. 9 citations verified, 1 repaired.
