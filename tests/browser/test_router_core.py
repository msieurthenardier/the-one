"""Router contract tests (M25 F2 L3, AC2-AC7, AC13).

These are the router's own contract tests, so they use LITERAL legacy and new
hashes -- the migration guard exempts ``tests/browser/test_router_*.py`` at
file level (see ``tests/test_nav_helper.py::ROUTER_CONTRACT_GLOB``).

Covers: the route builder/parser round trip and `~` output encoding; every DD2
redirect row (boot and traversal, replaceState) and JS<->``_nav`` parity; boot,
unknown and element-id hash rules; the pinned go()/traversal commit sequence;
the `sync` drop rules (incl. chat's reconnect auto-join from Settings); seq
history, Stay/Continue and joins; squawk 0082.
"""

from __future__ import annotations

import pytest
from browser import _chats, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def _boot(page: Page, base: str, hash_: str = "", *, settled: bool = True) -> None:
    """Load the app at a RAW hash and wait for the router to commit a route."""
    page.goto(base + "/" + hash_)
    page.wait_for_function("() => !!(window.App && App.router && App.router.current())")
    if settled:
        page.wait_for_function(
            "() => !!document.querySelector('.content-panel.active[data-destination]')"
        )


# Records every history write (url argument) so a test can see WHICH primitive
# the router used and what it wrote first, independent of what the area
# canonicalises the URL to later.
_RECORD_HISTORY_JS = """
(() => {
  window.__writes = [];
  for (const kind of ['replaceState', 'pushState']) {
    const orig = history[kind].bind(history);
    history[kind] = function (state, title, url) {
      window.__writes.push({ kind, url: String(url), state });
      return orig(state, title, url);
    };
  }
})();
"""


def _boot_recorded(page: Page, base: str, hash_: str) -> list[dict]:
    page.add_init_script(_RECORD_HISTORY_JS)
    _boot(page, base, hash_)
    return page.evaluate("window.__writes")


def _hold_guard(page: Page) -> None:
    """Replace the App.nav leave guard with one the test resolves by hand."""
    page.evaluate(
        """() => {
          window.__held = null;
          App.nav.isDirty = () => true;
          App.nav.confirmLeave = function () {
            return new Promise((resolve) => {
              window.__held = { proceed: () => resolve(true), abort: () => resolve(false) };
              App.confirmDialog.isOpen = () => true; // a pending decision, as a dialog would be
            });
          };
        }"""
    )


def _release(page: Page) -> None:
    page.evaluate("App.confirmDialog.isOpen = () => false")


# ── AC2: builder, parser, encoding ───────────────────────────────────────────

ROUND_TRIP_SPECS = [
    {"destination": "chats"},
    {"destination": "chats", "id": "abc 123"},
    # The pending new chat (M25 F4 L3b, DD2).
    {"destination": "chats", "create": True, "agent": "x"},
    {"destination": "chats", "create": True, "agent": "My ~Agent/é"},
    {"destination": "chats", "create": True, "agent": "~new"},
    {"destination": "agents"},
    {"destination": "agents", "create": True},
    {"destination": "agents", "id": "My Agent"},
    {"destination": "agents", "id": "a/b", "tab": "tools"},
    {"destination": "agents", "id": "日本語", "tab": "general"},
    {"destination": "agents", "id": "~new", "tab": "knowledge"},
    {"destination": "agents", "id": "x", "tab": "tools", "sub": "src/1 é"},
    {"destination": "agents", "id": "!'()*", "tab": "self-configuration"},
    {"destination": "library", "section": "providers", "create": True},
    {"destination": "library", "section": "providers", "id": "p/é!'()*~"},
    {"destination": "library", "section": "knowledge"},
    {"destination": "library", "section": "knowledge", "id": "kb 1"},
    {"destination": "library", "section": "knowledge", "create": True},
    {"destination": "library", "section": "mcp", "create": True},
    {"destination": "library", "section": "mcp", "id": "~src"},
    {"destination": "library", "section": "connectors"},
    {"destination": "library", "section": "connectors", "create": True},
    {"destination": "library", "section": "connectors", "id": "conn 1"},
    {"destination": "settings", "section": "appearance"},
    {"destination": "settings", "section": "date-and-time"},
    {"destination": "settings", "section": "prompts"},
    {"destination": "settings", "section": "encryption"},
    {"destination": "settings", "section": "tools", "id": "web search"},
    {"destination": "settings", "section": "knowledge-indexing"},
]


def test_href_parse_round_trip(app_clean: str, page: Page) -> None:
    _boot(page, app_clean)
    got = page.evaluate(
        "specs => specs.map(s => { const h = App.router.href(s); "
        "return { h, p: App.router.parse(h) }; })",
        ROUND_TRIP_SPECS,
    )
    for spec, row in zip(ROUND_TRIP_SPECS, got, strict=True):
        assert row["p"] == spec, (spec, row)
        assert row["h"].startswith("#" + spec["destination"])


