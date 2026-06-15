# Leg: single-instance-focus

**Status**: completed
**Flight**: [Windows Native App Hardening — Desktop Presence & Lifecycle](../flight.md)

## Objective

Make a second `the-one app` launch **raise the already-running window and exit**
instead of opening a duplicate — via a new `POST /api/window/focus` endpoint the second
process calls on the running instance — closing F4's duplicate-window gap.

## Context

- Flight DD4: single-instance focus through `/api/window/focus`, a **header-less
  loopback POST** that needs **no Origin-allowlist change** (verified:
  `the_one/interfaces/web/middleware.py:80-84,128-147` — the middleware rejects a gated
  POST only when an `Origin` header is present AND not allow-listed; a header-less
  request passes, and loopback origins are wildcard-allowed).
- The windowed app runs uvicorn **in-process** (F4 / Leg 1), so the endpoint handler
  (in the web app) can reach the pywebview window that `run_desktop()` created. Leg 2
  already keeps a module-level window reference (`_desktop_window`) in `desktop/shell.py`.
- F4's `run_desktop()` today: on `is_ours=True` it skips starting a server but **still
  opens a second window** against the running instance — the gap this leg closes.
- Marshalling: the handler runs on a uvicorn worker thread and calls into pywebview's
  GUI thread — use pywebview's **thread-safe** `show()`/`restore()` (the one marshalling
  story established in Leg 2), never native handles.

## Inputs

- `the_one/interfaces/web/app.py:1634 — "@app.get(\"/api/info\")"` — the route-style
  pattern; add `@app.post("/api/window/focus")` beside it.
- `the_one/interfaces/web/middleware.py:OriginAllowlistMiddleware` — confirms a
  header-less loopback POST passes (DD4).
- `the_one/interfaces/desktop/shell.py` — `run_desktop()` + the module-level window
  reference (`_desktop_window`) from Leg 2; `_select_port` returns `(port, is_ours)`.

## Outputs

- `the_one/interfaces/web/app.py` — new `POST /api/window/focus` handler that lazily
  imports `the_one.interfaces.desktop.shell` and calls a `focus_window()` function;
  returns `{"focused": bool}` 200.
- `the_one/interfaces/desktop/shell.py` — a `focus_window() -> bool` that raises/restores
  the module window (no-op `False` when no window is registered, e.g. `serve` mode); and
  the `run_desktop()` change: on `is_ours=True`, POST `/api/window/focus` (header-less)
  and **return** instead of creating a window.
- `tests/test_window_focus.py` — new; endpoint + focus-fn + focus-and-exit-branch tests.

## Acceptance Criteria

- [ ] `POST /api/window/focus` exists and returns **200** with `{"focused": true}` when
      a desktop window is registered (handler calls `focus_window()` →
      `window.show()` + `window.restore()`). (Tested via the web app's test client with
      `focus_window`/window mocked.)
- [ ] When **no** window is registered (e.g. `the-one serve`), the endpoint returns
      **200** `{"focused": false}` — it does **not** 500. (Tested: no window → no-op.)
- [ ] A **header-less** POST to `/api/window/focus` is **not** rejected by
      `OriginAllowlistMiddleware` (returns 200, not 403). (Tested with the test client
      sending no `Origin` header.)
- [ ] `run_desktop()` on `is_ours=True` POSTs to `http://{host}:{port}/api/window/focus`
      **with no `Origin` header** and **returns without creating a window**
      (no `webview.create_window`). (Tested: `_select_port` mocked → is_ours; httpx.post
      mocked; assert the POST target + headers, and that no window is created.)
- [ ] On `is_ours=False`, behavior is unchanged from Leg 2 (server starts, window opens,
      tray wires up). (Regression: existing shell/tray tests still pass.)
- [ ] If the focus POST raises (running instance momentarily unreachable), `run_desktop()`
      logs and **still exits** (the instance exists; opening a duplicate is the gap we're
      closing) — it does not crash or open a window. (Tested: httpx.post raising →
      run_desktop returns cleanly, no window.)
- [ ] `tests/test_window_focus.py` passes host-native; Leg 1/2 tests
      (`test_desktop_shell.py`, `test_desktop_tray.py`) still pass.

## Verification Steps

- `python -m pytest tests/test_window_focus.py tests/test_desktop_shell.py tests/test_desktop_tray.py -x --timeout=30 -q`
  (host-native — NOT docker) — all green.
- `python -c "from the_one.interfaces.web.app import app; print([r.path for r in app.routes if getattr(r,'path','')=='/api/window/focus'])"`
  — prints `['/api/window/focus']`.
- Web app still imports without a GUI stack:
  `python -c "import the_one.interfaces.web.app; print('web import ok')"` (the desktop
  import in the handler is lazy — not at module load).
- `git diff --stat` — scoped to `the_one/interfaces/{web/app.py,desktop/shell.py}` + `tests/`.

## Implementation Guidance

