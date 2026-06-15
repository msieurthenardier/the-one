# Leg: port-single-instance-and-fallback

**Status**: completed
**Flight**: [Native Application Window](../flight.md)

## Objective

Make the windowed launcher robust for the desktop form: select the port across
the three cases (free / our-instance / foreign-process), single-instance against
any running the-one (open a window onto it, no second server), and fall back to
the system browser when no WebView backend is available — reusing Leg 1's shared
shutdown helper throughout.

## Context

- **DD4 (resolves the mission Open Question):** `/api/info` returns
  `{version, base_prompt}` (static per build) — enough to tell "a the-one of this
  version is on the port," not desktop-vs-`serve`. Pragmatic, no-app-change:
  - (a) **free** → bind the configured port, open the window;
  - (b) **a the-one already on the port** (200 from `/api/info` with
    `version == the_one.__version__`) → single-instance: **do NOT start a second
    server**; open a window pointed at the running instance's URL (this process
    owns no server → its close path calls `_graceful_shutdown(None, None)`, a
    no-op — the Leg-1 case-b contract). Also single-instances against a running
    `the-one serve` (one the-one per port — accepted, documented).
  - (c) **a non-the-one process holds the port** → select a free port (bind-0)
    for this instance and pass it to both uvicorn and the window.
- **DD5 (fallback):** probe WebView-backend availability *before* creating the
  window; if absent (typically headless / minimal Linux without WebKitGTK),
  `webbrowser.open(url)` and keep serving — stop path **reuses Leg 1's shared
  helper**: install a SIGINT handler on the main thread that sets
  `server.should_exit = True`, then `server_thread.join()` (the drain completes;
  the main thread is free since no GUI loop runs).
- **Builds on Leg 1:** `the_one/interfaces/app.py` already has `run()`,
  `_graceful_shutdown(server, thread)` (no-ops on `server is None`), and
  `_wait_until_serving(host, port, timeout)`. This leg refactors `run()` to add
  port-selection + the backend-probe branch; the helpers are reused, not
  rewritten.
- `the_one.__version__` is `"0.2.0"` (`the_one/__init__.py:3`) — the
  single-instance version match.

## Inputs

- `the_one/interfaces/app.py` (Leg 1) — `run()`, `_graceful_shutdown`,
  `_wait_until_serving`.
- `the_one/config.py` — `settings.host`/`settings.port` (127.0.0.1:8484).
- `the_one/__init__.py:3` — `__version__`.
- `tests/test_app_launcher.py` (Leg 1) — extend with the new cases.

## Outputs

- `the_one/interfaces/app.py` — add:
  - `_select_port(host, port) -> tuple[int, bool]` → `(port_to_use,
    is_our_instance)` implementing cases a/b/c.
  - `_webview_available() -> bool` → True on Windows/macOS; on Linux attempt the
    `gi`/`WebKit2` GI import (catch `ImportError`/`ValueError`).
  - refactored `run()` wiring the three port cases × the webview/browser branch
    (incl. the fallback SIGINT→should_exit→join stop path).
- `tests/test_app_launcher.py` — extended unit tests (all webview/gi mocked).

## Acceptance Criteria

- [ ] `_select_port` returns: **(configured_port, False)** when the port is free;
      **(configured_port, True)** when a the-one with a matching `version` answers
      `/api/info` on it; **(free_port, False)** when a non-the-one process holds
      the configured port. (Probe `/api/info` for ours; else try to bind the
      configured port — bindable = free, not-bindable = foreign → bind-0 free
      port.)
- [ ] `_webview_available()` returns True on `win32`/`darwin`; on `linux`
      probes the `gi`/`WebKit2` import and returns False when absent. Pure
      function, mockable.
- [ ] `run()` (refactored): case (b) **starts no server** and opens a window
      pointed at the running instance (close path is the `_graceful_shutdown`
      no-op); cases (a)/(c) start the server on the selected port. When
      `_webview_available()` is **False**, the path `webbrowser.open(url)` +
      install a SIGINT handler that sets `server.should_exit` + `join` (drain
      completes) — and for case (b)+no-backend, just open the browser at the
      running URL and return (no server to stop).
- [ ] The system-browser fallback reuses Leg 1's `_graceful_shutdown`/shutdown
      semantics — no second shutdown code path.
- [ ] `serve`/`chat`/`version` still byte-identical; Leg 1's tests still pass.
- [ ] Extended `tests/test_app_launcher.py` (webview + `gi` + httpx/socket
      mocked) covers: the three `_select_port` cases; `_webview_available`
      True/False; `run()` case-(b) opens a window with NO server started; the
      no-backend fallback calls `webbrowser.open` + installs SIGINT + joins.
- [ ] Full suite green; lint clean; the launcher still imports clean on Linux
      without pywebview/gi installed (probes are mocked in tests; real probes are
      inside functions, lazy).

## Verification Steps

- `.venv/bin/python -m pytest tests/test_app_launcher.py -x --timeout=60 -q` — passes.
- `.venv/bin/python -c "import the_one.interfaces.app"` — clean on Linux without pywebview/gi (the `gi` import is inside `_webview_available`, the `webview` import inside `run()`).
- Full suite `.venv/bin/python -m pytest tests/ --timeout=300 -q` — green.
- `.venv/bin/python -m ruff check the_one/interfaces/app.py tests/test_app_launcher.py` + `ruff format --check`.

## Implementation Guidance

