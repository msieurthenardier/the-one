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
only; the build-and-launch proof on windows-2022 is performed by Leg 4's CI
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
# Leg-4 build note: if the build warns that the _winpty .pyd or winpty.dll is
# missing from the bundle, fall back to an explicit --add-binary / binaries
# tuple pointing at the installed pywinpty package (the flight's DD7 Divert
# criterion). collect_dynamic_libs returns [] off-Windows / when pywinpty is
# absent, which is why this spec cannot be freeze-validated on Linux.
winpty_bins = collect_dynamic_libs("winpty")

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
    *uvicorn_hidden,
    *mcp_hidden,
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


a = Analysis(
    ["frozen_entry.py"],
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

pyz = PYZ(a.pure)

# Single multi-call EXE (DD6 pin): ONE exe, `the-one.exe`, dispatches every
# subcommand (chat|serve|app|version|doctor) via cli_entry() on argv. The Leg-3
# Start-menu shortcut invokes `the-one.exe app`; the CLI is the same binary.
# No second exe. console=True keeps a console for the CLI subcommands; the
# windowed `app` subcommand opens its own webview regardless.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # one-dir: binaries live in the COLLECT dir
    name=APP_NAME,  # the-one.exe  (the-one v{APP_VERSION})
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
    # version= intentionally omitted — see module docstring (a bare string here
    # breaks the build; it needs a VSVersionInfo resource, out of scope).
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,  # dist/the-one/  (the-one v{APP_VERSION} one-dir bundle)
)
