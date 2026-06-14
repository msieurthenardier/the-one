# Flight: Packaging & Installer — Windows

**Status**: in-flight
**Mission**: [Native Desktop Installers](../../mission.md)

## Contributing to Criteria

- [ ] A user can install the app on **Windows (x64)** from a single downloadable
      installer artifact, with **no pre-existing Python or Docker installation**,
      and launch it from their OS application launcher. *(this flight delivers the
      Windows artifact + installer; the cross-OS criterion completes at F6/F7)*
- [ ] An MCP/tool child process **actually starts** when launched from the
      installed (frozen) app — not only from a source checkout. *(guards the
      PATH/library-var risk; proven this flight against the packaged Windows
      binary via the CI packaged-smoke + `the-one doctor`)*
- [ ] The installed deliverable includes a working **command-line interface**
      alongside the windowed app. *(Windows; CLI shipped inside the same frozen
      bundle)*
- [ ] When a required external runtime for MCP servers is absent, the app
      **detects this and presents actionable, non-Docker guidance** rather than
      failing silently. *(advanced via the `the-one doctor` diagnostic + frozen
      runtime-resolution errors)*

> The mission's cross-OS install criterion, the per-OS unsigned-app docs, and the
> **comprehensive operator HAT against the real installer** complete across F6
> (macOS), F7 (Linux), and F9 (acceptance). This flight stands up the **freeze
> runtime seam reused by all three** and proves it end-to-end on Windows.

---

## Pre-Flight

### Objective

Turn `the-one` into a **double-click Windows desktop application**: freeze the app
and its dependencies with **PyInstaller (one-dir)** into a self-contained bundle
(no system Python), wrap it in an **Inno Setup installer** whose Start-menu /
Desktop shortcut launches the windowed app (`the-one app`, from Flight 4), and
ship the CLI inside the same bundle. The load-bearing work is the **frozen-app
child-process spawn fix** — the mission's single biggest packaging risk: a frozen,
double-clicked app inherits a stripped `PATH` and PyInstaller injects library-path
env vars that corrupt spawned children (`node`/`uv`/`npx` for MCP, shell/python
tools). This flight builds a single `clean_subprocess_env()` sanitizer (routed
through the existing four-spawn-path chokepoint), fixes the frozen `sys.executable`
footgun, and closes the unencoded-text-I/O sites that fail silently in a
console-less Windows app. The fix is **proven against the packaged binary** by a CI
packaged-smoke on a Windows runner — not just the dev checkout. The cross-platform
env logic is written now so the macOS (F6) and Linux (F7) flights inherit the seam
and add only their OS-specific delta.

### Open Questions

- [x] Freeze tool (single bundler vs. freezer + per-OS installer) → **resolved,
      DD1** (PyInstaller one-dir + Inno Setup; recon-validated)
- [x] How a frozen, GUI-launched app finds `node`/`uv` and stops the bundle's
      libs leaking into children → **resolved, DD2** (`clean_subprocess_env`)
- [x] What a frozen `sys.executable` does to `run_python` → **resolved, DD3**
      (frozen-detection + external-interpreter resolution + actionable error)
- [x] How the spawn-fix is *observed* against the packaged artifact (apparatus) →
      **resolved, DD5** (`the-one doctor` diagnostic subcommand exercises the real
      frozen spawn path; CI packaged-smoke reads its exit code + output)
- [x] **`run_shell` Windows tree-kill** (F3 carry, mission Known Issue): fold into
      this flight, or carry to F7/maintenance? → **resolved: OUT of this flight
      unless trivially cheap.** Review confirmed `_kill_process_tree`
      (`shell.py:159-174`) does a bare `proc.kill()` on Windows (no Job Object),
      while the PTY backend already has the reusable `_create_job_and_assign`
      pattern (`pty_windows.py:319`) — but wiring a Job Object into
      `create_subprocess_shell`'s non-PTY proc is **more than a one-liner**, so it
      does **not** ride along in the load-bearing seam leg. Leg 5 records the
      disposition and carries it to F7/maintenance. It is a robustness gap (Windows
      ships unsandboxed, mission DD9), **not** a freeze blocker.

### Design Decisions

