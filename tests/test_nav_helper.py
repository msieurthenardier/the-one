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
from _ui_guard_helpers import parse_registry
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
    # A bare Library section (and `library`, whose legacy form is the same
    # alias) folds to `library`: the legacy hash is the alias, the round trip
    # lands on the root (model-providers sortie, DD2).
    ("library", "#studio/knowledge"),
    ("library/providers", "#studio/providers"),
    ("library/providers/~new", "#studio/providers/new"),
    ("library/providers/p1", "#studio/providers/p1"),
    ("library/knowledge", "#studio/knowledge"),
    ("library/knowledge/kb1", "#studio/knowledge/kb1"),
    ("library/knowledge/~new", "#studio/knowledge/new"),
    ("library/mcp", "#studio/mcp-sources"),
    ("library/mcp/~new", "#studio/mcp-sources/new"),
    ("library/mcp/src1", "#studio/mcp-sources/src1"),
    ("library/connectors", "#studio/connectors"),
    ("library/connectors/~new", "#studio/connectors/new"),
    ("library/connectors/c1", "#studio/connectors/c1"),
    ("settings", "#admin"),
    ("settings/appearance", "#admin/appearance"),
    ("settings/date-and-time", "#admin/date-and-time"),
    ("settings/prompts", "#admin/prompts"),
    ("settings/encryption", "#admin/encryption"),
    ("settings/tools", "#admin/tools"),
    ("settings/tools/web_search", "#admin/tools/web_search"),
    ("settings/knowledge-indexing", "#admin/knowledge"),
]


@pytest.mark.parametrize(("route", "legacy"), DD2_ROWS)
def test_legacy_hash_rows(route, legacy):
    assert _nav.legacy_hash(route) == legacy


@pytest.mark.parametrize(("route", "legacy"), DD2_ROWS)
def test_round_trip_is_canonical(route, legacy):
    assert _nav.route_from_hash(_nav.legacy_hash(route)) == _nav.canonical(route)


def test_new_hash_is_hash_plus_route():
    assert _nav.new_hash("library/providers/~new") == "#library/providers/~new"
    assert _nav.new_hash("chats") == "#chats"


def test_canonical_folds_default_redirects():
    assert _nav.canonical("settings") == "settings/appearance"
    assert _nav.canonical("library") == "library"
    # A bare Library section is the app's alias for the root; an item or a
    # create route is not folded.
    for section in ("knowledge", "mcp", "connectors", "providers"):
        assert _nav.canonical(f"library/{section}") == "library"
        assert _nav.canonical(f"library/{section}/x") == f"library/{section}/x"
        assert _nav.canonical(f"library/{section}/~new") == f"library/{section}/~new"
    assert _nav.canonical("agents") == "agents"
    # the observed legacy defaults map to the same canonical route
    assert _nav.route_from_hash("#studio") == _nav.route_from_hash("#studio/agents") == "agents"
    assert _nav.route_from_hash("#admin") == _nav.route_from_hash("#admin/general")
    assert _nav.route_from_hash("#admin/system") == "settings/appearance"
    assert _nav.route_from_hash("#admin/general") == "settings/appearance"
    assert _nav.route_from_hash("#studio/tools") == "agents"


def test_settings_general_is_not_folded():
    """M25 F3 leg 5a: the app redirects settings/general to settings/appearance.

    ``canonical`` never folds it, so a page that stayed on settings/general
    fails ``expect_route(page, "settings/appearance")`` (a missing redirect is
    caught), and ``legacy_hash`` rejects it as an unknown route.
    """
    assert _nav.canonical("settings/general") == "settings/general"
    assert not _nav.routes_equal("settings/general", "settings/appearance")
    with pytest.raises(ValueError):
        _nav.legacy_hash("settings/general")


