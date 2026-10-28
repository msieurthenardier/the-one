"""The agent picker (M25 F4 leg 4a, flight DD2, DD4, A16; reference spec 5.6).

The Chats list's New chat (``chats-new-btn``) opens ``App.chat.openPicker``: an
``App.ui.searchList`` in an ``App.ui.modal`` chooser (``agent-picker``, "Start
a chat with…", 640 wide at top 72, the "Esc" close button, the footer), built
fresh on every open with focus on its search (``agent-picker-search``).

* An empty query shows "Recently used" (up to five agents, by the latest
  ``updated_at`` over web sessions of live agents: connector sessions, deleted
  agents and the default agent are excluded) and "All agents" (A-Z).
* A query shows one "{n} matching" group, A-Z, matched case-insensitively over
  the name, the model, the provider type slug and the description.
* Enter picks the active row: the picker closes, then the pick routes to
  ``#chats/~new/{agent}`` (a re-pick on a ``~new`` route replaces).
* Escape, the close button and the backdrop close it with focus back on New
  chat; a guard Stay after a pick keeps the opener focused.
* Each row's lead is the provider dot (``badge--{type}``, ``badge-dot--none``
  without a provider).

Falls in the ``chats`` browser lane (``test_flow_chat*``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from browser import _chats, _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_mock_agent, seed_session
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

# The picker as rendered: {groups: [{label, rows: [{agent, label, desc, meta,
# mono, dot, leadHidden}]}], active, empty}.
_PICKER_JS = """
() => {
  const dlg = document.querySelector('[data-testid="agent-picker"]');
  if (!dlg) return null;
  const input = dlg.querySelector('[data-testid="agent-picker-search"]');
  const act = input.getAttribute('aria-activedescendant');
  const empty = dlg.querySelector('.ui-search-list-empty');
  return {
    groups: Array.from(dlg.querySelectorAll('.ui-search-list-group')).map((g) => ({
      label: g.querySelector('.ui-search-list-caption').textContent,
      rows: Array.from(g.querySelectorAll('[data-testid="agent-picker-row"]')).map((r) => {
        const lead = r.querySelector('.ui-search-list-lead');
        const meta = r.querySelector('.ui-search-list-meta');
        const desc = r.querySelector('.ui-search-list-description');
        return {agent: r.dataset.agent, label: r.querySelector('.ui-search-list-label').textContent,
                desc: desc ? desc.textContent : '', meta: meta ? meta.textContent : '',
                mono: !!(meta && meta.classList.contains('ui-search-list-meta-mono')),
                dot: lead ? lead.firstElementChild.className : null,
                leadHidden: lead ? lead.getAttribute('aria-hidden') : null};
      }),
    })),
    active: act ? document.getElementById(act).dataset.agent : null,
    empty: empty && !empty.hidden ? empty.textContent.trim() : null,
  };
}
"""


def _picker(page: Page) -> dict[str, Any]:
    return page.evaluate(_PICKER_JS)


def _names(group: dict[str, Any]) -> list[str]:
    return [r["agent"] for r in group["rows"]]


def _agent(
    base: str,
    name: str,
    provider_id: str | None,
    model: str = "mock-default",
    description: str = "",
) -> str:
    body: dict[str, Any] = {
        "name": name,
        "llm_model": model,
        "description": description,
        "system_prompt": "You are a test agent.",
    }
    if provider_id:
        body["provider_config_id"] = provider_id
    r = httpx.post(f"{base}/api/agents", json=body, headers=auth_headers_for(base), timeout=5)
    assert r.status_code == 201, r.text
    return name


def _provider(base: str, name: str, ptype: str) -> str:
    r = httpx.post(
        f"{base}/api/providers",
        json={"name": name, "type": ptype, "base_url": "http://127.0.0.1:9", "config": {}},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _dirty(page: Page, dirty: bool) -> None:
    """Register (or clean) a test leave-guard source (App.nav)."""
    page.evaluate(
        "(d) => App.nav.registerSource('picker-test', {isDirty: () => d, discard() {}})", dirty
    )


def _settled(page: Page, base: str) -> None:
    _nav.goto(page, base, "chats")
    page.wait_for_function(
        "() => { const a = (App.areas || []).find(x => x.id === 'chat');"
        " const st = a && a._sessionState ? a._sessionState().name : null;"
        " return st === 'joined' || (st === 'idle' &&"
        " !document.querySelector('[data-testid=\"chat-welcome\"]').hidden); }",
        timeout=8000,
    )


# ── Open, focus, close ──────────────────────────────────────────────────────


def test_new_chat_opens_the_picker_focused_and_every_close_returns_focus(
    app_with_agent: SeededApp, page: Page
) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _settled(page, base)
    new_btn = _chats.chats_new_button(page)

    _chats.open_picker(page)
    dlg = _chats.picker(page)
    expect(dlg.locator("h2")).to_have_text("Start a chat with…")
    close = dlg.locator('[data-testid="agent-picker-close"]')
    expect(close).to_have_text("Esc")
    expect(close).to_have_attribute("aria-label", "Close (Esc)")
    search = _chats.picker_search(page)
    expect(search).to_have_attribute("placeholder", "Find an agent by name, model or provider")
    expect(search).to_have_accessible_name("Find an agent")
    expect(dlg.locator(".modal-dialog-footer")).to_contain_text(
        "Picking an agent starts a new chat with it"
    )
    expect(dlg.locator(".modal-dialog-footer .modal-dialog-footer-end")).to_have_text(
        "Enter to start"
    )
    card = dlg.locator(".modal-dialog").bounding_box()
    assert card and round(card["width"]) == 640 and round(card["y"]) == 72, card
    got = _picker(page)
    assert [g["label"] for g in got["groups"]] == ["All agents"]  # no sessions yet
    assert _names(got["groups"][0]) == [agent] and got["active"] == agent

    # No match.
    search.fill("zzz")
    expect(dlg.locator(".ui-search-list-empty")).to_be_visible()
    assert _picker(page)["empty"] == 'No agents match "zzz".'

    # Escape closes; focus is back on New chat; nothing was picked.
    page.keyboard.press("Escape")
    expect(dlg).to_have_count(0)
    expect(new_btn).to_be_focused()
    _nav.expect_route(page, "chats")

    # Built fresh on every open: the query is cleared on the next open.
    _chats.open_picker(page)
    expect(search).to_have_value("")
    # The close button closes too, focus back on New chat.
    dlg.locator('[data-testid="agent-picker-close"]').click()
    expect(dlg).to_have_count(0)
    expect(new_btn).to_be_focused()
    # And the backdrop (the dialog itself, outside the card).
    _chats.open_picker(page)
    page.mouse.click(20, 600)
    expect(dlg).to_have_count(0)
    expect(new_btn).to_be_focused()
    assert _chats.session_state(page)["name"] == "idle"


# ── Recently used and All agents ────────────────────────────────────────────


def test_recently_used_and_all_agents(app_with_provider: SeededApp, page: Page) -> None:
    """Recently used: the five live agents with the latest web sessions, most
    recent first. A connector session (Golf), a deleted agent's session
    (Ghost) and a default-agent session are newer than most, yet excluded; the
    sixth web agent (Charlie) is past the cap. All agents: every live agent
    A-Z, the recent ones included."""
    base, pid = app_with_provider.base_url, app_with_provider.provider_id
    for n in ("Hotel", "Golf", "Foxtrot", "Echo", "Delta", "Charlie", "Bravo", "Alpha", "Ghost"):
        seed_mock_agent(base, pid, name=n)
    now = datetime.now(UTC)

    def at(minutes: int) -> datetime:
        return now - timedelta(minutes=minutes)

    seed_session(base, "Bravo", "b-new", at(1))  # newest overall (auto-joined)
    seed_session(base, "Golf", "golf on discord", at(2), platform="discord")
    seed_session(base, "Ghost", "ghost chat", at(3))
    seed_session(base, None, "default chat", at(4))
    seed_session(base, "Delta", "d", at(5))
    seed_session(base, "Alpha", "a", at(6))
    seed_session(base, "Bravo", "b-old", at(7))
    seed_session(base, "Echo", "e", at(8))
    seed_session(base, "Foxtrot", "f", at(9))
    seed_session(base, "Charlie", "c", at(10))
    r = httpx.delete(f"{base}/api/agents/Ghost", headers=auth_headers_for(base), timeout=5)
    assert r.status_code == 200, r.text

    _settled(page, base)
    _chats.open_picker(page)
    got = _picker(page)
    assert [g["label"] for g in got["groups"]] == ["Recently used", "All agents"]
    assert _names(got["groups"][0]) == ["Bravo", "Delta", "Alpha", "Echo", "Foxtrot"]
    assert _names(got["groups"][1]) == [
        "Alpha",
        "Bravo",
        "Charlie",
        "Delta",
        "Echo",
        "Foxtrot",
        "Golf",
        "Hotel",
    ]
    assert got["active"] == "Bravo"  # the first option is active
    # Arrow keys move the active option across groups.
    _chats.picker_search(page).press("ArrowDown")
    assert _picker(page)["active"] == "Delta"


# ── Matching ────────────────────────────────────────────────────────────────


def test_query_matches_name_model_type_and_description_a_to_z(
    app_with_provider: SeededApp, page: Page
) -> None:
    base, mock = app_with_provider.base_url, app_with_provider.provider_id
    ollama = _provider(base, "Local models", "ollama")
    _agent(base, "Writer", mock, "mock-default", "Drafts release notes")
    _agent(base, "Reviewer", ollama, "llama3.1:8b", "Reads diffs")
    _agent(base, "Archivist", ollama, "qwen2:7b", "Files notes into the wiki")
    _agent(base, "Zeta", mock, "special-model-x", "")
    _settled(page, base)
    _chats.open_picker(page)
    search = _chats.picker_search(page)

    def query(q: str) -> dict[str, Any]:
        search.fill(q)
        return _picker(page)

    cases = {
        "notes": ["Archivist", "Writer"],  # description, A-Z (A16)
        "OLLAMA": ["Archivist", "Reviewer"],  # provider type slug, case-insensitive
        "special-model": ["Zeta"],  # model
        "rev": ["Reviewer"],  # name
        "  wiki ": ["Archivist"],  # trimmed
        "e": ["Archivist", "Reviewer", "Writer", "Zeta"],
    }
    for q, want in cases.items():
        got = query(q)
        assert [g["label"] for g in got["groups"]] == [f"{len(want)} matching"], (q, got)
        assert _names(got["groups"][0]) == want, (q, got)
        assert got["active"] == want[0], (q, got)
    got = query("local models")  # the provider's display name is not matched
    assert got["groups"] == [] and got["empty"] == 'No agents match "local models".', got


# ── Picking ─────────────────────────────────────────────────────────────────


def test_enter_picks_and_a_re_pick_replaces(app_with_provider: SeededApp, page: Page) -> None:
    base, pid = app_with_provider.base_url, app_with_provider.provider_id
    seed_mock_agent(base, pid, name="Alpha")
    seed_mock_agent(base, pid, name="Bravo")
    frames = _chats.chat_frames(page, actions=("leave", "start_session", "join"))
    _settled(page, base)
    h0 = page.evaluate("history.length")

    # Type, Enter: the picker closes, then the pick routes (a first pick pushes).
    _chats.open_picker(page)
    _chats.picker_search(page).fill("alp")
    _chats.picker_search(page).press("Enter")
    expect(_chats.picker(page)).to_have_count(0)
    _nav.expect_route(page, "chats/~new/Alpha")
    st = _chats.session_state(page)
    assert st["name"] == "pending" and st["agent"] == "Alpha"
    expect(_chats.pending_row(page)).to_have_count(1)
    expect(_chats.pending_row(page)).to_contain_text("Alpha")
    # M31 F6 L05a (0.1, deliberate): a completed pick lands in the message box (it was the
    # opener); a leave-guard Stay keeps the opener (the next test).
    expect(page.locator('[data-testid="chat-input"]')).to_be_focused()
    h1 = page.evaluate("history.length")
    assert h1 == h0 + 1

    # A re-pick on a ~new route replaces it (history.length unchanged).
    _chats.pick(page, "Bravo")
    _nav.expect_route(page, "chats/~new/Bravo")
    expect(_chats.pending_row(page)).to_have_count(1)
    expect(_chats.pending_row(page)).to_contain_text("Bravo")
    assert page.evaluate("history.length") == h1
    assert frames == []  # nothing bound, nothing created


def test_a_guard_stay_keeps_the_pickers_opener_focused(
    app_with_agent: SeededApp, page: Page
) -> None:
    """A pick runs from the picker's onClose, after focus is back on New chat:
    a leave-guard dialog never stacks under the chooser, and Stay keeps New
    chat focused with the route unchanged. (No dirty source exists on Chats
    in practice; a test source stands in for one.)"""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _settled(page, base)
    _dirty(page, True)
    _chats.open_picker(page)
    _chats.picker_search(page).fill(agent)
    _chats.picker_search(page).press("Enter")
    dialog = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(dialog).to_be_visible()
    expect(_chats.picker(page)).to_have_count(0)  # closed before the guard asked
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(dialog).to_have_count(0)
    expect(_chats.chats_new_button(page)).to_be_focused()
    _nav.expect_route(page, "chats")
    assert _chats.session_state(page)["name"] == "idle"
    _dirty(page, False)


def test_open_picker_from_another_destination_moves_to_chats_first(
    app_with_agent: SeededApp, page: Page
) -> None:
    """App.chat.openPicker from a cold chat area (booted on Agents): it goes to
    Chats (a commit), then opens. A guard Stay on the move rejects it."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _nav.goto(page, base, "agents")
    expect(page.locator('[data-testid="agents-list"]')).to_be_visible(timeout=8000)
    # A Stay on the move: rejected, nothing opened, still on Agents.
    _dirty(page, True)
    page.evaluate(
        "() => { window.__pick = 'pending'; App.chat.openPicker({}).then("
        " () => { window.__pick = 'open'; }, () => { window.__pick = 'rejected'; }); }"
    )
    page.locator('[data-testid="modal-cancel-btn"]').click()
    page.wait_for_function("() => window.__pick === 'rejected'", timeout=8000)
    _nav.expect_route(page, "agents")
    expect(_chats.picker(page)).to_have_count(0)
    _dirty(page, False)
    # A clean move: Chats, then the picker.
    page.evaluate(
        "() => { window.__pick = 'pending'; App.chat.openPicker({}).then("
        " () => { window.__pick = 'open'; }, () => { window.__pick = 'rejected'; }); }"
    )
    page.wait_for_function("() => window.__pick === 'open'", timeout=8000)
    _nav.expect_route(page, "chats")
    expect(_chats.picker(page)).to_be_visible()
    expect(_chats.picker_search(page)).to_be_focused()
    expect(_chats.picker_row(page, agent)).to_have_count(1)


# ── Provider dots ───────────────────────────────────────────────────────────


def test_provider_dots_per_type(app_with_provider: SeededApp, page: Page) -> None:
    base, mock = app_with_provider.base_url, app_with_provider.provider_id
    ollama = _provider(base, "Local models", "ollama")
    _agent(base, "Llama", ollama, "llama3.1:8b", "Runs locally")
    _agent(base, "Mocky", mock, "mock-default", "Answers from a script")
    _agent(base, "Orphan", None, "", "")
    _settled(page, base)
    _chats.open_picker(page)
    rows = {r["agent"]: r for r in _picker(page)["groups"][0]["rows"]}
    assert {a: r["dot"] for a, r in rows.items()} == {
        "Llama": "badge badge--ollama badge-dot",
        "Mocky": "badge badge--mock badge-dot",
        "Orphan": "badge badge-dot badge-dot--none",
    }
    assert all(r["leadHidden"] == "true" for r in rows.values())
    assert rows["Llama"]["meta"] == "llama3.1:8b" and rows["Llama"]["mono"] is True
    assert rows["Llama"]["desc"] == "Runs locally"
    assert rows["Orphan"]["meta"] == "" and rows["Orphan"]["label"] == "Orphan"
