# Leg: desktop-shell-scaffold

**Status**: completed
**Flight**: [Windows Native App Hardening — Desktop Presence & Lifecycle](../flight.md)

## Objective

Introduce the `the_one/interfaces/desktop/` package and migrate the F4 launcher into
it as `run_desktop()`, with `the_one.interfaces.app` left as a thin back-compat shim —
no behavior change — and add `pystray` + `Pillow` to the `[gui]` extra so later legs
have the tray dependency.

## Context

- Flight DD1: a **single composable desktop module** (not a per-OS backend split).
  This leg creates that module and relocates the F4 window/lifecycle composition into
  it, so subsequent legs (tray, focus, window-state) build there. Scaffold-first
  **de-risks the refactor before features pile on**.
- F4 (completed) put the launcher in `the_one/interfaces/app.py`: `run()` plus helpers
  `_select_port`, `_webview_available`, `_wait_until_serving`, `_graceful_shutdown`. It
  runs uvicorn in a daemon thread **in-process** and calls `webview.start()` on the
  main thread.
- **No behavior change** this leg. The window must still open exactly as in F4;
  `serve`/`chat`/`version` paths are untouched.

## Inputs

- `the_one/interfaces/app.py` — the F4 launcher (`run` at `app.py:run`, helpers at
  `_select_port` / `_webview_available` / `_wait_until_serving` / `_graceful_shutdown`).
- `the_one/main.py:23 — "from the_one.interfaces.app import run as run_app"` — the
  `app` subcommand dispatch.
- `.github/workflows/windows-installer.yml:92 — "from the_one.interfaces.app import _select_port"`
  — the packaged-smoke single-instance probe (an **external consumer** of the symbol).
- `tests/test_app_launcher.py` — F4's launcher tests; several **patch attributes on
  the `the_one.interfaces.app` module object** (`launcher_module = the_one.interfaces.app`,
  then `patch.object(launcher_module, …)`) and then call `run()`.
- `pyproject.toml:53-56` — the `[gui]` optional-dependency group (today: pywebview
  only; `Pillow` lives in the `dev` extra at `pyproject.toml:60`).

## Outputs

- `the_one/interfaces/desktop/__init__.py` — new; exports `run_desktop`.
- `the_one/interfaces/desktop/shell.py` — new; the migrated launcher
  (`run_desktop()` + the four helpers), behavior identical to F4's `app.run()`.
- `the_one/interfaces/app.py` — reduced to a **back-compat shim** that re-exports
  `run` (→ `run_desktop`), `_select_port`, `_webview_available`, `_wait_until_serving`,
  `_graceful_shutdown` from `desktop.shell`.
- `tests/test_desktop_shell.py` — `tests/test_app_launcher.py` renamed + repointed to
  patch `the_one.interfaces.desktop.shell` (all assertions intact).
- `pyproject.toml` — `[gui]` extra gains `pystray>=0.19` and `pillow>=10.0`.

## Acceptance Criteria

- [ ] `the_one/interfaces/desktop/__init__.py` exists and exposes `run_desktop`
      (`from the_one.interfaces.desktop import run_desktop` succeeds).
- [ ] `the_one/interfaces/desktop/shell.py` contains `run_desktop()` plus
      `_select_port`, `_webview_available`, `_wait_until_serving`, `_graceful_shutdown`
      — the bodies moved **verbatim** from `app.py` (no logic change; the
      `finally: _graceful_shutdown(...)` block still wraps `webview.start()` — its
      re-homing is Leg 2's job, explicitly NOT this leg's).
- [ ] `the_one/interfaces/app.py` is a thin shim: `the_one.interfaces.app import run`,
      `_select_port`, `_webview_available`, `_wait_until_serving`, `_graceful_shutdown`
      all still succeed and resolve to the `desktop.shell` implementations.
- [ ] `the_one/main.py`'s `app` dispatch still launches the window unchanged
      (`from the_one.interfaces.app import run as run_app` resolves via the shim).