def test_chats_create_route_contract(app_clean: str, page: Page) -> None:
    """M25 F4 leg 3b (AC10): `#chats/~new/{agent}` follows the create
    convention: the agent goes through enc() (a leading `~` is `%7E`), bare
    `~new` is just Chats, extra segments fold, the area sub stays encoded."""
    _boot(page, app_clean)
    out = page.evaluate(
        """() => ({
            href: App.router.href({destination: 'chats', create: true, agent: 'x'}),
            hrefTilde: App.router.href({destination: 'chats', create: true, agent: '~x y'}),
            hrefNoAgent: App.router.href({destination: 'chats', create: true}),
            parse: App.router.parse('#chats/~new/My%20Agent'),
            parseBare: App.router.parse('#chats/~new'),
            parseTildeId: App.router.parse('#chats/%7Enew'),
            resolve: App.router.resolve('#chats/~new/My%20Agent'),
            resolveBare: App.router.resolve('#chats/~new'),
            resolveExtra: App.router.resolve('#chats/~new/x/y'),
            resolveLegacy: App.router.resolve('#chat/new/x'),
            routeFor: App.router.routeFor('chat', 'new/x'),
            routeForTilde: App.router.routeFor('chat', 'new/~x%20y'),
            routeForBare: App.router.routeFor('chat', 'new'),
            routeForSession: App.router.routeFor('chat', 'sessions/abc'),
        })"""
    )
    assert out["href"] == "#chats/~new/x"
    assert out["hrefTilde"] == "#chats/~new/%7Ex%20y"
    assert out["hrefNoAgent"] == "#chats"
    assert out["parse"] == {"destination": "chats", "create": True, "agent": "My Agent"}
    assert out["parseBare"] == {"destination": "chats"}
    assert out["parseTildeId"] == {"destination": "chats", "id": "~new"}
    r = out["resolve"]
    assert (r["route"], r["destination"], r["area"], r["sub"], r["redirected"]) == (
        "chats/~new/My%20Agent",
        "chats",
        "chat",
        "new/My%20Agent",
        False,
    )
    assert (
        out["resolveBare"]["route"],
        out["resolveBare"]["sub"],
        out["resolveBare"]["redirected"],
    ) == ("chats", None, True)
    assert (
        out["resolveExtra"]["route"],
        out["resolveExtra"]["sub"],
        out["resolveExtra"]["redirected"],
    ) == ("chats/~new/x", "new/x", True)
    # `#chats/~new/{agent}` never had a legacy form.
    assert (out["resolveLegacy"]["route"], out["resolveLegacy"]["redirected"]) == ("chats", True)
    assert out["routeFor"] == "chats/~new/x"
    assert out["routeForTilde"] == "chats/~new/%7Ex%20y"
    assert out["routeForBare"] == "chats"
    assert out["routeForSession"] == "chats/abc"


def test_leading_tilde_is_escaped_on_output(app_clean: str, page: Page) -> None:
    """An agent named `~new` never serialises to the reserved `~new` segment."""
    _boot(page, app_clean)
    out = page.evaluate(
        """() => ({
            href: App.router.href({destination: 'agents', id: '~new'}),
            hrefTab: App.router.href({destination: 'agents', id: '~new', tab: 'tools'}),
            create: App.router.href({destination: 'library', section: 'providers', create: true}),
            agentCreate: App.router.href({destination: 'agents', create: true}),
            // The agents create sub (M25 F3 L3) is exactly `agents/~new`, unescaped;
            // a longer raw-`~` sub is an agent path and keeps the escape.
            fromAreaCreate: App.router.routeFor('studio', 'agents/~new'),
            parseCreate: App.router.parse('#agents/~new'),
            parseTildeName: App.router.parse('#agents/%7Enew/general'),
            parseNewName: App.router.parse('#agents/new/general'),
            // serializeState's already-encoded segments pass through unchanged
            fromArea: App.router.routeFor('studio', 'agents/~new/general'),
            fromAreaEncoded: App.router.routeFor('studio', 'agents/My%20Agent/tools'),
            mcpCreate: App.router.routeFor('studio', 'mcp-sources/new'),
            // M25 F3 L4a: knowledge bases and connectors are creatable too.
            kbCreate: App.router.routeFor('studio', 'knowledge/new'),
            connCreate: App.router.routeFor('studio', 'connectors/new'),
            connItem: App.router.routeFor('studio', 'connectors/abc'),
            kbCreateSub: App.router.resolve('#library/knowledge/~new').sub,
            connCreateSub: App.router.resolve('#library/connectors/~new').sub,
            connItemSub: App.router.resolve('#library/connectors/abc').sub,
            provNew: App.router.routeFor('studio', 'providers/new'),
            agentNewName: App.router.routeFor('studio', 'agents/new/general'),
        })"""
    )
    assert out["href"] == "#agents/%7Enew"
    assert out["hrefTab"] == "#agents/%7Enew/tools"
    assert out["create"] == "#library/providers/~new"
    assert out["agentCreate"] == "#agents/~new"
    assert out["fromAreaCreate"] == "agents/~new"
    assert out["parseCreate"] == {"destination": "agents", "create": True}
    assert out["parseTildeName"] == {"destination": "agents", "id": "~new", "tab": "general"}
    assert out["parseNewName"] == {"destination": "agents", "id": "new", "tab": "general"}
    assert out["fromArea"] == "agents/%7Enew/general"
    assert out["fromAreaEncoded"] == "agents/My%20Agent/tools"
    assert out["mcpCreate"] == "library/mcp/~new"
    assert out["kbCreate"] == "library/knowledge/~new"
    assert out["connCreate"] == "library/connectors/~new"
    assert out["connItem"] == "library/connectors/abc"
    assert out["kbCreateSub"] == "knowledge/new"
    assert out["connCreateSub"] == "connectors/new"
    assert out["connItemSub"] == "connectors/abc"
    assert out["provNew"] == "library/providers/~new"
    assert out["agentNewName"] == "agents/new/general"  # "new" is a legal agent name


