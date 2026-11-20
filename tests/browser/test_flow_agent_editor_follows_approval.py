"""The agent editor follows a change the operator approved (M36 F2 L7, flight DD10).

The General tab takes the new value into every control the operator has not edited, keeps an
unsaved edit (with today's panel note) and marks each changed control with the quiet note
(``agent-approved-change-note``, board option A). The signal is ``config_changed`` (the server's
frame to every socket) or the applied proposal in the approve response, both through
``App.approvals.record``; a repeated proposal id acts once. Each test visits Chats first so the
socket is alive. The stored values are changed through the agent PUT, then the frame is pushed
through the real socket handler (the second-window shape), except the one test that approves a
seeded proposal through the real route.

Falls in the ``agent-tabs`` browser lane (an explicit entry in ``scripts/run-tests.sh``).
"""

from __future__ import annotations

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_gleepglorp_proposal
from browser.test_flow_chat_proposals import _world
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

NOTE = '[data-testid="agent-approved-change-note"]'
PANEL_NOTE = '[data-testid="agent-stored-value-changed"]'
UNSAVED = '[data-testid="editor-unsaved"]'
SAVE = '[data-testid="save-agent-btn"]'
CANCEL = '[data-testid="cancel-agent-btn"]'
DESC = "#studio-description"
PROMPT = "#studio-system-prompt"
MODEL = "#studio-model"
ITER = "#studio-max-iterations"
SWITCH = '[data-testid="agent-rich-visuals-toggle"]'
SOCKET_OPEN = """() => {
  const a = window.App.areas.find(x => x.id === 'chat');
  return !!(a && a._ws && a._ws() && a._ws().readyState === 1);
}"""


def _put(base: str, name: str, **changes: object) -> dict:
    """Change the stored agent behind the editor's back (what an approval does)."""
    h = auth_headers_for(base)
    got = httpx.get(f"{base}/api/agents/{_nav.seg(name)}", headers=h, timeout=5).json()
    got.update(changes)
    r = httpx.put(f"{base}/api/agents/{_nav.seg(name)}", json=got, headers=h, timeout=5)
    assert r.status_code == 200, r.text
    return r.json()


def _frame(agent: str, fields: list[str], pid: int, kind: str = "agent") -> dict:
    return {
        "type": "config_changed",
        "kind": kind,
        "agent": agent,
        "fields": fields,
        "session_id": "sess-approved",
        "proposal_id": pid,
        "at": "2026-01-02T15:05:00+00:00",
    }


def _visit_chats(page: Page, base: str) -> None:
    _nav.goto(page, base, "chats")
    page.wait_for_function(SOCKET_OPEN, timeout=8000)


def _open_agent(page: Page, agent: str) -> None:
    _nav.set_route(page, f"agents/{_nav.seg(agent)}/general")
    expect(page.locator(DESC)).to_be_attached(timeout=8000)
    expect(page.locator(MODEL)).to_have_value("mock-default", timeout=8000)


def _ready(app: SeededApp, page: Page) -> tuple[str, str]:
    base, agent = app.base_url, app.agent_name
    _visit_chats(page, base)
    _open_agent(page, agent)
    return base, agent


