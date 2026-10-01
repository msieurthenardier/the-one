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

import json

import pytest
from browser import _nav
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
    {"destination": "agents"},
    {"destination": "agents", "id": "My Agent"},
    {"destination": "agents", "id": "a/b", "tab": "tools"},
    {"destination": "agents", "id": "日本語", "tab": "general"},
    {"destination": "agents", "id": "~new", "tab": "knowledge"},
    {"destination": "agents", "id": "x", "tab": "mcps", "sub": "src/1 é"},
    {"destination": "agents", "id": "!'()*", "tab": "self-configuration"},
    {"destination": "library", "section": "knowledge"},
    {"destination": "library", "section": "knowledge", "id": "kb 1"},
    {"destination": "library", "section": "mcp", "create": True},
    {"destination": "library", "section": "mcp", "id": "~src"},
    {"destination": "library", "section": "connectors"},
    {"destination": "settings", "section": "general"},
    {"destination": "settings", "section": "providers", "create": True},
    {"destination": "settings", "section": "providers", "id": "p/é!'()*~"},
    {"destination": "settings", "section": "tools", "id": "web search"},
    {"destination": "settings", "section": "knowledge-indexing"},
    {"destination": "settings", "section": "design-language"},
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


def test_leading_tilde_is_escaped_on_output(app_clean: str, page: Page) -> None:
    """An agent named `~new` never serialises to the reserved `~new` segment."""
    _boot(page, app_clean)
    out = page.evaluate(
        """() => ({
            href: App.router.href({destination: 'agents', id: '~new'}),
            hrefTab: App.router.href({destination: 'agents', id: '~new', tab: 'tools'}),
            create: App.router.href({destination: 'settings', section: 'providers', create: true}),
            // serializeState's already-encoded segments pass through unchanged
            fromArea: App.router.routeFor('studio', 'agents/~new/general'),
            fromAreaEncoded: App.router.routeFor('studio', 'agents/My%20Agent/tools'),
            mcpCreate: App.router.routeFor('studio', 'mcp-sources/new'),
            provNew: App.router.routeFor('admin', 'providers/new'),
            agentNewName: App.router.routeFor('studio', 'agents/new/general'),
        })"""
    )
    assert out["href"] == "#agents/%7Enew"
    assert out["hrefTab"] == "#agents/%7Enew/tools"
    assert out["create"] == "#settings/providers/~new"
    assert out["fromArea"] == "agents/%7Enew/general"
    assert out["fromAreaEncoded"] == "agents/My%20Agent/tools"
    assert out["mcpCreate"] == "library/mcp/~new"
    assert out["provNew"] == "settings/providers/~new"
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
    ("#studio/agents/foo/mcps/src1", "agents/foo/mcps/src1"),
    ("#studio/agents/new", "agents/new"),  # an agent NAMED "new", not the create segment
    ("#studio/agents/new/general", "agents/new/general"),
    ("#studio/tools", "agents"),
    ("#studio/knowledge", "library/knowledge"),
    ("#studio/knowledge/kb1", "library/knowledge/kb1"),
    ("#studio/mcp-sources", "library/mcp"),
    ("#studio/mcp-sources/new", "library/mcp/~new"),
    ("#studio/mcp-sources/src1", "library/mcp/src1"),
    ("#studio/connectors", "library/connectors"),
    ("#admin", "settings/general"),
    ("#admin/general", "settings/general"),
    ("#admin/system", "settings/general"),
    ("#admin/providers", "settings/providers"),
    ("#admin/providers/new", "settings/providers/~new"),
    ("#admin/providers/p1", "settings/providers/p1"),
    ("#admin/tools", "settings/tools"),
    ("#admin/tools/web_search", "settings/tools/web_search"),
    ("#admin/knowledge", "settings/knowledge-indexing"),
    # current-scheme redirects
    ("#agents/~new", "agents"),
    ("#library", "library/knowledge"),
    ("#settings", "settings/general"),
]


@pytest.mark.parametrize(("legacy", "route"), REDIRECT_ROWS)
def test_redirect_row_on_boot(app_clean: str, page: Page, legacy: str, route: str) -> None:
    """Every DD2 row rewrites on boot, with replaceState (never a push), before
    the unknown-route check, stamping a seq."""
    writes = _boot_recorded(page, app_clean, legacy)
    first = writes[0]
    assert first["kind"] == "replaceState", writes
    assert first["url"] == "#" + route, writes
    assert isinstance(first["state"]["seq"], int)
    assert not [w for w in writes if w["kind"] == "pushState"], writes
    assert page.evaluate("history.length") == 2  # about:blank + the app entry


