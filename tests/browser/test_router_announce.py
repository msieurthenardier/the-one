"""Route announcer, document title and dialog-open hardening (M25 F2 flight review).

Router contract tests (literal route text is fine here; the migration guard
exempts ``tests/browser/test_router_*.py``).

* ``#route-announcer`` is one visually-hidden polite live region
  (``role=status``). It is written on a commit that changes destination, section
  or item -- never on boot. A ``sync`` (a tab switch, a canonicalisation, a chat
  session) is silent, except for one transition (M25 F3 L2, DD8): from a ``~new``
  route to an item in the same destination and section, i.e. a save-create.
* ``document.title`` follows every commit (boot included) and every sync.
* Item names come from ``App.store`` (providers, knowledge bases, MCP servers,
  connectors) or a sync's ``{name}`` hint; a cold or unknown item falls back to
  its type noun, never the raw id.
* A ``showModal()`` that throws must not leave ``App.confirmDialog.isOpen()``
  stuck true, which would make every later navigation resolve Stay.
"""

from __future__ import annotations

import httpx
import pytest
from browser import _chats, _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_agent
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

BRAND = "GleepGlorp AI"
ANNOUNCER = '[data-testid="route-announcer"]'
DIALOG = '[data-testid="confirm-dialog-overlay"]'
CONTINUE = '[data-testid="modal-confirm-btn"]'

# Counts every write to the announcer (text or child changes).
_COUNT_JS = """
(() => {
  window.__announceWrites = 0;
  new MutationObserver(recs => { window.__announceWrites += recs.length; })
    .observe(document.querySelector('[data-testid="route-announcer"]'),
             { childList: true, characterData: true, subtree: true });
})();
"""


def _writes(page: Page) -> int:
    return page.evaluate("window.__announceWrites")


def test_announcer_is_a_polite_status_region_and_empty_at_boot(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_agent.base_url, "chats")
    region = page.locator(ANNOUNCER)
    expect(region).to_have_count(1)
    expect(region).to_have_attribute("role", "status")
    expect(region).to_have_attribute("aria-live", "polite")
    expect(region).to_have_class("visually-hidden")
    expect(region).to_have_text("")  # boot's first commit is not announced
    expect(page).to_have_title(f"Chats · {BRAND}")


def test_rail_navigation_announces_and_titles_each_destination(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_agent.base_url, "chats")
    page.evaluate(_COUNT_JS)
    region = page.locator(ANNOUNCER)

    _nav.open_destination(page, "agents")
    expect(region).to_have_text("Agents")
    expect(page).to_have_title(f"Agents · {BRAND}")

    _nav.open_destination(page, "library")
    expect(region).to_have_text("Library")
    expect(page).to_have_title(f"Library · {BRAND}")

    _nav.open_destination(page, "settings")
    expect(region).to_have_text("Settings — Appearance")
    expect(page).to_have_title(f"Settings — Appearance · {BRAND}")

    # The Built-in tools page announces its page-header label (M25 F3 L5a).
    _lists.settings_nav_link(page, "tools").click()
    expect(region).to_have_text("Settings — Built-in tools")
    expect(page).to_have_title(f"Settings — Built-in tools · {BRAND}")

    _nav.open_destination(page, "chats")
    expect(region).to_have_text("Chats")
    expect(page).to_have_title(f"Chats · {BRAND}")
    assert _writes(page) >= 5


