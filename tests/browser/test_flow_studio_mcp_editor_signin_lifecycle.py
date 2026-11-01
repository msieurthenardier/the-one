# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""MCP source editor browser tests: honest sign-in and the editor lifecycle.

Split from test_flow_studio_mcp_editor.py (squawk 0271); shared helpers live in
browser/_mcp_editor.py."""

from __future__ import annotations

import json
import re

import pytest
from browser import _lists, _nav
from browser._mcp_editor import (
    _CONSENT_URL,
    _ED,
    _OK_TOOLS,
    _count,
    _fake_open,
    _get_source,
    _hold_requests,
    _install_counter,
    _list_sources,
    _open_editor,
    _seed_http,
    _seed_oauth_source,
    _seed_stdio,
    _stub_signin_routes,
    _wait_held,
    _yield_macrotasks,
)
from playwright.sync_api import Page, expect


def _leave_confirm(page: Page) -> None:
    page.locator('[data-testid="modal-confirm-btn"]').click()
    expect(page.locator(".modal-overlay")).to_have_count(0)


def _stub_poll_routes(page: Page, sid_re: str = r"[0-9a-f]{8,}") -> None:
    """Per-id GET answers with ``has_access_token`` false; ``/test/connect`` answers
    auth_required. Both are what a pending sign-in looks like."""

    def handle_get(route):
        if route.request.method != "GET":
            return route.fallback()
        resp = route.fetch()
        body = resp.json()
        body["has_access_token"] = False
        route.fulfill(response=resp, json=body)

    def handle_connect(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "auth_required", "consent_url": _CONSENT_URL}),
        )

    page.route(re.compile(rf".*/api/mcp-sources/{sid_re}$"), handle_get)
    page.route(re.compile(rf".*/api/mcp-sources/{sid_re}/test/connect$"), handle_connect)


def _start_poll(page: Page, sid: str) -> None:
    """Click Test on an editor whose connect answers auth_required, and let at
    least one poll GET land (the positive control)."""
    _fake_open(page)
    path = f"/api/mcp-sources/{sid}"
    before = _count(page, "GET", path)
    page.locator('[data-testid="mcp-test-connection"]').click()
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_have_count(1, timeout=8000)
    page.clock.run_for(1600)
    assert _count(page, "GET", path) > before, "the sign-in poll never ran"


@pytest.mark.browser
def test_null_popup_shows_link_block_keeps_polling_and_lists_tools(
    app_clean: str, page: Page
) -> None:
    """window.open -> null (the desktop webview, or a popup blocker) shows the link
    block and keeps waiting; once the token lands the tools list with no re-test."""
    sid = _seed_oauth_source(app_clean, "null-popup")
    state = _stub_signin_routes(page, app_clean, sid)
    _open_editor(page, app_clean, sid)
    page.evaluate(
        "() => { window.__opens = []; window.open = (u) => { __opens.push(u); return null; }; }"
    )

    page.locator('[data-testid="mcp-test-connection"]').click()
    url_input = page.locator('[data-testid="mcp-consent-link-url"]')
    expect(url_input).to_have_value(_CONSENT_URL, timeout=8000)
    anchor = page.locator('[data-testid="mcp-consent-link-open"]')
    expect(anchor).to_have_attribute("href", _CONSENT_URL)
    expect(anchor).to_have_attribute("target", "_blank")
    expect(anchor).to_have_attribute("rel", "noopener noreferrer")
    status = page.locator('[data-testid="mcp-test-status"]')
    expect(status).not_to_contain_text("Popup blocked")
    expect(status).to_contain_text("Waiting for sign-in")
    assert page.evaluate("() => window.__opens") == [_CONSENT_URL]

    state["token"] = True
    expect(
        page.locator('[data-testid="mcp-tools-list"] [data-testid="mcp-tool-item"]')
    ).to_have_count(1, timeout=10000)
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_have_count(0)
    expect(status).to_be_hidden()
    expect(page.locator('[data-testid="mcp-tools-list"]')).to_be_visible()
    assert state["connects"] == 2


@pytest.mark.browser
def test_status_live_region_exists_empty_before_its_first_text(app_clean: str, page: Page) -> None:
    sid = _seed_oauth_source(app_clean, "live-region")
    _stub_signin_routes(page, app_clean, sid)
    _open_editor(page, app_clean, sid)
    page.evaluate(
        """() => {
          window.open = () => null;
          window.__seen = [];
          new MutationObserver((muts) => {
            for (const m of muts) for (const n of m.addedNodes) {
              if (n.nodeType === 1 && n.classList.contains('mcp-consent-status-text')) {
                window.__seen.push({role: n.getAttribute('role'), text: n.textContent});
              }
            }
          }).observe(document.body, {childList: true, subtree: true});
        }"""
    )
    page.locator('[data-testid="mcp-test-connection"]').click()
    status = page.locator('[data-testid="mcp-test-status"]')
    expect(status).to_contain_text("Waiting for sign-in", timeout=8000)
    seen = page.evaluate("() => window.__seen")
    assert seen and seen[0] == {"role": "status", "text": ""}


@pytest.mark.browser
def test_success_after_sign_in_moves_focus_from_the_block_to_refresh(
    app_clean: str, page: Page
) -> None:
    sid = _seed_oauth_source(app_clean, "focus-success")
    state = _stub_signin_routes(page, app_clean, sid)
    _open_editor(page, app_clean, sid)
    page.evaluate("() => { window.open = () => null; }")
    page.locator('[data-testid="mcp-test-connection"]').click()
    anchor = page.locator('[data-testid="mcp-consent-link-open"]')
    expect(anchor).to_be_visible(timeout=8000)
    anchor.focus()
    expect(anchor).to_be_focused()
    state["token"] = True
    expect(
        page.locator('[data-testid="mcp-tools-list"] [data-testid="mcp-tool-item"]')
    ).to_have_count(1, timeout=10000)
    expect(page.locator('[data-testid="mcp-test-connection"]')).to_be_focused()


@pytest.mark.browser
def test_link_block_survives_status_text_and_popup_closing(app_clean: str, page: Page) -> None:
    sid = _seed_oauth_source(app_clean, "popup-closes")
    state = _stub_signin_routes(page, app_clean, sid)
    _open_editor(page, app_clean, sid)
    page.evaluate(
        "() => { window.__p = { closed: false, close() { this.closed = true; } };"
        " window.open = () => window.__p; }"
    )
    page.locator('[data-testid="mcp-test-connection"]').click()
    status = page.locator('[data-testid="mcp-test-status"]')
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_be_visible(timeout=8000)
    page.evaluate("() => { window.__p.closed = true; }")
    expect(status).to_contain_text("Waiting for sign-in", timeout=8000)
    # The status text changed; the block is still there, and polling goes on
    # well past the old 3s popup-close grace window.
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_be_visible()
    polls = state["polls"]
    page.wait_for_timeout(4000)
    assert state["polls"] > polls + 2
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_be_visible()
    state["token"] = True
    expect(
        page.locator('[data-testid="mcp-tools-list"] [data-testid="mcp-tool-item"]')
    ).to_have_count(1, timeout=10000)


@pytest.mark.browser
def test_failed_sign_in_removes_the_block_and_offers_retry(app_clean: str, page: Page) -> None:
    sid = _seed_oauth_source(app_clean, "signin-fails")
    _stub_signin_routes(page, app_clean, sid)
    _open_editor(page, app_clean, sid)
    page.evaluate("() => { window.open = () => null; }")
    page.locator('[data-testid="mcp-test-connection"]').click()
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_be_visible(timeout=8000)
    page.evaluate(
        "() => window.postMessage({type: 'mcp-oauth-result', status: 'failed',"
        " description: 'denied'}, window.location.origin)"
    )
    status = page.locator('[data-testid="mcp-test-status"]')
    expect(status).to_contain_text("Sign-in failed: denied", timeout=8000)
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_have_count(0)
    expect(page.locator('[data-testid="mcp-consent-btn"]')).to_be_visible()


@pytest.mark.browser
def test_credentials_rejected_renders_plain_headline(app_clean: str, page: Page) -> None:
    sid = _seed_oauth_source(app_clean, "rejected-key")
    raw = (
        "MCPCredentialsRejected: rejected-key rejected the configured credentials (401). "
        "Check the headers for this MCP server in Library › MCP servers, or the agent's "
        "Tools tab if it overrides them."
    )
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "error", "error": raw}),
        ),
    )
    _open_editor(page, app_clean, sid)
    page.locator('[data-testid="mcp-test-connection"]').click()
    err = page.locator('[data-testid="mcp-connection-error"]')
    expect(err).to_contain_text(
        "The server rejected the configured credentials. Check the headers on this MCP server.",
        timeout=8000,
    )
    expect(page.locator('[data-testid="mcp-consent-btn"]')).to_have_count(0)
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_have_count(0)


@pytest.mark.browser
def test_non_web_consent_url_opens_nothing_and_renders_no_link(app_clean: str, page: Page) -> None:
    sid = _seed_oauth_source(app_clean, "unsafe-consent")
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "auth_required", "consent_url": "javascript:alert(1)"}),
        ),
    )
    _open_editor(page, app_clean, sid)
    page.evaluate(
        "() => { window.__opens = []; window.open = (u) => { __opens.push(u); return null; }; }"
    )
    page.locator('[data-testid="mcp-test-connection"]').click()
    expect(page.locator(".consent-link-unsafe")).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="mcp-consent-link-open"]')).to_have_count(0)
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_have_count(0)
    assert page.evaluate("() => window.__opens") == []


@pytest.mark.browser
def test_late_save_never_writes_into_the_next_editor(app_clean: str, page: Page) -> None:
    """Defect 1: A's Save is in flight when B opens; the response must not retitle
    B, clear its unsaved state, flash into it or reset the leave guard."""
    a = _seed_stdio(app_clean, "late-save-a")
    _seed_stdio(app_clean, "late-save-b")
    _install_counter(page)
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(a)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("late-save-a-renamed")
    path = f"/api/mcp-sources/{a}"
    held = _hold_requests(page, re.compile(rf".*{re.escape(path)}$"), "PUT")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    _wait_held(page, held, "PUT", path)

    _lists.item_link(page, "library/mcp", "late-save-b").click()
    _leave_confirm(page)
    expect(page.locator(".editor-title")).to_have_text("late-save-b", timeout=8000)
    page.locator('[data-field="name"]').fill("late-save-b-edited")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")

    with page.expect_response(lambda r: r.request.method == "PUT" and r.url.endswith(path)):
        held[0].continue_()
    _yield_macrotasks(page)

    expect(page.locator(".editor-title")).to_have_text("late-save-b")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).not_to_be_disabled()
    expect(page.locator('[data-testid="cancel-mcp-source-btn"]')).not_to_be_disabled()
    expect(page.locator('[data-field="name"]')).to_have_value("late-save-b-edited")
    expect(page.locator(".app-flash")).to_have_count(0)
    assert page.evaluate("() => App.nav.isDirty()") is True
    assert _get_source(app_clean, a)["name"] == "late-save-a-renamed"
    expect(_lists.list_row(page, "library/mcp", "late-save-a-renamed")).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_late_delete_never_closes_the_next_editor(app_clean: str, page: Page) -> None:
    """Defect 1 (Delete): A's DELETE lands after B opened. B stays open and A's
    row leaves the list."""
    a = _seed_stdio(app_clean, "late-del-a")
    b = _seed_stdio(app_clean, "late-del-b")
    _install_counter(page)
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(a)}")
    expect(page.locator('[data-testid="delete-mcp-source-btn"]')).to_be_visible(timeout=8000)

    path = f"/api/mcp-sources/{a}"
    held = _hold_requests(page, re.compile(rf".*{re.escape(path)}$"), "DELETE")
    delete_btn = page.locator('[data-testid="delete-mcp-source-btn"]')
    delete_btn.click()
    delete_btn.click()
    _wait_held(page, held, "DELETE", path)

    _lists.open_item(page, "library/mcp", "late-del-b")
    expect(page.locator(".editor-title")).to_have_text("late-del-b", timeout=8000)

    with page.expect_response(lambda r: r.request.method == "DELETE" and r.url.endswith(path)):
        held[0].continue_()
    _yield_macrotasks(page)

    expect(_lists.list_row(page, "library/mcp", "late-del-a")).to_have_count(0, timeout=8000)
    expect(page.locator(".editor-title")).to_have_text("late-del-b")
    _nav.expect_route(page, f"library/mcp/{_nav.seg(b)}")
    expect(page.locator(".app-flash")).to_have_count(0)


@pytest.mark.browser
def test_late_test_connection_never_paints_the_next_editor(app_clean: str, page: Page) -> None:
    """Defect 1 (Test): A's connect answers after B opened. B's status line, Server section
    and Reset presence are unchanged, and no Reset carries A's name."""
    a = _seed_http(app_clean, "late-test-a")
    _seed_http(app_clean, "late-test-b")
    real_a = _get_source(app_clean, a)
    _install_counter(page)
    # A's per-id GET carries oauth_active, so the old Reset injection would show.
    page.route(
        re.compile(rf".*/api/mcp-sources/{re.escape(a)}$"),
        lambda route: (
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({**real_a, "oauth_active": True}),
            )
            if route.request.method == "GET"
            else route.fallback()
        ),
    )
    connect_path = f"/api/mcp-sources/{a}/test/connect"
    held = _hold_requests(page, re.compile(rf".*{re.escape(connect_path)}$"), "POST")
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(a)}")
    expect(page.locator('[data-testid="mcp-test-connection"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="mcp-test-connection"]').click()
    _wait_held(page, held, "POST", connect_path)

    _lists.open_item(page, "library/mcp", "late-test-b")
    expect(page.locator(".editor-title")).to_have_text("late-test-b", timeout=8000)
    probe = """() => ({
      led: (document.querySelector('[data-testid="mcp-connection-led"]') || {}).className,
      state: (document.querySelector('[data-testid="mcp-connection-status"]') || {}).dataset
        && document.querySelector('[data-testid="mcp-connection-status"]').dataset.state,
      line: (document.querySelector('[data-testid="mcp-connection-status"]') || {}).textContent,
      area: (document.querySelector('[data-testid="mcp-test-status"]') || {}).hidden,
      server: document.querySelectorAll('[data-testid="mcp-server-info-section"]:not([hidden])').length,
      reset: document.querySelectorAll('[data-testid="reset-mcp-connection-btn"]').length,
    })"""
    before = page.evaluate(probe)

    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith(connect_path)
    ):
        held[0].fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(_OK_TOOLS),
        )
    _yield_macrotasks(page)

    assert page.evaluate(probe) == before
    assert before["reset"] == 0
    assert (
        page.evaluate(
            "() => Array.from(document.querySelectorAll('[data-testid=\"reset-mcp-connection-btn\"]'))"
            ".some(b => b.dataset.name === 'late-test-a')"
        )
        is False
    )