1. **`focus_window()` in `desktop/shell.py`** — read the module window ref; if `None`
   return `False`; else call `window.show()` then `window.restore()` (thread-safe
   wrappers — the Leg-2 marshalling rule) and return `True`. Guard in try/except → log +
   return `False` on failure (don't propagate into the HTTP handler).

2. **The endpoint** in `interfaces/web/app.py`, beside `/api/info`:
   ```python
   @app.post("/api/window/focus")
   async def window_focus() -> dict[str, Any]:  # `Any` already imported (app.py:14);
       # `dict[str, Any]` matches the /api/info, /api/chat convention.
       # Lazy import: the web app must stay importable without the GUI stack
       # (serve mode, CI). The desktop module pulls pywebview only when present.
       from the_one.interfaces.desktop.shell import focus_window
       return {"focused": focus_window()}
   ```
   No request body, no auth — raising one's own local window. Header-less loopback POST
   clears the Origin middleware (DD4).

3. **`run_desktop()` focus-and-exit branch** — insert **immediately after
   `sel_port, is_ours = _select_port(host, port)` (shell.py:125) and BEFORE
   `url = f"http://{host}:{sel_port}/"` (shell.py:126) and before the `try:` block.**
   Do NOT alter the existing `if not is_ours:` server-start block — the early `return`
   simply makes it unreachable for the `is_ours` case:
   ```python
   if is_ours:
       # A the-one of our version already owns this port — raise its window and exit
       # instead of opening a duplicate (DD4). Header-less loopback POST (no Origin).
       try:
           httpx.post(f"http://{host}:{sel_port}/api/window/focus", timeout=2.0)
       except httpx.HTTPError:  # intentionally broad — covers ConnectError + TimeoutException
           log.warning("focus POST to running instance failed; exiting anyway")
       return
   ```
   `httpx` is already imported (shell.py:11). For `log`, use the module logger (add
   `log = logging.getLogger(__name__)` near the top if shell.py doesn't already have
   one). Because this `return` is **before** the `try/finally`, `_graceful_shutdown`
   never runs here (no server was started — `server`/`thread` are `None`), which is
   correct.

4. **Tests** (`tests/test_window_focus.py`):
   - Endpoint: mirror `tests/test_origin_allowlist.py`'s pattern —
     `from starlette.testclient import TestClient` with `with TestClient(app) as client:`
     (simpler than the async ASGITransport pattern; the handler is sync-friendly). Patch
     `the_one.interfaces.desktop.shell.focus_window`; assert 200 + body for window-present
     and window-absent; assert a **header-less** POST (TestClient sends no `Origin` by
     default) returns 200, not 403.
   - `focus_window()`: mock window → show+restore called, returns True; no window →
     returns False.
   - Focus-and-exit branch: mock `_select_port` → `(port, True)`, mock `httpx.post`,
     assert POST URL/`headers` (no `Origin`) and that `webview.create_window` is NOT
     called and `run_desktop` returns. Then the raise-path variant.

## Edge Cases

- **Serve mode / no window:** the endpoint exists in the same FastAPI app used by
  `the-one serve`; `focus_window()` no-ops to `False` there (no window registered).
- **Web app import purity:** the desktop import MUST be inside the handler (lazy) — a
  top-level `import the_one.interfaces.desktop.shell` would pull pywebview/pystray into
  every `serve`/CI import and break headless environments.
- **Focus POST failure:** exit anyway (the running instance is up per `is_ours`); a
  failed raise is a minor UX miss, not worth a duplicate window. Logged.
- **No new persisted state / no DB / no cache** — the window ref is the Leg-2 in-memory
  global; reachability/cache audits N/A.
- **Origin variants:** if a future caller attaches an `Origin`, a loopback origin is
  already wildcard-allowed (`middleware.py:128-147`); the leg's client deliberately
  sends none.

## Files Affected

- `the_one/interfaces/web/app.py` — new `POST /api/window/focus`.
- `the_one/interfaces/desktop/shell.py` — `focus_window()` + the `is_ours` focus-and-exit branch.
- `tests/test_window_focus.py` — new.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (`test_window_focus.py` + Leg 1/2 suites, host-native)
- [ ] Update flight-log.md with the leg progress entry
- [ ] Set this leg's status to `landed` (completion/commit deferred to flight-end review)

## Citation Audit

3 citations verified at leg-design time (2026-06-15): `interfaces/web/app.py:1634`
(`@app.get("/api/info")`) — OK (from this session's grep); `interfaces/web/middleware.py`
Origin behavior (`:80-84,128-147`) — OK (per the Phase-5b Architect read); `desktop/
shell.py` window ref + `_select_port` — OK (Leg 1/2 outputs). The module window
reference is `_desktop_window` (confirmed at `shell.py:24`; `run_desktop()` declares it
`global` at `:117` and resets it at `:122`); `_select_port` is called at `shell.py:125`
and the focus-and-exit branch inserts before `:126`. `httpx` is imported at `shell.py:11`.
