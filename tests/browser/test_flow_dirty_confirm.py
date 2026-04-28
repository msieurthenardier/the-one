"""End-to-end flow tests: dirty-state + App.confirmDialog modal (F5 leg 04).

Covers the dirty-state UX introduced in F5 leg 04:

- Save button is `disabled` when clean (single source of truth — leg 04
  removed the `.clean` / `.dirty` class machinery in favor of the
  [disabled] attribute)
- Save becomes enabled after a field changes
- Back-when-dirty triggers App.confirmDialog (cancel keeps state, confirm
  navigates to #studio/agents)
- Section-nav-when-dirty triggers the dialog (only in agents+selected
  context — Knowledge → Tools navigations don't prompt)
- Tile-click-when-dirty triggers the dialog (routes through selectAgent —
  inherits the dirty gate for free)
- Tab-click-when-dirty triggers the dialog
- Arrow-key tab navigation does NOT trigger the dialog (focus only)
- Modal full Tab/Shift-Tab focus-trap cycles forward + backward
- Modal Escape cancels and restores focus to the trigger
- Modal Enter confirms (when focus is not in a textarea)
- Modal ARIA contract: role=dialog, aria-modal=true, aria-labelledby,
  aria-describedby
- Clean-state navigation does NOT open any dialogs (all four paths)
- beforeunload listener: synthetic event with dirty=true → defaultPrevented
  is True; with dirty=false → defaultPrevented is False
- Singleton modal: second call while one is open is a no-op + console.warn
"""

from __future__ import annotations

import urllib.parse

import pytest
from browser.seeders import SeededApp, seed_mock_agent
from playwright.sync_api import Page, expect


def _wait_editor_ready(page: Page) -> None:
    """Wait for the agent editor to be the visible child in the main panel.

    Bare `#studio/agents` lands on the tile grid with no agent auto-selected
    (F5 leg 05 design): the section-content (tile grid) is visible and the
    editor is hidden. Click the first tile to swap them. Deep-link
    navigations (`#studio/agents/<name>/...`) hydrate the selection and the
    editor is already visible — skip the click.
    """
    expect(page.locator(".section-nav-header")).to_have_text("Studio", timeout=8000)
    editor_hidden = page.evaluate(
        "() => document.querySelector('.studio-editor')?.classList.contains('is-hidden')"
    )
    if editor_hidden:
        page.locator("button.entity-tile").first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)


def _make_dirty(page: Page) -> None:
    """Type into the description field to mark the form dirty."""
    desc = page.locator('[data-field="description"]')
    desc.click()
    desc.fill("dirty edit " + str(id(page))[:6])


@pytest.mark.browser
def test_save_button_disabled_when_clean(app_with_agent: SeededApp, page: Page) -> None:
    """On agent select, the Save button is initially disabled (clean)."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    save_btn = page.locator('[data-testid="save-agent-btn"]')
    expect(save_btn).to_be_disabled()


@pytest.mark.browser
def test_save_button_enabled_after_field_change(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Editing a field flips the Save button to enabled."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    save_btn = page.locator('[data-testid="save-agent-btn"]')
    expect(save_btn).to_be_disabled()

    _make_dirty(page)
    expect(save_btn).to_be_enabled()


@pytest.mark.browser
def test_back_when_dirty_cancel_keeps_state(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Back when dirty opens dialog; clicking Cancel keeps state + URL."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    initial_hash = page.evaluate("location.hash")
    _make_dirty(page)

    page.locator('[data-testid="back-agent-btn"]').click()

    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()

    page.locator('[data-testid="modal-cancel-btn"]').click()

    expect(overlay).to_have_count(0)
    # URL unchanged.
    assert page.evaluate("location.hash") == initial_hash
    # Editor still mounted.
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible()


@pytest.mark.browser
def test_back_when_dirty_confirm_navigates(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Back when dirty + Confirm navigates to #studio/agents."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    _make_dirty(page)
    page.locator('[data-testid="back-agent-btn"]').click()

    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()

    page.locator('[data-testid="modal-confirm-btn"]').click()

    expect(overlay).to_have_count(0)
    # URL is now #studio/agents (no agent selected).
    assert page.evaluate("location.hash") == "#studio/agents"
    # Main panel returned to the tile grid; editor is hidden.
    expect(page.locator(".entity-tile-grid")).to_be_visible()
    expect(page.locator(".studio-editor")).to_have_class("studio-editor is-hidden")


@pytest.mark.browser
def test_section_nav_when_dirty_opens_dialog(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Clicking a section button when dirty + selected-agent opens dialog."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    _make_dirty(page)

    # Click the Knowledge section button in the sidebar.
    knowledge_btn = page.locator(
        '.section-nav-item[data-section="knowledge"]'
    )
    expect(knowledge_btn).to_be_visible()
    knowledge_btn.click()

    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()

    # Cancel keeps us on agents.
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(overlay).to_have_count(0)
    # Agents tab still active.
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible()


@pytest.mark.browser
def test_section_nav_clean_does_not_open_dialog(
    app_with_provider: SeededApp, page: Page
) -> None:
    """Clean state: section nav clicks navigate immediately, no dialog."""
    base_url = app_with_provider.base_url
    page.goto(f"{base_url}#studio")
    expect(page.locator('[data-testid="agent-empty"]')).to_be_visible(timeout=8000)

    # No agent selected — knowledge nav should NOT prompt even if
    # somehow dirty (and it's clean here).
    knowledge_btn = page.locator(
        '.section-nav-item[data-section="knowledge"]'
    )
    knowledge_btn.click()

    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    expect(page.locator('[data-testid="studio-knowledge-stub"]')).to_be_visible()


@pytest.mark.browser
def test_hash_change_to_other_agent_when_dirty_opens_dialog(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Hash-route navigation to a different agent while dirty opens the dialog.

    With F5 leg 05's main-panel layout, the tile grid is hidden while an
    agent is being edited, so a direct tile click cannot reach a sibling
    agent. The equivalent path is a hash-route navigation (deep link or
    history navigation) which routes through `selectAgent` via
    `tryConsumePendingSelect`, inheriting the dirty gate.
    """
    base_url = app_with_agent.base_url
    provider_id = app_with_agent.provider_id

    seed_mock_agent(base_url, provider_id, name="second-agent")

    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    # Pick the agent that ISN'T the one currently in the editor — the
    # tile-grid sort order is not guaranteed, so deriving from the editor
    # title makes the test deterministic.
    current = page.locator(".editor-title").inner_text()
    other_name = "test-agent" if current == "second-agent" else "second-agent"

    _make_dirty(page)
    page.evaluate(f"location.hash = '#studio/agents/{other_name}/general'")

    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()


