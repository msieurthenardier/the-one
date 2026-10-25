# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-dir spec for GleepGlorp AI on Linux (Mission 32 Flight 1, candidate A).

SPIKE PROTOTYPE, not wired into CI. Borrowed from ../windows/the-one.spec: same
collection contract, minus the Windows-only parts (winpty, pystray._win32, the
console/windowed exe split: Linux has one exe serving the CLI and `app`).

Build with build.sh. Environment:
    M32_STAGE        the staged copy of the_one/ (packaging/stage.py output). REQUIRED.
    M32_NO_EXCLUDES  "1" = skip excludes.txt and keep the gi typelibs (the AC4 "before" build).

Unlike the Windows spec, this one never puts the repo root on sys.path and never
imports the_one from the repo: that would bundle unpatched code and the repo's
version. Only the staged copy is visible to the freeze.
"""

import fnmatch
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
_NO_EXCLUDES = os.environ.get("M32_NO_EXCLUDES") == "1"

# The collect_* helpers below import the_one in-process; make that the staged copy.
sys.path.insert(0, _STAGE)

_HERE = SPECPATH  # noqa: F821  (PyInstaller spec global)
# The Windows entry script is reused by path: it only calls freeze_support() and
# the_one.main.cli_entry, which resolves to the staged copy via pathex.
_ENTRY = os.path.abspath(os.path.join(_HERE, os.pardir, "windows", "frozen_entry.py"))

print(f"[the-one.spec] freezing from {_STAGE} (excludes {'OFF' if _NO_EXCLUDES else 'ON'})")

# ── Collection contract (from the Windows spec) ─────────────────────────────
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
pystray_hidden = collect_submodules("pystray", on_error="warn")
# PyInstaller's gi hooks cannot query GI on this build host (see README), so the PyGObject
# override modules (GLib.idle_add, Gtk, Gdk, ...) are not collected unless named. Without them
# pywebview's GLib.idle_add(func, ...) hits the raw typelib signature and the window never opens.
gi_overrides_hidden = collect_submodules("gi.overrides", on_error="warn")

static_datas = collect_data_files("the_one", includes=["interfaces/web/static/**/*"])
seed_datas = collect_data_files("the_one", includes=["llm/data/*.json"])
embedding_datas = collect_data_files("the_one", includes=["embeddings/data/**/*"])
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
    *pystray_hidden,
    *gi_overrides_hidden,
    *tzdata_hidden,
    *tzlocal_hidden,
    # Linux window and tray: the GTK backends are chosen at runtime by name
    # (pywebview's guilib, pystray's backend()), which the static walk can miss.
    "webview.platforms.gtk",
    # pystray's own import fails at build time here (no Ayatana typelib on the
    # build host), so collect_submodules finds nothing: name the Linux backends.
    "pystray._base",
    "pystray._appindicator",
    "pystray._gtk",
    "pystray._xorg",
    "pystray._dummy",
    "pystray._util",
    "pystray._util.gtk",
    "pystray._util.notify_dbus",
    "gi",
    "gi.repository.Gtk",
    "gi.repository.Gdk",
    "gi.repository.GLib",
    "gi.repository.Gio",
    "gi.repository.GObject",
    "gi.repository.WebKit2",
    "gi.repository.Soup",
    "gi.repository.AyatanaAppIndicator3",
]

datas = [
    *static_datas,
    *seed_datas,
    *embedding_datas,
    *tzdata_datas,
    *mcp_metadata,
    *uvicorn_datas,
]

# hf_xet: same stale-build-env guard as the Windows spec.
excludes = ["hf_xet"]

a = Analysis(
    [_ENTRY],
    pathex=[_STAGE],
    binaries=[*uvicorn_bins],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    # Pin the versions PyInstaller's gi hooks look up, and skip the host-owned
    # icon/theme/locale payloads (the host desktop provides them).
    hooksconfig={
        "gi": {
            "module-versions": {
                "Gtk": "3.0",
                "Gdk": "3.0",
                "WebKit2": "4.1",
                "Soup": "3.0",
                "AyatanaAppIndicator3": "0.1",
            },
            "icons": [],
            "themes": [],
            "languages": [],
        }
    },
    runtime_hooks=[] if _NO_EXCLUDES else [os.path.join(_HERE, "rthook_host_gtk.py")],
    excludes=excludes,
    noarchive=False,
)

# ── Host GTK/WebKit stack: not bundled (flight DD2 gate 3) ──────────────────
if not _NO_EXCLUDES:
    _patterns = []
    with open(os.path.join(_HERE, "excludes.txt"), encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.split("#", 1)[0].strip()
            if _line:
                _patterns.append(_line)

    def _excluded(dest):
        base = os.path.basename(dest)
        return any(fnmatch.fnmatch(base, pat) for pat in _patterns)

    _dropped = [b[0] for b in a.binaries if _excluded(b[0])]
    a.binaries = [b for b in a.binaries if not _excluded(b[0])]
    # Typelibs come from the host's girepository directory, never from the bundle.
    _dropped += [d[0] for d in a.datas if d[0].endswith(".typelib")]
    a.datas = [d for d in a.datas if not d[0].endswith(".typelib")]
    print(f"[the-one.spec] excluded {len(_dropped)} host-stack files:")
    for _d in sorted(_dropped):
        print(f"[the-one.spec]   - {_d}")

# PyInstaller's stock gi/gio/glib/gtk runtime hooks run AFTER rthook_host_gtk.py and re-point
# GI_TYPELIB_PATH, GIO_MODULE_DIR, XDG_DATA_DIRS, GTK_PATH and friends at directories in the
# bundle, undoing the hook; WebKit's helper processes then inherit those. They only set
# environment variables, and rthook_host_gtk.py owns that environment, so drop them.
if not _NO_EXCLUDES:
    a.scripts = [
        s for s in a.scripts if s[0] not in {"pyi_rth_gi", "pyi_rth_gio", "pyi_rth_glib", "pyi_rth_gtk"}
    ]

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="the-one",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="the-one",
)
