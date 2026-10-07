"""Static check on the served shell: the sidebar landmark is never unlabelled
before the router's first commit (Flight 6 leg 1a, A5)."""

from __future__ import annotations

import re
from pathlib import Path

INDEX = Path("the_one/interfaces/web/static/index.html")


def test_sidebar_aside_has_an_initial_aria_label() -> None:
    html = INDEX.read_text()
    m = re.search(r"<aside\b[^>]*\bid=\"app-sidebar\"[^>]*>", html)
    assert m, "no #app-sidebar aside"
    label = re.search(r"\baria-label=\"([^\"]+)\"", m.group(0))
    assert label and label.group(1).strip()