def test_opening_an_item_announces_it_and_a_tab_switch_does_not(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    page.evaluate(_COUNT_JS)
    region = page.locator(ANNOUNCER)

    page.locator('[data-testid="agent-item"]').first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    _nav.expect_route(page, f"agents/{_nav.seg(name)}/general")
    expect(region).to_have_text(f"Agents — {name}")
    expect(page).to_have_title(f"Agents — {name} · {BRAND}")
    # Settle: nothing else writes the region while we compare counts below.
    page.wait_for_function("window.__announceWrites >= 1")
    before = _writes(page)

    # A tab switch is a sync (same destination and item): title only, no announcement.
    other = page.locator('[role="tab"]:not([data-testid="tab-general"])').first
    tab_id = other.get_attribute("data-testid")
    other.click()
    page.wait_for_function(
        "t => (location.hash.split('/')[2] || '') !== 'general' && !!t", arg=tab_id
    )
    expect(region).to_have_text(f"Agents — {name}")
    assert _writes(page) == before
    expect(page).to_have_title(f"Agents — {name} · {BRAND}")


def test_show_modal_failure_does_not_leave_dialog_count_stuck(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    page.locator('[data-testid="agent-item"]').first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    route = _nav.current_route(page)
    desc = page.locator('[data-field="description"]')
    desc.click()
    desc.fill("dirty edit")
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_enabled()

    # The next showModal() throws once.
    page.evaluate(
        """() => {
          const orig = HTMLDialogElement.prototype.showModal;
          HTMLDialogElement.prototype.showModal = function () {
            HTMLDialogElement.prototype.showModal = orig;
            throw new Error('showModal boom');
          };
        }"""
    )
    _nav.open_destination(page, "library")
    # The failed open resolves Stay and leaves nothing pending or counted.
    page.wait_for_function("() => !App.router.isDeciding()")
    assert page.evaluate("App.confirmDialog.isOpen()") is False
    assert page.evaluate("App.nav.isPending()") is False
    expect(page.locator(DIALOG)).to_have_count(0)
    _nav.expect_route(page, route)

    # A later navigation is not stuck as Stay: the dialog opens, Continue leaves.
    _nav.open_destination(page, "library")
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    expect(_nav.destination_panel(page, "library")).to_be_visible(timeout=8000)
    assert page.evaluate("App.confirmDialog.isOpen()") is False


# ── Item names from the store (M25 F3 L2, DD8) ───────────────────────────


def _post(base: str, path: str, body: dict) -> dict:
    r = httpx.post(f"{base}{path}", json=body, headers=auth_headers_for(base), timeout=5)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _seed_items(app: SeededApp) -> dict[str, tuple[str, str]]:
    """kind -> (id, name) for one item of each store-named kind."""
    base = app.base_url
    kb = _post(base, "/api/knowledge-bases", {"name": "Warm KB"})
    mcp = _post(
        base,
        "/api/mcp-sources",
        {"name": "warm-mcp", "type": "stdio", "config": {"command": "x"}, "secrets": {}},
    )
    conn = _post(
        base,
        "/api/connectors",
        {
            "name": "Warm Connector",
            "type": "discord",
            "config": {"default_agent": app.agent_name, "enabled": False},
            "secrets": {},
        },
    )
    return {
        "provider": (app.provider_id, "mock"),  # seed_mock_provider's name
        "kb": (kb["id"], kb["name"]),
        "mcp": (mcp["id"], mcp["name"]),
        "connector": (conn["id"], conn["name"]),
    }


# kind -> (section route, store collection, spoken prefix, type noun)
KINDS = {
    "provider": ("library/providers", "providers", "Library — Model providers", "Model provider"),
    "kb": ("library/knowledge", "knowledge-bases", "Library — Knowledge", "Knowledge base"),
    "mcp": ("library/mcp", "mcp-sources", "Library — MCP servers", "MCP server"),
    "connector": ("library/connectors", "connectors", "Library — Connectors", "Connector"),
}


def _go_and_read(page: Page, route: str) -> tuple[str, str]:
    """go() to *route*; (title, announcer text) as the commit left them."""
    return tuple(
        page.evaluate(
            """async (r) => {
              await App.router.go(r);
              return [document.title,
                      document.querySelector('[data-testid="route-announcer"]').textContent];
            }""",
            "#" + route,
        )
    )


@pytest.mark.parametrize("kind", list(KINDS))
def test_item_is_named_from_the_warm_store(
    app_with_agent: SeededApp, page: Page, kind: str
) -> None:
    item_id, name = _seed_items(app_with_agent)[kind]
    section, collection, prefix, _noun = KINDS[kind]
    _nav.goto_settled(page, app_with_agent.base_url, section)
    page.wait_for_function(
        "c => App.store.peek(c).loaded", arg=collection, timeout=8000
    )  # the section's list warmed the store
    # (The router names the item at commit, before the area hydrates.)
    title, spoken = _go_and_read(page, f"{section}/{_nav.seg(item_id)}")
    assert spoken == f"{prefix} — {name}"
    assert title == f"{prefix} — {name} · {BRAND}"


def test_cold_item_routes_fall_back_to_the_type_noun(app_with_agent: SeededApp, page: Page) -> None:
    items = _seed_items(app_with_agent)
    # From Appearance nothing has loaded providers or the Library lists, and a
    # commit names its item BEFORE the area mounts and fetches. Each kind starts
    # from a fresh document: entering Library loads all three Library lists
    # (the list pane, M25 F3 L4a), so a second Library kind would never be cold.
    _nav.goto_settled(page, app_with_agent.base_url, "settings/appearance")
    for kind in ("provider", "kb", "mcp", "connector"):
        _nav.set_route(page, "settings/appearance")
        _nav.expect_route(page, "settings/appearance")
        page.reload()
        _nav.wait_settled(page)
        item_id, name = items[kind]
        section, collection, prefix, noun = KINDS[kind]
        assert page.evaluate("c => App.store.peek(c).loaded", collection) is False, kind
        title, spoken = _go_and_read(page, f"{section}/{_nav.seg(item_id)}")
        assert spoken == f"{prefix} — {noun}", kind
        assert item_id not in title and item_id not in spoken, kind
        if kind != "provider":
            # The post-hydrate sync saw the same cold store (the provider
            # editor's own sync may already name it once its list loads).
            assert title == f"{prefix} — {noun} · {BRAND}", kind
        _nav.wait_settled(page)
        # Never re-announced once the store warms (same key).
        expect(page.locator(ANNOUNCER)).to_have_text(f"{prefix} — {noun}")


def test_unknown_item_id_falls_back_to_the_type_noun(app_with_agent: SeededApp, page: Page) -> None:
    _seed_items(app_with_agent)
    _nav.goto_settled(page, app_with_agent.base_url, "library")
    page.wait_for_function("() => App.store.peek('mcp-sources').loaded")
    title, spoken = _go_and_read(page, "library/mcp/no-such-source")
    assert spoken == "Library — MCP servers — MCP server"
    assert "no-such-source" not in title


# ── sync() announces only create -> item (M25 F3 L2, DD8) ────────────────


def test_provider_save_create_announces_the_new_provider(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_agent.base_url, "library")
    _, spoken = _go_and_read(page, "library/providers/~new")
    assert spoken == "Library — Model providers — New"
    page.locator("#pf-name").fill("Created Provider")
    page.locator("#pf-type").select_option("mock")
    page.locator('[data-testid="save-provider-btn"]').click()
    _nav.wait_for_route_prefix(
        page, "library/providers/", not_equal="library/providers/~new", timeout=8000
    )
    expect(page.locator(ANNOUNCER)).to_have_text("Library — Model providers — Created Provider")
    expect(page).to_have_title(f"Library — Model providers — Created Provider · {BRAND}")


def test_mcp_save_create_announces_the_server_and_follow_up_syncs_are_silent(
    app_clean: str, page: Page
) -> None:
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="name"]').fill("created-mcp")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command-runtime"]').select_option("__custom__")
    page.locator('[data-field="command"]').fill("created-mcp")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    route = _nav.wait_for_route_prefix(
        page, "library/mcp/", not_equal="library/mcp/~new", timeout=8000
    )
    expect(page.locator(ANNOUNCER)).to_have_text("Library — MCP servers — created-mcp")
    expect(page).to_have_title(f"Library — MCP servers — created-mcp · {BRAND}")
    _nav.wait_settled(page)

    # The create path's follow-up syncs (a same-key re-sync of the item, and a
    # section-root sync) never announce: the previous key is the item now.
    page.evaluate(_COUNT_JS)
    source_id = route.split("/")[-1]
    page.evaluate("id => App.router.sync('studio', 'mcp-sources/' + id)", source_id)
    page.evaluate("() => App.router.sync('studio', 'mcp-sources')")
    assert _writes(page) == 0
    expect(page.locator(ANNOUNCER)).to_have_text("Library — MCP servers — created-mcp")


