"""Static guard for squawk 0255 (partial): the Linux spec's dropped PyInstaller hooks.

``packaging/linux/the-one.spec`` drops PyInstaller's stock gi/gio/glib/gtk runtime hooks
because they re-point ``GI_TYPELIB_PATH`` and friends into the bundle after
``rthook_host_gtk.py`` has run. Whether those four names are the whole set depends on the
PyInstaller release, and nothing off the container build can read that release's
``rthooks`` directory. So this guard pins what a unit test CAN see: the spec's dropped set
and the PyInstaller version every build recipe installs. A version bump fails here until
someone has re-read the new release's ``PyInstaller/hooks/rthooks/`` for gi-related
``pyi_rth_*`` hooks, then updated ``REVIEWED_PYINSTALLER`` and, if needed, the spec.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINUX = ROOT / "packaging" / "linux"
SPEC = LINUX / "the-one.spec"

# The release whose rthooks were last checked, and the hooks that check found to be
# gi/GTK-environment hooks (the ones the spec must drop).
REVIEWED_PYINSTALLER = "6.22.3"
DROPPED_HOOKS = {"pyi_rth_gi", "pyi_rth_gio", "pyi_rth_glib", "pyi_rth_gtk"}

_PIN = re.compile(r"pyinstaller==([0-9][0-9A-Za-z.]*)")


def _spec_dropped_hooks() -> set[str]:
    src = SPEC.read_text(encoding="utf-8")
    start = src.index("a.scripts = [")
    block = src[start : src.index("]", src.index("not in {", start))]
    return set(re.findall(r'"(pyi_rth_[a-z0-9_]+)"', block))


def test_the_spec_drops_exactly_the_reviewed_gi_hooks() -> None:
    assert _spec_dropped_hooks() == DROPPED_HOOKS


def test_the_spec_drop_is_skipped_only_with_the_no_excludes_switch() -> None:
    src = SPEC.read_text(encoding="utf-8")
    start = src.index("a.scripts = [")
    assert "if not _NO_EXCLUDES:" in src[max(0, start - 40) : start]


def test_every_linux_recipe_installs_the_reviewed_pyinstaller() -> None:
    pins = {}
    for rel in ("build.Dockerfile", "README.md"):
        found = set(_PIN.findall((LINUX / rel).read_text(encoding="utf-8")))
        assert found, f"{rel} no longer pins pyinstaller"
        pins[rel] = found
    for rel, found in pins.items():
        assert found == {REVIEWED_PYINSTALLER}, (
            f"{rel} installs pyinstaller {sorted(found)}, reviewed {REVIEWED_PYINSTALLER}: "
            "re-read PyInstaller/hooks/rthooks/ in the new release for gi-related "
            "pyi_rth_* hooks (squawk 0255), then update REVIEWED_PYINSTALLER and the spec"
        )
