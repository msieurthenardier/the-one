# ruff: noqa: E501  (inline JS snippets and long locator lines are kept verbatim)
"""The Routines tab's create/edit form on the calendar recurrence (M33 F1 L9; M33 F3 L7, DD7).

One inline form covers the name, the prompt, a start date and time, the Repeat presets and the
Custom recurrence dialog with its server preview. Every run starts a new chat, so the form has
no target. In edit mode Save is disabled until something changes. Falls in the
``agent-routines`` lane via the ``test_flow_agent_routines*`` glob.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_agent_routine, seed_mock_agent, seed_mock_provider
from browser.seeders import canonical_schedule as canon
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

FORM = '[data-testid="routine-form"]'
DIALOG = '[data-testid="routine-custom"]'


def _tid(page: Page, tid: str):
    return page.locator(f'[data-testid="{tid}"]')


def _list(base: str, agent: str) -> list[dict]:
    r = httpx.get(f"{base}/api/agents/{agent}/routines", headers=auth_headers_for(base), timeout=5)
    assert r.status_code == 200, r.text
    return r.json()["routines"]


def _create(base: str, agent: str, name: str, schedule: dict) -> dict:
    r = httpx.post(
        f"{base}/api/agents/{agent}/routines",
        json={"name": name, "prompt": "Say hello.", "schedule": schedule},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _sched(
    time: str = "09:00",
    day: str = "2026-01-01",
    repeat: dict | None = None,
    ends: dict | None = None,
) -> dict:
    """A canonical schedule whose start date is in the past, so edits are deterministic."""
    return {
        "start": {"date": day, "time": time},
        "repeat": repeat,
        "ends": ends or {"kind": "never"},
    }


def _daily(time: str, date_: str = "2026-01-01") -> dict:
    return _sched(time, date_, {"every": 1, "unit": "day"})


def _open_tab(page: Page, base: str, agent: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(agent)}/routines")
    expect(_tid(page, "routines-section")).to_be_visible(timeout=8000)


def _row(page: Page, name: str):
    return page.locator(
        '[data-testid="routine-row"]',
        has=page.locator('[data-testid="routine-name"]', has_text=name),
    )


def _edit(page: Page, name: str) -> None:
    """Open a row's actions menu and choose Edit."""
    row = _row(page, name)
    row.locator('[data-testid="routine-actions"]').click()
    row.locator('[data-testid="routine-edit"]').click()


def _new_form(page: Page) -> None:
    btn = _tid(page, "routines-new-btn")
    expect(btn).to_be_visible(timeout=8000)
    btn.click()
    expect(page.locator(FORM)).to_be_visible()
    expect(_tid(page, "routine-form-name")).to_be_focused()


def _fill(page: Page, name: str, prompt: str = "Say hi.") -> None:
    _tid(page, "routine-form-name").fill(name)
    _tid(page, "routine-form-prompt").fill(prompt)


def _save(page: Page) -> None:
    _tid(page, "routine-form-save").click()


def _shown(d: date) -> str:
    return f"{d.strftime('%a, %b')} {d.day}, {d.year}"


def _set_start(page: Page, d: date, time: str = "9:00 AM") -> None:
    """Type the start date and time, then leave each field so it commits."""
    dt = _tid(page, "routine-form-start-date-input")
    dt.fill(d.isoformat())
    dt.press("Tab")
    expect(dt).to_have_value(_shown(d))
    tm = _tid(page, "routine-form-start-time-input")
    tm.fill(time)
    tm.press("Tab")


def _future(day: int, min_ahead: int = 4) -> date:
    """The next date, at least ``min_ahead`` days out, whose day of the month is ``day``."""
    d = date.today() + timedelta(days=min_ahead)
    while d.day != day:
        d += timedelta(days=1)
    return d


def _selected_repeat_text(page: Page) -> str:
    return page.evaluate(
        """() => { const s = document.querySelector('[data-testid="routine-form-repeat"]');
                   return s.options[s.selectedIndex].textContent; }"""
    )


def _repeat_labels(page: Page) -> list[str]:
    return page.evaluate(
        """() => Array.from(document.querySelector('[data-testid="routine-form-repeat"]').options)
                      .map((o) => o.textContent)"""
    )


def _custom(page: Page, unit: str, every: str | None = None) -> None:
    """Open the Custom recurrence dialog and set the unit and the number."""
    _tid(page, "routine-form-repeat").select_option("custom")
    expect(page.locator(DIALOG)).to_be_visible()
    _tid(page, "routine-custom-unit").select_option(unit)
    if every is not None:
        _tid(page, "routine-custom-every").fill(every)


def _done(page: Page) -> None:
    _tid(page, "routine-custom-done").click()
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(_tid(page, "routine-form-repeat")).to_be_focused()


def _put_bodies(page: Page) -> list[dict]:
    bodies: list[dict] = []
    page.on(
        "request",
        lambda r: (
            bodies.append(json.loads(r.post_data))
            if r.method == "PUT" and "/routines/" in r.url
            else None
        ),
    )
    return bodies


# ── create: each Repeat preset ────────────────────────────────────────────

REPEAT = {
    "none": None,
    "day": {"every": 1, "unit": "day"},
    "weekday": {"every": 1, "unit": "week", "days": [0, 1, 2, 3, 4]},
    "monthday": {"every": 1, "unit": "month", "month_by": {"by": "day"}},
    "monthnth": {"every": 1, "unit": "month", "month_by": {"by": "weekday", "nth": 2}},
    "monthlast": {"every": 1, "unit": "month", "month_by": {"by": "weekday", "nth": -1}},
    "annual": {"every": 1, "unit": "year"},
}