**DD1 — PyInstaller, one-dir mode; checked-in `.spec` is the build contract.**
PyInstaller is the pragmatic choice for this shape (FastAPI server + pywebview
window + a thicket of native deps + spawns children): it has the strongest hook
ecosystem for exactly the bundling problem we have. **One-dir, not one-file** —
one-file unpacks to a transient `_MEIxxxxxx` temp dir on every launch (slow
startup, Windows AV false-positives, and — critically — it makes the child-spawn
library-leak (DD2) *worse* and harder to reason about because the bundle lives in a
temp path that can be cleaned mid-run). The build is driven from a **checked-in
`.spec`** (not ad-hoc CLI flags) so hidden-imports/data-collection are versioned.
- Rationale: alternatives are worse fits — **Nuitka** makes the native-dep/hidden-
  import debugging *harder* and slows CI compiles for zero benefit on an I/O-bound
  app; **Briefcase** itself hit the WebKitGTK/AppImage wall (relevant to F7) and
  fights a FastAPI-server-in-a-window shape; **PyOxidizer** is effectively
  unmaintained and hostile to packages expecting on-disk files; **cx_Freeze** has a
  weaker hook ecosystem (more hand-written collection). Recon (PyInstaller official
  docs) confirmed the mechanism and hooks.
- Trade-off: PyInstaller config is per-OS — the `.spec` and installer recipe here
  are Windows-specific; F6/F7 add their own (the *runtime seam*, DD2/DD3/DD4, is
  shared; the *freeze recipe* is not).

**DD2 — The frozen child-spawn fix: PATH-sanitize inside the existing
`_build_subprocess_env` allowlist chokepoint.** *(load-bearing — the flight's
central deliverable; premise-corrected at Phase-5b review)* When a PyInstaller app
spawns a child, the textbook failure is two-fold: (a) a GUI/double-click launch has
a **stripped `PATH`** (bare `node`/`uv`/`npx` aren't found), and (b) PyInstaller's
bootloader prepends the bundle dir to the dynamic-loader path
(`LD_LIBRARY_PATH`/`DYLD_*`, stashing the pre-freeze value in `<VAR>_ORIG`), which
**leaks into children** and makes them load the bundle's incompatible libs. **This
codebase has already defeated leak (b) by construction:** `the_one/platform/env.py`'s
`_build_subprocess_env` does **not** copy `os.environ` — it materializes a fresh
child env from a **hardcoded allowlist** (8 POSIX keys + 7 Windows keys;
`env.py:49-71`). `LD_LIBRARY_PATH`, `DYLD_*`, and `<VAR>_ORIG` **are not in the
allowlist, so no child ever inherits them** — the classic restore-`_ORIG`-or-delete
machinery would be a **no-op** here. The one allowlisted var PyInstaller *does*
mutate is **`PATH`** (it prepends `_MEIPASS`/the bundle dir). So the real fix is
narrow and precise: a `clean_subprocess_env()` step **inside `_build_subprocess_env`**
that, when frozen, **(1) strips the `_MEIPASS`/bundle dir from the front of the
child's `PATH`** (so a child doesn't search the bundle first) **and (2) augments
`PATH`** with the common runtime locations + an operator-configurable override (so
`node`/`uv` resolve from a GUI launch). `_build_subprocess_env` is the correct single
insertion point: every spawn path calls it and passes the result **verbatim**
through `backend.prepare_spawn` (passthrough — always the Windows backend — forwards
env unchanged, `passthrough.py:58`): MCP stdio (`stdio.py:430`, via
`build_stdio_environ`), `tools/shell.py:112,124`, `tools/python_exec.py:111,123`,
PTY (`pty_windows.py:301` / `pty_unix.py:199`). No production spawn bypasses it (the
`profile=None` legacy `os.environ` branch in the platform helpers is reached only by
direct unit tests, never by the tools — which always pass a profile).
- **Scope decision:** the sanitizer is **PATH-focused** — the only var that actually
  leaks through the allowlist. We do **not** write speculative `LD_LIBRARY_PATH`/
  `DYLD_*` restore-`_ORIG` code: it would be dead against the current allowlist and
  F6/F7 would inherit a puzzle. The forward-proofing F6/F7 actually need is simply
  *"keep the loader-path vars out of the allowlist"* — a one-line invariant + a test,
  not a restore routine. (If a future change ever adds a loader var to the allowlist,
  the restore logic gets written **then**, with a reachable test.)
