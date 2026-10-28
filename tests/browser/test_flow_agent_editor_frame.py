# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""The agent editor's frame on the control library (M31 F2 L06a; flight DD2, DD3, DD6).

The header is ``App.ui.editorShell`` and the tab strip ``App.ui.tabs``, mounted through a
mount slot. The identity is (the saved agent's name, create-or-edit): a rename remounts,
and a same-identity Save or Cancel calls ``patch``, which rebuilds the six panels in place.
Falls in the ``agents`` lane via the ``test_flow_agent_*`` glob.
"""

from __future__ import annotations

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_knowledge_base
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

SAVE = '[data-testid="save-agent-btn"]'
CANCEL = '[data-testid="cancel-agent-btn"]'


def _open(page: Page, base: str, agent: str, tab: str = "general") -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(agent)}/{tab}")
    expect(page.locator(f'[data-testid="tab-{tab}"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    expect(page.locator('[data-field="name"]')).to_be_attached(timeout=8000)


def _tab(page: Page, tab: str) -> None:
    page.locator(f'[data-testid="tab-{tab}"]').click()
    expect(page.locator(f'[data-testid="tab-{tab}"]')).to_have_attribute("aria-selected", "true")


def _selected_tab(page: Page) -> str:
    return page.evaluate(
        "() => document.querySelector('[role=tab][aria-selected=true]').dataset.tabId"
    )


def _mark_header(page: Page) -> None:
    page.evaluate("() => { document.querySelector('.editor-header').dataset.mark = 'kept'; }")


def test_frame_dom_shape_and_ids(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open(page, base, agent)
    out = page.evaluate(
        """() => {
          const ed = document.querySelector('.studio-editor');
          return {
            kids: Array.from(ed.children).map((k) => k.className.split(' ')[0]),
            tabs: Array.from(ed.querySelectorAll('[role=tab]')).map((t) => [t.id, t.getAttribute('aria-controls'), t.dataset.testid]),
            panels: Array.from(ed.querySelectorAll('[role=tabpanel]')).map((p) => p.id),
            loadError: !!ed.querySelector('[data-testid=agent-load-error]'),
          };
        }"""
    )
    assert out["kids"][:2] == ["editor-header", "tablist"]
    assert [t[0] for t in out["tabs"]] == [
        f"agent-tab-{t}"
        for t in ("general", "rules-and-notes", "knowledge", "mcps", "tools", "self-configuration")
    ]
    assert out["panels"][0] == "agent-tab-panel-general"
    assert out["tabs"][1][1] == "agent-tab-panel-rules-and-notes"
    assert out["loadError"] is False
    expect(page.locator('[data-testid="agent-chat-btn"]')).to_be_visible()
    expect(page.locator(CANCEL)).to_be_disabled()
    expect(page.locator(SAVE)).to_be_disabled()


def test_same_identity_save_patches_without_remount(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open(page, base, agent)
    _mark_header(page)
    page.locator('[data-field="description"]').fill("patched description")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    expect(page.locator(SAVE)).to_be_enabled()
    page.locator(SAVE).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=8000)
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("")
    expect(page.locator(".app-flash")).to_have_text("Agent saved")  # A14: was "Saved"
    expect(page.locator(".editor-subtitle")).to_have_text("patched description")
    # The frame (the shell header node) was patched, not remounted.
    assert page.evaluate("() => document.querySelector('.editor-header').dataset.mark") == "kept"
    expect(page.locator('[data-field="description"]')).to_have_value("patched description")


def test_save_keeps_active_tab_and_title_focus(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open(page, base, agent)
    page.locator('[data-field="description"]').fill("edited elsewhere")
    _tab(page, "rules-and-notes")
    page.locator(SAVE).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=8000)
    assert _selected_tab(page) == "rules-and-notes"
    _nav.expect_route(page, f"agents/{_nav.seg(agent)}/rules-and-notes")
    expect(page.locator(".editor-title")).to_be_focused(timeout=3000)


def test_rename_remounts_and_rules_are_stored_under_new_name(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    new = f"{agent}-renamed"
    _open(page, base, agent)
    _mark_header(page)
    page.locator('[data-field="name"]').fill(new)
    _tab(page, "rules-and-notes")
    page.locator(SAVE).click()
    expect(page.locator(".editor-title")).to_have_text(new, timeout=8000)
    # A rename is a new identity: the frame was remounted, the active tab restored.
    assert page.evaluate("() => document.querySelector('.editor-header').dataset.mark") is None
    assert _selected_tab(page) == "rules-and-notes"
    page.locator('[data-testid="rules-add-input"]').fill("a rule after the rename")
    page.locator('[data-testid="rules-add-btn"]').click()
    expect(page.locator('[data-testid="rules-row"]')).to_have_count(1, timeout=8000)
    r = httpx.get(f"{base}/api/agents/{new}/rules", headers=auth_headers_for(base), timeout=5)
    assert r.status_code == 200, r.text
    assert [x["text"] for x in r.json()["rules"]] == ["a rule after the rename"]


def test_save_then_knowledge_shows_current_kb_tool_names(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    kb_id = seed_knowledge_base(base, "Frame KB")
    _open(page, base, agent, "knowledge")
    toggle = page.locator(f'[data-testid="agent-knowledge-toggle-{kb_id}"]')
    expect(toggle).to_be_attached(timeout=8000)
    toggle.locator("xpath=ancestor::label").click()
    page.locator(SAVE).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=8000)
    _tab(page, "general")
    _tab(page, "knowledge")
    name_el = page.locator(f'[data-testid="agent-knowledge-tool-name-{kb_id}"]')
    expect(name_el).not_to_have_text("attach to see the tool name", timeout=5000)
    expect(name_el).to_contain_text("kb__")
    expect(toggle).to_be_checked()


def test_cancel_reverts_general_and_another_tab(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open(page, base, agent)
    original = page.locator('[data-field="description"]').input_value()
    _mark_header(page)
    page.locator('[data-field="description"]').fill("to be discarded")
    _tab(page, "tools")
    toggles = page.locator('input[type="checkbox"][data-tool]')
    before = toggles.first.is_checked()
    toggles.first.evaluate(
        "(el) => { el.checked = !el.checked; el.dispatchEvent(new Event('change', { bubbles: true })); }"
    )
    expect(page.locator(CANCEL)).to_be_enabled()
    page.locator(CANCEL).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=5000)
    expect(page.locator(CANCEL)).to_be_disabled()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("")
    assert toggles.first.is_checked() == before
    # Cancel rebuilds the panels; it does not remount the frame, and the tab stays.
    assert page.evaluate("() => document.querySelector('.editor-header').dataset.mark") == "kept"
    assert _selected_tab(page) == "tools"
    _tab(page, "general")
    expect(page.locator('[data-field="description"]')).to_have_value(original)


def test_save_block_survives_edits_and_cancel(app_with_agent: SeededApp, page: Page) -> None:
    """Squawk 0090 through the shell: a failed fresh-agent load keeps Save disabled
    after every dirty change and after Cancel's panel rebuild, with Cancel enabled."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    target = f"**/api/agents/{agent}"

    def handler(route):  # noqa: ANN001
        if route.request.method == "GET":
            route.abort()
        else:
            route.continue_()

    page.route(target, handler)
    _open(page, base, agent)
    expect(page.locator('[data-testid="agent-load-error"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="description"]').fill("blocked edit")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    expect(page.locator(SAVE)).to_be_disabled()
    expect(page.locator(CANCEL)).to_be_enabled()
    page.locator(CANCEL).click()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("")
    expect(page.locator('[data-testid="agent-load-error"]')).to_be_visible()
    page.locator('[data-field="description"]').fill("blocked again")
    expect(page.locator(SAVE)).to_be_disabled()
