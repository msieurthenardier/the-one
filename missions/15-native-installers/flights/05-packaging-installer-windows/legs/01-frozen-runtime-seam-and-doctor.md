# Leg: frozen-runtime-seam-and-doctor

**Status**: completed
**Flight**: [Packaging & Installer — Windows](../flight.md)

## Objective

Build the cross-OS **freeze runtime seam** — a `clean_subprocess_env()` PATH
sanitizer inside the existing env chokepoint, a frozen-detection helper, the
`resolve_python()` frozen fix, an `encoding="utf-8"` audit, `.env`-discovery
anchoring for frozen runtime, and a `the-one doctor` diagnostic subcommand — all
unit-tested host-native, written cross-platform, and Windows-exercised — so that a
frozen, double-clicked app can spawn `node`/`uv`/shell/python children correctly
and the spawn-fix is observable against the packaged binary.

## Context

This is **the load-bearing leg** of Flight 5 and the gate for the whole mission's
"a child process actually starts from the frozen app" criterion. The runtime seam
built here (DD2/DD3/DD4/DD8 + the `doctor` apparatus, DD5) is **reused unchanged by
Flight 6 (macOS) and Flight 7 (Linux)** — only the OS-specific freeze recipe and
installer differ downstream. The PyInstaller `.spec` (Leg 2), Inno installer (Leg
3), and CI packaged-smoke (Leg 4) all build on this leg's deliverables; the `doctor`
subcommand is the apparatus the CI smoke reads.

**Premise correction carried from Phase-5b review (flight DD2).** The textbook
PyInstaller child-spawn failure is two-fold: (a) a GUI launch has a stripped `PATH`,
and (b) PyInstaller leaks loader-path vars (`LD_LIBRARY_PATH`/`DYLD_*`, stashing the
originals in `<VAR>_ORIG`) into children. **This codebase already defeats (b) by
construction:** `_build_subprocess_env()` (`the_one/platform/env.py:74-95`) does
**not** copy `os.environ` — it materializes a fresh child env from a hardcoded
allowlist (8 POSIX keys + 7 Windows keys). `LD_LIBRARY_PATH`/`DYLD_*`/`*_ORIG` are
**not in the allowlist**, so no child ever inherits them; the classic
restore-`_ORIG` machinery would be **dead code** here. The only allowlisted var
PyInstaller mutates is **`PATH`** (it prepends the `_MEIPASS`/bundle dir). So the fix
is narrow: strip the bundle dir from the child PATH front + augment PATH with common
runtime locations and an operator override. **Do not write speculative
loader-var restore code** — instead enforce the invariant "loader-path vars stay out
of the allowlist" with a test (DD2 scope decision).

**Citation note (drift from flight spec, corrected here):** `select_shell` /
`_kill_process_tree` are in `the_one/platform/shell.py` (flight DD3 wrote
`shell.py`/`tools/shell.py` loosely); `build_stdio_environ` is in
`the_one/mcp/transports/stdio.py` (flight DD2 wrote `mcp/stdio.py`). This leg uses
the verified paths.

**Prior legs:** none in this flight. Upstream, Flight 1 already wired
`Settings.data_dir` to a per-user OS location via `platformdirs`
(`the_one/config.py:_default_data_dir`), and Flight 4 added the `the-one app`
windowed entry (`the_one/main.py:cli_entry` `app` branch).

## Inputs

What exists before this leg runs:

- `the_one/platform/env.py:74-95` — `_build_subprocess_env() -> dict[str,str]`
  building a child env from `_ENV_ALLOWLIST` (lines 49-58: `PATH, HOME, USER,
  LOGNAME, LANG, LC_ALL, TERM, TZ`) unioned with `_WINDOWS_ENV_ALLOWLIST` (lines
  63-71: `SystemRoot, PATHEXT, COMSPEC, TEMP, TMP, USERPROFILE, USERNAME`) on
  `os.name == "nt"`. No frozen handling; no `clean_subprocess_env`.
- `the_one/platform/interpreter.py:39-59` — `resolve_python()` returns
  `str(Path(sys.executable).resolve())`. No frozen handling. The legacy
  `profile=None` branch lives in `run_python()` (lines 91-119), not in
  `resolve_python()`.
