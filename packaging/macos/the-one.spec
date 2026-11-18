# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-dir spec for GleepGlorp AI on macOS (Mission 32 Flight 3).

Built by build.sh (macos-packages.yml). Same collection contract as ../linux/the-one.spec
(which borrowed it from ../windows/the-one.spec), with the Linux-only parts removed:

* no gi / GTK: pywebview uses its Cocoa backend (pyobjc); there is no tray (the app lives in
  the Dock, DD2), so pystray is not collected at all;
* no ``excludes.txt`` and no ``rthook_host_gtk.py``: those keep the host GTK stack out of a
  Linux bundle. macOS has nothing equivalent to leave out, the bundle carries everything;
* ``BUNDLE`` wraps the one-dir ``COLLECT`` as ``GleepGlorp AI.app``.

Environment:
    M32_STAGE   the staged copy of the_one/ (packaging/stage.py output). REQUIRED.
    M32_ICNS    path to the .icns for the bundle (build.sh generates it). Optional.
    M32_PRODUCT_JSON
                the rendered product values (``render.py --json --set version=V``, written
                by build.sh): bundle name, id, versions, minimum macOS. REQUIRED.

Like the Linux spec, this never puts the repo root on sys.path: only the staged copy is
visible to the freeze, so the bundle carries the staged version and nothing unpatched.
"""

import json
import os
import sys

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

_STAGE = os.environ.get("M32_STAGE")
if not _STAGE or not os.path.isdir(os.path.join(_STAGE, "the_one")):
    raise SystemExit("the-one.spec: set M32_STAGE to a stage.py output directory")
_STAGE = os.path.abspath(_STAGE)
_ICNS = os.environ.get("M32_ICNS") or None
_PRODUCT_JSON = os.environ.get("M32_PRODUCT_JSON")
if not _PRODUCT_JSON or not os.path.isfile(_PRODUCT_JSON):
    raise SystemExit("the-one.spec: set M32_PRODUCT_JSON to the render.py --json output")
with open(_PRODUCT_JSON, encoding="utf-8") as _fh:
    PRODUCT = json.load(_fh)

# The collect_* helpers below import the_one in-process; make that the staged copy.
sys.path.insert(0, _STAGE)
from the_one import __version__ as APP_VERSION  # noqa: E402  (staged copy, version rewritten)

_HERE = SPECPATH  # noqa: F821  (PyInstaller spec global)
sys.path.insert(0, _HERE)
from info_plist import info_plist  # noqa: E402  (packaging/macos/info_plist.py)

# macOS-only entry: no arguments (Finder/Dock) means `app`; arguments run the CLI.
_ENTRY = os.path.join(_HERE, "frozen_entry_mac.py")

print(f"[the-one.spec] freezing {APP_VERSION} from {_STAGE} for macOS")

# ── Collection contract (from the Windows/Linux specs) ──────────────────────
uvicorn_datas, uvicorn_bins, uvicorn_hidden = collect_all("uvicorn")
mcp_hidden = collect_submodules(
    "mcp",
    filter=lambda name: not (name.startswith("mcp.cli") or name.startswith("mcp.server.fastmcp")),
    on_error="warn",
)
mcp_types_hidden = collect_submodules("mcp_types", on_error="warn")
httpx2_hidden = collect_submodules("httpx2", on_error="warn")
httpcore2_hidden = collect_submodules("httpcore2", on_error="warn")
truststore_hidden = collect_submodules("truststore", on_error="warn")
opentelemetry_hidden = collect_submodules("opentelemetry", on_error="warn")
mcp_metadata = [*copy_metadata("httpx2"), *copy_metadata("httpcore2")]

# macOS only: the pyobjc packages pywebview's Cocoa backend imports by
# name at runtime (guilib / backend() choose them dynamically, so the static walk can miss
# them). The five locked pyobjc-* distributions provide objc, Foundation, AppKit, WebKit,
# Quartz, Security and PyObjCTools.
pyobjc_hidden = []
for _pkg in ("objc", "Foundation", "AppKit", "WebKit", "Quartz", "Security", "PyObjCTools"):
    pyobjc_hidden += collect_submodules(_pkg, on_error="warn")

static_datas = collect_data_files("the_one", includes=["interfaces/web/static/**/*"])
seed_datas = collect_data_files("the_one", includes=["llm/data/*.json"])
embedding_datas = collect_data_files("the_one", includes=["embeddings/data/**/*"])
# Chart-image fonts (M35 F3 L1): the bundled Geist TTFs and their licence.
font_datas = collect_data_files("the_one", includes=["visuals/fonts/*"])
# GleepGlorp's app guide (M36 F1 L07): the help topics get_app_guide reads.
guide_datas = collect_data_files("the_one", includes=["gleepglorp/guide/*.md"])
tzdata_datas = collect_data_files("tzdata")
tzdata_hidden = collect_submodules("tzdata")
tzlocal_hidden = collect_submodules("tzlocal")

hiddenimports = [
    "the_one.interfaces.cli",
    "the_one.interfaces.web.app",
    "the_one.interfaces.app",
    "the_one.diagnostics",
    "webview",
    "aiosqlite",
    "sqlite3",
    "the_one.embeddings",
    *collect_submodules("the_one.interfaces.desktop"),
    *collect_submodules("the_one.llm"),
    *uvicorn_hidden,
    *mcp_hidden,
    *mcp_types_hidden,
    *httpx2_hidden,
    *httpcore2_hidden,
    *truststore_hidden,
    *opentelemetry_hidden,
    *pyobjc_hidden,
    *tzdata_hidden,
    *tzlocal_hidden,
    # macOS window: the Cocoa backend of pywebview (no tray, DD2).
    "webview.platforms.cocoa",
]

datas = [
    *static_datas,
    *seed_datas,
    *embedding_datas,
    *font_datas,
    *guide_datas,
    *tzdata_datas,
    *mcp_metadata,
    *uvicorn_datas,
]

# hf_xet: same stale-build-env guard as the Windows and Linux specs.
excludes = ["hf_xet"]

a = Analysis(  # noqa: F821
    [_ENTRY],
    pathex=[_STAGE],
    binaries=[*uvicorn_bins],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=PRODUCT["bundle_executable"],
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # macOS: console=False selects the windowed bootloader, so a Finder launch shows no
    # Terminal. The same executable still runs the CLI from a shell (frozen_entry_mac.py),
    # and its stdout still reaches the terminal that started it.
    console=False,
    # macOS: leave argv alone. argv_emulation would turn Finder "open file" events into
    # argv entries, which this app has no use for and which would defeat the empty-argv test.
    argv_emulation=False,
    # macOS: arm64 only, the hosted runner's native arch (the spike measures one slice).
    target_arch=None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="the-one",
)

app = BUNDLE(  # noqa: F821
    coll,
    # macOS: the .app folder is the install unit; the formal name has a space, which
    # every probe and script must quote.
    name=PRODUCT["bundle_name"] + ".app",
    icon=_ICNS,
    bundle_identifier=PRODUCT["app_id"],
    version=PRODUCT["bundle_short_version"],
    info_plist=info_plist(PRODUCT),
)
