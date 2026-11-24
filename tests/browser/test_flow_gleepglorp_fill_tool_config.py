"""GleepGlorp fills the built-in tool editor (M36 F5 L4b, flight DD7, DD13 and DD14).

A ``tool_config`` fill writes a tool's Enabled switch and its allowlisted config fields into the
open editor (``#settings/tools/{name}``) as UNSAVED edits, each with a quiet note linked through
``aria-describedby``. Nothing is stored until the operator saves, and Save runs the impact dialog
as today. Covers, as state transitions:

* [grid] -> [editor filled]: the fill navigates, writes only the named fields, leaves the editor
  dirty and focus in the drawer composer (AC2);
* [backend + URL in one fill] -> the URL row is shown, filled and noted; a URL fill while the
  backend stays DuckDuckGo writes the hidden field with no note, and choosing SearXNG shows it;
* a value outside a select's choices shows as the "(custom)" option;
* a field the operator changed is kept; another route asks the leave guard and Stay writes nothing;
* a Save in flight holds a fill; the "Saving narrows N agents" dialog already open refuses one
  (the drawer's modal rule) and holds one already waiting until the operator chooses (AC3).

Seeds the fills straight into the database and delivers each real view into the drawer's socket,
as ``test_flow_gleepglorp_fill.py`` does. Lives in the ``gleepglorp-kinds`` browser lane.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from browser import _drawer, _nav
from browser._credential_registry import auth_headers_for
from browser._mcp_editor import _count, _hold_requests, _install_counter, _wait_held
from browser.test_flow_gleepglorp_fill import (
    _bworld,
    _deliver,
    _done,
    _drawer_receipt,
    _seed_b,
    _wait_status,
)
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

SAVE = '[data-testid="save-tool-btn"]'
CANCEL = '[data-testid="cancel-tool-btn"]'
UNSAVED = '[data-testid="editor-unsaved"]'
NOTE = '[data-testid="tool-filled-note"]'
COMPOSER = '[data-testid="gg-chat-input"]'
KEPT = '[data-testid="fill-receipt-kept"]'
TIMEOUT = "#tef-timeout_seconds_default"
OUTPUT = "#tef-output_cap_bytes"
ENABLED = "#tef-enabled"
BACKEND = "#tef-search_backend"
SEARX = "#tef-searxng_base_url"
IMPACT = {
    "agents": [{"agent": "plain", "fields": [{"field_title": "Default timeout", "dropped": []}]}]
}


def _world(app_with_data_dir: tuple[str, Any], page: Page) -> SimpleNamespace:
    return _bworld(app_with_data_dir, page, route="library")


def _fill(w: SimpleNamespace, tool: str, changes: dict, **kw: Any) -> int:
    return _seed_b(
        w, kind="tool_config", action="change", agent_name=None, target_id=tool,
        changes=changes, **kw,
    )  # fmt: skip


def _stored(base: str, tool: str) -> dict:
    r = httpx.get(f"{base}/api/tools/configs/{tool}", headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code == 200, r.text
    return r.json()


def _open(page: Page, tool: str) -> None:
    _nav.set_route(page, f"settings/tools/{tool}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)


def _describes(page: Page, control: str, note: str) -> bool:
    nid = page.locator(note).get_attribute("id")
    return nid in (page.locator(control).get_attribute("aria-describedby") or "").split()


# ── AC2: a fill from another destination ─────────────────────────────────────


def test_a_fill_opens_the_editor_writes_only_the_named_fields_and_leaves_it_dirty(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    before = _stored(w.base, "shell")
    enabled = not before["enabled"]
    page.locator(COMPOSER).focus()
    fid = _fill(
        w,
        "shell",
        {"timeout_seconds_default": 60, "output_cap_bytes": 65536, "enabled": enabled},
        base={},
    )
    _deliver(page, w, fid)
    expect(page.locator(TIMEOUT)).to_have_value("60", timeout=10000)
    _nav.expect_route(page, "settings/tools/shell")
    expect(page.locator(OUTPUT)).to_have_value("65536")
    if enabled:
        expect(page.locator(ENABLED)).to_be_checked()
    else:
        expect(page.locator(ENABLED)).not_to_be_checked()
    for field, control in (
        ("timeout_seconds_default", TIMEOUT),
        ("output_cap_bytes", OUTPUT),
        ("enabled", ENABLED),
    ):
        note = f'{NOTE}[data-field="{field}"]'
        expect(page.locator(note)).to_have_count(1)
        assert _describes(page, control, note)
    # Only the named fields: the maximum timeout keeps its stored value.
    expect(page.locator(f'{NOTE}[data-field="timeout_seconds_max"]')).to_have_count(0)
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    assert _stored(w.base, "shell") == before  # nothing is stored until Save
    done = _wait_status(page, w, fid, "filled")
    assert done["outcome"] == {"kept": [], "reason": None}
    page.wait_for_timeout(300)
    expect(page.locator(COMPOSER)).to_be_focused()
    _done(page)
    expect(_drawer_receipt(page, fid)).to_have_attribute("data-status", "filled")
    # Cancel restores the stored values and clears the notes.
    page.locator(CANCEL).click()
    expect(page.locator(NOTE)).to_have_count(0)
    expect(page.locator(TIMEOUT)).to_have_value(
        str(before["config"].get("timeout_seconds_default", 30))
    )


def test_the_notes_stay_linked_after_a_failed_save(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    """Save clears every field error first; that must not drop a note's describedby link."""
    w = _world(app_with_data_dir, page)
    page.locator(COMPOSER).focus()
    fid = _fill(w, "shell", {"timeout_seconds_default": 60, "output_cap_bytes": 65536}, base={})
    _deliver(page, w, fid)
    expect(page.locator(OUTPUT)).to_have_value("65536", timeout=10000)
    for field, control in (("timeout_seconds_default", TIMEOUT), ("output_cap_bytes", OUTPUT)):
        assert _describes(page, control, f'{NOTE}[data-field="{field}"]')
    page.route(
        "**/api/tools/configs/shell",
        lambda route: (
            route.fulfill(
                status=500,
                content_type="application/json",
                body=json.dumps({"detail": "Save failed on purpose"}),
            )
            if route.request.method == "PUT"
            else route.continue_()
        ),
    )
    page.locator(SAVE).click()
    expect(page.get_by_text("Save failed on purpose").first).to_be_visible(timeout=10000)
    for field, control in (("timeout_seconds_default", TIMEOUT), ("output_cap_bytes", OUTPUT)):
        note = f'{NOTE}[data-field="{field}"]'
        expect(page.locator(note)).to_have_count(1)
        assert _describes(page, control, note)