- [ ] `.github/workflows/windows-installer.yml:92`'s
      `from the_one.interfaces.app import _select_port` still resolves (back-compat
      verified by import, not a CI run) — **left unchanged**.
- [ ] `pyproject.toml` `[gui]` includes `pystray>=0.19` and `pillow>=10.0`; after
      `pip install -e ".[gui]"`, `python -c "import pystray, PIL"` succeeds.
- [ ] `tests/test_desktop_shell.py` (renamed from `test_app_launcher.py`) patches
      `the_one.interfaces.desktop.shell` where it previously patched
      `the_one.interfaces.app`; every prior assertion is preserved (nothing inverted —
      behavior is unchanged); the file passes host-native.
- [ ] `serve` / `chat` / `version` code paths are byte-identical to pre-leg.

## Verification Steps

- Import surface (new + back-compat):
  `python -c "from the_one.interfaces.desktop import run_desktop; from the_one.interfaces.app import run, _select_port, _webview_available, _wait_until_serving, _graceful_shutdown; print('ok')"`
- Deps present + importable:
  `grep -nE 'pystray|Pillow' pyproject.toml` then `pip install -e ".[gui]" && python -c "import pystray, PIL; print('deps ok')"`
- Tests (host-native — NOT docker):
  `python -m pytest tests/test_desktop_shell.py -x --timeout=30 -q`
- CI back-compat symbol resolves:
  `python -c "from the_one.interfaces.app import _select_port; print('ci-shim ok')"`
