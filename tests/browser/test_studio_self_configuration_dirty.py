"""A self-configuration change no longer discards unsaved agent-editor edits
(M31 F2 L10a, DD9-3).

Tests 1 and 3 fail on the pre-fix tree (the change re-selected the agent and
rebuilt every panel); 2, 4 and 5 and the patch test are regression guards. Falls
in the ``agents`` lane via the ``test_studio_*`` glob.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser._self_config import APPROVAL_SWITCH, ENABLE_SWITCH, click_switch
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def _api(base: str, method: str, path: str, **kw):  # noqa: ANN202
    r = httpx.request(method, f"{base}{path}", timeout=5.0, headers=auth_headers_for(base), **kw)
    assert r.status_code in (200, 201), f"{method} {path}: {r.status_code} {r.text}"
    return r.json()


def _seed_agent(base: str, name: str, **fields: object) -> dict:
    return _api(base, "POST", "/api/agents", json={"name": name, **fields})


def _get_agent(base: str, name: str) -> dict:
    return _api(base, "GET", f"/api/agents/{name}")


def _enable(base: str, name: str) -> None:
    _api(base, "POST", f"/api/agents/{name}/self-configuration")


def _seed_pending(data_dir: Path, agent: str, field: str, proposed: str, base: str) -> None:
    conn = sqlite3.connect(str(data_dir / "the-one.db"))
    try:
        conn.execute(
            "INSERT INTO agent_revisions ("
            " id, agent_name, field, proposed_value, base_value,"
            " status, source, restored_from, created_at, resolved_at"
            ") VALUES (?, ?, ?, ?, ?, 'pending', 'self', NULL, datetime('now'), NULL)",
            (uuid.uuid4().hex, agent, field, proposed, base),
        )
        conn.commit()
    finally:
        conn.close()


def _open(page: Page, base: str, agent: str, tab: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(agent)}/{tab}")
    expect(page.locator(f'[data-testid="tab-{tab}"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


def _tab(page: Page, tab: str) -> None:
    page.locator(f'[data-testid="tab-{tab}"]').click()
    expect(page.locator(f'[data-testid="tab-{tab}"]')).to_have_attribute("aria-selected", "true")


def _card(page: Page, field_label: str):  # noqa: ANN202
    return page.locator('[data-testid="revision-card"]').filter(
        has=page.locator('[data-testid="revision-field"]', has_text=field_label)
    )


NOTE = '[data-testid="agent-stored-value-changed"]'


def test_approval_toggle_keeps_typed_general_edits(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, _ = app_with_data_dir
    _seed_agent(base, "dirty-toggle", system_prompt="stored prompt")
    _enable(base, "dirty-toggle")
    _open(page, base, "dirty-toggle", "general")
    prompt = page.locator("#studio-system-prompt")
    prompt.fill("typed prompt")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_visible()
    _tab(page, "self-configuration")
    toggle = page.locator('[data-testid="approval-mode-toggle-btn"]')
    expect(toggle).to_be_enabled(timeout=8000)
    click_switch(page, APPROVAL_SWITCH)
    status = page.locator('[data-testid="approval-mode-status"]')
    expect(status).to_contain_text("Approval mode is on", timeout=8000)
    expect(toggle).to_be_checked()
    _tab(page, "general")
    expect(prompt).to_have_value("typed prompt")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_visible()
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_enabled()
    cfg = _api(base, "GET", "/api/agents/dirty-toggle/self-configuration")
    assert cfg["requires_approval"] is True


def test_enable_then_save_keeps_the_loopback_source(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, _ = app_with_data_dir
    _seed_agent(base, "dirty-enable", description="d0")
    _open(page, base, "dirty-enable", "self-configuration")
    toggle = page.locator('[data-testid="self-configuration-toggle-btn"]')
    expect(toggle).to_be_enabled(timeout=8000)
    click_switch(page, ENABLE_SWITCH)
    expect(page.locator('[data-testid="self-configuration-status"]')).to_contain_text(
        "enabled", timeout=8000
    )
    _tab(page, "general")
    page.locator("#studio-description").fill("d1")
    page.locator('[data-testid="save-agent-btn"]').click()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_hidden(timeout=8000)
    stored = _get_agent(base, "dirty-enable")
    assert stored["description"] == "d1"
    assert len(stored["mcp_source_ids"]) == 1, stored["mcp_source_ids"]


def test_conflicting_approval_keeps_typed_text_with_a_note(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, data_dir = app_with_data_dir
    _seed_agent(base, "dirty-conflict", description="stored desc", system_prompt="stored prompt")
    _api(
        base,
        "PUT",
        "/api/agents/dirty-conflict/self-configuration/approval-mode",
        json={"requires_approval": True},
    )
    _seed_pending(data_dir, "dirty-conflict", "description", "approved desc", "stored desc")
    _seed_pending(data_dir, "dirty-conflict", "system_prompt", "approved prompt", "stored prompt")
    _open(page, base, "dirty-conflict", "general")
    desc = page.locator("#studio-description")
    desc.fill("typed desc")
    _tab(page, "self-configuration")
    expect(page.locator('[data-testid="revision-card"]')).to_have_count(2, timeout=8000)
    _card(page, "Description").locator('[data-testid="revision-approve-btn"]').click()
    expect(page.locator('[data-testid="revision-card"]')).to_have_count(1, timeout=8000)
    # Focus went to the action status before the refetch removed the card.
    expect(page.locator('[data-testid="self-configuration-action-status"]')).to_be_focused()
    _tab(page, "general")
    expect(desc).to_have_value("typed desc")
    note = page.locator(NOTE)
    expect(note).to_contain_text(
        "The stored description changed. Save will replace it with your text."
    )
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_visible()
    # The untouched system prompt takes the stored value when it changes.
    _tab(page, "self-configuration")
    _card(page, "System prompt").locator('[data-testid="revision-approve-btn"]').click()
    expect(page.locator('[data-testid="revision-card"]')).to_have_count(0, timeout=8000)
    _tab(page, "general")
    expect(page.locator("#studio-system-prompt")).to_have_value("approved prompt")
    expect(desc).to_have_value("typed desc")
    expect(note).to_be_visible()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_visible()
    # Save stores the typed text and clears the note.
    page.locator('[data-testid="save-agent-btn"]').click()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_hidden(timeout=8000)
    expect(note).to_be_hidden()
    stored = _get_agent(base, "dirty-conflict")
    assert stored["description"] == "typed desc"
    assert stored["system_prompt"] == "approved prompt"


def _conflict(base: str, data_dir: Path, page: Page, name: str):  # noqa: ANN202
    _seed_agent(base, name, description="stored desc")
    _api(
        base,
        "PUT",
        f"/api/agents/{name}/self-configuration/approval-mode",
        json={"requires_approval": True},
    )
    _seed_pending(data_dir, name, "description", "approved desc", "stored desc")
    _open(page, base, name, "general")
    desc = page.locator("#studio-description")
    desc.fill("typed desc")
    _tab(page, "self-configuration")
    _card(page, "Description").locator('[data-testid="revision-approve-btn"]').click()
    expect(page.locator('[data-testid="revision-card"]')).to_have_count(0, timeout=8000)
    _tab(page, "general")
    expect(page.locator(NOTE)).to_be_visible()
    return desc


def test_conflict_note_clears_on_cancel(app_with_data_dir: tuple[str, Path], page: Page) -> None:
    base, data_dir = app_with_data_dir
    desc = _conflict(base, data_dir, page, "dirty-cancel")
    page.locator('[data-testid="cancel-agent-btn"]').click()
    expect(page.locator(NOTE)).to_be_hidden()
    expect(desc).to_have_value("approved desc")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_hidden()


def test_conflict_note_clears_when_the_field_is_clean_again(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, data_dir = app_with_data_dir
    desc = _conflict(base, data_dir, page, "dirty-reclean")
    desc.fill("approved desc")
    expect(page.locator(NOTE)).to_be_hidden()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_hidden()


def test_clean_field_takes_the_approved_value(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, data_dir = app_with_data_dir
    _seed_agent(base, "dirty-clean", description="stored desc")
    _api(
        base,
        "PUT",
        "/api/agents/dirty-clean/self-configuration/approval-mode",
        json={"requires_approval": True},
    )
    _seed_pending(data_dir, "dirty-clean", "description", "approved desc", "stored desc")
    _open(page, base, "dirty-clean", "self-configuration")
    _card(page, "Description").locator('[data-testid="revision-approve-btn"]').click()
    expect(page.locator('[data-testid="revision-card"]')).to_have_count(0, timeout=8000)
    expect(page.locator(".editor-subtitle")).to_have_text("approved desc")
    _tab(page, "general")
    expect(page.locator("#studio-description")).to_have_value("approved desc")
    expect(page.locator(NOTE)).to_be_hidden()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_hidden()


def test_disable_then_save_drops_the_loopback_source(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, _ = app_with_data_dir
    _seed_agent(base, "dirty-disable", description="d0")
    _enable(base, "dirty-disable")
    assert len(_get_agent(base, "dirty-disable")["mcp_source_ids"]) == 1
    _open(page, base, "dirty-disable", "self-configuration")
    toggle = page.locator('[data-testid="self-configuration-toggle-btn"]')
    expect(toggle).to_be_checked(timeout=8000)
    click_switch(page, ENABLE_SWITCH)
    expect(page.locator('[data-testid="self-configuration-status"]')).to_contain_text(
        "disabled", timeout=8000
    )
    _tab(page, "general")
    page.locator("#studio-description").fill("d1")
    page.locator('[data-testid="save-agent-btn"]').click()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_hidden(timeout=8000)
    stored = _get_agent(base, "dirty-disable")
    assert stored["description"] == "d1"
    assert stored["mcp_source_ids"] == [], stored["mcp_source_ids"]


def test_disable_while_dirty_stays_dirty_only_for_the_typed_edit(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """The snapshot rebase: enabling with a typed edit adds no spurious change."""
    base, _ = app_with_data_dir
    _seed_agent(base, "dirty-rebase", description="d0")
    _open(page, base, "dirty-rebase", "general")
    page.locator("#studio-description").fill("typed")
    _tab(page, "self-configuration")
    toggle = page.locator('[data-testid="self-configuration-toggle-btn"]')
    expect(toggle).to_be_enabled(timeout=8000)
    click_switch(page, ENABLE_SWITCH)
    expect(page.locator('[data-testid="self-configuration-status"]')).to_contain_text(
        "enabled", timeout=8000
    )
    _tab(page, "general")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_visible()
    # Reverting the one typed edit makes the form clean again.
    page.locator("#studio-description").fill("d0")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_hidden()
    expect(page.locator(NOTE)).to_be_hidden()


def test_general_save_patches_self_configuration_without_refetching(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, data_dir = app_with_data_dir
    _seed_agent(base, "dirty-patch", description="d0")
    _enable(base, "dirty-patch")
    _seed_pending(data_dir, "dirty-patch", "description", "p", "d0")
    _open(page, base, "dirty-patch", "self-configuration")
    expect(page.locator('[data-testid="revision-card"]')).to_have_count(1, timeout=8000)
    details = page.locator('[data-testid="revision-history-details"]')
    details.locator("summary").click()
    expect(details).to_have_attribute("open", "")
    page.evaluate(
        "() => { window.__scNode = "
        "document.querySelector('[data-testid=\"revision-history-details\"]'); }"
    )
    gets: list[str] = []

    def on_request(req) -> None:  # noqa: ANN001
        if req.method == "GET" and "/self-configuration" in req.url:
            gets.append(req.url)

    _tab(page, "general")
    page.locator("#studio-description").fill("d1")
    page.on("request", on_request)
    page.locator('[data-testid="save-agent-btn"]').click()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_hidden(timeout=8000)
    page.wait_for_timeout(500)
    page.remove_listener("request", on_request)
    _tab(page, "self-configuration")
    assert page.evaluate(
        "() => window.__scNode === document.querySelector("
        "'[data-testid=\"revision-history-details\"]')"
    )
    expect(details).to_have_attribute("open", "")
    assert gets == [], gets


# ── onSelfConfigChanged guards (flight review) ──────────────────────────────


def _hold(page: Page, pattern: str, method: str) -> list:
    """Hold matching requests: the route is parked in the returned list, not continued."""
    held: list = []

    def handler(route) -> None:  # noqa: ANN001
        if route.request.method == method:
            held.append(route)
        else:
            route.continue_()

    page.route(pattern, handler)
    return held


def _release(page: Page, held: list) -> None:
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(50)
    assert held, "the held request never arrived"
    held.pop(0).continue_()


def _approvable(base: str, data_dir: Path, name: str, desc: str = "stored desc") -> None:
    _seed_agent(base, name, description=desc)
    _api(
        base,
        "PUT",
        f"/api/agents/{name}/self-configuration/approval-mode",
        json={"requires_approval": True},
    )
    _seed_pending(data_dir, name, "description", f"approved {name}", desc)


def _click_approve(page: Page) -> None:
    _card(page, "Description").locator('[data-testid="revision-approve-btn"]').click()


def test_write_resolving_after_leaving_agents_does_not_throw_and_stored_value_shows_on_return(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """Behaviour pin: a write resolving after leaving Agents neither throws nor patches.

    Leaving Agents for Library destroys the editor first, so the identity guard and
    the `!!d.handle` check already stop the patch; the controller's
    `_activeSection === 'agents'` line is therefore not independently falsifiable by
    this test.
    """
    base, data_dir = app_with_data_dir
    _approvable(base, data_dir, "guard-area")
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open(page, base, "guard-area", "self-configuration")
    expect(page.locator('[data-testid="revision-card"]')).to_have_count(1, timeout=8000)
    held = _hold(page, "**/api/agents/guard-area/self-configuration/revisions/*/approve*", "POST")
    _click_approve(page)
    # Library closes the open editor, so the write resolves with no editor to patch.
    page.locator('[data-testid="rail-library"]').click()
    expect(page.locator('[data-testid="library-list"]')).to_be_visible()
    _release(page, held)
    page.wait_for_timeout(600)
    assert errors == [], errors
    page.locator('[data-testid="rail-agents"]').click()
    if page.locator('[data-testid="agent-item"]', has_text="guard-area").count():
        page.locator('[data-testid="agent-item"]', has_text="guard-area").click()
    expect(page.locator("#studio-description")).to_have_value("approved guard-area", timeout=8000)
    expect(page.locator(NOTE)).to_be_hidden()
    assert _get_agent(base, "guard-area")["description"] == "approved guard-area"


def test_write_resolving_after_selecting_another_agent_patches_nothing_there(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """Identity guard: another agent's editor is not patched by this agent's write."""
    base, data_dir = app_with_data_dir
    _approvable(base, data_dir, "guard-a")
    _seed_agent(base, "guard-b", description="b desc")
    _open(page, base, "guard-a", "self-configuration")
    expect(page.locator('[data-testid="revision-card"]')).to_have_count(1, timeout=8000)
    held = _hold(page, "**/api/agents/guard-a/self-configuration/revisions/*/approve*", "POST")
    _click_approve(page)
    page.locator('[data-testid="agent-item"]', has_text="guard-b").click()
    expect(page.locator("#studio-description")).to_have_value("b desc", timeout=8000)
    _release(page, held)
    page.wait_for_timeout(600)
    expect(page.locator("#studio-description")).to_have_value("b desc")
    expect(page.locator(".editor-subtitle")).not_to_have_text("approved guard-a")
    expect(page.locator(NOTE)).to_be_hidden()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_hidden()
    # The original agent's row / reselected editor carries the new value.
    page.locator('[data-testid="agent-item"]', has_text="guard-a").click()
    expect(page.locator("#studio-description")).to_have_value("approved guard-a", timeout=8000)
    expect(page.locator(NOTE)).to_be_hidden()


def test_write_landing_during_a_general_save_leaves_no_stale_note(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    """Save-in-flight guard: the write is not patched in while a Save is outstanding."""
    base, data_dir = app_with_data_dir
    _approvable(base, data_dir, "guard-save")
    _open(page, base, "guard-save", "general")
    page.locator("#studio-description").fill("typed desc")
    held_put = _hold(page, "**/api/agents/guard-save", "PUT")
    page.locator('[data-testid="save-agent-btn"]').click()
    for _ in range(100):
        if held_put:
            break
        page.wait_for_timeout(50)
    assert held_put, "the Save PUT never left the page"
    _tab(page, "self-configuration")
    expect(page.locator('[data-testid="revision-card"]')).to_have_count(1, timeout=8000)
    _click_approve(page)
    expect(page.locator('[data-testid="revision-card"]')).to_have_count(0, timeout=8000)
    assert _get_agent(base, "guard-save")["description"] == "approved guard-save"
    # While the Save is outstanding the write is not patched into the form: the typed
    # text stays, with no stored-value note.
    _tab(page, "general")
    expect(page.locator("#studio-description")).to_have_value("typed desc")
    page.wait_for_timeout(300)
    expect(page.locator(NOTE)).to_be_hidden()
    held_put.pop(0).continue_()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_be_hidden(timeout=8000)
    expect(page.locator(NOTE)).to_be_hidden()
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_disabled()
    expect(page.locator("#studio-description")).to_have_value("typed desc")
    assert _get_agent(base, "guard-save")["description"] == "typed desc"
