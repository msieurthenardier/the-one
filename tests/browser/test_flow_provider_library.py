"""Model providers in Library (sortie 02, leg 1).

The Library list's first group, "Model providers", and the provider editor in
the detail pane at ``#library/providers[/~new|/{id}]``. Settings still hosts
providers too until leg 2 (DD11), so these tests only ever open a provider
editor through the Library routes, and the Settings provider tests (the rest of
the ``providers`` lane) only through Settings: no page here holds both editors.
"""

from __future__ import annotations

import re

import httpx
import pytest
from browser import _lists, _nav, _providers
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_knowledge_base, seed_mock_provider
from playwright.sync_api import Page, expect

LIST = '[data-testid="library-list"]'


def _create_mock_provider(page: Page, name: str) -> None:
    """Fill and submit the create form (the mock type is the first option)."""
    page.locator("#pf-name").fill(name)
    page.locator("#pf-type").select_option("mock")
    page.locator('[data-testid="save-provider-btn"]').click()


def _provider_id(base: str, name: str) -> str:
    rows = httpx.get(f"{base}/api/providers", headers=auth_headers_for(base), timeout=5.0).json()
    return next(r["id"] for r in rows if r["name"] == name)


@pytest.mark.browser
def test_model_providers_is_the_first_group_with_badge_and_used_by(
    app_with_agent: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_agent.base_url, "library")
    captions = page.locator(f"{LIST} .ui-list-pane-caption")
    expect(captions.first).to_have_text("Model providers", timeout=8000)
    expect(captions).to_have_text(
        ["Model providers", "Knowledge bases", "MCP servers", "Connectors", "Secrets"]
    )
    row = _lists.list_row(page, "library/providers", "mock")
    expect(row).to_have_count(1)
    expect(row).to_have_attribute(
        "href", re.compile("^" + re.escape(_nav.href("library/providers")) + "/")
    )
    expect(row.locator(".badge")).to_have_text("mock")
    expect(row).to_contain_text("1 agent")
    # An empty library says so in the group, not with a missing group.
    _nav.goto_settled(page, app_with_agent.base_url, "library")
    expect(page.locator(f"{LIST} .ui-list-pane-group-empty")).to_have_count(4)


@pytest.mark.browser
def test_start_page_has_four_cards_providers_first(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "library")
    start = _lists.library_start(page)
    expect(start).to_be_visible(timeout=8000)
    expect(start.locator(".start-page-card-title")).to_have_text(
        ["Model providers", "Knowledge bases", "MCP servers", "Connectors", "Secrets"]
    )
    expect(start).to_contain_text("The connection an agent uses to reach a model")
    page.locator('[data-testid="library-start-providers-add"]').click()
    _nav.expect_route(page, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)


@pytest.mark.browser
def test_add_menu_creates_a_provider_and_opens_it_clean(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "library")
    _lists.library_add(page, "providers")
    # The Library chrome: exactly one h1 (the editor title) and the breadcrumb.
    expect(page.locator("h1")).to_have_count(1)
    expect(page.locator("h1.editor-title")).to_have_text("New model provider")
    crumb = _lists.breadcrumb_link(page)
    expect(crumb).to_have_text("Library")
    expect(page.locator(".editor-breadcrumb")).to_have_text("Library / Model providers")
    _create_mock_provider(page, "Made in Library")
    new_id = None
    expect(page.locator('[data-testid="delete-provider-btn"]')).to_be_visible(timeout=8000)
    new_id = _provider_id(app_clean, "Made in Library")
    _nav.expect_route(page, f"library/providers/{_nav.seg(new_id)}")
    expect(page.locator(".editor-title")).to_have_text("Made in Library")
    assert not _providers.studio_dirty(page)
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("")
    # No "Provider created" flash survives the re-mount (DD7), and the list
    # row is there and selected.
    expect(page.locator(".app-flash")).to_have_count(0)
    _lists.expect_selected(page, "library/providers", "Made in Library")


