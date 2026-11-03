# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-dir spec for the-one on Windows (M15 F5 L2, DD1).

This is the checked-in build *contract*: hidden-imports, native-binary
collection, and the web static-asset tree are versioned here rather than passed
as ad-hoc CLI flags, so the freeze recipe is reviewable and reproducible.

Build (native Windows only; see packaging/windows/README.md): use the recipe,
packaging\\windows\\build.ps1, which stages the source (packaging/stage.py --target windows),
sets M32_STAGE and runs

    pyinstaller --noconfirm --clean --workpath <Out>\\work-<V> --distpath <Out>\\dist-<V> \\
        packaging\\windows\\the-one.spec

Output one-dir: <distpath>\\the-one\\the-one.exe  (DD1 one-dir, NOT one-file).

Environment:
    M32_STAGE   the staged copy of the_one/ (packaging/stage.py output). REQUIRED. The project
                is never installed (no `pip install -e .`): only this copy is importable by the
                freeze, so the bundle carries the staged version and nothing unpatched.

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

# The staged copy goes at the FRONT of sys.path before any collect_* call below: those helpers
# import the_one in-process, and collect_data_files("the_one") reads the package directory, so
# both must see the staged copy. The repo root is never put on sys.path. packaging/ is added only
# for `import render` (the product names). SPECPATH is the dir containing this spec
# (packaging/windows/), so Analysis(["frozen_entry.py"]) and icon= below keep resolving from it.
_STAGE = os.environ.get("M32_STAGE")
if not _STAGE or not os.path.isdir(os.path.join(_STAGE, "the_one")):
    raise SystemExit("the-one.spec: set M32_STAGE to a stage.py output directory")
_STAGE = os.path.abspath(_STAGE)
_PACKAGING = os.path.abspath(os.path.join(SPECPATH, os.pardir))  # noqa: F821
_REPO = os.path.abspath(os.path.join(_PACKAGING, os.pardir))  # read-only: product.toml lives here
sys.path.insert(0, _PACKAGING)
sys.path.insert(0, _STAGE)

