"""components.css keeps every rule inside an ``@layer`` block (M31 F6 L03a).

Unlayered rules beat every layered rule, so one stray rule after the last layer silently
outranks the whole cascade. The scanner accepts one-line ``@layer`` blocks, ``@media``
blocks nested inside a layer, a bare ``@layer a, b;`` order statement and comments.
"""

from __future__ import annotations

import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static/css/components.css"


def unlayered_rules(css: str) -> list[str]:
    """The top-level statements of ``css`` that are neither an ``@layer`` block nor an
    ``@layer`` order statement."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(css):
        if ch == "{":
            if depth == 0:
                prelude = css[start:i].strip()
                if not re.match(r"@layer\b", prelude):
                    found.append(prelude)
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                start = i + 1
        elif ch == ";" and depth == 0:
            statement = css[start : i + 1].strip()
            if not re.match(r"@layer\b[^{]*;$", statement):
                found.append(statement)
            start = i + 1
    assert depth == 0, "unbalanced braces in components.css"
    rest = css[start:].strip()
    if rest:
        found.append(rest)
    return found


def test_components_css_has_no_rule_outside_a_layer() -> None:
    assert unlayered_rules(CSS.read_text()) == []


def test_scanner_accepts_layer_forms_and_rejects_a_stray_rule() -> None:
    ok = (
        "@layer a, b;\n/* c { x: y } */\n"
        "@layer a { .x { y: z } @media (a) { .q { r: s } } }\n@layer b { .k{l:m} }"
    )
    assert unlayered_rules(ok) == []
    assert unlayered_rules(ok + "\n.stray { color: red; }") == [".stray"]
    assert unlayered_rules(ok + "\n@media (a) { .stray { color: red } }") == ["@media (a)"]