- **MCP precedence caveat (flag for Leg 1):** `build_stdio_environ` merges as
  `{**allowlist_env, **config_env, **source.secrets}` (`stdio.py:391`) — an operator
  who sets `PATH` in MCP server config would **override** the sanitized PATH. Leg 1
  must decide the precedence (recommend: the bundle-dir *strip* always wins even over
  operator PATH; augmentation yields to an explicit operator PATH) and unit-test that
  the sanitizer survives the merge.
- Rationale: one sanitizer at the existing allowlist chokepoint, scoped to the var
  that genuinely leaks, with no per-call-site drift and no dead cross-OS code.
- Trade-off: PATH augmentation is heuristic (common locations + operator override);
  an exotic node/uv install still needs the configured-path escape hatch — acceptable,
  the mission already requires "detect + guide" for absent runtimes (the `the-one
  doctor` surface, DD5).

**DD3 — Frozen detection + the `resolve_python()` / bare-name-exec footgun.** In a
frozen app `sys.executable` is the **frozen binary, not a Python interpreter** —
so `interpreter.py:resolve_python()` (returns `sys.executable`) makes `run_python`
**re-launch the whole app** instead of running python. Detect frozen via
`getattr(sys, "frozen", False)` / `hasattr(sys, "_MEIPASS")`. When frozen:
`resolve_python()` must resolve a **real external interpreter by absolute path**
on the augmented PATH (consistent with how `node`/`uv` are already external
children) and raise an **actionable, non-Docker error** if none is found (feeds the
`the-one doctor` / runtime-detection surface). Same posture for the shell binary:
`shell.py:select_shell` and `pty_unix.py:248`'s `os.execvp` rely on PATH/`$SHELL`
resolution — the frozen path must use absolute/validated binaries, no bare-name
PATH exec. (On Windows `cmd.exe` resolves via Win32 / pywinpty so the risk is low
there; the POSIX `execvp` hardening is written for F7 but unit-tested now.)
- Trade-off: a frozen app with **no** system Python can't run python-interpreter
  tools — by design this surfaces a clear "install Python / configure a path"
  message rather than a silent re-launch. (External runtimes are explicitly not
  bundled — mission constraint.)

**DD4 — Encoding audit: explicit `encoding="utf-8"` on all unencoded text I/O.**
A `cp1252` `UnicodeDecodeError` in a **frozen console-less Windows app** is a
*silent* failure (no stderr to observe). Add `encoding="utf-8"` to the product
sites recon found (all line-confirmed at review) — `interfaces/web/app.py:1631`
(serves `index.html`), `agent/store.py:48/54/76/78` (agent config R/W),
`tools/filesystem.py:412/506` (user-file writes) — and grep the rest of `the_one/`
for any other unencoded `open(`/`read_text(`/`write_text(`. One more the grep finds,
`sandbox/factory.py:104` `open(_knob)`, reads a Linux procfs knob (ASCII, never hit
on Windows): list it in the audit with a **"Linux-only, ASCII, left as-is (revisit
at F7)"** disposition rather than silently skipping it. (`filesystem.py` *read* sites
382/496/740 already use `errors="replace"` — safe.) F3/F4 carry-forward.
- Rationale: deterministic UTF-8 across all platforms; removes a whole class of
  silent frozen-Windows crashes. Trade-off: none material.