# ── AC3: redirects ───────────────────────────────────────────────────────────

# (legacy or odd input hash, expected canonical route after the redirect)
REDIRECT_ROWS = [
    ("#chat", "chats"),
    ("#chat/sessions/abc123", "chats/abc123"),
    ("#studio", "agents"),
    ("#studio/agents", "agents"),
    ("#studio/agents/foo", "agents/foo"),
    ("#studio/agents/foo/tools", "agents/foo/tools"),
    ("#studio/agents/foo/mcps/src1", "agents/foo/tools/src1"),
    ("#agents/foo/mcps/src1", "agents/foo/tools/src1"),
    ("#agents/foo/mcps", "agents/foo/tools"),
    ("#studio/agents/new", "agents/new"),  # an agent NAMED "new", not the create segment
    ("#studio/agents/new/general", "agents/new/general"),
    ("#studio/tools", "agents"),
    # A bare Library section is an alias for the Library root (the start page).
    # `#studio/providers[/…]` still maps to Library's providers (accepted, DD8).
    ("#studio/providers", "library"),
    ("#studio/providers/new", "library/providers/~new"),
    ("#studio/providers/p1", "library/providers/p1"),
    ("#studio/knowledge", "library"),
    ("#studio/knowledge/kb1", "library/knowledge/kb1"),
    ("#studio/knowledge/new", "library/knowledge/~new"),
    ("#studio/mcp-sources", "library"),
    ("#studio/mcp-sources/new", "library/mcp/~new"),
    ("#studio/mcp-sources/src1", "library/mcp/src1"),
    ("#studio/connectors", "library"),
    ("#studio/connectors/new", "library/connectors/~new"),
    ("#studio/connectors/c1", "library/connectors/c1"),
    # M25 F3 L5a: the former General page is three; its legacy forms go to the
    # first page, Appearance, directly (one replaceState, no chained redirect).
    ("#admin", "settings/appearance"),
    ("#admin/general", "settings/appearance"),
    ("#admin/general/x", "settings/appearance"),
    ("#admin/system", "settings/appearance"),
    ("#admin/system/x", "settings/appearance"),
    ("#admin/tools", "settings/tools"),
    ("#admin/tools/web_search", "settings/tools/web_search"),
    ("#admin/knowledge", "settings/knowledge-indexing"),
    # current-scheme redirects: the bare Library section aliases fold to `library`
    ("#library/knowledge", "library"),
    ("#library/mcp", "library"),
    ("#library/connectors", "library"),
    ("#settings", "settings/appearance"),
]

# The `settings/general` alias (M25 F3 L5a, DD6): the former General page's
# route goes to the first General page, any further segments dropped. Kept out
# of PARITY_CORPUS on purpose: ``_nav.canonical`` never folds settings/general
# (so ``expect_route`` catches a missing redirect).
GENERAL_ALIAS_ROWS = [
    ("#settings/general", "settings/appearance"),
    ("#settings/general/x", "settings/appearance"),
    ("#settings/general/x/y", "settings/appearance"),
]


