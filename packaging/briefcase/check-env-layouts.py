#!/usr/bin/env python3
"""Faked-layout check of the staged env.py (Mission 32 Flight 1, leg 4). Spike verification.

Stages candidate B's patched ``the_one/platform/env.py`` (patches 01 and 02) and runs it in a
fresh interpreter per layout, with ``sys.executable`` faked, to prove how ``is_frozen()`` and
``_bundle_dir()`` read each one:

  macos-app        X.app/Contents/{MacOS/<stub>, Resources/app_packages}   frozen, bundle None
  linux-system     <prefix>/{bin/<name>, lib/<name>/app_packages}          frozen, bundle None
  source-install   <venv>/bin/python, no app_packages                      not frozen, bundle None
  macos-shaped     X.app/Contents/Resources/app_packages but exe is NOT    not frozen
                   under a directory named MacOS
  macos-no-pkgs    .../Contents/MacOS/<stub> with no Resources/app_packages not frozen

For the frozen layouts it also checks the child-process PATH: ``strip_bundle_dir_from_path``
must leave a PATH that contains the stub's directory exactly as given (nothing to strip),
and ``clean_subprocess_env`` must only append runtime dirs, never reorder or drop.

    python packaging/briefcase/check-env-layouts.py [STAGE_DIR]     (default: stage it itself)
Exit 0 only if every layout reads as expected.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

CHILD = r"""
import importlib.util, json, os, sys
sys.executable = sys.argv[2]
spec = importlib.util.spec_from_file_location("env_under_test", sys.argv[1])
env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(env)
exe_dir = os.path.dirname(sys.argv[2])
path = os.pathsep.join(["/usr/bin", exe_dir, "/bin"])
out = {
    "frozen": env.is_frozen(),
    "bundle": env._bundle_dir(),
    "strip_path": env.strip_bundle_dir_from_path({"PATH": path})["PATH"],
    "given_path": path,
    "clean_path": env.clean_subprocess_env({"PATH": path})["PATH"],
}
print(json.dumps(out))
"""


def touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("")
    return p


def run(env_py: Path, exe: Path) -> dict:
    r = subprocess.run(
        [sys.executable, "-I", "-c", CHILD, str(env_py), str(exe)],
        capture_output=True,
        text=True,
    )
    if r.returncode:
        raise SystemExit(f"child failed for {exe}:\n{r.stdout}{r.stderr}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def main() -> int:
    if len(sys.argv) > 1:
        stage = Path(sys.argv[1])
    else:
        out = Path(tempfile.mkdtemp(prefix="m32-env-check-"))
        subprocess.run(
            [sys.executable, str(REPO / "packaging/spike/stage.py"), "--version", "0.0.0",
             "--candidate", "briefcase", "--out", str(out)],
            check=True, capture_output=True,
        )  # fmt: skip
        stage = out / "stage-briefcase-0.0.0"
    env_py = stage / "the_one/platform/env.py"
    root = Path(tempfile.mkdtemp(prefix="m32-layouts-"))

    mac = touch(root / "GleepGlorp AI.app/Contents/MacOS/GleepGlorp AI")
    (root / "GleepGlorp AI.app/Contents/Resources/app_packages").mkdir(parents=True)
    linux = touch(root / "prefix/bin/the-one")
    (root / "prefix/lib/the-one/app_packages").mkdir(parents=True)
    src = touch(root / "venv/bin/python")
    shaped = touch(root / "Other.app/Contents/Elsewhere/GleepGlorp AI")
    (root / "Other.app/Contents/Resources/app_packages").mkdir(parents=True)
    nopkgs = touch(root / "Bare.app/Contents/MacOS/GleepGlorp AI")

    cases = [
        ("macos-app", mac, True, None),
        ("linux-system", linux, True, None),
        ("source-install", src, False, None),
        ("macos-shaped-not-MacOS", shaped, False, None),
        ("macos-no-app_packages", nopkgs, False, None),
    ]
    bad = 0
    for name, exe, want_frozen, want_bundle in cases:
        r = run(env_py, exe)
        ok = r["frozen"] is want_frozen and r["bundle"] == want_bundle
        if want_frozen:
            # nothing to strip: the PATH, stub directory included, is returned as given
            ok = ok and r["strip_path"] == r["given_path"]
            ok = ok and r["clean_path"].startswith(r["given_path"] + ":")
        print(f"{'ok  ' if ok else 'FAIL'} {name}: frozen={r['frozen']} bundle={r['bundle']!r}")
        if want_frozen:
            print(f"       strip_path unchanged={r['strip_path'] == r['given_path']}; "
                  f"clean_path={r['clean_path']}")  # fmt: skip
        bad += not ok
    print("RESULT", "PASS" if not bad else f"FAIL ({bad})")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
