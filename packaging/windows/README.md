# Windows packaging — PyInstaller one-dir freeze

This directory holds the **checked-in build contract** for freezing `the-one`
into a Windows one-dir bundle (windowed app + CLI + native deps + web static
assets):

- [`the-one.spec`](./the-one.spec) — the PyInstaller one-dir spec (hidden-imports,
  native-binary collection, static-asset tree). This is the versioned recipe;
  the build is driven from it, not from ad-hoc CLI flags.
- [`frozen_entry.py`](./frozen_entry.py) — the script PyInstaller analyses. Calls
  `multiprocessing.freeze_support()` (fork-bomb insurance) before delegating to
  `the_one.main.cli_entry`. Never imported by the running app.

These are **build artifacts**: the `the_one/` package never imports anything
under `packaging/`.

## ⚠️ Must build on native Windows (not WSL2)

PyInstaller emits a Windows `.exe` only when run **on native Windows**, and the
load-bearing native dependencies install on Windows only:

- `pywinpty` (ConPTY backend) — `sys_platform == "win32"` dependency.
- `pywebview` → `pythonnet` / `clr_loader` (the desktop webview).

The spec's `collect_*` helpers **import these packages at build time**, so the
freeze cannot be produced on Linux or WSL2 — it must run on a native Windows
host (or the `windows-2022` CI runner). On this repo's dev host (Linux/WSL2) the
spec is authored and statically validated via `py_compile` only.

## The recipe: `build.ps1` (Mission 32 Flight 4)

[`build.ps1`](./build.ps1) is the one Windows recipe. The Concourse task
(`ci/tasks/windows-installer-build.yml`, every push) and the GitHub workflow
(`.github/workflows/windows-packages.yml`) both call it, so both build the same way:

```powershell
packaging\windows\build.ps1 -Out C:\m32-build [-Version 0.11.9.dev1] [-Python C:\Python311\python.exe] [-ReuseVenv]
packaging\windows\build.ps1 -SelfTest        # argument handling, path checks, needle list; no Windows API
```

It does, in order, and throws on the first failure (`$LASTEXITCODE` is checked after every native call):

1. creates a fresh build venv under `-Out` (`-ReuseVenv` keeps one for an N+1 build);
2. installs the **locked closure** (`uv export --frozen ... --extra gui --extra all-llms`, then
   `pip install --require-hashes --no-deps`), never a fresh resolve (squawks 0009, 0015);
3. installs `pyinstaller==6.22.3` and records the `pyinstaller-hooks-contrib` version it pulled;
4. stages the source with `packaging/stage.py --target windows` into `<Out>\stage-windows-<V>`;
5. deletes, then renders, `packaging\windows\product.iss` from `product.iss.in` at version `<V>`
   (`render.py --set version=<V> --out ...`);
6. freezes with `M32_STAGE` set, into `<Out>\work-<V>` and `<Out>\dist-<V>`, so an N+1 build never
   clobbers N;
7. runs the frozen `the-one.exe doctor` and requires, by name, `usearch`, `fts5`, `embedding model`,
   `file watcher`, `window chrome`, `time zones`, `mcp sdk`, `desktop shell` and `child spawn` to read `OK`;
8. runs ISCC (`/DDistDir=<Out>\dist-<V> /O<Out>\installer-<V>`; Inno Setup 6.1 or newer when the
   version can be read) and writes `<Out>\build-<V>.env` (`VERSION`, `SETUP_EXE`, `DIST`).

Output: `<Out>\installer-<V>\the-one-setup-<V>.exe`. `-Version` empty means the `__version__` in
`the_one/__init__.py`. `-Out` must be **outside the repo**; the only file the build writes into the
repo is the rendered, gitignored `packaging\windows\product.iss`.

**The project is never installed** (no editable install). The spec requires `M32_STAGE` and puts only
the staged copy (and `packaging/`, for `import render`) on `sys.path`, as the macOS spec does, so the
bundle carries the staged version and nothing else. Nothing in `the_one/` reads its own distribution
metadata (`importlib.metadata.version("the-one")`; `diagnostics.py` reads only `mcp` and `httpcore2`),
so skipping the install is safe.

