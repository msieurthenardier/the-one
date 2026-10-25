#!/usr/bin/env python3
"""Audit a built macOS .app: every Mach-O must be arm64, link only to allowed places, and
need no newer macOS than the bundle declares (Mission 32 Flight 3 leg 6, DD8).

    audit.py APP (--min-os 14.0 | --product-json product.json) [--report-only]

Walks the bundle (symlinks are not followed), picks Mach-O files by magic number and runs
``lipo -archs``, ``otool -arch arm64 -L`` and ``otool -arch arm64 -l`` on each. Problems:

* a load path outside /System/, /usr/lib/, @rpath/, @loader_path/ or @executable_path/;
* a Mach-O with no arm64 slice (universal2 files are fat: listed, not a problem);
* an LC_BUILD_VERSION ``minos`` above ``--min-os`` (a file with only the older
  LC_VERSION_MIN_MACOSX is read from that; a file with neither is "unknown", not a problem).

Prints a summary and exits 1 on any problem, unless ``--report-only`` (the first hosted run,
so a false positive cannot burn a dispatch). Stdlib only; the parsers are pure functions.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

ALLOWED_PREFIXES = ("/System/", "/usr/lib/", "@rpath/", "@loader_path/", "@executable_path/")
MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce",
    b"\xfe\xed\xfa\xcf",
    b"\xce\xfa\xed\xfe",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",  # fat (also a Java class: otool/lipo decide)
    b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf",
    b"\xbf\xba\xfe\xca",
}
TIMEOUT = 120


def parse_archs(lipo_output: str) -> list[str]:
    """``lipo -archs`` prints the slices on one line: ``x86_64 arm64``."""
    return lipo_output.split()


def parse_libs(otool_libs: str) -> list[str]:
    """The load paths in ``otool -L`` output (the first line names the file itself)."""
    libs = []
    for line in otool_libs.splitlines()[1:]:
        if line[:1] in ("\t", " "):
            m = re.match(r"\s*(.+?) \(compatibility version", line)
            libs.append(m.group(1) if m else line.strip())
    return libs


def parse_install_name(otool_cmds: str) -> str | None:
    """The LC_ID_DYLIB name from ``otool -l`` output, which ``otool -L`` lists as a library."""
    block = re.search(r"cmd LC_ID_DYLIB\n(?:.*\n){0,4}?\s+name (.+?) \(offset", otool_cmds)
    return block.group(1) if block else None


def parse_minos(otool_cmds: str) -> str | None:
    """The highest minimum macOS in ``otool -l`` output, or None when the file states none.

    LC_BUILD_VERSION carries ``minos``; the older LC_VERSION_MIN_MACOSX carries ``version``.
    """
    found: list[str] = []
    for m in re.finditer(r"cmd LC_BUILD_VERSION\n(?:.*\n){0,8}?\s+minos (\S+)", otool_cmds):
        found.append(m.group(1))
    for m in re.finditer(r"cmd LC_VERSION_MIN_MACOSX\n(?:.*\n){0,3}?\s+version (\S+)", otool_cmds):
        found.append(m.group(1))
    return max(found, key=version_key) if found else None


def version_key(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split(".") if p.isdigit())


def bad_libs(libs: list[str], own_id: str | None = None) -> list[str]:
    return [lib for lib in libs if lib != own_id and not lib.startswith(ALLOWED_PREFIXES)]


def is_macho(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(4) in MACHO_MAGICS
    except OSError:
        return False


def run_tool(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, f"{type(exc).__name__}: {exc}"
    return p.returncode, p.stdout + p.stderr


def audit(app: str, min_os: str, run=None) -> dict:
    """Audit ``app``; ``run(cmd) -> (rc, output)`` is injected by the tests."""
    run = run or run_tool
    limit = version_key(min_os)
    files = fat = 0
    max_minos: str | None = None
    unknown: list[str] = []
    problems: list[str] = []
    for root, dirs, names in os.walk(app, followlinks=False):
        dirs.sort()
        for name in sorted(names):
            path = os.path.join(root, name)
            if os.path.islink(path) or not is_macho(path):
                continue
            rel = os.path.relpath(path, app)
            files += 1
            rc, out = run(["lipo", "-archs", path])
            if rc != 0:
                problems.append(f"{rel}: lipo failed (rc={rc}): {out.strip()[:200]}")
                continue
            archs = parse_archs(out)
            if len(archs) > 1:
                fat += 1
            if "arm64" not in archs:
                problems.append(f"{rel}: no arm64 slice (has: {' '.join(archs) or 'none'})")
                continue
            rc, libs_out = run(["otool", "-arch", "arm64", "-L", path])
            rc2, cmds_out = run(["otool", "-arch", "arm64", "-l", path])
            if rc != 0 or rc2 != 0:
                problems.append(f"{rel}: otool failed (rc={rc}/{rc2})")
                continue
            for lib in bad_libs(parse_libs(libs_out), parse_install_name(cmds_out)):
                problems.append(f"{rel}: load path outside the allowed places: {lib}")
            minos = parse_minos(cmds_out)
            if minos is None:
                unknown.append(rel)
                continue
            if max_minos is None or version_key(minos) > version_key(max_minos):
                max_minos = minos
            if version_key(minos) > limit:
                problems.append(f"{rel}: minos {minos} is above the declared {min_os}")
    return {
        "files": files,
        "fat": fat,
        "max_minos": max_minos,
        "unknown_minos": unknown,
        "problems": problems,
        "min_os": min_os,
    }


def format_report(result: dict) -> str:
    lines = [
        f"audit: {result['files']} Mach-O files, {result['fat']} fat (universal), "
        f"max minos {result['max_minos'] or 'unknown'} (declared {result['min_os']}), "
        f"{len(result['unknown_minos'])} with no minos, {len(result['problems'])} problem(s)"
    ]
    lines += [f"  PROBLEM {p}" for p in result["problems"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("app")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--min-os")
    src.add_argument("--product-json")
    ap.add_argument("--report-only", action="store_true", help="print problems, exit 0")
    args = ap.parse_args(argv)
    if not os.path.isdir(args.app):
        print(f"audit.py: not a directory: {args.app}", file=sys.stderr)
        return 2
    min_os = args.min_os
    if args.product_json:
        with open(args.product_json, encoding="utf-8") as fh:
            min_os = json.load(fh)["min_os"]
    result = audit(args.app, min_os)
    print(format_report(result))
    if result["problems"] and not args.report_only:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