1. **`_select_port`** — **connect-probe** (NOT a bind-probe: a bind-probe with
   `SO_REUSEADDR` gives a false "free" on a `TIME_WAIT` port → uvicorn then
   crashes on rebind — design review). Plus a **startup-retry** so a the-one
   that just bound but hasn't finished lifespan startup (`/api/info` not yet 200)
   isn't misclassified as foreign:
   ```python
   import socket, time
   from the_one import __version__

   def _select_port(host: str, port: int, retries: int = 3, delay: float = 0.3) -> tuple[int, bool]:
       for attempt in range(retries):
           # (b) a the-one of OUR version already answering? (json() raises
           # JSONDecodeError, a ValueError subclass, on a non-JSON 200)
           try:
               r = httpx.get(f"http://{host}:{port}/api/info", timeout=1.0)
               if r.status_code == 200 and r.json().get("version") == __version__:
                   return port, True
           except (httpx.HTTPError, ValueError):
               pass
           # is ANYTHING listening? connect-probe — no bind race.
           with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
               s.settimeout(0.5)
               occupied = s.connect_ex((host, port)) == 0
           if not occupied:
               return port, False          # (a) free — fast path, no retry
           if attempt < retries - 1:
               time.sleep(delay)            # occupied-not-(yet)-ours: a starting
                                            # the-one? give it the startup window
       # (c) occupied by a foreign process (or a the-one that never confirmed) →
       # a different the-one VERSION lands here too (→ a 2nd instance on a free
       # port; the existing one is untouched — intended upgrade-coexist behavior)
       with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
           s.bind((host, 0))
           return s.getsockname()[1], False
   ```

2. **`_webview_available`** — **probe the typelib WITHOUT importing/initializing
   GTK** (importing `Gtk`/`WebKit2` can init GLib / touch a display / hang on a
   headless box — design review). `gi.require_version` only checks the typelib is
   installed; it does not import or initialize anything:
   ```python
   import sys

   def _webview_available() -> bool:
       if sys.platform in ("win32", "darwin"):
           return True  # WebView2 (Win) / WKWebView (mac) assumed present
       try:
           import gi
       except ImportError:
           return False
       for ver in ("4.1", "4.0", "6.0"):   # Ubuntu 22.04 has 4.0; newer 4.1; GTK4 6.0
           try:
               gi.require_version("WebKit2", ver)
               return True                  # typelib present — do NOT import Gtk/WebKit2
           except ValueError:
               continue
       return False
   ```
   Mockable in tests by patching `the_one.interfaces.app._webview_available`.

3. **Refactor `run()`** — pseudocode:
   ```python
   def run() -> None:
       host, port = settings.host, settings.port
       sel_port, is_ours = _select_port(host, port)
       url = f"http://{host}:{sel_port}/"
       server = thread = None
       if not is_ours:
           server = uvicorn.Server(uvicorn.Config(app, host=host, port=sel_port, log_level="info"))
           thread = threading.Thread(target=server.run, daemon=True); thread.start()
           _wait_until_serving(host, sel_port)
       try:
           if _webview_available():
               import webview  # friendly SystemExit on ImportError (Leg 1)
               webview.create_window("GleepGlorp AI", url)
               webview.start()        # blocks until window closes
           else:
               webbrowser.open(url)
               if server is not None:
                   _install_sigint_should_exit(server)   # main thread free
                   thread.join()       # blocks until SIGINT → should_exit → drain
               # case (b)+no-backend: nothing to block on; just return
       finally:
           _graceful_shutdown(server, thread)   # no-op when server is None (case b)
   ```
   Move the lazy `from the_one.interfaces.web.app import app` to where the server
   is built. Keep the Leg-1 friendly-ImportError wrapper on `import webview`
   (it lives inside `if _webview_available():`). `import webbrowser` (stdlib) at
   module top. The SIGINT wiring is inlined in `run()` (main thread only):
   `signal.signal(signal.SIGINT, lambda *_: setattr(server, "should_exit", True))`
   — the handler stays installed for the process lifetime (fine; the launcher
   exits after `join()`). For **case (b)+no-backend**: `webbrowser.open(url)` then
   return immediately (no server to block on — the process exits; intended:
   open a tab onto the running instance and quit).

4. **Tests** — mock `webview` (sys.modules) and patch `_webview_available`,
   `_select_port`, and `httpx`/`socket` as needed so no real GUI/port work runs:
   - `_select_port`: (a) patch httpx to raise ConnectError + leave the port
     bindable → `(port, False)`; (b) patch httpx 200+matching version →
     `(port, True)`; (c) patch httpx non-the-one + make `bind(port)` raise OSError
     → returns a bind-0 free port with `False`.
   - `_webview_available`: monkeypatch `sys.platform`; for linux, inject a fake
     `gi` into `sys.modules` that raises / succeeds.
   - `run()` case (b): patch `_select_port` → `(port, True)`; assert NO
     `uvicorn.Server` constructed and `create_window` called at the running URL.
   - fallback: patch `_webview_available` → False; assert `webbrowser.open`
     called and the SIGINT-handler + join path runs (patch `signal.signal` and
     `thread.join`).
   - **Update the existing Leg-1 `test_run_raises_system_exit_when_webview_missing`**:
     after the refactor `import webview` is inside `if _webview_available()`, so
     that test must patch `_webview_available` → True (else the import is never
     reached and the SystemExit never fires).

5. **Do NOT** change the `serve`/`chat`/`version` branches or the Leg-1 helper
   signatures (extend, don't break).

## Citation Audit

Citations verified at leg-design time (2026-06-14): `app.py` Leg-1 functions
`run`/`_graceful_shutdown`/`_wait_until_serving` (`:37`/`:26`/`:12`) OK;
`config.py` `settings.host`/`settings.port` OK; `the_one/__init__.py:3`
`__version__ = "0.2.0"` OK; `/api/info` → `{version, base_prompt}`
(`app.py:1634-1636`) OK; `tests/browser/conftest.py` `_free_port` bind-0 pattern
OK. 5 citations verified, all clean.
