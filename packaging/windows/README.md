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

A one-dir bundle (DD1 — **not** one-file):

```
dist/the-one/
  the-one.exe        # single multi-call exe: the-one.exe [chat|serve|app|version|doctor]
  ...                # collected binaries, the_one/interfaces/web/static/**, deps
```

- `the-one.exe` dispatches every subcommand via `cli_entry()` on argv — there is
  no second exe. The Start-menu shortcut (Leg 3) invokes `the-one.exe app`.
- Smoke-check after building: `dist\the-one\the-one.exe doctor` (the
  frozen-runtime diagnostic) and `dist\the-one\the-one.exe version`.

`dist/the-one/` is also the input the Leg 3 Inno Setup script points at.

## Installer — Inno Setup (`the-one.iss`)

[`the-one.iss`](./the-one.iss) (DD6) wraps the one-dir above in a double-click
Windows installer: it installs `dist/the-one/` under
`Program Files\GleepGlorp AI\`, creates a Start-menu shortcut (and an optional
Desktop shortcut) launching the **windowed** app (`the-one.exe app`), and ships
the CLI in the same multi-call exe (`the-one.exe chat|serve|doctor|version` run
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

The installer/shortcut icon is
[`installer-assets/the-one.ico`](./installer-assets/the-one.ico) — a byte-for-byte
copy of `the_one/interfaces/web/static/brand/favicon.ico` (the only `.ico` in the
repo; 16/32/48 multi-size). Copying it here keeps the installer out of the app's
live static tree and localizes a future icon swap. The `.iss` installs it into
`{app}` so the shortcut and Add/Remove-Programs entry have a durable icon target
(the frozen exe carries no embedded icon resource — the Leg-2 `.spec` omits
`EXE(icon=)`).

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

## CI packaged-smoke (`windows-packaged-smoke` job)

The `windows-packaged-smoke` job in
[`.github/workflows/test.yml`](../../.github/workflows/test.yml) is the
load-bearing verification of this flight: it freezes the one-dir on a
`windows-2022` runner and **proves the DD2 child-spawn fix against the real
frozen binary** — the spawn-fix's only true apparatus (a checkout interpreter
can't exercise a PyInstaller bundle). It runs the freeze + smoke **before**
building the installer, so a red smoke never ships an unproven build, then builds
and uploads the Inno installer as the `the-one-windows-installer` artifact.

What it proves (against `dist/the-one/the-one.exe`, not the checkout):

- **(a) frozen `doctor`** exits 0 and prints both `child spawn: OK` and
  `RESULT: PASS` — `clean_subprocess_env` + PATH augmentation + the
  `resolve_python` interpreter gate all work on the packaged binary.
- **(b) frozen `serve`** answers `http://127.0.0.1:8484/api/info` with HTTP 200
  and `version == the_one.__version__`, polled with an `httpx` probe (the same
  library the product polls with — no Git-Bash-`curl` assumption).
- **(c) single-instance input**: the Flight-4 `_select_port` probe (run from
  source) sees the frozen instance as ours, confirming a second `app` launch
  would start no second server.

**Reading a failure — the Divert signal.** A red **(a) frozen doctor** step
means the packaged spawn-fix regressed: `clean_subprocess_env` / PATH / the
frozen `resolve_python` gate no longer work in the bundle. That is the flight's
**Divert** trigger (the whole-mission spawn gate) — escalate rather than patch
around it. A build-step failure naming a missing `pywinpty` `_winpty.pyd` /
`winpty.dll` is the same class of signal (see the pywinpty note below).

The job is **path-filtered** (inline git-diff, like the `browser` job) to
`packaging/**`, the runtime seam files, the smoke's pass-criteria files
(`__init__.py`, `config.py`, `interfaces/web/app.py`) and `pyproject.toml`, so
most PRs don't pay the freeze cost. **Adding a new seam file means adding it to
that grep** — otherwise the smoke won't run on the PR that changes it. Because
GitHub Actions cannot run on the Linux dev host, the **observed green run lands
when the flight's PR opens** and CI executes on `windows-2022`.

## Notes

- **One-dir, not one-file** (DD1): one-file is forbidden — it hurts the DD2
  child-spawn fix and triggers Windows AV heuristics.
- **Version**: the spec names the bundle from `the_one.__version__` (`0.2.0`).
  The stale `pyproject.toml` `version = "0.1.0"` is a known discrepancy left for
  a future maintenance reconcile — do not rely on the pyproject string here.
- **PyNaCl / Discord voice**: excluded (`excludes=["nacl"]`) — voice is unused.
- **pywinpty binaries**: if a build warns that the `_winpty` `.pyd` or
  `winpty.dll` is missing, add an explicit `--add-binary` / `binaries` tuple in
  the spec pointing at the installed `pywinpty` package.
