# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""The agent editor's General tab on the control library (M31 F2 L06b; flight DD7, DD8).

General is mounted once per editor identity and patched through ``setAgent`` on a
same-identity Save, Cancel and refresh. Each control's own listeners drive the dirty
state (Save, ``.editor-unsaved``); Test is a status line; the danger zone holds Delete
Agent and Purge now. Falls in the ``agents`` lane via the ``test_flow_agent_*`` glob.
"""

from __future__ import annotations

import pytest
from browser import _nav
from browser.seeders import SeededApp, seed_mock_provider
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

SAVE = '[data-testid="save-agent-btn"]'
CANCEL = '[data-testid="cancel-agent-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'


def _open(page: Page, base: str, agent: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(agent)}/general")
    expect(page.locator('[data-field="name"]')).to_be_attached(timeout=8000)
    # The model list has landed once the stored model is selected.
    expect(page.locator("#studio-model")).to_have_value("mock-default", timeout=8000)


def _expect_dirty(page: Page) -> None:
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    expect(page.locator(SAVE)).to_be_enabled()


def _expect_clean(page: Page) -> None:
    expect(page.locator(UNSAVED)).to_have_text("")
    expect(page.locator(SAVE)).to_be_disabled()


def test_field_ids_and_classes(app_with_agent: SeededApp, page: Page) -> None:
    _open(page, app_with_agent.base_url, app_with_agent.agent_name)
    out = page.evaluate(
        """() => ['studio-name','studio-description','studio-provider','studio-model','studio-system-prompt','studio-retention-days','studio-max-iterations'].map((id) => {
          const el = document.getElementById(id);
          const label = document.querySelector('label[for=' + id + ']');
          return [id, el.dataset.field, el.className, !!label];
        })"""
    )
    fields = {row[0]: row for row in out}
    assert fields["studio-name"][1] == "name"
    assert "field-input" in fields["studio-description"][2]
    assert "field-select" in fields["studio-provider"][2]
    assert "field-textarea" in fields["studio-system-prompt"][2]
    assert "field-input-short" in fields["studio-max-iterations"][2]
    assert all(row[3] for row in out)
    attrs = page.evaluate(
        "() => { const r = document.getElementById('studio-retention-days'); return [r.min, r.max, r.type]; }"
    )
    assert attrs == ["1", "365", "number"]


@pytest.mark.parametrize(
    "selector,value",
    [
        ('[data-field="name"]', "renamed-agent"),
        ('[data-field="description"]', "a description"),
        ('[data-field="system_prompt"]', "New instructions"),
        ('[data-field="chat_history_retention_days"]', "45"),
        ('[data-field="max_iterations"]', "7"),
    ],
)
def test_typing_in_a_general_field_enables_save(
    app_with_agent: SeededApp, page: Page, selector: str, value: str
) -> None:
    _open(page, app_with_agent.base_url, app_with_agent.agent_name)
    _expect_clean(page)
    box = page.locator(selector)
    box.click()
    box.press("Control+A")
    page.keyboard.type(value)
    _expect_dirty(page)
    # Cancel reverts the edit.
    page.locator(CANCEL).click()
    _expect_clean(page)


def test_provider_change_enables_save_then_cancel_restores_selects(
    app_with_agent: SeededApp, page: Page
) -> None:
    base = app_with_agent.base_url
    other = seed_mock_provider(
        base, name="other", config={"models": ["alpha", "beta"], "response": {"content": "x"}}
    )
    _open(page, base, app_with_agent.agent_name)
    provider = page.locator("#studio-provider")
    original = provider.input_value()
    provider.select_option(other)
    _expect_dirty(page)
    # The model list is refetched for the new provider; the old model is carried as custom.
    expect(page.locator("#studio-model option")).to_have_count(4, timeout=8000)
    page.locator("#studio-model").select_option("beta")
    _expect_dirty(page)

    page.locator(CANCEL).click()
    _expect_clean(page)
    expect(provider).to_have_value(original)
    expect(page.locator("#studio-model")).to_have_value("mock-default", timeout=8000)
    expect(page.locator("#studio-model option")).to_have_count(2)
    # The capability line was reset (no chips from the other provider).
    expect(page.locator(".model-capabilities")).to_have_text("")


def test_same_identity_save_keeps_the_general_nodes(app_with_agent: SeededApp, page: Page) -> None:
    _open(page, app_with_agent.base_url, app_with_agent.agent_name)
    page.evaluate("() => { document.getElementById('studio-description').dataset.mark = 'kept'; }")
    box = page.locator('[data-field="description"]')
    box.fill("saved description")
    _expect_dirty(page)
    page.locator(SAVE).click()
    _expect_clean(page)
    expect(box).to_have_value("saved description")
    assert (
        page.evaluate("() => document.getElementById('studio-description').dataset.mark") == "kept"
    )
    expect(page.locator("#studio-model")).to_have_value("mock-default", timeout=8000)


def test_test_button_is_a_status_line(app_with_agent: SeededApp, page: Page) -> None:
    _open(page, app_with_agent.base_url, app_with_agent.agent_name)
    btn = page.locator('[data-testid="test-provider-btn"]')
    result = page.locator('[data-testid="test-provider-result"]')
    expect(btn).to_have_text("Test")
    expect(btn).to_be_enabled()
    expect(result).to_be_hidden()
    btn.click()
    expect(result).to_have_attribute("data-state", "success", timeout=8000)
    expect(result).to_be_visible()


def test_danger_zone_holds_two_actions_with_library_labels(
    app_with_agent: SeededApp, page: Page
) -> None:
    _open(page, app_with_agent.base_url, app_with_agent.agent_name)
    zone = page.locator(".danger-zone")
    expect(zone.locator("button")).to_have_count(2)
    delete = page.locator('[data-testid="delete-agent-btn"]')
    purge = page.locator('[data-testid="purge-history-btn"]')
    expect(delete).to_have_text("Delete agent")
    expect(purge).to_have_text("Purge now")
    delete.click()
    expect(delete).to_have_text("Confirm delete?")
    purge.click()
    expect(purge).to_have_text("Confirm purge?")


def test_create_mode_has_no_danger_zone(app_clean: str, page: Page) -> None:
    seed_mock_provider(app_clean)
    _nav.goto(page, app_clean, "agents/~new")
    expect(page.locator('[data-field="name"]')).to_be_attached(timeout=8000)
    expect(page.locator(".danger-zone")).to_have_count(0)
    expect(page.locator('[data-testid="test-provider-btn"]')).to_be_visible()
