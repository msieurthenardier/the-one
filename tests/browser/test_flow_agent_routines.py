"""The agent editor's Routines tab, list half (M33 F1 L8; flight DD12, DD9).

The tab (between Tools and Self-configuration) lists an agent's routines with schedule,
target, next run and last outcome; each row has a switch, Run now, Delete and a History
disclosure. It loads lazily, polls only while a run is going, and saves every action at once.
The create/edit form is covered by ``test_flow_agent_routines_form.py`` (leg 9). Falls in the
``agent-tabs`` lane via the
``test_flow_agent_routines*`` glob.
"""

from __future__ import annotations

import re

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_session
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

ROWS = '[data-testid="routine-row"]'


def _create(base: str, agent: str, name: str, schedule: dict, target: dict | None = None) -> dict:
    r = httpx.post(
        f"{base}/api/agents/{agent}/routines",
        json={
            "name": name,
            "prompt": "Say hello.",
            "schedule": schedule,
            "target": target or {"kind": "new"},
        },
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


def test_form_buttons_show_for_a_named_agent(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "nightly", {"kind": "daily", "time": "09:00"})
    _open_tab(page, base, agent)
    expect(_row(page, "nightly")).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="routines-new-btn"]')).to_be_visible()
    expect(page.locator('[data-testid="routine-edit"]')).to_be_visible()
    expect(page.locator('[data-testid="routines-empty-new-btn"]')).to_have_count(0)


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
    _create(base, agent, "lazy", {"kind": "daily", "time": "09:00"})
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
    _create(base, agent, "once-only", {"kind": "daily", "time": "09:00"})
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
    sid = seed_session(base, agent, "Planning chat", "2026-10-01T10:00:00+00:00")
    _create(base, agent, "b-daily", {"kind": "daily", "time": "09:00"})
    _create(base, agent, "a-week", {"kind": "weekly", "days": [0, 2, 4], "time": "19:30"})
    _create(base, agent, "c-int", {"kind": "interval", "hours": 2}, {"kind": "own"})
    _create(
        base,
        agent,
        "d-days",
        {"kind": "weekdays", "time": "08:15"},
        {"kind": "chat", "session_id": sid},
    )
    _create(base, agent, "e-once", {"kind": "once", "in": {"amount": 3, "unit": "days"}})
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
    expect(_row(page, "b-daily").locator('[data-testid="routine-target"]')).to_have_text(
        "New chat each run"
    )
    expect(_row(page, "c-int").locator('[data-testid="routine-schedule"]')).to_have_text(
        re.compile(r"^Every 2 hours from \w{3} \d{1,2} at \d{1,2}:\d{2} (AM|PM)$")
    )
    expect(_row(page, "c-int").locator('[data-testid="routine-target"]')).to_have_text(
        "Its own chat"
    )
    expect(_row(page, "d-days").locator('[data-testid="routine-schedule"]')).to_have_text(
        "Every weekday at 8:15 AM"
    )
    expect(_row(page, "d-days").locator('[data-testid="routine-target"]')).to_have_text(
        "Planning chat"
    )
    expect(_row(page, "e-once").locator('[data-testid="routine-schedule"]')).to_have_text(
        re.compile(r"^Once, on \w{3}, \w{3} \d{1,2}, \d{4} at \d{1,2}:\d{2} (AM|PM)$")
    )
    expect(_row(page, "b-daily").locator('[data-testid="routine-next"]')).to_have_text(
        re.compile(r"^Next \w{3} \d{1,2}:\d{2} (AM|PM)$")
    )
    expect(_row(page, "b-daily").locator('[data-testid="routine-last"]')).to_have_text(
        "Not run yet"
    )


