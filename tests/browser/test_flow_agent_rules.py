"""The agent editor's Rules and notes tab, Rules section (M27 F1 L2; flight DD6, DD8).

Add, edit and cancel, toggle, move up and down, an armed delete, the empty state,
create mode, a 422 shown inline, persistence across a reload, and the deep link.
Every control saves immediately through the REST API (no Save button, no dirty
state). Falls in the ``agents`` lane via the ``test_flow_agent_*`` glob.
"""

from __future__ import annotations

import httpx
import pytest
from browser import _lists, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

ROWS = '[data-testid="rules-row"]'


def _add(base: str, agent: str, text: str, enabled: bool = True) -> str:
    r = httpx.post(
        f"{base}/api/agents/{agent}/rules",
        json={"text": text, "enabled": enabled},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _stored(base: str, agent: str) -> list[dict]:
    r = httpx.get(f"{base}/api/agents/{agent}/rules", headers=auth_headers_for(base), timeout=5)
    assert r.status_code == 200, r.text
    return r.json()["rules"]


def _open_tab(page: Page, base: str, agent: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(agent)}/rules-and-notes")
    expect(page.locator('[data-testid="tab-rules-and-notes"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    expect(page.locator('[data-testid="rules-section"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="rules-add-input"]')).to_be_visible()


def _texts(page: Page) -> list[str]:
    return page.locator('[data-testid="rules-row-text"]').all_inner_texts()


def test_deep_link_empty_state_and_section_chrome(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    expect(page.locator('[data-testid="rules-empty"]')).to_have_text("No rules yet.")
    expect(page.locator('[data-testid="rules-applies-note"]')).to_have_text(
        "Changes apply to new and reopened chats, and to the next message in connector channels."
    )
    expect(page.locator('[data-testid="rules-section"] h3')).to_have_text("Rules")
    expect(page.locator("label[for]", has_text="Add a rule")).to_be_visible()
    expect(page.locator('[data-testid="rules-add-count"]')).to_have_text("0 / 500")
    add = page.locator('[data-testid="rules-add-btn"]')
    expect(add).to_be_disabled()
    page.locator('[data-testid="rules-add-input"]').fill("   ")
    expect(add).to_be_disabled()
    page.locator('[data-testid="rules-add-input"]').fill("abc")
    expect(page.locator('[data-testid="rules-add-count"]')).to_have_text("3 / 500")
    expect(add).to_be_enabled()
    _nav.expect_route(page, f"agents/{_nav.seg(agent)}/rules-and-notes")


def test_tab_is_second_and_reachable_by_click_and_arrow_keys(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _nav.goto(page, base, f"agents/{_nav.seg(agent)}/general")
    tabs = page.locator('[role="tab"]')
    expect(tabs).to_have_count(6, timeout=8000)
    assert tabs.nth(1).get_attribute("data-tab-id") == "rules-and-notes"
    page.locator('[data-testid="tab-general"]').focus()
    page.keyboard.press("ArrowRight")
    assert page.evaluate("document.activeElement?.id") == "agent-tab-rules-and-notes"
    page.keyboard.press("Enter")
    _nav.expect_route(page, f"agents/{_nav.seg(agent)}/rules-and-notes")
    expect(page.locator("#agent-tab-panel-rules-and-notes")).to_be_visible()


def test_add_persists_across_reload_and_focus_returns_to_the_cleared_input(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    box = page.locator('[data-testid="rules-add-input"]')
    box.fill("Answer in French.")
    page.locator('[data-testid="rules-add-btn"]').click()
    expect(page.locator(ROWS)).to_have_count(1, timeout=8000)
    assert _texts(page) == ["Answer in French."]
    expect(box).to_have_value("")
    expect(box).to_be_focused()
    box.fill("Be brief.")
    page.locator('[data-testid="rules-add-btn"]').click()
    expect(page.locator(ROWS)).to_have_count(2, timeout=8000)
    assert [r["text"] for r in _stored(base, agent)] == ["Answer in French.", "Be brief."]
    # Saving a rule never dirties the General form or trips the leave guard.
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("")
    page.reload()
    expect(page.locator(ROWS)).to_have_count(2, timeout=8000)
    assert _texts(page) == ["Answer in French.", "Be brief."]


def test_edit_save_and_cancel(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _add(base, agent, "First rule.")
    _open_tab(page, base, agent)
    row = page.locator(ROWS).first
    expect(row).to_be_visible(timeout=8000)

    row.locator('[data-testid="rules-row-edit"]').click()
    edit = row.locator('[data-testid="rules-row-edit-input"]')
    expect(edit).to_be_focused()
    edit.fill("Changed but cancelled.")
    row.locator('[data-testid="rules-row-cancel"]').click()
    expect(row.locator('[data-testid="rules-row-text"]')).to_have_text("First rule.")
    expect(row.locator('[data-testid="rules-row-edit"]')).to_be_focused()
    assert _stored(base, agent)[0]["text"] == "First rule."

    row.locator('[data-testid="rules-row-edit"]').click()
    row.locator('[data-testid="rules-row-edit-input"]').fill("Saved edit.")
    row.locator('[data-testid="rules-row-save"]').click()
    expect(row.locator('[data-testid="rules-row-text"]')).to_have_text("Saved edit.", timeout=8000)
    expect(row.locator('[data-testid="rules-row-edit"]')).to_be_focused()
    assert _stored(base, agent)[0]["text"] == "Saved edit."


def test_toggle_disables_a_rule_and_keeps_its_place(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _add(base, agent, "One.")
    _add(base, agent, "Two.")
    _add(base, agent, "Three.")
    _open_tab(page, base, agent)
    second = page.locator(ROWS).nth(1)
    toggle = second.locator('[data-testid="rules-row-toggle"]')
    expect(toggle).to_be_checked(timeout=8000)
    assert toggle.get_attribute("role") == "switch"
    assert "Rule 2" in page.evaluate("(el) => el.labels[0].textContent", toggle.element_handle())
    toggle.click(force=True)
    second = page.locator(ROWS).nth(1)
    expect(second).to_have_attribute("data-enabled", "false", timeout=8000)
    expect(second).to_have_class(__import__("re").compile("rules-row--off"))
    expect(second.locator('[data-testid="rules-row-toggle"]')).not_to_be_checked()
    assert _texts(page) == ["One.", "Two.", "Three."]
    assert [r["enabled"] for r in _stored(base, agent)] == [True, False, True]


def test_move_up_and_down_with_ends_disabled_and_focus_kept(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    for t in ("A", "B", "C"):
        _add(base, agent, t)
    _open_tab(page, base, agent)
    rows = page.locator(ROWS)
    expect(rows).to_have_count(3, timeout=8000)
    expect(rows.nth(0).locator('[data-testid="rules-row-up"]')).to_be_disabled()
    expect(rows.nth(2).locator('[data-testid="rules-row-down"]')).to_be_disabled()

    rows.nth(2).locator('[data-testid="rules-row-up"]').click()
    expect(page.locator('[data-testid="rules-row-text"]').nth(1)).to_have_text("C", timeout=8000)
    assert _texts(page) == ["A", "C", "B"]
    # Focus stays on the moved row's Move up button.
    expect(rows.nth(1).locator('[data-testid="rules-row-up"]')).to_be_focused()
    rows.nth(1).locator('[data-testid="rules-row-up"]').click()
    expect(page.locator('[data-testid="rules-row-text"]').nth(0)).to_have_text("C", timeout=8000)
    # At the top its Move up is disabled, so focus moves to the other button.
    expect(rows.nth(0).locator('[data-testid="rules-row-down"]')).to_be_focused()
    assert [r["text"] for r in _stored(base, agent)] == ["C", "A", "B"]
    rows.nth(0).locator('[data-testid="rules-row-down"]').click()
    expect(page.locator('[data-testid="rules-row-text"]').nth(0)).to_have_text("A", timeout=8000)
    assert [r["text"] for r in _stored(base, agent)] == ["A", "C", "B"]


def test_delete_is_armed_then_confirmed_and_focus_goes_to_the_neighbour(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _add(base, agent, "Keep me.")
    _add(base, agent, "Delete me.")
    _open_tab(page, base, agent)
    rows = page.locator(ROWS)
    expect(rows).to_have_count(2, timeout=8000)
    btn = rows.nth(1).locator('[data-testid="rules-row-delete"]')
    btn.click()
    expect(btn).to_have_class(__import__("re").compile("confirm-delete"))
    assert len(_stored(base, agent)) == 2  # armed only: nothing deleted yet
    btn.click()
    expect(rows).to_have_count(1, timeout=8000)
    assert _texts(page) == ["Keep me."]
    expect(rows.nth(0).locator('[data-testid="rules-row-edit"]')).to_be_focused()
    # Deleting the last one lands focus on the Add textarea and shows the empty state.
    rows.nth(0).locator('[data-testid="rules-row-delete"]').click()
    rows.nth(0).locator('[data-testid="rules-row-delete"]').click()
    expect(page.locator('[data-testid="rules-empty"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="rules-add-input"]')).to_be_focused()
    assert _stored(base, agent) == []


def test_over_limit_state_is_text_and_aria_and_blocks_add(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _add(base, agent, "Existing.")
    _open_tab(page, base, agent)
    expect(page.locator(ROWS)).to_have_count(1, timeout=8000)
    box = page.locator('[data-testid="rules-add-input"]')
    box.fill("x" * 501)
    expect(page.locator('[data-testid="rules-add-count"]')).to_have_text(
        "501 / 500 \u2014 over the limit"
    )
    expect(box).to_have_attribute("aria-invalid", "true")
    expect(page.locator('[data-testid="rules-add-btn"]')).to_be_disabled()
    expect(page.locator('[data-testid="rules-add-count"]')).not_to_have_attribute(
        "aria-live", "polite"
    )
    box.fill("ok")
    expect(box).not_to_have_attribute("aria-invalid", "true")
    expect(page.locator('[data-testid="rules-add-btn"]')).to_be_enabled()
    page.locator('[data-testid="rules-add-btn"]').click()
    expect(page.locator(ROWS)).to_have_count(2, timeout=8000)


def test_failed_toggle_and_failed_save_restore_focus(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _add(base, agent, "Alpha.")
    _open_tab(page, base, agent)
    rows = page.locator(ROWS)
    expect(rows).to_have_count(1, timeout=8000)

    def fail_put(route):
        if route.request.method == "PUT":
            route.fulfill(status=500, content_type="application/json", body='{"detail":"boom"}')
        else:
            route.continue_()

    page.route("**/api/agents/*/rules/**", fail_put)
    toggle = rows.nth(0).locator('[data-testid="rules-row-toggle"]')
    toggle.focus()
    page.keyboard.press("Space")
    expect(page.locator('[data-testid="rules-error"]')).to_be_visible(timeout=8000)
    _lists.wait_active_testid(page, ("rules-row-toggle", "rules-row-edit"))

    rows.nth(0).locator('[data-testid="rules-row-edit"]').click()
    inp = rows.nth(0).locator('[data-testid="rules-row-edit-input"]')
    inp.fill("Beta.")
    save = rows.nth(0).locator('[data-testid="rules-row-save"]')
    save.focus()
    save.click()
    expect(page.locator('[data-testid="rules-error"]')).to_be_visible(timeout=8000)
    expect(inp).to_have_value("Beta.")
    _lists.wait_active_testid(page, ("rules-row-save",))


def test_failed_add_keeps_text_shows_error_and_refocuses_the_input(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)

    def fail_post(route):
        if route.request.method == "POST":
            route.fulfill(status=500, content_type="application/json", body='{"detail":"boom"}')
        else:
            route.continue_()

    page.route("**/api/agents/*/rules", fail_post)
    box = page.locator('[data-testid="rules-add-input"]')
    box.fill("Keep me.")
    page.locator('[data-testid="rules-add-btn"]').focus()
    page.keyboard.press("Enter")
    expect(page.locator('[data-testid="rules-error"]')).to_be_visible(timeout=8000)
    expect(box).to_have_value("Keep me.")
    expect(box).to_be_focused()
    assert _stored(base, agent) == []


def test_delete_arm_is_announced(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _add(base, agent, "Alpha.")
    _open_tab(page, base, agent)
    rows = page.locator(ROWS)
    expect(rows).to_have_count(1, timeout=8000)
    rows.nth(0).locator('[data-testid="rules-row-delete"]').click()
    expect(page.locator('[data-testid="ui-confirm-live"]')).to_have_text(
        "Press Delete rule 1 again to confirm delete."
    )


def test_create_mode_shows_save_first_and_no_controls(
    app_with_provider: SeededApp, page: Page
) -> None:
    _nav.goto(page, app_with_provider.base_url, "agents")
    _lists.agents_new(page)
    page.locator('[data-testid="tab-rules-and-notes"]').click()
    expect(page.locator('[data-testid="rules-create-mode"]')).to_have_text(
        "Save the agent first to add rules."
    )
    expect(page.locator('[data-testid="rules-add-input"]')).to_have_count(0)
    expect(page.locator('[data-testid="rules-add-btn"]')).to_have_count(0)


def test_failed_add_by_mouse_click_lands_focus_on_the_add_textarea(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Flight 1 cycle-3 residual: the failure focus comes from the explicit origin,
    not document.activeElement, so a mouse click (which can leave focus on <body>
    in WebKit) still ends on the Add textarea."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)

    def fail_post(route):
        if route.request.method == "POST":
            route.fulfill(status=500, content_type="application/json", body='{"detail":"boom"}')
        else:
            route.continue_()

    page.route("**/api/agents/*/rules", fail_post)
    box = page.locator('[data-testid="rules-add-input"]')
    box.fill("Keep me.")
    page.click('[data-testid="rules-add-btn"]')
    expect(page.locator('[data-testid="rules-error"]')).to_be_visible(timeout=8000)
    expect(box).to_have_value("Keep me.")
    expect(box).to_be_focused()