def test_each_preset_saves_the_canonical_schedule_it_means(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    cases = [
        ("none", 10),
        ("day", 10),
        ("weekday", 10),
        ("weekly", 10),
        ("monthday", 10),
        ("monthnth", 10),  # day 10 is the second weekday of its month
        ("monthlast", 25),  # day 25 is always in the month's last 7 days
        ("annual", 10),
    ]
    for key, day in cases:
        d = _future(day)
        _new_form(page)
        _fill(page, f"P-{key}")
        _set_start(page, d, "9:30 AM")
        _tid(page, "routine-form-repeat").select_option(key)
        expect(_tid(page, "routine-form-preview")).to_contain_text("9:30 AM")
        _save(page)
        row = _row(page, f"P-{key}")
        expect(row).to_be_visible(timeout=8000)
        expect(page.locator(FORM)).to_have_count(0)
        stored = {r["name"]: r for r in _list(base, agent)}[f"P-{key}"]
        repeat = REPEAT.get(key)
        if key == "weekly":
            repeat = {"every": 1, "unit": "week", "days": [d.weekday()]}
        assert stored["schedule"] == {
            "start": {"date": d.isoformat(), "time": "09:30"},
            "repeat": repeat,
            "ends": {"kind": "never"},
        }, key
        expect(row.locator('[data-testid="routine-schedule"]')).to_have_text(
            stored["schedule_text"]
        )
        expect(row.locator('[data-testid="routine-next"]')).to_have_text(
            re.compile(r"\d{1,2}:\d{2} (AM|PM)$")
        )


def test_the_preset_list_follows_the_start_date(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    second = _future(10)
    _set_start(page, second)
    wd = second.strftime("%A")
    labels = _repeat_labels(page)
    assert labels == [
        "Does not repeat",
        "Every day",
        "Every weekday (Monday to Friday)",
        f"Weekly on {wd}",
        "Monthly on day 10",
        f"Monthly on the second {wd}",
        f"Annually on {second.strftime('%B')} 10",
        "Custom…",
    ]
    # The final 7 days of a month offer "last" and, past the 28th, no nth.
    last = _future(25)
    _set_start(page, last)
    labels = _repeat_labels(page)
    assert f"Monthly on the last {last.strftime('%A')}" in labels
    assert not any("second" in x for x in labels) and "Monthly on day 25" in labels
    # A chosen preset keeps its meaning when the date moves.
    _tid(page, "routine-form-repeat").select_option("weekly")
    moved = last + timedelta(days=1)
    _set_start(page, moved)
    assert _selected_repeat_text(page) == f"Weekly on {moved.strftime('%A')}"
    # A preset that stops applying falls back within its family.
    _tid(page, "routine-form-repeat").select_option("monthlast")
    fifth = _future(31)  # the 31st is the fifth weekday: no "nth", but still "last"
    _set_start(page, fifth)
    assert _selected_repeat_text(page) == f"Monthly on the last {fifth.strftime('%A')}"
    _set_start(page, _future(10))
    _tid(page, "routine-form-repeat").select_option("monthnth")
    _set_start(page, _future(29))  # 29th: the fifth weekday and (Feb aside) not "last"
    assert _selected_repeat_text(page).startswith("Monthly on ")


# ── the Custom recurrence dialog ──────────────────────────────────────────


def test_custom_recurrence_each_unit_round_trips_to_the_form(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Custom")
    d = _future(10)
    _set_start(page, d)
    preview = _tid(page, "routine-form-preview")
    # minutes, hours, days
    _custom(page, "minute", "90")
    _done(page)
    expect(preview).to_contain_text("Every 90 minutes", timeout=8000)
    assert _selected_repeat_text(page).startswith("Every 90 minutes")
    _custom(page, "hour", "3")
    _done(page)
    expect(preview).to_contain_text("Every 3 hours", timeout=8000)
    _custom(page, "day", "2")
    _done(page)
    expect(preview).to_contain_text("Every 2 days", timeout=8000)
    # weeks, with days: the start's weekday is preselected, Sunday-first toggles
    _tid(page, "routine-form-repeat").select_option("custom")
    _tid(page, "routine-custom-unit").select_option("week")
    expect(_tid(page, "routine-custom-day-%d" % d.weekday())).to_be_checked()
    _tid(page, "routine-custom-every").fill("2")
    _tid(page, "routine-custom-day-1").check()
    _tid(page, "routine-custom-day-3").check()
    _tid(page, "routine-custom-day-%d" % d.weekday()).set_checked(d.weekday() in (1, 3))
    _done(page)
    expect(preview).to_contain_text("Every 2 weeks on Tue, Thu", timeout=8000)
    # months, by day and by weekday
    _custom(page, "month", "2")
    expect(_tid(page, "routine-custom-month-by")).to_be_visible()
    expect(page.get_by_role("group", name="Repeat on day of month")).to_have_count(1)
    expect(page.get_by_role("group", name="Repeat on", exact=True)).to_have_count(0)
    _done(page)
    expect(preview).to_contain_text("Every 2 months on day 10", timeout=8000)
    _custom(page, "month", "3")
    _tid(page, "routine-custom-month-by").get_by_role(
        "radio", name="On the second", exact=False
    ).check()
    _done(page)
    expect(preview).to_contain_text("Every 3 months on the second", timeout=8000)
    # years
    _custom(page, "year", "2")
    _done(page)
    expect(preview).to_contain_text("Every 2 years on", timeout=8000)
    _save(page)
    row = _row(page, "Custom")
    expect(row).to_be_visible(timeout=8000)
    stored = _list(base, agent)[0]["schedule"]
    assert stored["repeat"] == {"every": 2, "unit": "year"}
    assert stored["start"] == {"date": d.isoformat(), "time": "09:00"}


def test_custom_week_and_month_values_are_stored(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    d = _future(10)
    _new_form(page)
    _fill(page, "Weeks")
    _set_start(page, d)
    _tid(page, "routine-form-repeat").select_option("custom")
    _tid(page, "routine-custom-unit").select_option("week")
    _tid(page, "routine-custom-every").fill("2")
    for i in range(7):
        _tid(page, f"routine-custom-day-{i}").set_checked(i in (1, 6))  # Tue, Sun
    _done(page)
    _save(page)
    expect(_row(page, "Weeks")).to_be_visible(timeout=8000)
    stored = {r["name"]: r for r in _list(base, agent)}["Weeks"]["schedule"]
    assert stored["repeat"] == {"every": 2, "unit": "week", "days": [1, 6]}  # Monday = 0


@pytest.mark.parametrize(
    ("ends", "sentence", "want"),
    [
        ("on", "until", {"kind": "on"}),
        ("after", "5 times", {"kind": "after", "count": 5}),
    ],
)
def test_custom_ends_choices(
    app_with_agent: SeededApp, page: Page, ends: str, sentence: str, want: dict
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    d = _future(10)
    _new_form(page)
    _fill(page, "Ends")
    _set_start(page, d)
    _custom(page, "day", "1")
    group = _tid(page, "routine-custom-ends")
    group.get_by_role("radio", name="On" if ends == "on" else "After", exact=True).check()
    last = d + timedelta(days=9)
    if ends == "on":
        field = _tid(page, "routine-custom-ends-date-input")
        field.fill(last.isoformat())
        field.press("Tab")
        want = {**want, "date": last.isoformat()}
    else:
        _tid(page, "routine-custom-ends-count").fill("5")
    _done(page)
    expect(_tid(page, "routine-form-preview")).to_contain_text(sentence, timeout=8000)
    expect(_tid(page, "routine-form-preview")).to_contain_text("Last:")
    _save(page)
    expect(_row(page, "Ends")).to_be_visible(timeout=8000)
    assert _list(base, agent)[0]["schedule"]["ends"] == want


def test_custom_ends_after_defaults_to_seven_occurrences(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _set_start(page, _future(10))
    _custom(page, "day", "1")
    group = _tid(page, "routine-custom-ends")
    group.get_by_role("radio", name="After", exact=True).check()
    expect(_tid(page, "routine-custom-ends-count")).to_have_value("7")


def test_custom_cancel_discards_and_reopens_with_the_current_recurrence(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    d = _future(10)
    _set_start(page, d)
    _custom(page, "minute", "5")
    _tid(page, "routine-custom-cancel").click()
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(_tid(page, "routine-form-repeat")).to_be_focused()
    assert _selected_repeat_text(page) == "Does not repeat"
    # Apply a weekly recurrence, switch to a preset, and reopen: the dialog shows the
    # recurrence the form holds (every day), not defaults.
    _custom(page, "week", "2")
    _done(page)
    expect(_tid(page, "routine-form-preview")).to_contain_text("Every 2 weeks", timeout=8000)
    assert _selected_repeat_text(page).startswith("Every 2 weeks")
    _tid(page, "routine-form-repeat").select_option("day")
    _tid(page, "routine-form-repeat").select_option("custom")
    expect(_tid(page, "routine-custom-unit")).to_have_value("day")
    expect(_tid(page, "routine-custom-every")).to_have_value("1")
    _tid(page, "routine-custom-cancel").click()
    assert _selected_repeat_text(page) == "Every day"
    # Escape also discards
    _tid(page, "routine-form-repeat").select_option("custom")
    page.keyboard.press("Escape")
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(_tid(page, "routine-form-repeat")).to_be_focused()


def test_custom_validates_its_ranges_with_field_errors(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    d = _future(10)
    _set_start(page, d)
    _custom(page, "minute", "1440")
    _tid(page, "routine-custom-done").click()
    expect(_tid(page, "routine-custom-every-error")).to_have_text(
        "Repeat every must be a whole number from 1 to 1439."
    )
    expect(page.locator(DIALOG)).to_be_visible()
    _tid(page, "routine-custom-unit").select_option("year")
    _tid(page, "routine-custom-every").fill("11")
    _tid(page, "routine-custom-done").click()
    expect(_tid(page, "routine-custom-every-error")).to_have_text(
        "Repeat every must be a whole number from 1 to 10."
    )
    _tid(page, "routine-custom-every").fill("0")
    _tid(page, "routine-custom-done").click()
    expect(_tid(page, "routine-custom-every-error")).to_be_visible()
    _tid(page, "routine-custom-unit").select_option("week")
    _tid(page, "routine-custom-every").fill("1")
    _tid(page, "routine-custom-day-%d" % d.weekday()).uncheck()
    _tid(page, "routine-custom-done").click()
    expect(_tid(page, "routine-custom-days-error")).to_have_text("Pick at least one day.")
    _tid(page, "routine-custom-day-0").check()
    _tid(page, "routine-custom-ends").get_by_role("radio", name="After", exact=True).check()
    _tid(page, "routine-custom-ends-count").fill("1001")
    _tid(page, "routine-custom-done").click()
    expect(_tid(page, "routine-custom-ends-error")).to_contain_text("from 1 to 1000")
    _tid(page, "routine-custom-ends-count").fill("0")
    _tid(page, "routine-custom-done").click()
    expect(_tid(page, "routine-custom-ends-error")).to_be_visible()
    _tid(page, "routine-custom-ends").get_by_role("radio", name="On", exact=True).check()
    before = _tid(page, "routine-custom-ends-date-input")
    before.fill((d - timedelta(days=1)).isoformat())
    before.press("Tab")
    _tid(page, "routine-custom-done").click()
    expect(_tid(page, "routine-custom-ends-error")).to_be_visible()
    expect(page.locator(DIALOG)).to_be_visible()
    # nothing was applied to the form
    _tid(page, "routine-custom-cancel").click()
    assert _selected_repeat_text(page) == "Does not repeat"


def test_escape_with_the_ends_calendar_open_closes_only_the_calendar(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _set_start(page, _future(10))
    _custom(page, "day", "1")
    _tid(page, "routine-custom-ends").get_by_role("radio", name="On", exact=True).check()
    _tid(page, "routine-custom-ends-date-button").click()
    cal = _tid(page, "routine-custom-ends-date-calendar")
    expect(cal).to_be_visible()
    # The start field's picker is independent: its calendar is not open.
    expect(_tid(page, "routine-form-start-date-calendar")).to_be_hidden()
    page.keyboard.press("Escape")
    expect(cal).to_be_hidden()
    expect(page.locator(DIALOG)).to_be_visible()
    _tid(page, "routine-custom-ends-date-button").focus()
    page.keyboard.press("Escape")
    expect(page.locator(DIALOG)).to_have_count(0)
    expect(_tid(page, "routine-form-repeat")).to_be_focused()


# ── the preview line ──────────────────────────────────────────────────────


def test_preview_shows_sentence_next_and_last_and_updates(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    d = _future(10)
    _set_start(page, d, "7:15 AM")
    preview = _tid(page, "routine-form-preview")
    expect(preview).to_contain_text("Once, on", timeout=8000)
    expect(preview).to_contain_text("Next: ")
    expect(preview).to_contain_text("at 7:15 AM")
    expect(preview).not_to_contain_text("Last:")
    assert preview.get_attribute("role") == "status"
    _tid(page, "routine-form-repeat").select_option("day")
    expect(preview).to_contain_text("Every day at 7:15 AM", timeout=8000)
    _custom(page, "day", "1")
    _tid(page, "routine-custom-ends").get_by_role("radio", name="After", exact=True).check()
    _tid(page, "routine-custom-ends-count").fill("3")
    _done(page)
    last = d + timedelta(days=2)
    expect(preview).to_contain_text(
        f"Last: {last.strftime('%b')} {last.day}, {last.year}", timeout=8000
    )


def test_preview_refusal_is_the_schedule_error(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Gone")
    _set_start(page, date.today(), "12:00 AM")  # earlier today: a one-off with no runs left
    error = _tid(page, "routine-form-schedule-error")
    expect(error).to_have_text("This schedule has no runs left.", timeout=8000)
    expect(_tid(page, "routine-form-preview")).to_be_hidden()
    _save(page)
    expect(error).to_have_text("This schedule has no runs left.", timeout=8000)
    assert _list(base, agent) == []
    # The error is tied to the control it concerns (WCAG 3.3.1).
    repeat = _tid(page, "routine-form-repeat")
    expect(repeat).to_have_attribute("aria-invalid", "true")
    error_id = error.get_attribute("id")
    assert error_id and error_id in (repeat.get_attribute("aria-describedby") or "").split()
    # Moving to a repeating schedule clears it.
    _tid(page, "routine-form-repeat").select_option("day")
    expect(error).to_be_hidden(timeout=8000)
    expect(repeat).not_to_have_attribute("aria-invalid", "true")
    assert error_id not in (repeat.get_attribute("aria-describedby") or "").split()
    expect(_tid(page, "routine-form-preview")).to_contain_text("Every day", timeout=8000)


def test_month_day_warning_is_a_hint_described_by_the_repeat_select(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _set_start(page, _future(31))
    _tid(page, "routine-form-repeat").select_option("monthday")
    hint = _tid(page, "routine-form-schedule-hint")
    expect(hint).to_contain_text("Some months have fewer than 31 days", timeout=8000)
    hint_id = hint.get_attribute("id")
    assert (
        hint_id
        and hint_id
        in (_tid(page, "routine-form-repeat").get_attribute("aria-describedby") or "").split()
    )
    _tid(page, "routine-form-repeat").select_option("day")
    expect(hint).to_have_count(0, timeout=8000)


def test_the_latest_preview_response_wins(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    held: list = []

    def handler(route):
        if not held:
            held.append(route)  # the first preview is held back
        else:
            route.continue_()

    page.route("**/routines/preview", handler)
    _open_tab(page, base, agent)
    _new_form(page)
    page.wait_for_timeout(800)
    assert len(held) == 1
    _tid(page, "routine-form-repeat").select_option("day")
    preview = _tid(page, "routine-form-preview")
    expect(preview).to_contain_text("Every day", timeout=8000)
    held[0].fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps(
            {
                "schedule": {},
                "text": "STALE TEXT",
                "next_runs": [],
                "last_occurrence": None,
                "warnings": [],
            }
        ),
    )
    page.wait_for_timeout(500)
    expect(preview).to_contain_text("Every day")
    expect(preview).not_to_contain_text("STALE TEXT")


# ── starts: the quick "in" start and the operator zone ────────────────────


def _expected_parts(page: Page, offset_minutes: int) -> tuple[str, str]:
    return page.evaluate(
        """(off) => {
          const p = App.time.parts(new Date(Date.now() + off * 60000));
          const M = App.studio.routinesFormModel;
          return [M.isoOf(p.year, p.month, p.day), ('0' + p.hour).slice(-2) + ':' + ('0' + p.minute).slice(-2)];
        }""",
        offset_minutes,
    )


def test_in_quick_start_sets_the_start_fields(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Soon")
    expect(page.get_by_label("Start in, amount")).to_have_count(1)
    expect(page.get_by_label("Start in, unit")).to_have_count(1)
    _tid(page, "routine-form-start-in").check()
    _tid(page, "routine-form-in-amount").fill("2")
    _tid(page, "routine-form-in-unit").select_option("days")
    got = page.evaluate(
        """() => [document.querySelector('[data-testid="routine-form-start-date-input"]').value,
                  document.querySelector('[data-testid="routine-form-start-time-input"]').value]"""
    )
    day, time = _expected_parts(page, 2 * 24 * 60)
    want = datetime.fromisoformat(day)
    assert got[0] == _shown(want.date())
    # rounded up to the next minute: the hour:minute is within one minute of now + 2 days
    h, m = (int(x) for x in time.split(":"))
    shown = datetime.strptime(got[1], "%I:%M %p")
    delta = abs((shown.hour * 60 + shown.minute) - (h * 60 + m))
    assert delta in (0, 1, 1439, 1438)
    _save(page)
    row = _row(page, "Soon")
    expect(row.locator('[data-testid="routine-schedule"]')).to_contain_text("Once,", timeout=8000)
    stored = _list(base, agent)[0]["schedule"]
    assert stored["start"]["date"] == day and stored["repeat"] is None


def test_the_pickers_today_follows_the_operator_zone(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    # Whichever of these two zones is not on the host's date, the picker uses the zone's.
    zone = "Pacific/Kiritimati"
    if datetime.now(ZoneInfo(zone)).date() == date.today():
        zone = "Pacific/Pago_Pago"
    assert datetime.now(ZoneInfo(zone)).date() != date.today()
    r = httpx.put(
        f"{base}/api/time-settings",
        json={"mode": "zone", "zone": zone},
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 200, r.text
    today = datetime.now(ZoneInfo(zone)).date()
    _open_tab(page, base, agent)
    _new_form(page)
    _tid(page, "routine-form-start-date-button").click()
    expect(_tid(page, "routine-form-start-date-calendar")).to_be_visible()
    today_btn = _tid(page, "routine-form-start-date-calendar").locator('[aria-current="date"]')
    expect(today_btn).to_have_attribute("data-date", today.isoformat())
    page.keyboard.press("Escape")
    # The default start is the next whole hour in the zone.
    nxt = datetime.now(ZoneInfo(zone)).replace(minute=0, second=0, microsecond=0) + timedelta(
        hours=1
    )
    expect(_tid(page, "routine-form-start-date-input")).to_have_value(_shown(nxt.date()))


def test_a_start_time_in_the_spring_forward_gap_runs_at_the_end_of_the_gap(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    zone = ZoneInfo("America/New_York")
    d = datetime.now(zone).date() + timedelta(days=1)
    for _ in range(366):
        t = datetime(d.year, d.month, d.day, 2, 30, tzinfo=zone)
        if t.astimezone(ZoneInfo("UTC")).astimezone(zone).hour != 2:
            break
        d += timedelta(days=1)
    else:
        pytest.skip("no spring-forward gap within the start limit")
    httpx.put(
        f"{base}/api/time-settings",
        json={"mode": "zone", "zone": "America/New_York"},
        headers=auth_headers_for(base),
        timeout=5,
    ).raise_for_status()
    _open_tab(page, base, agent)
    _new_form(page)
    _set_start(page, d, "2:30 AM")
    preview = _tid(page, "routine-form-preview")
    expect(preview).to_contain_text("Next: ", timeout=8000)
    expect(preview).to_contain_text("at 3:00 AM")
    # the form keeps the typed time
    expect(_tid(page, "routine-form-start-time-input")).to_have_value("2:30 AM")


# ── no target: every run starts a new chat ────────────────────────────────


def test_the_form_has_no_target_and_create_never_sends_one(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    form = page.locator(FORM)
    # The only radios are the Starts choice (no target choice).
    expect(form.get_by_role("radio")).to_have_count(3)
    expect(form.get_by_role("radio", name="Immediately")).to_have_count(1)
    expect(form).not_to_contain_text(re.compile(r"runs? in\b|choose chat|own chat", re.I))
    posts: list[dict] = []
    page.on(
        "request",
        lambda r: (
            posts.append(json.loads(r.post_data))
            if r.method == "POST" and r.url.endswith(f"/{agent}/routines")
            else None
        ),
    )
    _fill(page, "No target")
    _save(page)
    expect(_row(page, "No target")).to_be_visible(timeout=8000)
    assert len(posts) == 1 and set(posts[0]) == {"name", "prompt", "schedule"}, posts


def test_save_in_edit_mode_is_disabled_until_a_field_changes(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "Steady", _daily("09:00"))
    _open_tab(page, base, agent)
    _edit(page, "Steady")
    save = _tid(page, "routine-form-save")
    expect(save).to_be_disabled()
    # A name change enables it; reverting disables it again.
    name = _tid(page, "routine-form-name")
    name.fill("Steady 2")
    expect(save).to_be_enabled()
    name.fill("Steady")
    expect(save).to_be_disabled()
    # The prompt, the Repeat select and the start time each enable it and revert alike.
    prompt = _tid(page, "routine-form-prompt")
    prompt.fill("Say hello twice.")
    expect(save).to_be_enabled()
    prompt.fill("Say hello.")
    expect(save).to_be_disabled()
    repeat = _tid(page, "routine-form-repeat")
    repeat.select_option("weekday")
    expect(save).to_be_enabled()
    repeat.select_option("day")
    expect(save).to_be_disabled()
    tm = _tid(page, "routine-form-start-time-input")
    tm.fill("10:00 AM")
    tm.press("Tab")
    expect(save).to_be_enabled()
    tm.fill("9:00 AM")
    tm.press("Tab")
    expect(save).to_be_disabled()
    # Create mode is not gated.
    _tid(page, "routine-form-cancel").click()
    _new_form(page)
    expect(_tid(page, "routine-form-save")).to_be_enabled()


def test_edit_replaces_the_card_in_place_and_cancel_and_save_restore_it(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "aaa", _daily("08:00"))
    _create(base, agent, "bbb", _daily("09:00"))
    _create(base, agent, "ccc", _daily("10:00"))
    _open_tab(page, base, agent)
    names = _tid(page, "routine-name")
    expect(names).to_have_count(3, timeout=8000)
    row = _row(page, "bbb")
    _edit(page, "bbb")
    form = page.locator(FORM)
    expect(form).to_be_visible()
    # The form sits where the card was (between aaa and ccc, not in the top host), and the card
    # with its menu is not reachable while it is edited.
    slot = page.locator('[role="listitem"]').nth(1)
    expect(slot.locator(FORM)).to_have_count(1)
    expect(page.locator(".routines-form-host " + FORM)).to_have_count(0)
    expect(row).to_be_hidden()
    expect(row.locator('[data-testid="routine-actions"]')).to_be_hidden()
    # A second Edit (or New) while one is open only focuses the open form.
    _edit(page, "aaa")
    expect(form).to_have_count(1)
    expect(_row(page, "aaa")).to_be_visible()
    expect(_tid(page, "routine-form-name")).to_be_focused()
    # Cancel: the same card is back in the same place, focus on its actions button.
    _tid(page, "routine-form-cancel").click()
    expect(form).to_have_count(0)
    expect(row).to_be_visible()
    expect(row.locator('[data-testid="routine-actions"]')).to_be_focused()
    assert names.all_text_contents() == ["aaa", "bbb", "ccc"]
    # Save: the card returns in place with the new name, focus on its actions button.
    _edit(page, "bbb")
    _tid(page, "routine-form-name").fill("bbb2")
    _tid(page, "routine-form-save").click()
    expect(form).to_have_count(0, timeout=8000)
    expect(names).to_have_text(["aaa", "bbb2", "ccc"], timeout=8000)
    expect(_row(page, "bbb2").locator('[data-testid="routine-actions"]')).to_be_focused()


def test_focus_moves_to_cancel_when_a_revert_disables_the_focused_save(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "Steady", _daily("09:00"))
    _open_tab(page, base, agent)
    _edit(page, "Steady")
    save = _tid(page, "routine-form-save")
    name = _tid(page, "routine-form-name")
    name.fill("Steady 2")
    expect(save).to_be_enabled()
    save.focus()
    expect(save).to_be_focused()
    # Revert the name behind the focus (as an undo or a script would): Save disables itself.
    name.evaluate(
        "(el) => { el.value = 'Steady'; el.dispatchEvent(new Event('input', {bubbles: true})); }"
    )
    expect(save).to_be_disabled()
    expect(_tid(page, "routine-form-cancel")).to_be_focused()


def test_a_flagged_routines_save_is_enabled_and_sends_the_prompt(
    app_with_data_dir: tuple[str, Path], page: Page
) -> None:
    base, data_dir = app_with_data_dir
    agent = seed_mock_agent(base, seed_mock_provider(base))
    seed_agent_routine(data_dir, agent, "Flagged", untrusted=True, sources=["web_fetch"])
    _open_tab(page, base, agent)
    _edit(page, "Flagged")
    save = _tid(page, "routine-form-save")
    expect(save).to_be_enabled()
    bodies = _put_bodies(page)
    save.click()
    expect(page.locator(FORM)).to_have_count(0, timeout=8000)
    assert len(bodies) == 1 and set(bodies[0]) == {"prompt"}, bodies


# ── edit ──────────────────────────────────────────────────────────────────

EDIT_CASES = [
    # (name, schedule, selected option text starts with / equals)
    ("E-day", _daily("21:15"), "Every day"),
    (
        "E-weekday",
        _sched("09:00", repeat={"every": 1, "unit": "week", "days": [0, 1, 2, 3, 4]}),
        "Every weekday (Monday to Friday)",
    ),
    ("E-minutes", _sched("09:00", repeat={"every": 90, "unit": "minute"}), "Every 90 minutes"),
    ("E-hours", _sched("09:00", repeat={"every": 3, "unit": "hour"}), "Every 3 hours"),
    ("E-two-days", _sched("09:00", repeat={"every": 2, "unit": "day"}), "Every 2 days at 9:00 AM"),
    (
        "E-weeks",
        _sched("09:00", repeat={"every": 2, "unit": "week", "days": [1, 3]}),
        "Every 2 weeks on Tue, Thu",
    ),
    (
        "E-months",
        _sched("09:00", repeat={"every": 2, "unit": "month", "month_by": {"by": "day"}}),
        "Every 2 months on day 1",
    ),
    (
        "E-monthnth",
        _sched(
            "09:00",
            "2026-01-12",
            repeat={"every": 1, "unit": "month", "month_by": {"by": "weekday", "nth": 2}},
        ),
        "Monthly on the second Monday",
    ),
    ("E-years", _sched("09:00", repeat={"every": 2, "unit": "year"}), "Every 2 years on January 1"),
    (
        "E-ends",
        _sched(
            "09:00",
            (date.today() + timedelta(days=2)).isoformat(),  # an end needs runs left
            repeat={"every": 1, "unit": "day"},
            ends={"kind": "after", "count": 4},
        ),
        "Every day at 9:00 AM, 4 times",
    ),
]


def test_edit_shows_the_start_and_the_preset_or_the_sentence_of_every_unit(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    for name, sched, _ in EDIT_CASES:
        _create(base, agent, name, sched)
    stored = {r["name"]: r for r in _list(base, agent)}
    _open_tab(page, base, agent)
    for name, sched, want in EDIT_CASES:
        _edit(page, name)
        expect(_tid(page, "routine-form-name")).to_have_value(name)
        start = date.fromisoformat(stored[name]["schedule"]["start"]["date"])
        expect(_tid(page, "routine-form-start-date-input")).to_have_value(_shown(start))
        text = _selected_repeat_text(page)
        if want.startswith(("Every 90", "Every 3 hours")):
            # An instant-anchored unit: the sentence carries "from {date}"
            assert text.startswith(want), (name, text)
        elif want in (
            "Every day",
            "Every weekday (Monday to Friday)",
            "Monthly on the second Monday",
        ):
            assert text == want, (name, text)
        else:
            assert text.startswith(want) and text == stored[name]["schedule_text"], (name, text)
        labels = _repeat_labels(page)
        if text not in (
            "Every day",
            "Every weekday (Monday to Friday)",
            "Monthly on the second Monday",
        ):
            # The extra option sits above "Custom…".
            assert labels[-2] == text and labels[-1] == "Custom…", (name, labels)
        _tid(page, "routine-form-cancel").click()
        expect(page.locator(FORM)).to_have_count(0)


def test_edit_sends_only_what_changed(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    made = _create(base, agent, "Nightly", _daily("21:15"))
    _open_tab(page, base, agent)
    _edit(page, "Nightly")
    expect(_tid(page, "routine-form-name")).to_have_value("Nightly")
    expect(_tid(page, "routine-form-prompt")).to_have_value("Say hello.")
    expect(_tid(page, "routine-form-start-time-input")).to_have_value("9:15 PM")
    bodies = _put_bodies(page)
    # change then revert the schedule: untouched
    _tid(page, "routine-form-repeat").select_option("weekday")
    _tid(page, "routine-form-repeat").select_option("day")
    t = _tid(page, "routine-form-start-time-input")
    t.fill("10:00 PM")
    t.press("Tab")
    t.fill("9:15 PM")
    t.press("Tab")
    _tid(page, "routine-form-name").fill("Nightly 2")
    _save(page)
    expect(_row(page, "Nightly 2")).to_be_visible(timeout=8000)
    assert bodies == [{"name": "Nightly 2"}]
    assert _list(base, agent)[0]["id"] == made["id"]
    # Cancel returns focus to the opener and discards text.
    actions = _row(page, "Nightly 2").locator('[data-testid="routine-actions"]')
    _edit(page, "Nightly 2")
    _tid(page, "routine-form-name").fill("scribble")
    _tid(page, "routine-form-cancel").click()
    expect(page.locator(FORM)).to_have_count(0)
    expect(actions).to_be_focused()
    expect(_row(page, "Nightly 2")).to_be_visible()


def test_edit_changes_the_recurrence(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "Flip", _daily("09:00"))
    _open_tab(page, base, agent)
    _edit(page, "Flip")
    _custom(page, "hour", "12")
    _done(page)
    bodies = _put_bodies(page)
    _save(page)
    expect(_row(page, "Flip").locator('[data-testid="routine-schedule"]')).to_contain_text(
        "Every 12 hours from", timeout=8000
    )
    assert len(bodies) == 1 and set(bodies[0]) == {"schedule"}
    assert bodies[0]["schedule"]["repeat"] == {"every": 12, "unit": "hour"}
    assert bodies[0]["schedule"]["start"] == {"date": "2026-01-01", "time": "09:00"}


def test_a_schedule_the_old_form_could_not_express_is_editable(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "Alternate", _sched("09:00", repeat={"every": 2, "unit": "day"}))
    # a daily whose first run is tomorrow (a start still ahead) was read-only in the old form
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    _create(base, agent, "Ahead", _daily("09:00", tomorrow))
    _open_tab(page, base, agent)
    _edit(page, "Alternate")
    expect(_tid(page, "routine-form-repeat")).to_be_enabled()
    assert _selected_repeat_text(page) == "Every 2 days at 9:00 AM"
    bodies = _put_bodies(page)
    _tid(page, "routine-form-name").fill("Alternate 2")
    _save(page)
    expect(_row(page, "Alternate 2")).to_be_visible(timeout=8000)
    assert bodies == [{"name": "Alternate 2"}]
    assert {r["name"]: r for r in _list(base, agent)}["Alternate 2"]["schedule"]["repeat"] == {
        "every": 2,
        "unit": "day",
    }
    _edit(page, "Ahead")
    assert _selected_repeat_text(page) == "Every day"
    expect(_tid(page, "routine-form-start-date-input")).to_have_value(
        _shown(date.today() + timedelta(days=1))
    )
    _tid(page, "routine-form-repeat").select_option("weekday")
    _save(page)
    expect(_row(page, "Ahead").locator('[data-testid="routine-schedule"]')).to_contain_text(
        "Every weekday", timeout=8000
    )


def test_editing_a_one_off_into_the_past_shows_the_refusal_on_save(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "Once", {"start": {"in": {"amount": 1, "unit": "days"}}})
    _open_tab(page, base, agent)
    _edit(page, "Once")
    assert _selected_repeat_text(page) == "Does not repeat"
    _set_start(page, date.today(), "12:00 AM")
    _save(page)
    expect(_tid(page, "routine-form-schedule-error")).to_have_text(
        "This schedule has no runs left.", timeout=8000
    )
    expect(page.locator(FORM)).to_be_visible()
    # Untouched: a prompt-only change does not re-send the schedule.
    _row_before = _list(base, agent)[0]["schedule"]
    assert _row_before["repeat"] is None


# ── errors ────────────────────────────────────────────────────────────────


def test_duplicate_name_is_shown_on_the_name_field(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "Taken", canon("09:00"))
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


def test_server_schedule_error_lands_on_the_schedule_field(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Far")
    _set_start(page, date.today() + timedelta(days=400))
    error = _tid(page, "routine-form-schedule-error")
    expect(error).to_have_text("That time is more than a year away.", timeout=8000)
    _save(page)
    expect(error).to_have_text("That time is more than a year away.", timeout=8000)
    assert _list(base, agent) == []


def test_an_unreadable_start_blocks_the_save_on_its_field(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Typo")
    tm = _tid(page, "routine-form-start-time-input")
    tm.fill("banana")
    tm.press("Tab")
    expect(tm).to_have_attribute("aria-invalid", "true")
    posts: list[str] = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    _save(page)
    expect(_tid(page, "routine-form-schedule-error")).to_have_text(
        "Enter a start time like 9:30 AM."
    )
    expect(tm).to_be_focused()
    assert [u for u in posts if "/routines" in u and "/preview" not in u] == []


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


def test_form_model_rules(app_with_agent: SeededApp, page: Page) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    out = page.evaluate(
        """() => {
          const M = App.studio.routinesFormModel;
          const res = {};
          // calendar arithmetic and presets (2026-10-29 is a Thursday: the fifth, last week)
          res.weekday = ['2026-10-26', '2026-10-29', '2026-11-01'].map(M.weekdayMon0);
          res.nth = ['2026-10-01', '2026-10-07', '2026-10-08', '2026-10-29'].map(M.nthOf);
          res.last = ['2026-10-24', '2026-10-25', '2026-02-21', '2026-02-22'].map(M.isLastWeek);
          res.presets = M.presets('2026-10-14').map((o) => o.value + '=' + o.label);
          res.presets29 = M.presets('2026-10-29').map((o) => o.value);
          res.presetsFeb = M.presets('2026-02-22').map((o) => o.value);
          res.rep = {
            weekly: M.presetRepeat('weekly', '2026-11-01'),
            nth: M.presetRepeat('monthnth', '2026-10-14'),
            nthNone: M.presetRepeat('monthnth', '2026-10-29') === undefined,
            lastNone: M.presetRepeat('monthlast', '2026-10-14') === undefined,
            last: M.presetRepeat('monthlast', '2026-10-29'),
          };
          res.avail = [M.availableMode('monthnth', '2026-10-29'), M.availableMode('monthlast', '2026-10-14'),
                       M.availableMode('weekly', '2026-10-14'), M.availableMode('current', '2026-10-14')];
          res.match = [
            M.matchPreset(null, {kind: 'never'}, '2026-10-14'),
            M.matchPreset({every: 1, unit: 'week', days: [2]}, {kind: 'never'}, '2026-10-14'),
            M.matchPreset({every: 1, unit: 'week', days: [3]}, {kind: 'never'}, '2026-10-14'),
            M.matchPreset({every: 1, unit: 'day'}, {kind: 'after', count: 3}, '2026-10-14'),
            M.matchPreset({every: 2, unit: 'day'}, {kind: 'never'}, '2026-10-14'),
            M.matchPreset({every: 1, unit: 'month', month_by: {by: 'weekday', nth: 2}}, {kind: 'never'}, '2026-10-14'),
            M.matchPreset({every: 1, unit: 'month', month_by: {by: 'weekday', nth: 3}}, {kind: 'never'}, '2026-10-14'),
            M.matchPreset({unit: 'year', every: 1}, {kind: 'never'}, '2026-10-14'),
          ];
          res.monthBy = M.monthByOptions('2026-10-14').map((o) => o.value)
            .concat(M.monthByOptions('2026-10-29').map((o) => o.value))
            .concat(M.monthByOptions('2026-10-14', 'nth:3').map((o) => o.value));
          // starts
          const zp = (d) => { const u = new Date(d.getTime() + 330 * 60000);
            return {year: u.getUTCFullYear(), month: u.getUTCMonth(), day: u.getUTCDate(),
                    hour: u.getUTCHours(), minute: u.getUTCMinutes()}; };  // UTC+05:30
          const now = Date.UTC(2026, 9, 29, 20, 10, 20);   // 01:40:20 on Oct 30 in UTC+05:30
          res.defaultStart = M.defaultStart(now, zp);
          res.in = [M.startFromIn(now, 90, 'minutes', zp), M.startFromIn(now, 2, 'hours', zp),
                    M.startFromIn(now, 1, 'days', zp)];
          // state and body
          const st = M.defaultState(now, zp);
          res.state = [st.startDate, st.startTime, st.mode];
          res.createBody = M.formToBody(Object.assign({}, st, {name: ' N ', prompt: ' p ', mode: 'weekly'}), {mode: 'create'});
          const row = {name: 'R', prompt: 'p',
            schedule_text: 'Every 2 weeks on Tue, Thu at 9:00 AM',
            schedule: {start: {date: '2026-01-01', time: '09:00'},
                       repeat: {unit: 'week', every: 2, days: [3, 1]}, ends: {kind: 'never'}}};
          const init = M.bodyToFormState(row);
          res.initial = [init.mode, init.currentLabel, init.startTime, Object.keys(init).sort().join(',')];
          res.untouched = M.formToBody(JSON.parse(JSON.stringify(init)), {mode: 'edit', initial: init});
          res.touched = M.formToBody(Object.assign({}, init, {startTime: '10:30'}), {mode: 'edit', initial: init});
          res.toPreset = M.formToBody(Object.assign({}, init, {mode: 'day'}), {mode: 'edit', initial: init});
          res.flagged = M.formToBody(init, {mode: 'edit', initial: init, flagged: true});
          const one = M.bodyToFormState({name: 'O', prompt: 'p', schedule: {start: {date: '2026-11-02', time: '09:00'}, repeat: null, ends: {kind: 'never'}}});
          res.one = [one.mode, M.scheduleBody(one)];
          const ends = M.bodyToFormState({name: 'O', prompt: 'p', schedule: {start: {date: '2026-11-02', time: '09:00'}, repeat: {every: 1, unit: 'day'}, ends: {kind: 'on', date: '2026-12-01'}}});
          res.ends = [ends.mode, M.scheduleBody(ends).ends];
          // the dialog's rules
          const v = (o) => Object.assign({every: '2', unit: 'week', days: [1], endsKind: 'never', endsDate: null, endsCount: '5', monthBy: 'day'}, o);
          res.valid = [
            M.validateCustom(v({every: '0'}), '2026-10-14'),
            M.validateCustom(v({unit: 'minute', every: '1440'}), '2026-10-14'),
            M.validateCustom(v({unit: 'minute', every: '1439'}), '2026-10-14'),
            M.validateCustom(v({unit: 'month', every: '13'}), '2026-10-14'),
            M.validateCustom(v({days: []}), '2026-10-14'),
            M.validateCustom(v({endsKind: 'on', endsDate: '2026-10-13'}), '2026-10-14'),
            M.validateCustom(v({endsKind: 'on', endsDate: '2026-10-14'}), '2026-10-14'),
            M.validateCustom(v({endsKind: 'after', endsCount: '1001'}), '2026-10-14'),
            M.validateCustom(v({endsKind: 'after', endsCount: 'x'}), '2026-10-14'),
          ];
          res.value = [
            M.customToValue(v({days: [6, 1]})),
            M.customToValue(v({unit: 'month', monthBy: 'nth:-1', endsKind: 'after', endsCount: '3'})),
            M.customToValue(v({unit: 'day', endsKind: 'on', endsDate: '2026-12-01', days: [1]})),
          ];
          res.pre = [
            M.precheck(Object.assign({}, st, {name: 'n', prompt: 'p', startDate: null}), {mode: 'create'}, {}),
            M.precheck(Object.assign({}, st, {name: 'n', prompt: 'p', startTime: null}), {mode: 'create'}, {}),
          ];
          return res;
        }"""
    )
    assert out["weekday"] == [0, 3, 6]
    assert out["nth"] == [1, 1, 2, 5]
    assert out["last"] == [False, True, False, True]
    assert out["presets"] == [
        "none=Does not repeat",
        "day=Every day",
        "weekday=Every weekday (Monday to Friday)",
        "weekly=Weekly on Wednesday",
        "monthday=Monthly on day 14",
        "monthnth=Monthly on the second Wednesday",
        "annual=Annually on October 14",
    ]
    assert out["presets29"] == [
        "none",
        "day",
        "weekday",
        "weekly",
        "monthday",
        "monthlast",
        "annual",
    ]
    # Feb 22 (a 28-day month) is both the fourth weekday and in the last 7 days
    assert out["presetsFeb"] == [
        "none",
        "day",
        "weekday",
        "weekly",
        "monthday",
        "monthnth",
        "monthlast",
        "annual",
    ]
    assert out["rep"] == {
        "weekly": {"every": 1, "unit": "week", "days": [6]},
        "nth": {"every": 1, "unit": "month", "month_by": {"by": "weekday", "nth": 2}},
        "nthNone": True,
        "lastNone": True,
        "last": {"every": 1, "unit": "month", "month_by": {"by": "weekday", "nth": -1}},
    }
    assert out["avail"] == ["monthday", "monthday", "weekly", "current"]
    assert out["match"] == ["none", "weekly", None, None, None, "monthnth", None, "annual"]
    assert out["monthBy"] == ["day", "nth:2", "day", "nth:-1", "day", "nth:2", "nth:3"]
    # 20:10:20 UTC on Oct 29 is 01:40:20 on Oct 30 at +05:30: the next whole hour is 02:00
    assert out["defaultStart"] == {"date": "2026-10-30", "time": "02:00"}
    assert out["in"] == [
        {"date": "2026-10-30", "time": "03:11"},  # 90 minutes, rounded up from :20 to the minute
        {"date": "2026-10-30", "time": "03:41"},
        {"date": "2026-10-31", "time": "01:41"},
    ]
    assert out["state"] == ["2026-10-30", "02:00", "none"]
    assert out["createBody"] == {
        "name": "N",
        "prompt": "p",
        "schedule": {
            "start": {"date": "2026-10-30", "time": "02:00"},
            "repeat": {"every": 1, "unit": "week", "days": [4]},
            "ends": {"kind": "never"},
        },
    }
    # The form state holds no target fields.
    assert out["initial"] == [
        "current",
        "Every 2 weeks on Tue, Thu at 9:00 AM",
        "09:00",
        "currentLabel,ends,mode,name,prompt,repeat,startDate,startMode,startTime",
    ]
    assert out["untouched"] == {}
    assert out["touched"] == {
        "schedule": {
            "start": {"date": "2026-01-01", "time": "10:30"},
            "repeat": {"every": 2, "unit": "week", "days": [1, 3]},
            "ends": {"kind": "never"},
        }
    }
    assert out["toPreset"]["schedule"]["repeat"] == {"every": 1, "unit": "day"}
    assert out["flagged"] == {"prompt": "p"}
    assert out["one"] == [
        "none",
        {
            "start": {"date": "2026-11-02", "time": "09:00"},
            "repeat": None,
            "ends": {"kind": "never"},
        },
    ]
    assert out["ends"] == ["current", {"kind": "on", "date": "2026-12-01"}]
    assert out["valid"] == [
        {"every": "Repeat every must be a whole number from 1 to 52."},
        {"every": "Repeat every must be a whole number from 1 to 1439."},
        {},
        {"every": "Repeat every must be a whole number from 1 to 12."},
        {"days": "Pick at least one day."},
        {"ends": "The end date must be on or after the start."},
        {},
        {"ends": "The number of occurrences must be a whole number from 1 to 1000."},
        {"ends": "The number of occurrences must be a whole number from 1 to 1000."},
    ]
    assert out["value"] == [
        {"repeat": {"every": 2, "unit": "week", "days": [1, 6]}, "ends": {"kind": "never"}},
        {
            "repeat": {"every": 2, "unit": "month", "month_by": {"by": "weekday", "nth": -1}},
            "ends": {"kind": "after", "count": 3},
        },
        {"repeat": {"every": 2, "unit": "day"}, "ends": {"kind": "on", "date": "2026-12-01"}},
    ]
    assert out["pre"] == [
        {"schedule": "Choose a start date."},
        {"schedule": "Enter a start time like 9:30 AM."},
    ]


# ── starts: On / In / Immediately (M33 F4 L4) ───────────────────────────────


def _runs_of(base: str, agent: str, rid: str) -> list[dict]:
    r = httpx.get(
        f"{base}/api/agents/{agent}/routines/{rid}/runs",
        headers=auth_headers_for(base),
        timeout=5,
    )
    assert r.status_code == 200, r.text
    return r.json()["runs"]


def _wait_runs(page: Page, base: str, agent: str, rid: str, n: int = 1) -> list[dict]:
    runs: list[dict] = []
    for _ in range(40):
        runs = _runs_of(base, agent, rid)
        if len(runs) >= n and all(x.get("outcome") for x in runs):
            return runs
        page.wait_for_timeout(500)
    return runs


def test_starts_radio_group_enables_only_the_chosen_option(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    on, in_, now = (_tid(page, f"routine-form-start-{k}") for k in ("on", "in", "now"))
    date_in, time_in = (_tid(page, f"routine-form-start-{k}-input") for k in ("date", "time"))
    amount, unit, result = (
        _tid(page, f"routine-form-in-{k}") for k in ("amount", "unit", "result")
    )
    expect(page.get_by_role("group", name="Starts")).to_have_count(1)
    expect(on).to_be_checked()
    expect(date_in).to_be_enabled()
    expect(time_in).to_be_enabled()
    expect(amount).to_be_disabled()
    expect(unit).to_be_disabled()
    expect(page.get_by_text("The first run starts when you save")).to_be_visible()
    in_.check()
    expect(date_in).to_be_disabled()
    expect(time_in).to_be_disabled()
    expect(amount).to_be_enabled()
    expect(unit).to_be_enabled()
    expect(result).to_have_text("")
    amount.fill("2")
    expect(result).to_have_text(re.compile(r"(Today|Tomorrow) at \d+:\d\d (AM|PM)|, \d{4}|at \d"))
    amount.fill("")
    expect(result).to_have_text("")
    now.check()
    for ctl in (date_in, time_in, amount, unit):
        expect(ctl).to_be_disabled()
    on.check()
    expect(date_in).to_be_enabled()
    expect(amount).to_be_disabled()


def test_immediately_runs_a_repeating_routine_at_once(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Right now")
    _tid(page, "routine-form-start-now").check()
    _tid(page, "routine-form-repeat").select_option("day")
    expect(_tid(page, "routine-form-preview")).to_contain_text(
        "First run: when you save", timeout=8000
    )
    _save(page)
    row = _row(page, "Right now")
    expect(row).to_be_visible(timeout=8000)
    saved = next(r for r in _list(base, agent) if r["name"] == "Right now")
    runs = _wait_runs(page, base, agent, saved["id"])
    assert len(runs) == 1 and runs[0]["outcome"] == "ok" and runs[0]["trigger_kind"] == "schedule"
    after = next(r for r in _list(base, agent) if r["name"] == "Right now")
    assert after["finished_at"] is None
    assert after["next_run_at"] > saved["created_at"]


def test_immediately_runs_a_one_off_once_and_it_is_done(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _open_tab(page, base, agent)
    _new_form(page)
    _fill(page, "Once now")
    _tid(page, "routine-form-start-now").check()
    _save(page)
    expect(_row(page, "Once now")).to_be_visible(timeout=8000)
    saved = next(r for r in _list(base, agent) if r["name"] == "Once now")
    runs = _wait_runs(page, base, agent, saved["id"])
    assert len(runs) == 1 and runs[0]["outcome"] == "ok"
    expect(_row(page, "Once now").locator('[data-testid="routine-next"]')).to_have_text(
        "Done", timeout=8000
    )


def test_immediately_in_edit_is_a_change_and_flipping_back_is_clean(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, agent = app_with_agent.base_url, app_with_agent.agent_name
    _create(base, agent, "Edit me", _daily("09:00", "2026-01-01"))
    _open_tab(page, base, agent)
    _edit(page, "Edit me")
    save = _tid(page, "routine-form-save")
    expect(_tid(page, "routine-form-start-on")).to_be_checked()
    expect(save).to_be_disabled()
    _tid(page, "routine-form-start-now").check()
    expect(save).to_be_enabled()
    _tid(page, "routine-form-start-on").check()
    expect(_tid(page, "routine-form-start-date-input")).to_have_value(_shown(date(2026, 1, 1)))
    expect(_tid(page, "routine-form-start-time-input")).to_have_value("9:00 AM")
    expect(save).to_be_disabled()
    _tid(page, "routine-form-start-in").check()
    _tid(page, "routine-form-in-amount").fill("3")
    expect(save).to_be_enabled()
    _tid(page, "routine-form-in-amount").fill("")
    expect(save).to_be_disabled()