def test_chats_new_route_canonical_and_no_legacy_form():
    """M25 F4 leg 3b (AC11): ``#chats/~new/{agent}`` is the pending new chat.

    ``canonical`` folds a bare ``chats/~new`` to ``chats`` (the app's own
    redirect) and keeps the agent form; ``legacy_hash`` raises for it, since it
    never had a legacy form (so it is not a ``DD2_ROWS`` row).
    """
    assert _nav.canonical("chats/~new") == "chats"
    assert _nav.canonical("#chats/~new/") == "chats"
    assert _nav.canonical("chats/~new/Alpha") == "chats/~new/Alpha"
    assert _nav.canonical("chats/~new/My Agent") == "chats/~new/My%20Agent"
    assert _nav.canonical("chats/~new/%7Ex") == "chats/~new/%7Ex"
    assert _nav.routes_equal("chats/~new", "chats")
    assert not _nav.routes_equal("chats/~new/a", "chats")
    for route in ("chats/~new/Alpha", "chats/~new", "chats/~new/a/b"):
        with pytest.raises(ValueError):
            _nav.legacy_hash(route)
    assert not [r for r, _ in DD2_ROWS if r.startswith("chats/~new")]
    # A session id still maps as before.
    assert _nav.legacy_hash("chats/abc") == "#chat/sessions/abc"


def test_per_segment_comparison():
    assert _nav.routes_equal("agents/My%20Agent/tools", "agents/My Agent/tools")
    # %2F inside an id is NOT a path separator
    assert not _nav.routes_equal("agents/a%2Fb", "agents/a/b")
    assert _nav.canonical("agents/a%2Fb") == "agents/a%2Fb"
    assert _nav.route_from_hash("#studio/agents/a%2Fb/general") == "agents/a%2Fb/general"
    assert _nav.route_from_hash("#studio/agents/My Agent") == "agents/My%20Agent"


def test_settings_providers_is_an_unknown_route():
    """Sortie 02 (DD8): Settings no longer has a Providers page, so the helper
    maps no ``settings/providers`` route (the app resolves it as unknown)."""
    for route in ("settings/providers", "settings/providers/~new", "settings/providers/p1"):
        with pytest.raises(ValueError):
            _nav.legacy_hash(route)


def test_new_scoping_only_for_library():
    assert _nav.legacy_hash("library/providers/~new") == "#studio/providers/new"
    assert _nav.legacy_hash("library/mcp/~new") == "#studio/mcp-sources/new"
    # M25 F3 L4a: knowledge bases and connectors are creatable too.
    assert _nav.legacy_hash("library/knowledge/~new") == "#studio/knowledge/new"
    assert _nav.legacy_hash("library/connectors/~new") == "#studio/connectors/new"
    assert _nav.route_from_hash("#studio/knowledge/new") == "library/knowledge/~new"
    assert _nav.route_from_hash("#studio/connectors/new") == "library/connectors/~new"
    # An agent literally named "new" stays an agent named "new".
    assert _nav.legacy_hash("agents/new/general") == "#studio/agents/new/general"
    assert _nav.route_from_hash("#studio/agents/new/general") == "agents/new/general"
    assert _nav.route_from_hash("#studio/mcp-sources/new") == "library/mcp/~new"
    assert _nav.route_from_hash("#studio/providers/new") == "library/providers/~new"
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
    assert _nav.hash_for("library/providers/~new") == "#studio/providers/new"
    assert _nav.href("agents") == "#studio"
    monkeypatch.setattr(_nav, "SCHEME", "new")
    assert _nav.hash_for("library/providers/~new") == "#library/providers/~new"
    assert _nav.href("agents") == "#agents"
    assert _nav.route_from_hash("#settings") == "settings/appearance"
    assert _nav.route_from_hash("#library/mcp/~new") == "library/mcp/~new"


def test_goto_builds_absolute_url_and_passes_kwargs():
    calls = []

    class FakePage:
        def goto(self, url, **kw):
            calls.append((url, kw))

    _nav.goto(FakePage(), "http://127.0.0.1:9/", "library/providers/~new", wait_until="commit")
    assert calls == [("http://127.0.0.1:9/#studio/providers/new", {"wait_until": "commit"})]


