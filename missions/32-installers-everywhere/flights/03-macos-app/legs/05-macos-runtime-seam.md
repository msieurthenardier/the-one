# Leg: macos-runtime-seam

**Status**: completed
**Flight**: [macOS app](../flight.md)

## Objective
Make the frozen runtime safe and complete on a stock Mac:
- the interpreter resolver never runs the Command Line Tools stub and walks every `PATH` entry;
- a Finder-launched app gets the user's login-shell `PATH`, primed once at command start;
- `doctor` reports all of this, plus DD2's `tray: dock` line and a darwin `desktop shell` gate that never imports the Cocoa backend.

## Context
- **Flight DDs:** DD6 (the stub, the `PATH` walk, the runtime list), DD7 (the login-shell `PATH`: placement, isolation, order, fallback, the static additions, `doctor`'s source line), DD2 (`tray: dock`; the darwin `desktop shell` gate via `find_spec`). Per the flight's Technical Approach, **this leg owns every `the_one/diagnostics.py` and `tests/test_doctor.py` change** in the flight.
- **The seam stays one implementation** (mission constraint): everything lives in `the_one/platform/env.py` and `the_one/platform/interpreter.py`, behind `is_frozen()` plus `sys.platform == "darwin"`. Linux and Windows output is unchanged, except DD6's `PATH` walk and the two additive static `PATH` entries (harmless when the directories don't exist), which applies everywhere (strictly better on Windows: a Store alias earlier on `PATH` no longer hides a real Python later on it).
- **Leg 4 runs beside this leg.** It owns `the_one/interfaces/desktop/` (including `shell.py`). DD7's priming for the `app` command belongs in `DesktopSession.run` just after the `is_ours` return, so **leg 4 adds that one call**, to the function this leg provides (`env.prime_login_shell_path()`). This leg adds the calls for `serve` and `doctor` in `the_one/main.py::cli_entry`. The interface is fixed here:
  - `prime_login_shell_path(timeout: float = 5.0) -> str`: idempotent, thread-safe (guarded by a `threading.Lock`), never raises, returns `"login shell"`, `"static fallback"` or `"not applicable"`;
  - `path_source() -> tuple[str, str]`: `(source, reason)`, where the source is `"unprimed"`, `"login shell"`, `"static fallback"` or `"not applicable"`, and `reason` is empty except on fallback.
- **Probe evidence (leg 3, run `40203877635`)** may refine P7 (`xcode-select` on the runner) and P8 (the inherited `PATH`/`SHELL`). If leg 3 lands first, read its section. Nothing in this leg's design depends on it, because the runner has Xcode and a stock Mac is the target.
- **`tests/conftest.py`'s port guard and the leg-1 `state.reset()` autouse fixture** stay as they are.

## Inputs
- `the_one/platform/env.py`: `is_frozen`, `_bundle_dir`, `_common_runtime_dirs` (the POSIX list at `env.py::_common_runtime_dirs`), `strip_bundle_dir_from_path`, `clean_subprocess_env` (the order is existing `PATH`, then the static list, then `THE_ONE_EXTRA_PATH`), `_build_subprocess_env`.
- `the_one/platform/interpreter.py`: `_resolve_frozen_python` (the first `shutil.which` hit per name), `_is_store_alias`.
- `the_one/diagnostics.py`: `detect_runtimes` (`shutil.which` per name), `_probe_desktop_shell` (non-frozen-Linux falls back to `_probe_desktop_shell_generic`, which imports pystray), `_advisory_lines`, `_tray_line` (darwin → `"tray: not probed (macOS)"`), `run_doctor`.
- `the_one/main.py::cli_entry` (the `serve` and `doctor` branches).
- Tests: `tests/test_doctor.py` and the existing env/interpreter test files (grep for `_resolve_frozen_python`, `clean_subprocess_env`, `_common_runtime_dirs`).

## Outputs
- **`the_one/platform/interpreter.py`:**
  - A per-entry `PATH` walk: for each candidate name, for each `PATH` entry in order, `shutil.which(cand, path=entry)`. The first hit that is not a stub or alias wins.
  - **Empty `PATH` entries are skipped.** Relative entries resolve against the cwd as before, and the result still goes through `.resolve()`. The order stays candidate-outer, entry-inner: `python3` across the whole `PATH` first, then `python`.
  - `_is_clt_stub(path)` on darwin: true for `/usr/bin/python3` and `/usr/bin/python`, compared after `os.path.normpath` (never by resolving symlinks, which would wrongly flag the real CLT Python under `/Library/Developer/...`), unless `xcode-select -p` exits 0 **and** prints a directory that exists. The check runs with a 5 s bound, is cached per process, never runs the stub itself, and is never called off darwin.
  - The error text for "only a stub was found" on darwin: "only the macOS Command Line Tools stub `/usr/bin/python3` was found, which is not an installed Python; install Python 3 (python.org or Homebrew), or set THE_ONE_PYTHON". The Windows alias text stays.
  - An explicit `THE_ONE_PYTHON` override is never filtered (as today).
