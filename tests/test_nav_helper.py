"""Unit tests for ``tests/browser/_nav.py`` and the browser-test migration guard.

Unmarked on purpose: these run in ``make test-unit`` with no browser. See
``_nav.py``'s docstring for the route table and the scheme switch.
"""

from __future__ import annotations

import ast
import fnmatch
import re
from pathlib import Path

import pytest
from browser import _nav

BROWSER_DIR = Path(__file__).parent / "browser"


@pytest.fixture(autouse=True)
def _legacy_scheme(monkeypatch):
    monkeypatch.setattr(_nav, "SCHEME", "legacy")


# Every DD2 row (new route -> legacy hash), plus the bare destinations.
DD2_ROWS = [
    ("chats", "#chat"),
    ("chats/abc123", "#chat/sessions/abc123"),
    ("agents", "#studio"),
    ("agents/foo", "#studio/agents/foo"),
    ("agents/foo/general", "#studio/agents/foo/general"),
    ("agents/foo/mcps/src1", "#studio/agents/foo/mcps/src1"),
    ("agents/foo/self-configuration", "#studio/agents/foo/self-configuration"),
    ("library", "#studio/knowledge"),
    ("library/knowledge", "#studio/knowledge"),
    ("library/knowledge/kb1", "#studio/knowledge/kb1"),
    ("library/mcp", "#studio/mcp-sources"),
    ("library/mcp/~new", "#studio/mcp-sources/new"),
    ("library/mcp/src1", "#studio/mcp-sources/src1"),
    ("library/connectors", "#studio/connectors"),
    ("settings", "#admin"),
    ("settings/general", "#admin/general"),
    ("settings/providers", "#admin/providers"),
    ("settings/providers/~new", "#admin/providers/new"),
    ("settings/providers/p1", "#admin/providers/p1"),
    ("settings/tools", "#admin/tools"),
    ("settings/tools/web_search", "#admin/tools/web_search"),
    ("settings/knowledge-indexing", "#admin/knowledge"),
    ("settings/design-language", "#admin/design-language"),
]


@pytest.mark.parametrize(("route", "legacy"), DD2_ROWS)
def test_legacy_hash_rows(route, legacy):
    assert _nav.legacy_hash(route) == legacy


@pytest.mark.parametrize(("route", "legacy"), DD2_ROWS)
def test_round_trip_is_canonical(route, legacy):
    assert _nav.route_from_hash(_nav.legacy_hash(route)) == _nav.canonical(route)


def test_new_hash_is_hash_plus_route():
    assert _nav.new_hash("settings/providers/~new") == "#settings/providers/~new"
    assert _nav.new_hash("chats") == "#chats"


def test_canonical_folds_default_redirects():
    assert _nav.canonical("settings") == "settings/general"
    assert _nav.canonical("library") == "library/knowledge"
    assert _nav.canonical("agents") == "agents"
    # the observed legacy defaults map to the same canonical route
    assert _nav.route_from_hash("#studio") == _nav.route_from_hash("#studio/agents") == "agents"
    assert _nav.route_from_hash("#admin") == _nav.route_from_hash("#admin/general")
    assert _nav.route_from_hash("#admin/system") == "settings/general"
    assert _nav.route_from_hash("#studio/tools") == "agents"


def test_per_segment_comparison():
    assert _nav.routes_equal("agents/My%20Agent/tools", "agents/My Agent/tools")
    # %2F inside an id is NOT a path separator
    assert not _nav.routes_equal("agents/a%2Fb", "agents/a/b")
    assert _nav.canonical("agents/a%2Fb") == "agents/a%2Fb"
    assert _nav.route_from_hash("#studio/agents/a%2Fb/general") == "agents/a%2Fb/general"
    assert _nav.route_from_hash("#studio/agents/My Agent") == "agents/My%20Agent"


