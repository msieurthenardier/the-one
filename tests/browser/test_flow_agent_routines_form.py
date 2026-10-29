# ruff: noqa: E501  (inline JS snippets and long locator lines are kept verbatim)
"""The Routines tab's create/edit form (M33 F1 L9; flight DD12, DD2, DD9).

One inline form covers the name, the prompt, all five schedule kinds and the three target
kinds, with a searchable chooser for an existing chat. Falls in the ``agent-tabs`` lane via the
``test_flow_agent_routines*`` glob.
"""

from __future__ import annotations

import json

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_session
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

FORM = '[data-testid="routine-form"]'


def _tid(page: Page, tid: str):
    return page.locator(f'[data-testid="{tid}"]')


def _list(base: str, agent: str) -> list[dict]:
    r = httpx.get(f"{base}/api/agents/{agent}/routines", headers=auth_headers_for(base), timeout=5)
    assert r.status_code == 200, r.text
    return r.json()["routines"]


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


def _open_tab(page: Page, base: str, agent: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(agent)}/routines")
    expect(_tid(page, "routines-section")).to_be_visible(timeout=8000)


def _row(page: Page, name: str):
    return page.locator(
        '[data-testid="routine-row"]',
        has=page.locator('[data-testid="routine-name"]', has_text=name),
    )


def _new_form(page: Page) -> None:
    btn = _tid(page, "routines-new-btn")
    expect(btn).to_be_visible(timeout=8000)
    btn.click()
    expect(page.locator(FORM)).to_be_visible()
    expect(_tid(page, "routine-form-name")).to_be_focused()


def _fill(page: Page, name: str, prompt: str = "Say hi.") -> None:
    _tid(page, "routine-form-name").fill(name)
    _tid(page, "routine-form-prompt").fill(prompt)


def _kind(page: Page, label: str) -> None:
    page.locator(FORM).get_by_role("radio", name=label, exact=True).check()


def _save(page: Page) -> None:
    _tid(page, "routine-form-save").click()


# ── schedule kinds, create ────────────────────────────────────────────────


