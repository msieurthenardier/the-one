# Leg: shell-split

**Status**: in-flight
**Flight**: [macOS app](../flight.md)

## Objective
Split `the_one/interfaces/desktop/shell.py` into a takeover module, a window-control module and one session-state object, with no behaviour change on any platform, and re-point every test and caller so a patch of a moved name cannot silently miss.

## Context
- **Flight DD1** (read it in full). The Flight 2 debrief's top recommendation: both reviewers ranked this split first, before macOS adds Dock, reopen and terminate states (legs 4-5 build on these modules).
- **Today:**
  - `shell.py` is 1478 lines.
  - `DesktopSession.run()` (line 1020 to about 1468) is about 450 lines.
  - Nine module-level mutable names coordinate it: `_really_quit`, `_desktop_window`, `_tray_mode`, `_session`, `_tracked_visible`, `_booting`, `_quit_requested`, `_browser_server`, and the lock `_window_lock`. `global` statements touch them at 9 sites.
  - `with _window_lock` appears 7 times.
- **DD3 (leg 4) will need** the session's `server` and `thread` on the state object. Today they are locals of `run()`. This leg adds the two slots and sets them, with no other use yet.
- **No behaviour change.** Same logs, same route answers, same close/quit/show sequences, the same Windows/Linux/darwin branches. Leg 4 is where darwin behaviour changes.
- **Build discipline:** the frozen bundles collect every desktop submodule (`collect_submodules("the_one.interfaces.desktop")` in all three `the-one.spec` files), so new modules ship with no spec change.

## Inputs
- Branch `flight/03-macos-app` at `09bdda5` or later. The working tree may also hold leg 2's uncommitted files under `packaging/macos/` and `.github/`, which are disjoint; leave them alone.
- `the_one/interfaces/desktop/shell.py` as on `main` `e21d219`.
- Consumers:
  - `the_one/interfaces/app.py`, a back-compat shim that re-exports `_select_port`, `_webview_available`, `_wait_until_serving`, `_graceful_shutdown`, and `run_desktop as run`;
  - `the_one/interfaces/desktop/__init__.py` (`run_desktop`);
  - `the_one/interfaces/web/app.py`, whose routes lazily import `focus_window`, `window_state`, `quit_desktop` and `set_window_theme` from `shell`;
  - `the_one/main.py::_quit_command` (`_wait_for_exit`);
  - `the_one/diagnostics.py`, if it references shell names (grep).
- Test consumers: `tests/conftest.py` (the `stub_desktop_host` fixture, the 8484/8485 port guard), `test_desktop_shell.py`, `test_desktop_tray.py`, `test_desktop_takeover.py`, `test_window_focus.py`, `test_window_routes.py`, `test_window_state.py`, `test_api_window_chrome.py`, `test_cli_quit.py`, `test_doctor.py`, `test_packaging_score.py`.

## Outputs
- **`the_one/interfaces/desktop/takeover.py`** (new). Moved verbatim apart from imports:
  - `_now`, `_sleep`, `_parse_version`, `_is_older`, `_auth_headers`, `_running_version`, `_request_quit`, `_pid_alive`, `_wait_for_exit`, `_activation_token`, `_post_focus`, `_takeover`, `_select_port`;
  - `_TAKEOVER_WAIT_BOUND`, `_TAKEOVER_POLL`, `_TAKEOVER_NOTICE_AFTER`.
- **`the_one/interfaces/desktop/window_control.py`** (new):
  - `_is_gtk_backend`, `_on_wayland`, `_mark_visible`, `_show_window`, `_gtk_read`, `window_visible`, `_window_mapped`, `_mode`, `window_state`, `quit_desktop`, `_gtk_activate`, `focus_window`, `set_window_theme`, `_no_tray_hide`;
  - the no-tray notice constants `_NO_TRAY_NOTICE_SUMMARY`/`_NO_TRAY_NOTICE_BODY`, whose only user is `_no_tray_hide` (verified by the design review).
  - The tray notice constants `_TRAY_NOTICE_TITLE`/`_BODY` stay in `shell.py`: `test_desktop_tray.py` reads them from the shell module.