def test_legacy_url_tests_are_well_formed():
    assert len(_nav.LEGACY_URL_TESTS) >= 6
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
    sibling = listed + '\n\ndef test_unlisted(page, b):\n    page.goto(f"{b}#admin/tools")\n'
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


# ── No `settings/providers` route literals (model-providers sortie, DD8, leg 2) ──

# Settings no longer has a Providers page (its routes are unknown), so no browser
# test or helper may name the route as a string literal.  Docstrings and comments
# are exempt (as with the guards above), and so are the router's own contract
# tests (``ROUTER_CONTRACT_GLOB``), which pin that the route is unknown.
_SETTINGS_PROVIDERS_RE = re.compile(r"settings/providers")


def find_settings_providers_literals(source: str, filename: str) -> list[str]:
    if fnmatch.fnmatch(filename, ROUTER_CONTRACT_GLOB):
        return []
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    return [
        f"{filename}:{node.lineno}: {node.value[:80]!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skip
        and _SETTINGS_PROVIDERS_RE.search(node.value)
    ]


def test_no_settings_providers_route_in_browser_tests():
    violations: list[str] = []
    for path in sorted(BROWSER_DIR.glob("*.py")):
        violations += find_settings_providers_literals(path.read_text(), path.name)
    assert not violations, "`settings/providers` route literals:\n" + "\n".join(violations)


def test_settings_providers_guard_self_test():
    bad = 'def test_a(page):\n    _nav.goto(page, base, "settings/providers/~new")\n'
    assert len(find_settings_providers_literals(bad, "test_x.py")) == 1
    ok_doc = 'def test_a(page):\n    """Used to open settings/providers."""\n    pass\n'
    assert find_settings_providers_literals(ok_doc, "test_x.py") == []
    comment = "def test_a(page):\n    # settings/providers is gone\n    pass\n"
    assert find_settings_providers_literals(comment, "test_x.py") == []
    assert find_settings_providers_literals(bad, "test_router_core.py") == []
    assert len(find_settings_providers_literals(bad, "test_routerish.py")) == 1
    ok = 'def test_a(page):\n    _nav.goto(page, base, "library/providers/~new")\n'
    assert find_settings_providers_literals(ok, "test_x.py") == []


# ── Retired-selector guard (M25 F3 L1, DD11; unconditional since L6) ─────

