#!/usr/bin/env python3
"""Rehearse Briefcase's macOS requirement install on Linux (Mission 32 Flight 1, leg 4).

Spike verification, not product. It reproduces what Briefcase 0.4.6 runs on macOS
(``pip install --platform macosx_<V>_arm64 --only-binary :all: --no-deps --require-hashes
--no-binary proxy-tools -r closure.txt``) as ``pip download``, so a wheel that is missing
for a macOS tag shows up before any hosted minute is spent.

pip evaluates environment markers against the *running* interpreter, so on Linux the
macOS-only pins (pyobjc) would be dropped and the Linux-only ones (pygobject) kept. This
script first evaluates every marker as macOS arm64 and writes a filtered closure.

    macos-resolution-rehearsal.py CLOSURE.txt SCRATCH --python 3.11 --tag 11_0 [--tag 12_0 ...]

Needs ``pip`` and ``packaging`` importable by the interpreter that runs it.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from packaging.markers import Marker

MAC_ENV = {
    "sys_platform": "darwin",
    "platform_system": "Darwin",
    "os_name": "posix",
    "platform_machine": "arm64",
    "platform_release": "24.0.0",
    "platform_python_implementation": "CPython",
    "implementation_name": "cpython",
}


def filter_closure(src: Path, dst: Path, python: str) -> tuple[int, int]:
    """Write the macOS-applicable entries of a uv-exported closure; return (kept, dropped)."""
    env = dict(MAC_ENV, python_version=python, python_full_version=f"{python}.0")
    blocks, cur = [], []
    for line in src.read_text().splitlines():
        if re.match(r"^[A-Za-z0-9]", line):
            if cur:
                blocks.append(cur)
            cur = [line]
        elif cur:
            cur.append(line)
    if cur:
        blocks.append(cur)
    kept = dropped = 0
    out = []
    for b in blocks:
        head = b[0].rstrip(" \\")
        req, _, marker = head.partition(";")
        if marker.strip() and not Marker(marker.strip()).evaluate(env):
            dropped += 1
            continue
        kept += 1
        # pip would re-evaluate the marker against Linux: emit the pin without it
        out.append(req.strip() + " \\")
        out.extend(x for x in b[1:] if not x.lstrip().startswith("#"))
    dst.write_text("\n".join(out) + "\n")
    return kept, dropped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("closure")
    ap.add_argument("scratch")
    ap.add_argument("--python", required=True, help="target Python, e.g. 3.11")
    ap.add_argument("--tag", action="append", required=True, help="e.g. 11_0")
    ap.add_argument("--arch", default="arm64")
    a = ap.parse_args()
    scratch = Path(a.scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    filt = scratch / f"closure-macos-py{a.python}.txt"
    kept, dropped = filter_closure(Path(a.closure), filt, a.python)
    print(f"closure for macOS py{a.python}: {kept} pins kept, {dropped} dropped by marker")
    rc = 0
    for tag in a.tag:
        dest = scratch / f"dl-py{a.python}-macosx_{tag}_{a.arch}"
        dest.mkdir(exist_ok=True)
        cmd = [
            sys.executable, "-m", "pip", "download", "--dest", str(dest),
            "--platform", f"macosx_{tag}_{a.arch}", "--python-version", a.python,
            "--implementation", "cp", "--only-binary", ":all:", "--no-binary", "proxy-tools",
            "--no-deps", "--require-hashes", "--disable-pip-version-check", "-q",
            "-r", str(filt),
        ]  # fmt: skip
        r = subprocess.run(cmd, capture_output=True, text=True)
        n = len(list(dest.iterdir()))
        print(f"macosx_{tag}_{a.arch} py{a.python}: rc={r.returncode} files={n}")
        if r.returncode:
            rc = 1
            print("\n".join((r.stdout + r.stderr).strip().splitlines()[-6:]))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
