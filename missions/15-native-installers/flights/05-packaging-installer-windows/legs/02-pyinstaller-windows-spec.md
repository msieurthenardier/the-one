# Leg: pyinstaller-windows-spec

**Status**: completed
**Flight**: [Packaging & Installer — Windows](../flight.md)

## Objective

Author the checked-in **PyInstaller one-dir `.spec`** (the build contract, DD1) plus
a frozen entry script with `multiprocessing.freeze_support()` (DD7), so that a frozen
Windows one-dir bundle of `the-one` — windowed app + CLI + all native deps + web
static assets — builds and launches on a `windows-2022` runner, with the hidden-import
/ data-collection contract (DD7) and frozen-resource resolution (DD8) all explicit.

## Context

Leg 2 consumes Leg 1's freeze runtime seam (the spawn fix, `is_frozen()`,
`resolve_python` frozen branch, `.env` anchoring, `the-one doctor`) and produces the
**freeze recipe** that turns the source tree into a Windows bundle. Per DD1 the build
is driven from a **checked-in `.spec`** (not ad-hoc CLI flags) so hidden-imports and
data-collection are versioned. The `.spec` and entry here are **Windows-specific**;
F6 (macOS `BUNDLE`+`.dmg`) and F7 (Linux `.deb`/`.rpm`) add their own freeze recipe —
but they reuse the **runtime seam** (Leg 1), not this `.spec`.

**Build-host reality (orchestration note).** PyInstaller must run on **native
Windows** to emit a Windows exe, and the load-bearing native deps (`pywinpty`,
`pywebview`→`pythonnet`) only install on Windows. This host is Linux/WSL2, so the
**actual freeze build + launch cannot be reproduced here** — the `.spec` is authored
and **statically validated** in this leg; the **build-and-launch proof on
`windows-2022` is performed by Leg 4's CI packaged-smoke** (which builds the frozen
one-dir from this `.spec`, then runs `the-one doctor`/`serve` against it). This leg's
acceptance criteria are therefore the locally-verifiable ones (spec is well-formed,
the contract matches DD7, the entry is unit-tested); the "frozen one-dir builds and
launches on windows-2022" milestone from the flight is **gated on Leg 4** and noted
as a forward dependency, not a regression in this leg.

## Inputs

What exists before this leg runs (post-Leg-1):

- `pyproject.toml` — `[project] name="the-one"`, deps include `uvicorn[standard]`,
  `mcp==1.27.0`, `cryptography>=43`, `aiosqlite>=0.20`, `discord.py>=2.4,<2.5`,
  `pywinpty>=2.0; sys_platform == "win32"`, `platformdirs>=4`. `[project.optional-
  dependencies] gui = ["pywebview[gtk]…; linux", "pywebview>=5,<6; sys_platform !=
  'linux'"]`. `[project.scripts] the-one = "the_one.main:cli_entry"`.
  `[tool.setuptools.package-data] the_one = ["interfaces/web/static/**/*"]`.
  **Version note:** `[project] version = "0.1.0"` but the runtime source of truth is
  `the_one/__init__.py:3 __version__ = "0.2.0"` — the `.spec` reads
  `the_one.__version__`, not the pyproject string.
