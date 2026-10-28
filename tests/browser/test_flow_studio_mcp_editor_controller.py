# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""MCP source editor browser tests: review fixes and the editor controller.

Split from test_flow_studio_mcp_editor.py (squawk 0271); shared helpers live in
browser/_mcp_editor.py."""

from __future__ import annotations

import json
import re

import pytest
from browser import _lists, _nav
from browser._mcp_editor import (
    _ED,
    _OK_TOOLS,
    _RESULT,
    _cache,
    _count,
    _expect_clean,
    _fake_open,
    _get_source,
    _hold_requests,
    _http_source,
    _info_cache,
    _install_counter,
    _kv_add,
    _list_sources,
    _open,
    _open_editor,
    _open_source,
    _save_edit,
    _seed_mcp_source,
    _seed_oauth_source,
    _seed_state,
    _seed_stdio,
    _stub_signin_routes,
    _wait_held,
    _yield_macrotasks,
)
from playwright.sync_api import Page, expect

_NAME = '[data-field="name"]'


_SAVE = '[data-testid="save-mcp-source-btn"]'


_CANCEL = '[data-testid="cancel-mcp-source-btn"]'


_TEST = '[data-testid="mcp-test-connection"]'


_ERROR = ".editor-header .editor-error"


_SUBTITLE = '[data-testid="mcp-editor-subtitle"]'


_TITLES_JS = """() => Array.from(document.querySelectorAll('#main-content .editor-section .section-title'))
  .filter(e => e.getClientRects().length > 0)
  .map(e => e.textContent.trim())"""


def _mock_if_held(page: Page, sid: str, method: str = "PUT") -> list:
    _install_counter(page)
    return _hold_requests(page, f"**/api/mcp-sources/{sid}", method)


_BASELINE_SEEDS = [
    ("uvx", {"command": "uvx", "args": ["pkg", "--flag"]}),
    ("npx", {"command": "npx", "args": ["-y", "@scope/pkg"]}),
    ("pipx", {"command": "pipx", "args": ["run", "tool"]}),
    ("custom", {"command": "bash /app/start.sh", "args": []}),
    ("no-args", {"command": "uvx"}),
    ("empty-cwd", {"command": "uvx", "cwd": "", "args": ["a"]}),
    ("dup-arg", {"command": "uvx", "args": ["a", "a", "b"]}),
    (
        "dup-path",
        {
            "command": "uvx",
            "args": ["a"],
            "sandbox": {"network_allowed": False, "writable_paths": ["/x", "/x", "/y"]},
        },
    ),
    ("net-off", {"command": "uvx", "sandbox": {"network_allowed": False, "writable_paths": []}}),
]


# ── Batch B4 review fixes ────────────────────────────────────────────


@pytest.mark.browser
def test_malformed_cached_tools_render_without_error(app_clean: str, page: Page) -> None:
    """A cache with a numeric description, a null entry and an object description
    still renders the Tools list (null entries are skipped, descriptions coerced)."""
    cache = _cache(tools=False)
    cache["tools"] = [
        {"name": "num", "description": 12345, "input_schema": {}},
        None,
        {"name": "obj", "description": {"a": 1}, "input_schema": {}},
        {"name": "ok", "description": "fine", "input_schema": {}},
    ]
    cache["capabilities"] = {"tools": {}}
    sid = _seed_state(app_clean, "malformed-tools", cache=cache)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _open(page, app_clean, sid)
    items = page.locator('[data-testid="mcp-tools-list"] [data-testid="mcp-tool-item"]')
    expect(items).to_have_count(3)
    expect(items.nth(0)).to_contain_text("12345")
    assert errors == []


@pytest.mark.browser
def test_test_result_uses_one_persistent_live_region(app_clean: str, page: Page) -> None:
    """WCAG 4.1.3: the announcer node is created at mount, kept across a Test (same
    element), holds the transient text, and a failed Test's error block carries no
    assertive role."""
    sid = _seed_state(app_clean, "live-region")
    _install_counter(page)
    held = _hold_requests(page, re.compile(rf".*/api/mcp-sources/{sid}/test/connect$"), "POST")
    _open(page, app_clean, sid)
    live = '[data-testid="mcp-test-live"]'
    expect(page.locator(live)).to_have_attribute("role", "status")
    page.evaluate(f"() => {{ document.querySelector('{live}').__ident = 7; }}")
    page.locator('[data-testid="mcp-test-connection"]').click()
    _wait_held(page, held, "POST", f"/api/mcp-sources/{sid}/test/connect")
    expect(page.locator(live)).to_have_text("Testing connection…")
    held[0].fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"status": "error", "error": "MCPConnectionError: refused"}),
    )
    err = page.locator('[data-testid="mcp-connection-error"]')
    expect(err).to_be_visible()
    assert page.evaluate(f"() => document.querySelector('{live}').__ident") == 7
    assert err.get_attribute("role") is None
    # The result area has no alert of its own (the shell's editor error is a separate,
    # empty role=alert region in the header).
    expect(page.locator(f'{_RESULT} [role="alert"]')).to_have_count(0)


@pytest.mark.browser
def test_build_mcp_error_live_option(app_clean: str, page: Page) -> None:
    """buildMcpError keeps role=alert by default; live 'status' and 'none' are honoured."""
    sid = _seed_state(app_clean, "live-opt")
    _open(page, app_clean, sid)
    roles = page.evaluate(
        """() => ['alert', 'status', 'none', undefined].map(function (l) {
          var o = l === undefined ? {} : { live: l };
          return window.App.buildMcpError('MCPConnectionError: x', o).getAttribute('role');
        })"""
    )
    assert roles == ["alert", "status", None, "alert"]


@pytest.mark.browser
@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (
            "stdio",
            ["Connection", "Environment variables", "Sandbox", "Server", "Tools", "Danger zone"],
        ),
        ("streamable-http", ["Connection", "Headers", "Server", "Tools", "Danger zone"]),
    ],
)
def test_l10_sections_follow_the_b1_order(
    app_clean: str, page: Page, kind: str, expected: list
) -> None:
    """B1: Connection, Environment variables or Headers, Sandbox, Server, Tools, Danger zone."""
    if kind == "stdio":
        sid = _seed_mcp_source(
            app_clean,
            {
                "name": "b1-stdio",
                "type": "stdio",
                "config": {"command": "echo", "env": {}, "_cache": _info_cache()},
                "secrets": {},
            },
        )
    else:
        sid = _seed_state(app_clean, "b1-http", cache=_info_cache())
    _open_source(page, app_clean, sid)
    expect(page.locator('[data-testid="mcp-tools-section"]')).to_be_visible()
    assert page.evaluate(_TITLES_JS) == expected


@pytest.mark.browser
def test_l10_cancel_after_save_reverts_to_the_saved_values(app_clean: str, page: Page) -> None:
    """Defect 3: Cancel reverts to the last SAVED row, not the mount-time one."""
    sid = _seed_stdio(app_clean, "d3-a")
    _open_source(page, app_clean, sid)
    page.locator(_NAME).fill("d3-saved")
    page.locator('[data-field="cwd"]').fill("/tmp/saved")
    _save_edit(page)
    _expect_clean(page)
    page.locator(_NAME).fill("d3-junk")
    page.locator('[data-field="cwd"]').fill("/tmp/junk")
    page.locator(_CANCEL).click()
    expect(page.locator(_NAME)).to_have_value("d3-saved")
    expect(page.locator('[data-field="cwd"]')).to_have_value("/tmp/saved")
    expect(page.locator(".editor-title")).to_have_text("d3-saved")
    _expect_clean(page)
    expect(page.locator(_CANCEL)).to_be_disabled()


@pytest.mark.browser
def test_l10_second_save_keeps_a_secret_the_first_save_added(app_clean: str, page: Page) -> None:
    """Defect 3: Save adds a secret, an edit is cancelled, a second Save keeps the secret."""
    sid = _seed_mcp_source(app_clean, _http_source("d3-b"))
    _open_source(page, app_clean, sid)
    _kv_add(page, "X-Sec", "secret-value-1234", sensitive=True)
    _save_edit(page)
    page.locator(_NAME).fill("d3-b-junk")
    page.locator(_CANCEL).click()
    expect(page.locator(_NAME)).to_have_value("d3-b")
    page.locator(_NAME).fill("d3-b-renamed")
    _save_edit(page)
    src = _get_source(app_clean, sid)
    assert src["name"] == "d3-b-renamed"
    assert src["secrets"]["X-Sec"].endswith("1234")


@pytest.mark.browser
def test_l10_double_click_on_create_sends_one_post(app_clean: str, page: Page) -> None:
    """Defect 5: a second click while the POST is held sends nothing."""
    _install_counter(page)
    held = _hold_requests(page, "**/api/mcp-sources", "POST")
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator(_SAVE)).to_be_visible(timeout=8000)
    page.locator(_NAME).fill("d5-create")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command-runtime"]').select_option("__custom__")
    page.locator('[data-field="command"]').fill("echo")
    page.evaluate(
        "() => { const b = document.querySelector('[data-testid=\"save-mcp-source-btn\"]');"
        " b.click(); b.click(); }"
    )
    _wait_held(page, held, "POST", "/api/mcp-sources")
    _yield_macrotasks(page)
    assert _count(page, "POST", "/api/mcp-sources") == 1
    expect(page.locator(_SAVE)).to_be_disabled()
    expect(page.locator(_CANCEL)).to_be_disabled()
    held[0].continue_()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)
    assert len([s for s in _list_sources(app_clean) if s["name"] == "d5-create"]) == 1


@pytest.mark.browser
def test_l10_save_cancel_and_test_are_busy_while_an_edit_save_is_held(
    app_clean: str, page: Page
) -> None:
    """Defect 5 (row 33): Save, Cancel and Test are disabled while a PUT is in flight."""
    sid = _seed_state(app_clean, "d5-edit")
    held = _mock_if_held(page, sid)
    _open_source(page, app_clean, sid)
    page.locator(_NAME).fill("d5-edit-2")
    page.locator(_SAVE).click()
    _wait_held(page, held, "PUT", f"/api/mcp-sources/{sid}")
    for sel in (_SAVE, _CANCEL, _TEST):
        expect(page.locator(sel)).to_be_disabled()
    # The fields stay editable during a Save.
    expect(page.locator(_NAME)).to_be_editable()
    held[0].continue_()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    expect(page.locator(_TEST)).to_be_enabled()
    _expect_clean(page)


@pytest.mark.browser
def test_l10_a_throwing_create_callback_is_not_a_failed_save(app_clean: str, page: Page) -> None:
    """Review fix: the record WAS created, so a throw in the glue's onSaveSuccess is logged,
    not shown as a save error, and Save is not left busy (mirrors the edit path)."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator(_SAVE)).to_be_visible(timeout=8000)
    page.locator(_NAME).fill("cb-throw")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command-runtime"]').select_option("__custom__")
    page.locator('[data-field="command"]').fill("echo")
    # The glue calls App.router.sync from onSaveSuccess: make it throw once.
    page.evaluate(
        "() => { const o = App.router.sync;"
        " App.router.sync = function () { App.router.sync = o; throw new Error('boom'); }; }"
    )
    page.locator(_SAVE).click()
    expect(page.locator(".app-flash")).to_contain_text("created", timeout=8000)
    assert len([s for s in _list_sources(app_clean) if s["name"] == "cb-throw"]) == 1
    expect(page.locator(_ERROR)).to_have_text("")
    expect(page.locator(_SAVE)).to_be_enabled()
    expect(page.locator(_CANCEL)).to_be_enabled()


