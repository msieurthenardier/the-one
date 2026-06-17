# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-dir spec for the-one on Windows (M15 F5 L2, DD1).

This is the checked-in build *contract*: hidden-imports, native-binary
collection, and the web static-asset tree are versioned here rather than passed
as ad-hoc CLI flags, so the freeze recipe is reviewable and reproducible.

Build (native Windows only — see packaging/windows/README.md):

    pip install -e ".[gui,all-llms]"
    pip install pyinstaller
    pyinstaller --noconfirm packaging/windows/the-one.spec

Output one-dir: dist/the-one/the-one.exe  (DD1 one-dir, NOT one-file).

IMPORTANT — build host: PyInstaller must run on **native Windows** (not WSL2).
The load-bearing native deps (pywinpty, pywebview->pythonnet) only install on
Windows, and the collect_* helpers below import those packages at *build time*.
On this Linux host the spec is authored and statically validated (py_compile)
only; the build-and-launch proof on windows-2022 is performed by the CI
packaged-smoke, which consumes this spec.

Version: the dist-dir / EXE name and the comments here read the runtime source
of truth — the_one.__version__ ("0.2.0") — NOT the stale pyproject string
("0.1.0"). NOTE: __version__ is used for naming/comments only. It is deliberately
NOT passed to EXE(version=...): that keyword expects a VSVersionInfo resource
file/object, and a bare string is treated as a filename and breaks the build.
A VSVersionInfo resource is optional polish, out of scope for this unsigned leg.
"""

import os
import sys

# Put the repo root on sys.path BEFORE importing the_one — this import runs at
# spec-load time, before Analysis(pathex=...) takes effect. SPECPATH is the dir
# containing this spec (packaging/windows/); the repo root is two parents up.
_REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir, os.pardir))  # noqa: F821
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from PyInstaller.utils.hooks import (  # noqa: E402  (must follow the sys.path insert)
    collect_all,
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

from the_one import __version__  # noqa: E402  (must follow the sys.path insert)

# Runtime source of truth (the_one/__init__.py), NOT the stale pyproject 0.1.0.
# Used for the EXE / dist-dir name and the version comment below — NOT passed to
# EXE(version=...): that keyword wants a VSVersionInfo resource, and a bare
# string breaks the build (see module docstring).
APP_VERSION = __version__  # "0.2.0"
APP_NAME = "the-one"  # the-one.exe / dist/the-one/  (the-one v{APP_VERSION})

# Surface the version in the PyInstaller build log so the bundle's provenance is
# visible (and so APP_VERSION is load-bearing, not just a comment).
print(f"[the-one.spec] freezing {APP_NAME} v{APP_VERSION} (one-dir, Windows)")

# ── DD7 collection contract ──────────────────────────────────────────────────
# uvicorn: collect_all pulls its loops.auto / protocols.*.auto string-imports
# plus the optional uvloop/httptools/websockets accelerators ([standard] extra).
uvicorn_datas, uvicorn_bins, uvicorn_hidden = collect_all("uvicorn")

# mcp (model-context-protocol SDK, pinned 1.27.0): submodules cover its
# dynamically-dispatched transports/handlers.
#
# Exclude the optional `mcp.cli` subpackage: its __init__ imports `typer` (the
# mcp[cli] extra), which the app does NOT use and which is not installed. Without
# the filter, PyInstaller's isolated submodule walk imports mcp.cli, hits
# ModuleNotFoundError: typer, and aborts the entire freeze. on_error="warn" is a
# belt-and-suspenders so any OTHER optional mcp submodule that fails to import
# only warns instead of killing the build.
mcp_hidden = collect_submodules(
    "mcp",
    filter=lambda name: not name.startswith("mcp.cli"),
    on_error="warn",
)

# pywinpty (Windows ConPTY backend): collect the native binaries — the
# _winpty ABI .pyd and its sibling winpty.dll.  NOTE: collect_dynamic_libs only
# grabs binaries, NOT the pure-Python `winpty` submodules, so the import name is
# added to hiddenimports below as well.
# Build note: if the build warns that the _winpty .pyd or winpty.dll is missing
# from the bundle, fall back to an explicit --add-binary / binaries tuple pointing
# at the installed pywinpty package (the flight's DD7 Divert criterion).
# collect_dynamic_libs returns [] off-Windows / when pywinpty is absent, which is
# why this spec cannot be freeze-validated on Linux.
winpty_bins = collect_dynamic_libs("winpty")

# pystray (system-tray icon): collect all submodules but tolerate import
# failures for platform-only backends.  pystray ships backend subpackages
# (_xorg, _gtk, _appindicator, _darwin) that import Linux/macOS-only deps
# (Xlib, gi, AppKit) at module scope.  Without on_error="warn" the collect
# walk imports those backends on Windows, hits ModuleNotFoundError, and aborts
# the entire freeze — the same failure mode handled for mcp.cli at line 75.
pystray_hidden = collect_submodules("pystray", on_error="warn")

# Pillow (PIL): the pyinstaller-hooks-contrib PIL hook handles _imaging +
# plugins.  No explicit collect_submodules("PIL") is needed here — keeping
# PyInstaller and pyinstaller-hooks-contrib current is the contract.  Add an
# explicit collect only if a frozen build proves a plugin is missing.

# Web static assets (DD8): the 78-file tree under
# the_one/interfaces/web/static must land at the same package-relative path in
# the bundle so the frozen STATIC_DIR = Path(__file__).parent / "static"
# resolves under _MEIPASS. The **/* glob mirrors pyproject.toml package-data and
# recurses through js/areas/admin/**, fonts/, brand/, css/ — all files, not just
# index.html.
static_datas = collect_data_files(
    "the_one", includes=["interfaces/web/static/**/*"]
)

# cryptography and pywebview (->pythonnet/clr_loader: Python.Runtime.dll,
# WebBrowserInterop) ship maintained PyInstaller contrib hooks — let those
# hooks collect their datas/binaries/hiddenimports rather than hand-rolling
# them. Keeping PyInstaller current is the contract; only hand-roll if a build
# proves a hook gap.

hiddenimports = [
    # winpty pure-Python submodules — binaries come from collect_dynamic_libs
    # above; the import name itself must be declared explicitly.
    "winpty",
    # Lazy app subpackages: cli_entry() imports these inside each branch
    # (string-ish / runtime imports PyInstaller's static analysis can miss).
    "the_one.interfaces.cli",
    "the_one.interfaces.web.app",
    "the_one.interfaces.app",
    "the_one.diagnostics",
    # pywebview: imported lazily inside `the-one app`.
    "webview",
    # aiosqlite + the stdlib sqlite3 C-extension backing it.
    "aiosqlite",
    "sqlite3",
    # pystray Windows backend — the collect_submodules walk covers the package
    # tree but a redundant explicit entry ensures the win32 backend is present.
    "pystray._win32",
    "pystray._util.win32",
    # Desktop subpackage: tray.py, notice.py, and window_state.py are imported
    # LAZILY inside function bodies (shell.py / _on_closing / _on_quit), so
    # PyInstaller's static analysis does NOT reach them from the top-level
    # import of the_one.interfaces.web.app. Without this, a frozen build would
    # silently omit those modules → guaranteed `desktop shell: RESULT: FAIL`
    # from `the-one doctor` on first launch. collect_submodules picks up all
    # current and future members of the desktop package in one declaration.
    *collect_submodules("the_one.interfaces.desktop"),
    *uvicorn_hidden,
    *mcp_hidden,
    *pystray_hidden,
]

datas = [
    *static_datas,
    *uvicorn_datas,
]

binaries = [
    *uvicorn_bins,
    *winpty_bins,
]

# PyNaCl / discord voice: discord.py voice support is unused by this app, so
# nacl is force-EXCLUDED. This both silences PyInstaller's "missing module"
# warning for the optional voice path and trims the bundle — preferred over
# collecting a dependency we never call.
excludes = ["nacl"]


# TWO EXEs in one one-dir bundle (operator-HAT fix). DD6 originally pinned a single
# multi-call exe with console=True, but a console-subsystem exe pops a blank console
# window when the Start-menu shortcut launches the GUI (`the-one.exe app`). Fix:
#   * the-one.exe      — console=True  — the CLI (chat|serve|doctor|version) + the CI
#                        packaged-smoke (reads its stdout). Behavior unchanged.
#   * the-one-app.exe  — console=False — the WINDOWED launcher the shortcut uses;
#                        opens the webview with NO console window. Always runs `app`.
# Both share the same collection inputs; MERGE de-dupes the shared payload so the
# ~38 MB of deps isn't bundled twice in the one-dir.
_analysis_kwargs = dict(
    pathex=[_REPO_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

a_cli = Analysis(["frozen_entry.py"], **_analysis_kwargs)
a_gui = Analysis(["frozen_entry_gui.py"], **_analysis_kwargs)

# De-dupe shared binaries/datas/pyz across the two exes: a_cli owns the shared
# files; a_gui references them (so the one-dir carries one copy).
MERGE(  # noqa: F821  (PyInstaller spec global)
    (a_cli, "the-one", "the-one"),
    (a_gui, "the-one-app", "the-one-app"),
)

pyz_cli = PYZ(a_cli.pure)
pyz_gui = PYZ(a_gui.pure)

# version= intentionally omitted on both — a bare string breaks the build (it needs
# a VSVersionInfo resource, out of scope; see module docstring).
exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,  # one-dir: binaries live in the COLLECT dir
    name=APP_NAME,  # the-one.exe  (console — CLI + CI smoke)
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name=f"{APP_NAME}-app",  # the-one-app.exe  (windowed — Start-menu shortcut)
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # windowed: NO console window when launching the GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='installer-assets/the-one.ico',  # DD5: brand icon embedded in windowed exe (window/taskbar/Alt-Tab)
)

coll = COLLECT(
    exe_cli,
    exe_gui,
    a_cli.binaries,
    a_cli.datas,
    a_gui.binaries,
    a_gui.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,  # dist/the-one/  (the-one v{APP_VERSION} one-dir bundle)
)
