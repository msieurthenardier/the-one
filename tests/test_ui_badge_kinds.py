"""``App.ui.badge.KINDS`` is pinned against the ``.badge--<kind>`` selectors in
``static/css/*.css`` (M25 F1 L4, AC5): adding a CSS modifier without the factory
list (or the reverse) fails here."""

from __future__ import annotations

import re

from tests._ui_guard_helpers import UI_DIR

CSS_DIR = UI_DIR.parents[1] / "css"
_KINDS_ARRAY = re.compile(r"var BADGE_KINDS = \[(.*?)\];", re.S)
_CSS_KIND = re.compile(r"\.badge--([a-z][a-z-]*)")


def _factory_kinds() -> set[str]:
    m = _KINDS_ARRAY.search((UI_DIR / "feedback.js").read_text())
    assert m, "BADGE_KINDS array not found in ui/feedback.js"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def _css_kinds() -> set[str]:
    kinds: set[str] = set()
    for css in sorted(CSS_DIR.glob("*.css")):
        text = re.sub(r"/\*.*?\*/", "", css.read_text(), flags=re.S)
        kinds.update(_CSS_KIND.findall(text))
    return kinds


def test_badge_kinds_match_css_modifiers() -> None:
    assert _factory_kinds() == _css_kinds()


def test_badge_kind_count() -> None:
    assert len(_factory_kinds()) == 14