@pytest.mark.browser
def test_l10_delete_cannot_run_while_an_edit_save_is_held(app_clean: str, page: Page) -> None:
    """Review fix: the danger-zone Delete follows the Save busy state, so it cannot be
    armed and confirmed while a PUT is in flight; it is enabled again afterwards."""
    sid = _seed_state(app_clean, "del-busy")
    held = _mock_if_held(page, sid)
    _open_source(page, app_clean, sid)
    delete_btn = page.locator('[data-testid="delete-mcp-source-btn"]')
    page.locator(_NAME).fill("del-busy-2")
    page.locator(_SAVE).click()
    _wait_held(page, held, "PUT", f"/api/mcp-sources/{sid}")
    expect(delete_btn).to_be_disabled()
    page.evaluate(
        "() => { const b = document.querySelector('[data-testid=\"delete-mcp-source-btn\"]');"
        " b.click(); b.click(); }"
    )
    _yield_macrotasks(page)
    assert _count(page, "DELETE", f"/api/mcp-sources/{sid}") == 0
    held[0].continue_()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    expect(delete_btn).to_be_enabled()
    assert any(s["id"] == sid for s in _list_sources(app_clean))


@pytest.mark.browser
def test_l10_required_name_and_url_errors_go_on_the_fields(app_clean: str, page: Page) -> None:
    """A2 / defect 10: each empty required field shows its message on the field; focus
    moves to the first; no request is made; the message clears when the field changes."""
    _install_counter(page)
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator(_SAVE)).to_be_visible(timeout=8000)
    page.locator('[data-field="type"]').select_option("streamable-http")
    page.locator(_SAVE).click()
    expect(page.locator(_NAME)).to_have_attribute("aria-invalid", "true")
    expect(page.locator(_NAME)).to_have_accessible_description("Enter a name.")
    expect(page.locator('[data-field="url"]')).to_have_accessible_description(
        "Enter the server's URL."
    )
    expect(page.locator(_NAME)).to_be_focused()
    expect(page.locator(_ERROR)).to_have_text("")
    _yield_macrotasks(page)
    assert _count(page, "POST", "/api/mcp-sources") == 0
    page.locator(_NAME).fill("a")
    expect(page.locator(_NAME)).not_to_have_attribute("aria-invalid", "true")
    expect(page.locator('[data-field="url"]')).to_have_attribute("aria-invalid", "true")
    page.locator('[data-field="url"]').fill("https://x.example/mcp")
    expect(page.locator('[data-field="url"]')).not_to_have_attribute("aria-invalid", "true")