# Selectors of the surfaces Flight 3 retired: the entity tiles, the section nav
# (DD6), the Back controls (DD2), the Library grids' create CTAs (leg 4a, DD5:
# the Library list's Add menu replaces them) and the agent tiles' tool counts
# (leg 3).  Flight 4 leg 4a (DD12) adds the old chat history list's class
# fragments: ``session-item`` (and its ``-title``/``-agent``/``-source``
# parts), ``session-list``, ``session-group`` and ``list-item-delete`` (the
# Chats list is an App.ui.listPane; tests reach its rows through
# ``tests/browser/_chats.py``).  ``list-item-delete`` is fenced for browser
# tests only: the Design language page's surfaces demo keeps the class.
# Flight 4 leg 4b (DD3, DD6, DD12) adds the chat pane's retired surfaces: the
# header's ``new-chat-btn`` (a testid, also in the registry's Retired table)
# and two class fragments, ``chat-welcome-item`` (the welcome's agent options,
# with their ``-name``/``-meta`` parts) and ``session-agent-badge`` (the old
# header's h2), plus ``chat-welcome-list`` (the welcome listbox that held the
# options).  They replace the leg 3a chat-seam guard (``CHAT_SEAM_*``), which
# fenced the first two outside ``_chats.py`` while the flight migrated; the
# seam module is now checked like every other file.  The KEPT welcome surface
# is NOT retired: the ``chat-welcome`` testid (the pane's empty and guidance
# state) and its ``chat-welcome-mascot`` / ``-greeting`` / ``-prompt`` /
# ``-guidance`` / ``-link`` / ``-notice`` / ``-inner`` / ``-actions`` classes
# stay live (no entry here is a prefix of them).
# Browser tests reach list rows through ``tests/browser/_lists.py`` instead.
# An id never leaves this tuple: a retired surface cannot come back into a
# test.  ``test_retired_selectors_cover_the_registry_retired_table`` pins the
# union with ``RETIRED_EXACT`` against ``docs/ui-testid-registry.md``'s
# "Retired testids" table.
RETIRED_SELECTORS = (
    "base-prompt-content",
    "platform-variant-",
    "ui-demo-chooser",
    "ui-demo-chooser-close",
    "ui-demo-chooser-row",
    "ui-demo-chooser-search",
    "ui-demo-drawer-",
    "ui-demo-drawer-toggle-",
    "ui-demo-modal",
    "entity-tile",
    "section-nav-item",
    "back-agent-btn",
    "back-knowledge-btn",
    "back-mcp-source-btn",
    "back-connector-btn",
    "back-provider-btn",
    "back-tool-btn",
    "new-knowledge-base-btn",
    "new-mcp-source-btn",
    "new-connector-btn",
    "agent-tile-tool-count",
    "agent-tile-mcp-tool-count",
    "session-item",
    "session-list",
    "session-group",
    "list-item-delete",
    "new-chat-btn",
    "chat-welcome-item",
    "notes-row-check",
    "chat-drawer-notes-check",
    "chat-drawer-notes-clear",
    "chat-drawer-notes-delete",
    "chat-drawer-notes-edit-link",
    "chat-drawer-notes-failed",
    "chat-drawer-notes-status",
    "chat-drawer-rules-edit-link",
    "chat-welcome-list",
    "session-agent-badge",
    # Flight 4 leg 5: the composer's old single-line row (its controls keep
    # their testids inside the new ``.composer-box``).
    "input-area",
    # Model-providers sortie (DD6, DD8): the Library start page's testids were
    # renamed (`library-start`, `library-start-{group}-add`) when `#library`
    # became the one root; a prefix, so every `library-empty-*` id is fenced.
    "library-empty-",
    # Model-providers sortie, leg 2 (DD8): Settings no longer hosts providers.
    # ``providers-empty`` covers ``providers-empty-add``; ``settings-nav-providers``
    # is fenced here only (``settings-nav-`` stays a live registry prefix, so it
    # is not in the Retired table); ``provider-tile`` is the retired tile class
    # (``provider-tile-link`` and friends). ``providers-list`` is deliberately
    # NOT fenced: it would catch future ``providers-list-*`` ids.
    "new-provider-btn",
    "providers-empty",
    "settings-nav-providers",
    "provider-tile",
    # M31 F3 HAT: "Other items" is renamed "Individual files"
    # (``kb-individual-files-panel``).
    "kb-other-items-panel",
    # M31 F4 L08a: the Appearance page's segmented toggle host is replaced by the
    # ``theme-picker`` radio group.
    "admin-theme-toggle-mount",
)
# Retired ids matched EXACTLY, with a right boundary too (Flight 4 leg 4a,
# DD12): the chat sidebar's ``agent-select`` dropdown, whose name is a prefix
# of the live Flight 3 testid ``agent-select-empty`` (the Agents detail
# pane's empty state), which must stay usable.
RETIRED_EXACT = ("agent-select",)
# RETIRED_SELECTORS take a left boundary only: ``entity-tile-name`` is part of
# the retired tile, while a longer id that merely ends in one
# (``feedback-agent-btn``) is not.  RETIRED_EXACT entries take both.
_RETIRED_RE = re.compile(
    r"(?<![\w-])(?:"
    + "|".join(re.escape(s) for s in RETIRED_SELECTORS)
    + r")|(?<![\w-])(?:"
    + "|".join(re.escape(s) for s in RETIRED_EXACT)
    + r")(?![\w-])"
)

# The guard is unconditional.  While Flight 3 migrated the browser tests leg by
# leg (M25 F3 L1-L5b), a per-file allow-list held the files that still named a
# retired surface: 29 at leg 1, empty after leg 5b.  Leg 6 removed the
# allow-list mechanism itself, so no file can be exempted again: every browser
# test file and every helper module is checked alike.  Docstrings and comments
# stay exempt (they may describe a retired surface); string literals never are.
# The flight log (missions/25-workbench-navigation/flights/03-list-and-detail)
# records which leg migrated which file.


