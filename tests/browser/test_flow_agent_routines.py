# ruff: noqa: E501  (inline JS snippets and long locator lines are kept verbatim)
"""The agent editor's Routines tab, list half (M33 F1 L8; flight DD12, DD9).

The tab (between Tools and Self-configuration) lists an agent's routines as cards built like the
Tools tab's (switch, name and actions menu on top, the schedule and the next and last runs
under it, a "Details" expander at the bottom: the prompt and the recent runs, each linking to
the chat it started).
It loads lazily, polls only while a run is going, and saves every action at once. Every run
starts a new chat, so a routine has no target. The create/edit form is covered by
``test_flow_agent_routines_form.py`` (leg 9). Falls in the ``agent-routines`` lane via the
``test_flow_agent_routines*`` glob.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_agent_routine, seed_mock_agent, seed_mock_provider
from browser.seeders import canonical_schedule as canon
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

ROWS = '[data-testid="routine-row"]'
# Relative starts: the first run is a set time from the request, whatever the date.
EVERY_2H = {
    "start": {"in": {"amount": 2, "unit": "hours"}},
    "repeat": {"every": 2, "unit": "hour"},
}
IN_3_DAYS = {"start": {"in": {"amount": 3, "unit": "days"}}}


def _create(base: str, agent: str, name: str, schedule: dict) -> dict:
    r = httpx.post(
        f"{base}/api/agents/{agent}/routines",
        json={"name": name, "prompt": "Say hello.", "schedule": schedule},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _list(base: str, agent: str) -> list[dict]:
    r = httpx.get(f"{base}/api/agents/{agent}/routines", headers=auth_headers_for(base), timeout=5)
    assert r.status_code == 200, r.text
    return r.json()["routines"]


def _open_tab(page: Page, base: str, agent: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(agent)}/routines")
    expect(page.locator('[data-testid="tab-routines"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    expect(page.locator('[data-testid="routines-section"]')).to_be_visible(timeout=8000)


def _row(page: Page, name: str):
    return page.locator(ROWS, has=page.locator('[data-testid="routine-name"]', has_text=name))


def _item(row, testid: str):
    """Open a row's actions menu and return one of its items."""
    if row.locator('[data-testid="routine-menu"]').is_hidden():
        row.locator('[data-testid="routine-actions"]').click()
    return row.locator(f'[data-testid="{testid}"]')