@pytest.mark.browser
@pytest.mark.parametrize("leave", ["other-item", "settings", "breadcrumb"])
def test_leaving_the_editor_stops_the_sign_in_poll(app_clean: str, page: Page, leave: str) -> None:
    """Defect 2: the consent poll ran up to 120 s after the editor was gone."""
    a = _seed_http(app_clean, "poll-a")
    _seed_stdio(app_clean, "poll-b")
    _install_counter(page)
    page.clock.install()
    _stub_poll_routes(page)
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(a)}")
    expect(page.locator('[data-testid="mcp-test-connection"]')).to_be_visible(timeout=8000)
    _start_poll(page, a)

    if leave == "other-item":
        _lists.open_item(page, "library/mcp", "poll-b")
        expect(page.locator(".editor-title")).to_have_text("poll-b", timeout=8000)
    elif leave == "settings":
        _nav.open_destination(page, "settings")
        expect(_lists.settings_nav(page)).to_be_visible(timeout=8000)
    else:
        _lists.close_item(page)
        expect(_lists.library_start(page)).to_be_visible(timeout=8000)

    _yield_macrotasks(page)
    path = f"/api/mcp-sources/{a}"
    gets = _count(page, "GET", path)
    posts = _count(page, "POST", f"{path}/test/connect")
    page.clock.run_for(125_000)
    _yield_macrotasks(page)
    assert _count(page, "GET", path) == gets
    assert _count(page, "POST", f"{path}/test/connect") == posts