@pytest.mark.browser
def test_l10_required_type_and_command_errors(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator(_SAVE)).to_be_visible(timeout=8000)
    page.locator(_NAME).fill("needs-type")
    page.locator(_SAVE).click()
    expect(page.locator('[data-field="type"]')).to_have_accessible_description(
        "Choose how it connects."
    )
    expect(page.locator('[data-field="type"]')).to_be_focused()
    page.locator('[data-field="type"]').select_option("stdio")
    expect(page.locator('[data-field="type"]')).not_to_have_attribute("aria-invalid", "true")
    page.locator('[data-field="command-runtime"]').select_option("__custom__")
    page.locator(_SAVE).click()
    expect(page.locator('[data-field="command"]')).to_have_accessible_description(
        "Choose or enter a command."
    )
    expect(page.locator('[data-field="command"]')).to_be_focused()


@pytest.mark.browser
def test_l10_server_422_reaches_its_field_and_the_rest_the_editor_error(
    app_clean: str, page: Page
) -> None:
    """Defect 10: a 422 `loc` goes to its field, a string detail and the rest go to the
    editor error (role=alert); both together split."""
    sid = _seed_state(app_clean, "d10")
    reply: dict = {}

    def handle(route):
        if route.request.method != "PUT":
            return route.fallback()
        route.fulfill(status=422, content_type="application/json", body=json.dumps(reply))

    page.route(f"**/api/mcp-sources/{sid}", handle)
    _open_source(page, app_clean, sid)
    page.locator('[data-field="url"]').fill("ftp://bad")
    reply["detail"] = [
        {"loc": ["body", "config", "url"], "msg": "Value error, not a web address", "type": "x"}
    ]
    page.locator(_SAVE).click()
    expect(page.locator('[data-field="url"]')).to_have_attribute("aria-invalid", "true")
    expect(page.locator('[data-field="url"]')).to_have_accessible_description(
        re.compile("not a web address")
    )
    expect(page.locator(_ERROR)).to_have_text("")
    expect(page.locator(_SAVE)).to_be_enabled()

    reply["detail"] = "Command is not allowed here"
    page.locator(_SAVE).click()
    expect(page.locator(_ERROR)).to_contain_text("Command is not allowed here")
    expect(page.locator(_ERROR)).to_have_attribute("role", "alert")
    expect(page.locator('[data-field="url"]')).not_to_have_attribute("aria-invalid", "true")

    reply["detail"] = [
        {"loc": ["body", "name"], "msg": "String should have at least 1 character", "type": "x"},
        {"loc": [], "msg": "Another problem", "type": "x"},
    ]
    page.locator(_SAVE).click()
    expect(page.locator(_NAME)).to_have_attribute("aria-invalid", "true")
    expect(page.locator(_ERROR)).to_contain_text("Another problem")
    expect(page.locator(_ERROR)).not_to_contain_text("at least 1 character")