SENTINEL = "sentinel: nothing announced"


def _seed_sentinel(page: Page) -> None:
    page.evaluate(
        "t => { document.querySelector('[data-testid=\"route-announcer\"]').textContent = t; }",
        SENTINEL,
    )
    page.evaluate(_COUNT_JS)


def _sync(page: Page, area: str, sub: str | None) -> bool:
    return page.evaluate("([a, s]) => App.router.sync(a, s)", [area, sub])


def _assert_silent(page: Page) -> None:
    assert _writes(page) == 0
    expect(page.locator(ANNOUNCER)).to_have_text(SENTINEL)


def test_other_syncs_never_announce(app_with_agent: SeededApp, page: Page) -> None:
    base, name = app_with_agent.base_url, app_with_agent.agent_name
    kb = _post(base, "/api/knowledge-bases", {"name": "Sync KB"})

    # A Chats session sync (chat.js on session_joined) and a canonicalisation.
    _nav.goto_settled(page, base, "chats")
    _seed_sentinel(page)
    assert _sync(page, "chat", "sessions/some-session") is True
    assert _sync(page, "chat", "sessions/some-session") is True  # same key
    _assert_silent(page)

    # Agents syncs: opening an item's tab route, and back to the root.
    _nav.open_destination(page, "agents")
    expect(page.locator(ANNOUNCER)).to_have_text("Agents")
    _seed_sentinel(page)
    assert _sync(page, "studio", f"agents/{_nav.seg(name)}/general") is True
    assert _sync(page, "studio", "agents") is True
    _assert_silent(page)

    # Studio section syncs: same-key canonicalisation and a section change.
    _go_and_read(page, "library")
    _seed_sentinel(page)
    assert _sync(page, "studio", "library") is True
    assert _sync(page, "studio", "mcp-sources") is True  # a bare section sub folds to the root
    _assert_silent(page)

    # From ~new: an item in ANOTHER section, and the section root.
    for sub in (f"knowledge/{_nav.seg(kb['id'])}", "library"):
        _, spoken = _go_and_read(page, "library/mcp/~new")
        assert spoken == "Library — MCP servers — New"
        _seed_sentinel(page)
        assert _sync(page, "studio", sub) is True
        _assert_silent(page)


