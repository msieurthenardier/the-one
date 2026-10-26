#!/usr/bin/env python3
"""The release version gate (Mission 32 Flight 4, DD6). Stdlib only.

    release_check.py --event E --ref R [--input-version V] [--platforms P] [--repo DIR]

Prints the version to build on stdout and exits 0, or prints the reason on stderr and exits 1.

* ``--event push`` with a ``refs/tags/v`` ref is the real release: the tag must be exactly
  ``v`` + ``the_one.__version__``, the version a final ``X.Y.Z`` (no ``.devN``), and the tagged
  commit (``HEAD``) an ancestor of ``origin/main``. The path is chosen by the event AND the ref,
  never the ref alone: a ``workflow_dispatch`` run on a tag ref is a dry run.
* ``--event workflow_dispatch`` accepts ``--input-version`` in the strict grammar (``X.Y.Z`` or
  ``X.Y.Z.devN``), or ``__version__`` when it is empty, and validates ``--platforms``
  (comma-separated, no spaces, each of windows/linux/macos, at least one).

Either way the version goes through ``render.load`` so every derived field (``deb_version``,
``bundle_version``, ``bundle_short_version``) is valid. ``packaging/render.py`` is loaded by
path: ``import packaging.render`` would resolve to the PyPI ``packaging`` distribution.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

PLATFORMS = ("windows", "linux", "macos")
REPO = Path(__file__).resolve().parent.parent


class GateError(Exception):
    pass


def load_render(repo: Path):
    spec = importlib.util.spec_from_file_location(
        "release_check_render", Path(repo) / "packaging" / "render.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclass-free, but keeps tracebacks readable
    spec.loader.exec_module(mod)
    return mod


def check_platforms(platforms: str) -> list[str]:
    tokens = platforms.split(",")
    bad = [t for t in tokens if t not in PLATFORMS]
    if bad:
        shown = ", ".join(repr(t) for t in bad)
        raise GateError(
            f"platforms: unknown or blank entry {shown}; use a comma-separated list "
            f"(no spaces) of {', '.join(PLATFORMS)}"
        )
    return tokens


def _is_ancestor(repo: Path, commit: str, main_ref: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", commit, main_ref],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    raise GateError(
        f"could not compare {commit} with {main_ref} (is the checkout complete, "
        f"fetch-depth: 0?): {proc.stderr.strip()}"
    )


def gate(
    event: str,
    ref: str,
    input_version: str = "",
    platforms: str | None = None,
    repo: Path = REPO,
    main_ref: str = "origin/main",
    commit: str = "HEAD",
) -> str:
    render = load_render(repo)
    try:
        dunder = render.read_version(repo)
        if event == "push":
            if not ref.startswith("refs/tags/v"):
                raise GateError(f"a push release needs a refs/tags/v* ref, got {ref!r}")
            version = ref[len("refs/tags/v") :]
            if version != dunder:
                raise GateError(
                    f"tag {ref!r} does not match the_one.__version__ {dunder!r}; "
                    f"the tag must be exactly v{dunder}"
                )
            parts = render._release_parts(version)
            if parts[3] is not None:
                raise GateError(f"{version!r} is a dev version; a release tag is a final X.Y.Z")
            if not _is_ancestor(repo, commit, main_ref):
                raise GateError(f"the tagged commit is not an ancestor of {main_ref}")
        elif event == "workflow_dispatch":
            if platforms is not None:
                check_platforms(platforms)
            version = input_version.strip() or dunder
            render._release_parts(version)  # the strict grammar: X.Y.Z or X.Y.Z.devN
        else:
            raise GateError(f"unsupported event {event!r} (push or workflow_dispatch)")
        render.load(repo, {"version": version})  # every derived field must be valid
    except render.RenderError as exc:
        raise GateError(str(exc)) from exc
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--event", required=True, help="github.event_name")
    parser.add_argument("--ref", required=True, help="github.ref")
    parser.add_argument("--input-version", default="")
    parser.add_argument("--platforms", default=None)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--main-ref", default="origin/main")
    args = parser.parse_args(argv)
    try:
        print(
            gate(
                args.event,
                args.ref,
                args.input_version,
                args.platforms,
                args.repo,
                args.main_ref,
            )
        )
    except GateError as exc:
        print(f"release gate: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
