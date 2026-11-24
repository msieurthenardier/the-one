"""The built-in tools page follows a change the operator approved in a GleepGlorp chat (M36 F5 L4b,
flight DD7, DD9 and DD14).

With the editor open on tool T, approving a ``tool_config`` proposal for T lands in it without a
reload or a re-mount: a clean field takes the stored value, a field the operator changed keeps
their value while its baseline moves, and a quiet note sits under each changed field (per-field
placement, DD14 choice 2). With the Tools grid showing, an approved ``enabled`` change flips that
tool's switch and puts a follow note at the foot of its card (DD14 choice 5), cleared by the
operator's next toggle of that tile. Most tests signal through ``App.approvals.record`` after
changing the stored row through its API; one approves a seeded proposal through the route.

Lives in the ``gleepglorp-kinds`` browser lane.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import seed_gleepglorp_proposal
from browser.test_flow_agent_editor_follows_approval import _visit_chats
from browser.test_flow_chat_proposals import _world
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

SAVE = '[data-testid="save-tool-btn"]'
CANCEL = '[data-testid="cancel-tool-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'
NOTE = '[data-testid="tool-approved-change-note"]'
GRID_NOTE = '[data-testid="tool-grid-approved-change-note"]'
TIMEOUT = "#tef-timeout_seconds_default"
OUTPUT = "#tef-output_cap_bytes"
ENABLED = "#tef-enabled"
_pid = [500]


def _get(base: str, tool: str) -> dict:
    r = httpx.get(f"{base}/api/tools/configs/{tool}", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    return r.json()


def _approve_row(base: str, tool: str, enabled: bool | None = None, **config: Any) -> dict:
    """Change the stored row the way an approved proposal does (through the API)."""
    cur = _get(base, tool)
    body = {
        "enabled": cur["enabled"] if enabled is None else enabled,
        "config": {**cur["config"], **config},
    }
    r = httpx.put(
        f"{base}/api/tools/configs/{tool}", json=body, headers=auth_headers_for(base), timeout=5.0
    )
    assert r.status_code == 200, r.text
    return r.json()


def _signal(page: Page, tool: str, fields: list[str]) -> None:
    _pid[0] += 1
    page.evaluate(
        "(d) => App.approvals.record(d)",
        {
            "kind": "tool_config",
            "target_id": tool,
            "fields": fields,
            "session_id": "sess-approved",
            "proposal_id": _pid[0],
            "at": "2026-01-02T15:05:00+00:00",
        },
    )


def _open_edit(page: Page, base: str, tool: str) -> None:
    _nav.goto_settled(page, base, f"settings/tools/{tool}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)
    expect(page.locator(UNSAVED)).to_have_text("")


def _describes(page: Page, control: str, note: str) -> bool:
    nid = page.locator(note).get_attribute("id")
    return nid in (page.locator(control).get_attribute("aria-describedby") or "").split()


# ── The editor ───────────────────────────────────────────────────────────────


def test_an_approved_change_lands_in_a_clean_editor_without_a_reload_with_notes(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    _open_edit(page, base, "shell")
    page.evaluate("() => { window.__same_page = 1; }")
    _approve_row(base, "shell", timeout_seconds_default=60, output_cap_bytes=65536)
    _signal(page, "shell", ["timeout_seconds_default", "output_cap_bytes"])
    expect(page.locator(TIMEOUT)).to_have_value("60", timeout=8000)
    expect(page.locator(OUTPUT)).to_have_value("65536")
    for field, control in (("timeout_seconds_default", TIMEOUT), ("output_cap_bytes", OUTPUT)):
        note = f'{NOTE}[data-field="{field}"]'
        expect(page.locator(note)).to_have_count(1)
        assert _describes(page, control, note)
    expect(page.locator(f"{NOTE} a").first).to_have_attribute(
        "href", _nav.href("chats/sess-approved")
    )
    expect(page.locator(UNSAVED)).to_have_text("")  # clean: the baseline moved with the values
    assert page.evaluate("() => window.__same_page") == 1


def test_a_dirty_field_keeps_the_operators_value_while_the_baseline_moves(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    _open_edit(page, base, "shell")
    page.locator(TIMEOUT).select_option("90")
    # An unrelated unsaved edit and a node of the editor, to prove nothing re-mounts.
    page.evaluate("() => { document.querySelector('#tef-output_cap_bytes').__mark = 1; }")
    _approve_row(base, "shell", timeout_seconds_default=60, output_cap_bytes=65536)
    _signal(page, "shell", ["timeout_seconds_default", "output_cap_bytes"])
    expect(page.locator(OUTPUT)).to_have_value("65536", timeout=8000)
    expect(page.locator(TIMEOUT)).to_have_value("90")  # the operator's, kept
    expect(page.locator(f'{NOTE}[data-field="output_cap_bytes"]')).to_have_count(1)
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    expect(page.locator(SAVE)).to_be_enabled()
    assert page.evaluate("() => document.querySelector('#tef-output_cap_bytes').__mark") == 1
    # Cancel shows the approved (now baseline) values.
    page.locator(CANCEL).click()
    expect(page.locator(TIMEOUT)).to_have_value("60")
    expect(page.locator(OUTPUT)).to_have_value("65536")
    expect(page.locator(NOTE)).to_have_count(0)


def test_an_approved_enabled_change_flips_the_switch_and_an_other_tools_editor_is_untouched(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    _open_edit(page, base, "shell")
    now = _get(base, "shell")["enabled"]
    _approve_row(base, "shell", enabled=not now)
    _signal(page, "python_exec", ["enabled"])  # another tool: nothing changes
    page.wait_for_timeout(500)
    expect(page.locator(NOTE)).to_have_count(0)
    assert page.locator(ENABLED).is_checked() == now
    _signal(page, "shell", ["enabled"])
    note = f'{NOTE}[data-field="enabled"]'
    expect(page.locator(note)).to_have_count(1, timeout=8000)
    assert page.locator(ENABLED).is_checked() == (not now)
    assert _describes(page, ENABLED, note)
    expect(page.locator(UNSAVED)).to_have_text("")


def test_a_real_approval_reaches_the_open_editor(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir)
    prop = seed_gleepglorp_proposal(
        w.data,
        w.sid,
        kind="tool_config",
        agent_name=None,
        target_id="shell",
        changes={"output_cap_bytes": 65536},
        base={"output_cap_bytes": 262144},
    )
    _visit_chats(page, w.base)
    _nav.set_route(page, "settings/tools/shell")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)
    r = httpx.post(
        f"{w.base}/api/gleepglorp/proposals/{prop}/approve",
        headers=auth_headers_for(w.base),
        timeout=10,
    )
    assert r.status_code == 200, r.text
    expect(page.locator(OUTPUT)).to_have_value("65536", timeout=8000)
    expect(page.locator(f'{NOTE}[data-field="output_cap_bytes"]')).to_have_count(1, timeout=8000)
    assert _get(w.base, "shell")["config"]["output_cap_bytes"] == 65536


# ── The grid ─────────────────────────────────────────────────────────────────


def _show_grid(page: Page, base: str) -> None:
    _nav.goto_settled(page, base, "settings/tools")
    page.locator('[data-testid="tab-execution"]').click()
    expect(page.locator('[data-testid="tool-card"][data-name="shell"]')).to_be_visible(
        timeout=10000
    )


def _toggle(page: Page, tool: str):
    return page.locator(f'[data-testid="tool-toggle"][data-name="{tool}"]')


def test_an_approved_enabled_change_flips_the_tile_and_notes_it_until_the_next_toggle(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    _show_grid(page, base)
    now = _toggle(page, "shell").is_checked()
    _approve_row(base, "shell", enabled=not now)
    _signal(page, "shell", ["enabled"])
    card = page.locator('[data-testid="tool-card"][data-name="shell"]')
    expect(card.locator(GRID_NOTE)).to_have_count(1, timeout=8000)
    assert _toggle(page, "shell").is_checked() == (not now)
    assert _describes(page, '[data-testid="tool-toggle"][data-name="shell"]', GRID_NOTE)
    # The link repeats per card: its name carries the tool (visible text stays "Open chat").
    link = card.locator(GRID_NOTE).get_by_role("link")
    expect(link).to_have_text("Open chat")
    expect(link).to_have_attribute("aria-label", "Open chat (shell)")
    # A caption, not unstyled body text: the caption token's size and the tertiary text colour,
    # read from a probe element that uses the tokens directly.
    got = page.evaluate(
        """() => {
          const note = document.querySelector('[data-testid="tool-grid-approved-change-note"]');
          const probe = document.createElement('span');
          probe.style.cssText = 'font-size: var(--font-size-caption); color: var(--fg-tertiary)';
          document.body.appendChild(probe);
          const want = getComputedStyle(probe);
          const have = getComputedStyle(note);
          const out = [have.fontSize, want.fontSize, have.color, want.color];
          probe.remove();
          return out;
        }"""
    )
    assert got[0] == got[1] and got[2] == got[3], got
    # Another tile has no note; the operator's next toggle of this one clears it.
    expect(page.locator(GRID_NOTE)).to_have_count(1)
    _toggle(page, "shell").evaluate("el => el.click()")
    expect(page.locator(GRID_NOTE)).to_have_count(0)


def test_a_non_enabled_change_puts_no_note_on_the_grid_and_a_newer_approval_replaces_one(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    base, _data = app_with_data_dir
    _show_grid(page, base)
    _approve_row(base, "shell", output_cap_bytes=65536)
    _signal(page, "shell", ["output_cap_bytes"])
    page.wait_for_timeout(600)
    expect(page.locator(GRID_NOTE)).to_have_count(0)
    now = _toggle(page, "shell").is_checked()
    _approve_row(base, "shell", enabled=not now)
    _signal(page, "shell", ["enabled"])
    expect(page.locator(GRID_NOTE)).to_have_count(1, timeout=8000)
    _approve_row(base, "shell", enabled=now)
    _signal(page, "shell", ["enabled"])
    page.wait_for_timeout(600)
    expect(page.locator(GRID_NOTE)).to_have_count(1)
    assert _toggle(page, "shell").is_checked() == now
