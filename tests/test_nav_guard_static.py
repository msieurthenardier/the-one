"""Static pins for the unified leave guard (M25 F2 L5).

Cheap source-level invariants that keep the per-area guard copies from creeping
back: one `beforeunload`, no area `confirmLeave`, and `App.confirmDialog(`
called only by nav.js, the design-language modal demo, and the Notes
section's Clear all.
"""

from __future__ import annotations

import re
from pathlib import Path

JS = Path(__file__).resolve().parent.parent / "the_one" / "interfaces" / "web" / "static" / "js"


def _files():
    return sorted(JS.rglob("*.js"))


def _code(path: Path) -> str:
    """Source with // line comments and /* */ blocks removed."""
    text = path.read_text()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$|(?<=\s)//\s.*$", "", text)


def test_confirm_dialog_called_only_by_nav_the_modal_demo_and_notes_clear_all():
    callers = {
        p.name for p in _files() if re.search(r"App\.confirmDialog\s*\(", _code(p)) is not None
    }
    # rules-notes-tab.js (M27 F2 L3, DD10): the Notes section's Clear all is a
    # blocking "this can't be undone" decision, not a leave guard.
    assert callers <= {"ui-modal-section.js", "rules-notes-tab.js"}
    # nav.js reaches it through a lazily-resolved local, never a literal call site.
    assert "window.App.confirmDialog" in (JS / "nav.js").read_text()


def test_one_beforeunload_listener_lives_in_nav_js():
    holders = {p.name for p in _files() if "beforeunload" in _code(p)}
    assert holders == {"nav.js"}


def test_no_area_confirm_leave_or_impl_remains():
    for p in _files():
        code = _code(p)
        assert "_confirmLeaveImpl" not in code, p.name
        assert not re.search(r"\bconfirmLeave\s*:\s*function", code), p.name
    assert not re.search(r"area\.confirmLeave|\.confirmLeave\(\s*function", _code(JS / "router.js"))