@pytest.mark.browser
def test_l10_subtitle_uses_the_type_label_and_follows_a_save(app_clean: str, page: Page) -> None:
    """A4 / defect 12."""
    sid = _seed_state(app_clean, "a4-http")
    _open_source(page, app_clean, sid)
    expect(page.locator(_SUBTITLE)).to_have_text("Remote server (HTTP) · https://example.com/mcp")
    page.locator('[data-field="url"]').fill("https://other.example/mcp")
    _save_edit(page)
    expect(page.locator(_SUBTITLE)).to_have_text("Remote server (HTTP) · https://other.example/mcp")
    sid2 = _seed_stdio(app_clean, "a4-stdio")
    _open_source(page, app_clean, sid2)
    expect(page.locator(_SUBTITLE)).to_have_text("Local program (stdio) · echo")
    page.locator('[data-field="command"]').fill("echo2")
    _save_edit(page)
    expect(page.locator(_SUBTITLE)).to_have_text("Local program (stdio) · echo2")
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator(_SAVE)).to_be_visible(timeout=8000)
    expect(page.locator(_SUBTITLE)).to_have_count(0)


@pytest.mark.browser
def test_l10_copy_is_sentence_case(app_clean: str, page: Page) -> None:
    """A3: titles, flashes, the delete button and the danger zone."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator(".editor-title")).to_have_text("New MCP server", timeout=8000)
    page.locator(_NAME).fill("a3-copy")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command-runtime"]').select_option("__custom__")
    page.locator('[data-field="command"]').fill("echo")
    # The create's remount replaces the flash at once, so record the texts shown.
    page.evaluate(
        "() => { window.__flashes = []; new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach("
        "n => { if (n.classList && n.classList.contains('app-flash')) __flashes.push(n.textContent); }))"
        ").observe(document.body, {childList: true, subtree: true}); }"
    )
    page.locator(_SAVE).click()
    page.wait_for_function("() => window.__flashes.includes('MCP server created')")
    delete_btn = page.locator('[data-testid="delete-mcp-source-btn"]')
    expect(delete_btn).to_have_text("Delete MCP server", timeout=8000)
    expect(page.locator(".danger-zone-title")).to_have_text("Danger zone")
    page.locator(_NAME).fill("a3-copy-2")
    page.locator(".app-flash").evaluate_all("els => els.forEach(e => e.remove())")
    page.locator(_SAVE).click()
    expect(page.locator(".app-flash")).to_have_text("MCP server saved", timeout=8000)
    delete_btn.click()
    expect(delete_btn).to_have_text("Confirm delete?")
    delete_btn.click()
    expect(_lists.library_start(page)).to_be_visible(timeout=5000)


@pytest.mark.browser
def test_l10_delete_error_shows_in_the_editor_error_and_reverts(app_clean: str, page: Page) -> None:
    """Row 29: a failed Delete is the editor error, not a toast; the button reverts and
    takes focus back."""
    sid = _seed_stdio(app_clean, "row29")

    def handle(route):
        if route.request.method != "DELETE":
            return route.fallback()
        route.fulfill(
            status=500,
            content_type="application/json",
            body=json.dumps({"detail": "Could not delete: still in use"}),
        )

    page.route(f"**/api/mcp-sources/{sid}", handle)
    _open_source(page, app_clean, sid)
    delete_btn = page.locator('[data-testid="delete-mcp-source-btn"]')
    delete_btn.click()
    delete_btn.click()
    expect(page.locator(_ERROR)).to_contain_text("Could not delete: still in use", timeout=8000)
    expect(page.locator(_ERROR)).to_have_attribute("role", "alert")
    expect(page.locator(".app-flash")).to_have_count(0)
    expect(delete_btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"))
    expect(delete_btn).to_have_text("Delete MCP server")
    expect(delete_btn).to_be_focused()
    assert any(s["id"] == sid for s in _list_sources(app_clean))


@pytest.mark.browser
def test_l10_typing_during_a_running_test_keeps_test_disabled(app_clean: str, page: Page) -> None:
    """One Test-hold writer: a keystroke (a dirty change) must not re-enable a running Test."""
    sid = _seed_state(app_clean, "hold-typing")
    held = _hold_requests(page, f"**/api/mcp-sources/{sid}/test/connect", "POST")
    _install_counter(page)
    _open_source(page, app_clean, sid)
    page.locator(_TEST).click()
    _wait_held(page, held, "POST", f"/api/mcp-sources/{sid}/test/connect")
    expect(page.locator(_TEST)).to_be_disabled()
    expect(page.locator(_TEST)).to_have_text("Test")
    page.locator(_NAME).press_sequentially("xyz")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    expect(page.locator(_TEST)).to_be_disabled()
    held[0].fulfill(status=200, content_type="application/json", body=json.dumps(_OK_TOOLS))
    expect(page.locator(_TEST)).to_be_enabled(timeout=8000)


@pytest.mark.browser
def test_l10_mounts_without_a_test_button_throw_nothing(app_clean: str, page: Page) -> None:
    """Create mode and a legacy-type mount have no Test; runTest is a quiet no-op."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator(_SAVE)).to_be_visible(timeout=8000)
    expect(page.locator(_TEST)).to_have_count(0)
    page.evaluate(f"() => {{ {_ED}.runTest({{}}); {_ED}.runTest({{autoRun: true}}); }}")
    result = page.evaluate(
        """() => {
          const host = document.createElement('div');
          document.body.appendChild(host);
          const types = [{value: 'stdio', label: 'Local program (stdio)'}];
          let error = null, ctl = null;
          try {
            ctl = App.studio.renderMcpSourceEditor(
              host, {id: 'legacy-1', name: 'leg', type: 'weird', config: {command: 'x'}},
              types, {});
            ctl.runTest({});
          } catch (e) { error = String(e); }
          const out = {
            error: error,
            tests: host.querySelectorAll('[data-testid="mcp-test-connection"]').length,
            subtitle: (host.querySelector('.editor-subtitle') || {}).textContent
          };
          if (ctl) ctl.destroy();
          host.remove();
          return out;
        }"""
    )
    assert result == {"error": None, "tests": 0, "subtitle": "weird"}