def test_redirect_rows_on_boot(app_clean: str, page: Page) -> None:
    """Every DD2 row rewrites on boot, with replaceState (never a push), before
    the unknown-route check, stamping a seq, and the committed destination
    renders. One server; each row boots a fresh page in the same (cookied)
    context so ``history.length`` is per row. Failures are collected so one bad
    row never hides another."""
    failures: list[str] = []
    # The fixture page's first goto performs the handoff exchange, landing the
    # session cookie in the shared context that the per-row pages reuse.
    _boot(page, app_clean)
    for legacy, route in REDIRECT_ROWS + GENERAL_ALIAS_ROWS:
        row_page = page.context.new_page()
        try:
            writes = _boot_recorded(row_page, app_clean, legacy)
            first = writes[0] if writes else {}
            seen: list[str] = []
            if first.get("kind") != "replaceState":
                seen.append(f"first write kind {first.get('kind')!r}")
            if first.get("url") != "#" + route:
                seen.append(f"first write url {first.get('url')!r}")
            if not isinstance((first.get("state") or {}).get("seq"), int):
                seen.append(f"seq {(first.get('state') or {}).get('seq')!r}")
            if [w for w in writes if w["kind"] == "pushState"]:
                seen.append("pushState used")
            length = row_page.evaluate("history.length")
            if length != 2:  # about:blank + the app entry
                seen.append(f"history.length {length}")
            dest = row_page.evaluate(
                "() => { const p = document.querySelector("
                "'.content-panel.active[data-destination]');"
                " return p ? p.getAttribute('data-destination') : null; }"
            )
            if dest != route.split("/")[0]:
                seen.append(f"active destination {dest!r}")
            if seen:
                failures.append(f"({legacy!r}, {route!r}): {'; '.join(seen)}; writes={writes}")
        except Exception as exc:  # noqa: BLE001 - collected, reported below
            failures.append(f"({legacy!r}, {route!r}): raised {exc!r}")
        finally:
            row_page.close()
    assert not failures, "redirect rows failed:\n" + "\n".join(failures)


def test_library_root_is_a_route_of_its_own(app_clean: str, page: Page) -> None:
    """`#library` is Library's own route (the start page), not a redirect: it
    boots as itself with no history write, and the bare section aliases fold to
    it (redirected), while item and create routes are unchanged."""
    _boot(page, app_clean, "#library")
    assert page.evaluate("App.router.current().route") == "library"
    assert page.evaluate("location.hash") == "#library"
    assert page.evaluate("App.router.resolve('#library')") == {
        "kind": "route",
        "route": "library",
        "destination": "library",
        "area": "studio",
        "sub": "library",
        "redirected": False,
    }
    for alias in ("#library/knowledge", "#library/mcp", "#library/connectors"):
        got = page.evaluate("h => App.router.resolve(h)", alias)
        assert (got["route"], got["sub"], got["redirected"]) == ("library", "library", True), alias
    for item, sub in (
        ("#library/mcp/~new", "mcp-sources/new"),
        ("#library/connectors/c1", "connectors/c1"),
        ("#library/knowledge/kb1", "knowledge/kb1"),
    ):
        got = page.evaluate("h => App.router.resolve(h)", item)
        assert (got["sub"], got["redirected"]) == (sub, False), item
    assert page.evaluate("App.router.href({destination: 'library'})") == "#library"
    assert page.evaluate("App.router.lastRoute('library')") == "library"
    assert page.evaluate("App.router.routeFor('studio', 'library')") == "library"
    # The bare sections are never produced as an href or as a sync target's URL.
    assert page.evaluate("App.router.root('library')") == "library"


def test_redirect_on_traversal_replaces(app_clean: str, page: Page) -> None:
    """A legacy hash arriving after boot (typed) is rewritten in place."""
    _boot(page, app_clean, "#settings/appearance")
    before = page.evaluate("history.length")
    page.evaluate("location.hash = '#admin/tools'")
    _nav.expect_route(page, "settings/tools")
    # One entry for the typed navigation, rewritten in place (no second one).
    assert page.evaluate("history.length") == before + 1
    assert page.evaluate("location.hash") == "#settings/tools"
    # Back goes to the previous route, not to a bounce through the legacy form.
    page.go_back()
    _nav.expect_route(page, "settings/appearance")


def test_agents_create_route_boots_without_redirect(app_clean: str, page: Page) -> None:
    """Inverted Flight 2 pin (formerly the ``#agents/~new -> agents`` redirect row):
    since M25 F3 L3 ``#agents/~new`` is the agent create route. It boots as itself
    (one replaceState, no push, no redirect to the root) and opens the create form;
    extra segments after it are dropped by a redirect to the bare create route."""
    writes = _boot_recorded(page, app_clean, "#agents/~new")
    first = writes[0]
    assert first["kind"] == "replaceState" and first["url"] == "#agents/~new", writes
    assert not [w for w in writes if w["kind"] == "pushState"], writes
    assert page.evaluate("App.router.current().route") == "agents/~new"
    expect(page.locator(".editor-title")).to_have_text("New Agent", timeout=8000)
    assert page.evaluate("location.hash") == "#agents/~new"
    resolved = page.evaluate("App.router.resolve('#agents/~new/general')")
    assert (resolved["route"], resolved["redirected"]) == ("agents/~new", True)


