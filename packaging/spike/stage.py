#!/usr/bin/env python3
"""Shared staging step for the Mission 32 packaging spike (spike tooling, not product).

Copies ``the_one/`` into a staging directory OUTSIDE the repo, rewrites
``__version__`` there, applies the candidate's patch diffs to the copy, and
leaves the repo untouched. Every candidate builds from that copy.

    python packaging/spike/stage.py --version 0.11.9.dev1 --candidate linux

Output: ``$M32_BUILD/stage-<candidate>-<version>/`` (``--out`` overrides the
parent directory). It holds ``the_one/`` and ``icon-512.png``.
Stdlib only. Exits non-zero on any problem.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VERSION_RE = re.compile(r'^__version__\s*=\s*"[^"]*"\s*$', re.MULTILINE)
ICON = Path("the_one/interfaces/web/static/brand/icon-512.png")


def die(msg: str) -> "None":
    print(f"stage.py: error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def repo_toplevel() -> Path:
    r = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=REPO, capture_output=True, text=True
    )
    if r.returncode != 0:
        die(f"git rev-parse failed: {r.stderr.strip()}")
    return Path(r.stdout.strip()).resolve()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", required=True, help="e.g. 0.11.9.dev1")
    ap.add_argument("--candidate", required=True, help="linux, briefcase, macos, ...")
    ap.add_argument(
        "--out",
        default=os.environ.get("M32_BUILD") or str(Path.home() / "the-one-m32-build"),
        help="parent directory for the staging dir (default $M32_BUILD)",
    )
    args = ap.parse_args()

    top = repo_toplevel()
    out_parent = Path(args.out).expanduser().resolve()
    dest = out_parent / f"stage-{args.candidate}-{args.version}"
    for p in (out_parent, dest):
        if p == top or top in p.parents:
            die(f"output path {p} resolves inside the repo ({top})")

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copytree(
        REPO / "the_one",
        dest / "the_one",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copy2(REPO / ICON, dest / "icon-512.png")

    init = dest / "the_one" / "__init__.py"
    text = init.read_text(encoding="utf-8")
    hits = VERSION_RE.findall(text)
    if len(hits) != 1:
        die(f"expected exactly one __version__ line in {init}, found {len(hits)}")
    init.write_text(
        VERSION_RE.sub(f'__version__ = "{args.version}"', text, count=1), encoding="utf-8"
    )

    patch_dir = REPO / "packaging" / args.candidate / "patches"
    for diff in sorted(patch_dir.glob("*.diff")):
        r = subprocess.run(
            ["patch", "-p1", "--no-backup-if-mismatch", "-d", str(dest), "-i", str(diff)],
            capture_output=True,
            text=True,
        )
        print(r.stdout, end="")
        if r.returncode != 0:
            die(f"patch {diff.name} failed:\n{r.stdout}{r.stderr}")
        print(f"applied {diff.name}")

    print(f"staged {args.candidate} {args.version} -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
