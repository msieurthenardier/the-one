"""Guard: no packaging entry point ships the frozen Windows app from an
unlocked dependency resolve (squawk 0009, squawk 0015).

Squawk 0009 fixed `.github/workflows/windows-installer.yml` (the GitHub `v*`-tag
release path) to install the LOCKED closure — `uv export --no-dev
--no-emit-project --extra gui --extra all-llms --format requirements-txt`,
`pip install -r <export>`, then `pip install -e . --no-deps` — instead of a fresh
`pip install -e ".[gui,all-llms]"` resolve, which can re-resolve version ranges at
build time and bundle an untested SDK into the frozen app. Squawk 0015 found that
`ci/tasks/windows-installer-build.yml` (the Concourse task that builds the
installer on every push to `main`) still did the unlocked resolve, and ported the
same sequence there. This test guards both regressions and any THIRD packaging
entry point repeating the pattern.

Rule (plain-text grep — no YAML parsing dependencies)
------------------------------------------------------
1. ALLOWLIST — the two known artifact-producing entry points that actually build
   and ship the frozen Windows app (`ci/tasks/windows-installer-build.yml` —
   Concourse, every push — and `.github/workflows/windows-installer.yml` — the
   GitHub `v*`-tag release path) MUST contain the locked-closure sequence: a
   `uv export ... --extra gui ... --extra all-llms ...` line AND a
   `pip install ... --no-deps` line. Losing either marker fails the test — this
   is the exact regression squawk 0015 caught.

2. DENYLIST (`[gui` specifically) — scanned across every EXECUTABLE
   packaging/CI entry point under `ci/tasks/*.yml`, `.github/workflows/*.yml`,
   `packaging/**`, `Makefile`, and `scripts/**`: any line that installs the
   project's `gui` extra via a fresh resolve (`pip install -e ".[...gui...]"` /
   `pip install -e '.[...gui...]'` / `pip install .[...gui...]`) is disallowed
   UNLESS the SAME FILE also contains the rule-1 locked-closure sequence. The
   `[gui` extra is a deliberate, narrow trigger: only an installer build ever
   requests it — every test/dev install in this repo (`ci/tasks/test.yml`,
   `ci/tasks/browser.yml`, `ci/tasks/bwrap.yml`, `ci/tasks/windows-tests.yml`,
   `.github/workflows/test.yml`) uses `.[all-llms,dev]`, which never matches.
   In particular `ci/tasks/windows-tests.yml` runs
   `pip install -e ".[all-llms,dev]"` against the source checkout to run the
   OS-divergent test subset — that installs a TEST ENVIRONMENT, not a shipped
   artifact, and is correctly left alone by this rule (no `gui` extra, so it
   never matches the pattern in the first place).

   Only files with an extension that a shell/CI runner actually executes
   (`.yml`, `.yaml`, `.sh`, `.ps1`, `.py`) or the extensionless `Makefile` are
   scanned. `packaging/**` is walked per the rule-2 glob, but its `*.md` docs
   (e.g. `packaging/windows/README.md`) and the PyInstaller `*.spec`'s embedded
   build docstring (`packaging/windows/the-one.spec`) are excluded by
   extension: both mention `pip install -e ".[gui,all-llms]"` as instructions
   for a MANUAL native-Windows developer build (a human iterating on the freeze
   on their own machine), not as a command any CI/build tool executes. No
   automated packaging entry point reads or runs those files' `pip install`
   lines.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Rule 1 — artifact-producing entry points that MUST carry the locked-closure
# sequence.
LOCKED_CLOSURE_REQUIRED = [
    "ci/tasks/windows-installer-build.yml",
    ".github/workflows/windows-installer.yml",
]

# Locked-closure sequence markers (both must be present in the file).
UV_EXPORT_RE = re.compile(r"uv export .*--extra gui.*--extra all-llms")
NO_DEPS_RE = re.compile(r"pip install .*--no-deps")

# Rule 2 — fresh-resolve extras install, any of the three quoting styles the
# squawk calls out: `pip install -e ".[`, `pip install -e '.[`, `pip install .[`.
FRESH_RESOLVE_RE = re.compile(r"""pip install (-e )?["']?\.\[[^\]]*\]""")
GUI_EXTRA_RE = re.compile(r"\[[^\]]*\bgui\b")

# Directories/globs scanned for rule 2 — the packaging/CI surface named in the
# squawk's evidence.
SCAN_GLOBS = [
    "ci/tasks/*.yml",
    ".github/workflows/*.yml",
    "packaging/**/*",
    "Makefile",
    "scripts/**/*",
]

# Only extensions a shell/CI runner actually executes (plus the extensionless
# Makefile) are in scope for rule 2 — see module docstring rule 2 for why
# *.md / *.spec are excluded.
EXECUTABLE_SUFFIXES = {".yml", ".yaml", ".sh", ".ps1", ".py"}


def _is_scannable(path: Path) -> bool:
    if not path.is_file():
        return False
    if "__pycache__" in path.parts:
        return False
    if path.name == "Makefile":
        return True
    return path.suffix in EXECUTABLE_SUFFIXES


def _iter_scanned_files():
    seen: set[Path] = set()
    for pattern in SCAN_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if path in seen or not _is_scannable(path):
                continue
            seen.add(path)
            yield path


def _has_locked_closure_sequence(text: str) -> bool:
    return bool(UV_EXPORT_RE.search(text)) and bool(NO_DEPS_RE.search(text))


def test_artifact_producing_entry_points_use_locked_closure() -> None:
    """Rule 1: the two known installer-build entry points must stay locked."""
    failures = []
    for relpath in LOCKED_CLOSURE_REQUIRED:
        path = REPO_ROOT / relpath
        text = path.read_text(encoding="utf-8")
        if not _has_locked_closure_sequence(text):
            failures.append(relpath)
    assert not failures, (
        "These artifact-producing entry points must install the LOCKED "
        "dependency closure (`uv export --no-dev --no-emit-project --extra "
        "gui --extra all-llms` -> `pip install -r ...` -> "
        "`pip install -e . --no-deps`), not a fresh resolve — see squawk "
        f"0009 / 0015: {failures}"
    )


def test_no_unlocked_gui_extra_install_outside_locked_files() -> None:
    """Rule 2: no packaging entry point installs `[gui` via a fresh resolve
    unless the same file also carries the locked-closure sequence."""
    violations = []
    for path in _iter_scanned_files():
        text = path.read_text(encoding="utf-8")
        if _has_locked_closure_sequence(text):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if FRESH_RESOLVE_RE.search(line) and GUI_EXTRA_RE.search(line):
                relpath = path.relative_to(REPO_ROOT)
                violations.append(f"{relpath}:{lineno}: {line.strip()}")
    assert not violations, (
        "Found a fresh-resolve install of the `gui` extra outside the "
        "locked-closure sequence — this ships an unpinned SDK into a frozen "
        "build (squawk 0009 / 0015):\n" + "\n".join(violations)
    )