def test_redirect_on_traversal_replaces(app_clean: str, page: Page) -> None:
    """A legacy hash arriving after boot (typed) is rewritten in place."""
    _boot(page, app_clean, "#settings/general")
    before = page.evaluate("history.length")
    page.evaluate("location.hash = '#admin/providers'")
    _nav.expect_route(page, "settings/providers")
    # One entry for the typed navigation, rewritten in place (no second one).
    assert page.evaluate("history.length") == before + 1
    assert page.evaluate("location.hash") == "#settings/providers"
    # Back goes to the previous route, not to a bounce through the legacy form.
    page.go_back()
    _nav.expect_route(page, "settings/general")


# The corpus for JS <-> _nav parity: every DD2 legacy form + the bare destinations.
PARITY_CORPUS = [h for h, _ in REDIRECT_ROWS if h != "#agents/~new"] + [
    "#chats",
    "#chats/abc",
    "#agents",
    "#agents/foo/general",
    "#library/knowledge",
    "#library/mcp/~new",
    "#settings/providers/~new",
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
    _boot(page, app_clean, "#settings/providers")
    _nav.expect_route(page, "settings/providers")
    page.evaluate("location.hash = '#installation'")  # e.g. an agent-authored anchor
    page.wait_for_function("location.hash === '#settings/providers'")
    page.evaluate("location.hash = ''")
    page.wait_for_function("location.hash === '#settings/providers'")
    assert page.evaluate("App.router.current().route") == "settings/providers"


def test_element_id_fragment_is_never_routed(app_clean: str, page: Page) -> None:
    """The skip link's #main-content is not a route; later syncs are not dropped."""
    _boot(page, app_clean, "#settings/general")
    _nav.expect_route(page, "settings/general")
    page.evaluate("location.hash = '#main-content'")
    page.wait_for_timeout(300)
    assert page.evaluate("location.hash") == "#main-content"
    assert page.evaluate("App.router.current().route") == "settings/general"
    assert page.evaluate("App.router.isDeciding()") is False
    # A sync fired while the element fragment is present is kept.
    assert page.evaluate("App.router.sync('admin', 'providers')") is True
    assert page.evaluate("App.router.current().route") == "settings/providers"
    assert page.evaluate("location.hash") == "#settings/providers"


def test_returning_from_element_fragment_is_a_noop(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/general")
    page.evaluate("location.hash = '#main-content'")
    page.wait_for_timeout(200)
    page.go_back()
    page.wait_for_function("location.hash === '#settings/general'")
    assert page.evaluate("App.router.isDeciding()") is False
    expect(_nav.destination_panel(page, "settings")).to_be_visible()


def test_no_destination_id_equals_an_element_id(app_clean: str, page: Page) -> None:
    _boot(page, app_clean)
    clashes = page.evaluate(
        "() => App.router.destinations.map(d => d.id).filter(id => document.getElementById(id))"
    )
    assert clashes == []


def test_design_language_route_follows_dev_mode_rules(app_clean: str, page: Page) -> None:
    """The browser-lane app runs in dev mode, so the route is known there; with
    dev_mode forced off it follows the unknown-hash rules (boot -> chats, after
    boot -> restore current)."""
    _boot(page, app_clean, "#settings/design-language")
    _nav.expect_route(page, "settings/design-language")
    page.evaluate("App.config.dev_mode = false")
    page.evaluate("location.hash = '#settings/design-language'")  # no-op: same route
    page.evaluate("location.hash = '#settings/general'")
    page.wait_for_function("App.router.current().route === 'settings/general'")
    page.evaluate("location.hash = '#settings/design-language'")
    page.wait_for_function("location.hash === '#settings/general'")


def test_design_language_unknown_at_boot_without_dev_mode(app_clean: str, page: Page) -> None:
    page.route(
        "**/api/config",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"dev_mode": False, "version": "x"}),
        ),
    )
    _boot(page, app_clean, "#settings/design-language")
    assert page.evaluate("location.hash").startswith("#chats")


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
    assert page.evaluate("App.router.go('settings/providers')") is True

    log = page.evaluate("window.__seq")
    steps = [e["step"] for e in log]
    assert steps[0] == "guard" and log[0]["hash"] == "#agents"  # URL not yet written
    hyd = next(e for e in log if e["step"] == "hydrate")
    assert hyd["sub"] == "providers"
    assert hyd["hash"] == "#settings/providers"  # 3. URL written before hydrate
    assert hyd["current"] == "settings/providers"  # 4. current committed
    assert hyd["lastRoute"] == "settings/providers"  # 4. lastRoute committed
    assert hyd["aside"] == "Settings" and hyd["asideHidden"] is False  # 5. shell
    assert hyd["panel"] == "settings"  # 6. mountArea
    # 8. the post-hydrate canonicalisation (serializeState -> sync) follows the hydrate
    assert steps.index("serialize") > steps.index("hydrate")
    assert page.evaluate("history.length") == before + 1  # pushed once