def _selector_hits(source: str, filename: str, pattern: re.Pattern[str]) -> list[str]:
    """Matches of *pattern* in string literals (docstrings and comments exempt).

    The walk sees every Python string literal, including JS passed to
    ``page.evaluate``.
    """
    tree = ast.parse(source)
    skip = _docstring_nodes(tree)
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in skip:
            continue
        hits = sorted(set(pattern.findall(node.value)))
        if hits:
            out.append(f"{filename}:{node.lineno}: {', '.join(hits)} in {node.value[:80]!r}")
    return out


def find_retired_selectors(source: str, filename: str) -> list[str]:
    """Retired selectors named in string literals (docstrings and comments exempt).

    The walk sees every Python string literal, including JS passed to
    ``page.evaluate``.
    """
    return _selector_hits(source, filename, _RETIRED_RE)


def check_retired_selectors(sources: dict[str, str]) -> list[str]:
    """Every retired-selector hit in *sources* (basename -> source).

    There is no exemption by file: a test module and a helper module fail alike.
    """
    problems: list[str] = []
    for name, source in sorted(sources.items()):
        problems += find_retired_selectors(source, name)
    return problems


def test_retired_selector_guard_self_test():
    clean = 'def test_a(page):\n    page.locator("[data-testid=agent-item]").click()\n'
    tile = 'def test_a(page):\n    page.locator(".entity-tile").first.click()\n'
    back = "def test_a(page):\n    page.click('[data-testid=\"back-agent-btn\"]')\n"
    in_js = (
        "def test_a(page):\n    page.evaluate(\"document.querySelector('.section-nav-item')\")\n"
    )
    count = 'def test_a(page):\n    page.get_by_test_id("agent-tile-tool-count")\n'
    doc = 'def test_a(page):\n    """Replaces .entity-tile and back-tool-btn."""\n    pass\n'
    comment = "def test_a(page):\n    # was .section-nav-item\n    pass\n"
    longer = 'def test_a(page):\n    page.click("#feedback-agent-btn")\n'
    # Flight 4 leg 4a: the old chat history list's fragments, and the exact id.
    session = "def test_a(page):\n    page.locator('.session-item-title').first\n"
    group = "def test_a(page):\n    page.locator('.session-group-label')\n"
    delete = 'def test_a(page):\n    page.locator(".list-item .list-item-delete").click()\n'
    dropdown = "def test_a(page):\n    page.locator('[data-testid=\"agent-select\"]')\n"
    empty = "def test_a(page):\n    page.locator('[data-testid=\"agent-select-empty\"]')\n"
    frame = 'def test_a(page):\n    assert f["type"] == "session_list"\n'
    # Flight 4 leg 4b: the chat pane's retired header and welcome list.
    header_btn = "def test_a(page):\n    page.locator('[data-testid=\"new-chat-btn\"]').click()\n"
    option = 'def test_a(page):\n    page.locator(".chat-welcome-item-name")\n'
    listbox = "def test_a(page):\n    page.locator('.chat-welcome-list')\n"
    badge = (
        "def test_a(page):\n    page.evaluate(\"document.querySelector('.session-agent-badge')\")\n"
    )
    kept = (
        "def test_a(page):\n"
        "    page.locator('[data-testid=\"chat-welcome\"] .chat-welcome-greeting')\n"
        "    page.locator('.chat-welcome-prompt, .chat-welcome-guidance, .chat-welcome-link')\n"
        "    page.locator('[data-testid=\"chat-welcome-mascot\"]')\n"
        "    page.locator('[data-testid=\"chats-new-btn\"]')\n"
        "    page.locator('[data-testid=\"chat-empty-new-btn\"]')\n"
    )
    # Flight 4 leg 5: the composer's old row; the box and the kept testids pass.
    row = "def test_a(page):\n    page.locator('.area-chat .input-area')\n"
    composer = (
        "def test_a(page):\n"
        "    page.locator('.composer-box [data-testid=\"chat-input\"]')\n"
        "    page.locator('[data-testid=\"chat-send-btn\"], .composer-telemetry')\n"
    )
    for src in (header_btn, option, listbox, badge, row):
        assert len(find_retired_selectors(src, "t.py")) == 1, src
    assert find_retired_selectors(composer, "t.py") == []
    assert find_retired_selectors(kept, "t.py") == []  # the kept welcome surface
    # The former chat-seam module is no longer exempt.
    problems = check_retired_selectors({"_chats.py": badge})
    assert len(problems) == 1 and problems[0].startswith("_chats.py:"), problems
    assert len(find_retired_selectors(session, "t.py")) == 1
    assert len(find_retired_selectors(group, "t.py")) == 1
    assert len(find_retired_selectors(delete, "t.py")) == 1
    assert len(find_retired_selectors(dropdown, "t.py")) == 1
    assert find_retired_selectors(empty, "t.py") == []  # the live Flight 3 id
    assert find_retired_selectors(frame, "t.py") == []  # the WebSocket frame type
    assert len(find_retired_selectors(tile, "t.py")) == 1
    assert len(find_retired_selectors(back, "t.py")) == 1
    assert len(find_retired_selectors(in_js, "t.py")) == 1  # JS passed to evaluate counts
    assert len(find_retired_selectors(count, "t.py")) == 1
    assert find_retired_selectors(doc, "t.py") == []  # docstring mention: exempt
    assert find_retired_selectors(comment, "t.py") == []  # comment mention: exempt
    assert find_retired_selectors(longer, "t.py") == []
    assert find_retired_selectors(clean, "t.py") == []
    # No file is exempt: a test module and a helper module fail alike, whatever
    # their names (the per-file allow-list the migration used is gone).
    for name in ("test_old.py", "test_router_core.py", "_lists.py", "conftest.py"):
        problems = check_retired_selectors({name: tile, "test_clean.py": clean + doc + comment})
        assert len(problems) == 1 and problems[0].startswith(f"{name}:"), (name, problems)
    assert check_retired_selectors({"test_doc.py": doc + comment}) == []