- `the_one/platform/shell.py:47-63` — `select_shell()` (POSIX honors `$SHELL`,
  Windows returns `cmd.exe`); `:159-174` — `_kill_process_tree()` (Windows path is a
  bare `proc.kill()`). **Note:** a sibling `_kill_process_tree` also exists at
  `the_one/platform/interpreter.py:158-170`. Tree-kill is **out of scope** for this
  leg (dispositioned OUT in the flight Open Questions → carried to F7/maintenance);
  both are listed only so the implementer isn't surprised by the duplicate.
- `the_one/platform/pty_unix.py:248` — `os.execvp(spec.command, [spec.command,
  *spec.args])`; spawn env computed pre-fork at `:195-201`.
- `the_one/platform/pty_windows.py:301` — spawn env via `_build_subprocess_env()`.
- `the_one/mcp/transports/stdio.py:366-391` — `build_stdio_environ(source,
  allowlist_env)` returns `{**allowlist_env, **config_env, **source.secrets}`.
  External-runtime detection is **inlined** in `_translate_inner_spawn_error()`
  (`:276-363`) with a `_RUNTIME_INSTALL_HINTS` dict (~`:230-250`) — there is **no**
  standalone `detect_runtimes()` helper yet.
- `the_one/platform/sandbox/passthrough.py:43-58` — `prepare_spawn()` forwards env
  verbatim (`env=dict(env)`); the active Windows/non-Linux backend.
- `the_one/tools/python_exec.py:111,123` — both call `_build_subprocess_env()`.
- `the_one/main.py:10-36` — `cli_entry()` dispatches `chat|serve|app|version`,
  trailing `else` prints usage + `sys.exit(1)`.
- `the_one/config.py:26` — `model_config = {"env_prefix": "THE_ONE_", "env_file":
  ".env", "extra": "ignore"}`; `_default_data_dir()` (lines 15-22) via
  `platformdirs.user_data_dir("the-one", appauthor=False)`.
- Encoding sites (unencoded text I/O): `the_one/interfaces/web/app.py:1631`
  (`(STATIC_DIR / "index.html").read_text()`; `STATIC_DIR` at `:80`);
  `the_one/agent/store.py:48,54,76,78` (**`:48,76` are `read_text()`, `:54,78` are
  `write_text()` — all four need `encoding="utf-8"`, reads included, since the
  cp1252 *decode* risk DD4 targets is on reads**); `the_one/tools/filesystem.py:412,506`
  (writes — reads at `:382,496,740` already use `errors="replace"`);
  `the_one/platform/sandbox/factory.py:104` (`open(_knob)` reading a Linux procfs
  knob — ASCII, Linux-only).
- **Grep false-positives to pre-empt (NOT encoding sites, leave untouched):**
  `the_one/interfaces/web/api.py:4534` — `os.open(...)` + `os.write(fd, new_key)`,
  genuinely **binary** fd I/O (an encryption key); adding `encoding=` to `os.open`
  is a `TypeError`. `the_one/interfaces/app.py:135` — `webbrowser.open(url)`, not
  file I/O. The `open\(`/`read_text`/`write_text` grep will surface both; both are
  correct as-is.
- Tests live flat under `tests/` (e.g. `test_platform_interpreter.py`,
  `test_platform_shell.py`, `test_execution_helpers.py` covers
  `_build_subprocess_env`, `test_mcp_stdio_sandbox.py` covers `build_stdio_environ`).
  `pyproject.toml`: `asyncio_mode = "auto"`; default marks exclude `live, browser,
  pixel, requires_bwrap, discord_hat`. Host-native invocation:
  `.venv/bin/python -m pytest …`.

## Outputs

What exists after this leg completes:

- `the_one/platform/env.py` — a `clean_subprocess_env(env: dict[str,str]) ->
  dict[str,str]` function and a frozen-detection helper (`is_frozen()` and the
  bundle-dir resolver), with `clean_subprocess_env` applied inside
  `_build_subprocess_env()` so every spawn path inherits the sanitized PATH. The
  loader-var-out-of-allowlist invariant is asserted by a test.
- `the_one/platform/interpreter.py` — `resolve_python()` resolves a real external
  interpreter when frozen and raises an actionable, non-Docker error if none found.
- `the_one/platform/shell.py` / `pty_unix.py` — frozen-binary posture for shell
  selection / `execvp` (absolute/validated binary, no bare-name PATH exec when
  frozen); Windows `cmd.exe` path unchanged.
