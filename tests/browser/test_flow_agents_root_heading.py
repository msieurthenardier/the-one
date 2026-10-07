"""Flight 6 leg 1a: the Agents and Library roots' visually hidden ``h1`` (DD11)
and the Tools tab's category master toggle's accessible name (squawk 0113).

At a root with no editor open the page has exactly one ``h1``, visually hidden
("Agents" / "Library"); with an item open, ``.editor-title`` is the only one.
Falls in the ``agents`` lane (``test_flow_agents_*``); the Library roots are
covered here too, since the heading is built by the one Studio area module.
"""

from __future__ import annotations

import pytest
from browser import _lists, _nav
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

H1S = "#main-content h1"


def _h1_texts(page: Page) -> list[str]:
    return page.evaluate(
        "(s) => Array.from(document.querySelectorAll(s))"
        ".filter((h) => h.getClientRects().length).map((h) => h.textContent.trim())",
        H1S,
    )


@pytest.mark.browser
def test_agents_root_has_one_hidden_h1_and_editor_title_replaces_it(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto(page, app_with_agent.base_url, "agents")
    expect(page.locator('[data-testid="root-heading"]')).to_have_text("Agents", timeout=8000)
    assert _h1_texts(page) == ["Agents"]
    root = page.locator('[data-testid="root-heading"]')
    # DD15 (leg 4c): the h1 is the start page's visible title.
    assert not root.evaluate("e => e.classList.contains('visually-hidden')")
    assert root.evaluate("e => e.getBoundingClientRect().width") > 1

    _lists.open_item(page, "agents", app_with_agent.agent_name)
    expect(page.locator(".editor-title")).to_be_visible(timeout=8000)
    assert _h1_texts(page) == [app_with_agent.agent_name]
    expect(page.locator('[data-testid="root-heading"]')).to_have_count(0)

    _lists.close_item(page)
    expect(page.locator('[data-testid="root-heading"]')).to_have_text("Agents", timeout=8000)
    assert _h1_texts(page) == ["Agents"]


@pytest.mark.browser
@pytest.mark.parametrize("section", ["knowledge", "mcp", "connectors"])
def test_library_roots_have_one_hidden_h1(app_clean: str, page: Page, section: str) -> None:
    """Zero items in every group: the h1 sits beside the empty state."""
    _nav.goto(page, app_clean, f"library/{section}")
    expect(page.locator('[data-testid="root-heading"]')).to_have_text("Library", timeout=8000)
    assert _h1_texts(page) == ["Library"]
    # The start page's blocks are h2s (DD15): one per type.
    expect(page.locator(f'[data-testid="library-empty-{section}"] h2')).to_have_count(3)


@pytest.mark.browser
def test_library_open_item_has_only_the_editor_h1(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "library/mcp/~new")
    expect(page.locator(".editor-title")).to_be_visible(timeout=8000)
    assert len(_h1_texts(page)) == 1
    expect(page.locator('[data-testid="root-heading"]')).to_have_count(0)


@pytest.mark.browser
def test_tools_tab_category_master_toggles_are_named(app_with_agent: SeededApp, page: Page) -> None:
    _nav.goto(page, app_with_agent.base_url, f"agents/{_nav.seg(app_with_agent.agent_name)}/tools")
    masters = page.locator("input[data-category-master]")
    expect(masters.first).to_be_attached(timeout=8000)
    assert masters.count() >= 1
    for i in range(masters.count()):
        cat = masters.nth(i).get_attribute("data-category-master")
        assert masters.nth(i).get_attribute("aria-label") == f"Enable all {cat} tools"


# ── Leg 4c (DD15): the start pages ─────────────────────────────────────────

LIBRARY_ORDER = [
    ("knowledge", "Knowledge bases"),
    ("mcp", "MCP servers"),
    ("connectors", "Connectors"),
]


@pytest.mark.browser
def test_agents_start_page_with_agents(app_with_agent: SeededApp, page: Page) -> None:
    _nav.goto(page, app_with_agent.base_url, "agents")
    state = page.locator('[data-testid="agent-select-empty"]')
    expect(state).to_be_visible(timeout=8000)
    expect(state).to_contain_text("An agent is an assistant you set up for a kind of work.")
    expect(state).to_contain_text("Pick an agent from the list to edit it.")
    expect(state.locator("h1, h2")).to_have_count(0)
    assert _h1_texts(page) == ["Agents"]
    page.locator('[data-testid="agent-empty-new"]').click()
    _nav.expect_route(page, "agents/~new")


@pytest.mark.browser
def test_agents_start_page_with_no_agents(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto(page, app_with_provider.base_url, "agents")
    state = page.locator('[data-testid="agent-empty"]')
    expect(state).to_be_visible(timeout=8000)
    expect(state).to_contain_text("An agent is an assistant you set up for a kind of work.")
    expect(state).to_contain_text("No agents yet.")
    assert _h1_texts(page) == ["Agents"]
    page.locator('[data-testid="agent-empty-new"]').click()
    _nav.expect_route(page, "agents/~new")


def _expect_library_page(page: Page, section: str) -> None:
    root = page.locator(f'[data-testid="library-empty-{section}"]')
    expect(root).to_be_visible(timeout=8000)
    assert _h1_texts(page) == ["Library"]
    expect(root.locator("h1")).to_have_count(0)
    expect(root.locator("h2")).to_have_text([label for _, label in LIBRARY_ORDER])
    for kind, _ in LIBRARY_ORDER:
        expect(root.locator(f'[data-testid="library-empty-{kind}-add"]')).to_be_visible()


@pytest.mark.browser
@pytest.mark.parametrize("section", ["knowledge", "mcp", "connectors"])
def test_library_start_page_at_every_root(app_clean: str, page: Page, section: str) -> None:
    _nav.goto(page, app_clean, f"library/{section}")
    _expect_library_page(page, section)
    # An Add button other than the route's own opens its own create route.
    other = "connectors" if section != "connectors" else "knowledge"
    page.locator(f'[data-testid="library-empty-{other}-add"]').click()
    _nav.expect_route(page, f"library/{other}/~new")


@pytest.mark.browser
def test_start_pages_do_not_overflow_at_1024(app_with_agent: SeededApp, page: Page) -> None:
    page.set_viewport_size({"width": 1024, "height": 768})
    for route in ("agents", "library/knowledge"):
        _nav.goto(page, app_with_agent.base_url, route)
        expect(page.locator('[data-testid="root-heading"]')).to_be_visible(timeout=8000)
        assert page.evaluate(
            "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
        assert page.evaluate(
            "() => { const m = document.querySelector('#main-content');"
            " return m.scrollWidth <= m.clientWidth; }"
        )


@pytest.mark.browser
def test_library_start_page_survives_failed_collection_loads(app_clean: str, page: Page) -> None:
    for coll in ("knowledge-bases", "mcp-sources", "connectors"):
        page.route(f"**/api/{coll}", lambda route: route.fulfill(status=500, body="{}"))
    _nav.goto(page, app_clean, "library/mcp")
    _expect_library_page(page, "mcp")
