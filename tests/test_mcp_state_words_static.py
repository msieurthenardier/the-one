"""The MCP connection-state words have one source (M31 F5 L11, DD6).

The editor's status line (``mcp-connection-status.js``) and the Library list
(``library-pane.js``) read the words from ``App.usage.mcpStateLabel``; neither
file may carry one as a literal, so the two readers cannot drift apart.
"""

from __future__ import annotations

import re
from pathlib import Path

STUDIO = Path(__file__).resolve().parent.parent / ("the_one/interfaces/web/static/js/areas/studio")
STORE = STUDIO.parent.parent / "store.js"

# "Couldn't connect" may be written with a straight, a curly or an escaped apostrophe.
WORDS = {
    "Sign-in needed": re.compile(r"Sign-in needed"),
    "Couldn't connect": re.compile(r"Couldn(?:'|’|\\u2019|\\')t connect"),
    "Not connected": re.compile(r"Not connected"),
    "Connected": re.compile(r"\bConnected\b"),
}


def _code_only(text: str) -> str:
    """The file with block and line comments removed (strings are kept)."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$|(?<=\s)//\s.*$", "", text)


def test_the_two_readers_carry_no_state_word_literal() -> None:
    for name in ("mcp-connection-status.js", "library-pane.js"):
        code = _code_only((STUDIO / name).read_text(encoding="utf-8"))
        for word, pattern in WORDS.items():
            assert not pattern.search(code), f"{name} carries the literal {word!r}"


def test_the_one_source_carries_all_four_words() -> None:
    code = STORE.read_text(encoding="utf-8")
    for word, pattern in WORDS.items():
        assert pattern.search(code), f"store.js lost {word!r}"


def test_both_readers_use_the_one_derivation() -> None:
    status = (STUDIO / "mcp-connection-status.js").read_text(encoding="utf-8")
    pane = (STUDIO / "library-pane.js").read_text(encoding="utf-8")
    assert "App.usage.mcpStateLabel" in status
    assert "App.usage.mcpStateLabel" in pane and "App.usage.mcpState(" in pane