@pytest.mark.browser
def test_reset_leaves_the_editor_clean_and_focused(app_clean: str, page: Page) -> None:
    """Defect 6 (leg 08b): Reset patches the SAME editor in place (no re-mount), keeps the
    operator's unsaved edit and its caption, keeps focus off body, and the mount still
    owns its poll."""
    sid = _seed_http(
        app_clean,
        "reset-clean",
        secrets={"access_token": "tok", "dcr_credentials": {"client_id": "cid"}},
    )
    _install_counter(page)
    page.clock.install()
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    reset_btn = page.locator('[data-testid="reset-mcp-connection-btn"]')
    expect(reset_btn).to_be_visible(timeout=8000)
    page.locator('[data-field="name"]').fill("reset-clean-edited")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    page.evaluate("() => { window.__ed0 = " + _ED + "; }")

    reset_btn.click()
    reset_btn.click()
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]:not([hidden])')).to_have_count(
        0, timeout=8000
    )
    # In place: the edit and its caption survive, and the controller is the same one.
    expect(page.locator('[data-field="name"]')).to_have_value("reset-clean-edited")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    assert page.evaluate("() => App.nav.isDirty()") is True
    assert page.evaluate("() => " + _ED + " === window.__ed0") is True
    active = page.evaluate(
        "() => { const a = document.activeElement; return a && a !== document.body "
        "? (a.dataset.testid || a.className) : null; }"
    )
    assert active in ("mcp-test-connection", "editor-title"), active

    # The mount owns its poll: leaving stops it. Revert the edit so leaving is clean.
    page.locator('[data-field="name"]').fill("reset-clean")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("")
    _stub_poll_routes(page)
    _start_poll(page, sid)
    _lists.close_item(page)
    expect(page.locator(".modal-overlay")).to_have_count(0)
    expect(_lists.library_start(page)).to_be_visible(timeout=8000)
    _yield_macrotasks(page)
    path = f"/api/mcp-sources/{sid}"
    gets = _count(page, "GET", path)
    page.clock.run_for(125_000)
    _yield_macrotasks(page)
    assert _count(page, "GET", path) == gets