- Reload target intact (the renamed test's `importlib.reload` home):
  `python -c "import importlib, the_one.interfaces.desktop.shell as s; importlib.reload(s); print('reload ok')"`
- No stray references to the old test module:
  `grep -rn "test_app_launcher" . --include=*.py --include=*.yml | grep -v .venv` returns nothing.
- `serve`/`chat`/`version` untouched: `git diff --stat` shows changes only in
  `the_one/interfaces/{app.py,desktop/}`, `tests/`, and `pyproject.toml`.

## Implementation Guidance

1. **Create the package.**
   - `the_one/interfaces/desktop/__init__.py`: `from the_one.interfaces.desktop.shell import run_desktop` and `__all__ = ["run_desktop"]`.
   - `the_one/interfaces/desktop/shell.py`: move the **entire** body of `app.py`
     (module docstring, imports, the four helpers, and `run`) into it. Rename `run` →
     `run_desktop`. Do not change any logic — this is a relocation, not a rewrite.

2. **Reduce `app.py` to a shim.**
   ```python
   from __future__ import annotations

   # Back-compat shim. The desktop launcher moved to the_one.interfaces.desktop.shell
   # (M15 F6 DD1 — single composable desktop module). These re-exports keep existing
   # imports working: main.py's `app` dispatch and the CI packaged-smoke's
   # `from the_one.interfaces.app import _select_port`.
   from the_one.interfaces.desktop.shell import (  # noqa: F401
       _graceful_shutdown,
       _select_port,
       _wait_until_serving,
       _webview_available,
       run_desktop as run,
   )

   __all__ = [
       "run",
       "_select_port",
       "_webview_available",
       "_wait_until_serving",
       "_graceful_shutdown",
   ]
   ```

3. **Add the deps.** In `pyproject.toml` `[gui]`, add `pystray>=0.19` and
   `pillow>=10.0` to **both** the linux and non-linux entries (alongside `pywebview`) —
   pystray and Pillow are cross-platform pure-/native-Python wheels, no platform
   marker needed:
   ```toml
   gui = [
       "pywebview[gtk]>=5,<6; sys_platform == 'linux'",
       "pywebview>=5,<6; sys_platform != 'linux'",
       "pystray>=0.19",
       "pillow>=10.0",
   ]
   ```

4. **Repoint the tests.** `git mv tests/test_app_launcher.py tests/test_desktop_shell.py`.
   In the renamed file, replace every `the_one.interfaces.app` with
   `the_one.interfaces.desktop.shell` (the function-local imports at lines ~77/94/106/
   119/136/153/172 and the `launcher_module = the_one.interfaces.app` / `from
   the_one.interfaces import app as launcher_module` bindings at ~202/213/225/238/253/
   273/319/351/389/431). The `import webview` mock fixture installs into `sys.modules`
   and is **home-agnostic** — leave it. Do not change any assertion; behavior is
   identical, so nothing is inverted.

5. **Run the deps install + tests host-native** and confirm green.

## Edge Cases

- **Patch-home (the load-bearing subtlety):** `run_desktop` looks up `_webview_available`
  etc. in **`desktop.shell`'s** namespace. Tests that `patch.object(launcher_module, …)`
  MUST bind `launcher_module = the_one.interfaces.desktop.shell`, or the patch won't be
  seen by `run_desktop`. This is the whole reason the test file is repointed, not just
  the import lines.
- **No circular import:** `app.py` imports from `desktop.shell`; `desktop.shell` imports
  only `the_one.config` / `the_one` (as `app.py` did) — never `interfaces.app`.
- **`finally: _graceful_shutdown` stays put** this leg. Re-homing the teardown out of
  the `webview.start()` `finally` (needed once Quit becomes a tray callback) is Leg 2
  — Leg 2's spec covers it (its "Quit teardown ordering" test), so the deferral is
  tracked (design-review Q1).
- **`importlib.reload` test (line ~431-445, `test_run_raises_system_exit_when_webview_missing`):**
  after the `the_one.interfaces.app` → `the_one.interfaces.desktop.shell` substitution,
  `launcher_mod` references `shell` directly, so `importlib.reload(launcher_mod)` and
  the subsequent `patch.object(launcher_mod, …)` + `launcher_mod.run()` (now
  `run_desktop`) all land in `shell`'s namespace — **correct after the mechanical
  replacement, no extra change needed**. Just don't leave the reload pointed at the
  shim (design-review medium note).
- **Pillow moves from a dev-only to a `[gui]` runtime dep — intentional** (the tray
  icon in later legs needs Pillow at runtime; `[gui]`-only installers must get it).
  This is a deliberate runtime-surface addition, not an accident (design-review Q2).
- **Don't touch `serve`/`chat`/`version`** — they're dispatched independently in
  `main.py` and are out of scope.
- No DB/schema, no cache, no new lifecycle state — the state-machine-reachability and
  cache-freshness audits are N/A (pure relocation + dependency add).

## Files Affected

- `the_one/interfaces/desktop/__init__.py` — new (package export).
- `the_one/interfaces/desktop/shell.py` — new (migrated launcher).
- `the_one/interfaces/app.py` — reduced to a back-compat shim.
- `tests/test_app_launcher.py` → `tests/test_desktop_shell.py` — renamed + repointed.
- `pyproject.toml` — `[gui]` gains `pystray` + `Pillow`.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (`tests/test_desktop_shell.py`, host-native)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header) — *(deferred to the
      flight's end-of-flight review/commit per the batch model; the implementing
      Developer sets `landed`, not `completed`/committed)*
- [ ] Check off this leg in flight.md

## Citation Audit

5 code-location citations, all verified against current code at leg-design time
(2026-06-15): `the_one/main.py:23` ("from the_one.interfaces.app import run as
run_app") — OK; `.github/workflows/windows-installer.yml:92` ("from
the_one.interfaces.app import _select_port") — OK; `pyproject.toml:53-56` (`[gui]`
group) + `:60` (`dev` has `Pillow`) — OK; `tests/test_app_launcher.py` patch-target
lines (~77–431) — OK (enumerated from a live grep this session). Symbol-form citations
(`app.py:run`/`_select_port`/`_webview_available`/`_wait_until_serving`/
`_graceful_shutdown`) verified present in `the_one/interfaces/app.py`.
