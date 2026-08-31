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

## Prerequisites (native Windows)

- Windows 10/11 (or a `windows-2022` runner)
- Python 3.11
- The GUI + LLM extras **and** PyInstaller:

```powershell
pip install -e ".[gui,all-llms]"
pip install pyinstaller
```

> **The `[gui]` extra is required.** Without it, `pywebview` (and its transitive
> `pythonnet`) are absent and the spec's pywebview collection import-fails at
> build time. The existing `windows` CI job installs only `.[all-llms,dev]`
> (no `[gui]`) — the freeze job (Leg 4) must install `.[gui,all-llms]` +
> `pyinstaller`.

## Build

From the repo root:

```powershell
pyinstaller --noconfirm packaging/windows/the-one.spec
```

## Output

A one-dir bundle (DD1 — **not** one-file) containing **two exes**:

```
dist/the-one/
  the-one.exe        # CLI (console=True): chat|serve|app|version|doctor|rotate-api-credential  — no shortcut
  the-one-app.exe    # windowed launcher (console=False): always runs `app` — Start-menu shortcut
  ...                # collected binaries, the_one/interfaces/web/static/**, deps
```

- `the-one.exe` is the CLI entry point (all subcommands). Used for `the-one.exe doctor`,
  `the-one.exe chat`, etc. — no Start-menu shortcut.
- `the-one-app.exe` is the windowed launcher: `console=False`, no console window, hard-wired
  to run `app`. The Inno Setup `[Icons]` block creates the Start-menu (and optional desktop)
  shortcut pointing at `the-one-app.exe`, not `the-one.exe`.
- Smoke-check after building: `dist\the-one\the-one.exe doctor` (the frozen-runtime
  diagnostic) and `dist\the-one\the-one.exe version`.

`dist/the-one/` is also the input the Leg 3 Inno Setup script points at.

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
after that job has built the one-dir the installer consumes.

### Build

`iscc` needs the one-dir present at `dist/the-one/` first
(`pyinstaller --noconfirm packaging/windows/the-one.spec`). Then, from the repo
root:

```powershell
iscc packaging\windows\the-one.iss
```

The version defaults to `0.2.0` (a `#define AppVersion`, guarded by `#ifndef`).
CI overrides it with the live `the_one.__version__`:

```powershell
iscc /DAppVersion=1.2.3 packaging\windows\the-one.iss
```

### Output

```
packaging\windows\Output\the-one-setup-<version>.exe
```

e.g. `packaging\windows\Output\the-one-setup-0.2.0.exe` — the double-click
installer artifact (Leg 4's CI uploads it from `packaging/windows/Output/`).

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

- **Local Concourse (primary, unlimited).** A pipeline in the `the-one` Concourse
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
- **Version**: the spec names the bundle from `the_one.__version__` (`0.2.0`).
  The stale `pyproject.toml` `version = "0.1.0"` is a known discrepancy left for
  a future maintenance reconcile — do not rely on the pyproject string here.
- **PyNaCl / Discord voice**: `excludes = []` — the nacl exclusion existed only
  for discord.py's optional voice support; discord.py itself is gone from the
  dependency closure (Mission 23 Flight 1), so there is nothing left to
  exclude.
- **pywinpty binaries**: if a build warns that the `_winpty` `.pyd` or
  `winpty.dll` is missing, add an explicit `--add-binary` / `binaries` tuple in
  the spec pointing at the installed `pywinpty` package.