- All unencoded product text-I/O sites carry `encoding="utf-8"`; `factory.py:104`
  carries a documented "Linux-only, ASCII, left as-is (revisit at F7)" disposition.
- `.env` discovery anchored for frozen runtime (or frozen-ignores-`.env`
  documented) — DD8.
- `the_one/main.py` — a `doctor` subcommand; a `the_one/diagnostics.py` (or similar)
  module implementing the spawn-probe + a factored `detect_runtimes()`.
- New unit tests covering all of the above; full host-native unit suite green.

## Acceptance Criteria

- [ ] `clean_subprocess_env(env)` exists in `the_one/platform/env.py` and, when the
      app is frozen, **(1)** removes the `_MEIPASS`/bundle directory from the front of
      the child's `PATH` and **(2)** augments `PATH` with common runtime locations
      plus an operator-configurable override; when **not** frozen it returns PATH
      effectively unchanged.
- [ ] `_build_subprocess_env()` applies `clean_subprocess_env` to its result, so
      MCP stdio, shell, python-exec, and PTY spawn paths all receive the sanitized
      env without per-call-site changes.
- [ ] A frozen-detection helper (`is_frozen()` reading `getattr(sys, "frozen",
      False)` / `hasattr(sys, "_MEIPASS")`) exists and is used by the seam.
- [ ] The MCP PATH-precedence is resolved and tested: a `strip_bundle_dir_from_path`
      helper is **re-applied at the caller** (`transports/stdio.py:430`) after the
      `build_stdio_environ` merge `{**allowlist_env, **config_env, **source.secrets}`,
      so the bundle-dir strip survives even when operator config sets `PATH` (strip
      always wins; augmentation yields to an explicit operator `PATH`).
      `build_stdio_environ` stays pure (uncoupled from the freeze seam). A unit test
      asserts the sanitized PATH survives the merge.
- [ ] An invariant test asserts `LD_LIBRARY_PATH`, `DYLD_LIBRARY_PATH`,
      `DYLD_FALLBACK_LIBRARY_PATH`, and any `*_ORIG` keys are **not** present in
      `_ENV_ALLOWLIST`/`_WINDOWS_ENV_ALLOWLIST` and never appear in a built child env
      (no restore-`_ORIG` code is added).
- [ ] When frozen, `resolve_python()` returns a real external interpreter resolved
      by absolute path on the augmented PATH, and raises an **actionable, non-Docker**
      error (naming "install Python / configure a path") when none is found —
      verified by a unit test mocking `sys.frozen`/`_MEIPASS`.
- [ ] Frozen shell/PTY posture: when frozen, shell selection and the POSIX
      `os.execvp` path use an absolute/validated binary rather than a bare-name PATH
      exec; Windows `cmd.exe`/pywinpty path is unchanged. Unit-tested.
- [ ] Every product unencoded text-I/O site listed in Inputs carries
      `encoding="utf-8"`; `factory.py:104` carries the documented Linux-only/ASCII
      disposition (a code comment). A grep across `the_one/` finds no remaining
      unencoded `open(`/`read_text(`/`write_text(` on text (binary `"rb"`/`"wb"` and
      already-`errors="replace"` read sites excluded).
- [ ] `.env` discovery is anchored for frozen runtime (DD8): either `env_file` is
      anchored to a known location (data dir / next to the exe) so a frozen app's
      unpredictable CWD doesn't silently drop `.env`, **or** the frozen build is
      documented to ignore `.env` and read `THE_ONE_*` env vars — with the chosen
      behavior unit-tested or asserted.
- [ ] A `the-one doctor` subcommand exists (`main.py:cli_entry` `doctor` branch). It
      runs inside the (potentially frozen) process, calls `_build_subprocess_env()`,
      **spawns a probe child** through the real spawn path (e.g. `cmd /c echo` on
      Windows / `sh -c echo` on POSIX, plus `node --version` when present), runs
      external-runtime detection, prints a structured PASS/FAIL including a "child
      spawn: OK"-style line, and **exits non-zero on failure**. It is LLM-free (no
      agent loop).
- [ ] A `detect_runtimes()` probe is factored out (or inlined in `doctor`) — `doctor`
      does not assume a pre-existing reusable detector.
- [ ] New unit tests pass host-native; the full default unit suite
      (`-m 'not live and not browser and not pixel and not requires_bwrap and not
      discord_hat'`) is green; `serve`/`chat`/`app`/`version` dispatch unchanged.

## Verification Steps