def test_new_scoping_only_for_providers_and_mcp():
    assert _nav.legacy_hash("settings/providers/~new") == "#admin/providers/new"
    assert _nav.legacy_hash("library/mcp/~new") == "#studio/mcp-sources/new"
    # An agent literally named "new" stays an agent named "new".
    assert _nav.legacy_hash("agents/new/general") == "#studio/agents/new/general"
    assert _nav.route_from_hash("#studio/agents/new/general") == "agents/new/general"
    assert _nav.route_from_hash("#studio/mcp-sources/new") == "library/mcp/~new"
    assert _nav.route_from_hash("#admin/providers/new") == "settings/providers/~new"
    # An id that is literally "new" under a different section is not rewritten.
    assert _nav.legacy_hash("settings/tools/new") == "#admin/tools/new"
    # An agent named "~new" is encoded, so it never equals the reserved segment.
    assert _nav.seg("~new") == "%7Enew"
    assert _nav.canonical("agents/%7Enew") == "agents/%7Enew"
    assert not _nav.routes_equal("library/mcp/~new", f"library/mcp/{_nav.seg('~new')}")


def test_seg_encoding_matches_encode_uri_component():
    assert _nav.seg("My Agent") == "My%20Agent"
    assert _nav.seg("a/b") == "a%2Fb"
    assert _nav.seg("é") == "%C3%A9"
    assert _nav.seg("日本") == "%E6%97%A5%E6%9C%AC"
    assert _nav.seg("~new") == "%7Enew"
    assert _nav.seg("a~b") == "a~b"  # only a LEADING ~ is encoded
    assert _nav.seg("!'()*") == "!'()*"  # unencoded in JS too
    assert _nav.seg("a-b_c.d") == "a-b_c.d"
    assert _nav.seg("a&b=c?d#e") == "a%26b%3Dc%3Fd%23e"


def test_scheme_switch(monkeypatch):
    assert _nav.hash_for("settings/providers/~new") == "#admin/providers/new"
    assert _nav.href("agents") == "#studio"
    monkeypatch.setattr(_nav, "SCHEME", "new")
    assert _nav.hash_for("settings/providers/~new") == "#settings/providers/~new"
    assert _nav.href("agents") == "#agents"
    assert _nav.route_from_hash("#settings") == "settings/general"
    assert _nav.route_from_hash("#library/mcp/~new") == "library/mcp/~new"


def test_goto_builds_absolute_url_and_passes_kwargs():
    calls = []

    class FakePage:
        def goto(self, url, **kw):
            calls.append((url, kw))

    _nav.goto(FakePage(), "http://127.0.0.1:9/", "settings/providers/~new", wait_until="commit")
    assert calls == [("http://127.0.0.1:9/#admin/providers/new", {"wait_until": "commit"})]


def test_legacy_url_tests_are_well_formed():
    assert len(_nav.LEGACY_URL_TESTS) >= 8
    for ident in _nav.LEGACY_URL_TESTS:
        assert re.fullmatch(r"test_\w+\.py::test_\w+", ident), ident
        assert ident in _nav.__doc__, f"{ident} missing from _nav.py docstring"


# ── Migration guard ───────────────────────────────────────────────────────