The product names (`install_dir_name`, `setup_file_stem`, `cli_executable`, `gui_executable`,
`publisher`) and the app GUID come from the `[windows]` section of `packaging/product.toml`. The
spec reads the two exe names through `render.load`; the installer reads the rest from the rendered
`product.iss`. The `AppId` line in `the-one.iss` stays **literal** (a test pins it to `app_guid`),
because it is the upgrade and uninstall identity of every shipped install.

## Building by hand (native Windows)

Only needed when iterating on the spec; prefer `build.ps1`. After a stage and a locked-closure install
(what `build.ps1` does), freeze from the repo root with the stage set:

```powershell
python packaging/stage.py --version 0.11.9.dev1 --target windows --out C:\m32-build
$env:M32_STAGE = "C:\m32-build\stage-windows-0.11.9.dev1"
pyinstaller --noconfirm --clean --workpath C:\m32-build\work --distpath C:\m32-build\dist packaging/windows/the-one.spec
```

> **The `[gui]` extra is required** in the build environment. Without it, `pywebview` (and its
> transitive `pythonnet`) are absent and the spec's pywebview collection import-fails at build time.

## Output

A one-dir bundle (DD1 — **not** one-file) containing **two exes**:

```
<Out>\dist-<V>\the-one\
  the-one.exe        # CLI (console=True): chat|serve|app|version|doctor|rotate-api-credential  — no shortcut
  the-one-app.exe    # windowed launcher (console=False): always runs `app` — Start-menu shortcut
  ...                # collected binaries, the_one/interfaces/web/static/**, deps
```

- `the-one.exe` is the CLI entry point (all subcommands). Used for `the-one.exe doctor`,
  `the-one.exe chat`, etc. — no Start-menu shortcut.
- `the-one-app.exe` is the windowed launcher: `console=False`, no console window, hard-wired
  to run `app`. The Inno Setup `[Icons]` block creates the Start-menu (and optional desktop)
  shortcut pointing at `the-one-app.exe`, not `the-one.exe`.
- Smoke-check after building: `<dist>\the-one\the-one.exe doctor` (the frozen-runtime
  diagnostic; `build.ps1` runs it) and `<dist>\the-one\the-one.exe version`.

The one-dir is also the input the Inno Setup script packages (`/DDistDir=<dist>`).

## Installer — Inno Setup (`the-one.iss`)

[`the-one.iss`](./the-one.iss) (DD6) wraps the one-dir above in a double-click
Windows installer: it installs `dist/the-one/` under
`Program Files\GleepGlorp AI\`, creates a Start-menu shortcut (and an optional
Desktop shortcut) launching the **windowed** app (`the-one.exe app`), and ships
the CLI in the same multi-call exe (`the-one.exe chat|serve|doctor|version|rotate-api-credential` run
from the install dir). The uninstaller is the Inno default — a clean uninstall
removes `{app}` and both shortcuts.

> **Display-name / slug split (deliberate):** the product display name is
> **"GleepGlorp AI"** (`AppName`, install dir, shortcut — matches
> `the-one.exe version` → `GleepGlorp AI v0.2.0`); the internal slug / exe name is
> **"the-one"** (`the-one.exe`, `the-one-setup-*.exe`). So `the-one.exe` lands
> under `Program Files\GleepGlorp AI\` with a "GleepGlorp AI" shortcut — intended,
> not a mismatch.

### ⚠️ Must compile on native Windows (not WSL2)

`iscc` (the Inno Setup compiler) is **Windows-only** — it cannot run on Linux or
WSL2. The `.iss` is authored and statically reviewed on the dev host; the actual
installer `.exe` is built by **Leg 4's CI on `windows-2022`** (which pins
**Inno Setup ≥6.3** so the `ArchitecturesAllowed=x64compatible` token compiles),
after that job has built the one-dir the installer consumes. (`build.ps1` checks the Inno version
when it can read it and refuses one older than 6.1; an unreadable version, such as the `0.0.0.0` the
hosted image reports, continues and the compile is the check.)

### Build

`build.ps1` does this (step 5 and 8 above). By hand, after a freeze, from the repo root: render the
include for the version you are building, then compile.

```powershell
python packaging/render.py --repo . --template packaging/windows/product.iss.in --set version=1.2.3 --out packaging/windows/product.iss
iscc /DDistDir=C:\m32-build\dist /OC:\m32-build\installer packaging\windows\the-one.iss
```

`the-one.iss` `#include`s `product.iss`, the only source of the version, the product name and the exe
names: there is no `AppVersion` define on the command line and no fallback, so a missing
`product.iss` is an ISCC error. `DistDir` is also required (`#error` when undefined). ISPP looks for
the include in the `.iss`'s own directory first, which is why `product.iss` is rendered there
(gitignored, deleted and re-rendered on every build).

