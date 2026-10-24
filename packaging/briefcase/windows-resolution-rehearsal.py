#!/usr/bin/env python3
"""Rehearse Briefcase's Windows requirement install on Linux (Mission 32 Flight 1, leg 6).

Spike verification, not product. On Windows Briefcase 0.4.6 runs pip natively (no ``--platform``;
``virtual_environment/base.py::platform_tag`` returns None) with ``--target=<app_packages>
--only-binary :all:`` (``require_binary_installs`` is True) plus the app's
``requirement_installer_args``. This reproduces that as ``pip download --platform win_amd64``,
so a wheel that is missing for Windows shows up before any hosted minute is spent.

It reuses ``macos-resolution-rehearsal.py``'s closure filter with the environment swapped for
Windows AMD64, so ``pywinpty``, ``pywin32`` and ``pythonnet`` stay in and ``pygobject`` and
``pyobjc`` drop out (pip would evaluate the markers against the Linux host).

    windows-resolution-rehearsal.py CLOSURE.txt SCRATCH --python 3.11
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIN_ENV = {
    "sys_platform": "win32",
    "platform_system": "Windows",
    "os_name": "nt",
    "platform_machine": "AMD64",
    "platform_release": "10",
    "platform_python_implementation": "CPython",
    "implementation_name": "cpython",
}


def load_mac_module():
    spec = importlib.util.spec_from_file_location(
        "mac_rehearsal", HERE / "macos-resolution-rehearsal.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("closure")
    ap.add_argument("scratch")
    ap.add_argument("--python", required=True, help="target Python, e.g. 3.11")
    ap.add_argument("--no-proxy-tools-exception", action="store_true", help="negative control")
    a = ap.parse_args()
    mod = load_mac_module()
    mod.MAC_ENV = WIN_ENV
    scratch = Path(a.scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    filt = scratch / f"closure-windows-py{a.python}.txt"
    kept, dropped = mod.filter_closure(Path(a.closure), filt, a.python)
    print(f"closure for win_amd64 py{a.python}: {kept} pins kept, {dropped} dropped by marker")
    suffix = "-noexc" if a.no_proxy_tools_exception else ""
    dest = scratch / f"dl-py{a.python}-win_amd64{suffix}"
    dest.mkdir(exist_ok=True)
    cmd = [
        sys.executable, "-m", "pip", "download", "--dest", str(dest),
        "--platform", "win_amd64", "--python-version", a.python,
        "--implementation", "cp", "--only-binary", ":all:",
        "--no-deps", "--require-hashes", "--disable-pip-version-check", "-q",
        "-r", str(filt),
    ]  # fmt: skip
    if not a.no_proxy_tools_exception:
        cmd[cmd.index("--no-deps") : cmd.index("--no-deps")] = ["--no-binary", "proxy-tools"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    names = sorted(p.name for p in dest.iterdir())
    print(f"win_amd64 py{a.python}: rc={r.returncode} files={len(names)}")
    for key in ("pywinpty", "pywin32", "pythonnet", "proxy_tools", "usearch", "numpy-"):
        hits = [n for n in names if n.lower().startswith(key.lower())]
        print(f"  {key}: " + (", ".join(hits) or "(none)"))
    if r.returncode:
        print("\n".join((r.stdout + r.stderr).strip().splitlines()[-6:]))
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