# The router's own contract tests (tests/browser/test_router_*.py) are exempt AT
# FILE LEVEL: they pin the literal legacy and new hashes the router must accept,
# redirect and emit, so they cannot go through ``_nav``'s mapping.  Every other
# file is still checked.
ROUTER_CONTRACT_GLOB = "test_router_*.py"
_ROUTE_RE = re.compile(r"(?<![\w&/])#(?:studio|admin|chats?|agents|library|settings)(?![\w-])")
_TOPBAR_MARKERS = (".app-picker-button", "nav-chat-btn", "#app-topbar")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def find_violations(source: str, filename: str, legacy: frozenset[str] | set[str]) -> list[str]:
    """Raw route hashes / top-bar selectors in string literals (not docstrings).

    Functions named ``filename::func`` in *legacy* are exempt, by enclosing
    ``FunctionDef`` span (never whole files).  The one whole-file exemption is
    the router contract tests (``ROUTER_CONTRACT_GLOB``).
    """
    if fnmatch.fnmatch(filename, ROUTER_CONTRACT_GLOB):
        return []
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    spans = [
        (n.lineno, n.end_lineno or n.lineno)
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and f"{filename}::{n.name}" in legacy
    ]
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in skip:
            continue
        text = node.value
        if not (_ROUTE_RE.search(text) or any(m in text for m in _TOPBAR_MARKERS)):
            continue
        if any(lo <= node.lineno <= hi for lo, hi in spans):
            continue
        out.append(f"{filename}:{node.lineno}: {text[:80]!r}")
    return out


def _function_has_raw_route(source: str, func: str) -> bool:
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == func:
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and id(node) not in skip
                    and _ROUTE_RE.search(node.value)
                ):
                    return True
    return False


def test_guard_self_test():
    legacy = {"test_x.py::test_listed"}
    ok_css = 'def test_a(page):\n    page.locator("#studio-model").click()\n'
    assert find_violations(ok_css, "test_x.py", legacy) == []
    ok_doc = 'def test_a(page):\n    """Opens #studio/agents."""\n    pass\n'
    assert find_violations(ok_doc, "test_x.py", legacy) == []
    bad_goto = 'def test_a(page, b):\n    page.goto(f"{b}#studio/agents")\n'
    assert len(find_violations(bad_goto, "test_x.py", legacy)) == 1
    listed = 'def test_listed(page, b):\n    page.goto(f"{b}#studio/agents")\n'
    assert find_violations(listed, "test_x.py", legacy) == []
    sibling = listed + '\n\ndef test_unlisted(page, b):\n    page.goto(f"{b}#admin/providers")\n'
    assert len(find_violations(sibling, "test_x.py", legacy)) == 1
    bad_top = 'def test_a(page):\n    page.click(".app-picker-button")\n'
    assert len(find_violations(bad_top, "test_x.py", legacy)) == 1
    comment_only = "def test_a(page):\n    # goes to #studio/agents\n    pass\n"
    assert find_violations(comment_only, "test_x.py", legacy) == []
    non_route = (
        "def test_a(page):\n    page.evaluate(\"document.querySelector('#main-content')\")\n"
    )
    assert find_violations(non_route, "test_x.py", legacy) == []
    # The router contract tests are exempt at file level -- and ONLY by name.
    router_src = 'def test_a(page, b):\n    page.goto(f"{b}#studio/agents")\n'
    assert find_violations(router_src, "test_router_core.py", legacy) == []
    assert len(find_violations(router_src, "test_routerish.py", legacy)) == 1
    assert len(find_violations(router_src, "test_flow_router_x.py", legacy)) == 1


def test_no_raw_route_hashes_in_browser_tests():
    legacy = _nav.LEGACY_URL_TESTS
    # Every allow-listed function must still exist (a rename can't orphan one).
    for ident in sorted(legacy):
        fname, func = ident.split("::")
        path = BROWSER_DIR / fname
        assert path.exists(), f"LEGACY_URL_TESTS file missing: {ident}"
        tree = ast.parse(path.read_text())
        names = {
            n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert func in names, f"LEGACY_URL_TESTS entry no longer exists: {ident}"
        # ...and must still carry a raw legacy route (else the entry is stale).
        assert _function_has_raw_route(path.read_text(), func), (
            f"LEGACY_URL_TESTS entry has no raw legacy route any more: {ident}"
        )
    violations: list[str] = []
    for path in sorted(BROWSER_DIR.glob("test_*.py")):
        violations += find_violations(path.read_text(), path.name, legacy)
    assert not violations, "raw route hashes / top-bar selectors outside _nav.py:\n" + "\n".join(
        violations
    )