- `clean_subprocess_env` strip+augment: unit test mocking a frozen `sys`
  (`sys.frozen=True`, `sys._MEIPASS="/bundle"`) and a `PATH` of `"/bundle:/usr/bin"`
  → assert `/bundle` removed from the front and common dirs appended; non-frozen →
  PATH unchanged.
- MCP precedence: build `build_stdio_environ` with a config `env={"PATH": "/op"}`
  and assert the bundle-dir strip still holds and the result is well-defined per the
  chosen precedence rule.
- Allowlist invariant: `assert "LD_LIBRARY_PATH" not in _ENV_ALLOWLIST + _WINDOWS_ENV_ALLOWLIST`
  (and the DYLD/`*_ORIG` variants); build a child env with those set in
  `os.environ` and assert they're absent from the result.
- `resolve_python()` frozen branch: mock `sys.frozen`; with a fake interpreter on
  PATH assert it's resolved by absolute path; with none assert the actionable error
  is raised with the expected guidance text.
- Encoding audit: `grep -rnE "open\(|read_text\(|write_text\(" the_one/` and confirm
  every text site either has `encoding="utf-8"`, is binary (`"rb"`/`"wb"`), uses
  `errors="replace"` on read, or carries the factory.py Linux-only disposition.
- `doctor`: run `.venv/bin/python -m the_one doctor` (or `the-one doctor`) on the
  host → exit 0, output contains a child-spawn-OK line and a runtime-detection
  summary; simulate a missing runtime / unspawnable child and assert non-zero exit.
- Regression: `.venv/bin/python -m pytest -m 'not live and not browser and not pixel
  and not requires_bwrap and not discord_hat' tests/ -x --timeout 60`.

## Implementation Guidance

1. **Frozen-detection helper (DD3).** Add to `the_one/platform/env.py` (or a small
   shared spot the seam already imports): `def is_frozen() -> bool: return
   getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS")` and a
   `_bundle_dir() -> str | None` returning `sys._MEIPASS` (or `Path(sys.executable).parent`
   for a one-dir layout) when frozen, else `None`. Keep it import-cheap (no heavy
   deps) — it's called on every spawn.

2. **`clean_subprocess_env()` (DD2 — load-bearing).** Add
   `def clean_subprocess_env(env: dict[str, str]) -> dict[str, str]` that operates on
   the **already-allowlisted** dict:
   - If not frozen, return `env` unchanged (cheap fast-path).
   - If frozen: split `env.get("PATH", "")` on `os.pathsep`; drop leading entries
     equal to the bundle dir (normalize with `os.path.normcase`/`normpath` on
     Windows); then append common runtime locations (platform-appropriate — e.g.
     `/usr/local/bin`, `/opt/homebrew/bin`, `~/.local/bin`, npm/uv global bins on
     POSIX; `%ProgramFiles%\nodejs`, `%APPDATA%\npm`, the uv install dir on Windows)
     plus an operator override read from settings/env (e.g. `THE_ONE_EXTRA_PATH`).
     De-dup while preserving order.
   - Call it at the end of `_build_subprocess_env()`:
     `return clean_subprocess_env({k: os.environ[k] for k in allowlist if k in os.environ})`.
   - **MCP precedence (DD2 — DECIDED).** Rule: the **bundle-dir strip always wins**
     (applied even to an operator-supplied `PATH`); **augmentation yields** to an
     explicit operator `PATH`. **Keep `build_stdio_environ` pure** (it stays a small
     merge) — do **not** couple the MCP transport to the freeze seam. Instead export a
     tiny `strip_bundle_dir_from_path(env: dict[str,str]) -> dict[str,str]` from
     `platform/env.py` and **re-apply it at the caller** — the spawn site
     `transports/stdio.py:430` (`build_stdio_environ(source, _build_subprocess_env())`)
     — after the merge, so an operator `PATH` in MCP config never re-introduces the
     bundle dir. Unit-test the survival-through-merge at that boundary.
   - **Override source (DECIDED).** Read the operator overrides (`THE_ONE_EXTRA_PATH`,
     and `THE_ONE_PYTHON` in step 3) from **raw `os.environ`**, not from `Settings`.
     `platform/env.py` has no `config` import today; reading `os.environ` keeps the
     seam free of a `platform → config` dependency (avoids an import cycle). They share
     the `THE_ONE_` prefix convention but are intentionally plumbing-level, not
     product settings.
   - **Do NOT** add `LD_LIBRARY_PATH`/`DYLD_*`/`*_ORIG` restore logic — it is dead
     against the allowlist. Instead add the invariant test (criterion above).

