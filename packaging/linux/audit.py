#!/usr/bin/env python3
"""Post-freeze bundle audit for the Linux build (Mission 32, DD2). Stdlib only.

    audit.py BUNDLE_DIR [--excludes excludes.txt] [--max-glibc 2.39]

Run by build-inner.sh right after the freeze, before wrapping. Scoped to the PyInstaller
bundle directory only (never the AppImage fallback directory). Fails (exit 1, offending paths
printed) when
  * a file's base name matches an excludes.txt pattern (the host provides that library);
  * a ``*.typelib`` is present (the host's GObject introspection data is used);
  * an ELF file requires a GLIBC_ symbol version newer than --max-glibc (default 2.39, the
    build image's glibc and so the package's floor).
Prints a summary: file count, maximum glibc found, pass/fail.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_MAX_GLIBC = "2.39"
HERE = Path(__file__).resolve().parent
_GLIBC_RE = re.compile(r"GLIBC_(\d+(?:\.\d+)*)")


def load_patterns(path: Path) -> list[str]:
    pats = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            pats.append(line)
    return pats


def is_elf(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def glibc_requirements(path: Path) -> list[str]:
    """GLIBC_ versions an ELF file requires, from ``readelf -V`` (the seam tests replace)."""
    r = subprocess.run(["readelf", "-V", str(path)], capture_output=True, text=True)
    return _GLIBC_RE.findall(r.stdout)


def _vkey(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


def audit(bundle: Path, patterns: list[str], max_glibc: str = DEFAULT_MAX_GLIBC):
    """Return (problems, file_count, highest_glibc_or_None)."""
    problems: list[str] = []
    count = 0
    highest: str | None = None
    for p in sorted(bundle.rglob("*")):
        if p.is_symlink() or not p.is_file():
            continue
        count += 1
        rel = p.relative_to(bundle)
        for pat in patterns:
            if fnmatch.fnmatch(p.name, pat):
                problems.append(f"excluded library present: {rel} (matches {pat})")
                break
        if p.name.endswith(".typelib"):
            problems.append(f"typelib present: {rel}")
        if is_elf(p):
            vers = glibc_requirements(p)
            if vers:
                top = max(vers, key=_vkey)
                if highest is None or _vkey(top) > _vkey(highest):
                    highest = top
                if _vkey(top) > _vkey(max_glibc):
                    problems.append(f"needs GLIBC_{top} (newer than {max_glibc}): {rel}")
    return problems, count, highest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--excludes", type=Path, default=HERE / "excludes.txt")
    ap.add_argument("--max-glibc", default=DEFAULT_MAX_GLIBC)
    args = ap.parse_args(argv)
    if not args.bundle.is_dir():
        print(f"audit.py: not a directory: {args.bundle}", file=sys.stderr)
        return 2
    problems, count, highest = audit(args.bundle, load_patterns(args.excludes), args.max_glibc)
    for line in problems:
        print(f"AUDIT FAIL: {line}")
    verdict = "FAIL" if problems else "PASS"
    print(
        f"audit: {count} files, max GLIBC_{highest or 'none'} (limit {args.max_glibc}), "
        f"{len(problems)} problem(s): {verdict}"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
