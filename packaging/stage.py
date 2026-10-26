#!/usr/bin/env python3
"""Shared packaging staging step: the freeze input for the Linux and macOS builds.

Copies ``the_one/`` into a staging directory OUTSIDE the repo, rewrites
``__version__`` there, applies the target's patch diffs to the copy, and
leaves the repo untouched. Every target builds from that copy.

    python packaging/stage.py --version 0.11.9.dev1 --target linux

Output: ``$M32_BUILD/stage-<target>-<version>/`` (``--out`` overrides the
parent directory). It holds ``the_one/`` and ``icon-512.png``.
Stdlib only. Exits non-zero on any problem. Needs no git, except to apply a target's
``packaging/<target>/patches/*.diff`` on macOS and Windows (``git apply``); the windows target
has none.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r'^__version__\s*=\s*"[^"]*"\s*$', re.MULTILINE)
ICON = Path("the_one/interfaces/web/static/brand/icon-512.png")


def die(msg: str) -> "None":
    print(f"stage.py: error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def repo_toplevel() -> Path:
    """The repo's top level for the outside-the-repo check.

    Asks git; on ANY failure (git missing, a non-zero exit such as a worktree's ``.git``
    gitlink pointing at a path that does not exist on this host, which is what
    ``fly execute`` uploads) falls back to the resolved location of this script's repo, so a
    staging run needs no git. Git is then required only for a target that has patch diffs.
    """
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=REPO, capture_output=True, text=True
        )
    except OSError:  # FileNotFoundError: no git on PATH
        return REPO.resolve()
    if r.returncode != 0 or not r.stdout.strip():
        return REPO.resolve()
    return Path(r.stdout.strip()).resolve()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", required=True, help="e.g. 0.11.9.dev1")
    ap.add_argument(
        "--target",
        "--candidate",  # alias kept for one release (the old spike spelling)
        dest="target",
        required=True,
        help="linux, macos, ...",
    )
    ap.add_argument(
        "--out",
        default=os.environ.get("M32_BUILD") or str(Path.home() / "the-one-m32-build"),
        help="parent directory for the staging dir (default $M32_BUILD)",
    )
    args = ap.parse_args()

    top = repo_toplevel()
    # M32_SOURCE: a directory holding the_one/ (and the icon) to stage instead of the working
    # tree, e.g. a `git archive HEAD` export, so a build never freezes half-edited files.
    src = Path(os.environ["M32_SOURCE"]).resolve() if os.environ.get("M32_SOURCE") else REPO
    out_parent = Path(args.out).expanduser().resolve()
    dest = out_parent / f"stage-{args.target}-{args.version}"
    for p in (out_parent, dest):
        if p == top or top in p.parents:
            die(f"output path {p} resolves inside the repo ({top})")

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    shutil.copytree(
        src / "the_one",
        dest / "the_one",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copy2(src / ICON, dest / "icon-512.png")

    init = dest / "the_one" / "__init__.py"
    text = init.read_text(encoding="utf-8")
    hits = VERSION_RE.findall(text)
    if len(hits) != 1:
        die(f"expected exactly one __version__ line in {init}, found {len(hits)}")
    init.write_text(
        VERSION_RE.sub(f'__version__ = "{args.version}"', text, count=1), encoding="utf-8"
    )

    patch_dir = REPO / "packaging" / args.target / "patches"
    for diff in sorted(patch_dir.glob("*.diff")):
        use_git = sys.platform in ("darwin", "win32")
        if use_git:
            # macOS ships BSD patch, whose option set differs from GNU's, and GNU patch is not
            # on a Windows runner's PATH; git is already a build requirement and applies the
            # same diffs. (Windows: set core.autocrlf=false before checkout, so the sources and
            # diffs keep LF.)
            cmd = ["git", "apply", "-p1", "--verbose", str(diff)]
        else:
            cmd = ["patch", "-p1", "--no-backup-if-mismatch", "-d", str(dest), "-i", str(diff)]
        try:
            r = subprocess.run(
                cmd,
                cwd=dest if use_git else None,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            die(f"cannot apply {diff.name}: {cmd[0]} is not available ({exc})")
        print(r.stdout, end="")
        if r.returncode != 0:
            die(f"patch {diff.name} failed:\n{r.stdout}{r.stderr}")
        print(f"applied {diff.name}")

    print(f"staged {args.target} {args.version} -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
