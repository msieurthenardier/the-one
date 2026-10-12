"""Provider list rows and editor flows in Library (sortie 02, leg 2).

The provider half of the former ``test_flow_settings_items.py`` and the
surviving scenarios of the former ``test_flow_provider_grid.py``, rewritten
against the Library list rows and detail pane (``#library/providers[/~new|/{id}]``)
now that Settings no longer hosts providers. The Settings tile grid itself (its
layout, title row, ellipsis, two-column flow and tab order) retired with it; what
survives as a Library row is the badge, the "used by" meta, the A-Z order, the
selection, the focus after close, Cancel and delete, and the dirty guard.
Providers lane (``test_flow_provider_*`` in ``scripts/run-tests.sh``).
"""

from __future__ import annotations

import re

import pytest
from browser import _lists, _nav
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

DIALOG = '[data-testid="confirm-dialog-overlay"]'
STAY = '[data-testid="modal-cancel-btn"]'
CONTINUE = '[data-testid="modal-confirm-btn"]'
TITLE = ".editor-title"
UNSAVED = '[data-testid="editor-unsaved"]'


def _seed_three(app: SeededApp) -> dict[str, str]:
    """ "mock" (the fixture's, 0 agents), "Bravo" (2 agents), "Alpha" (1 agent)."""
    base = app.base_url
    ids = {"mock": app.provider_id}
    ids["Bravo"] = seed_mock_provider(base, name="Bravo")
    ids["Alpha"] = seed_mock_provider(base, name="Alpha")
    seed_mock_agent(base, ids["Bravo"], name="bravo one")
    seed_mock_agent(base, ids["Bravo"], name="bravo two")
    seed_mock_agent(base, ids["Alpha"], name="alpha one")
    return ids


def _rows(page: Page):
    return page.locator('[data-testid="library-list"] [data-testid="provider-card"]')


def test_provider_rows_sort_a_z_with_badge_and_used_by_counts(
    app_with_provider: SeededApp, page: Page
) -> None:
    ids = _seed_three(app_with_provider)
    _nav.goto_settled(page, app_with_provider.base_url, "library")
    rows = _rows(page)
    expect(rows).to_have_count(3, timeout=8000)
    page.wait_for_function(
        "() => [...document.querySelectorAll('[data-testid=\"provider-card\"]')]"
        ".every((r) => /agent/.test(r.textContent))"
    )
    # A-Z; the counts come from the agents list (singular for one).
    expected = [("Alpha", "1 agent"), ("Bravo", "2 agents"), ("mock", "0 agents")]
    for i, (name, used) in enumerate(expected):
        row = rows.nth(i)
        expect(row).to_contain_text(name)
        expect(row).to_contain_text(used)
        expect(row.locator(".badge.badge--mock")).to_have_text("mock")
    # The row is the item link (href, data-id), and no row is selected at the root.
    link = _lists.list_row(page, "library/providers", "Bravo")
    expect(link).to_have_attribute("href", _nav.href(f"library/providers/{_nav.seg(ids['Bravo'])}"))
    _lists.expect_none_selected(page, "library/providers")
    # The type badge is quiet lowercase (the retired uppercase eyebrow stays retired).
    assert rows.first.locator(".badge").evaluate("(b) => getComputedStyle(b).textTransform") == (
        "none"
    )


def test_used_by_is_absent_until_agents_load(app_with_provider: SeededApp, page: Page) -> None:
    """While the agents list has never loaded (here: every read fails), a row
    never reads "0 agents" (A23)."""
    page.route("**/api/agents", lambda route: route.fulfill(status=500, body="{}"))
    _nav.goto_settled(page, app_with_provider.base_url, "library")
    row = _lists.list_row(page, "library/providers", "mock")
    expect(row).to_have_count(1, timeout=8000)
    expect(row).not_to_contain_text("agent")


def test_a_row_click_opens_the_provider_and_a_refresh_keeps_it(
    app_with_provider: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_provider.base_url, "library")
    _lists.open_item(page, "library/providers", "mock")
    expect(page.locator(TITLE)).to_have_text("mock", timeout=5000)
    saved_route = _nav.current_route(page)
    assert saved_route == f"library/providers/{_nav.seg(app_with_provider.provider_id)}"
    # The list stays beside the open provider.
    expect(_lists.list_row(page, "library/providers", "mock")).to_be_visible()
    page.reload()
    expect(page.locator(TITLE)).to_have_text("mock", timeout=8000)
    _nav.expect_route(page, saved_route)
    _lists.expect_selected(page, "library/providers", "mock")


