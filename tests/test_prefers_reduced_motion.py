"""Asserts the prefers-reduced-motion safeguard is present in base CSS."""

from __future__ import annotations

import re
from pathlib import Path


def test_prefers_reduced_motion_query_exists():
    css_dir = Path("the_one/interfaces/web/static/css")
    found = False
    for path in css_dir.glob("*.css"):
        content = path.read_text()
        if "prefers-reduced-motion" in content and re.search(
            r"\*,\s*\*::before,\s*\*::after",
            content,
        ):
            found = True
            break
    assert found, (
        "No prefers-reduced-motion universal-selector guard found in any "
        "static/css/*.css file. Add one to base.css."
    )