def test_describe_helpers_precedence_and_outcomes(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    out = page.evaluate(
        """() => {
          const d = App.studio.routinesDescribe;
          const now = new Date().toISOString();
          return {
            running: d.describeNext({running: true, finished_at: now, enabled: false}),
            done: d.describeNext({finished_at: now, enabled: false}),
            off: d.describeNext({enabled: false, next_run_at: now}),
            gone: d.describeTarget({kind: 'chat', missing: true}),
            ok: d.outcomeStatus({outcome: 'ok', finished_at: now}),
            failed: d.outcomeStatus({outcome: 'failed', finished_at: now, reason: 'boom'}),
            missed: d.outcomeStatus({outcome: 'missed', reason: 'App was closed'}),
            stopped: d.outcomeStatus({outcome: 'stopped', finished_at: now}),
            none: d.outcomeStatus(null),
            run: d.outcomeStatus({outcome: 'ok'}, true),
            schedule: typeof d.describeSchedule,
          };
        }"""
    )
    assert out["running"] == "Running"
    assert out["done"] == "Done"
    assert out["off"] == "Off"
    assert out["gone"] == "Chat gone, a new one starts on the next run"
    assert out["ok"]["state"] == "success" and out["ok"]["label"].startswith("Ran ")
    assert out["failed"]["state"] == "danger" and out["failed"]["label"].endswith(": boom")
    assert out["missed"] == {"state": "warning", "label": "Missed: App was closed"}
    assert out["stopped"]["state"] == "idle"
    assert out["none"] == {"state": "idle", "label": "Not run yet"}
    assert out["run"] == {"state": "pending", "label": "Running"}
    assert out["schedule"] == "undefined"  # the server words schedules


def test_toggle_saves_and_row_goes_off(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "flip", {"kind": "daily", "time": "09:00"})
    _open_tab(page, base, agent)
    row = _row(page, "flip")
    toggle = row.locator('[data-testid="routine-toggle"]')
    expect(toggle).to_be_checked(timeout=8000)
    assert toggle.get_attribute("aria-label") == "Run flip on schedule"
    toggle.click(force=True)
    expect(row.locator('[data-testid="routine-next"]')).to_have_text("Off", timeout=8000)
    expect(toggle).not_to_be_checked()
    assert _list(base, agent)[0]["enabled"] is False
    toggle.click(force=True)
    expect(row.locator('[data-testid="routine-next"]')).to_have_text(
        re.compile(r"^Next "), timeout=8000
    )


def test_delete_arms_then_removes_and_shows_empty(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "gone", {"kind": "daily", "time": "09:00"})
    _open_tab(page, base, agent)
    row = _row(page, "gone")
    delete = row.locator('[data-testid="routine-delete"]')
    delete.click()
    expect(delete).to_have_class(re.compile("confirm-delete"))
    assert len(_list(base, agent)) == 1
    delete.click()
    expect(page.locator(ROWS)).to_have_count(0, timeout=8000)
    expect(page.locator('[data-testid="routines-empty"]')).to_be_visible()
    assert _list(base, agent) == []


def test_delete_moves_focus_to_the_neighbour_toggle(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "aaa", {"kind": "daily", "time": "09:00"})
    _create(base, agent, "bbb", {"kind": "daily", "time": "10:00"})
    _open_tab(page, base, agent)
    delete = _row(page, "aaa").locator('[data-testid="routine-delete"]')
    delete.click()
    delete.click()
    expect(page.locator(ROWS)).to_have_count(1, timeout=8000)
    expect(_row(page, "bbb").locator('[data-testid="routine-toggle"]')).to_be_focused()


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
    _create(base, agent, "manual", {"kind": "daily", "time": "09:00"})
    _open_tab(page, base, agent)
    row = _row(page, "manual")
    run = row.locator('[data-testid="routine-run-now"]')
    expect(run).to_be_enabled(timeout=8000)
    run.click()
    expect(row.locator('[data-testid="routine-last"]')).to_have_text("Running", timeout=8000)
    # Focus stays in the row (not the body) and the start is announced once.
    expect(run).to_be_disabled()
    assert page.evaluate("document.activeElement !== document.body")
    assert row.evaluate("(r) => r.contains(document.activeElement)")
    expect(page.locator('[data-testid="routines-live"]')).to_have_text("Started manual")
    expect(row.locator('[data-testid="routine-next"]')).to_have_text("Running")
    expect(run).to_be_disabled()
    expect(row.locator('[data-testid="routine-last"]')).to_have_text(
        re.compile(r"^Ran "), timeout=20000
    )
    expect(row.locator('[data-testid="routine-next"]')).to_have_text(re.compile(r"^Next "))
    expect(run).to_be_enabled()
    expect(page.locator('[data-testid="routines-live"]')).to_have_text(re.compile(r"^manual: Ran "))
    # The History disclosure shows the manual run.
    row.locator('[data-testid="routine-history"] summary').click()
    entry = row.locator('[data-testid="routine-run"]')
    expect(entry).to_have_count(1, timeout=8000)
    expect(entry.first).to_contain_text("Run now")
    expect(entry.first).to_contain_text("New chat")
    expect(row.locator('[data-testid="routine-history-more"]')).to_be_hidden()


def test_run_now_conflict_shows_inline_message(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _set_delay(base, app_with_agent.provider_id, 4000)
    rid = _create(base, agent, "busy", {"kind": "daily", "time": "09:00"})["id"]
    _open_tab(page, base, agent)
    row = _row(page, "busy")
    # Start a run behind the tab's back, then click Run now before the next refresh.
    r = httpx.post(
        f"{base}/api/agents/{agent}/routines/{rid}/run", headers=auth_headers_for(base), timeout=5
    )
    assert r.status_code == 202
    run = row.locator('[data-testid="routine-run-now"]')
    run.click()
    expect(row.locator('[data-testid="routine-error"]')).to_have_text(
        "This routine is already running.", timeout=8000
    )
    expect(row.locator('[data-testid="routine-last"]')).to_have_text("Running", timeout=8000)
    expect(row.locator('[data-testid="routine-last"]')).to_have_text(
        re.compile(r"^Ran "), timeout=20000
    )


def test_history_empty_state(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "paged", {"kind": "daily", "time": "09:00"})
    _open_tab(page, base, agent)
    row = _row(page, "paged")
    row.locator('[data-testid="routine-history"] summary').click()
    expect(row.locator('[data-testid="routine-history-empty"]')).to_be_visible(timeout=8000)


def test_leaving_the_tab_or_area_stops_polling(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _set_delay(base, app_with_agent.provider_id, 12000)
    rid = _create(base, agent, "slow", {"kind": "daily", "time": "09:00"})["id"]
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
    row.locator('[data-testid="routine-run-now"]').click()  # 409 or fresh start: polling starts
    expect(row.locator('[data-testid="routine-last"]')).to_have_text("Running", timeout=8000)
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
    _create(base, agent, "kept", {"kind": "daily", "time": "09:00"})
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
    _create(base, agent, "zoned", {"kind": "once", "in": {"amount": 3, "unit": "days"}})
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


def test_default_agent_shows_the_named_agent_notice(app_with_agent: SeededApp, page: Page) -> None:
    base = app_with_agent.base_url
    r = httpx.post(
        f"{base}/api/agents",
        json={
            "name": "default",
            "provider_config_id": app_with_agent.provider_id,
            "llm_model": "mock-default",
            "system_prompt": "x",
        },
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code in (200, 201), r.text
    reqs: list[str] = []
    page.on(
        "request",
        lambda r: (
            reqs.append(r.url)
            if "/api/" in r.url and "/routines" in r.url and "/self-configuration/" not in r.url
            else None
        ),
    )
    _nav.goto(page, base, "agents/default/routines")
    expect(page.locator('[data-testid="routines-default-agent"]')).to_have_text(
        "Routines need a named agent.", timeout=8000
    )
    assert reqs == []