- **`the_one/platform/env.py`:**
  - `prime_login_shell_path(timeout=5.0) -> str` per DD7:
    - **The shell:** `$SHELL`, else `pwd.getpwuid(os.getuid()).pw_shell`, else `/bin/zsh`.
    - **The command:** `[shell, "-l", "-i", "-c", "printf '%s\\n' __M32_PATH_BEGIN__; /usr/bin/printenv PATH; printf '%s\\n' __M32_PATH_END__"]` (the marker names are the leg's choice).
    - **Isolation:** stdin `/dev/null`, stderr `/dev/null`, stdout to a `tempfile` (not a pipe), `start_new_session=True`. On timeout, `os.killpg(proc.pid, SIGKILL)` then reap. Any `Exception` (a missing or relative `$SHELL` raises `OSError` in `Popen`) is a fallback, not a raise.
    - **Parsing:** the lines between the markers, the last block if several. An empty or missing block is a fallback with a reason.
    - **Result:** cached in module globals under the lock: the entries, the source and the reason. **A fallback is cached too**, so a failed probe never re-runs the shell. The state goes unprimed → `"login shell"` or `"static fallback"` once, and stays. Off frozen darwin the call returns `"not applicable"` with no state change. One log line on fallback, with its reason.
    - **Scope:** only when `is_frozen()` and `sys.platform == "darwin"`, else it returns `"not applicable"` and does nothing.
  - `clean_subprocess_env` on darwin, when primed: login-shell entries, then the existing `PATH`, then the static list, then `THE_ONE_EXTRA_PATH`, de-duplicated. **`strip_bundle_dir_from_path` runs over the combined `PATH`**, so a login `PATH` that names the bundle dir cannot leak it into a child. The shell, python-exec and PTY paths have no re-strip of their own; only MCP stdio does (`stdio.py`). An operator-supplied MCP `PATH` still replaces `PATH` wholesale (`build_stdio_environ`), as today. An unprimed process uses today's order and **never** primes lazily.
  - `_common_runtime_dirs` (POSIX) gains `~/.volta/bin` and `~/.local/share/fnm/aliases/default/bin`.
  - `path_source() -> str` for `doctor`.
- **`the_one/main.py`:** the `serve` and `doctor` branches call `prime_login_shell_path()` first. It is a no-op off frozen darwin.
- **`the_one/diagnostics.py`:**
  - `detect_runtimes` uses the same per-entry walk and stub filter for `python`/`python3`. A stub alone is reported as `"not found — only the macOS Command Line Tools stub is on PATH; install Python 3 (python.org or Homebrew)"`. The other hints stay `stdio.py::_RUNTIME_INSTALL_HINTS`, unchanged.
  - `_tray_line` on darwin: `"tray: dock — macOS keeps the app in the Dock"`.
  - An advisory `path:` line on frozen darwin, from `path_source()`, through `_advisory_lines`: `"path: login shell"` or `"path: static fallback — <reason>"`. It's absent elsewhere (tested). Like `sandbox:`/`tray:`, it has no OK/FAIL, so `score.py`'s `GATE_RE` never matches it.
  - `_probe_desktop_shell` on darwin (frozen or not) uses the existing `bundle_has_modules(("webview.platforms.cocoa", "objc", "AppKit", "WebKit"))`, which checks dotted names without running a package `__init__`:
    - OK: `"Cocoa backend present"`. The frozen OK detail must never contain the word "skipped": `score.py::score_doctor` treats any "skipped" detail as bad, except window chrome's.
    - Frozen and missing: FAIL, `"missing from the bundle: <names>"`.
    - Not frozen and missing: `ok=True`, with a detail containing "skipped".
    - It never imports `webview.platforms.cocoa`, `AppKit` or `pystray`.
  - The Windows and Linux branches are unchanged.
- **Tests (unit, Linux host, `sys.platform` monkeypatched to `darwin` where needed):**
  - the interpreter walk: a stub first with no Command Line Tools → the later real Python; the stub with the CLT installed → `/usr/bin/python3`; only the stub → the DD6 error; the Windows alias shadowing case; the override is never filtered;
  - `xcode-select` is cached and bounded (a fake binary that sleeps);
  - `prime_login_shell_path`:
    - with a fake shell script: the markers are parsed;
    - a fish-style `PATH` works, through `printenv`;
    - noise on stdout from an rc file outside the markers is ignored;
    - a timeout kills the process group. A `#!/bin/sh` fake shell forks a sleeping child holding stdout and writes the child's pid to a file. With `timeout=0.5` the call returns within about 1.5 s, and the child is gone: poll `/proc/<pid>/stat` with a bound, treating state `Z` or a missing entry as gone. An orphan re-parented to a non-reaping PID 1 in a container stays a zombie, so `os.kill(pid, 0)` is not the test;
    - a fake shell that never exits (an rc file doing `exec tmux`) is bounded the same way;
    - a missing or relative `$SHELL` (an `OSError`), a non-zero exit, an empty marker block, `$SHELL` unset (the `pwd` fallback), idempotence, a cached fallback, and two concurrent first calls (one probe run);
    - a login `PATH` containing the bundle dir: it is stripped;
    - "not applicable" off frozen darwin;
  - the `clean_subprocess_env` order when primed or unprimed, and that the bundle strip wins;
  - the static additions;
  - `doctor`: `tray: dock`, the `path:` line, the darwin `desktop shell` gate (specs present, missing frozen, missing non-frozen), `detect_runtimes` with the stub;
  - `main` calls priming for `serve`/`doctor` (patched).
- **Behaviour note for the docs:** a Terminal-launched frozen `serve` on macOS now also gets the login-shell-first order.
- **Docs:** `the_one/agents.md` (the frozen-seam section gains the darwin login-shell `PATH`, the stub rule, the per-entry walk, the `doctor` lines) and `CLAUDE.md`'s Frozen-runtime seam paragraph (one additive sentence). Both are additive; Mission 31 is still active.

## Acceptance Criteria
- [x] **AC1:** every behaviour under Outputs is implemented and unit-tested as listed. The tests run on Linux with no AppKit, no real `xcode-select` and no real user shell (fakes and `tmp_path` scripts only).
- [x] **AC2:** Linux and Windows unchanged, except the `PATH` walk and the additive static entries. The existing env, interpreter and doctor tests pass unmodified, except where a test pinned first-hit-only behaviour. Such a test is renamed and inverted, never deleted (state which, or state that none was). The resolver's darwin message still satisfies `test_platform_interpreter.py`'s "install python"/"THE_ONE_PYTHON" assertions; pin the new text in a new test.
- [x] **AC3:** `make test-unit` passes with the expected 12 skips; `ruff check`/`ruff format --check` are clean.
- [x] **AC4:** `the-one doctor` on this Linux dev host (non-frozen, scratch data dir, port ≥ 8490) prints the same gate lines and `sandbox:`/`tray:` lines as before, and no `path:` line. Its output is quoted in the flight log.
- [x] **AC5:** a **mandatory** regression test in `tests/test_packaging_score.py` feeds a sample frozen-darwin `doctor` output to `score_doctor` and asserts a pass. The output has the `desktop shell: OK — Cocoa backend present` line, `window chrome`'s "skipped (not Windows)", and the `sandbox:`, `tray: dock` and `path: login shell` advisory lines. `score.py` itself needs no change: it keys on no pystray text, and `GATE_RE` ignores advisory lines.
- [x] **AC6:** hygiene: no 8484/8485, the operator data dir unchanged, only recorded pids killed, no files outside this leg's set (beyond the flight log section).

## Verification Steps
- The test names for each listed behaviour; `make test-unit` summary; the ruff lines.
- AC4: `THE_ONE_DATA_DIR=<scratch> THE_ONE_PORT=8496 .venv/bin/the-one doctor` output.
- AC5: grep `score.py` for the desktop-shell expectations; the test.

## Implementation Guidance
1. Interpreter first (pure, small), then the env priming, the order and the static list, then `main`, then `doctor`, then the docs.
2. Keep `prime_login_shell_path` free of `subprocess.run(timeout=…)`: use `Popen` with `start_new_session=True`, `wait(timeout)`, and `killpg` on timeout. `run(timeout=)` hangs when a grandchild holds the output pipe.
3. Record in the flight log any behaviour you chose that the DD leaves open.

## Edge Cases
- **`xcode-select -p` prints a path that no longer exists** (CLT removed): treat it as no CLT.
- **A login shell that prints the markers twice** (an rc file running a subshell): take the last block.
- **`PATH` entries with spaces:** split on `os.pathsep` only.
- **A user whose shell is `/usr/bin/false` or nologin:** a non-zero exit, so the static fallback.
- **`HOME` unset** in an odd launch: `Path.home()` may raise; guard it.

## Files Affected
- `the_one/platform/{env.py,interpreter.py}`, `the_one/diagnostics.py`, `the_one/main.py` (`stdio.py` unchanged)
- tests: the existing env/interpreter test files plus `tests/test_doctor.py` (and `tests/test_packaging_score.py` only if AC5 requires it)
- `packaging/linux/checks/score.py`: unchanged (AC5 adds only a test)
- `the_one/agents.md`, `CLAUDE.md` (additive)

### Citation Audit
Checked at `503ac2e`:
- `env.py::clean_subprocess_env`'s order (existing, then augment, then extra);
- `_common_runtime_dirs`'s POSIX list;
- `interpreter.py::_resolve_frozen_python`'s first-hit `which` and its Store-alias skip;
- `diagnostics.py::detect_runtimes` (`which` per name), `_probe_desktop_shell` (non-frozen-Linux → generic, which imports pystray), `_tray_line` (darwin `"tray: not probed (macOS)"`);
- `main.py::cli_entry`'s `serve`/`doctor` branches.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