def test_clean_fields_take_new_values_with_notes(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = _ready(app_with_agent, page)
    expect(page.locator(NOTE)).to_have_count(0)
    _put(
        base,
        agent,
        description="Approved description",
        llm_model="mock-approved",
        max_iterations=7,
        rich_visuals=False,
    )
    _chats.emit_frame(
        page, _frame(agent, ["description", "llm_model", "max_iterations", "rich_visuals"], 1)
    )
    expect(page.locator(DESC)).to_have_value("Approved description", timeout=8000)
    expect(page.locator(MODEL)).to_have_value("mock-approved", timeout=8000)
    expect(page.locator(ITER)).to_have_value("7")
    expect(page.locator(SWITCH)).not_to_be_checked()
    for field in ("description", "llm_model", "max_iterations", "rich_visuals"):
        expect(page.locator(f'{NOTE}[data-field="{field}"]')).to_have_count(1)
    expect(page.locator(f'{NOTE}[data-field="description"]')).to_contain_text(
        "Changed by a change you approved in a GleepGlorp chat"
    )
    link = page.locator(f'{NOTE}[data-field="description"] a')
    expect(link).to_have_text("Open chat")
    expect(link).to_have_attribute("href", _nav.href("chats/sess-approved"))
    # The values are the new baseline: no unsaved caption, no panel note.
    expect(page.locator(UNSAVED)).to_have_text("")
    expect(page.locator(SAVE)).to_be_disabled()
    expect(page.locator(PANEL_NOTE)).to_be_hidden()


def test_a_dirty_prompt_is_kept_beside_a_clean_description(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = _ready(app_with_agent, page)
    page.locator(PROMPT).fill("My unsaved prompt")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    _put(base, agent, description="Fresh description", system_prompt="Stored by approval")
    _chats.emit_frame(page, _frame(agent, ["description", "system_prompt"], 2))
    expect(page.locator(DESC)).to_have_value("Fresh description", timeout=8000)
    expect(page.locator(PROMPT)).to_have_value("My unsaved prompt")
    expect(page.locator(PANEL_NOTE)).to_contain_text(
        "The stored system prompt changed. Save will replace it with your text."
    )
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    # Only the prompt is still an unsaved edit: the description went to the baseline.
    expect(page.locator(SAVE)).to_be_enabled()
    expect(page.locator(f'{NOTE}[data-field="description"]')).to_have_count(1)
    # Making the prompt equal to the new stored value makes the editor clean again.
    page.locator(PROMPT).fill("Stored by approval")
    expect(page.locator(UNSAVED)).to_have_text("")
    expect(page.locator(PANEL_NOTE)).to_be_hidden()


def test_an_event_for_another_agent_changes_nothing(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = _ready(app_with_agent, page)
    _chats.emit_frame(page, _frame("someone-else", ["description"], 3))
    page.wait_for_timeout(400)
    expect(page.locator(NOTE)).to_have_count(0)
    expect(page.locator(UNSAVED)).to_have_text("")
    assert page.evaluate("App.approvals.forAgent(%r)" % agent) == {}


def test_a_duplicate_event_acts_once(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = _ready(app_with_agent, page)
    _put(base, agent, description="First")
    _chats.emit_frame(page, _frame(agent, ["description"], 4))
    expect(page.locator(DESC)).to_have_value("First", timeout=8000)
    _put(base, agent, description="Second")
    # The same proposal id again (the response and the frame both carry it): ignored.
    _chats.emit_frame(page, _frame(agent, ["description"], 4))
    page.wait_for_timeout(500)
    expect(page.locator(DESC)).to_have_value("First")
    assert page.evaluate("d => App.approvals.record(d)", _frame(agent, ["description"], 4)) is False
    assert page.evaluate("d => App.approvals.record(d)", _frame(agent, ["description"], 5)) is True


def test_the_notes_clear_on_cancel_and_on_save(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = _ready(app_with_agent, page)
    _put(base, agent, description="Approved A")
    _chats.emit_frame(page, _frame(agent, ["description"], 6))
    expect(page.locator(NOTE)).to_have_count(1, timeout=8000)

    page.locator(DESC).fill("Edited")
    expect(page.locator(CANCEL)).to_be_enabled()
    page.locator(CANCEL).click()
    expect(page.locator(DESC)).to_have_value("Approved A", timeout=8000)
    expect(page.locator(NOTE)).to_have_count(0)

    _put(base, agent, description="Approved B")
    _chats.emit_frame(page, _frame(agent, ["description"], 7))
    expect(page.locator(NOTE)).to_have_count(1, timeout=8000)
    page.locator(DESC).fill("Saved by the operator")
    page.locator(SAVE).click()
    expect(page.locator(SAVE)).to_be_disabled(timeout=8000)
    expect(page.locator(NOTE)).to_have_count(0)


def test_the_return_path_shows_the_notes_on_first_open(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Approve in Chats, then open Agents for the first time in this window."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _visit_chats(page, base)
    _put(base, agent, description="Approved while in Chats", max_iterations=9)
    _chats.emit_frame(page, _frame(agent, ["description", "max_iterations"], 8))
    _open_agent(page, agent)
    expect(page.locator(DESC)).to_have_value("Approved while in Chats", timeout=8000)
    expect(page.locator(ITER)).to_have_value("9")
    expect(page.locator(f'{NOTE}[data-field="description"]')).to_have_count(1, timeout=8000)
    expect(page.locator(f'{NOTE}[data-field="max_iterations"]')).to_have_count(1)
    expect(page.locator(UNSAVED)).to_have_text("")
    # Leaving and coming back re-patches the editor in full: the notes are drawn again.
    _nav.set_route(page, "agents")
    _open_agent(page, agent)
    expect(page.locator(f'{NOTE}[data-field="description"]')).to_have_count(1, timeout=8000)


def test_a_real_approval_reaches_an_open_editor(app_with_data_dir: tuple, page: Page) -> None:
    """The Leg 4 route's own ``config_changed`` broadcast, with the editor open and clean."""
    w = _world(app_with_data_dir)
    base = w.base
    agent = "plain"
    pid = seed_gleepglorp_proposal(
        w.data,
        w.sid,
        agent_name=agent,
        changes={"description": "Approved for real"},
        base={"description": ""},
    )
    _visit_chats(page, base)
    _nav.set_route(page, f"agents/{_nav.seg(agent)}/general")
    expect(page.locator(DESC)).to_be_attached(timeout=8000)
    expect(page.locator(MODEL)).to_have_value("mock-default", timeout=8000)
    r = httpx.post(
        f"{base}/api/gleepglorp/proposals/{pid}/approve",
        headers=auth_headers_for(base),
        timeout=10,
    )
    assert r.status_code == 200, r.text
    expect(page.locator(DESC)).to_have_value("Approved for real", timeout=8000)
    expect(page.locator(f'{NOTE}[data-field="description"]')).to_have_count(1, timeout=8000)
    expect(page.locator(UNSAVED)).to_have_text("")


# ── The other tabs (M36 F2 L8) ───────────────────────────────────────────────

TOOL_NOTE = f'{NOTE}[data-field="tools"]'


def _tool(page: Page, name: str):
    return page.locator(f'input[type="checkbox"][data-tool="{name}"]')


def _expand_filesystem(page: Page) -> None:
    page.locator('[data-category="Filesystem"] .ui-group-tile-expand').click()
    expect(_tool(page, "read_file")).to_be_visible()


def _open_tab(page: Page, agent: str, tab: str) -> None:
    _nav.set_route(page, f"agents/{_nav.seg(agent)}/{tab}")
    expect(page.locator(f'[data-testid="tab-{tab}"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


def _seed_attachables(base: str) -> tuple[str, str]:
    from browser.seeders import seed_knowledge_base, seed_mcp_source

    return seed_knowledge_base(base, "Docs"), seed_mcp_source(base, "Search", ["lookup"])


def test_clean_tool_mcp_and_kb_toggles_follow_with_notes(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    kb, sid = _seed_attachables(base)
    _visit_chats(page, base)
    _open_agent(page, agent)
    _put(base, agent, disabled_tools=["grep"], mcp_source_ids=[sid], kb_ids=[kb])
    _chats.emit_frame(page, _frame(agent, ["disabled_tools", "mcp_source_ids", "kb_ids"], 20))
    expect(_tool(page, "grep")).not_to_be_checked(timeout=8000)
    expect(_tool(page, "read_file")).to_be_checked()
    expect(page.locator(f'[data-testid="mcp-source-toggle-{sid}"]')).to_be_checked()
    expect(page.locator(f'[data-testid="agent-knowledge-toggle-{kb}"]')).to_be_checked()
    expect(page.locator(f'{TOOL_NOTE}[data-item="grep"]')).to_have_count(1)
    expect(page.locator(f'{NOTE}[data-field="mcp_source_ids"][data-item="{sid}"]')).to_have_count(1)
    expect(page.locator(f'{NOTE}[data-field="kb_ids"][data-item="{kb}"]')).to_have_count(1)
    # No other row got a note, and the form is clean (the values are the baseline).
    expect(page.locator(TOOL_NOTE)).to_have_count(1)
    expect(page.locator(UNSAVED)).to_have_text("")
    expect(page.locator(SAVE)).to_be_disabled()
    # The notes survive a tab switch and show where the item is.
    _open_tab(page, agent, "tools")
    expect(page.locator(f'{NOTE}[data-field="mcp_source_ids"][data-item="{sid}"]')).to_be_visible()
    _open_tab(page, agent, "knowledge")
    expect(page.locator(f'{NOTE}[data-field="kb_ids"][data-item="{kb}"]')).to_be_visible()
    # A remount (leave and return) draws them again from the record.
    _nav.set_route(page, "agents")
    _open_agent(page, agent)
    expect(page.locator(f'{NOTE}[data-field="kb_ids"][data-item="{kb}"]')).to_have_count(
        1, timeout=8000
    )
    expect(page.locator(f'{TOOL_NOTE}[data-item="grep"]')).to_have_count(1)


def test_approving_in_chats_then_opening_agents_notes_the_changed_tiles(
    app_with_data_dir: tuple, page: Page
) -> None:
    """Return path: the approval record carries the changed items, so a first open of the tabs
    (no live editor to diff) still draws a note on each changed tile."""
    from browser.seeders import seed_knowledge_base

    w = _world(app_with_data_dir)
    base, agent = w.base, "plain"
    kb = seed_knowledge_base(base, "Docs")
    pid = seed_gleepglorp_proposal(
        w.data,
        w.sid,
        agent_name=agent,
        changes={"disabled_tools": ["grep"], "kb_ids": [kb]},
        base={"disabled_tools": [], "kb_ids": []},
    )
    page.goto(base)
    _chats.open_chat(page, w.sid)
    card = page.locator(f'[data-testid="proposal-card"][data-proposal-id="{pid}"]')
    card.locator('[data-testid="proposal-approve"]').click()
    expect(card).to_have_attribute("data-state", "applied", timeout=8000)
    # First visit to Agents in this window.
    _open_tab(page, agent, "tools")
    expect(page.locator(f'{TOOL_NOTE}[data-item="grep"]')).to_have_count(1, timeout=8000)
    expect(page.locator(TOOL_NOTE)).to_have_count(1)
    _open_tab(page, agent, "knowledge")
    expect(page.locator(f'{NOTE}[data-field="kb_ids"][data-item="{kb}"]')).to_have_count(
        1, timeout=8000
    )


def test_a_dirty_tool_row_is_kept_beside_a_clean_one(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _visit_chats(page, base)
    _open_agent(page, agent)
    _open_tab(page, agent, "tools")
    _expand_filesystem(page)
    _tool(page, "read_file").uncheck()
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    _put(base, agent, disabled_tools=["grep"])
    _chats.emit_frame(page, _frame(agent, ["disabled_tools"], 21))
    expect(_tool(page, "grep")).not_to_be_checked(timeout=8000)
    expect(_tool(page, "read_file")).not_to_be_checked()
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    expect(page.locator(SAVE)).to_be_enabled()
    # Putting the operator's row back leaves nothing unsaved: grep is the baseline now.
    _tool(page, "read_file").check()
    expect(page.locator(UNSAVED)).to_have_text("")


def test_an_mcp_tile_with_dirty_credentials_is_kept(app_with_agent: SeededApp, page: Page) -> None:
    from browser.test_flow_studio_tools_mcp_credentials import _btn, _seed_keyed, _tr, _value

    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    sid = _seed_keyed(base)
    _visit_chats(page, base)
    _open_agent(page, agent)
    _open_tab(page, agent, "tools")
    page.locator(f'[data-testid="mcp-source-expand-{sid}"]').click()
    _btn(page, "override", sid).click()
    _value(_tr(page, sid, "X-Api-Key")).fill("typed-secret-0001")
    _put(base, agent, mcp_source_ids=[sid])
    _chats.emit_frame(page, _frame(agent, ["mcp_source_ids"], 22))
    expect(page.locator(f'[data-testid="mcp-source-toggle-{sid}"]')).to_be_checked(timeout=8000)
    # The unsaved credential edit is untouched, and the tile says what changed.
    expect(_value(_tr(page, sid, "X-Api-Key"))).to_have_value("typed-secret-0001")
    expect(page.locator(f'{NOTE}[data-field="mcp_source_ids"][data-item="{sid}"]')).to_have_count(1)


def test_the_kb_list_not_loaded_sets_nothing_and_the_first_load_shows_stored(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    kb, _sid = _seed_attachables(base)
    _visit_chats(page, base)
    _nav.set_route(page, "agents")
    expect(page.locator('[data-testid="agent-item"]').first).to_be_visible(timeout=8000)
    # The knowledge-base list fails to load as the editor opens (Studio itself has loaded).
    page.route("**/api/knowledge-bases", lambda route: route.fulfill(status=500, body="{}"))
    _open_agent(page, agent)
    page.locator('[data-testid="tab-knowledge"]').click()
    expect(page.locator('[data-testid="agent-knowledge-load-error"]')).to_be_visible(timeout=8000)
    _put(base, agent, kb_ids=[kb])
    _chats.emit_frame(page, _frame(agent, ["kb_ids"], 23))
    page.wait_for_timeout(600)
    expect(page.locator(f'[data-testid="agent-knowledge-toggle-{kb}"]')).to_have_count(0)
    expect(page.locator(NOTE)).to_have_count(0)
    expect(page.locator(UNSAVED)).to_have_text("")
    # The list loads on the next mount: the stored value is what shows.
    page.unroute("**/api/knowledge-bases")
    _nav.set_route(page, "agents")
    _open_agent(page, agent)
    _open_tab(page, agent, "knowledge")
    expect(page.locator(f'[data-testid="agent-knowledge-toggle-{kb}"]')).to_be_checked(timeout=8000)
    expect(page.locator(UNSAVED)).to_have_text("")


def _add_rule(base: str, agent: str, text: str) -> str:
    r = httpx.post(
        f"{base}/api/agents/{_nav.seg(agent)}/rules",
        json={"text": text},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _edit_rule(base: str, agent: str, rid: str, text: str) -> None:
    r = httpx.put(
        f"{base}/api/agents/{_nav.seg(agent)}/rules/{rid}",
        json={"text": text},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 200, r.text


def test_a_rule_approval_keeps_an_open_inline_edit(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    rid = _add_rule(base, agent, "Original rule")
    _add_rule(base, agent, "Other rule")
    _visit_chats(page, base)
    _open_agent(page, agent)
    _open_tab(page, agent, "rules-and-notes")
    texts = page.locator('[data-testid="rules-row-text"]')
    expect(texts).to_have_count(2, timeout=8000)
    page.locator(f'[data-testid="rules-row-edit"][data-rule-id="{rid}"]').click()
    inline = page.locator('[data-testid="rules-row-edit-input"]')
    inline.fill("My unsaved wording")
    _edit_rule(base, agent, rid, "Approved wording")
    _chats.emit_frame(page, _frame(agent, [], 24, kind="rule"))
    expect(page.locator('[data-testid="rules-row-changed-note"]')).to_have_text(
        "This rule changed. Save will replace it with your text.", timeout=8000
    )
    expect(inline).to_have_value("My unsaved wording")
    expect(page.locator(f'{NOTE}[data-field="rules"]')).to_have_count(1)
    # The Add textarea is untouched and the other rule is still listed.
    expect(page.locator('[data-testid="rules-add-input"]')).to_have_value("")
    expect(texts).to_have_count(1)


def test_a_rule_approval_just_updates_a_clean_list(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    rid = _add_rule(base, agent, "Original rule")
    _visit_chats(page, base)
    _open_agent(page, agent)
    _open_tab(page, agent, "rules-and-notes")
    expect(page.locator('[data-testid="rules-row-text"]')).to_have_text(
        "Original rule", timeout=8000
    )
    page.locator('[data-testid="rules-add-input"]').fill("typed but not added")
    _edit_rule(base, agent, rid, "Approved wording")
    _chats.emit_frame(page, _frame(agent, [], 25, kind="rule"))
    expect(page.locator('[data-testid="rules-row-text"]')).to_have_text(
        "Approved wording", timeout=8000
    )
    expect(page.locator('[data-testid="rules-row-changed-note"]')).to_have_count(0)
    expect(page.locator(f'{NOTE}[data-field="rules"]')).to_have_count(1)
    expect(page.locator('[data-testid="rules-add-input"]')).to_have_value("typed but not added")


def test_a_routine_approval_reloads_and_keeps_an_open_form(
    app_with_data_dir: tuple, page: Page
) -> None:
    from browser.seeders import seed_agent_routine

    w = _world(app_with_data_dir)
    base, agent = w.base, "plain"
    _visit_chats(page, base)
    _nav.set_route(page, f"agents/{_nav.seg(agent)}/routines")
    expect(page.locator('[data-testid="routines-new-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="routines-new-btn"]').click()
    name = page.locator('[data-testid="routine-form-name"]')
    name.fill("Half typed")
    seed_agent_routine(w.data, agent, "Approved routine", created_by="operator")
    _chats.emit_frame(page, _frame(agent, [], 26, kind="routine"))
    expect(page.locator('[data-testid="routine-name"]', has_text="Approved routine")).to_be_visible(
        timeout=8000
    )
    expect(name).to_have_value("Half typed")
    expect(page.locator(f'{NOTE}[data-field="routines"]')).to_have_count(1)