# The corpus for JS <-> _nav parity: every DD2 legacy form + the bare destinations.
# The `agents/{name}/mcps` alias (M33 F1 L06) is a router-only redirect, like the
# settings/general alias above: `_nav` never folds it, so its rows stay out.
PARITY_CORPUS = [h for h, _ in REDIRECT_ROWS if "/mcps" not in h] + [
    "#chats",
    "#chats/abc",
    # The pending new chat (M25 F4 L3b): an agent with a space and a leading
    # `~` (written %7E), and the bare `~new` that folds to Chats.
    "#chats/~new/x",
    "#chats/~new/My%20~Agent",
    "#chats/~new/%7EMy%20Agent",
    "#chats/~new",
    "#agents",
    "#agents/~new",
    "#agents/foo/general",
    "#library",
    "#library/knowledge",
    "#library/mcp",
    "#library/connectors",
    "#library/knowledge/~new",
    "#library/mcp/~new",
    "#library/connectors/~new",
    "#library/connectors/c1",
    "#settings/appearance",
    "#settings/date-and-time",
    "#settings/prompts",
    "#settings/encryption",
    "#library/providers/~new",
    "#studio/providers/new",
    "#settings/knowledge-indexing",
]


def test_js_mapping_matches_nav_mapping(app_clean: str, page: Page) -> None:
    """The JS redirect/alias mapping equals _nav's mapping functions, so the
    Python helper and the app cannot drift."""
    _boot(page, app_clean)
    got = page.evaluate("corpus => corpus.map(h => App.router.resolve(h).route)", PARITY_CORPUS)
    for hash_, js_route in zip(PARITY_CORPUS, got, strict=True):
        legacy_head = hash_[1:].split("/")[0] in ("chat", "studio", "admin")
        want = _nav._from_legacy(hash_) if legacy_head else _nav.canonical(hash_)
        assert _nav.canonical(js_route) == want, (hash_, js_route, want)


# ── AC4: boot, unknown and element hashes ────────────────────────────────────


@pytest.mark.parametrize("raw", ["", "#", "#bogus", "#nothing/here", "#settings/bogus"])
def test_unknown_or_empty_hash_at_boot_goes_to_chats(app_clean: str, page: Page, raw: str) -> None:
    writes = _boot_recorded(page, app_clean, raw)
    assert writes[0]["kind"] == "replaceState" and writes[0]["url"] == "#chats", writes
    assert page.evaluate("App.router.current().destination") == "chats"