def test_create_url_refresh_preserves_create_mode(app_clean: str, page: Page) -> None:
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(TITLE)).to_have_text("New model provider", timeout=8000)
    page.reload()
    expect(page.locator(TITLE)).to_have_text("New model provider", timeout=8000)
    _nav.expect_route(page, "library/providers/~new")


def test_dirty_provider_and_another_row_asks_once(app_with_provider: SeededApp, page: Page) -> None:
    ids = _seed_three(app_with_provider)
    _nav.goto_settled(
        page, app_with_provider.base_url, f"library/providers/{_nav.seg(ids['Alpha'])}"
    )
    expect(page.locator("#pf-name")).to_have_value("Alpha", timeout=8000)
    page.locator("#pf-name").fill("Alpha edited")
    _lists.list_row(page, "library/providers", "Bravo").click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(page.locator("#pf-name")).to_have_value("Alpha edited")
    _nav.expect_route(page, f"library/providers/{_nav.seg(ids['Alpha'])}")
    _lists.expect_selected(page, "library/providers", "Alpha")
    _lists.list_row(page, "library/providers", "Bravo").click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    expect(page.locator("#pf-name")).to_have_value("Bravo", timeout=8000)
    expect(page.locator(DIALOG)).to_have_count(0)
    _lists.expect_selected(page, "library/providers", "Bravo")


def test_dirty_breadcrumb_close_asks_once_and_focuses_the_row(
    app_with_provider: SeededApp, page: Page
) -> None:
    ids = _seed_three(app_with_provider)
    _nav.goto_settled(
        page, app_with_provider.base_url, f"library/providers/{_nav.seg(ids['Bravo'])}"
    )
    expect(page.locator(TITLE)).to_have_text("Bravo", timeout=8000)
    page.locator("#pf-name").fill("Bravo edited")
    _lists.close_item(page)
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    expect(_lists.breadcrumb_link(page)).to_be_focused()
    _lists.close_item(page)
    page.locator(CONTINUE).click()
    _nav.expect_route(page, "library")
    expect(page.locator(TITLE)).to_have_count(0, timeout=5000)
    expect(_lists.list_row(page, "library/providers", "Bravo")).to_be_focused()
    assert page.evaluate("App.nav.isDirty()") is False


def test_create_form_cancel_stays_enabled_when_the_form_is_clean_again(
    app_with_provider: SeededApp, page: Page
) -> None:
    """An edit undone on the create form leaves it clean (Create disabled, no
    caption) but Cancel enabled. (Edit mode's clean-disabled Cancel is pinned by
    `test_flow_provider_editor.py::test_save_and_cancel_disabled_when_clean`.)"""
    _nav.goto_settled(page, app_with_provider.base_url, "library")
    _lists.library_add(page, "providers")
    expect(page.locator(TITLE)).to_have_text("New model provider", timeout=8000)
    name = page.locator("#pf-name")
    cancel = page.locator('[data-testid="cancel-provider-btn"]')
    name.fill("x")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    expect(cancel).to_be_enabled()
    name.fill("")
    expect(page.locator(UNSAVED)).to_have_text("")
    expect(page.locator('[data-testid="save-provider-btn"]')).to_be_disabled()
    expect(cancel).to_be_enabled()
    cancel.click()
    _nav.expect_route(page, "library")
    expect(page.locator(TITLE)).to_have_count(0, timeout=5000)
    expect(page.locator("dialog[open]")).to_have_count(0)


@pytest.mark.parametrize(
    ("victim", "focus"),
    [("Bravo", "mock"), ("mock", "Bravo")],
    ids=["middle-focuses-next", "last-focuses-previous"],
)
def test_delete_focuses_the_nearest_row(
    app_with_provider: SeededApp, page: Page, victim: str, focus: str
) -> None:
    """Delete replaces to the root and focuses the next row, else the previous
    (rows sort A-Z: Alpha, Bravo, mock; no agents use them, so the delete is
    not hard-blocked)."""
    base = app_with_provider.base_url
    ids = {"mock": app_with_provider.provider_id}
    ids["Alpha"] = seed_mock_provider(base, name="Alpha")
    ids["Bravo"] = seed_mock_provider(base, name="Bravo")
    _nav.goto_settled(page, base, f"library/providers/{_nav.seg(ids[victim])}")
    expect(page.locator(TITLE)).to_have_text(victim, timeout=8000)
    delete = page.locator('[data-testid="delete-provider-btn"]')
    delete.click()
    expect(delete).to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=5000)
    delete.click()
    _nav.expect_route(page, "library", timeout=8000)
    expect(page.locator(TITLE)).to_have_count(0, timeout=5000)
    expect(_lists.list_row(page, "library/providers", victim)).to_have_count(0)
    expect(_lists.list_row(page, "library/providers", focus)).to_be_focused()