def test_create_daily_with_new_chat_target(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Morning")
    _kind(page, "Daily")
    _tid(page, "routine-form-hour").select_option("7")
    _tid(page, "routine-form-minute").select_option("30")
    _tid(page, "routine-form-ampm").select_option("PM")
    _save(page)
    row = _row(page, "Morning")
    expect(row).to_be_visible(timeout=8000)
    expect(row.locator('[data-testid="routine-schedule"]')).to_have_text("Daily at 7:30 PM")
    expect(row.locator('[data-testid="routine-target"]')).to_have_text("New chat each run")
    expect(page.locator(FORM)).to_have_count(0)
    expect(row.locator('[data-testid="routine-edit"]')).to_be_focused()
    stored = _list(base, agent)[0]
    assert stored["schedule"] == {"kind": "daily", "time": "19:30"}
    assert stored["prompt"] == "Say hi."


def test_create_weekdays_and_own_chat(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Weekday")
    _kind(page, "Weekdays")
    page.locator(FORM).get_by_role("radio", name="Its own chat").check()
    _save(page)
    row = _row(page, "Weekday")
    expect(row.locator('[data-testid="routine-schedule"]')).to_have_text(
        "Weekdays at 9:00 AM", timeout=8000
    )
    expect(row.locator('[data-testid="routine-target"]')).to_have_text("Its own chat")


def test_weekly_days_use_monday_zero_numbering(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Weekly")
    _kind(page, "Weekly")
    # No day yet: the client blocks the save.
    _save(page)
    expect(_tid(page, "routine-form-schedule-error")).to_have_text("Pick at least one day.")
    expect(_tid(page, "routine-form-day-0")).to_be_focused()
    assert _list(base, agent) == []
    _tid(page, "routine-form-day-6").check()
    _tid(page, "routine-form-day-0").check()
    _save(page)
    row = _row(page, "Weekly")
    expect(row.locator('[data-testid="routine-schedule"]')).to_have_text(
        "Mon, Sun at 9:00 AM", timeout=8000
    )
    assert _list(base, agent)[0]["schedule"] == {"kind": "weekly", "days": [0, 6], "time": "09:00"}


def test_create_interval(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Often")
    _kind(page, "Every N hours")
    _tid(page, "routine-form-interval").fill("3")
    _save(page)
    row = _row(page, "Often")
    expect(row.locator('[data-testid="routine-schedule"]')).to_have_text(
        "Every 3 hours", timeout=8000
    )


def test_create_once_in_and_at(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Soon")
    _kind(page, "Once")
    _tid(page, "routine-form-in-amount").fill("2")
    _tid(page, "routine-form-in-unit").select_option("days")
    _save(page)
    expect(_row(page, "Soon").locator('[data-testid="routine-schedule"]')).to_contain_text(
        "Once,", timeout=8000
    )
    # "At": tomorrow 9:00 AM, converted on the server.
    _new_form(page)
    _fill(page, "Later")
    _kind(page, "Once")
    page.locator(FORM).get_by_role("radio", name="At", exact=True).check()
    _tid(page, "routine-form-at-day").select_option(index=1)
    _tid(page, "routine-form-at-hour").select_option("9")
    _tid(page, "routine-form-at-minute").select_option("0")
    _tid(page, "routine-form-at-ampm").select_option("AM")
    _save(page)
    row = _row(page, "Later")
    expect(row.locator('[data-testid="routine-schedule"]')).to_contain_text(
        "at 9:00 AM", timeout=8000
    )
    stored = {r["name"]: r for r in _list(base, agent)}
    assert stored["Later"]["schedule"]["kind"] == "once"
    assert stored["Soon"]["schedule"]["kind"] == "once"


def test_at_in_the_past_is_blocked_before_sending(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Past")
    _kind(page, "Once")
    page.locator(FORM).get_by_role("radio", name="At", exact=True).check()
    _tid(page, "routine-form-at-day").select_option(index=0)
    _tid(page, "routine-form-at-hour").select_option("12")
    _tid(page, "routine-form-at-minute").select_option("0")
    _tid(page, "routine-form-at-ampm").select_option("AM")
    posts: list[str] = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    _save(page)
    expect(_tid(page, "routine-form-schedule-error")).to_have_text("That time has already passed.")
    assert [u for u in posts if "/routines" in u] == []
    expect(page.locator(FORM)).to_be_visible()


# ── target: the chat chooser ──────────────────────────────────────────────


def test_chat_chooser_filters_picks_and_returns_focus(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    sid_a = seed_session(base, agent, "Alpha plans", "2026-10-01T10:00:00Z")
    seed_session(base, agent, "Beta notes", "2026-10-02T10:00:00Z", platform="discord")
    seed_session(base, None, "Not mine", "2026-10-03T10:00:00Z")
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Chatty")
    page.locator(FORM).get_by_role("radio", name="A chat").check()
    expect(_tid(page, "routine-form-chat")).to_have_text("No chat chosen.")
    # Saving without a chat is blocked on the Run in group.
    _save(page)
    expect(_tid(page, "routine-form-target-error")).to_have_text("Pick a chat.")
    _tid(page, "routine-target-picker").click()
    chooser = _tid(page, "routine-chat-chooser")
    expect(chooser).to_be_visible()
    opts = _tid(page, "routine-chat-option")
    expect(opts).to_have_count(2)
    expect(opts.first).to_contain_text("Beta notes")  # newest first
    expect(opts.first).to_contain_text("Discord")
    _tid(page, "routine-chat-search").fill("alpha")
    expect(opts).to_have_count(1)
    _tid(page, "routine-chat-search").fill("disc")
    expect(opts).to_have_count(1)
    expect(opts.first).to_contain_text("Beta notes")
    _tid(page, "routine-chat-search").fill("alpha")
    page.keyboard.press("Enter")
    expect(chooser).to_have_count(0)
    expect(_tid(page, "routine-target-picker")).to_be_focused()
    expect(_tid(page, "routine-form-chat")).to_have_text("Alpha plans")
    # The choice is part of the button's accessible name (visible text comes first).
    expect(_tid(page, "routine-target-picker")).to_have_attribute(
        "aria-label", "Choose chat, current: Alpha plans"
    )
    _save(page)
    row = _row(page, "Chatty")
    expect(row.locator('[data-testid="routine-target"]')).to_have_text("Alpha plans", timeout=8000)
    assert _list(base, agent)[0]["target"]["session_id"] == sid_a


def test_chat_chooser_escape_and_empty_line(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    page.locator(FORM).get_by_role("radio", name="A chat").check()
    _tid(page, "routine-target-picker").click()
    expect(_tid(page, "routine-chat-chooser")).to_contain_text("This agent has no chats yet.")
    page.keyboard.press("Escape")
    expect(_tid(page, "routine-chat-chooser")).to_have_count(0)
    expect(_tid(page, "routine-target-picker")).to_be_focused()
    expect(_tid(page, "routine-form-chat")).to_have_text("No chat chosen.")


def test_chat_chooser_load_failure(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    page.locator(FORM).get_by_role("radio", name="A chat").check()
    page.route("**/api/chat/sessions", lambda route: route.fulfill(status=500, body="boom"))
    _tid(page, "routine-target-picker").click()
    expect(_tid(page, "routine-chat-chooser")).to_contain_text("Couldn’t load chats.")


# ── edit ──────────────────────────────────────────────────────────────────


def test_edit_prefills_and_sends_only_what_changed(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    made = _create(base, agent, "Nightly", {"kind": "daily", "time": "21:15"})
    _open_tab(page, base, agent)
    _row(page, "Nightly").locator('[data-testid="routine-edit"]').click()
    expect(_tid(page, "routine-form-name")).to_have_value("Nightly")
    expect(_tid(page, "routine-form-prompt")).to_have_value("Say hello.")
    expect(_tid(page, "routine-form-hour")).to_have_value("9")
    expect(_tid(page, "routine-form-minute")).to_have_value("15")  # the routine's own minute
    expect(_tid(page, "routine-form-ampm")).to_have_value("PM")
    bodies: list[dict] = []
    page.on(
        "request",
        lambda r: (
            bodies.append(json.loads(r.post_data))
            if r.method == "PUT" and "/routines/" in r.url
            else None
        ),
    )
    # change then revert the schedule: untouched
    _tid(page, "routine-form-hour").select_option("10")
    _tid(page, "routine-form-hour").select_option("9")
    _tid(page, "routine-form-name").fill("Nightly 2")
    _save(page)
    expect(_row(page, "Nightly 2")).to_be_visible(timeout=8000)
    assert bodies == [{"name": "Nightly 2"}]
    assert _list(base, agent)[0]["id"] == made["id"]
    # Cancel returns focus to the opener and discards text.
    edit = _row(page, "Nightly 2").locator('[data-testid="routine-edit"]')
    edit.click()
    _tid(page, "routine-form-name").fill("scribble")
    _tid(page, "routine-form-cancel").click()
    expect(page.locator(FORM)).to_have_count(0)
    expect(edit).to_be_focused()
    expect(_row(page, "Nightly 2")).to_be_visible()


def test_edit_changes_kind_and_target(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "Flip", {"kind": "daily", "time": "09:00"})
    _open_tab(page, base, agent)
    _row(page, "Flip").locator('[data-testid="routine-edit"]').click()
    _kind(page, "Every N hours")
    _tid(page, "routine-form-interval").fill("12")
    page.locator(FORM).get_by_role("radio", name="Its own chat").check()
    bodies: list[dict] = []
    page.on(
        "request",
        lambda r: (
            bodies.append(json.loads(r.post_data))
            if r.method == "PUT" and "/routines/" in r.url
            else None
        ),
    )
    _save(page)
    expect(_row(page, "Flip").locator('[data-testid="routine-schedule"]')).to_have_text(
        "Every 12 hours", timeout=8000
    )
    assert bodies == [{"schedule": {"kind": "interval", "hours": 12}, "target": {"kind": "own"}}]


def test_edit_of_a_one_off_prefills_at_and_omits_the_untouched_schedule(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    made = _create(base, agent, "Once", {"kind": "once", "in": {"amount": 1, "unit": "days"}})
    _open_tab(page, base, agent)
    _row(page, "Once").locator('[data-testid="routine-edit"]').click()
    expect(_tid(page, "routine-form-at-day")).to_be_visible()
    _tid(page, "routine-form-prompt").fill("Changed prompt")
    bodies: list[dict] = []
    page.on(
        "request",
        lambda r: (
            bodies.append(json.loads(r.post_data))
            if r.method == "PUT" and "/routines/" in r.url
            else None
        ),
    )
    _save(page)
    expect(page.locator(FORM)).to_have_count(0, timeout=8000)
    assert bodies == [{"prompt": "Changed prompt"}]
    assert _list(base, agent)[0]["id"] == made["id"]


# ── errors ────────────────────────────────────────────────────────────────


def test_duplicate_name_is_shown_on_the_name_field(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "Taken", {"kind": "daily", "time": "09:00"})
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "taken")
    _save(page)
    group = page.locator(FORM).locator(".field-group", has=_tid(page, "routine-form-name"))
    expect(group.locator(".field-error")).to_be_visible(timeout=8000)
    expect(page.locator(FORM)).to_be_visible()


def test_empty_name_and_prompt_show_on_their_fields(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _save(page)
    form = page.locator(FORM)
    expect(form.locator(".field-error").first).to_be_visible()
    assert form.locator(".field-error:visible").count() == 2
    assert _list(base, agent) == []


def test_server_schedule_error_lands_on_the_schedule_group(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Far")
    _kind(page, "Once")
    _tid(page, "routine-form-in-amount").fill("400")
    _tid(page, "routine-form-in-unit").select_option("days")
    _save(page)
    expect(_tid(page, "routine-form-schedule-error")).to_have_text(
        "That time is more than a year away.", timeout=8000
    )


def test_deleted_chat_error_lands_on_the_target_group(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    sid = seed_session(base, agent, "Doomed", "2026-10-01T10:00:00Z")
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Gone")
    page.locator(FORM).get_by_role("radio", name="A chat").check()
    _tid(page, "routine-target-picker").click()
    _tid(page, "routine-chat-option").first.click()
    httpx.delete(f"{base}/api/chat/sessions/{sid}", headers=auth_headers_for(base), timeout=5)
    _save(page)
    expect(_tid(page, "routine-form-target-error")).to_have_text(
        "That chat doesn't exist.", timeout=8000
    )


def test_unsaved_form_is_discarded_when_the_tab_is_left(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Draft")
    _tid(page, "tab-tools").click()
    _tid(page, "tab-routines").click()
    expect(page.locator(FORM)).to_have_count(0)
    _new_form(page)
    expect(_tid(page, "routine-form-name")).to_have_value("")


# ── the pure model, through page.evaluate ─────────────────────────────────


def test_form_model_body_rules(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    out = page.evaluate(
        """() => {
          const M = App.studio.routinesFormModel;
          const today = {year: 2026, month: 9, day: 28, weekday: 3, hour: 10, minute: 0};
          const base = M.defaultState(today);
          const st = (o) => Object.assign({}, base, o);
          const res = {};
          res.daily = M.formToBody(st({name: ' N ', prompt: ' p ', kind: 'daily', hour: 12, ampm: 'AM'}), {mode: 'create'});
          res.pm = M.scheduleBody(st({kind: 'weekdays', hour: 12, minute: 5, ampm: 'PM'}));
          res.weekly = M.scheduleBody(st({kind: 'weekly', days: [6, 0], hour: 1, ampm: 'PM'}));
          res.in = M.scheduleBody(st({kind: 'once', onceMode: 'in', inAmount: '5', inUnit: 'minutes'}));
          res.on = M.scheduleBody(st({kind: 'once', onceMode: 'at', atDay: '2026-11-02', atHour: 9, atMinute: 0, atAmpm: 'AM'}));
          // only the active kind's keys
          res.interval = M.scheduleBody(st({kind: 'interval', interval: '4', days: [1], inAmount: 3}));
          const row = {name: 'R', prompt: 'p', schedule: {kind: 'once', at: '2024-01-05T17:00:00+00:00'},
                       target: {kind: 'chat', session_id: 's1', title: 'T'}};
          const init = M.bodyToFormState(row, (d) => ({year: 2024, month: 0, day: 5, hour: 9, minute: 7}), today);
          res.initial = init;
          res.untouched = M.formToBody(init, {mode: 'edit', initial: init});
          res.opts = M.dayOptions(today, init.atDay).map((o) => o.value);
          res.mins = M.hourMinuteOptions(7).minutes.map((o) => o.value);
          res.touchedOnce = M.formToBody(st(Object.assign({}, init, {atMinute: 10})), {mode: 'edit', initial: init});
          return res;
        }"""
    )
    assert out["daily"] == {
        "name": "N",
        "prompt": "p",
        "schedule": {"kind": "daily", "time": "00:00"},
        "target": {"kind": "new"},
    }
    assert out["pm"] == {"kind": "weekdays", "time": "12:05"}
    assert out["weekly"] == {"kind": "weekly", "days": [0, 6], "time": "13:00"}
    assert out["in"] == {"kind": "once", "in": {"amount": 5, "unit": "minutes"}}
    assert out["on"] == {"kind": "once", "on": {"date": "2026-11-02", "time": "09:00"}}
    assert out["interval"] == {"kind": "interval", "hours": 4}
    assert out["initial"]["onceMode"] == "at" and out["initial"]["atDay"] == "2024-01-05"
    assert (out["initial"]["atHour"], out["initial"]["atMinute"], out["initial"]["atAmpm"]) == (
        9,
        7,
        "AM",
    )
    assert out["initial"]["chatId"] == "s1" and out["initial"]["targetKind"] == "chat"
    assert out["untouched"] == {}
    assert len(out["opts"]) == 61 and out["opts"][0] == "2024-01-05"  # the routine's own past date
    assert out["opts"][1] == "2026-10-28"
    assert 7 in out["mins"] and out["mins"][:3] == [0, 5, 7]
    assert out["touchedOnce"] == {
        "schedule": {"kind": "once", "on": {"date": "2024-01-05", "time": "09:10"}}
    }