def test_go_to_current_route_replaces_and_hydrates(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "settings/providers")
    expect(_nav.destination_panel(page, "settings")).to_be_visible()
    page.evaluate(_SPY_JS)
    before = page.evaluate("history.length")
    assert page.evaluate("App.router.go('settings/providers')") is True
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
    assert page.evaluate("App.router.go('settings/general')") is True
    assert page.evaluate("App.router.go('agents')") is True
    counts = page.evaluate("window.__counts")
    assert counts == {"activate": 1, "deactivate": 1}, counts


def test_go_returns_false_for_unknown_route(app_clean: str, page: Page) -> None:
    _boot(page, app_clean)
    assert page.evaluate("App.router.go('#nope/nothing')") is False
    assert page.evaluate("App.router.go('')") is False


# ── AC6: sync drop rules ─────────────────────────────────────────────────────


def test_sync_dropped_for_other_destination(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/general")
    assert page.evaluate("App.router.sync('chat', 'sessions/xyz')") is False
    assert page.evaluate("App.router.sync('studio', 'agents/foo/general')") is False
    assert page.evaluate("location.hash") == "#settings/general"
    # and a same-destination sync is applied
    assert page.evaluate("App.router.sync('admin', 'tools')") is True
    assert page.evaluate("location.hash") == "#settings/tools"


def test_sync_dropped_while_decision_pending(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/general")
    _hold_guard(page)
    page.evaluate("() => { window.__p = App.router.go('library/mcp'); }")
    assert page.evaluate("App.router.isDeciding()") is True
    assert page.evaluate("App.router.sync('admin', 'tools')") is False
    assert page.evaluate("location.hash") == "#settings/general"
    page.evaluate("window.__held.abort()")
    _release(page)
    assert page.evaluate("window.__p") is False
    assert page.evaluate("App.router.isDeciding()") is False
    assert page.evaluate("App.router.sync('admin', 'tools')") is True


def test_sync_dropped_when_location_differs_from_router(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/general")
    # A URL the router has not committed (e.g. a traversal that has not landed).
    page.evaluate("history.replaceState(history.state, '', '#settings/tools')")
    assert page.evaluate("App.router.sync('admin', 'providers')") is False
    assert page.evaluate("location.hash") == "#settings/tools"


def test_chat_reconnect_autojoin_does_not_write_into_settings(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Chat's session_joined sync, arriving while the user is in Settings, must
    not move the URL (it used to write `#admin/sessions/{id}`)."""
    _boot(page, app_with_agent.base_url, "#chats")
    page.locator(".chat-welcome-item").filter(has_text=app_with_agent.agent_name).click()
    page.wait_for_function("location.hash.startsWith('#chats/')", timeout=10000)
    session_id = page.evaluate("App.areas.find(a => a.id === 'chat')._currentSessionId")
    assert session_id

    _nav.open_destination(page, "settings")
    _nav.expect_route(page, "settings/general")
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
    assert page.evaluate("location.hash") == "#settings/general"


# ── AC7: seq history, Stay/Continue, joins ───────────────────────────────────


def test_every_write_stamps_a_seq_and_replace_keeps_it(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/general")
    s0 = page.evaluate("history.state.seq")
    assert isinstance(s0, int)
    page.evaluate("App.router.sync('admin', 'tools')")  # replace keeps the seq
    assert page.evaluate("history.state.seq") == s0
    page.evaluate("App.router.go('settings/providers')")  # push -> +1
    assert page.evaluate("history.state.seq") == s0 + 1
    page.reload()  # boot adopts the surviving seq
    page.wait_for_function("() => !!(window.App && App.router && App.router.current())")
    assert page.evaluate("history.state.seq") == s0 + 1


def test_stay_after_back_reverts_with_history_go(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/general")
    page.evaluate("App.router.go('settings/providers')")
    seq = page.evaluate("history.state.seq")
    length = page.evaluate("history.length")
    _hold_guard(page)
    page.go_back()
    page.wait_for_function("window.__held !== null")
    assert page.evaluate("App.router.isDeciding()") is True
    assert page.evaluate("App.router.current().route") == "settings/providers"
    page.evaluate("window.__held.abort()")
    _release(page)
    page.wait_for_function("location.hash === '#settings/providers'")
    assert page.evaluate("history.state.seq") == seq  # back on the very same entry
    assert page.evaluate("history.length") == length  # nothing pushed
    assert page.evaluate("App.router.isDeciding()") is False
    # the revert's own popstate was a no-op: no hydrate to settings/general
    assert page.evaluate("App.router.current().route") == "settings/providers"


def test_continue_after_back_does_not_push_and_hydrates_latest(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/general")
    page.evaluate("App.router.go('settings/providers')")
    length = page.evaluate("history.length")
    _hold_guard(page)
    page.go_back()
    page.wait_for_function("window.__held !== null")
    _release(page)
    page.evaluate("window.__held.proceed()")
    page.wait_for_function("App.router.current().route === 'settings/general'")
    assert page.evaluate("location.hash") == "#settings/general"
    assert page.evaluate("history.length") == length  # Continue never pushes
    expect(page.locator(".page-title")).to_have_text("General", timeout=5000)


def test_stay_after_typed_url_repushes_current_route(app_clean: str, page: Page) -> None:
    """A null-state arrival (typed URL) has no delta: Stay re-pushes the stayed
    route -- one duplicate entry, accepted and documented -- and the screen and
    URL agree."""
    _boot(page, app_clean, "#settings/general")
    length = page.evaluate("history.length")
    _hold_guard(page)
    page.evaluate("location.hash = '#settings/providers'")
    page.wait_for_function("window.__held !== null")
    _release(page)
    page.evaluate("window.__held.abort()")
    page.wait_for_function("location.hash === '#settings/general'")
    assert page.evaluate("history.length") == length + 2  # the typed entry + the re-push
    assert page.evaluate("App.router.current().route") == "settings/general"
    assert isinstance(page.evaluate("history.state.seq"), int)
    expect(page.locator(".page-title")).to_have_text("General")


def test_traversal_with_nonrouter_dialog_open_reverts_as_stay(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/general")
    page.evaluate("App.router.go('settings/providers')")
    seq = page.evaluate("history.state.seq")
    page.evaluate(
        "App.confirmDialog({ title: 'Other', message: 'unrelated', "
        "onConfirm: () => {}, onCancel: () => {} })"
    )
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible()
    page.go_back()
    page.wait_for_function("location.hash === '#settings/providers'")
    assert page.evaluate("history.state.seq") == seq
    # the open dialog stays in charge
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible()
    assert page.evaluate("App.router.isDeciding()") is False
    assert page.evaluate("App.router.current().route") == "settings/providers"


def test_go_with_dialog_open_resolves_stay_and_syncs_continue(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/general")
    page.evaluate(
        "App.confirmDialog({ title: 'Other', message: 'unrelated', "
        "onConfirm: () => {}, onCancel: () => {} })"
    )
    assert page.evaluate("App.router.go('library/mcp')") is False
    assert page.evaluate("App.router.isDeciding()") is False
    assert page.evaluate("location.hash") == "#settings/general"
    assert page.evaluate("App.router.sync('admin', 'tools')") is True


def test_concurrent_gos_join_and_latest_target_wins(app_clean: str, page: Page) -> None:
    _boot(page, app_clean, "#settings/general")
    _hold_guard(page)
    page.evaluate(
        """() => {
          window.__r = [];
          App.router.go('settings/providers').then(v => window.__r.push(['a', v]));
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
    expect(page.locator(".page-title")).to_have_text("Knowledge", timeout=8000)
    page.evaluate("App.router.sync('admin', 'providers')")  # the area changes its own sub
    _nav.expect_route(page, "settings/providers")
    assert page.evaluate("App.router.current().route") == "settings/providers"
    # a hashchange back to the previous sub must be honoured
    page.evaluate("location.hash = '#settings/knowledge-indexing'")
    page.wait_for_function("App.router.current().route === 'settings/knowledge-indexing'")
    expect(page.locator(".page-title")).to_have_text("Knowledge", timeout=8000)