- `the_one/main.py:cli_entry` — dispatches `chat|serve|app|version|doctor` (Leg 1
  added `doctor`). All subcommands are reached through this single entry; lazy
  `from …import` inside each branch (so `webview`, `interfaces.cli`,
  `interfaces.web.app`, `interfaces.app`, `diagnostics` are **runtime/string-ish**
  imports PyInstaller's static analysis may miss → hiddenimports).
- `the_one/__main__.py` — `python -m the_one` → `cli_entry()` (Leg 1).
- `the_one/interfaces/app.py:run` — the `the-one app` windowed entry: threaded
  in-process `uvicorn.Server`, lazy `import webview`, `webview.create_window(…)`;
  `webbrowser.open` fallback when no webview.
- `the_one/interfaces/web/app.py:80` — `STATIC_DIR = Path(__file__).parent /
  "static"`; 78 static files (html/css/js/woff2/png/ico) under
  `the_one/interfaces/web/static/**`. This is the only `__file__`-anchored resource
  load (freeze-safe under `_MEIPASS` *iff* the files are bundled as `datas`).
- No `freeze_support()` anywhere in `the_one/` (grep-confirmed). No `.spec`, no
  `packaging/`/`installer/` dir, no `build.py`.
- `.github/workflows/test.yml` — already has a **`windows` job on `windows-2022`**
  (Git Bash) installing `pip install -e ".[all-llms,dev]"` and running a curated
  platform-divergent test subset. Leg 4 extends this file (or adds a sibling job) with
  the packaged-smoke; **this leg does not touch CI**.

## Outputs

- `packaging/windows/the-one.spec` *(new)* — the checked-in PyInstaller one-dir spec.
- `packaging/windows/frozen_entry.py` *(new)* — the frozen entry script:
  `multiprocessing.freeze_support()` then `the_one.main.cli_entry()`.
- `packaging/windows/README.md` *(new)* — how to build locally on Windows
  (`pip install -e ".[gui,all-llms]"` + pyinstaller; `pyinstaller
  packaging/windows/the-one.spec`), the one-dir output path, and the
  windows-only-build caveat.
- A unit test for the frozen entry (freeze_support called + dispatch delegates).
- CLAUDE.md / README build-notes pointer (kept tight; the detailed recipe lives in
  `packaging/windows/README.md`).

## Acceptance Criteria

- [ ] `packaging/windows/the-one.spec` exists and is **syntactically valid Python**
      (`python -m py_compile packaging/windows/the-one.spec` succeeds) configured for
      **one-dir** (a `COLLECT`, not a one-file `EXE`-only build).
- [ ] The `.spec` reads the app version from `the_one.__version__` (0.2.0), not the
      stale pyproject `0.1.0`, and uses it **only for the dist-dir / EXE name and
      comments** — it does **NOT** pass a bare string to PyInstaller's `EXE(version=)`
      keyword (that keyword expects a `VSVersionInfo` resource file/object; a string
      is treated as a filename and **breaks the build**). For this unsigned leg, omit
      `version=` entirely (a `VSVersionInfo` resource is optional polish, out of scope).
- [ ] The `.spec` inserts the repo root on `sys.path` (`sys.path.insert(0, …)`) at the
      top, **before** `from the_one import __version__`, since that import runs at spec
      load time before `Analysis(pathex=…)` takes effect.
- [ ] The `.spec` entry script is `packaging/windows/frozen_entry.py`, which calls
      `multiprocessing.freeze_support()` **before** `cli_entry()` (DD7 fork-bomb
      insurance) — so the frozen `the-one.exe` dispatches `chat|serve|app|version|
      doctor` exactly like the console script.
- [ ] The `.spec` **hidden-imports / collection contract** covers (DD7):
      `collect_all('uvicorn')` (its `loops.auto`/`protocols.*.auto` string-imports +
      uvloop/httptools/websockets); `collect_submodules('mcp')` or
      `collect_all('mcp')`; `collect_dynamic_libs('winpty')` **plus** an explicit
      check/`--add-binary` for the ABI `.pyd` + sibling `winpty.dll`; cryptography +
      pywebview via their contrib hooks, with pywebview's transitive
      `pythonnet`/`clr_loader` (`Python.Runtime.dll`/`WebBrowserInterop`) collected;
      `aiosqlite` + the stdlib `sqlite3` C-extension; the lazy app subpackages
      (`the_one.interfaces.cli`, `the_one.interfaces.web.app`, `the_one.interfaces.app`,
      `the_one.diagnostics`, `webview`); and **`winpty` in `hiddenimports`** —
      `collect_dynamic_libs('winpty')` collects only the `.dll`/`.pyd` *binaries*, not
      the pure-Python `winpty` submodules, so the import name must be added explicitly.
- [ ] The web static assets are collected as `datas` via
      `collect_data_files('the_one', includes=['interfaces/web/static/**/*'])` (the
      `**/*` form — matching `pyproject.toml:69` package-data — for reliable deep
      recursion through `js/areas/admin/**`), preserving the package-relative path so
      the frozen app's `STATIC_DIR = Path(__file__).parent / "static"` resolves under
      `_MEIPASS` (DD8) — all 78 files, not just `index.html`.
- [ ] `discord.py` voice is confirmed unused → `PyNaCl` is **not** force-collected
      (or, if PyInstaller pulls it transitively, it is documented as benign); the
      `.spec` notes the disposition.
- [ ] `packaging/windows/README.md` documents the exact Windows build command, the
      required extras (`gui`, `all-llms`), the one-dir output location, and the
      **must-build-on-native-Windows** caveat (not WSL2).
- [ ] A unit test asserts `frozen_entry` calls `multiprocessing.freeze_support` and
      delegates to `cli_entry` (mock both) — runs host-native (no frozen binary
      needed).
- [ ] Host-native default unit suite stays green; no runtime code regressions
      (`serve`/`chat`/`app`/`version`/`doctor` unchanged). The `.spec`/entry are build
      artifacts — they must not be imported by the app at runtime.
- [ ] **Forward dependencies recorded (not a gate this leg):**
      (a) the actual frozen-build + launch on `windows-2022` is proven by Leg 4's CI
      packaged-smoke that consumes this `.spec`; and
      (b) **Leg 4's freeze job MUST install `pip install -e ".[gui,all-llms]"` then
      `pip install pyinstaller`** — the existing `windows` job in `test.yml` installs
      only `.[all-llms,dev]` (no `[gui]`), so without the `[gui]` extra the spec's
      pywebview→pythonnet collection import-fails at build time. The leg artifact and
      flight log state both explicitly.
- [ ] **Single multi-call EXE (DD6 pin):** the `.spec` emits **one** `EXE`/`COLLECT`
      (`the-one.exe`) that dispatches all subcommands via `cli_entry()` on argv — the
      Leg-3 shortcut invokes `the-one.exe app`, the CLI is the same exe. No second exe.

## Verification Steps

- `python -m py_compile packaging/windows/the-one.spec packaging/windows/frozen_entry.py`
  → no syntax errors.
- Read the `.spec` and confirm each DD7 collection line is present and correctly
  spelled (`collect_all`, `collect_submodules`, `collect_dynamic_libs` imported from
  `PyInstaller.utils.hooks`).
- Confirm `datas` includes the static tree — e.g. via
  `collect_data_files('the_one', includes=['interfaces/web/static/**'])` or an
  explicit `(src, 'the_one/interfaces/web/static')` Tree/tuple.
- `grep -n "freeze_support" packaging/windows/frozen_entry.py` → present before the
  `cli_entry()` call.
- `.venv/bin/python -m pytest tests/test_frozen_entry.py -x --timeout 60` (new) green;
  then the broader unit suite `-m 'not live and not browser and not pixel and not
  requires_bwrap and not discord_hat'` green.
- Confirm the app package does **not** import anything under `packaging/` (grep
  `import packaging` / `from packaging` across `the_one/` — should be the stdlib
  `packaging` dep usage only, if any, never this dir).

## Implementation Guidance

1. **Layout.** Create `packaging/windows/`. Keep all freeze artifacts here so the app
   package (`the_one/`) stays import-clean. F6/F7 will add `packaging/macos/`,
   `packaging/linux/` siblings.

2. **Frozen entry (`frozen_entry.py`).**
   ```python
   import multiprocessing
   from the_one.main import cli_entry

   if __name__ == "__main__":
       multiprocessing.freeze_support()  # DD7: no-op off-Windows; fork-bomb insurance
       cli_entry()
   ```
   This is the script PyInstaller analyses. `freeze_support()` must run first.

3. **The `.spec` (one-dir).** Author a standard PyInstaller `.spec`:
   - At the very top, `import sys, os; sys.path.insert(0, <repo root>)` **before**
     `from the_one import __version__` — the version import runs at spec-load time,
     before `Analysis(pathex=…)` is set. Compute the repo root relative to the spec
     file location (`packaging/windows/` → two parents up).
   - Use `__version__` for the **dist-dir / EXE name and a comment only**. Do **NOT**
     pass it to `EXE(version=…)` — that keyword wants a `VSVersionInfo` resource path/
     object; a string breaks the build. Omit `version=` (unsigned; resource metadata
     is out of scope).
   - `Analysis(['frozen_entry.py'], …)` with `pathex` set so `the_one` imports
     resolve, `hiddenimports=[…]` (the lazy subpackages above),
     `datas=collect_data_files('the_one', includes=['interfaces/web/static/**'])` +
     any hook datas, `binaries=collect_dynamic_libs('winpty') + …`.
   - Build `hiddenimports`/`datas`/`binaries` by composing the DD7 helpers:
     ```python
     from PyInstaller.utils.hooks import (
         collect_all, collect_submodules, collect_dynamic_libs, collect_data_files,
     )
     uvicorn_datas, uvicorn_bins, uvicorn_hidden = collect_all('uvicorn')
     mcp_hidden = collect_submodules('mcp')
     winpty_bins = collect_dynamic_libs('winpty')
     ```
     then merge into the `Analysis` args. Rely on contrib hooks for `cryptography`
     and `pywebview` (keep PyInstaller current) — do not hand-roll those unless the
     build proves them missing.
   - `EXE(…, name='the-one', console=True, …)` then `COLLECT(…)` for the one-dir.
     Keep `console=True` so the CLI (`the-one doctor`, `chat`, `serve`) has a console;
     the windowed `the-one app` opens its own webview regardless. (A
     console-less GUI variant is a possible later refinement — out of scope here;
     DD4's encoding audit already de-risks the console-less direction.)
   - **pywinpty `.pyd`/`winpty.dll`:** `collect_dynamic_libs('winpty')` grabs the
     binaries; **also add `'winpty'` to `hiddenimports`** (the helper collects only
     binaries, not the Python submodules). Add a comment instructing the Leg-4 build to
     verify and fall back to `--add-binary`/an explicit `binaries` tuple if the ABI
     `.pyd` or `winpty.dll` is missing (the flight's DD7 + Divert criterion).
   - **PyNaCl/discord voice:** add `excludes=['nacl']` — voice is unused, and
     excluding it both silences the PyInstaller "missing module" warning and trims the
     bundle (preferred over collecting-but-not-using).

4. **Static assets (DD8).** Ensure the 78-file static tree lands at
   `the_one/interfaces/web/static` inside the bundle so the rewritten `__file__`
   resolves. `collect_data_files('the_one', includes=['interfaces/web/static/**'])`
   preserves the package-relative path. Double-check `index.html`, `css/`, `js/`,
   `js/areas/**`, `fonts/`, `brand/` are all included (not just top-level).

5. **README build notes.** In `packaging/windows/README.md`: prerequisites (native
   Windows, Python 3.11, `pip install -e ".[gui,all-llms]"`, `pip install
   pyinstaller`), build command (`pyinstaller --noconfirm packaging/windows/the-one.spec`),
   output (`dist/the-one/the-one.exe`), and the WSL2-won't-work caveat. This README is
   the human-facing companion to the `.spec` contract and the input Leg 3's Inno
   script points at (`dist/the-one/`).

6. **Tests.** `tests/test_frozen_entry.py`: import `packaging/windows/frozen_entry.py`
   as a module (via `importlib.util.spec_from_file_location`) with `freeze_support`
   and `cli_entry` monkeypatched, assert call order. Do not attempt to run pyinstaller.

7. **Docs.** Add a one-line pointer in CLAUDE.md/README ("Windows packaging: see
   `packaging/windows/README.md`") — keep the detail in the packaging README.

## Edge Cases

- **PyInstaller not installed on this host** — fine; the `.spec` is data, validated by
  `py_compile`, not executed here. Do not add pyinstaller to the dev extras unless the
  flight calls for it (Leg 4's CI installs it on the runner).
- **`collect_*` helpers run at build time** — they import the target package, so they
  can't run on Linux for `winpty`. That's expected; the spec just *declares* them.
- **Version drift (pyproject 0.1.0 vs __init__ 0.2.0)** — read `__init__`. Optionally
  note the discrepancy for a future maintenance reconcile; do **not** rewrite
  pyproject here (out of leg scope).
- **One-file temptation** — DD1 forbids one-file (worse for the DD2 spawn fix +
  Windows AV). Keep `COLLECT` (one-dir).
- **`packaging/` picked up by setuptools find** — `[tool.setuptools.packages.find]`
  includes `the_one*` only, so `packaging/` won't be packaged into the wheel; confirm
  it isn't accidentally matched.

## Files Affected

- `packaging/windows/the-one.spec` *(new)*
- `packaging/windows/frozen_entry.py` *(new)*
- `packaging/windows/README.md` *(new)*
- `tests/test_frozen_entry.py` *(new)*
- `CLAUDE.md`, `README.md` — one-line packaging pointer.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All locally-verifiable acceptance criteria met; forward dependency on Leg 4 CI
      recorded
- [ ] `py_compile` + host-native unit suite green
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (Flight 5 batches review + commit after Leg 4;
      do NOT commit, do NOT touch flight.md status)

## Citation Audit

All citations verified against current code at leg design time (2026-06-14) via a
dedicated recon pass over the post-Leg-1 tree: `pyproject.toml` (deps/extras/scripts/
package-data), `the_one/__init__.py:3` (`__version__ = "0.2.0"`),
`the_one/main.py:cli_entry` (now with `doctor`), `the_one/__main__.py`,
`the_one/interfaces/app.py:run`, `the_one/interfaces/web/app.py:80` (`STATIC_DIR`),
`.github/workflows/test.yml` (`windows-2022` job). No drift found; all `OK`.