**DD5 — Verification: seam unit-tests + a `the-one doctor` diagnostic + a CI
packaged-smoke on a Windows runner (the spawn-fix's only real proof).**
*(operator-chosen apparatus)* Three layers:
1. **Unit tests (CI, host-native):** `clean_subprocess_env` (mock a frozen `sys` +
   a `_MEIPASS`-on-`PATH` and assert the bundle-dir strip + PATH augmentation +
   survival through `build_stdio_environ`'s merge), frozen-detection (mock
   `sys.frozen`/`_MEIPASS`), the `resolve_python()` frozen branch (external resolve
   + actionable error), the encoding sites. Fast, but never touches a real frozen
   binary.
2. **`the-one doctor` diagnostic subcommand (new, ships in the product):** a
   `main.py:cli_entry` branch that runs *inside the frozen process* — calls
   `_build_subprocess_env()` and **spawns a probe child** (e.g. `cmd /c echo` and,
   if present, `node --version`) through the real spawn path, plus runs the
   external-runtime detection — and prints a structured PASS/FAIL + exits non-zero
   on failure. This is the **apparatus** that makes the spawn-fix *observable*
   against the packaged artifact (read path = subcommand stdout + exit code), and
   it doubles as a user-facing "can my install spawn MCP runtimes?" diagnostic
   (mission's detect-and-guide criterion). LLM-free — does not need the agent loop.
   *(Note: today's external-runtime detection lives inside `stdio.py`'s spawn-error
   translation (`stdio.py:206`), not a standalone helper — Leg 1 factors a small
   `detect_runtimes()` out (or inlines a probe); `doctor` should not assume a
   reusable detector already exists.)*
3. **CI packaged-smoke (the real proof) — `windows-2022` runner:** build the frozen
   one-dir with the `.spec`, then (a) run **`the-one doctor`** against the *frozen*
   binary and assert exit 0 + "child spawn: OK" (proves `clean_subprocess_env` +
   PATH augmentation work on the packaged binary, not the checkout); (b) launch
   **`the-one serve`** frozen, poll `/api/info` until 200 (frozen app actually
   serves); (c) assert **single-instance** with the packaged binary (a second
   launch detects the first via the F4 `/api/info`+version probe). No Witnessed
   behavior test this flight — the rendered-window GUI HAT apparatus (the next
   mission's gated MCP) doesn't exist yet; the operator's **manual installer HAT**
   is the comprehensive end-of-mission acceptance (F9). An **optional operator HAT
   leg** (Leg 5) lets the operator install the real `.exe` on their Windows box as
   an early preview.

**DD6 — Installer: Inno Setup; shortcut → `the-one app`; CLI in the same bundle;
unsigned-app (SmartScreen) documented.** Inno Setup over NSIS/WiX — simplest
scriptable path for "take the one-dir, install under Program Files, make a
Start-menu + Desktop shortcut, give an uninstaller," with no MSI/Group-Policy need
and no signing this round. The shortcut invokes the **windowed entry `the-one app`**
(Flight 4 DD3) — *not* bare `the-one` (which drops to `chat`). The frozen bundle
ships the **CLI alongside** the windowed app (one multi-call exe dispatching on
argv per `main.py:cli_entry`, or a thin second exe — architect's call). The
installer is **unsigned**: Windows SmartScreen "unknown publisher / Windows
protected your PC → More info → Run anyway" is the click-through to document (the
Windows analogue of macOS Gatekeeper; full per-OS docs are F9). CI-friendly —
`iscc your.iss` runs headless on `windows-2022`.
- Trade-off: unsigned = SmartScreen friction on first run; accepted per the mission
  no-signing constraint. CI is structured so a signing step can be added later
  (conditional on a cert secret) without reworking the recipe.

**DD7 — `.spec` hidden-imports / data-collection contract.** PyInstaller's static
analysis misses runtime/string imports; the `.spec` must explicitly collect:
- **uvicorn[standard]** — `collect_all('uvicorn')` (its `loops.auto` /
  `protocols.http.auto` / `protocols.websockets.auto` string-imports + `uvloop`,
  `httptools`, `websockets`).
- **mcp** — `collect_submodules('mcp')` / `collect_all('mcp')` (pydantic-driven
  submodules missed statically).
- **pywinpty** — `collect_dynamic_libs('winpty')` + verify the ABI-specific `.pyd`
  and sibling `winpty.dll` are collected (add via `--add-binary` if not). Windows-
  only, must build on a Windows runner so the ABI matches (F3 carry).
- **cryptography** + **pywebview** — rely on the official contrib hooks (keep
  PyInstaller current); pywebview's hook pulls `pythonnet`'s `Python.Runtime.dll` +
  `WebBrowserInterop` on Windows. The freeze must include the **`the-one[gui]`
  extra** (`pyproject.toml:53-56` — the extra is **just `pywebview`**; `pythonnet`
  arrives **transitively** via pywebview's Windows EdgeChromium backend). The `.spec`
  collection must therefore walk pywebview's transitive closure (`pythonnet` /
  `clr_loader`), and `pip install the-one[gui]` on the Windows runner must actually
  resolve pythonnet — confirm at Leg 2.
- **aiosqlite / sqlite3** — confirm the stdlib `sqlite3` C-extension lands.
- **web static assets** — collect `the_one/interfaces/web/static/**` as `datas` so
  the frozen app serves the UI (`STATIC_DIR = Path(__file__).parent/"static"` is
  freeze-safe under `_MEIPASS`; the *data* must be bundled).
- **discord.py** — fine unless voice is used (`PyNaCl` hidden import); confirm not
  needed.
- **`multiprocessing.freeze_support()`** — absent today (`serve` runs single-process
  `uvicorn.run(app)`, no workers; no `multiprocessing` use in `the_one/`), so nothing
  triggers the Windows re-exec-the-bundle fork bomb now. Add a defensive
  `freeze_support()` at the top of the frozen entry as cheap insurance against any
  dep ever spawning via multiprocessing on Windows (Leg 2).

**DD8 — Frozen-runtime resource resolution: anchor `.env` discovery; static assets
are freeze-safe.** pydantic-settings resolves `env_file=".env"` (`config.py:26`)
**relative to runtime CWD** — and a double-clicked frozen app has an unpredictable
CWD (often `C:\Windows\System32` or the install dir), so `.env` silently resolves to
nothing or the wrong file. A behavior change, not a crash, but exactly the
"silent frozen-app surprise" class. Leg 1 (or Leg 2) must either **anchor
`env_file`** to a known location (the data dir / next to the exe) **or explicitly
document** that frozen builds ignore `.env` and read `THE_ONE_*` env vars. (The
mission's Open Questions already flag "pydantic-settings env-file discovery" as
expected long-tail freeze work — resolve it here, don't let it slip to F8.) The web
static dir (`STATIC_DIR = Path(__file__).parent/"static"`, `app.py:80`) is the **only**
`__file__`-based resource load in the package and is freeze-safe under `_MEIPASS`
**provided** the 78 static files are bundled as `datas` at `the_one/interfaces/web/
static` (DD7) so the rewritten `__file__` resolves.

### Prerequisites

- [x] Flight 4 completed — the windowed `the-one app` entry exists
      (`the_one/interfaces/app.py:run`, `main.py` `app` branch) for the shortcut to
      invoke.
- [x] `_build_subprocess_env` is the single env chokepoint all four spawn paths
      route through (`the_one/platform/env.py`) — so DD2 has one insertion point.
- [x] pywinpty + pywebview install on `windows-2022` (F3 already runs pywinpty on
      that runner; the `[gui]` extra adds pywebview+pythonnet) — confirm the freeze
      pulls `the-one[gui]` at Leg 2.
- [ ] **Windows build host**: the canonical build runs on the `windows-2022` GitHub
      runner (PyInstaller must run on native Windows to emit a Windows exe — *not*
      under WSL2). The operator's Windows box is for the optional HAT (Leg 5), not
      required to produce the artifact. Confirm at Leg 2.
- [ ] **Packaged-smoke prerequisites (behavior-test-adjacent, apparatus-audited):**
      the `windows-2022` runner can (a) build the frozen one-dir, (b) run the
      frozen binary headless, (c) reach `node` on PATH for the `doctor` node-probe
      (windows-2022 ships Node) — verified at Leg 4. The *act* path is `the-one
      doctor` / `the-one serve` on the frozen binary; the *observe* path is the
      subcommand exit code + stdout and `/api/info`'s 200 + version body.

### Pre-Flight Checklist

- [x] Open questions resolved (DD1–DD8); run_shell tree-kill explicitly dispositioned
      OUT (carry to F7/maintenance)
- [x] Design decisions documented
- [x] Prerequisites verified (three confirm-at-leg items, non-blocking to start)
- [x] Validation approach defined (DD5 — unit + `doctor` + CI packaged-smoke)
- [x] Legs defined

---

## In-Flight

### Technical Approach

Build the **freeze runtime seam** first (Leg 1): `clean_subprocess_env()` inside
`platform/env.py`'s `_build_subprocess_env`, frozen-detection, the `resolve_python`
frozen fix, the encoding audit, and a `the-one doctor` diagnostic that exercises the
spawn path — all unit-tested host-native, all cross-platform but Windows-exercised.
Then author the checked-in **PyInstaller `.spec`** (Leg 2, DD1/DD7) and confirm a
frozen one-dir builds and launches on `windows-2022`. Wrap it in an **Inno Setup
installer** (Leg 3, DD6) with the `the-one app` shortcut + CLI. Stand up the **CI
packaged-smoke** (Leg 4, DD5) that builds the frozen artifact and proves — against
the *packaged* binary — that `the-one doctor` spawns a child, `serve` serves, and
single-instance holds. Close with **docs + verify** (Leg 5): Windows install +
SmartScreen workaround, the run_shell tree-kill disposition, README/CLAUDE build
notes, all lanes green, `serve`/`chat`/`app` unchanged — plus an optional operator
HAT installing the real `.exe`.

### Checkpoints

- [ ] `clean_subprocess_env()` strips the `_MEIPASS`/bundle dir from the child's
      `PATH` and augments it (survives the `build_stdio_environ` merge); routed
      through `_build_subprocess_env`; unit-tested. (The allowlist already blocks the
      `LD_LIBRARY_PATH`/`DYLD_*` leak class — invariant + test, no restore code.)
- [ ] `.env` discovery anchored (or frozen-ignores-`.env` documented); `freeze_support()`
      in the frozen entry — DD8
- [ ] Frozen-detection + `resolve_python()` frozen branch (external resolve +
      actionable error); shell/PTY frozen-binary posture; unit-tested
- [ ] All unencoded text-I/O sites carry `encoding="utf-8"` (audit clean)
- [ ] `the-one doctor` spawns a probe child through the real path, detects external
      runtimes, exits non-zero on failure
- [ ] PyInstaller `.spec` builds a frozen one-dir on `windows-2022` that launches
      (`the-one app` opens; `the-one serve` serves)
- [ ] Inno Setup installer installs under Program Files, makes a Start-menu /
      Desktop shortcut → `the-one app`, ships the CLI, uninstalls cleanly
- [ ] **CI packaged-smoke (windows-2022):** frozen `the-one doctor` exits 0 + "child
      spawn: OK"; frozen `serve` → `/api/info` 200; single-instance holds on the
      packaged binary
- [ ] `serve` / `chat` / `app` paths unchanged (regression); all CI lanes green
- [ ] *(optional)* Operator HAT: real `.exe` installs + launches + spawns a child +
      single-instances on the Windows box

### Adaptation Criteria

**Divert if**:
- PyInstaller cannot collect a load-bearing native dep (pywinpty `.pyd`/`winpty.dll`
  or pywebview/pythonnet) even with a custom hook, such that the frozen app can't
  open a window or run a PTY → re-evaluate the bundler (cx_Freeze fallback) with
  operator input before continuing.
- `clean_subprocess_env` can't be made to reliably spawn a child from the frozen
  binary on Windows (the packaged-smoke `doctor` step stays red) → escalate; this is
  the flight's central risk and the gate for the whole mission's spawn criterion.

**Acceptable variations**:
- The exact `.spec` collection mechanics (`collect_all` vs. enumerated hidden-
  imports) and custom-hook vs. `--add-binary` for pywinpty
- CLI-as-second-exe vs. one multi-call exe (DD6) — architect/`.spec` call
- `the-one doctor` naming (`doctor`/`selfcheck`/`--check`) and probe-child choice
- The MCP `PATH`-precedence resolution (DD2) — bundle-strip-always vs. yield-to-
  operator-PATH-config — within the stated intent
- Inno Setup vs. an equivalent (NSIS) if a blocker appears — DD6 is the default

### Legs

> Tentative breakdown — refined per-leg at design time (`/leg`).

1. **frozen-runtime-seam-and-doctor** — `clean_subprocess_env()` in
   `platform/env.py`'s `_build_subprocess_env` (**strip `_MEIPASS`/bundle dir from
   the child PATH front + augment PATH**; the allowlist already blocks the
   `LD_LIBRARY_PATH`/`DYLD_*` leak class → an invariant + test, **no** restore-`_ORIG`
   code; resolve the MCP `build_stdio_environ` PATH-precedence; DD2); frozen-detection
   helper; the `resolve_python()` frozen fix + actionable error and the shell/PTY
   frozen-binary posture (DD3); the unencoded-I/O audit incl. the `factory.py:104`
   disposition (DD4); `.env`-discovery anchoring (DD8); and the **`the-one doctor`**
   diagnostic subcommand (factor/inline a `detect_runtimes()` probe + spawn-probe —
   the DD5 apparatus). Unit-tested host-native, cross-platform logic, Windows-
   exercised. *The load-bearing leg.* (run_shell Windows tree-kill is **out** — see
   Open Questions.)
2. **pyinstaller-windows-spec** — the checked-in PyInstaller `.spec` (one-dir;
   `collect_all` uvicorn/mcp; `collect_dynamic_libs` winpty + the `.pyd`;
   cryptography/pywebview hooks incl. pywebview's transitive `pythonnet`/`clr_loader`;
   static-asset `datas`; the `the-one[gui]` extra; `multiprocessing.freeze_support()`
   in the frozen entry; the `the-one app` windowed entry + the CLI). A frozen one-dir
   builds and **launches** on `windows-2022` (DD1/DD7).
3. **inno-windows-installer** — the Inno Setup `.iss`: one-dir → Program Files,
   Start-menu/Desktop shortcut → `the-one app`, uninstaller, CLI shipped, unsigned-
   SmartScreen note. Produces the `.exe` installer (DD6).
4. **packaged-smoke-ci** — a `windows-2022` CI job that builds the frozen artifact
   and proves the spawn-fix against the *packaged* binary: frozen `the-one doctor`
   exits 0 + "child spawn: OK"; frozen `serve` → `/api/info` 200; single-instance
   holds (DD5). The spawn-fix's only real proof.
5. **docs-and-verify** *(+ optional HAT)* — Windows install + unsigned-app
   (SmartScreen) docs; record the run_shell tree-kill disposition; README/CLAUDE
   build-and-package notes (new `.spec`, Inno recipe, `the-one doctor`); verify all
   lanes green and `serve`/`chat`/`app` unchanged. **HAT/alignment (optional):** the
   operator installs the real `.exe` on their Windows box and confirms the window
   launches, a child process spawns, and single-instance holds — an early preview of
   the F9 comprehensive HAT.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (host-native unit lanes + the Windows packaged-smoke)
- [ ] Documentation updated (Windows install + SmartScreen; build/package notes;
      `the-one doctor`)

### Verification

- **Seam logic (CI, host-native)** — unit tests: `clean_subprocess_env` bundle-dir
  strip + PATH augmentation + survival through the `build_stdio_environ` merge (env
  mocked), frozen-detection (`sys.frozen`/`_MEIPASS` mocked), the `resolve_python`
  frozen branch + actionable error, the encoding sites.
- **Packaged artifact (CI, `windows-2022`)** — the packaged-smoke: build the frozen
  one-dir, then frozen `the-one doctor` exits 0 with a successful child spawn,
  frozen `the-one serve` answers `/api/info` 200, and a second frozen launch
  single-instances against the first. This is the **only** layer that exercises a
  real frozen binary — the spawn-fix's proof.
- **Installer (CI + optional operator HAT)** — `iscc` builds the `.exe` headless;
  optionally the operator installs it on a real Windows box and confirms launch +
  child spawn + single-instance (Leg 5).
- **No-regression** — `serve` / `chat` / `app` unchanged; all existing CI lanes
  (Linux default, Windows curated subset, bwrap, path-filtered browser) green.
- **Deferred** — the rendered-window GUI behavior test (apparatus = next mission's
  gated MCP) and the comprehensive cross-OS install HAT land at F9.