- **Loggers:** `takeover.py` and `window_control.py` use `logging.getLogger("the_one.interfaces.desktop.shell")`, so the logger name and every log line stay the same (AC1's "same logs" holds literally).
- **`the_one/interfaces/desktop/session_state.py`** (new): a `SessionState` class and one module-level instance, `state`. It holds:
  - the flags `really_quit`, `desktop_window`, `tray_mode`, `session`, `tracked_visible`, `booting`, `quit_requested`, `browser_server`;
  - `lock` (a `threading.Lock`);
  - two new slots `server` and `thread` (set by `run()` when it starts a server; `None` otherwise).

  It has small methods for each locked critical section that exists today, with names that describe them:
  - `publish_window(window)` (step 6, returns whether a quit was requested);
  - `request_quit()` (`quit_desktop`'s locked section). It returns a tagged result:
    - `("already", None)` when `really_quit` is set;
    - `("booting", None)` after setting `quit_requested`;
    - `("browser", None)` after setting `browser_server.should_exit = True` under the lock, as today;
    - `("window", session)` for the published window;
    - `(None, None)` when there is nothing to quit.

    The caller then calls `session._on_quit(session._icon)` outside the lock;
  - `clear_booting()` (today's `_clear_booting`, `shell.py:818`, used by `run()` at three sites);
  - `claim_browser_server(server)`.

  Each returns what the caller must do *after* the lock is released, so no method calls `_on_quit` or any pywebview method under the lock. Writes that are lock-free today stay lock-free (e.g. `_no_tray_hide`'s and `_mark_visible`'s `tracked_visible`).

  It also carries leg 4's (DD3) stated needs as inert slots now, so leg 4 does not reopen the class: `server`, `thread`, and `boot_stopped` (a `threading.Event`, cleared by `reset()`). It has no `begin_quit()` yet; leg 4 adds it. `run()` keeps `server`/`thread` as locals for its `finally` and also stores them on `state`.

  `reset()` restores every field to its default **in place**; the instance is never rebound.
- **`shell.py`** keeps:
  - `DesktopSession`, the splash (`_SPLASH_*`, `_splash_html`, `_splash_text_only`);
  - `_wait_until_serving`, `_graceful_shutdown`, `_webview_available`;
  - `_NoTrayError`, `_NO_WEBVIEW_BODIES`, `_no_webview_body`;
  - the tray notice constants;
  - `run_desktop`.

  It reaches the moved code **through the module**: `takeover._select_port(...)`, `window_control.focus_window(...)`, `session_state.state.desktop_window`. It does not `from … import` a moved function or flag.
- **Callers updated:**
  - `the_one/interfaces/app.py` re-exports from the new homes, with the same names and the same `__all__`;
  - `web/app.py`'s routes import from `window_control`;
  - `main._quit_command` imports from `takeover`.
- **Tests re-pointed:** each test patches or assigns the name **in the module that defines or uses it**. A module-level import is patched in the module whose code calls it: `__version__`, `desktop_host`, `httpx` and `get_credential` for the takeover go to `takeover`, not `shell`. The known sites, from the design review:
  - `test_desktop_takeover.py:52,65,183-184` (`__version__`, `desktop_host.send_notification`; `uvicorn`/`threading.Thread` stay on `shell` only if `shell.py` still uses them);
  - `test_cli_quit.py:153,164,175,211` and `main.py:68` (`_wait_for_exit` → `takeover`);
  - `test_window_routes.py:26-90` (`_desktop_window`/`_session` → `state`; the functions → `window_control`);
  - `test_api_window_chrome.py:46` (`"…shell.set_window_theme"` → `window_control`);
  - `test_window_focus.py:126,138,152` (`"…shell.focus_window"` → `window_control`);
  - `test_desktop_shell.py:1754` (`_window_lock.locked()` → `state.lock`), its about 25 `launcher_module` patches of `_select_port`/`_running_version`/… (→ `takeover`), and `_boot_harness`'s `ns.launcher` (lines 1060, 1761, 1813): the harness now exposes `ns.state` and the modules explicitly, so no `ns.launcher.<flag>` form remains;
  - `test_window_state.py:315,354`;
  - `tests/conftest.py:535` (`monkeypatch.setattr(shell, "_tray_mode", None, raising=False)`: with `raising=False` a miss is silent, so this becomes `state.tray_mode`).

  `tests/test_platform_shell.py` uses an unrelated `shell_mod` (the platform shell); leave it alone.
- **State reset:** one **autouse** fixture in `tests/conftest.py` calls `session_state.state.reset()` before and after every test. `importlib.reload(shell…)` resets (`test_window_focus.py:45,59,76,142,183`, `test_desktop_tray.py:117`'s `shell_module` fixture) no longer reset lifecycle state, which now lives in `session_state`. Keep a reload only where a test needs `shell`'s own module globals, and fix the `shell_module` fixture's docstring.
- **`tests/test_desktop_split_guard.py`** (new): the guard (see AC3).
- **Docs:** `the_one/agents.md`'s "Desktop launcher" section (and the Linux packaging section's mentions of `shell.py` names) say where each piece now lives, in one short additive paragraph; `CLAUDE.md` needs no change unless it names a moved symbol (grep).

## Acceptance Criteria
- [ ] **AC1 — Moved, not changed.** Every function listed under Outputs exists in its new module with a body identical to `main`'s apart from:
  - the module-qualified references (`state.X` for a flag, `takeover.X`/`window_control.X` for a cross-module call);
  - the lock sections replaced by `SessionState` methods.

  No log message, return value, route answer or branch changes. `shell.py` no longer defines any moved name.
- [ ] **AC2 — Consumers.**
  - `from the_one.interfaces.app import _select_port, _webview_available, _wait_until_serving, _graceful_shutdown, run` still works (the CI packaged smoke depends on `_select_port`).
  - The window routes, `the-one quit` and `run_desktop` work through their new imports.
  - `grep -rn "from the_one.interfaces.desktop.shell import" the_one/` lists only names `shell.py` still defines.
- [ ] **AC3 — The guard.** `tests/test_desktop_split_guard.py` parses every `tests/**/*.py` with `ast` and fails, naming file and line, when a test patches or assigns through `shell` a name that is **not a `def`, `class` or assignment target at the top level of `shell.py`** (read from `shell.py`'s own AST; names `shell.py` merely imports are not allowed, so a patch of `shell.__version__` or `shell.desktop_host` fails).

  The patch and assignment forms:
  - `monkeypatch.setattr("the_one.interfaces.desktop.shell.<name>", …)`;
  - `monkeypatch.setattr(<alias>, "<name>", …)`, including `raising=False`;
  - `unittest.mock.patch("…shell.<name>")`;
  - `patch.object(<alias>, "<name>")`;
  - an assignment `<alias>.<name> = …`.

  `<alias>` is any name bound to the `shell` module, **at any scope** (module or inside a function body), by:
  - `import the_one.interfaces.desktop.shell as A`;
  - `from the_one.interfaces.desktop import shell [as A]`, including a multi-name `from … import host, shell`;
  - `A = sys.modules["the_one.interfaces.desktop.shell"]`;
  - `A = importlib.import_module("the_one.interfaces.desktop.shell")`;
  - `A = B`, where `B` is already an alias;
  - a fixture that returns such an alias. Fixtures are resolved by following `def <fixture>` bodies in the same file and in `tests/conftest.py`.

  Detection is by module binding, never by a variable's name, so files where `shell` is a tool or a fixture value (`test_agent_redundant_backstop.py`, `test_agent_degraded_injection.py`, `test_platform_shell.py`) are not flagged.

  The guard has its own small unit tests on synthetic sources: each patch form and each alias form is caught, an imported (not defined) name is caught, and an allowed name passes. It passes on the final tree.
- [ ] **AC4 — Unit tier.** *(Phase A ends here.)*
  - `make test-unit`: every test that existed on `e21d219` still exists (moved or re-pointed, none deleted or skipped) and passes.
  - New tests: `SessionState` (each method's return-after-unlock contract, `reset()` in place) and the guard.
  - The skip count is the expected 12 (no netns) or 14 (netns).
  - `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/ evals/` are clean.
- [ ] **AC5 — Browser lanes.** `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane settings -x` passes (the window-chrome route and its mock). Run the full `--parallel 3` gate only if no other browser run is active on the host (check first, as the debrief Developer did), else record that only `settings` ran.
- [ ] **AC6 — Real GTK, both baselines.**
  - Build a `.deb` from the working tree with Flight 2's recipe: `M32_BUILD=$HOME/the-one-m32-build/f3 packaging/linux/build.sh --version 0.11.9.dev30` (the default `M32_BUILD` is Flight 2's `…/f2`, so the override is required). Evidence goes under `$HOME/the-one-m32-evidence/f3/leg1/`. `dev30` is newer than Flight 2's `dev20`/`dev21`, as the takeover run needs.
  - Run `packaging/linux/checks/gtk-smoke.sh <distro> --deb FILE --evidence DIR` on the `ubuntu-26.04` and `debian-13` baselines. OVERALL PASS on both, with the same rows as Flight 2 leg 3:
    - the window maps;
    - a real `WM_DELETE_WINDOW` close behaves per tray mode;
    - size is stable across relaunches;
    - the quit route exits within 15 s;
    - the tray decision is `none`.
  - Run it again with `--takeover-from OLD.deb` on one baseline, where OLD is Flight 2's `gleepglorp-ai_0.11.9~dev20_amd64.deb` from `$HOME/the-one-m32-build/f2/packages/` (present; built from `main`'s shell). The new build replaces the old running instance, as in Flight 2 (the takeover code moved).
  - The package's gates pass in the container: `packaging/linux/checks/gates.sh <label> deb <distro> baseline --pkgdir DIR --n VER --display xvfb` on both distros. The score line matches Flight 2's `.deb` rows (`G1p G1u G2 G3 G4 single` PASS; `upgrade=N/A` in single-version mode).
- [ ] **AC7 — Hygiene.**
  - No port 8484/8485 used, and the operator's data dir is unchanged (record its newest mtime before and after).
  - Only `m32-*` containers were created, and none are left.
  - Only PIDs you recorded were killed.
  - No root-owned files left in `$HOME`.
  - `git status` shows only this leg's files plus any concurrent leg-2 files under `packaging/macos/` and `.github/`.

## Phases
The leg runs as two Developer spawns (as Flight 2 legs 4 and 5 did):
- **Phase A:** the three modules, the `shell.py` rewrite, the caller re-imports, test re-pointing, the guard and its tests, the docs, lint, and `make test-unit` (AC1-AC4). It ends with a checkpoint in the flight log.
- **Phase B:** the `settings` lane, the `.deb` build, the GTK smoke test on both distros plus the takeover run, the container gates, and hygiene (AC5-AC7).

## Verification Steps
- AC1: `git diff e21d219 -- the_one/interfaces/desktop/` reviewed function by function. Report any non-mechanical edit with its reason in the flight log.
- AC2: `python -c "from the_one.interfaces.app import _select_port, _webview_available, _wait_until_serving, _graceful_shutdown, run"`; the grep.
- AC3: run the guard; also show it failing on a deliberately wrong patch in a scratch copy (not committed).
- AC4-AC5: the commands above; quote the summary lines.
- AC6: `score`/`OVERALL` lines in the flight log; evidence paths.
- AC7: the recorded checks.

## Implementation Guidance
1. **Map the globals first.** For every read and write of the nine names (including the `global` statements at lines 613, 729, 819, 832, 998, 1032-1033, 1237, 1248), note which function does it and whether it holds the lock. Write the `SessionState` methods from that map, one per existing locked section, not a new protocol.
2. **Move the takeover cluster** (lines 292-547), then the window-control cluster (595-850, minus what stays). Keep definition order and comments. Module docstrings name the mission, flight and DD1.
3. **Rewrite `DesktopSession`** to use `state` and the module-qualified calls. Keep `run()`'s structure and step comments as they are. The method split of `run()` itself is not this leg.
4. **Avoid import cycles.** `window_control` needs `chrome`, `notice`, `desktop_host`, `window_state_store` and `session_state`, never `shell`. `takeover` needs no desktop module beyond `session_state` (if any). `shell` imports all three. If `quit_desktop` needs `DesktopSession._on_quit`, reach it through `state.session` as today.
5. **Re-point the tests** file by file. Where a test sets a flag (`shell._desktop_window = …`, `monkeypatch.setattr(shell_state, "_tray_mode", …)`), set it on `session_state.state` instead. Make the autouse reset fixture call `state.reset()`. Keep test names; rename only when a name states a module that changed (rename, never delete and re-add).
6. **Write the guard last** and make it pass.
7. **Docs:** one additive paragraph in `the_one/agents.md` (the module map); check `CLAUDE.md`'s Desktop launcher paragraph for moved names.

## Edge Cases
- **`DesktopSession.__init__`'s comment** says the F6 test suite "writes the module global directly". It becomes "sets `session_state.state` directly"; update the comment.
- **`_tracked_visible` is written by `_mark_visible` and by `_no_tray_hide`.** Both move to `window_control` and write `state.tracked_visible`.
- **`_is_gtk_backend` reads `sys.modules["webview"].renderer` at call time.** Keep that: never import `renderer`.
- **`the_one/interfaces/app.py`'s shim** must not import `window_control` at module top-level if that would import pywebview. It doesn't today; keep the import graph GTK-free (the base install has no `[gui]`).
- **Tests that patch `shell.os` or `shell.uvicorn`** keep working if those names stay used in `shell.py`. Otherwise re-point them to the module that now uses them.
- **The conftest port guard** (8484/8485) and `stub_desktop_host` stay effective: check what they patch.

## Files Affected
- `the_one/interfaces/desktop/{shell.py,takeover.py,window_control.py,session_state.py}`
- `the_one/interfaces/app.py`, `the_one/interfaces/web/app.py` (the four route imports only), `the_one/main.py` (one import)
- the test files listed under Inputs, plus `tests/test_desktop_split_guard.py`
- `the_one/agents.md` (additive)

### Citation Audit
Checked at `09bdda5`:
- the line ranges (292-547 takeover, 595-850 window control, 1020 `run`);
- the 9 `global` sites and the 7 `with _window_lock` sites;
- the `interfaces/app.py` shim's names;
- the route imports at `web/app.py` (`focus_window`, `window_state`, `quit_desktop`, `set_window_theme`);
- `main.py`'s `_wait_for_exit` import;
- `collect_submodules("the_one.interfaces.desktop")` in all three specs.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