def test_new_chat_route_announces_the_agent_and_the_first_send_sync_is_silent(
    app_with_provider: SeededApp, page: Page
) -> None:
    """M25 F4 leg 3b (AC10): `#chats/~new/{agent}` is titled and announced
    "New chat with {agent}" (its key names the agent, so a re-pick of another
    agent announces), and the first send's sync to `chats/{id}` is SILENT.
    That silence is by construction, not by a special case: the key
    `chats//~new/{agent}` does not end in `/~new`, so isCreateToItem is false.
    Pinned because it is an accidental property."""
    base = app_with_provider.base_url
    seed_mock_agent(base, app_with_provider.provider_id, name="Alpha")
    seed_mock_agent(base, app_with_provider.provider_id, name="Beta")
    _nav.goto_settled(page, base, "chats")
    title, spoken = _go_and_read(page, "chats/~new/Alpha")
    assert spoken == "Chats — New chat with Alpha"
    assert title == f"Chats — New chat with Alpha · {BRAND}"
    _, spoken = _go_and_read(page, "chats/~new/Beta")  # a re-pick announces
    assert spoken == "Chats — New chat with Beta"
    _seed_sentinel(page)
    sid = _chats.send_first(page, "hello")
    _nav.expect_route(page, f"chats/{_nav.seg(sid)}")
    _assert_silent(page)
    expect(page).to_have_title(f"Chats · {BRAND}")
