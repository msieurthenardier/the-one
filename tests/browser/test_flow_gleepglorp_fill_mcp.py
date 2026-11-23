"""GleepGlorp fills the MCP server editor (M36 F4 L4b, flight DD8 and DD9).

A fill writes unsaved edits into the Library's MCP server create form or an existing server's edit
form: every field on a create, every field but the type on an existing server. Each filled control
gets a quiet note, the env or headers table gets one, and an empty Sensitive row hands a key to the
operator. Covers, as state transitions:

* [create form] -> [filled: HTTP, empty Sensitive header] -> [typed + saved] (AC5);
* the editor seam writes nothing, runs no Test and opens no popup (AC4);
* a stdio create fill collapses `npx -y`; a change fill writes only the named fields (AC6);
* a field the operator changed is kept, on the same route; another route asks the leave guard
  (AC7); a row that is there is kept, a handoff never replaces it;
* a deleted server is target gone.

Seeds the fills straight into the database and delivers each real view into the drawer's socket,
as ``test_flow_gleepglorp_fill.py`` does. Lives in the ``gleepglorp`` browser lane.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from browser import _drawer, _nav
from browser._credential_registry import auth_headers_for
from browser._mcp_editor import (
    _ED,
    _count,
    _get_source,
    _install_counter,
    _kv_row_by_key,
    _kv_rows,
    _kv_val,
    _list_sources,
    _seed_http,
    _seed_mcp_source,
    _seed_stdio,
)
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

NAME = "#mf-name"
TYPE = "#mf-type"
URL = "#mf-url"
RUNTIME = "#mf-command-runtime"
UNSAVED = '[data-testid="editor-unsaved"]'
SAVE = '[data-testid="save-mcp-source-btn"]'
NOTE = '[data-testid="mcp-filled-note"]'
KV = '[data-testid="mcp-kv-table"]'
ARGS_INPUT = '[data-testid="mcp-args-input"]'
KEPT = '[data-testid="fill-receipt-kept"]'


def _world(app_with_data_dir: tuple[str, Any], page: Page) -> SimpleNamespace:
    return _bworld(app_with_data_dir, page, route="library")


def _fill(w: SimpleNamespace, action: str, changes: dict, **kw: Any) -> int:
    return _seed_b(w, kind="mcp_server", action=action, agent_name=None, changes=changes, **kw)


def _open_create(page: Page) -> None:
    _nav.set_route(page, "library/mcp/~new")
    expect(page.locator(NAME)).to_be_attached(timeout=10000)


def _open_edit(page: Page, sid: str) -> None:
    _nav.set_route(page, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator(SAVE)).to_be_visible(timeout=10000)


def _rows(page: Page) -> list[dict]:
    return page.evaluate(f"() => {_ED}.values().rows")


def _http_create(**extra: Any) -> dict:
    return {
        "name": "Acme",
        "type": "streamable-http",
        "url": "https://mcp.acme.test/mcp",
        **extra,
    }


# ── AC5: a create fill, HTTP ─────────────────────────────────────────────────


def test_a_create_fill_sets_http_fields_notes_each_control_and_hands_over_the_key(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    before = _list_sources(w.base)
    fid = _fill(w, "create", _http_create(headers={"X-Api-Key": ""}))
    _deliver(page, w, fid)
    expect(page.locator(NAME)).to_have_value("Acme", timeout=10000)
    expect(page.locator(TYPE)).to_have_value("streamable-http")
    expect(page.locator(URL)).to_have_value("https://mcp.acme.test/mcp")
    _nav.expect_route(page, "library/mcp/~new")
    rows = _rows(page)
    assert [(r["key"], r["value"], r["sensitive"], r["_originalMasked"]) for r in rows] == [
        ("X-Api-Key", "", True, "")
    ]
    # Notes: one under each filled control, one under the table.
    for field in ("name", "type", "url"):
        expect(page.locator(f'{NOTE}[data-field="{field}"]')).to_have_count(1)
    table_note = page.locator(f'{NOTE}[data-field="headers"]')
    expect(table_note).to_have_text(
        "Filled by GleepGlorp: X-Api-Key. Enter the value for X-Api-Key."
    )
    # Each note describes its control; the table note describes the table. No live region.
    for field, selector in (("name", NAME), ("type", TYPE), ("url", URL)):
        nid = page.locator(f'{NOTE}[data-field="{field}"]').get_attribute("id")
        assert nid in (page.locator(selector).get_attribute("aria-describedby") or "").split()
    tid = table_note.get_attribute("id")
    assert tid in (page.locator(f"{KV}").get_attribute("aria-describedby") or "").split()
    expect(page.locator(f"{NOTE}[role], {NOTE} [aria-live]")).to_have_count(0)
    # Unsaved: the caption shows and nothing is stored.
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    assert _list_sources(w.base) == before
    done = _wait_status(page, w, fid, "filled")
    assert done["outcome"] == {"kept": [], "reason": None}
    _done(page)
    expect(_drawer_receipt(page, fid)).to_have_attribute("data-status", "filled")
    # The operator types the key and saves: the header lands in secrets.
    _kv_val(_kv_row_by_key(page, "X-Api-Key")).fill("sk-operator-typed")
    page.locator(SAVE).click()
    page.wait_for_function("() => App.router.current().route.indexOf('~new') === -1", timeout=10000)
    made = [s for s in _list_sources(w.base) if s["name"] == "Acme"]
    assert len(made) == 1
    stored = _get_source(w.base, made[0]["id"])
    assert "X-Api-Key" in stored["secrets"]
    assert "X-Api-Key" not in (stored["config"].get("headers") or {})
    assert stored["config"]["url"] == "https://mcp.acme.test/mcp"


def test_a_refill_replaces_the_notes_and_cancel_and_save_clear_them(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    sid = _seed_http(w.base, "Docs")
    _open_edit(page, sid)
    fid = _fill(w, "change", {"url": "https://one.test/mcp"}, target_id=sid, base={})
    _deliver(page, w, fid)
    expect(page.locator(URL)).to_have_value("https://one.test/mcp", timeout=10000)
    expect(page.locator(f'{NOTE}[data-field="url"]')).to_have_count(1)
    fid2 = _fill(
        w, "change", {"url": "https://two.test/mcp"}, target_id=sid, base={}, tool_call_id="tc-2"
    )
    _deliver(page, w, fid2)
    expect(page.locator(URL)).to_have_value("https://two.test/mcp", timeout=10000)
    expect(page.locator(f'{NOTE}[data-field="url"]')).to_have_count(1)
    assert page.locator(URL).get_attribute("aria-describedby") == page.locator(
        f'{NOTE}[data-field="url"]'
    ).get_attribute("id")
    # Cancel clears the note and drops the link.
    page.locator('[data-testid="cancel-mcp-source-btn"]').click()
    expect(page.locator(NOTE)).to_have_count(0)
    expect(page.locator(URL)).not_to_have_attribute("aria-describedby", r".+")
    expect(page.locator(URL)).to_have_value("https://example.com/mcp")
    # A Save clears it too.
    fid3 = _fill(
        w, "change", {"url": "https://three.test/mcp"}, target_id=sid, base={}, tool_call_id="tc-3"
    )
    _deliver(page, w, fid3)
    expect(page.locator(f'{NOTE}[data-field="url"]')).to_have_count(1, timeout=10000)
    page.locator(SAVE).click()
    expect(page.locator(NOTE)).to_have_count(0)
    assert _get_source(w.base, sid)["config"]["url"] == "https://three.test/mcp"


# ── AC4: the editor seam ─────────────────────────────────────────────────────


def test_the_editor_seam_swaps_types_keeps_rows_and_never_saves_tests_or_opens_a_popup(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    _install_counter(page)
    page.add_init_script(
        "window.__popups = 0; window.open = () => { window.__popups++; return null; };"
    )
    w = _world(app_with_data_dir, page)
    _open_create(page)
    ed = _ED
    page.evaluate(f"() => {ed}.setType('streamable-http')")
    page.evaluate(f"() => {ed}.setRows([{{key: 'Accept', value: 'application/json'}}])")
    expect(page.locator(URL)).to_be_visible()
    expect(page.locator(RUNTIME)).to_be_hidden()
    # A type swap shows the other sections and keeps the rows the operator typed.
    page.evaluate(f"() => {ed}.setType('stdio')")
    expect(page.locator(RUNTIME)).to_be_visible()
    expect(page.locator(URL)).to_be_hidden()
    assert [r["key"] for r in _rows(page)] == ["Accept"]
    # The command group goes through the collapse: `npx -y` with the rest as arguments.
    page.evaluate(f"() => {ed}.setField('command', {{command: 'npx', args: ['-y', '@acme/x']}})")
    expect(page.locator(RUNTIME)).to_have_value("npx -y")
    expect(page.locator(ARGS_INPUT)).to_have_count(1)
    expect(page.locator(ARGS_INPUT)).to_have_value("@acme/x")
    # An empty-valued row is added Sensitive and keeps the other rows.
    page.evaluate(f"() => {ed}.setRows([{{key: 'API_KEY', value: ''}}])")
    rows = _rows(page)
    assert [(r["key"], r["sensitive"]) for r in rows] == [("Accept", False), ("API_KEY", True)]
    assert len(_kv_rows(page).all()) == 2
    # Nothing was sent: no write, no Test, no popup.
    for method in ("POST", "PUT"):
        assert _count(page, method, "/api/mcp-sources") == 0
    assert _count(page, "POST", "/api/mcp-sources/test/connect") == 0
    assert page.evaluate("() => window.__popups") == 0
    assert _list_sources(w.base) == []


# ── AC6: stdio ───────────────────────────────────────────────────────────────


def test_a_stdio_create_fill_writes_the_collapse_and_a_plain_row_and_a_change_fill_only_the_named(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    fid = _fill(
        w,
        "create",
        {
            "name": "Fetcher",
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@acme/x"],
            "env": {"LOG_LEVEL": "debug"},
        },
    )
    _deliver(page, w, fid)
    expect(page.locator(RUNTIME)).to_have_value("npx -y", timeout=10000)
    expect(page.locator(NAME)).to_have_value("Fetcher")
    expect(page.locator(TYPE)).to_have_value("stdio")
    expect(page.locator(ARGS_INPUT)).to_have_value("@acme/x")
    assert [(r["key"], r["value"], r["sensitive"]) for r in _rows(page)] == [
        ("LOG_LEVEL", "debug", False)
    ]
    expect(page.locator(f'{NOTE}[data-field="command"]')).to_have_count(1)
    expect(page.locator(f'{NOTE}[data-field="env"]')).to_have_text(
        "Filled by GleepGlorp: LOG_LEVEL."
    )
    _wait_status(page, w, fid, "filled")
    page.locator(SAVE).click()
    page.wait_for_function("() => App.router.current().route.indexOf('~new') === -1", timeout=10000)
    made = next(s for s in _list_sources(w.base) if s["name"] == "Fetcher")
    cfg = _get_source(w.base, made["id"])["config"]
    assert cfg["command"] == "npx" and cfg["args"] == ["-y", "@acme/x"]
    assert cfg["env"] == {"LOG_LEVEL": "debug"}

    # A change fill on an existing stdio server writes only what it names.
    sid = _seed_mcp_source(
        w.base,
        {
            "name": "Local",
            "type": "stdio",
            "config": {
                "command": "echo",
                "args": ["hello"],
                "cwd": "/tmp/keep-me",
                "env": {"A": "1"},
            },
            "secrets": {},
        },
    )
    _open_edit(page, sid)
    fid2 = _fill(
        w,
        "change",
        {"args": ["--flag"]},
        target_id=sid,
        base={"args": ["hello"]},
        tool_call_id="tc-2",
    )
    _deliver(page, w, fid2)
    expect(page.locator(ARGS_INPUT)).to_have_value("--flag", timeout=10000)
    expect(page.locator("#mf-command")).to_have_value("echo")  # a custom command, untouched
    expect(page.locator("#mf-cwd")).to_have_value("/tmp/keep-me")
    assert [(r["key"], r["value"]) for r in _rows(page)] == [("A", "1")]
    _wait_status(page, w, fid2, "filled")
    page.locator(SAVE).click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    saved = _get_source(w.base, sid)["config"]
    assert saved["args"] == ["--flag"] and saved["command"] == "echo"
    assert saved["cwd"] == "/tmp/keep-me" and saved["env"] == {"A": "1"}


# ── AC7: the operator's edits win ────────────────────────────────────────────


def test_a_field_and_the_command_group_the_operator_changed_are_kept_and_named(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    sid = _seed_http(w.base, "Docs")
    _open_edit(page, sid)
    page.locator(URL).fill("https://mine.test/mcp")
    fid = _fill(
        w,
        "change",
        {"url": "https://gg.test/mcp", "name": "Docs renamed"},
        target_id=sid,
        base={"url": "https://example.com/mcp", "name": "Docs"},
    )
    _deliver(page, w, fid)
    expect(page.locator(NAME)).to_have_value("Docs renamed", timeout=10000)
    expect(page.locator(URL)).to_have_value("https://mine.test/mcp")
    done = _wait_status(page, w, fid, "partly_filled")
    assert done["outcome"] == {"kept": ["url"], "reason": None}
    expect(page.locator(f'{NOTE}[data-field="name"]')).to_have_count(1)
    expect(page.locator(f'{NOTE}[data-field="url"]')).to_have_count(0)

    # The command and its arguments are one group, kept together and reported as "command".
    page.locator('[data-testid="cancel-mcp-source-btn"]').click()  # the guard would ask otherwise
    expect(page.locator(UNSAVED)).to_have_text("")
    stdio = _seed_stdio(w.base, "Local")
    _open_edit(page, stdio)
    page.locator('[data-testid="mcp-args-add-row-btn"]').click()
    page.locator(ARGS_INPUT).first.fill("mine")
    fid2 = _fill(
        w,
        "change",
        {"command": "uvx", "args": ["gg-arg"]},
        target_id=stdio,
        base={"command": "echo"},
        tool_call_id="tc-2",
    )
    _deliver(page, w, fid2)
    done2 = _wait_status(page, w, fid2, "partly_filled")
    assert done2["outcome"] == {"kept": ["command"], "reason": None}
    expect(page.locator("#mf-command")).to_have_value("echo")
    expect(page.locator(ARGS_INPUT).first).to_have_value("mine")
    # The receipts (held while the turn ran) name the kept fields.
    _done(page)
    expect(_drawer_receipt(page, fid).locator(KEPT)).to_contain_text("URL")
    expect(_drawer_receipt(page, fid2).locator(KEPT)).to_contain_text("Command")


def test_a_dirty_editor_on_another_server_asks_the_guard_and_stay_writes_nothing(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    first = _seed_http(w.base, "First")
    second = _seed_http(w.base, "Second")
    _open_edit(page, first)
    page.locator(NAME).fill("typed by me")
    expect(page.locator(UNSAVED)).to_have_text("Unsaved changes")
    fid = _fill(w, "change", {"url": "https://gg.test/mcp"}, target_id=second, base={})
    _deliver(page, w, fid)
    expect(page.locator(_drawer.STAY)).to_be_visible(timeout=8000)
    page.locator(_drawer.STAY).click()
    done = _wait_status(page, w, fid, "not_filled")
    assert done["outcome"] == {"kept": [], "reason": "stay"}
    expect(page.locator(NAME)).to_have_value("typed by me")
    expect(page.locator(URL)).to_have_value("https://example.com/mcp")
    assert _get_source(w.base, second)["config"]["url"] == "https://example.com/mcp"


def test_a_row_that_is_there_is_kept_and_the_handoff_never_replaces_it(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    sid = _seed_mcp_source(
        w.base,
        {
            "name": "Docs",
            "type": "streamable-http",
            "config": {
                "url": "https://example.com/mcp",
                "headers": {"X-Api-Key": "plain-on-server", "Accept": "a/b"},
            },
            "secrets": {},
        },
    )
    _open_edit(page, sid)
    # The operator types a value into a row of their own.
    page.locator('[data-testid="kv-add-row-btn"]').click()
    row = _kv_rows(page).last
    row.locator("td").nth(0).locator("input").fill("X-Mine")
    _kv_val(row).fill("operator-typed")
    fid = _fill(
        w,
        "change",
        {"headers": {"x-api-key": "", "X-Mine": "from-gg", "Accept": "c/d"}},
        target_id=sid,
        base={"headers": {"Accept": "a/b"}},
    )
    _deliver(page, w, fid)
    done = _wait_status(page, w, fid, "partly_filled")
    assert done["outcome"] == {"kept": ["headers"], "reason": None}
    by_key = {r["key"]: r for r in _rows(page)}
    # The plain row on the server stays plain and keeps its value; the operator's row is theirs;
    # the clean row took the fill.
    assert (
        by_key["X-Api-Key"]["value"] == "plain-on-server" and not by_key["X-Api-Key"]["sensitive"]
    )
    assert by_key["X-Mine"]["value"] == "operator-typed"
    assert by_key["Accept"]["value"] == "c/d"
    assert len(by_key) == 3


# ── Target gone ──────────────────────────────────────────────────────────────


def test_a_change_fill_for_a_deleted_server_is_target_gone(
    app_with_data_dir: tuple[str, Any], page: Page
) -> None:
    w = _world(app_with_data_dir, page)
    sid = _seed_http(w.base, "Short lived")
    fid = _fill(w, "change", {"url": "https://gg.test/mcp"}, target_id=sid, base={})
    r = httpx.delete(
        f"{w.base}/api/mcp-sources/{sid}", headers=auth_headers_for(w.base), timeout=5.0
    )
    assert r.status_code in (200, 204), r.text
    _deliver(page, w, fid)
    done = _wait_status(page, w, fid, "not_filled")
    assert done["outcome"] == {"kept": [], "reason": "target_gone"}
    _done(page)
    expect(_drawer_receipt(page, fid)).to_contain_text("no longer exists")
    expect(
        _drawer_receipt(page, fid).locator('[data-testid="fill-receipt-fill-now"]')
    ).to_have_count(0)