from PyInstaller.utils.hooks import (  # noqa: E402  (must follow the sys.path inserts)
    collect_all,
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

import render  # noqa: E402  (packaging/render.py)
from the_one import __version__  # noqa: E402  (the staged copy, version rewritten by stage.py)

# Runtime source of truth: the STAGED the_one/__init__.py (stage.py wrote the build's version).
# Used for the EXE / dist-dir name and the version comment below — NOT passed to
# EXE(version=...): that keyword wants a VSVersionInfo resource, and a bare
# string breaks the build (see module docstring).
APP_VERSION = __version__  # "0.2.0"
# The two exe names come from packaging/product.toml [windows] (one source with the .iss).
PRODUCT = render.load(_REPO, {"version": APP_VERSION})
APP_NAME = PRODUCT["cli_executable"]  # the-one.exe / dist/the-one/  (the-one v{APP_VERSION})
GUI_NAME = PRODUCT["gui_executable"]  # the-one-app.exe (windowed)

# Surface the version in the PyInstaller build log so the bundle's provenance is
# visible (and so APP_VERSION is load-bearing, not just a comment).
print(f"[the-one.spec] freezing {APP_NAME} v{APP_VERSION} from {_STAGE} (one-dir, Windows)")

# ── DD7 collection contract ──────────────────────────────────────────────────
# uvicorn: collect_all pulls its loops.auto / protocols.*.auto string-imports
# plus the optional uvloop/httptools/websockets accelerators ([standard] extra).
uvicorn_datas, uvicorn_bins, uvicorn_hidden = collect_all("uvicorn")

# mcp (model-context-protocol SDK, pinned 2.3.0): submodules cover its
# dynamically-dispatched transports/handlers.
#
# Exclude the optional `mcp.cli` subpackage: its __init__ imports `typer` (the
# mcp[cli] extra), which the app does NOT use and which is not installed. Without
# the filter, PyInstaller's isolated submodule walk imports mcp.cli, hits
# ModuleNotFoundError: typer, and aborts the entire freeze. Likewise exclude
# `mcp.server.fastmcp`: in 2.x it is a stub module that raises on import (the
# 1.x FastMCP API moved to MCPServer), so the walk would hit that error.
# on_error="warn" is a belt-and-suspenders so any OTHER optional mcp submodule
# that fails to import only warns instead of killing the build.
mcp_hidden = collect_submodules(
    "mcp",
    filter=lambda name: not (name.startswith("mcp.cli") or name.startswith("mcp.server.fastmcp")),
    on_error="warn",
)

# mcp 2.x's runtime closure (M29 F1 L2). The SDK now splits its wire types and
# HTTP stack into separate distributions that its dispatch reaches by import
# paths PyInstaller's static walk can miss, so each is collected whole:
#   * mcp_types: the protocol model package the SDK re-exports as mcp.types;
#   * httpx2 / httpcore2: the SDK's HTTP client stack (renamed forks, distinct
#     from the app's own httpx);
#   * truststore: the OS trust-store SSL context the SDK builds for TLS;
#   * opentelemetry: the tracing API the SDK instruments itself with.
# httpx2/__version__.py and httpcore2/__init__.py call
# importlib.metadata.version() at import time, so their dist-info is copied into
# the bundle (copy_metadata below); without it the import raises PackageNotFound.
# The frozen `the-one.exe doctor` `mcp sdk` gate is the judge.
mcp_types_hidden = collect_submodules("mcp_types", on_error="warn")
httpx2_hidden = collect_submodules("httpx2", on_error="warn")
httpcore2_hidden = collect_submodules("httpcore2", on_error="warn")
truststore_hidden = collect_submodules("truststore", on_error="warn")
opentelemetry_hidden = collect_submodules("opentelemetry", on_error="warn")
mcp_metadata = [*copy_metadata("httpx2"), *copy_metadata("httpcore2")]

# pywinpty (Windows ConPTY backend): collect the native binaries — the
# _winpty ABI .pyd and its sibling winpty.dll.  NOTE: collect_dynamic_libs only
# grabs binaries, NOT the pure-Python `winpty` submodules, so the import name is
# added to hiddenimports below as well.
# Build note: if the build warns that the _winpty .pyd or winpty.dll is missing
# from the bundle, fall back to an explicit --add-binary / binaries tuple pointing
# at the installed pywinpty package (the flight's DD7 Divert criterion).
# collect_dynamic_libs returns [] off-Windows / when pywinpty is absent, which is
# why this spec cannot be freeze-validated on Linux.
# Squawk 0162: collect_dynamic_libs' default patterns match only *.dll/*.pyd, so
# pywinpty >= 3's helper executables were left out of the bundle. They must sit
# in the same winpty/ dir as conpty.dll: the bundled conpty.dll spawns
# OpenConsole.exe from its own directory (without it every PTY child dies at
# start, "session not active"), and winpty-agent.exe is the agent for the WinPTY
# fallback backend. Hence the explicit "*.exe" pattern.
winpty_bins = collect_dynamic_libs("winpty", search_patterns=["*.dll", "*.pyd", "*.exe"])

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

# Model-catalog seed (M16 F05 DD6): the_one/llm/data/model_catalog.json is the
# bundled offline-safe context-window seed, loaded at runtime via
# importlib.resources.files("the_one.llm")/"data"/"model_catalog.json"
# (the_one/llm/model_catalog.py:_load_seed). collect_submodules above ships the
# llm *modules* but NOT this data file, and the package-data glob in
# pyproject.toml only covers wheels/sdist — not this PyInstaller path. Without
# this collection the frozen build has no seed: _load_seed() fails, the catalog
# resolves empty (fail-open), and every model silently reports the class default
# (200k for all Claude incl. the 1M default, 128k for OpenAI). Same packaging-
# survival class as the provider tree-shake above, one layer down at the data file.
seed_datas = collect_data_files("the_one", includes=["llm/data/*.json"])

# Bundled float16 embedding model (M24 F01 L02, DD-1/DD-2): the five-file
# `potion-retrieval-32M` directory under the_one/embeddings/data/ is the
# mission's default embedding backend, loaded at runtime via
# importlib.resources.files("the_one.embeddings")/"data"/"potion-retrieval-32M"
# (the_one/diagnostics.py:_probe_embedding_model). Exactly the same two-sided
# requirement as the model-catalog seed above: the pyproject.toml package-data
# glob covers the wheel/sdist path and NOT this one, and collect_submodules
# ships the `the_one.embeddings` module but none of its data. Without this
# collection the frozen bundle has no weights at all.
#
# collect_data_files IS the right mechanism here, unlike the Flight 1
# native-loadable-extension case below: its unconditional exclusion of
# importlib.machinery.all_suffixes() blocks only importable extension
# suffixes (.so/.pyd/.py), and every file in this directory is .json,
# .safetensors or .md. The **/* glob must cover all
# five files — model2vec's loader validates the layout, so a partial glob fails
# at load rather than degrading silently.
#
# Failure mode if this is dropped: the `embedding model` doctor gate FAILS the
# build (it is unconditional per DD-7), which is the point — a tree-shaken model
# directory would otherwise be a silent fetch from the Hugging Face hub on any
# networked machine. The probe asserts the packaged path exists and sets
# HF_HUB_OFFLINE=1 before loading precisely so that cannot happen.
#
# NO hook and NO hiddenimports entry is needed for the native payloads this
# pulls in. Verified against a real one-dir build: `tokenizers.abi3.so`,
# `_safetensors_rust.abi3.so` and hf-xet's extension are ordinary importable
# extension modules, so PyInstaller's module graph collects them unaided.
# pyinstaller-hooks-contrib ships no hook for tokenizers, safetensors,
# huggingface_hub or model2vec — do not go looking for one.
embedding_datas = collect_data_files("the_one", includes=["embeddings/data/**/*"])

# A native loadable-extension collection lesson from Flight 1 (a vector-store
# candidate removed from the closure in Flight 2 Leg 6): `collect_data_files`
# silently drops `.so` files (it excludes every
# `importlib.machinery.all_suffixes()` entry), so a native library that is
# data to the module graph — nothing imports it, it is opened by path at
# runtime — needs `collect_dynamic_libs` with explicit `search_patterns`, not
# `collect_data_files`, or the frozen bundle silently ships nothing on Linux
# while appearing to work elsewhere.
#
# usearch.compiled and numkong._numkong need NO spec entry — both are ordinary
# importable extension modules, so PyInstaller's module graph collects them with
# no configuration (verified against a no-hook one-dir build).
#
# ── numkong / SIMD on Windows: do NOT go hunting here ────────────────────────
# The frozen Windows doctor reports `numkong=no, simd=serial` while Linux
# reports `numkong=yes, simd=haswell`. That asymmetry is NOT a packaging defect
# and no spec entry, PyInstaller hook, add_dll_directory, or binaries tuple can
# change it. Evidence, taken from the published wheels themselves:
#
#   * usearch's Linux `compiled.*.so` has UNDEFINED `nk_*` symbols (nk_capabilities,
#     nk_find_kernel_punned, ...), resolved from the numkong `.so` that
#     usearch/__init__.py loads with RTLD_GLOBAL, and carries the full ISA name
#     table (haswell/skylake/icelake/genoa/...).
#   * usearch's `win_amd64` `compiled.cp311-win_amd64.pyd` has ZERO `nk_`
#     references, no import-table entry for `_numkong*.pyd`, an EMPTY delay-import
#     directory, no GetProcAddress/LoadLibrary in its KERNEL32 imports, and
#     `serial` as its only ISA name string. It has no code path that can call
#     numkong. Checked across 2.16.0, 2.20.0, 2.25.0, 2.26.0 and 2.26.2 (latest):
#     every Windows wheel is built the same way.
#   * numkong's own `win_amd64` wheel is fine — it exports the whole `nk_*`
#     surface and ships all ISA kernels; it is simply not linked to.
#   * macOS is NOT affected: the `macosx_11_0_arm64` wheel carries `nk_*`
#     references and neon/haswell/skylake ISA names like Linux. Windows is the
#     lone outlier of the three platforms this mission targets.
#
# `USES_NUMKONG` is therefore compile-time, and 0 in every published Windows
# usearch wheel. Changing it would mean building usearch from source on Windows,
# which is far outside this leg. The doctor's usearch line says so explicitly
# (the_one/diagnostics.py:_numkong_extension_state) so the next reader does not
# repeat the search. numkong stays in the bundle regardless: usearch/__init__.py
# imports it unconditionally, so removing it would only trade dead weight for a
# swallowed ImportError.
# cryptography and pywebview (->pythonnet/clr_loader: Python.Runtime.dll,
# WebBrowserInterop) ship maintained PyInstaller contrib hooks — let those
# hooks collect their datas/binaries/hiddenimports rather than hand-rolling
# them. Keeping PyInstaller current is the contract; only hand-roll if a build
# proves a hook gap.

# IANA zone data and host-zone detection (M28 F1 L1, DD8/DD9). Windows ships no
# zone database, so the operator time-zone setting reads the `tzdata` package:
#   * the zone files and tzdata.zi are reached through importlib.resources by
#     string (`tzdata.zoneinfo.America`, "Los_Angeles"), which PyInstaller's
#     module graph never sees, so the data must be collected explicitly;
#   * collect_data_files skips .py files, and tzdata's zoneinfo directories are
#     packages (each has an __init__.py that importlib.resources needs), so
#     collect_submodules("tzdata") is added to the hidden imports as well;
#   * tzlocal picks its backend by platform at import (tzlocal.win32 on Windows,
#     imported lazily), so its submodules are collected too.
# The frozen `the-one.exe doctor` `time zones` gate is the judge: it loads a
# zone straight from the package and checks the exact formatted strings.
tzdata_datas = collect_data_files("tzdata")
tzdata_hidden = collect_submodules("tzdata")
tzlocal_hidden = collect_submodules("tzlocal")

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
    # M24 F01 L02 (updated M24 F02 L03) — `the_one.embeddings` IS now
    # imported as a module (`the_one.diagnostics` and `the_one.knowledge.settings`
    # both import from `the_one.embeddings.local` at module load time), so
    # PyInstaller's static analysis DOES see this package today. The entry
    # stays anyway: `the_one.embeddings.local.resolve_model_dir` still
    # reaches the packaged weights only by NAME, via
    # importlib.resources.files("the_one.embeddings").joinpath("data", ...) —
    # a string argument PyInstaller's import-graph walk cannot follow.
    # Without this entry the package's `data/` payload would still ship
    # (embedding_datas above ships it independently) but a build that ever
    # dropped the module import above would silently tree-shake the package
    # itself back out, so the explicit entry remains the load-bearing one.
    "the_one.embeddings",
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
    # LLM providers are loaded LAZILY via a string __import__ in
    # the_one/llm/registry.py:_try_load_builtin (e.g.
    # __import__("the_one.llm.ollama_provider")). PyInstaller's static import
    # analysis cannot see those string references, so without this every
    # provider module is tree-shaken out of the bundle — get_provider() then
    # raises ModuleNotFoundError at agent-create time, the WS handler crashes,
    # and the chat silently drops (the M16 frozen-provider regression). Declare
    # the whole the_one.llm subpackage so all current AND future providers ship.
    *collect_submodules("the_one.llm"),
    *uvicorn_hidden,
    *mcp_hidden,
    *mcp_types_hidden,
    *httpx2_hidden,
    *httpcore2_hidden,
    *truststore_hidden,
    *opentelemetry_hidden,
    *pystray_hidden,
    *tzdata_hidden,
    *tzlocal_hidden,
]

