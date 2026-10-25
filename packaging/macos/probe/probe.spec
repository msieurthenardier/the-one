# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the probe app (Mission 32 Flight 3, leg 2): ``M32 Probe.app``.

Build-time tooling. Freezes ``delegate_probe.py`` (no product code) in the same venv as the
product build. No ATS key in the Info.plist on purpose: the probe tests what pywebview's
in-memory key alone does. On Linux the Analysis runs but the pyobjc packages are absent (darwin
markers), so the hidden imports below are only proven by the runner's ``--selftest`` step.
"""

import os

_HERE = SPECPATH  # noqa: F821  (PyInstaller spec global)

hiddenimports = [
    "webview",
    "webview.platforms.cocoa",
    "AppKit",
    "Foundation",
    "WebKit",
    "objc",
    "PyObjCTools",
    "PyObjCTools.AppHelper",
]

a = Analysis(  # noqa: F821
    [os.path.join(_HERE, "delegate_probe.py")],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["hf_xet"],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="m32-probe",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="m32-probe",
)

app = BUNDLE(  # noqa: F821
    coll,
    name="M32 Probe.app",
    bundle_identifier="ai.gleepglorp.m32probe",
    version="0.0.1",
    info_plist={
        "CFBundleName": "M32 Probe",
        "CFBundleDisplayName": "M32 Probe",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
    },
)