### Output

```
<output-dir>\the-one-setup-<version>.exe
```

e.g. `C:\m32-build\installer-0.11.8\the-one-setup-0.11.8.exe` (the stem is `setup_file_stem` in
`product.toml`). The Concourse task copies it to `installer/` for the MinIO step, which matches
`the-one-setup-*.exe`.

### Installer icon

[`installer-assets/the-one.ico`](./installer-assets/the-one.ico) is a multi-size
brand icon (256/128/64/48/32/16 px) generated from the 512 px brand master
(`the_one/interfaces/web/static/brand/icon-512.png`). It is used in two places:

- **Baked into `exe_gui`** (`EXE(icon=...)` in `the-one.spec`): the windowed
  `the-one-app.exe` carries the brand icon as an embedded PE resource, giving the
  window title bar, taskbar button, and Alt-Tab switcher the brand icon on Windows.
  The CLI exe (`exe_cli`) does NOT carry the icon — console windows don't display it.
- **Installed by the Inno installer**: the `.iss` copies the `.ico` into `{app}` so
  the Start-menu shortcut and Add/Remove-Programs entry have a durable icon target
  independent of the exe resource.

**Regenerating the icon** (after a brand master change):

```powershell
python packaging/windows/regenerate_icon.py
```

Requires Pillow (`pip install Pillow`). Reads `icon-512.png`, writes
`installer-assets/the-one.ico`. Commit the updated `.ico` alongside the brand master
change.

### Privileges

`PrivilegesRequired=admin` + `{autopf}` → a machine-wide **Program Files**
install (requires elevation). The per-user alternative (out of scope this round)
is `PrivilegesRequired=lowest`, where `{autopf}` resolves to the per-user app dir
— no elevation, but per-user only.

### Unsigned installer — first run (SmartScreen)

This installer is **unsigned** (no code-signing this round, per the mission
constraint). On first double-click, Windows Defender SmartScreen shows a blue
**"Windows protected your PC"** dialog (unknown publisher). To proceed:

1. Click **More info**.
2. Click **Run anyway**.

This is expected for an unsigned app from an unknown publisher — it is **not** a
malware detection. A code-signing step can be added later (conditional on a cert
secret) by uncommenting the inert `SignTool=` / `SignedUninstaller` hook in
`the-one.iss` — no `.iss` rework required.

## Where the installer is built

Two places build the frozen installer; both run the same freeze + packaged-smoke:

- **Local Concourse (primary, unlimited).** The task runs `build.ps1` with `-Out` set to `build/`, a
  sibling of `repo`, and then copies the installer to `installer/`; it logs the ISCC version and
  whether `git` is on `PATH` (the staging step needs no git, so a `fly execute` upload whose `.git`
  gitlink points at nothing still builds). A pipeline in the `the-one` Concourse
  team (`ci/windows-installer.pipeline.yml` + `ci/tasks/windows-installer-build.yml`)
  polls the branch, builds on a `platform: windows` worker, and publishes the `.exe`
  to a local minio bucket. This is the day-to-day build — it runs on every push, with
  no GitHub artifact-storage quota.