@pytest.mark.browser
def test_one_sign_in_poll_at_a_time(app_clean: str, page: Page) -> None:
    """Defect 8: with a sign-in polling, Test is disabled and runTest is a no-op, so
    no second poller or /test/connect starts."""
    _install_counter(page)
    page.clock.install()
    _stub_poll_routes(page)
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    _fake_open(page)
    page.locator('[data-field="name"]').fill("one-poll")
    page.locator('[data-field="type"]').select_option("streamable-http")
    page.locator('[data-field="url"]').fill("https://example.com/mcp")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    consent_btn = page.locator('[data-testid="mcp-consent-btn"]')
    expect(consent_btn).to_be_visible(timeout=8000)
    consent_btn.click()
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_have_count(1, timeout=8000)

    expect(page.locator('[data-testid="mcp-test-connection"]')).to_be_disabled()
    sid = _list_sources(app_clean)[0]["id"]
    path = f"/api/mcp-sources/{sid}"
    connects = _count(page, "POST", f"{path}/test/connect")
    page.evaluate("() => " + _ED + ".runTest()")
    _yield_macrotasks(page)
    assert _count(page, "POST", f"{path}/test/connect") == connects

    base = _count(page, "GET", path)
    page.clock.run_for(2000)
    _yield_macrotasks(page)
    delta = _count(page, "GET", path) - base
    assert 3 <= delta <= 5, f"one poller ticks 4 times in 2 s, saw {delta}"