def test_retired_exact_spares_the_live_agent_select_empty():
    """``agent-select`` is retired, but the live Flight 3 testid
    ``agent-select-empty`` (the Agents detail pane's empty state) is not: the
    helper that names it passes the guard, while the bare id fails."""
    lists = (BROWSER_DIR / "_lists.py").read_text()
    assert '[data-testid="agent-select-empty"]' in lists
    assert find_retired_selectors(lists, "_lists.py") == []
    assert _RETIRED_RE.findall('[data-testid="agent-select-empty"]') == []
    assert _RETIRED_RE.findall('[data-testid="agent-select"]') == ["agent-select"]
    assert _RETIRED_RE.findall("#agent-select.x") == ["agent-select"]


def test_no_retired_selectors_in_browser_tests():
    sources = {p.name: p.read_text() for p in sorted(BROWSER_DIR.glob("*.py"))}
    # The walk is not vacuous: it covers the test files and the helper modules
    # (``_chats.py`` included since Flight 4 leg 4b retired its seam guard).
    assert {"_nav.py", "_lists.py", "_chats.py", "seeders.py", "conftest.py"} <= set(sources)
    assert sum(name.startswith("test_") for name in sources) > 50
    problems = check_retired_selectors(sources)
    assert not problems, (
        "retired selectors in browser tests or helpers (reach rows through "
        "tests/browser/_lists.py; the guard exempts no file):\n" + "\n".join(problems)
    )


REGISTRY_DOC = Path(__file__).resolve().parent.parent / "docs" / "ui-testid-registry.md"
_REGISTRY_ROW = re.compile(r"^\|\s*`([^`|]+)`\s*\|")


def _registry_retired_ids() -> list[str]:
    """First-column ids of the registry's "Retired testids" table, in order."""
    ids: list[str] = []
    inside = False
    for line in REGISTRY_DOC.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            inside = stripped.lstrip("#").strip().lower().startswith("retired testids")
            continue
        m = _REGISTRY_ROW.match(stripped) if inside else None
        if m:
            ids.append(m.group(1).strip())
    return ids