@pytest.mark.browser
def test_l10_leaving_during_a_session_leaves_the_next_mount_with_a_plain_test(
    app_clean: str, page: Page
) -> None:
    """After a session on a mount that is then destroyed, the NEXT mount's Test reads
    "Test" and is enabled (a dead mount's button is no longer rewritten)."""
    sid = _seed_oauth_source(app_clean, "hold-leave")
    other = _seed_stdio(app_clean, "hold-leave-b")
    _stub_signin_routes(page, app_clean, sid)
    _open_editor(page, app_clean, sid)
    _fake_open(page)
    page.locator(_TEST).click()
    expect(page.locator(_TEST)).to_have_text("Waiting for sign-in…", timeout=8000)
    _lists.open_item(page, "library/mcp", "hold-leave-b")
    expect(page.locator(".editor-title")).to_have_text("hold-leave-b", timeout=8000)
    _lists.open_item(page, "library/mcp", "hold-leave")
    expect(page.locator(".editor-title")).to_have_text("hold-leave", timeout=8000)
    expect(page.locator(_TEST)).to_have_text("Test")
    expect(page.locator(_TEST)).to_be_enabled()
    assert other


@pytest.mark.browser
def test_l10_baseline_from_equals_values_after_set_values(app_clean: str, page: Page) -> None:
    """baselineFrom(src) is exactly what values() reads after setValues(src), for every
    capture seed shape, a legacy type and null (the create defaults)."""
    _nav.goto_settled(page, app_clean, "library")
    seeds = [{"type": "stdio", "name": n, "config": c} for n, c in _BASELINE_SEEDS]
    seeds += [
        {"type": "streamable-http", "name": "http", "config": {"url": "https://x.example/mcp"}},
        {
            "type": "streamable-http",
            "name": "http-hdr",
            "config": {"url": "u", "headers": {"A": "b"}},
        },
        {"type": "weird", "name": "legacy", "config": {"command": "x", "args": ["q", "q"]}},
        None,
    ]
    out = page.evaluate(
        """(seeds) => {
          const cf = App.studio.mcpEditor.connectionFields, sf = App.studio.mcpEditor.sandboxFields;
          const types = [{value: 'stdio', label: 'Local program (stdio)'},
                         {value: 'streamable-http', label: 'Remote server (HTTP)'}];
          const bad = [];
          seeds.forEach((s, i) => {
            const c = cf.create({source: s, mcpTypes: types});
            const sb = sf.create({source: s});
            if (typeof c.baselineFrom !== 'function' || typeof sb.baselineFrom !== 'function') {
              bad.push([i, 'missing baselineFrom']); return;
            }
            c.setValues(s); sb.setValues(s);
            if (JSON.stringify(c.baselineFrom(s)) !== JSON.stringify(c.values())) {
              bad.push([i, 'connection', JSON.stringify(c.baselineFrom(s)), JSON.stringify(c.values())]);
            }
            if (JSON.stringify(sb.baselineFrom(s)) !== JSON.stringify(sb.values())) {
              bad.push([i, 'sandbox', JSON.stringify(sb.baselineFrom(s)), JSON.stringify(sb.values())]);
            }
            c.destroy(); sb.destroy();
          });
          return bad;
        }""",
        seeds,
    )
    assert out == []


