"""Settings > General > Date and time (M28 F2 L3, flight DD4).

The page picks the time zone agents tell the time in and the app shows times in.
The browser's zone is controlled with ``credentialed_context(timezone_id=...)``;
the server's system zone is pinned by spawning the app with ``TZ``. State is read
back through ``GET /api/time-settings``. ``page.clock.install()`` is never used
(it would break ``_nav.wait_settled``); a fixed clock uses ``set_fixed_time``.

Falls in the ``settings`` browser lane (``test_flow_settings_*``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from browser import _chats, _lists, _nav
from browser._credential_registry import auth_headers_for
from browser._credential_registry import unregister as _unregister_credential
from browser.conftest import _spawn_app, _teardown_proc, credentialed_context
from browser.seeders import (
    seed_mock_agent,
    seed_mock_provider,
    seed_session,
    seed_tool_config,
)
from playwright.sync_api import Browser, Page, expect

pytestmark = pytest.mark.browser

ROUTE = "settings/date-and-time"
CHICAGO = "America/Chicago"
KOLKATA = "Asia/Kolkata"
KIRITIMATI = "Pacific/Kiritimati"
TIME_SETTINGS = "**/api/time-settings"
TIME_ZONES = "**/api/time-zones"


def tid(page: Page, testid: str) -> Any:
    # .first: a test that mounts a scratch second instance (appended to the body)
    # has duplicates; the page under test is always the first in document order.
    return page.locator(f'[data-testid="{testid}"]').first


def zone_rows(page: Page) -> Any:
    return page.locator('[data-testid="date-time-zone-row"]')


def get_settings(base: str) -> dict[str, Any]:
    r = httpx.get(f"{base}/api/time-settings", headers=auth_headers_for(base), timeout=5)
    assert r.status_code == 200, r.text
    return r.json()


def put_settings(base: str, body: dict[str, Any]) -> dict[str, Any]:
    r = httpx.put(f"{base}/api/time-settings", json=body, headers=auth_headers_for(base), timeout=5)
    assert r.status_code == 200, r.text
    return r.json()


@contextmanager
def session(
    tmp_path: Path,
    browser: Browser,
    *,
    server_tz: str | None = None,
    browser_tz: str = CHICAGO,
    fixed: datetime | None = None,
) -> Iterator[tuple[str, Page]]:
    """A spawned app (system zone pinned by ``TZ`` when given) and a page whose
    browser zone is *browser_tz*."""
    env = {"TZ": server_tz} if server_tz else None
    base, proc, _credential, _data_dir = _spawn_app(tmp_path, extra_env=env)
    context = None
    try:
        context = credentialed_context(browser, base, timezone_id=browser_tz)
        page = context.new_page()
        if fixed is not None:
            page.clock.set_fixed_time(fixed)
        yield base, page
    finally:
        if context is not None:
            context.close()
        _unregister_credential(base)
        _teardown_proc(proc)


def open_page(page: Page, base: str) -> None:
    _nav.goto(page, base, ROUTE)
    expect(tid(page, "date-time-mode")).to_be_visible(timeout=10000)


def choose_zone_mode(page: Page) -> None:
    tid(page, "date-time-mode-zone").check()
    expect(tid(page, "date-time-search")).to_be_visible()


def pick(page: Page, zone: str, query: str | None = None) -> None:
    tid(page, "date-time-search").fill(query if query is not None else zone)
    row = page.locator(f'[data-testid="date-time-zone-row"][data-zone="{zone}"]')
    row.click()


def expect_saved(page: Page) -> None:
    expect(tid(page, "date-time-status")).to_contain_text("Saved.", timeout=8000)


def test_system_load_describes_the_detected_zone(tmp_path: Path, browser: Browser) -> None:
    with session(tmp_path, browser, server_tz=CHICAGO, browser_tz=CHICAGO) as (base, page):
        open_page(page, base)
        _nav.expect_route(page, ROUTE)
        expect(_lists.settings_page_title(page)).to_have_text("Date and time")
        expect(tid(page, "date-time-mode-system")).to_be_checked()
        expect(tid(page, "date-time-mode-zone")).not_to_be_checked()
        body = page.locator("body")
        expect(body).to_contain_text(f"Detected on the machine running the-one: {CHICAGO}")
        expect(tid(page, "date-time-mismatch")).to_be_hidden()
        expect(tid(page, "date-time-search")).to_be_hidden()
        s = get_settings(base)
        assert s["mode"] == "system"
        # The tool line carries the current time, so the page's string (taken at
        # load) can differ from the server's later one by a second or a minute
        # rollover: match the time digits by shape, the zone suffix exactly.
        tool_line = s["preview"]["tool"].split("\n")[0]
        assert tool_line.endswith(f"({CHICAGO})"), tool_line
        tool_shape = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d" + re.escape(tool_line[19:])
        expect(tid(page, "date-time-preview-tool")).to_have_text(re.compile(f"^{tool_shape}$"))
        expect(tid(page, "date-time-preview-prompt")).to_have_text(s["preview"]["prompt"])
        expect(tid(page, "date-time-preview-clock")).to_have_text(
            re.compile(r"^\d{1,2}:\d\d [AP]M in the Chats list and on messages$")
        )


def test_search_and_pick(tmp_path: Path, browser: Browser) -> None:
    with session(tmp_path, browser, server_tz=CHICAGO) as (base, page):
        open_page(page, base)
        choose_zone_mode(page)
        search = tid(page, "date-time-search")
        rows = zone_rows(page)
        assert rows.count() > 100
        search.fill("kolk")
        expect(rows.filter(has_text="Kolkata")).to_have_count(1)
        search.fill("Europe/")
        assert rows.count() > 10
        zones = [r.get_attribute("data-zone") for r in rows.all()]
        assert all(z.startswith("Europe/") for z in zones), zones
        search.fill("+05:30")
        expect(rows.filter(has_text="Kolkata")).to_have_count(1)
        search.fill("ko")
        expect(rows.first).to_have_attribute("data-zone", KOLKATA)
        assert not [r for r in rows.all() if "North_Dakota" in r.get_attribute("data-zone")]
        search.fill("salem")
        expect(rows.filter(has_text="New Salem")).to_have_count(1)
        search.fill("argentina")
        expect(rows.filter(has_text="Buenos Aires")).to_have_count(1)
        search.fill("ist")
        expect(rows.filter(has_text="Kolkata")).to_have_count(1)
        search.fill("+05:30")
        expect(rows.filter(has_text="Kolkata")).to_have_count(1)
        rows.filter(has_text="Kolkata").click()
        expect_saved(page)
        expect(tid(page, "date-time-status")).to_contain_text(f"Agents now use {KOLKATA}.")
        expect(tid(page, "date-time-chosen")).to_have_text(
            "Selected: Kolkata Asia/Kolkata · UTC+05:30"
        )
        s = get_settings(base)
        assert (s["mode"], s["zone"]) == ("zone", KOLKATA)
        expect(tid(page, "date-time-preview-tool")).to_contain_text(KOLKATA)
        # The query is kept after a pick.
        expect(search).to_have_value("+05:30")


def test_choosing_with_nothing_stored_saves_nothing(tmp_path: Path, browser: Browser) -> None:
    with session(tmp_path, browser, server_tz=CHICAGO) as (base, page):
        puts: list[str] = []
        page.on(
            "request",
            lambda r: (
                puts.append(r.url) if r.method == "PUT" and "time-settings" in r.url else None
            ),
        )
        open_page(page, base)
        choose_zone_mode(page)
        expect(tid(page, "date-time-chosen")).to_have_text(
            "Pick a zone below. Nothing changes until you do."
        )
        page.wait_for_timeout(400)
        assert puts == []
        assert get_settings(base)["mode"] == "system"
        # The chooser stays shown although the server still says system.
        expect(tid(page, "date-time-search")).to_be_visible()


def test_back_to_system_keeps_the_stored_zone(tmp_path: Path, browser: Browser) -> None:
    with session(tmp_path, browser, server_tz=CHICAGO) as (base, page):
        open_page(page, base)
        choose_zone_mode(page)
        pick(page, KOLKATA)
        expect_saved(page)
        tid(page, "date-time-mode-system").check()
        expect(tid(page, "date-time-status")).to_contain_text("the system time zone")
        s = get_settings(base)
        assert (s["mode"], s["zone"]) == ("system", KOLKATA)
        puts: list[str] = []
        page.on(
            "request",
            lambda r: (
                puts.append(r.post_data or "")
                if r.method == "PUT" and "time-settings" in r.url
                else None
            ),
        )
        tid(page, "date-time-mode-zone").check()
        expect(tid(page, "date-time-status")).to_contain_text(f"Agents now use {KOLKATA}.")
        assert len(puts) == 1 and json.loads(puts[0]) == {"mode": "zone", "zone": KOLKATA}
        assert get_settings(base)["mode"] == "zone"


def test_mismatch_hint_and_its_one_step_fix(tmp_path: Path, browser: Browser) -> None:
    with session(tmp_path, browser, server_tz=CHICAGO, browser_tz=KIRITIMATI) as (base, page):
        open_page(page, base)
        hint = tid(page, "date-time-mismatch")
        expect(hint).to_be_visible()
        # B9: the hint leads with city names; the raw zone ids stay in its title.
        text = hint.locator(".date-time-mismatch-text")
        expect(text).to_contain_text("Your browser is in Kiritimati")
        expect(text).to_contain_text("the machine running the-one reports Chicago")
        expect(text).not_to_contain_text(KIRITIMATI)
        title = hint.get_attribute("title") or ""
        assert KIRITIMATI in title and CHICAGO in title, title
        # HAT (ledger 53): the button names the same place as the banner text.
        button = tid(page, "date-time-use-browser")
        expect(button).to_have_text("Use Kiritimati")
        button.click()
        expect_saved(page)
        expect(hint).to_be_hidden()
        s = get_settings(base)
        assert (s["mode"], s["zone"]) == ("zone", KIRITIMATI)


def test_a_legacy_alias_is_not_a_mismatch(tmp_path: Path, browser: Browser) -> None:
    # Chromium reports Asia/Calcutta for Asia/Kolkata: the same clock, no hint.
    with session(tmp_path, browser, server_tz=KOLKATA, browser_tz=KOLKATA) as (base, page):
        open_page(page, base)
        expect(tid(page, "date-time-mode-system")).to_be_checked()
        page.wait_for_timeout(300)
        expect(tid(page, "date-time-mismatch")).to_be_hidden()


def test_a_merged_zone_is_found_by_name_and_stored_as_chosen(
    tmp_path: Path, browser: Browser
) -> None:
    with session(tmp_path, browser, server_tz="Europe/Berlin", browser_tz="Europe/Oslo") as (
        base,
        page,
    ):
        open_page(page, base)
        page.wait_for_timeout(300)
        expect(tid(page, "date-time-mismatch")).to_be_hidden()
        choose_zone_mode(page)
        tid(page, "date-time-search").fill("Oslo")
        item = page.locator('[data-testid="date-time-zone-row"][data-zone="Europe/Oslo"]')
        expect(item).to_have_count(1)
        expect(item).to_contain_text("Europe/Oslo · same clock as Europe/Berlin")
        item.click()
        expect_saved(page)
        assert get_settings(base)["zone"] == "Europe/Oslo"
        chosen = tid(page, "date-time-chosen")
        expect(chosen).to_contain_text("Selected: Oslo Europe/Oslo · ")


def test_a_stored_alias_item_carries_the_check_and_is_active(
    tmp_path: Path, browser: Browser
) -> None:
    with session(tmp_path, browser, server_tz="Europe/Berlin", browser_tz="Europe/Oslo") as (
        base,
        page,
    ):
        put_settings(base, {"mode": "zone", "zone": "Europe/Oslo"})
        open_page(page, base)
        tid(page, "date-time-search").fill("oslo")
        item = page.locator('[data-testid="date-time-zone-row"][data-zone="Europe/Oslo"]')
        expect(item).to_have_count(1)
        expect(item).to_have_attribute("aria-selected", "true")
        expect(item.locator("svg")).to_have_count(1)


def test_tool_turned_off_changes_the_preview(tmp_path: Path, browser: Browser) -> None:
    with session(tmp_path, browser, server_tz=CHICAGO) as (base, page):
        seed_tool_config(base, "current_time", enabled=False)
        open_page(page, base)
        s = get_settings(base)
        assert s["tool_enabled"] is False
        expect(tid(page, "date-time-preview-prompt")).to_have_text(
            s["preview"]["prompt_without_tool"]
        )
        expect(tid(page, "date-time-prompt-muted")).to_be_visible()
        expect(tid(page, "date-time-prompt-muted")).to_have_text(
            "The time tool is turned off in Built-in tools."
        )


def test_a_rejected_zone_shows_the_server_sentence_and_restores(
    tmp_path: Path, browser: Browser
) -> None:
    bogus = "Mars/Olympus_Mons"

    def inject(route: Any) -> None:
        resp = route.fetch()
        body = resp.json()
        body["zones"].append(
            {
                "zone": bogus,
                "region": "Mars",
                "city": "Olympus Mons",
                "offset": "UTC+00:00",
                "abbreviation": "MST",
            }
        )
        route.fulfill(response=resp, json=body)

    with session(tmp_path, browser, server_tz=CHICAGO) as (base, page):
        page.route(TIME_ZONES, inject)
        open_page(page, base)
        choose_zone_mode(page)
        pick(page, bogus, query="Olympus")
        error = tid(page, "date-time-error")
        expect(error).to_contain_text(f"Unknown time zone '{bogus}'")
        expect(tid(page, "date-time-mode-system")).to_be_checked(timeout=8000)
        assert get_settings(base)["mode"] == "system"


def _mount_scratch(page: Page) -> None:
    page.evaluate(
        """() => {
          const d = document.createElement('div');
          d.id = 'dt-scratch';
          document.body.appendChild(d);
          App.admin.renderDateTimePage(d);
        }"""
    )


def test_a_late_load_never_overrides_a_newer_save(tmp_path: Path, browser: Browser) -> None:
    # A second mount (a re-entry in practice) takes an older generation: its late
    # response must not touch App.time, and the visible page keeps the pick.
    with session(tmp_path, browser, server_tz=CHICAGO) as (base, page):
        _nav.goto_settled(page, base, "settings/appearance")
        _nav.goto(page, base, ROUTE)
        expect(tid(page, "date-time-mode")).to_be_visible(timeout=10000)
        held: list[Any] = []

        def hold(route: Any) -> None:
            if route.request.method != "GET":
                route.fallback()
                return
            held.append((route, route.fetch()))  # the old state, captured now

        page.route(TIME_SETTINGS, hold)
        _mount_scratch(page)
        page.wait_for_function("() => !!document.querySelector('#dt-scratch')")
        for _ in range(50):
            if held:
                break
            page.wait_for_timeout(100)
        assert held, "the scratch mount's GET was not captured"
        choose_zone_mode(page)
        pick(page, KIRITIMATI)
        expect_saved(page)
        route, resp = held[0]
        route.fulfill(response=resp)
        page.wait_for_timeout(500)
        assert page.evaluate("() => App.time.zone()") == KIRITIMATI
        expect(tid(page, "date-time-status")).to_contain_text(f"Agents now use {KIRITIMATI}.")
        assert get_settings(base)["zone"] == KIRITIMATI


def test_the_apps_clocks_follow_without_a_reload(tmp_path: Path, browser: Browser) -> None:
    fixed = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    with session(
        tmp_path,
        browser,
        server_tz="Pacific/Pago_Pago",
        browser_tz="Pacific/Pago_Pago",
        fixed=fixed,
    ) as (base, page):
        provider_id = seed_mock_provider(base)
        agent = seed_mock_agent(base, provider_id)
        seed_session(base, agent, "Chat A", "2026-06-15T11:30:00+00:00")
        label_js = """() => {
          const t = document.querySelector('[data-testid="chats-list"] .ui-list-pane-time');
          return t ? t.textContent : null;
        }"""
        _nav.goto_settled(page, base, "chats")
        expect(_chats.chat_rows(page)).to_have_count(1, timeout=8000)
        before = page.evaluate(label_js)
        assert before == "12:30 AM", before
        _nav.open_destination(page, "settings")
        _lists.open_settings_page(page, "date-and-time")
        expect(tid(page, "date-time-mode")).to_be_visible(timeout=8000)
        choose_zone_mode(page)
        pick(page, KIRITIMATI)
        expect_saved(page)
        _nav.open_destination(page, "chats")
        expect(_chats.chat_rows(page)).to_have_count(1, timeout=8000)
        for _ in range(40):
            if page.evaluate(label_js) == "1:30 AM":
                break
            page.wait_for_timeout(100)
        assert page.evaluate(label_js) == "1:30 AM"


def test_keyboard_reaches_the_search_and_enter_picks(tmp_path: Path, browser: Browser) -> None:
    with session(tmp_path, browser, server_tz=CHICAGO) as (base, page):
        open_page(page, base)
        tid(page, "date-time-mode-system").focus()
        # Arrow keys move the selection and save, as a native radio group does.
        page.keyboard.press("ArrowDown")
        expect(tid(page, "date-time-mode-zone")).to_be_checked()
        expect(tid(page, "date-time-search")).to_be_visible()
        page.keyboard.press("Tab")
        search = tid(page, "date-time-search")
        expect(search).to_be_focused()
        page.keyboard.type("Kolkata")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        expect_saved(page)
        assert get_settings(base)["zone"] == KOLKATA
        expect(search).to_be_focused()


def test_an_unmounted_instances_late_answer_leaves_the_visible_page(
    tmp_path: Path, browser: Browser
) -> None:
    with session(tmp_path, browser, server_tz=CHICAGO) as (base, page):
        open_page(page, base)
        held: list[Any] = []

        def hold(route: Any) -> None:
            if route.request.method != "GET":
                route.fallback()
                return
            held.append(route)

        page.route(TIME_SETTINGS, hold)
        choose_zone_mode(page)
        _mount_scratch(page)
        for _ in range(50):
            if held:
                break
            page.wait_for_timeout(100)
        assert held
        # Proves only this: a second instance torn down before its answer arrives
        # (the latest answer) may touch App.time, never the visible page's chooser.
        page.evaluate("() => document.getElementById('dt-scratch').remove()")
        held[0].continue_()
        page.wait_for_timeout(500)
        assert get_settings(base)["mode"] == "system"
        expect(tid(page, "date-time-mode-zone")).to_be_checked()
        expect(tid(page, "date-time-search")).to_be_visible()


def test_a_failed_zone_list_keeps_the_rest_of_the_page(tmp_path: Path, browser: Browser) -> None:
    with session(tmp_path, browser, server_tz=CHICAGO) as (base, page):
        page.route(
            TIME_ZONES,
            lambda route: route.fulfill(status=500, json={"detail": "boom"}),
        )
        open_page(page, base)
        expect(tid(page, "date-time-preview-tool")).to_be_visible()
        tid(page, "date-time-mode-zone").check()
        expect(tid(page, "date-time-search")).to_be_hidden()
        expect(page.get_by_text("The list of time zones could not be loaded.")).to_be_visible()


def test_a_fast_double_pick_ends_on_the_second(tmp_path: Path, browser: Browser) -> None:
    with session(tmp_path, browser, server_tz=CHICAGO) as (base, page):
        open_page(page, base)
        choose_zone_mode(page)
        held: list[Any] = []

        def hold_first(route: Any) -> None:
            if route.request.method != "PUT":
                route.fallback()
                return
            if not held:
                held.append((route, route.fetch()))  # applied, but its answer is held
                return
            route.fallback()

        page.route(TIME_SETTINGS, hold_first)
        pick(page, KOLKATA)
        for _ in range(50):
            if held:
                break
            page.wait_for_timeout(100)
        assert held
        pick(page, "Asia/Tokyo")
        expect(tid(page, "date-time-status")).to_contain_text("Agents now use Asia/Tokyo.")
        route, resp = held[0]
        route.fulfill(response=resp)
        page.wait_for_timeout(500)
        expect(tid(page, "date-time-status")).to_contain_text("Agents now use Asia/Tokyo.")
        expect(tid(page, "date-time-chosen")).to_contain_text("Tokyo")
        assert get_settings(base)["zone"] == "Asia/Tokyo"


def test_zone_mode_hint_names_the_chosen_zone(tmp_path: Path, browser: Browser) -> None:
    with session(tmp_path, browser, server_tz=CHICAGO, browser_tz="Asia/Tokyo") as (base, page):
        put_settings(base, {"mode": "zone", "zone": KOLKATA})
        open_page(page, base)
        hint = tid(page, "date-time-mismatch")
        expect(hint).to_be_visible()
        expect(hint).to_contain_text("Your browser is in Tokyo")
        expect(hint).to_contain_text("agents use Kolkata")
        title = hint.get_attribute("title") or ""
        assert "Asia/Kolkata" in title and "Asia/Tokyo" in title, title
        expect(tid(page, "date-time-mode-zone")).to_be_checked()
        expect(tid(page, "date-time-chosen")).to_contain_text("Selected: Kolkata Asia/Kolkata")


# ── M31 F4 L09: DD8-13 and B8-B10 ─────────────────────────────────────────


def test_use_browser_zone_moves_focus_to_the_chosen_line(tmp_path: Path, browser: Browser) -> None:
    """DD8-13: 'Use {zone}' hides the hint that holds the focused button; focus must
    land on the chosen-zone line instead of dropping to the body."""
    with session(tmp_path, browser, server_tz=CHICAGO, browser_tz=KIRITIMATI) as (base, page):
        open_page(page, base)
        button = tid(page, "date-time-use-browser")
        expect(button).to_be_visible()
        button.focus()
        page.keyboard.press("Enter")
        expect_saved(page)
        expect(tid(page, "date-time-mismatch")).to_be_hidden()
        expect(tid(page, "date-time-chosen")).to_be_focused()
        assert tid(page, "date-time-chosen").get_attribute("tabindex") == "-1"


def test_a_failed_use_keeps_the_button_and_its_focus(tmp_path: Path, browser: Browser) -> None:
    with session(tmp_path, browser, server_tz=CHICAGO, browser_tz=KIRITIMATI) as (base, page):
        open_page(page, base)

        def refuse(route: Any) -> None:
            if route.request.method == "PUT":
                route.fulfill(status=500, json={"detail": "disk is read-only"})
            else:
                route.fallback()

        page.route(TIME_SETTINGS, refuse)
        button = tid(page, "date-time-use-browser")
        button.focus()
        page.keyboard.press("Enter")
        expect(tid(page, "date-time-error")).to_contain_text("disk is read-only", timeout=8000)
        expect(tid(page, "date-time-mismatch")).to_be_visible()
        expect(button).to_be_visible()
        expect(button).to_be_focused()


def test_the_hint_names_an_alias_by_its_canonical_city(tmp_path: Path, browser: Browser) -> None:
    """B9: Chromium reports Asia/Calcutta for Kolkata; the hint reads 'Kolkata'."""
    with session(tmp_path, browser, server_tz=CHICAGO, browser_tz="Asia/Calcutta") as (base, page):
        open_page(page, base)
        hint = tid(page, "date-time-mismatch")
        text = hint.locator(".date-time-mismatch-text")
        expect(text).to_contain_text("Your browser is in Kolkata")
        expect(text).not_to_contain_text("Calcutta")
        expect(tid(page, "date-time-use-browser")).to_have_text("Use Kolkata")


def test_a_zone_with_no_city_falls_back_to_its_id(tmp_path: Path, browser: Browser) -> None:
    with session(tmp_path, browser, server_tz=CHICAGO, browser_tz="UTC") as (base, page):
        open_page(page, base)
        text = tid(page, "date-time-mismatch").locator(".date-time-mismatch-text")
        expect(text).to_contain_text("Your browser is in UTC")
        expect(tid(page, "date-time-use-browser")).to_have_text("Use UTC")


def test_a_zone_whose_label_is_its_id_is_named_once(tmp_path: Path, browser: Browser) -> None:
    """HAT (ledger 54): 'Selected: UTC UTC' repeated itself. A zone whose label equals
    its id (UTC, Japan) shows it once, on the Selected line and on an alias row; a zone
    whose label differs keeps the label, the id and the offset."""
    with session(tmp_path, browser, server_tz=CHICAGO) as (base, page):
        put_settings(base, {"mode": "zone", "zone": "UTC"})
        open_page(page, base)
        chosen = tid(page, "date-time-chosen")
        expect(chosen).to_have_text("Selected: UTC · UTC+00:00")
        tid(page, "date-time-search").fill("Japan")
        item = page.locator('[data-testid="date-time-zone-row"][data-zone="Japan"]')
        expect(item).to_have_count(1)
        expect(item.locator(".ui-search-list-description")).to_have_text("Same clock as Asia/Tokyo")
        item.click()
        expect_saved(page)
        expect(chosen).to_have_text("Selected: Japan · UTC+09:00")
        pick(page, "Europe/Paris", "Paris")
        expect_saved(page)
        expect(chosen).to_contain_text("Selected: Paris Europe/Paris · UTC+")


def test_the_stored_zone_is_centred_and_ids_share_one_font(
    tmp_path: Path, browser: Browser
) -> None:
    """B8: the selected zone is centred in the list; zone ids and offsets use one font in
    the list and in the 'Selected:' line."""
    with session(tmp_path, browser, server_tz=CHICAGO) as (base, page):
        put_settings(base, {"mode": "zone", "zone": KOLKATA})
        open_page(page, base)
        expect(tid(page, "date-time-chosen")).to_contain_text("Kolkata")
        box = page.evaluate(
            """() => {
              const lb = document.querySelector('.ui-search-list-listbox');
              const row = lb.querySelector('[data-zone="Asia/Kolkata"]');
              const a = lb.getBoundingClientRect();
              const b = row.getBoundingClientRect();
              return { mid: a.top + a.height / 2, rowMid: b.top + b.height / 2,
                       rowH: b.height, top: lb.scrollTop };
            }"""
        )
        assert box["top"] > 0, box
        assert abs(box["rowMid"] - box["mid"]) <= box["rowH"], box
        fonts = page.evaluate(
            """() => {
              const f = (el) => getComputedStyle(el).fontFamily;
              const lb = document.querySelector('.ui-search-list-listbox');
              const desc = lb.querySelector('.ui-search-list-description');
              const chosen = document.querySelector('[data-testid="date-time-chosen"]');
              const id = chosen.querySelector('.date-time-chosen-id');
              return { list: f(desc), chosen: id ? f(id) : null };
            }"""
        )
        assert fonts["chosen"] == fonts["list"], fonts


def test_a_pick_does_not_scroll_the_list(tmp_path: Path, browser: Browser) -> None:
    with session(tmp_path, browser, server_tz=CHICAGO) as (base, page):
        open_page(page, base)
        choose_zone_mode(page)
        listbox = page.locator(".ui-search-list-listbox").first
        listbox.evaluate("el => { el.scrollTop = 1200; }")
        before = listbox.evaluate("el => el.scrollTop")
        assert before > 500
        # A row fully inside the listbox's viewport (Playwright scrolls a row that is not).
        zone = listbox.evaluate(
            """lb => {
              const box = lb.getBoundingClientRect();
              for (const r of lb.querySelectorAll('[data-zone]')) {
                const b = r.getBoundingClientRect();
                if (b.top >= box.top + 4 && b.bottom <= box.bottom - 4) return r.dataset.zone;
              }
              return null;
            }"""
        )
        assert zone
        page.locator(f'[data-testid="date-time-zone-row"][data-zone="{zone}"]').click()
        expect_saved(page)
        after = listbox.evaluate("el => el.scrollTop")
        assert abs(after - before) <= 1, (before, after)


def test_an_empty_status_takes_no_height(tmp_path: Path, browser: Browser) -> None:
    """B10: no reserved gap below the zone card while there is no status."""
    with session(tmp_path, browser, server_tz=CHICAGO) as (base, page):
        open_page(page, base)
        region = tid(page, "date-time-status")
        assert region.get_attribute("role") == "status"
        assert region.bounding_box()["height"] == 0
        choose_zone_mode(page)
        pick(page, KOLKATA)
        expect_saved(page)
        assert region.bounding_box()["height"] > 0