@pytest.mark.browser
def test_tab_click_when_dirty_switches_without_dialog(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Clicking a tab when dirty switches immediately — no dialog (F5 leg 05).

    Tabs in the same agent share one form; switching tabs does not lose
    unsaved data (panels are hidden, not unmounted), so the dirty gate
    does NOT fire on tab change. Dirty state and Save-enabled persist
    across the switch.
    """
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    _make_dirty(page)
    page.locator('[data-testid="tab-knowledge"]').click()

    # No dialog appears; tab switches directly.
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    expected = f"#studio/agents/{urllib.parse.quote(agent_name)}/knowledge"
    assert page.evaluate("location.hash") == expected
    expect(page.locator('[data-testid="tab-knowledge"]')).to_have_attribute(
        "aria-selected", "true"
    )
    # Dirty state survives the tab switch (Save remains enabled).
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_enabled()


@pytest.mark.browser
def test_arrow_keys_in_tablist_do_not_open_dialog(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Arrow-key tab navigation moves focus only, never opens dialog."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    _make_dirty(page)

    page.locator('[data-testid="tab-general"]').focus()
    page.keyboard.press("ArrowRight")

    # No dialog opened.
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    # Focus moved to Knowledge.
    focused_id = page.evaluate("document.activeElement?.id")
    assert focused_id == "agent-tab-knowledge"


@pytest.mark.browser
def test_modal_focus_trap_tab_cycles_forward(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Tab from the last focusable wraps to the first."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    _make_dirty(page)
    page.locator('[data-testid="back-agent-btn"]').click()

    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()

    # Cancel is focused first by default. Press Tab → Confirm.
    cancel = page.locator('[data-testid="modal-cancel-btn"]')
    confirm = page.locator('[data-testid="modal-confirm-btn"]')

    # Focus should be on Cancel (helper focuses Cancel by default).
    expect(cancel).to_be_focused()

    page.keyboard.press("Tab")
    expect(confirm).to_be_focused()

    # Tab from Confirm (last) should wrap back to Cancel (first).
    page.keyboard.press("Tab")
    expect(cancel).to_be_focused()


@pytest.mark.browser
def test_modal_focus_trap_shift_tab_cycles_backward(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Shift+Tab from the first focusable wraps to the last."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    _make_dirty(page)
    page.locator('[data-testid="back-agent-btn"]').click()

    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible()

    cancel = page.locator('[data-testid="modal-cancel-btn"]')
    confirm = page.locator('[data-testid="modal-confirm-btn"]')

    # Cancel is focused; Shift+Tab from it should wrap to Confirm (last).
    expect(cancel).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(confirm).to_be_focused()


@pytest.mark.browser
def test_modal_escape_cancels(app_with_agent: SeededApp, page: Page) -> None:
    """Escape closes the dialog without confirming."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    initial_hash = page.evaluate("location.hash")
    _make_dirty(page)
    page.locator('[data-testid="back-agent-btn"]').click()

    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()

    page.keyboard.press("Escape")

    expect(overlay).to_have_count(0)
    # URL unchanged — the cancel path doesn't navigate.
    assert page.evaluate("location.hash") == initial_hash


@pytest.mark.browser
def test_modal_enter_confirms(app_with_agent: SeededApp, page: Page) -> None:
    """Enter (when focus is on a button) confirms via onConfirm."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    _make_dirty(page)
    page.locator('[data-testid="back-agent-btn"]').click()

    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()

    # Cancel is focused; press Enter — should fire onConfirm and close.
    page.keyboard.press("Enter")

    expect(overlay).to_have_count(0)
    # URL navigated to #studio/agents.
    assert page.evaluate("location.hash") == "#studio/agents"


@pytest.mark.browser
def test_modal_aria_contract(app_with_agent: SeededApp, page: Page) -> None:
    """Modal has role=dialog, aria-modal=true, aria-labelledby, aria-describedby."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    _make_dirty(page)
    page.locator('[data-testid="back-agent-btn"]').click()

    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()

    expect(overlay).to_have_attribute("role", "dialog")
    expect(overlay).to_have_attribute("aria-modal", "true")

    labelled_by = overlay.get_attribute("aria-labelledby")
    described_by = overlay.get_attribute("aria-describedby")
    assert labelled_by, "aria-labelledby must be present"
    assert described_by, "aria-describedby must be present"

    # The referenced elements must exist within the dialog.
    assert page.locator(f"#{labelled_by}").count() == 1
    assert page.locator(f"#{described_by}").count() == 1


@pytest.mark.browser
def test_modal_restore_focus_on_close(
    app_with_agent: SeededApp, page: Page
) -> None:
    """After close, focus returns to the trigger element."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    _make_dirty(page)

    back_btn = page.locator('[data-testid="back-agent-btn"]')
    back_btn.focus()
    expect(back_btn).to_be_focused()
    back_btn.click()

    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()

    page.keyboard.press("Escape")
    expect(overlay).to_have_count(0)

    # Focus should be restored to the Back button.
    expect(back_btn).to_be_focused()


@pytest.mark.browser
def test_clean_state_does_not_open_dialog_on_back(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Back when clean navigates immediately — no dialog."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    page.locator('[data-testid="back-agent-btn"]').click()

    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    assert page.evaluate("location.hash") == "#studio/agents"


@pytest.mark.browser
def test_clean_state_does_not_open_dialog_on_tab_click(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Tab click when clean commits immediately — no dialog."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    page.locator('[data-testid="tab-knowledge"]').click()

    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)
    expected = f"#studio/agents/{urllib.parse.quote(agent_name)}/knowledge"
    assert page.evaluate("location.hash") == expected


@pytest.mark.browser
def test_beforeunload_listener_prevents_when_dirty(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Synthetic beforeunload when dirty has defaultPrevented = True."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    _make_dirty(page)

    # Use page.evaluate to dispatch a synthetic beforeunload event and
    # inspect event.defaultPrevented. Headless Chromium suppresses the
    # native dialog event in page.on('dialog', ...), so this synthetic-
    # event pattern is the reliable signal (per leg artifact step 7).
    prevented = page.evaluate(
        """() => {
            const e = new Event('beforeunload', { cancelable: true });
            window.dispatchEvent(e);
            return e.defaultPrevented;
        }"""
    )
    assert prevented is True


@pytest.mark.browser
def test_beforeunload_listener_does_not_prevent_when_clean(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Synthetic beforeunload when clean has defaultPrevented = False."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    # Form is clean — no edits made.
    prevented = page.evaluate(
        """() => {
            const e = new Event('beforeunload', { cancelable: true });
            window.dispatchEvent(e);
            return e.defaultPrevented;
        }"""
    )
    assert prevented is False


@pytest.mark.browser
def test_singleton_modal_second_call_warns(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Calling App.confirmDialog while one is open is a no-op + console.warn."""
    base_url = app_with_agent.base_url
    page.goto(f"{base_url}#studio")
    _wait_editor_ready(page)

    # Capture console warnings.
    warnings: list[str] = []
    page.on("console", lambda msg: warnings.append(msg.text) if msg.type == "warning" else None)

    _make_dirty(page)
    page.locator('[data-testid="back-agent-btn"]').click()

    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()

    # Try to open a second dialog while one is already open.
    page.evaluate("window.App.confirmDialog({})")

    # Still exactly ONE overlay (singleton).
    expect(overlay).to_have_count(1)

    # The warning should have been logged.
    assert any("already open" in w for w in warnings), (
        f"Expected 'already open' console.warn, got: {warnings}"
    )
