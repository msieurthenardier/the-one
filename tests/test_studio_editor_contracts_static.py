"""Static pins for the studio editor contracts (squawk 0235, M31 F3 L01).

The studio ``state`` object is a closure-local ``var state = {...}`` inside
``init`` in ``studio.js``, so a unit test cannot reach it; these checks parse the
source instead. See ``the_one/agents.md`` "Editor contracts (M31 F3 L01)".
"""

from __future__ import annotations

import re
from pathlib import Path

STUDIO_JS = Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static/js/areas"
SHELL = STUDIO_JS / "studio.js"
MODULES = sorted((STUDIO_JS / "studio").glob("*.js"))

# The documented set of ``state`` keys (21 at Mission 31 Flight 3 Leg 01). Adding or
# removing a key means updating this set AND the agents.md subsection.
STATE_KEYS = {
    "dirty",
    "snapshot",
    "tabHandle",
    "selectSeq",
    "editorGen",
    "mcpSourceFormMode",
    "editingMcpSource",
    "pendingMcpSourceId",
    "pendingMcpSourceFormMode",
    "connectorFormMode",
    "editingConnector",
    "pendingConnectorId",
    "pendingConnectorFormMode",
    "kbCreateMode",
    "kbFocusFolderFor",
    "knowledgeDetailHandle",
    "bootLoad",
    "knowledgeBases",
    "mcpSources",
    "connectors",
    "providersCache",
}

# Tabs whose builder returns no ``destroy``, each with its reason.
DESTROY_EXEMPT = {
    "general": "controls live in the panel and die with tabs.destroy(); no outside listeners",
    "rules-and-notes": "returns nothing; saves immediately, built once per identity",
}


def _strip_comments(src: str) -> str:
    """Remove // and /* */ comments; string literals are kept verbatim."""
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        two = src[i : i + 2]
        if two == "//":
            while i < n and src[i] != "\n":
                i += 1
        elif two == "/*":
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c in "'\"`":
            q = c
            start = i
            i += 1
            while i < n and src[i] != q:
                if src[i] == "\\":
                    i += 1
                i += 1
            i += 1
            out.append(src[start:i])
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _balanced(src: str, open_at: int) -> str:
    """The text from the ``{`` at open_at to its matching ``}``, string literals skipped."""
    depth, i = 0, open_at
    while i < len(src):
        c = src[i]
        if c in "'\"`":
            q = c
            i += 1
            while src[i] != q:
                i += 2 if src[i] == "\\" else 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[open_at : i + 1]
        i += 1
    raise AssertionError("unbalanced braces")


def _top_level_keys(literal: str) -> list[str]:
    keys, depth, i, start = [], 0, 0, 0
    body = literal[1:-1]
    while i < len(body):
        c = body[i]
        if c in "'\"`":
            q = c
            i += 1
            while body[i] != q:
                i += 2 if body[i] == "\\" else 1
        elif c in "{[(":
            depth += 1
        elif c in "}])":
            depth -= 1
        elif c == "," and depth == 0:
            keys.append(body[start:i])
            start = i + 1
        i += 1
    keys.append(body[start:])
    found = []
    for part in keys:
        m = re.match(r"\s*(\w+)\s*:", part)
        if m:
            found.append(m.group(1))
    return found


def _state_keys() -> list[str]:
    src = _strip_comments(SHELL.read_text(encoding="utf-8"))
    m = re.search(r"\bvar state = \{", src)
    assert m, "studio.js no longer declares `var state = {`"
    return _top_level_keys(_balanced(src, m.end() - 1))


def test_state_key_set_is_pinned() -> None:
    keys = _state_keys()
    assert len(keys) == len(set(keys)), "duplicate key in the state literal"
    assert set(keys) == STATE_KEYS, (
        f"added: {sorted(set(keys) - STATE_KEYS)}; removed: {sorted(STATE_KEYS - set(keys))}. "
        "Update STATE_KEYS and the agents.md 'Editor contracts' subsection."
    )


def test_every_state_write_names_a_declared_key() -> None:
    declared = set(_state_keys())
    write = re.compile(r"\bstate\.(\w+)\s*(?:=(?!=)|\+\+|--|\+=|-=)")
    bad: list[str] = []
    for path in [SHELL, *MODULES]:
        for name in write.findall(_strip_comments(path.read_text(encoding="utf-8"))):
            if name not in declared:
                bad.append(f"{path.name}: state.{name}")
    assert not bad, f"writes to undeclared state keys: {sorted(set(bad))}"


def _tab_files() -> dict[str, Path]:
    editor = _strip_comments((STUDIO_JS / "studio" / "agent-editor.js").read_text("utf-8"))
    ids = re.findall(r"\{\s*id:\s*'([\w-]+)',\s*label:", editor)
    assert len(ids) == 6, ids
    names = {"rules-and-notes": "rules-notes-tab.js"}
    return {i: STUDIO_JS / "studio" / names.get(i, f"{i}-tab.js") for i in ids}


def _returns_destroy(src: str) -> bool:
    """True when some `return {...}` at the builder's top level carries a destroy member."""
    for m in re.finditer(r"^    return \{", src, re.M):
        literal = _balanced(src, m.end() - 1)
        if "destroy" in _top_level_keys(literal):
            return True
    return False


def test_every_tab_returns_destroy_except_the_documented_exemptions() -> None:
    tabs = _tab_files()
    assert set(DESTROY_EXEMPT) <= set(tabs)
    for tab_id, path in tabs.items():
        src = _strip_comments(path.read_text(encoding="utf-8"))
        has = _returns_destroy(src)
        if tab_id in DESTROY_EXEMPT:
            assert not has, f"{tab_id} now returns destroy: drop it from DESTROY_EXEMPT"
        else:
            assert has, f"{path.name} returns a tab handle without destroy()"