def test_the_fill_never_offers_a_secret_or_list_handle(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    """Defence in depth: the fill's allowed set drops password, secret and array handles."""
    _world(app_with_data_dir, page)
    got = page.evaluate(
        """() => {
          const div = () => document.createElement('div');
          const input = () => document.createElement('input');
          const handle = () => ({ el: div(), control: input() });
          const env = {
            name: 'x', el: document.createElement('div'),
            properties: {
              n: { type: 'integer' }, s: { type: 'string' },
              key: { type: 'string', ui_hint: 'password' },
              sec: { type: 'string', secret: true },
              paths: { type: 'array' },
            },
            fieldNames: ['n', 's', 'key', 'sec', 'paths'],
            handles: { n: handle(), s: handle(), key: handle(), sec: handle(), paths: handle() },
            enabledToggle: { el: div(), control: input(), setChecked() {} },
            isAlive: () => true, busy: () => false,
          };
          const ctl = App.admin.toolsEditorController.create(env);
          const out = { all: ctl.fields(), fill: ctl.fillFields() };
          ctl.destroy();
          return out;
        }"""
    )
    assert got["all"] == ["enabled", "n", "s", "key", "sec", "paths"]
    assert got["fill"] == ["enabled", "n", "s"]


def test_a_value_outside_the_choices_shows_as_the_custom_option_and_save_stores_it(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    _open(page, "shell")
    fid = _fill(w, "shell", {"timeout_seconds_default": 45})
    _deliver(page, w, fid)
    expect(page.locator(TIMEOUT)).to_have_value("45", timeout=10000)
    assert "(custom)" in page.locator(f"{TIMEOUT} option:checked").inner_text()
    _wait_status(page, w, fid, "filled")
    page.locator(SAVE).click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    assert _stored(w.base, "shell")["config"]["timeout_seconds_default"] == 45
    expect(page.locator(NOTE)).to_have_count(0)  # Save clears the notes


# ── the show_if rows ─────────────────────────────────────────────────────────


def test_a_backend_and_its_url_in_one_fill_show_the_url_row_filled_and_noted(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    fid = _fill(
        w, "web_search",
        {"search_backend": "searxng", "searxng_base_url": "https://searx.example.org"},
    )  # fmt: skip
    _deliver(page, w, fid)
    expect(page.locator(BACKEND)).to_have_value("searxng", timeout=10000)
    expect(page.locator(SEARX)).to_be_visible()
    expect(page.locator(SEARX)).to_have_value("https://searx.example.org")
    for field, control in (("search_backend", BACKEND), ("searxng_base_url", SEARX)):
        note = f'{NOTE}[data-field="{field}"]'
        expect(page.locator(note)).to_have_count(1)
        assert _describes(page, control, note)
    _wait_status(page, w, fid, "filled")


def test_a_url_fill_while_the_backend_stays_hidden_is_written_with_no_note(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    _open(page, "web_search")
    fid = _fill(w, "web_search", {"searxng_base_url": "https://searx.example.org"})
    _deliver(page, w, fid)
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes", timeout=10000)
    expect(page.locator(SEARX)).to_be_hidden()
    expect(page.locator(NOTE)).to_have_count(0)
    # The receipt says filled: the value is part of the unsaved edit.
    done = _wait_status(page, w, fid, "filled")
    assert done["outcome"] == {"kept": [], "reason": None}
    # Choosing SearXNG afterwards shows the filled URL.
    page.locator(BACKEND).select_option("searxng")
    expect(page.locator(SEARX)).to_be_visible()
    expect(page.locator(SEARX)).to_have_value("https://searx.example.org")


# ── AC3: dirty and busy ──────────────────────────────────────────────────────


def test_a_field_the_operator_changed_is_kept_on_the_same_route(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    _open(page, "shell")
    page.locator(TIMEOUT).select_option("90")
    fid = _fill(w, "shell", {"timeout_seconds_default": 60, "output_cap_bytes": 65536})
    _deliver(page, w, fid)
    done = _wait_status(page, w, fid, "partly_filled")
    assert done["outcome"] == {"kept": ["timeout_seconds_default"], "reason": None}
    expect(page.locator(TIMEOUT)).to_have_value("90")
    expect(page.locator(OUTPUT)).to_have_value("65536")
    expect(page.locator(f'{NOTE}[data-field="timeout_seconds_default"]')).to_have_count(0)
    expect(page.locator(f'{NOTE}[data-field="output_cap_bytes"]')).to_have_count(1)
    _done(page)
    expect(_drawer_receipt(page, fid).locator(KEPT)).to_be_visible()


def test_a_dirty_editor_on_another_tool_asks_the_guard_and_stay_writes_nothing(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    _open(page, "shell")
    page.locator(TIMEOUT).select_option("90")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    fid = _fill(w, "python_exec", {"timeout_seconds_default": 60})
    _deliver(page, w, fid)
    expect(page.locator(_drawer.STAY)).to_be_visible(timeout=8000)
    page.locator(_drawer.STAY).click()
    done = _wait_status(page, w, fid, "not_filled")
    assert done["outcome"] == {"kept": [], "reason": "stay"}
    expect(page.locator(TIMEOUT)).to_have_value("90")
    _nav.expect_route(page, "settings/tools/shell")
    _done(page)
    expect(_drawer_receipt(page, fid)).to_contain_text(
        "You chose to stay on the page you were editing."
    )


def test_a_fill_that_arrives_during_a_save_waits_for_it(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    _install_counter(page)
    w = _world(app_with_data_dir, page)
    _open(page, "shell")
    held = _hold_requests(page, "**/api/tools/configs/shell", "PUT")
    page.locator(TIMEOUT).select_option("90")
    page.locator(SAVE).click()
    _wait_held(page, held, "PUT", "/api/tools/configs/shell")
    fid = _fill(w, "shell", {"output_cap_bytes": 65536})
    _deliver(page, w, fid)
    page.wait_for_timeout(600)
    assert page.locator(OUTPUT).input_value() != "65536"  # nothing written yet
    held[0].continue_()
    expect(page.locator(OUTPUT)).to_have_value("65536", timeout=10000)
    _wait_status(page, w, fid, "filled")
    assert _stored(w.base, "shell")["config"]["timeout_seconds_default"] == 90
    assert _count(page, "PUT", "/api/tools/configs/shell") == 1


def _fake_impact(page: Page, tool: str) -> list:
    """Hold each ``/impact`` preview for *tool*; the test answers it (a narrowing result)."""
    held: list = []
    page.route(f"**/api/tools/configs/{tool}/impact", lambda route: held.append(route))
    return held


def test_a_fill_arriving_with_the_narrowing_dialog_open_is_not_filled_stay(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    _open(page, "shell")
    held = _fake_impact(page, "shell")
    page.locator(TIMEOUT).select_option("90")
    page.locator(SAVE).click()
    while not held:
        page.wait_for_timeout(50)
    held[0].fulfill(status=200, content_type="application/json", body=json.dumps(IMPACT))
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_be_visible(timeout=8000)
    fid = _fill(w, "shell", {"output_cap_bytes": 65536})
    _deliver(page, w, fid)
    done = _wait_status(page, w, fid, "not_filled")
    assert done["outcome"] == {"kept": [], "reason": "stay"}
    assert page.locator(OUTPUT).input_value() != "65536"


@pytest.mark.parametrize("choice", ["cancel", "save"])
def test_a_fill_waiting_when_the_dialog_opens_writes_nothing_until_the_operator_chooses(
    app_with_data_dir: tuple[str, Any], page: Page, choice: str
) -> None:
    w = _world(app_with_data_dir, page)
    _open(page, "shell")
    held = _fake_impact(page, "shell")
    page.locator(TIMEOUT).select_option("90")
    page.locator(SAVE).click()  # the preview is held: the editor is busy, no dialog yet
    while not held:
        page.wait_for_timeout(50)
    fid = _fill(w, "shell", {"output_cap_bytes": 65536})
    _deliver(page, w, fid)
    page.wait_for_timeout(500)
    assert page.locator(OUTPUT).input_value() != "65536"  # waiting on the preview
    held[0].fulfill(status=200, content_type="application/json", body=json.dumps(IMPACT))
    dialog = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(dialog).to_be_visible(timeout=8000)
    page.wait_for_timeout(600)
    assert page.locator(OUTPUT).input_value() != "65536"  # still held behind the dialog
    page.locator(
        '[data-testid="modal-confirm-btn"]'
        if choice == "save"
        else '[data-testid="modal-cancel-btn"]'
    ).click()
    expect(page.locator(OUTPUT)).to_have_value("65536", timeout=10000)
    _wait_status(page, w, fid, "filled")
    if choice == "save":
        assert _stored(w.base, "shell")["config"]["timeout_seconds_default"] == 90