@pytest.mark.browser
def test_edit_then_save_keeps_the_editor_and_clears_the_unsaved_caption(
    app_with_provider: SeededApp, page: Page
) -> None:
    pid = app_with_provider.provider_id
    _nav.goto(page, app_with_provider.base_url, f"library/providers/{_nav.seg(pid)}")
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    _lists.expect_selected(page, "library/providers", "mock")
    page.locator("#pf-name").fill("renamed")
    expect(page.locator('[data-testid="editor-unsaved"]')).not_to_have_text("")
    assert _providers.studio_dirty(page)
    page.locator('[data-testid="save-provider-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("renamed", timeout=8000)
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("")
    assert not _providers.studio_dirty(page)
    _nav.expect_route(page, f"library/providers/{_nav.seg(pid)}")
    expect(_lists.list_row(page, "library/providers", "renamed")).to_have_count(1, timeout=8000)


@pytest.mark.browser
def test_delete_lands_on_library_with_focus_on_the_neighbour(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    seed_mock_provider(base, name="zeta")
    _nav.goto(page, base, f"library/providers/{_nav.seg(app_with_provider.provider_id)}")
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    delete_btn.click()
    delete_btn.click()
    _nav.expect_route(page, "library")
    expect(_lists.library_start(page)).to_be_visible(timeout=8000)
    zeta = _lists.list_row(page, "library/providers", "zeta")
    expect(zeta).to_have_count(1, timeout=8000)
    expect(zeta).to_be_focused()
    assert not _providers.studio_dirty(page)


@pytest.mark.browser
def test_cold_deep_link_opens_the_editor_and_a_dead_id_heals(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    _nav.goto(page, base, f"library/providers/{_nav.seg(app_with_provider.provider_id)}")
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    _nav.goto(page, base, "library/providers/does-not-exist")
    _nav.expect_route(page, "library", timeout=8000)
    expect(_lists.library_start(page)).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_bare_providers_section_is_an_alias_for_the_library_root(
    app_clean: str, page: Page
) -> None:
    _nav.goto(page, app_clean, "library/providers")
    _nav.expect_route(page, "library")
    assert page.evaluate("location.hash") == _nav.href("library")


@pytest.mark.browser
def test_breadcrumb_closes_to_library_and_focuses_the_row(
    app_with_provider: SeededApp, page: Page
) -> None:
    pid = app_with_provider.provider_id
    _nav.goto(page, app_with_provider.base_url, f"library/providers/{_nav.seg(pid)}")
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    _lists.close_item(page)
    _nav.expect_route(page, "library")
    expect(_lists.library_start(page)).to_be_visible()
    expect(_lists.list_row(page, "library/providers", "mock")).to_be_focused(timeout=5000)


@pytest.mark.browser
def test_create_cancel_returns_to_library_and_focuses_the_group_start(
    app_with_provider: SeededApp, page: Page
) -> None:
    _nav.goto_settled(page, app_with_provider.base_url, "library")
    _lists.library_add(page, "providers")
    page.locator('[data-testid="cancel-provider-btn"]').click()
    _nav.expect_route(page, "library")
    expect(_lists.library_start(page)).to_be_visible()
    expect(_lists.list_row(page, "library/providers", "mock")).to_be_focused(timeout=5000)


@pytest.mark.browser
def test_plan_create_remounts_in_edit_mode_and_starts_sign_in(app_clean: str, page: Page) -> None:
    """The create-to-edit hand-off (pendingAutoSignInId) works from Library:
    one click on the sign-in button creates the provider, re-mounts the editor
    in edit mode and shows the consent UI with no second click."""
    _providers.block_claude_ai(page)
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    page.locator("#pf-type").select_option("anthropic-plan")
    page.locator("#pf-name").fill("Library Plan")
    page.locator('[data-testid="plan-signin-btn"]').click()
    expect(page.locator('[data-testid="plan-signin-consent"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="plan-signin-url"]')).to_have_value(
        re.compile(r"^https://claude\.ai/oauth/authorize\?")
    )
    expect(page.locator('[data-testid="plan-code-input"]')).to_be_visible()
    expect(page.locator('[data-testid="test-connection-btn"]')).to_be_visible()
    new_id = _provider_id(app_clean, "Library Plan")
    _nav.expect_route(page, f"library/providers/{_nav.seg(new_id)}")


@pytest.mark.browser
def test_jump_to_reaches_a_provider(app_with_provider: SeededApp, page: Page) -> None:
    _nav.goto_settled(page, app_with_provider.base_url, "chats")
    page.keyboard.press("Control+k")
    page.locator('[data-testid="jump-to-input"]').fill("mock")
    row = page.locator('[data-testid="jump-to-result"][data-kind="provider"]')
    expect(row).to_have_count(1, timeout=8000)
    expect(row).to_contain_text("Library · Model provider")
    row.click()
    _nav.expect_route(page, f"library/providers/{_nav.seg(app_with_provider.provider_id)}")
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)


@pytest.mark.browser
def test_dirty_provider_editor_asks_once_before_a_rail_navigation(
    app_with_provider: SeededApp, page: Page
) -> None:
    pid = app_with_provider.provider_id
    _nav.goto(page, app_with_provider.base_url, f"library/providers/{_nav.seg(pid)}")
    expect(page.locator(".editor-title")).to_have_text("mock", timeout=8000)
    page.locator("#pf-name").fill("dirty")
    _nav.open_destination(page, "agents")
    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_have_count(1, timeout=5000)
    # Stay keeps the editor and its edit.
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(overlay).to_have_count(0)
    expect(page.locator("#pf-name")).to_have_value("dirty")
    _nav.expect_route(page, f"library/providers/{_nav.seg(pid)}")


@pytest.mark.browser
def test_a_create_resolving_after_the_user_left_does_not_move_the_url_back(
    app_clean: str, page: Page
) -> None:
    """The save-create staleness guard holds for providers: a create whose
    response lands after a breadcrumb go to #library cannot sync the URL back."""
    _nav.goto(page, app_clean, "library/providers/~new")
    expect(page.locator(".editor-title")).to_have_text("New model provider", timeout=8000)
    page.locator("#pf-name").fill("Held create")
    page.locator("#pf-type").select_option("mock")
    held: list = []

    def handler(route) -> None:
        if route.request.method == "POST":
            held.append(route)  # keep it: not fulfilled until released
        else:
            route.continue_()

    page.route("**/api/providers", handler)
    page.locator('[data-testid="save-provider-btn"]').click()
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(50)
    assert held, "the create POST never reached the route handler"

    _lists.close_item(page)
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible(timeout=5000)
    page.locator('[data-testid="modal-confirm-btn"]').click()
    _nav.expect_route(page, "library")
    expect(_lists.library_start(page)).to_be_visible(timeout=5000)

    held[0].continue_()
    page.unroute("**/api/providers", handler)
    # The provider is created and listed, but the URL and the page stay on the root.
    expect(_lists.list_row(page, "library/providers", "Held create")).to_have_count(1, timeout=8000)
    assert page.evaluate("location.hash") == _nav.href("library")
    expect(_lists.library_start(page)).to_be_visible()
    expect(page.locator(".editor-title")).to_have_count(0)


# ── Stale in-flight edit/delete callbacks (review fix round 2) ──────────


def _hold(page: Page, pattern: str, method: str) -> tuple[list, object]:
    """Hold requests of *method* to *pattern*; returns (held routes, handler)."""
    held: list = []

    def handler(route) -> None:
        if route.request.method == method:
            held.append(route)
        else:
            route.continue_()

    page.route(pattern, handler)
    return held, handler


def _wait_held(page: Page, held: list) -> None:
    for _ in range(100):
        if held:
            return
        page.wait_for_timeout(50)
    raise AssertionError("the held request never reached the route handler")


def _leave_to(page: Page, dest: str, name: str) -> None:
    """Click the row *name*; confirm the leave guard if it asks."""
    _lists.item_link(page, dest, name).click()
    dialog = page.locator('[data-testid="confirm-dialog-overlay"]')
    try:
        dialog.wait_for(state="visible", timeout=1500)
    except Exception:  # noqa: BLE001 - a clean editor does not ask
        return
    page.locator('[data-testid="modal-confirm-btn"]').click()


@pytest.mark.browser
def test_a_held_edit_save_resolving_on_another_library_item_leaves_it_alone(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    pid = app_with_provider.provider_id
    seed_knowledge_base(base, "Held KB")
    _nav.goto(page, base, f"library/providers/{_nav.seg(pid)}")
    expect(page.locator("#pf-name")).to_be_visible(timeout=8000)
    page.locator("#pf-name").fill("mock renamed")
    held, handler = _hold(page, f"**/api/providers/{pid}", "PUT")
    page.locator('[data-testid="save-provider-btn"]').click()
    _wait_held(page, held)
    # Revert the field so the editor reads clean again: leaving then asks nothing,
    # so no discard bumps the editor generation (the path the guard must cover).
    page.locator("#pf-name").fill("mock")
    assert not _providers.studio_dirty(page)

    _leave_to(page, "library/knowledge", "Held KB")
    expect(page.locator('[data-testid="kb-name-input"]')).to_be_visible(timeout=8000)
    kb_route = page.evaluate("location.hash")
    page.locator('[data-testid="kb-name-input"]').fill("Held KB edited")
    assert _providers.studio_dirty(page)

    held[0].continue_()
    page.wait_for_timeout(1000)
    page.unroute(f"**/api/providers/{pid}", handler)
    assert page.evaluate("location.hash") == kb_route
    expect(page.locator('[data-testid="kb-name-input"]')).to_have_value("Held KB edited")
    assert _providers.studio_dirty(page), (
        "a stale provider save cleared the new editor's dirty flag"
    )


@pytest.mark.browser
def test_a_held_edit_save_resolving_on_another_provider_leaves_it_alone(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    pid = app_with_provider.provider_id
    bid = seed_mock_provider(base, name="beta")
    _nav.goto(page, base, f"library/providers/{_nav.seg(pid)}")
    expect(page.locator("#pf-name")).to_have_value("mock", timeout=8000)
    page.locator("#pf-name").fill("mock renamed")
    held, handler = _hold(page, f"**/api/providers/{pid}", "PUT")
    page.locator('[data-testid="save-provider-btn"]').click()
    _wait_held(page, held)
    # Revert the field so the editor reads clean again: leaving then asks nothing,
    # so no discard bumps the editor generation (the path the guard must cover).
    page.locator("#pf-name").fill("mock")
    assert not _providers.studio_dirty(page)

    _leave_to(page, "library/providers", "beta")
    _nav.expect_route(page, f"library/providers/{_nav.seg(bid)}")
    expect(page.locator("#pf-name")).to_have_value("beta", timeout=8000)
    page.locator("#pf-name").fill("beta edited")

    held[0].continue_()
    page.wait_for_timeout(1000)
    page.unroute(f"**/api/providers/{pid}", handler)
    _nav.expect_route(page, f"library/providers/{_nav.seg(bid)}")
    _lists.expect_selected(page, "library/providers", "beta")
    expect(page.locator("#pf-name")).to_have_value("beta edited")
    assert _providers.studio_dirty(page)


@pytest.mark.browser
def test_a_held_delete_resolving_on_another_provider_leaves_it_alone(
    app_with_provider: SeededApp, page: Page
) -> None:
    base = app_with_provider.base_url
    pid = app_with_provider.provider_id
    bid = seed_mock_provider(base, name="beta")
    _nav.goto(page, base, f"library/providers/{_nav.seg(pid)}")
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    expect(delete_btn).to_be_visible(timeout=8000)
    held, handler = _hold(page, f"**/api/providers/{pid}", "DELETE")
    delete_btn.click()
    delete_btn.click()
    _wait_held(page, held)

    _leave_to(page, "library/providers", "beta")
    _nav.expect_route(page, f"library/providers/{_nav.seg(bid)}")
    expect(page.locator("#pf-name")).to_have_value("beta", timeout=8000)

    held[0].continue_()
    page.wait_for_timeout(1000)
    page.unroute(f"**/api/providers/{pid}", handler)
    _nav.expect_route(page, f"library/providers/{_nav.seg(bid)}")
    expect(page.locator("#pf-name")).to_have_value("beta")
    expect(_lists.list_row(page, "library/providers", "mock")).to_have_count(0, timeout=8000)