@pytest.mark.browser
def test_destroy_is_idempotent(app_clean: str, page: Page) -> None:
    """The controller's destroy can run twice without an error."""
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _nav.goto_settled(page, app_clean, "library")
    result = page.evaluate(
        """async () => {
          const types = await (await fetch('/api/mcp-sources/types')).json();
          const div = document.createElement('div');
          const src = {id: 'x', name: 'n', type: 'stdio', config: {command: 'echo'}};
          const ctl = App.studio.renderMcpSourceEditor(div, src, types, {});
          const keys = Object.keys(ctl).sort();
          ctl.destroy();
          ctl.destroy();
          return keys;
        }"""
    )
    assert result == ["destroy", "runTest", "setBusy", "setError"]
    assert errors == []


@pytest.mark.browser
@pytest.mark.parametrize(("kind", "expected"), [("streamable-http", 1), ("stdio", 0)])
def test_auto_run_after_create_fires_once_for_http_and_never_for_stdio(
    app_clean: str, page: Page, kind: str, expected: int
) -> None:
    """The auto-run goes through runTest: one /test/connect after a streamable-http
    create, none after a stdio create."""
    _install_counter(page)
    page.route(
        re.compile(r".*/api/mcp-sources/[^/]+/test/connect$"),
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(_OK_TOOLS)
        ),
    )
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="name"]').fill(f"auto-{kind}")
    page.locator('[data-field="type"]').select_option(kind)
    if kind == "stdio":
        page.locator('[data-field="command-runtime"]').select_option("__custom__")
        page.locator('[data-field="command"]').fill("echo")
    else:
        page.locator('[data-field="url"]').fill("https://example.com/mcp")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)
    if expected:
        expect(
            page.locator('[data-testid="mcp-tools-list"] [data-testid="mcp-tool-item"]')
        ).to_have_count(1, timeout=8000)
    _yield_macrotasks(page)
    n = page.evaluate("() => window.__reqs.filter(r => /\\/test\\/connect$/.test(r.p)).length")
    assert n == expected