datas = [
    *static_datas,
    *seed_datas,
    *embedding_datas,
    *tzdata_datas,
    *mcp_metadata,
    *uvicorn_datas,
]

binaries = [
    *uvicorn_bins,
    *winpty_bins,
]

# Mission 23 Flight 1 (backend-removal leg): the nacl exclusion existed
# only for discord.py's optional voice support; discord.py itself is
# gone from the dependency closure now, so there was nothing left to
# exclude for a while — but see the hf_xet entry below (M24 F02 L06).
#
# Squawk 0049 / M24 F02 L06: `hf-xet` is excluded from the dependency
# closure itself via `[tool.uv] exclude-dependencies` (pyproject.toml),
# but `huggingface_hub` still carries a guarded `import hf_xet` in its
# download path — if the module happens to be importable in the BUILD
# environment for any reason, PyInstaller follows that import and bundles
# it regardless of what the closure says. Concourse build 606657 proved
# this isn't hypothetical: the Windows worker runs tasks uncontainerised,
# `C:\Python312` site-packages persist across builds, and a stale
# `hf_xet` copy from an earlier build was importable at freeze time —
# `hf_xet.pyd` shipped in the bundle and the installer stayed at the
# pre-squawk-0049 baseline size even though the doctor gate (which never
# imports `hf_xet`) still passed. Excluding it here makes the bundle
# correct regardless of what else is sitting in the build environment.
excludes = ["hf_xet"]


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
    pathex=[_STAGE],
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
    (a_cli, APP_NAME, APP_NAME),
    (a_gui, GUI_NAME, GUI_NAME),
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
    name=GUI_NAME,  # the-one-app.exe  (windowed — Start-menu shortcut)
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
    # UPX-packing a native library is a known load-failure source. No toolchain
    # in either CI path currently provides UPX, so `upx=True` is a no-op today
    # and these entries are free insurance against a future UPX install rather
    # than a live fix. Covers usearch's and numkong's native extension modules
    # (M24 F01 L01, the surviving vector store per M24 F02 L06 DD-9) plus the
    # model2vec closure's native payloads (M24 F01 L02). `hf-xet` was excluded
    # from the dependency closure entirely in Leg 6 (squawk 0049), so it no
    # longer ships and needs no entry here.
    upx_exclude=[
        "compiled*",  # usearch native core (compiled.cp311-win_amd64.pyd)
        "_numkong*",  # numkong native core (_numkong.cp311-win_amd64.pyd)
        # M24 F01 L02 — native payloads of the model2vec closure. Same rule as
        # the two above: UPX-compressing a Rust/pybind extension is the
        # classic source of an import that works unpacked and dies packed.
        "tokenizers*",  # HF tokenizers Rust core (tokenizers.abi3.so / .pyd)
        "_safetensors_rust*",  # safetensors Rust core
    ],
    name=APP_NAME,  # dist/the-one/  (the-one v{APP_VERSION} one-dir bundle)
)