@pytest.mark.browser
@pytest.mark.parametrize(("label", "config"), _BASELINE_SEEDS, ids=[s[0] for s in _BASELINE_SEEDS])
def test_l10_a_clean_stdio_mount_is_never_dirty(
    app_clean: str, page: Page, label: str, config: dict
) -> None:
    """A keystroke and its undo leave an untouched mount clean (the baseline matches)."""
    sid = _seed_mcp_source(
        app_clean,
        {"name": f"clean-{label}", "type": "stdio", "config": {**config, "env": {}}, "secrets": {}},
    )
    _open_source(page, app_clean, sid)
    page.locator(_NAME).press("End")
    page.locator(_NAME).press_sequentially("z")
    expect(page.locator(_SAVE)).to_be_enabled()
    page.locator(_NAME).press("Backspace")
    _expect_clean(page)


@pytest.mark.browser
def test_l10_a_clean_http_mount_is_never_dirty(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(app_clean, _http_source("clean-http", headers={"A": "b"}))
    _open_source(page, app_clean, sid)
    page.locator(_NAME).press("End")
    page.locator(_NAME).press_sequentially("z")
    expect(page.locator(_SAVE)).to_be_enabled()
    page.locator(_NAME).press("Backspace")
    _expect_clean(page)


@pytest.mark.browser
def test_l10_a_field_edited_during_a_held_save_stays_dirty(app_clean: str, page: Page) -> None:
    """The submitted edit is clean after the Save; a field edited while the PUT was held
    keeps its text and stays dirty; an untouched form is clean."""
    sid = _seed_stdio(app_clean, "held-field")
    held = _mock_if_held(page, sid)
    _open_source(page, app_clean, sid)
    page.locator(_NAME).fill("held-field-2")
    page.locator(_SAVE).click()
    _wait_held(page, held, "PUT", f"/api/mcp-sources/{sid}")
    page.locator('[data-field="cwd"]').fill("/during")
    held[0].continue_()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    expect(page.locator('[data-field="cwd"]')).to_have_value("/during")
    expect(page.locator(_NAME)).to_have_value("held-field-2")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    expect(page.locator(_SAVE)).to_be_enabled()
    assert _get_source(app_clean, sid)["name"] == "held-field-2"
    assert "cwd" not in _get_source(app_clean, sid)["config"]
    # Cancel returns to the saved row.
    page.locator(_CANCEL).click()
    expect(page.locator('[data-field="cwd"]')).to_have_value("")
    _expect_clean(page)


@pytest.mark.browser
def test_l10_an_untouched_form_is_clean_after_a_held_save(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "held-clean",
            "type": "stdio",
            "config": {"command": "uvx", "args": ["a", "a", "b"], "env": {}},
            "secrets": {},
        },
    )
    held = _mock_if_held(page, sid)
    _open_source(page, app_clean, sid)
    page.locator(_NAME).fill("held-clean-2")
    page.locator(_SAVE).click()
    _wait_held(page, held, "PUT", f"/api/mcp-sources/{sid}")
    held[0].continue_()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    _expect_clean(page)