- **GitHub Actions (release only).** The `build-windows-installer` job in
  [`.github/workflows/windows-installer.yml`](../../.github/workflows/windows-installer.yml)
  runs **only on a version tag** (`v*` pushed to `main`, e.g. `git tag v0.2.0 && git
  push origin v0.2.0`). Routine PRs/pushes do **not** trigger it — they run the unit
  CI in `test.yml`. (Flight 8 evolves this into the full release pipeline that
  publishes a GitHub Release asset.)

> **Mission 32 Flight 4, until leg 4:** `windows-installer.yml` still runs the old unstaged
> recipe (an editable install and a bare `the-one.spec` freeze), which the staged spec and `.iss`
> now refuse, so it is broken by design and leg 4 deletes it. **Push no `v*` tag before then.**

## CI packaged-smoke (the freeze proof)

The installer build **proves the DD2 child-spawn fix against the real frozen
binary** — the spawn-fix's only true apparatus (a checkout interpreter can't
exercise a PyInstaller bundle). It runs the freeze + smoke **before** building the
installer, so a red smoke never ships an unproven build, then builds the Inno
installer (and on the GitHub/tag path, uploads it as the `the-one-windows-installer`
artifact).

What it proves (against `dist/the-one/the-one.exe`, not the checkout):

- **(a) frozen `doctor`** exits 0 and prints both `child spawn: OK` and
  `RESULT: PASS` — `clean_subprocess_env` + PATH augmentation + the
  `resolve_python` interpreter gate all work on the packaged binary.
- **(b) frozen `serve`** answers a **credentialed** `http://127.0.0.1:8484/api/info`
  with HTTP 200 and `version == the_one.__version__`, polled with an `httpx`
  probe (the same library the product polls with — no Git-Bash-`curl`
  assumption). The local-API credential gate is live (Mission 20 Flight 1);
  `/api/info` returns `base_prompt` and is therefore never the unauthenticated
  exemption (that's `/api/live` — see `SECURITY-MODEL.md` "Authentication"),
  so the probe reads the long-lived credential via `get_credential()` and
  sends `Authorization: Bearer <credential>`. This works unmodified because
  the runner process and the frozen `serve` process share the same
  default `%LOCALAPPDATA%\the-one` data directory — whichever of the two
  creates the credential file first, the other reads it back.
- **(c) single-instance input**: the Flight-4 `_select_port` probe (run from
  source) sees the frozen instance as ours, confirming a second `app` launch
  would start no second server.

**Reading a failure — the Divert signal.** A red **(a) frozen doctor** step
means the packaged spawn-fix regressed: `clean_subprocess_env` / PATH / the
frozen `resolve_python` gate no longer work in the bundle. That is the flight's
**Divert** trigger (the whole-mission spawn gate) — escalate rather than patch
around it. A build-step failure naming a missing `pywinpty` `_winpty.pyd` /
`winpty.dll` is the same class of signal (see the pywinpty note below).

Because GitHub Actions cannot run on the Linux dev host, the GitHub installer build
is observed only when a tag is cut; the Concourse pipeline is what exercises the
freeze on every push in the meantime.

## Notes

- **One-dir, not one-file** (DD1): one-file is forbidden — it hurts the DD2
  child-spawn fix and triggers Windows AV heuristics.
- **Version**: the spec names the bundle from the *staged* `the_one.__version__` (`stage.py` writes
  the version being built, so an N+1 build is named N+1).
  The stale `pyproject.toml` `version = "0.1.0"` is a known discrepancy left for
  a future maintenance reconcile — do not rely on the pyproject string here.
- **PyNaCl / Discord voice**: the nacl exclusion existed only for discord.py's
  optional voice support; discord.py itself is gone from the dependency
  closure (Mission 23 Flight 1), so there was nothing left to exclude on that
  front. `excludes` is not empty, though — it now carries `["hf_xet"]`, dropped
  in for an unrelated reason; see the spec's own comment above `excludes =
  ["hf_xet"]` (squawk 0049 / M24 F02 L06) for why.
- **pywinpty binaries**: if a build warns that the `_winpty` `.pyd` or
  `winpty.dll` is missing, add an explicit `--add-binary` / `binaries` tuple in
  the spec pointing at the installed `pywinpty` package.