3. **`resolve_python()` frozen fix (DD3).** In
   `the_one/platform/interpreter.py:resolve_python`, branch on `is_frozen()`: when
   frozen, do **not** return `sys.executable` (it's the frozen app, not python).
   Resolve a real interpreter by absolute path — search the augmented PATH for
   `python3`/`python` (and `THE_ONE_PYTHON` override if you add one) via
   `shutil.which` against the cleaned env's PATH; if none, raise a clear error
   (reuse the project's error type if one fits; message must be non-Docker and tell
   the operator to install Python or set the override). Non-frozen behavior is
   unchanged. Feed this error into the `doctor` runtime-detection surface.

4. **Frozen shell/PTY posture (DD3).** `shell.py:select_shell` POSIX branch and
   `pty_unix.py:248`'s `os.execvp` rely on PATH/`$SHELL`. When frozen, resolve the
   shell to an absolute path (e.g. `shutil.which` on the cleaned PATH, fall back to
   `/bin/sh`) so there's no bare-name exec against a stripped PATH. Windows
   (`cmd.exe` via `select_shell` / pywinpty) already resolves via Win32 — leave it.
   Keep changes minimal and behind `is_frozen()` so non-frozen behavior is identical.

5. **Encoding audit (DD4).** Add `encoding="utf-8"` to:
   `interfaces/web/app.py:1631` (`read_text(encoding="utf-8")`);
   `agent/store.py:48,54,76,78` (the `read_text`/`write_text` calls);
   `tools/filesystem.py:412,506` (the `write_text` calls). Leave the
   `errors="replace"` read sites (`filesystem.py:382,496,740`) as-is. At
   `factory.py:104` add a comment: `# Linux-only procfs knob (ASCII); explicit
   encoding unnecessary, left as-is — revisit at F7`. Re-grep to confirm no other
   product text site is unencoded.

6. **`.env` anchoring (DD8).** Decide: anchor `env_file` to a stable path so a
   frozen app's CWD doesn't matter, **or** document frozen-ignores-`.env`.
   Recommended: when frozen, point pydantic-settings `env_file` at a known location
   (the data dir, or the directory next to the exe). **Chicken-and-egg caveat:**
   pydantic-settings resolves `env_file` from `model_config` at **class-definition
   time**, before any `Settings` instance exists — so you cannot reference
   `_default_data_dir()` as an instance method there. Compute the anchor path at
   import time (a module-level helper conditioned on `is_frozen()`, reusing the same
   `platformdirs.user_data_dir("the-one", appauthor=False)` call that
   `_default_data_dir` uses) and build the `SettingsConfigDict`/`model_config`
   `env_file` from it. Assert the chosen behavior in a test and note it in the
   data-dir/config docs. `THE_ONE_*` env vars must keep working regardless.

7. **`the-one doctor` (DD5 apparatus).** Add an `elif args[0] == "doctor":` branch
   in `main.py:cli_entry` (before the trailing `else`). Implement the logic in a new
   module (e.g. `the_one/diagnostics.py`) so it's testable: it (a) calls
   `_build_subprocess_env()`, (b) spawns a probe child through the real spawn path
   — `cmd /c echo the-one-doctor` on Windows, `sh -c 'echo the-one-doctor'` on POSIX
   — and checks output/exit, (c) probes `node --version` / `uv --version` when
   present, (d) runs `detect_runtimes()` — **reuse** the `_RUNTIME_INSTALL_HINTS`
   dict (~`transports/stdio.py:230-250`) for the install-guidance *messaging*, but
   **write the actual probe fresh** (`shutil.which`-style presence check against the
   cleaned PATH); there is no existing detector to extract, only hint strings, so do
   not assume a reusable detector exists, (e) prints a structured report with an
   unambiguous `child spawn: OK`/`child spawn: FAIL` line and a runtimes summary, and
   (f) `sys.exit(0)` on full pass, non-zero otherwise. No agent loop, no LLM. This is
   exactly what Leg 4's CI smoke reads (exit code + stdout).

8. **Tests.** Add focused unit files (match existing flat `tests/` naming):
   extend `test_execution_helpers.py` (or a new `test_frozen_runtime_seam.py`) for
   `clean_subprocess_env` + frozen-detection + the allowlist invariant; extend
   `test_platform_interpreter.py` for the frozen `resolve_python` branch;
   `test_mcp_stdio_sandbox.py` for PATH-survival-through-merge; a `test_doctor.py`
   for the `doctor` probe (mock the child spawn / monkeypatch a frozen `sys`). Mock
   `sys.frozen`/`sys._MEIPASS` via `monkeypatch.setattr`. Run host-native with
   `-x --timeout 60`.

## Edge Cases

- **Operator sets `PATH` in MCP server config** — bundle-dir strip must still apply
  (don't let the bundle leak back in via config). Tested.
- **Frozen app with no system Python** — `resolve_python()` must surface the
  actionable error, not silently re-launch the app. Tested.
- **One-dir vs one-file bundle dir** — DD1 commits to one-dir; `_bundle_dir()` should
  handle `_MEIPASS` (set in both) and the one-dir `sys.executable`'s parent. Don't
  hard-assume one-file temp-dir semantics.
- **Windows path case-insensitivity** — normalize with `os.path.normcase` before
  comparing the bundle dir against PATH entries.
- **`doctor` on a host (non-frozen) dev checkout** — must still pass (child spawns,
  runtimes detected) so the dev loop and CI host-native run can exercise it before a
  frozen binary exists.
- **Empty / missing `PATH`** — `clean_subprocess_env` must not crash on
  `env.get("PATH", "")` being empty.

**Scope note — POSIX frozen hardening is written-and-unit-tested now, not
load-bearing for *this* flight's CI.** The frozen `select_shell`/`os.execvp`
absolute-binary posture (step 4) and the POSIX side of `resolve_python` are written
here so F7 (Linux) inherits them, but the Windows packaged-smoke (Leg 4) exercises
only the Windows `cmd.exe`/pywinpty path. A frozen-POSIX regression would be caught
by the host-native unit tests on the Linux CI runner, **not** by the Windows smoke —
so it is correctness coverage, not a Windows-flight gate.

## Files Affected

- `the_one/platform/env.py` — `is_frozen()`, `_bundle_dir()`,
  `clean_subprocess_env()`, applied in `_build_subprocess_env()`.
- `the_one/platform/interpreter.py` — frozen branch in `resolve_python()`.
- `the_one/platform/shell.py` — frozen shell-resolution posture.
- `the_one/platform/pty_unix.py` — frozen `execvp` absolute-binary posture.
- `the_one/mcp/transports/stdio.py` — PATH-precedence handling in/after
  `build_stdio_environ`; possibly the factored `detect_runtimes()` source.
- `the_one/config.py` — frozen `.env` anchoring (DD8).
- `the_one/interfaces/web/app.py`, `the_one/agent/store.py`,
  `the_one/tools/filesystem.py`, `the_one/platform/sandbox/factory.py` — encoding
  audit.
- `the_one/main.py` — `doctor` dispatch branch.
- `the_one/diagnostics.py` *(new)* — `doctor` implementation + `detect_runtimes()`.
- `tests/test_frozen_runtime_seam.py` *(new)* + extensions to
  `test_platform_interpreter.py`, `test_mcp_stdio_sandbox.py`, `tests/test_doctor.py`
  *(new)*.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (host-native unit suite)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (this leg does NOT commit — Flight 5 batches
      review + commit after Leg 4; the Developer leaves status `landed`, signals
      `[HANDOFF:review-needed]`, and does not commit)
- [ ] (Flight-level) leg checkboxes / flight status handled at the flight commit

## Citation Audit

All citations were verified against current code at leg design time (2026-06-14) via
a dedicated recon pass. Two drift repairs vs. the flight spec were applied: (1)
`select_shell`/`_kill_process_tree` cited at `the_one/platform/shell.py:47-63,159-174`
(flight DD3 wrote `shell.py`/`tools/shell.py` ambiguously); (2) `build_stdio_environ`
cited at `the_one/mcp/transports/stdio.py:366-391` (flight DD2 wrote
`mcp/stdio.py:391`). All other line/symbol citations (`env.py:74-95`/`49-71`,
`interpreter.py:39-59`, `pty_unix.py:248`/`195-201`, `pty_windows.py:301`,
`passthrough.py:43-58`, `python_exec.py:111,123`, `main.py:10-36`, `config.py:26`,
encoding sites) verified `OK`.