def _runs(base: str, agent: str, rid: str) -> list[dict]:
    r = httpx.get(
        f"{base}/api/agents/{agent}/routines/{rid}/runs",
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 200, r.text
    return r.json()["runs"]


def test_tab_order_route_and_empty_state(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    ids = page.locator('[role="tab"]').evaluate_all("els => els.map(e => e.dataset.tabId)")
    assert ids == [
        "general",
        "rules-and-notes",
        "knowledge",
        "tools",
        "routines",
        "self-configuration",
    ]
    _nav.expect_route(page, f"agents/{_nav.seg(agent)}/routines")
    expect(page.locator('[data-testid="routines-empty"]')).to_contain_text("No routines yet.")
    expect(page.locator('[data-testid="routines-section"] h3')).to_have_text("Routines")
    # One New routine control on the empty tab: the toolbar's, none in the empty state.
    expect(page.get_by_role("button", name="New routine")).to_have_count(1)
    expect(page.locator('[data-testid="routines-new-btn"]')).to_be_visible()
    expect(page.locator('[data-testid="routines-empty"] button')).to_have_count(0)


def test_form_buttons_show_for_a_named_agent(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "nightly", canon("09:00"))
    _open_tab(page, base, agent)
    expect(_row(page, "nightly")).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="routines-new-btn"]')).to_be_visible()
    expect(_item(_row(page, "nightly"), "routine-edit")).to_be_visible()


def test_create_mode_shows_save_first(app_with_provider: SeededApp, page: Page) -> None:
    base = app_with_provider.base_url
    _nav.goto(page, base, "agents/~new")
    page.locator('[data-testid="tab-routines"]').click(timeout=8000)
    expect(page.locator('[data-testid="routines-save-first"]')).to_be_visible()
    reqs: list[str] = []
    page.on(
        "request",
        lambda r: (
            reqs.append(r.url)
            if "/api/" in r.url and "/routines" in r.url and "/self-configuration/" not in r.url
            else None
        ),
    )
    page.wait_for_timeout(300)
    assert reqs == []


def test_lazy_load_no_request_until_the_tab_opens(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "lazy", canon("09:00"))
    reqs: list[str] = []
    page.on(
        "request",
        lambda r: (
            reqs.append(r.url)
            if "/api/" in r.url and "/routines" in r.url and "/self-configuration/" not in r.url
            else None
        ),
    )
    _nav.goto(page, base, f"agents/{_nav.seg(agent)}/general")
    expect(page.locator('[data-testid="tab-general"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
    page.wait_for_timeout(500)
    assert reqs == []
    page.locator('[data-testid="tab-routines"]').click()
    expect(_row(page, "lazy")).to_be_visible(timeout=8000)
    page.wait_for_timeout(300)
    assert len(reqs) == 1, reqs
    # Re-selecting the same tab does not refetch.
    page.locator('[data-testid="tab-routines"]').click()
    page.wait_for_timeout(300)
    assert len(reqs) == 1, reqs


def test_direct_open_fetches_once(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "once-only", canon("09:00"))
    reqs: list[str] = []
    page.on(
        "request",
        lambda r: reqs.append(r.url) if r.url.endswith(f"/{agent}/routines") else None,
    )
    _open_tab(page, base, agent)
    expect(_row(page, "once-only")).to_be_visible(timeout=8000)
    page.wait_for_timeout(500)
    assert len(reqs) == 1, reqs


def test_row_texts(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "b-daily", canon("09:00"))
    week = {"every": 1, "unit": "week", "days": [0, 2, 4]}
    _create(base, agent, "a-week", canon("19:30", repeat=week))
    _create(base, agent, "c-int", EVERY_2H)
    _create(base, agent, "d-days", canon("08:15", repeat="weekdays"))
    _create(base, agent, "e-once", IN_3_DAYS)
    _open_tab(page, base, agent)
    names = page.locator('[data-testid="routine-name"]')
    expect(names).to_have_count(5, timeout=8000)
    assert names.all_inner_texts() == ["a-week", "b-daily", "c-int", "d-days", "e-once"]
    expect(_row(page, "a-week").locator('[data-testid="routine-schedule"]')).to_have_text(
        "Every week on Mon, Wed, Fri at 7:30 PM"
    )
    expect(_row(page, "b-daily").locator('[data-testid="routine-schedule"]')).to_have_text(
        "Every day at 9:00 AM"
    )
    expect(_row(page, "c-int").locator('[data-testid="routine-schedule"]')).to_have_text(
        re.compile(r"^Every 2 hours from \w{3} \d{1,2} at \d{1,2}:\d{2} (AM|PM)$")
    )
    expect(_row(page, "d-days").locator('[data-testid="routine-schedule"]')).to_have_text(
        "Every weekday at 8:15 AM"
    )
    expect(_row(page, "e-once").locator('[data-testid="routine-schedule"]')).to_have_text(
        re.compile(r"^Once, on \w{3}, \w{3} \d{1,2}, \d{4} at \d{1,2}:\d{2} (AM|PM)$")
    )
    expect(_row(page, "b-daily").locator('[data-testid="routine-next"]')).to_have_text(
        re.compile(r"^(Today|Tomorrow|\w{3}|\w{3} \d{1,2},) \d{1,2}:\d{2} (AM|PM)$")
    )
    expect(_row(page, "b-daily").locator('[data-testid="routine-last"]')).to_have_text(
        "Not run yet"
    )
    # No target anywhere in the list: every run starts a new chat.
    section = page.locator('[data-testid="routines-section"]')
    expect(section).not_to_contain_text(
        re.compile(r"runs? in\b|own chat|chat each|chat gone", re.I)
    )
    expect(page.locator(".routines-intro")).to_have_text(
        "A routine sends a prompt to this agent on a schedule. Each run starts a new chat."
    )


def test_each_routine_is_a_group_tile_title_on_top_details_expander_below(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Built like the Tools tab's cards: the title row (switch, name, menu) above the schedule
    and the next and last runs, the "Details" expander at the bottom; no caption row."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    long_name = "a-very-long-routine-name-" + "x" * 38
    _create(base, agent, long_name, canon("09:00"))
    every_day = {"every": 1, "unit": "week", "days": [0, 1, 2, 3, 4, 5, 6]}
    _create(base, agent, "short", canon("07:05", repeat=every_day))
    page.set_viewport_size({"width": 1440, "height": 900})
    _open_tab(page, base, agent)
    row = _row(page, "short")
    expect(row).to_be_visible(timeout=8000)
    expect(row).to_have_class(re.compile(r"\bui-group-tile\b"))
    assert page.locator(".routines-captions, .routines-table").count() == 0

    def top(sel: str) -> float:
        return row.locator(sel).first.evaluate("(e) => e.getBoundingClientRect().top")

    name_top = top('[data-testid="routine-name"]')
    assert abs(top('[data-testid="routine-toggle"]') - name_top) < 30
    assert abs(top('[data-testid="routine-actions"]') - name_top) < 30
    sub_top = top('[data-testid="routine-schedule"]')
    next_top = top('[data-testid="routine-next"]')
    expand = row.locator('[data-testid="routine-details-toggle"]')
    expand_top = top('[data-testid="routine-details-toggle"]')
    assert name_top < sub_top < next_top < expand_top
    expect(expand).to_have_text(re.compile(r"^Details"))
    assert expand.get_attribute("aria-label") == "Details for short"
    expect(row.locator('[data-testid="routine-next"]')).to_be_visible()
    times = row.locator("p.routine-times").text_content() or ""
    assert times.startswith("Next run: ") and "Last run: " in times
    page.set_viewport_size({"width": 1024, "height": 800})
    expect(_row(page, long_name[:30])).to_be_visible()
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0, overflow
    # The menu stays reachable at the narrow width.
    expect(_item(_row(page, "short"), "routine-edit")).to_be_visible()


def test_describe_helpers_precedence_and_outcomes(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    out = page.evaluate(
        """() => {
          const d = App.studio.routinesDescribe;
          const now = new Date().toISOString();
          const slim = (s) => ({state: s.state, label: s.label, text: s.text});
          return {
            done: d.describeNext({finished_at: now, enabled: false}),
            off: d.describeNext({enabled: false, next_run_at: now}),
            unset: d.describeNext({enabled: true}),
            today: d.describeNext({enabled: true, next_run_at: now}).startsWith('Today '),
            ok: slim(d.outcomeStatus({outcome: 'ok', finished_at: now})),
            failed: slim(d.outcomeStatus({outcome: 'failed', finished_at: now, reason: 'boom'})),
            missed: slim(d.outcomeStatus({outcome: 'missed', reason: 'App was closed'})),
            skipped: slim(d.outcomeStatus({outcome: 'skipped', reason: 'Skipped 3 times in a row'})),
            stopped: slim(d.outcomeStatus({outcome: 'stopped', finished_at: now})),
            none: slim(d.outcomeStatus(null)),
            run: slim(d.outcomeStatus({outcome: 'ok'}, true)),
            schedule: typeof d.describeSchedule,
            targets: Object.keys(d).filter((k) => /target/i.test(k)),
          };
        }"""
    )
    assert out["done"] == "Done"
    assert out["off"] == "Off"
    assert out["unset"] == "Not scheduled"
    assert out["today"] is True
    assert out["ok"]["state"] == "success" and out["ok"]["label"].startswith("Ran ")
    assert out["ok"]["text"] == "Ran"  # no stored reason: the verb alone
    # The label (the last-run cell) never carries the reason; the text (a run's line) states
    # the stored reason once.
    assert out["failed"]["state"] == "danger" and out["failed"]["label"].startswith("Failed ")
    assert "boom" not in out["failed"]["label"] and out["failed"]["text"] == "Failed: boom"
    assert out["missed"]["state"] == "warning"
    assert out["missed"]["text"] == "Missed: App was closed"
    # A reason that already opens with the verb stands alone (no "Skipped: Skipped ...").
    assert out["skipped"]["text"] == "Skipped 3 times in a row"
    assert out["stopped"]["state"] == "idle"
    assert out["none"] == {"state": "idle", "label": "Not run yet", "text": "Not run yet"}
    assert out["run"]["state"] == "pending" and out["run"]["label"] == "Running…"
    assert out["schedule"] == "undefined"  # the server words schedules
    assert out["targets"] == []  # a routine has no target


def test_toggle_saves_and_row_goes_off(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "flip", canon("09:00"))
    _open_tab(page, base, agent)
    row = _row(page, "flip")
    toggle = row.locator('[data-testid="routine-toggle"]')
    expect(toggle).to_be_checked(timeout=8000)
    assert toggle.get_attribute("aria-label") == "Enable flip"
    toggle.click(force=True)
    expect(row.locator('[data-testid="routine-next"]')).to_have_text("Off", timeout=8000)
    expect(toggle).not_to_be_checked()
    assert _list(base, agent)[0]["enabled"] is False
    toggle.click(force=True)
    expect(row.locator('[data-testid="routine-next"]')).not_to_have_text("Off", timeout=8000)
    expect(row.locator('[data-testid="routine-next"]')).to_have_text(
        re.compile(r"\d{1,2}:\d{2} (AM|PM)$")
    )


def test_delete_asks_in_a_dialog_then_removes_and_shows_empty(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "gone", canon("09:00"))
    _open_tab(page, base, agent)
    row = _row(page, "gone")
    _item(row, "routine-delete").click()
    dialog = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("Delete gone?")
    expect(dialog).to_contain_text("Its run history goes with it")
    confirm = page.locator('[data-testid="modal-confirm-btn"]')
    expect(confirm).to_have_text("Delete")
    expect(confirm).to_have_class(re.compile("btn-muted-destructive"))
    # Cancel leaves the routine and returns focus to the row's actions button.
    page.locator('[data-testid="modal-cancel-btn"]').click()
    expect(dialog).to_have_count(0)
    expect(row.locator('[data-testid="routine-actions"]')).to_be_focused()
    assert len(_list(base, agent)) == 1
    _item(row, "routine-delete").click()
    page.keyboard.press("Escape")
    expect(row.locator('[data-testid="routine-actions"]')).to_be_focused()
    assert len(_list(base, agent)) == 1
    _item(row, "routine-delete").click()
    confirm.click()
    expect(page.locator(ROWS)).to_have_count(0, timeout=8000)
    expect(page.locator('[data-testid="routines-empty"]')).to_be_visible()
    assert _list(base, agent) == []
    expect(page.locator('[data-testid="routines-new-btn"]')).to_be_focused()


def test_delete_moves_focus_to_the_neighbour_row(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "aaa", canon("09:00"))
    _create(base, agent, "bbb", canon("10:00"))
    _open_tab(page, base, agent)
    _item(_row(page, "aaa"), "routine-delete").click()
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(ROWS)).to_have_count(1, timeout=8000)
    expect(_row(page, "bbb").locator('[data-testid="routine-details-toggle"]')).to_be_focused()


def test_the_last_rows_menu_is_not_clipped(app_with_agent: SeededApp, page: Page) -> None:
    """The card list does not clip a popup: the last card's Delete is whole and clickable."""
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "aaa", canon("09:00"))
    _create(base, agent, "zzz", canon("10:00"))
    _open_tab(page, base, agent)
    row = _row(page, "zzz")
    delete = _item(row, "routine-delete")
    expect(delete).to_be_visible()
    # Hit-test the item's centre: the element on top there is the item itself (not clipped
    # away and not covered by the list border or the next element).
    on_top = delete.evaluate(
        """(el) => { const r = el.getBoundingClientRect();
          const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return top === el || el.contains(top); }"""
    )
    assert on_top
    delete.click(timeout=3000)
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible()


def test_a_done_routine_has_a_disabled_switch_and_cannot_run_now(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, data_dir = app_with_data_dir
    agent = seed_mock_agent(base, seed_mock_provider(base))
    seed_agent_routine(
        data_dir,
        agent,
        "finished",
        created_by="operator",
        finished_at="2026-01-02T09:00:00+00:00",
    )
    _create(base, agent, "live", canon("09:00"))
    _open_tab(page, base, agent)
    done = _row(page, "finished")
    expect(done.locator('[data-testid="routine-next"]')).to_have_text("Done", timeout=8000)
    expect(done.locator('[data-testid="routine-toggle"]')).to_have_count(1)
    # A Done routine keeps its switch, disabled and off, with the reason attached.
    expect(done.locator(".ui-toggle")).to_be_visible()
    expect(done.locator('[data-testid="routine-toggle"]')).to_be_disabled()
    expect(done.locator('[data-testid="routine-toggle"]')).not_to_be_checked()
    expect(done.locator('[data-testid="routine-toggle"]')).to_have_attribute(
        "aria-describedby", re.compile(r"routine-done")
    )
    expect(_item(done, "routine-run-now")).to_have_attribute("aria-disabled", "true")
    expect(_item(done, "routine-edit")).not_to_have_attribute("aria-disabled", "true")
    page.keyboard.press("Escape")
    # A live routine keeps its switch and a runnable Run now.
    live = _row(page, "live")
    expect(live.locator(".ui-toggle")).to_be_visible()
    expect(_item(live, "routine-run-now")).not_to_have_attribute("aria-disabled", "true")


def _wait_more(page: Page, reqs: list, floor: int, timeout_ms: int = 10000) -> None:
    """Wait (page timeouts, no sleeps) until more than *floor* requests have been seen."""
    waited = 0
    while len(reqs) <= floor:
        assert waited < timeout_ms, f"no new request past {floor}: {reqs}"
        page.wait_for_timeout(250)
        waited += 250


def _set_delay(base: str, provider_id: str, ms: int) -> None:
    r = httpx.put(
        f"{base}/api/providers/{provider_id}",
        json={"config": {"delay_ms": ms}},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 200, r.text


def test_run_now_shows_running_then_ran_and_history(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _set_delay(base, app_with_agent.provider_id, 2000)
    _create(base, agent, "manual", canon("09:00"))
    _open_tab(page, base, agent)
    row = _row(page, "manual")
    run = row.locator('[data-testid="routine-run-now"]')
    # Open the details first: an open row stays open through the running-state refetches.
    row.locator('[data-testid="routine-details-toggle"]').click()
    expect(row.locator('[data-testid="routine-details"]')).to_be_visible()
    expect(row.locator('[data-testid="routine-details-prompt"]')).to_have_text("Say hello.")
    expect(row.locator('[data-testid="routine-recent-runs"]')).to_have_count(1)
    expect(row.get_by_text("No runs yet.")).to_be_visible(timeout=8000)
    _item(row, "routine-run-now").click()
    expect(row.locator('[data-testid="routine-last"]')).to_have_text("Running…", timeout=8000)
    # The menu closed and focus returned to the row's actions button; Run now is disabled for
    # the length of the run and the start is announced once.
    expect(row.locator('[data-testid="routine-actions"]')).to_be_focused()
    expect(run).to_have_attribute("aria-disabled", "true")
    expect(page.locator('[data-testid="routines-live"]')).to_have_text("Started manual")
    expect(row.locator('[data-testid="routine-details"]')).to_be_visible()
    expect(row.locator('[data-testid="routine-last"]')).to_have_text(
        re.compile(r"^Ran "), timeout=20000
    )
    expect(row.locator('[data-testid="routine-next"]')).not_to_have_text("Running")
    expect(run).not_to_have_attribute("aria-disabled", "true")
    expect(page.locator('[data-testid="routines-live"]')).to_have_text(re.compile(r"^manual: Ran "))
    # The open details followed the run: it is listed, started by Run now, and links to its chat.
    entry = row.locator('[data-testid="routine-recent-run"]')
    expect(entry).to_have_count(1, timeout=8000)
    expect(entry.first).to_contain_text("Run now")
    expect(entry.first).to_contain_text("Ran")
    expect(row.locator('[data-testid="routine-recent-runs-more"]')).to_be_hidden()


def test_a_recent_run_links_to_its_chat_and_a_deleted_chat_says_so(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    rid = _create(base, agent, "linked", canon("09:00"))["id"]
    for done in (1, 2):
        r = httpx.post(
            f"{base}/api/agents/{agent}/routines/{rid}/run",
            headers=auth_headers_for(base),
            timeout=5,
        )
        assert r.status_code == 202
        waited = 0
        while len([x for x in _runs(base, agent, rid) if x["outcome"] == "ok"]) < done:
            assert waited < 40, "the run did not finish"
            page.wait_for_timeout(500)
            waited += 1
    runs = _runs(base, agent, rid)
    assert len(runs) == 2 and all(x["session_id"] for x in runs)
    newest, oldest = runs[0], runs[1]
    # Delete the older run's chat: its line says so and offers no link.
    d = httpx.delete(
        f"{base}/api/chat/sessions/{oldest['session_id']}",
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert d.status_code in (200, 204), d.text
    _open_tab(page, base, agent)
    row = _row(page, "linked")
    row.locator('[data-testid="routine-details-toggle"]').click()
    lines = row.locator('[data-testid="routine-recent-run"]')
    expect(lines).to_have_count(2, timeout=8000)
    link = row.locator('[data-testid="routine-recent-run-chat"]')
    expect(link).to_have_count(1)
    expect(lines.nth(1)).to_contain_text("Chat deleted")
    expect(lines.nth(1).locator('[data-testid="routine-recent-run-chat"]')).to_have_count(0)
    assert link.get_attribute("href") == _nav.href(f"chats/{newest['session_id']}")
    # The link names the routine and the run (the same words repeat down the list).
    assert re.fullmatch(
        r"Open chat, linked, run at (.+ )?\d{1,2}:\d{2} (AM|PM)",
        link.get_attribute("aria-label") or "",
    )
    link.click()
    _nav.expect_route(page, f"chats/{newest['session_id']}")


def _mock_runs(page: Page, runs: list[dict]) -> list[str]:
    """Answer a routine's runs requests from a fixed list (newest first), honouring limit and
    before, and record each request's query."""
    seen: list[str] = []

    def handle(route):
        from urllib.parse import parse_qs, urlparse

        q = parse_qs(urlparse(route.request.url).query)
        seen.append(urlparse(route.request.url).query)
        limit = int(q.get("limit", ["50"])[0])
        before = q.get("before", [None])[0]
        rows = [r for r in runs if before is None or r["started_at"] < before][:limit]
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"runs": rows}))

    page.route(re.compile(r".*/routines/[^/]+/runs(\?.*)?$"), handle)
    return seen


def _fake_run(i: int, outcome: str = "ok", reason: str | None = None, **extra) -> dict:
    return {
        "id": f"r{i}",
        "routine_id": "x",
        "trigger_kind": "schedule",
        "outcome": outcome,
        "reason": reason,
        "started_at": f"2026-10-{i:02d}T09:00:00+00:00",
        "finished_at": f"2026-10-{i:02d}T09:00:30+00:00",
        "due_at": f"2026-10-{i:02d}T09:00:00+00:00",
        "session_id": None,
        "chat_exists": False,
        **extra,
    }


def test_recent_runs_show_the_stored_reason_once_and_page_with_show_more(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "reasons", canon("09:00"))
    runs = [
        _fake_run(28, "skipped", "the previous run was still going"),
        _fake_run(27, "failed", "The run took longer than 15 minutes."),
        _fake_run(26, "skipped", "Skipped 3 times while the app was closed"),
        _fake_run(25, "missed", "The app was closed at the scheduled time."),
        _fake_run(24, "ok", trigger_kind="manual"),
        *[_fake_run(i) for i in range(23, 4, -1)],  # 19 older runs: one short page of 20
    ]
    seen = _mock_runs(page, runs)
    _open_tab(page, base, agent)
    row = _row(page, "reasons")
    row.locator('[data-testid="routine-details-toggle"]').click()
    lines = row.locator('[data-testid="routine-recent-run"]')
    expect(lines).to_have_count(5, timeout=8000)
    assert "limit=5" in seen[0], seen
    texts = [t.strip() for t in lines.all_inner_texts()]
    assert "Skipped: the previous run was still going" in texts[0]
    assert "Failed: The run took longer than 15 minutes." in texts[1]
    # A reason that opens with the verb is not prefixed with it again.
    assert "Skipped 3 times while the app was closed" in texts[2]
    assert "Skipped: Skipped" not in texts[2]
    assert "Missed: The app was closed at the scheduled time." in texts[3]
    assert "Run now" in texts[4]
    assert lines.locator('[data-testid="routine-recent-run-chat"]').count() == 0
    # Show more appends the next page of 20 after the last run shown.
    more = row.locator('[data-testid="routine-recent-runs-more"]')
    expect(more).to_be_visible()
    more.click()
    expect(lines).to_have_count(24, timeout=8000)
    assert "limit=20" in seen[-1] and "before=" in seen[-1], seen
    expect(more).to_be_hidden()


def test_details_use_headings_and_runs_read_with_separators(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "a11y", canon("09:00"))
    _mock_runs(page, [_fake_run(28, "failed", "The run took longer than 15 minutes.")])
    _open_tab(page, base, agent)
    row = _row(page, "a11y")
    row.locator('[data-testid="routine-details-toggle"]').click()
    expect(row.locator('[data-testid="routine-recent-run"]')).to_have_count(1, timeout=8000)
    # "Prompt" and "Recent runs" are headings under the section's h3.
    heads = row.locator('[data-testid="routine-details"] h4')
    assert heads.all_text_contents() == ["Prompt", "Recent runs"]
    assert page.locator('[data-testid="routines-section"] h3').count() >= 1
    # when / how / outcome are separated for a screen reader.
    seps = row.locator('[data-testid="routine-recent-run"] .visually-hidden')
    assert seps.all_text_contents() == [", ", ", "]
    # The prompt is a styled block (the app's code block), not bare text.
    prompt = row.locator('[data-testid="routine-details-prompt"]')
    assert prompt.evaluate("(e) => getComputedStyle(e).borderTopWidth") == "1px"
    assert prompt.evaluate("(e) => e.classList.contains('code-block')")
    # The last-run reason is not left only in a tooltip.
    assert row.locator('[data-testid="routine-last"]').get_attribute("title") is None


def test_each_run_is_one_aligned_line_with_the_link_at_the_end(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "tidy", canon("09:00"))
    _mock_runs(
        page,
        [
            _fake_run(28, "ok", session_id="s28", chat_exists=True),
            _fake_run(27, "failed", "The run took longer than 15 minutes.", trigger_kind="manual"),
            _fake_run(26, "ok", session_id="s26", chat_exists=False),
        ],
    )
    _open_tab(page, base, agent)
    row = _row(page, "tidy")
    row.locator('[data-testid="routine-details-toggle"]').click()
    lines = row.locator('[data-testid="routine-recent-run"]')
    expect(lines).to_have_count(3, timeout=8000)
    boxes = lines.evaluate_all(
        """(els) => els.map((li) => {
          const r = (s) => { const n = li.querySelector(s); return n ? n.getBoundingClientRect() : null; };
          const out = r('.routine-recent-outcome'), how = r('.routine-recent-how'),
                chat = r('.routine-recent-chat > *'), line = li.getBoundingClientRect();
          return {howX: how.left, outX: out.left, outTop: out.top, outBottom: out.bottom,
                  chatTop: chat ? chat.top : null, chatRight: chat ? chat.right : null,
                  lineRight: line.right, height: line.height};
        })"""
    )
    # Columns align across runs, and a run with a link keeps it on the outcome's line at the end.
    assert len({round(b["howX"]) for b in boxes}) == 1, boxes
    assert len({round(b["outX"]) for b in boxes}) == 1, boxes
    for b in (boxes[0], boxes[2]):
        assert b["chatTop"] is not None
        assert b["outTop"] - 2 <= b["chatTop"] <= b["outBottom"], b
        assert b["lineRight"] - b["chatRight"] < 2, b
    assert boxes[0]["height"] < 45, boxes[0]
    # The prompt block and the run list share one left edge (Show more is offset to match).
    prompt_left = row.locator('[data-testid="routine-details-prompt"]').evaluate(
        "(e) => e.getBoundingClientRect().left"
    )
    list_left = row.locator('[data-testid="routine-recent-runs"]').evaluate(
        "(e) => e.getBoundingClientRect().left"
    )
    assert abs(prompt_left - list_left) < 1


def test_run_now_conflict_shows_inline_message(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _set_delay(base, app_with_agent.provider_id, 4000)
    rid = _create(base, agent, "busy", canon("09:00"))["id"]
    _open_tab(page, base, agent)
    row = _row(page, "busy")
    # Start a run behind the tab's back, then click Run now before the next refresh.
    r = httpx.post(
        f"{base}/api/agents/{agent}/routines/{rid}/run", headers=auth_headers_for(base), timeout=5
    )
    assert r.status_code == 202
    # Click only once the run is observably in progress (a run row with no outcome yet).
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        runs = _runs(base, agent, rid)
        if any(x.get("outcome") == "running" for x in runs):
            break
        page.wait_for_timeout(100)
    else:
        raise AssertionError("the started run never became observable as in progress")
    _item(row, "routine-run-now").click()
    expect(row.locator('[data-testid="routine-error"]')).to_have_text(
        "This routine is already running.", timeout=8000
    )
    expect(row.locator('[data-testid="routine-last"]')).to_have_text("Running…", timeout=8000)
    expect(row.locator('[data-testid="routine-last"]')).to_have_text(
        re.compile(r"^Ran "), timeout=20000
    )


def test_details_disclosure_is_keyboard_operable_and_named(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "paged", canon("09:00"))
    _open_tab(page, base, agent)
    row = _row(page, "paged")
    toggle = row.locator('[data-testid="routine-details-toggle"]')
    details = row.locator('[data-testid="routine-details"]')
    expect(details).to_be_hidden()
    assert toggle.get_attribute("aria-expanded") == "false"
    assert toggle.get_attribute("aria-controls") == details.get_attribute("id")
    toggle.focus()
    page.keyboard.press("Enter")
    expect(details).to_be_visible()
    assert toggle.get_attribute("aria-expanded") == "true"
    expect(row.get_by_text("No runs yet.")).to_be_visible(timeout=8000)
    page.keyboard.press("Space")
    expect(details).to_be_hidden()
    assert toggle.get_attribute("aria-expanded") == "false"
    # The switch and the actions button are named for the routine.
    assert (
        row.locator('[data-testid="routine-toggle"]').get_attribute("aria-label") == "Enable paged"
    )
    assert (
        row.locator('[data-testid="routine-actions"]').get_attribute("aria-label")
        == "Actions for paged"
    )


def test_leaving_the_tab_or_area_stops_polling(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _set_delay(base, app_with_agent.provider_id, 12000)
    rid = _create(base, agent, "slow", canon("09:00"))["id"]
    reqs: list[str] = []
    page.on(
        "request",
        lambda r: reqs.append(r.url) if r.url.endswith(f"/{agent}/routines") else None,
    )
    _open_tab(page, base, agent)
    row = _row(page, "slow")
    expect(row).to_be_visible(timeout=8000)
    httpx.post(
        f"{base}/api/agents/{agent}/routines/{rid}/run", headers=auth_headers_for(base), timeout=5
    )
    _item(row, "routine-run-now").click()  # 409 or fresh start: polling starts
    expect(row.locator('[data-testid="routine-last"]')).to_have_text("Running…", timeout=8000)
    # It polls while the tab is shown.
    before = len(reqs)
    _wait_more(page, reqs, before)
    # Leaving to another tab stops it.
    page.locator('[data-testid="tab-general"]').click()
    page.wait_for_timeout(400)
    stopped = len(reqs)
    page.wait_for_timeout(4500)
    assert len(reqs) == stopped, reqs
    # Coming back refetches once and resumes while the run goes on.
    page.locator('[data-testid="tab-routines"]').click()
    _wait_more(page, reqs, stopped, 8000)
    # Leaving the area (to Settings) stops it again.
    _nav.set_route(page, "settings/appearance")
    page.wait_for_timeout(500)
    left = len(reqs)
    page.wait_for_timeout(4500)
    assert len(reqs) == left, reqs


def test_rename_remount_on_the_tab_still_works(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "kept", canon("09:00"))
    _open_tab(page, base, agent)
    expect(_row(page, "kept")).to_be_visible(timeout=8000)
    r = httpx.get(f"{base}/api/agents/{agent}", headers=auth_headers_for(base), timeout=5)
    body = r.json()
    body["name"] = agent + "-renamed"
    put = httpx.put(
        f"{base}/api/agents/{agent}", json=body, headers=auth_headers_for(base), timeout=5
    )
    assert put.status_code == 200, put.text
    _nav.goto(page, base, f"agents/{_nav.seg(agent + '-renamed')}/routines")
    expect(_row(page, "kept")).to_be_visible(timeout=8000)


def test_time_zone_change_repaints_times_without_a_refetch(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "zoned", IN_3_DAYS)
    reqs: list[str] = []
    page.on(
        "request",
        lambda r: reqs.append(r.url) if r.url.endswith(f"/{agent}/routines") else None,
    )
    _open_tab(page, base, agent)
    # The schedule sentence is the server's (`schedule_text`); the next-run line is the browser's
    # and follows the operator zone without a refetch.
    nxt = _row(page, "zoned").locator('[data-testid="routine-next"]')
    expect(nxt).to_be_visible(timeout=8000)
    before = nxt.inner_text()
    page.evaluate("() => App.time.setZone('Pacific/Kiritimati')")
    expect(nxt).not_to_have_text(before, timeout=5000)
    assert len(reqs) == 1, reqs