def test_retired_selectors_cover_the_registry_retired_table():
    """A retired id cannot come back: every id the registry records as retired is
    fenced, and none of Flight 3's retired surfaces ever leaves the tuple."""
    retired = _registry_retired_ids()
    assert len(retired) >= 12, retired  # the table is found and parsed
    fenced = RETIRED_SELECTORS + RETIRED_EXACT
    assert len(set(fenced)) == len(fenced)
    missing = sorted(set(retired) - set(fenced))
    assert not missing, (
        f"registry-retired ids missing from RETIRED_SELECTORS / RETIRED_EXACT: {missing}"
    )
    assert "agent-select" in retired and "agent-select" in RETIRED_EXACT  # Flight 4 leg 4a
    assert "new-chat-btn" in retired and "new-chat-btn" in RETIRED_SELECTORS  # Flight 4 leg 4b
    flight3 = {
        "entity-tile",
        "section-nav-item",
        *(f"back-{s}-btn" for s in ("agent", "knowledge", "mcp-source", "connector")),
        *(f"back-{s}-btn" for s in ("provider", "tool")),
        "new-knowledge-base-btn",
        "new-mcp-source-btn",
        "new-connector-btn",
    }
    assert flight3 <= set(RETIRED_SELECTORS)
    # ...and none of them is live again: the registry sync (test_ui_guards) forces
    # a testid back in source into the live tables, where this fails.
    literals, prefixes, manual = parse_registry(REGISTRY_DOC)
    revived = sorted(set(retired) & set(literals + manual))
    revived += sorted(r for r in retired for p in prefixes if r.startswith(p))
    assert not revived, f"retired testids registered as live again: {revived}"


# ── No bare-section producers (model-providers sortie, DD2) ──────────────────

_STATIC_JS = (
    Path(__file__).resolve().parents[1] / "the_one" / "interfaces" / "web" / "static" / "js"
)
_LIBRARY_HREF_RE = re.compile(r"href\(\s*\{[^{}]*?destination:\s*'library'[^{}]*?\}", re.S)
_BARE_SYNC_RE = re.compile(
    r"sync\(\s*'studio'\s*,\s*'(?:knowledge|mcp-sources|connectors|providers)'\s*[,)]"
)


def test_no_bare_library_section_producers_in_static_js():
    """`#library` is the only Library root and a bare `library/{section}` is an
    alias nothing may produce: no `href({destination: 'library', section: X})`
    without an id or `create`, and no `sync('studio', '<section>')` with a bare
    section sub (a bare sync writes the URL without hydrating)."""
    offenders: list[str] = []
    for path in sorted(_STATIC_JS.rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        for m in _LIBRARY_HREF_RE.finditer(text):
            spec = m.group(0)
            if "section" in spec and "id:" not in spec and "create" not in spec:
                offenders.append(f"{path.relative_to(_STATIC_JS)}: {' '.join(spec.split())}")
        for m in _BARE_SYNC_RE.finditer(text):
            offenders.append(f"{path.relative_to(_STATIC_JS)}: {m.group(0)}")
    assert not offenders, "bare Library section producers:\n" + "\n".join(offenders)


def test_bare_library_section_check_detects_a_producer():
    """The check's own regexes: a bare section href and a bare sync match, an
    item or create href and a Settings section href do not."""
    bad = "App.router.href({ destination: 'library', section: 'mcp' })"
    assert _LIBRARY_HREF_RE.search(bad) and "id:" not in bad
    assert _BARE_SYNC_RE.search("App.router.sync('studio', 'connectors');")
    assert not _BARE_SYNC_RE.search("App.router.sync('studio', 'connectors/' + id, {})")
    assert not _BARE_SYNC_RE.search("App.router.sync('studio', 'agents')")
    ok = "href({ destination: 'library', section: g.route, id: row.id })"
    assert "id:" in _LIBRARY_HREF_RE.search(ok).group(0)