def test_unknown_hash_after_boot_restores_current_route(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/tools")
    _nav.expect_route(page, "settings/tools")
    page.evaluate("location.hash = '#installation'")  # e.g. an agent-authored anchor
    page.wait_for_function("location.hash === '#settings/tools'")
    page.evaluate("location.hash = ''")
    page.wait_for_function("location.hash === '#settings/tools'")
    assert page.evaluate("App.router.current().route") == "settings/tools"


def test_element_id_fragment_is_never_routed(app_clean: str, page: Page) -> None:
    """The skip link's #main-content is not a route; later syncs are not dropped."""
    _boot(page, app_clean, "#settings/appearance")
    _nav.expect_route(page, "settings/appearance")
    page.evaluate("location.hash = '#main-content'")
    page.wait_for_timeout(300)
    assert page.evaluate("location.hash") == "#main-content"
    assert page.evaluate("App.router.current().route") == "settings/appearance"
    assert page.evaluate("App.router.isDeciding()") is False
    # A sync fired while the element fragment is present is kept.
    assert page.evaluate("App.router.sync('admin', 'tools')") is True
    assert page.evaluate("App.router.current().route") == "settings/tools"
    assert page.evaluate("location.hash") == "#settings/tools"


def test_returning_from_element_fragment_is_a_noop(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/appearance")
    page.evaluate("location.hash = '#main-content'")
    page.wait_for_timeout(200)
    page.go_back()
    page.wait_for_function("location.hash === '#settings/appearance'")
    assert page.evaluate("App.router.isDeciding()") is False
    expect(_nav.destination_panel(page, "settings")).to_be_visible()


def test_no_destination_id_equals_an_element_id(app_clean: str, page: Page) -> None:
    _boot(page, app_clean)
    clashes = page.evaluate(
        "() => App.router.destinations.map(d => d.id).filter(id => document.getElementById(id))"
    )
    assert clashes == []


# ── AC5: the commit sequence ─────────────────────────────────────────────────

_SPY_JS = """
() => {
  const log = (window.__seq = []);
  const studio = App.areas.find(a => a.id === 'studio');
  const admin = App.areas.find(a => a.id === 'admin');
  const origIsDirty = App.nav.isDirty;
  App.nav.isDirty = function () {
    log.push({ step: 'guard', hash: location.hash });
    return origIsDirty.call(this);
  };
  const origSerialize = admin.serializeState;
  admin.serializeState = function () {
    log.push({ step: 'serialize' });
    return origSerialize.call(this);
  };
  const origHydrate = admin.hydrateState;
  admin.hydrateState = function (sub) {
    const panel = document.querySelector('.content-panel.active');
    log.push({
      step: 'hydrate', sub, hash: location.hash,
      current: App.router.current().route,
      lastRoute: App.router.lastRoute('settings'),
      aside: document.getElementById('app-sidebar').getAttribute('aria-label'),
      asideHidden: document.getElementById('app-sidebar').hidden,
      panel: panel && panel.dataset.destination,
    });
    return origHydrate.call(this, sub);
  };
  window.__counts = { activate: 0, deactivate: 0 };
  const oa = studio.activate, od = studio.deactivate;
  studio.activate = function () {
    window.__counts.activate++;
    return oa.apply(this, arguments);
  };
  studio.deactivate = function () {
    window.__counts.deactivate++;
    return od.apply(this, arguments);
  };
}
"""


def test_go_commit_sequence(app_clean: str, page: Page) -> None:
    """guard -> URL -> current/lastRoute -> shell -> mountArea -> hydrate -> sync."""
    _nav.goto_settled(page, app_clean, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible()
    page.evaluate(_SPY_JS)
    before = page.evaluate("history.length")
    assert page.evaluate("App.router.go('settings/tools')") is True

    log = page.evaluate("window.__seq")
    steps = [e["step"] for e in log]
    assert steps[0] == "guard" and log[0]["hash"] == "#agents"  # URL not yet written
    hyd = next(e for e in log if e["step"] == "hydrate")
    assert hyd["sub"] == "tools"
    assert hyd["hash"] == "#settings/tools"  # 3. URL written before hydrate
    assert hyd["current"] == "settings/tools"  # 4. current committed
    assert hyd["lastRoute"] == "settings/tools"  # 4. lastRoute committed
    assert hyd["aside"] == "Settings" and hyd["asideHidden"] is False  # 5. shell
    assert hyd["panel"] == "settings"  # 6. mountArea
    # 8. the post-hydrate canonicalisation (serializeState -> sync) follows the hydrate
    assert steps.index("serialize") > steps.index("hydrate")
    assert page.evaluate("history.length") == before + 1  # pushed once


def test_go_to_current_route_replaces_and_hydrates(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "settings/tools")
    expect(_nav.destination_panel(page, "settings")).to_be_visible()
    page.evaluate(_SPY_JS)
    before = page.evaluate("history.length")
    assert page.evaluate("App.router.go('settings/tools')") is True
    assert page.evaluate("history.length") == before  # replaced, not pushed
    assert any(e["step"] == "hydrate" for e in page.evaluate("window.__seq"))  # not skipped


def test_agents_library_does_not_reactivate_studio(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible()
    page.evaluate(_SPY_JS)
    assert page.evaluate("App.router.go('library/mcp')") is True
    assert page.evaluate("App.router.go('agents')") is True
    counts = page.evaluate("window.__counts")
    assert counts == {"activate": 0, "deactivate": 0}, counts
    # ...but leaving the module does deactivate it, and returning re-activates.
    assert page.evaluate("App.router.go('settings/appearance')") is True
    assert page.evaluate("App.router.go('agents')") is True
    counts = page.evaluate("window.__counts")
    assert counts == {"activate": 1, "deactivate": 1}, counts


def test_go_returns_false_for_unknown_route(app_clean: str, page: Page) -> None:
    _boot(page, app_clean)
    assert page.evaluate("App.router.go('#nope/nothing')") is False
    assert page.evaluate("App.router.go('')") is False


# ── AC6: sync drop rules ─────────────────────────────────────────────────────


def test_sync_dropped_for_other_destination(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/appearance")
    assert page.evaluate("App.router.sync('chat', 'sessions/xyz')") is False
    assert page.evaluate("App.router.sync('studio', 'agents/foo/general')") is False
    assert page.evaluate("location.hash") == "#settings/appearance"
    # and a same-destination sync is applied
    assert page.evaluate("App.router.sync('admin', 'tools')") is True
    assert page.evaluate("location.hash") == "#settings/tools"


def test_sync_dropped_while_decision_pending(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/appearance")
    _hold_guard(page)
    page.evaluate("() => { window.__p = App.router.go('library/mcp'); }")
    assert page.evaluate("App.router.isDeciding()") is True
    assert page.evaluate("App.router.sync('admin', 'tools')") is False
    assert page.evaluate("location.hash") == "#settings/appearance"
    page.evaluate("window.__held.abort()")
    _release(page)
    assert page.evaluate("window.__p") is False
    assert page.evaluate("App.router.isDeciding()") is False
    assert page.evaluate("App.router.sync('admin', 'tools')") is True


def test_sync_dropped_when_location_differs_from_router(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/appearance")
    # A URL the router has not committed (e.g. a traversal that has not landed).
    page.evaluate("history.replaceState(history.state, '', '#settings/tools')")
    assert page.evaluate("App.router.sync('admin', 'tools')") is False
    assert page.evaluate("location.hash") == "#settings/tools"


def test_chat_reconnect_autojoin_does_not_write_into_settings(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Chat's session_joined sync, arriving while the user is in Settings, must
    not move the URL (it used to write `#admin/sessions/{id}`)."""
    _boot(page, app_with_agent.base_url, "#chats")
    _chats.start_chat(page, app_with_agent.agent_name)
    _chats.send_first(page, "hello")  # a start is pending; the send makes the session
    page.wait_for_function("location.hash.startsWith('#chats/')", timeout=10000)
    session_id = _chats.current_session_id(page)
    assert session_id

    _nav.open_destination(page, "settings")
    _nav.expect_route(page, "settings/appearance")
    page.evaluate(
        """() => {
          window.__syncs = [];
          const orig = App.router.sync;
          App.router.sync = function (a, s) {
            const r = orig(a, s);
            window.__syncs.push({ a, s, r });
            return r;
          };
        }"""
    )
    # Re-join the session in the background (what the reconnect auto-join does).
    page.evaluate("id => App.areas.find(a => a.id === 'chat')._joinSession(id)", session_id)
    page.wait_for_function("() => window.__syncs.some(x => x.a === 'chat')", timeout=10000)
    syncs = page.evaluate("window.__syncs")
    assert all(x["r"] is False for x in syncs if x["a"] == "chat"), syncs
    assert page.evaluate("location.hash") == "#settings/appearance"


# ── AC7: seq history, Stay/Continue, joins ───────────────────────────────────


def test_every_write_stamps_a_seq_and_replace_keeps_it(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/appearance")
    s0 = page.evaluate("history.state.seq")
    assert isinstance(s0, int)
    page.evaluate("App.router.sync('admin', 'tools')")  # replace keeps the seq
    assert page.evaluate("history.state.seq") == s0
    page.evaluate("App.router.go('settings/prompts')")  # push -> +1
    assert page.evaluate("history.state.seq") == s0 + 1
    page.reload()  # boot adopts the surviving seq
    page.wait_for_function("() => !!(window.App && App.router && App.router.current())")
    assert page.evaluate("history.state.seq") == s0 + 1


def test_stay_after_back_reverts_with_history_go(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/appearance")
    page.evaluate("App.router.go('settings/tools')")
    seq = page.evaluate("history.state.seq")
    length = page.evaluate("history.length")
    _hold_guard(page)
    page.go_back()
    page.wait_for_function("window.__held !== null")
    assert page.evaluate("App.router.isDeciding()") is True
    assert page.evaluate("App.router.current().route") == "settings/tools"
    page.evaluate("window.__held.abort()")
    _release(page)
    page.wait_for_function("location.hash === '#settings/tools'")
    assert page.evaluate("history.state.seq") == seq  # back on the very same entry
    assert page.evaluate("history.length") == length  # nothing pushed
    assert page.evaluate("App.router.isDeciding()") is False
    # the revert's own popstate was a no-op: no hydrate to settings/appearance
    assert page.evaluate("App.router.current().route") == "settings/tools"


def test_continue_after_back_does_not_push_and_hydrates_latest(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/appearance")
    page.evaluate("App.router.go('settings/tools')")
    length = page.evaluate("history.length")
    _hold_guard(page)
    page.go_back()
    page.wait_for_function("window.__held !== null")
    _release(page)
    page.evaluate("window.__held.proceed()")
    page.wait_for_function("App.router.current().route === 'settings/appearance'")
    assert page.evaluate("location.hash") == "#settings/appearance"
    assert page.evaluate("history.length") == length  # Continue never pushes
    expect(page.locator(".page-title")).to_have_text("Appearance", timeout=5000)


def test_stay_after_typed_url_repushes_current_route(app_clean: str, page: Page) -> None:
    """A null-state arrival (typed URL) has no delta: Stay re-pushes the stayed
    route -- one duplicate entry, accepted and documented -- and the screen and
    URL agree."""
    _boot(page, app_clean, "#settings/appearance")
    length = page.evaluate("history.length")
    _hold_guard(page)
    page.evaluate("location.hash = '#settings/tools'")
    page.wait_for_function("window.__held !== null")
    _release(page)
    page.evaluate("window.__held.abort()")
    page.wait_for_function("location.hash === '#settings/appearance'")
    assert page.evaluate("history.length") == length + 2  # the typed entry + the re-push
    assert page.evaluate("App.router.current().route") == "settings/appearance"
    assert isinstance(page.evaluate("history.state.seq"), int)
    expect(page.locator(".page-title")).to_have_text("Appearance")


def test_traversal_with_nonrouter_dialog_open_reverts_as_stay(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/appearance")
    page.evaluate("App.router.go('settings/tools')")
    seq = page.evaluate("history.state.seq")
    page.evaluate(
        "App.confirmDialog({ title: 'Other', message: 'unrelated', "
        "onConfirm: () => {}, onCancel: () => {} })"
    )
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible()
    page.go_back()
    page.wait_for_function("location.hash === '#settings/tools'")
    assert page.evaluate("history.state.seq") == seq
    # the open dialog stays in charge
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible()
    assert page.evaluate("App.router.isDeciding()") is False
    assert page.evaluate("App.router.current().route") == "settings/tools"


def test_go_with_dialog_open_resolves_stay_and_syncs_continue(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/appearance")
    page.evaluate(
        "App.confirmDialog({ title: 'Other', message: 'unrelated', "
        "onConfirm: () => {}, onCancel: () => {} })"
    )
    assert page.evaluate("App.router.go('library/mcp')") is False
    assert page.evaluate("App.router.isDeciding()") is False
    assert page.evaluate("location.hash") == "#settings/appearance"
    assert page.evaluate("App.router.sync('admin', 'tools')") is True


def test_concurrent_gos_join_and_latest_target_wins(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/appearance")
    _hold_guard(page)
    page.evaluate(
        """() => {
          window.__r = [];
          App.router.go('settings/tools').then(v => window.__r.push(['a', v]));
          App.router.go('library/mcp').then(v => window.__r.push(['b', v]));
          App.router.go('chats').then(v => window.__r.push(['c', v]));
        }"""
    )
    assert page.evaluate("App.router.isDeciding()") is True
    _release(page)
    page.evaluate("window.__held.proceed()")
    page.wait_for_function("window.__r.length === 3")
    assert sorted(page.evaluate("window.__r")) == [["a", True], ["b", True], ["c", True]]
    assert page.evaluate("App.router.current().destination") == "chats"


# ── AC13: squawk 0082 ────────────────────────────────────────────────────────


def test_hashchange_back_to_previous_sub_after_sync_is_honoured(app_clean: str, page: Page) -> None:
    """Squawk 0082: `replaceSub` left the router's current sub stale, so after a
    sub-route change a hashchange back to the PREVIOUS sub was swallowed as a
    same-route no-op. The router's current route now updates on every write."""
    _boot(page, app_clean, "#settings/knowledge-indexing")
    expect(page.locator(".page-title")).to_have_text("Knowledge indexing", timeout=8000)
    page.evaluate("App.router.sync('admin', 'tools')")  # the area changes its own sub
    _nav.expect_route(page, "settings/tools")
    assert page.evaluate("App.router.current().route") == "settings/tools"
    # a hashchange back to the previous sub must be honoured
    page.evaluate("location.hash = '#settings/knowledge-indexing'")
    page.wait_for_function("App.router.current().route === 'settings/knowledge-indexing'")
    expect(page.locator(".page-title")).to_have_text("Knowledge indexing", timeout=8000)


# ── Providers left Settings (sortie 02, DD8): their old routes are unknown ───

# `#settings/providers[/…]` and `#admin/providers[/…]` are dropped, not redirected
# (the operator's decision): they resolve as unknown routes.
DROPPED_PROVIDER_HASHES = [
    "#settings/providers",
    "#settings/providers/~new",
    "#settings/providers/abc",
    "#admin/providers",
    "#admin/providers/new",
    "#admin/providers/abc",
]


def test_old_settings_provider_routes_resolve_as_unknown(app_clean: str, page: Page) -> None:
    _boot(page, app_clean)
    got = page.evaluate("hs => hs.map(h => App.router.resolve(h).kind)", DROPPED_PROVIDER_HASHES)
    assert got == ["unknown"] * len(DROPPED_PROVIDER_HASHES), got
    # Nothing in the Settings page table or the rail route knows the section.
    assert page.evaluate("App.settingsPages.some(p => p.section === 'providers')") is False
    # `#studio/providers[/…]` is the accepted exception: it maps to Library (DD8).
    assert page.evaluate("App.router.resolve('#studio/providers/p1').route") == (
        "library/providers/p1"
    )


@pytest.mark.parametrize("raw", ["#settings/providers", "#admin/providers/abc"])
def test_old_provider_route_at_boot_lands_on_chats(app_clean: str, page: Page, raw: str) -> None:
    """A bookmarked old link: the boot treats the non-route hash as unknown."""
    writes = _boot_recorded(page, app_clean, raw)
    assert writes[0]["kind"] == "replaceState" and writes[0]["url"] == "#chats", writes
    assert page.evaluate("App.router.current().destination") == "chats"


def test_old_provider_route_is_refused_in_app(app_clean: str, page: Page) -> None:
    """In-app: ``go()`` resolves false for it (nothing moves), and a typed hash
    restores the current route."""
    _boot(page, app_clean, "#settings/appearance")
    before = page.evaluate("history.length")
    assert page.evaluate("App.router.go('settings/providers')") is False
    assert page.evaluate("App.router.go('settings/providers/~new')") is False
    assert page.evaluate("history.length") == before
    assert page.evaluate("App.router.current().route") == "settings/appearance"
    page.evaluate("location.hash = '#settings/providers/abc'")
    page.wait_for_function("location.hash === '#settings/appearance'")
    assert page.evaluate("App.router.current().route") == "settings/appearance"
