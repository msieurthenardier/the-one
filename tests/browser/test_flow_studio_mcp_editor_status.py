# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""MCP source editor browser tests: connection status, Test, Reset and Forget.

Split from test_flow_studio_mcp_editor.py (squawk 0271); shared helpers live in
browser/_mcp_editor.py."""

from __future__ import annotations

import json
import re

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser._mcp_editor import (
    _OK_TOOLS,
    _RESULT,
    _cache,
    _count,
    _fake_open,
    _get_source,
    _hold_requests,
    _install_counter,
    _open,
    _open_editor,
    _seed_http,
    _seed_mcp_source,
    _seed_oauth_source,
    _seed_state,
    _seed_stdio,
    _stub_signin_routes,
    _wait_held,
    _yield_macrotasks,
)
from playwright.sync_api import Page, expect


def _intercept_test_connect(page: Page, sid: str, reply: dict) -> list:
    """Stub /test/connect, returning the (live) list of request bodies (None = no body)."""
    bodies: list = []

    def handle(route):
        bodies.append(route.request.post_data)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(reply))

    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle)
    return bodies


_STATUS = '[data-testid="mcp-connection-status"]'


_UNREACHABLE = "http://127.0.0.1:9/mcp"


_OAUTH_SECRETS = {"access_token": "tok", "dcr_credentials": {"client_id": "cid"}}


# ── F9 L1 (vibing): persisted tools cache + Reset connection button ───────


@pytest.mark.browser
def test_cached_tools_render_on_initial_mount(app_clean: str, page: Page) -> None:
    """A streamable-http source with config._cache populated renders the
    Tools section pre-populated WITHOUT clicking Test, and the status line reads
    "Connected · checked {clock time}" (M31 F5 L08b; it replaced "Last updated").

    Seed via the API including a `_cache` block (POST does not strip it).
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "cached-source",
            "type": "streamable-http",
            "config": {
                "url": "https://example.com/mcp",
                "_cache": {
                    "tools": [
                        {"name": "echo", "description": "echo back", "input_schema": {}},
                        {"name": "shout", "description": "shout it", "input_schema": {}},
                    ],
                    "capabilities": {
                        "tools": {},
                        "resources": None,
                        "prompts": None,
                        "logging": None,
                        "completions": None,
                        "tasks": None,
                    },
                    # 30 seconds in the past → "just now" (diffSec < 60).
                    "last_updated": __import__("time").time() - 30,
                },
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Tools list rendered without clicking Refresh.
    tool_items = page.locator('[data-testid="mcp-tools-list"] [data-testid="mcp-tool-item"]')
    expect(tool_items).to_have_count(2)
    # The "Server exposes N tools." line is gone: the result area is hidden and the status
    # line says Connected (a legacy cache without last_check falls back to last_updated).
    expect(page.locator('[data-testid="mcp-test-status"]')).to_be_hidden()
    status = page.locator('[data-testid="mcp-connection-status"]')
    expect(status).to_have_text(re.compile(r"^Connected · checked \d{1,2}:\d{2} (AM|PM)$"))
    expect(status.locator('[data-testid="mcp-connection-led"]')).to_have_count(1)
    expect(
        page.locator(".mcp-connection-status-row [data-testid='mcp-connection-status']")
    ).to_have_count(1)


@pytest.mark.browser
def test_last_updated_renders_relative_time_format(app_clean: str, page: Page) -> None:
    """The status line shows the clock time the cache was written (DD14: local 12-hour
    through App.time.formatClock), not a relative "N minutes ago" (ledger row 6)."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "relative-time-source",
            "type": "streamable-http",
            "config": {
                "url": "https://example.com/mcp",
                "_cache": {
                    "tools": [{"name": "t", "description": "", "input_schema": {}}],
                    "capabilities": {"tools": {}},
                    # 7 minutes ago.
                    "last_updated": __import__("time").time() - 7 * 60,
                },
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    text = page.locator('[data-testid="mcp-connection-status"]').inner_text()
    assert re.fullmatch(
        r"Connected · checked (?:[A-Z][a-z]{2} \d{1,2}, \d{4}, )?\d{1,2}:\d{2} (AM|PM)", text
    ), text
    assert "ago" not in text and "Last updated" not in text


@pytest.mark.browser
def test_reset_button_hidden_for_stdio_source(app_clean: str, page: Page) -> None:
    """stdio sources never show the Reset connection button (no OAuth concept)."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "stdio-source",
            "type": "stdio",
            "config": {"command": "x"},
            "secrets": {},
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="delete-mcp-source-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]')).to_have_count(0)


@pytest.mark.browser
def test_reset_button_hidden_for_streamable_http_without_oauth(app_clean: str, page: Page) -> None:
    """A streamable-http source with no OAuth state shows Delete but not Reset."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "no-oauth",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="delete-mcp-source-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]')).to_have_count(0)


@pytest.mark.browser
def test_reset_button_visible_for_streamable_http_with_oauth(app_clean: str, page: Page) -> None:
    """A streamable-http source with OAuth state (access_token + dcr_credentials
    persisted) shows the Reset connection button alongside Delete."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "with-oauth",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {
                "access_token": "tok",
                "dcr_credentials": {"client_id": "cid"},
            },
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="delete-mcp-source-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]')).to_be_visible(timeout=8000)


@pytest.mark.browser
def test_reset_button_two_step_confirmation(app_clean: str, page: Page) -> None:
    """First click on Reset arms the confirm-delete state (label flips,
    `confirm-delete` class is added); second click commits the DELETE and patches
    the editor in place: the Tools section back to its empty state and the Reset
    button hidden."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "reset-two-step",
            "type": "streamable-http",
            "config": {
                "url": "https://example.com/mcp",
                "_cache": {
                    "tools": [{"name": "t", "description": "", "input_schema": {}}],
                    "capabilities": {"tools": {}},
                    "last_updated": __import__("time").time() - 30,
                },
            },
            "secrets": {
                "access_token": "tok",
                "dcr_credentials": {"client_id": "cid"},
            },
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    reset_btn = page.locator('[data-testid="reset-mcp-connection-btn"]')
    expect(reset_btn).to_be_visible(timeout=8000)

    # Pre-click: cached tools render.
    expect(
        page.locator('[data-testid="mcp-tools-list"] [data-testid="mcp-tool-item"]')
    ).to_have_count(1)

    # First click arms.
    reset_btn.click()
    expect(reset_btn).to_have_text("Reset connection?")
    expect(reset_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    # Second click commits.
    reset_btn.click()

    # After the patch: Reset is hidden (no more OAuth state) and the Tools section
    # collapsed to its empty-state hint.
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]:not([hidden])')).to_have_count(
        0, timeout=5000
    )
    expect(page.locator(".mcp-tools-empty")).to_contain_text("Press Test", timeout=5000)
    expect(page.locator('[data-testid="mcp-tools-list"]')).to_be_hidden()


@pytest.mark.browser
def test_reset_mcp_connection_confirm_lapse_is_visually_distinct(
    app_clean: str, page: Page
) -> None:
    """Mission 24 Flight 7 confirm-lapse leg, AC-4: the connection Reset
    confirm (`mcp-connection-status.js`) is distinguishable on screen from
    one that was never armed, past the real 3s `revertMs` — and, since
    reverting here does NOT navigate away, the reverted control is still
    reachable to observe."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "reset-lapse-me",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {
                "access_token": "tok",
                "dcr_credentials": {"client_id": "cid"},
            },
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    reset_btn = page.locator('[data-testid="reset-mcp-connection-btn"]')
    expect(reset_btn).to_be_visible(timeout=8000)
    expect(reset_btn).not_to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    reset_btn.click()
    expect(reset_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    expect(reset_btn).not_to_have_class(re.compile(r"\bconfirm-delete\b"), timeout=4000)
    expect(reset_btn).to_have_class(re.compile(r"\bconfirm-lapsed\b"))
    expect(reset_btn).to_have_text("Reset connection")
    # The connection was never actually reset (no commit fired). OAuth-managed
    # keys (access_token, dcr_credentials) are always stripped from the GET
    # response body (api.py's OAUTH_MANAGED_SECRET_KEYS visibility filter),
    # so `oauth_active` — not raw secret presence — is the observable here.
    src = _get_source(app_clean, sid)
    assert src["oauth_active"] is True


# ── F9 L1 (vibing follow-up): Reset button placement + post-OAuth visibility +
#                              auto-run-on-create ─────────────────────────


@pytest.mark.browser
def test_reset_button_renders_in_connection_block_not_danger_zone(
    app_clean: str, page: Page
) -> None:
    """The Reset connection button is rendered next to Refresh in the
    Connection block (paired secondary action), NOT inside the Danger Zone.
    Reset is a reversible operation (just re-OAuth) and doesn't belong
    among destructive actions.

    Asserted invariants:
    - Reset button is a descendant of `.mcp-connection-status-row` (the
      flex group that pairs it with the status line).
    - Reset button is NOT a descendant of `.editor-section.danger-zone`.
    - Refresh button precedes Reset button in document order (visual
      hierarchy: primary → secondary).
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "reset-placement",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {
                "access_token": "tok",
                "dcr_credentials": {"client_id": "cid"},
            },
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]')).to_be_visible(timeout=8000)

    # Reset is inside the connection-actions cluster.
    expect(
        page.locator('.mcp-connection-status-row [data-testid="reset-mcp-connection-btn"]')
    ).to_have_count(1)

    # Reset is NOT inside the Danger Zone block.
    expect(
        page.locator('.editor-section.danger-zone [data-testid="reset-mcp-connection-btn"]')
    ).to_have_count(0)

    # Refresh precedes Reset in document order (within the same actions
    # cluster). compareDocumentPosition returns FOLLOWING (4) when
    # `refresh` is followed by `reset` in the DOM.
    refresh_precedes_reset = page.evaluate(
        "() => {"
        "  var refresh = document.querySelector('[data-testid=\"mcp-test-connection\"]');"
        "  var reset = document.querySelector('[data-testid=\"reset-mcp-connection-btn\"]');"
        "  if (!refresh || !reset) return false;"
        "  return !!(refresh.compareDocumentPosition(reset) & Node.DOCUMENT_POSITION_FOLLOWING);"
        "}"
    )
    assert refresh_precedes_reset, "Refresh must precede Reset in document order"


@pytest.mark.browser
def test_reset_button_two_step_confirmation_in_connection_block(app_clean: str, page: Page) -> None:
    """The two-step confirmation flow on the Reset button: first click flips the label to
    "Reset connection?" and adds the `confirm-delete` class; second click commits."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "reset-two-step-connection-block",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {
                "access_token": "tok",
                "dcr_credentials": {"client_id": "cid"},
            },
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    reset_btn = page.locator('.mcp-connection-status-row [data-testid="reset-mcp-connection-btn"]')
    expect(reset_btn).to_be_visible(timeout=8000)

    # First click arms.
    reset_btn.click()
    expect(reset_btn).to_have_text("Reset connection?")
    expect(reset_btn).to_have_class(re.compile(r"\bconfirm-delete\b"))

    # Second click commits → patched with no OAuth state, button hides.
    reset_btn.click()
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]:not([hidden])')).to_have_count(
        0, timeout=5000
    )


@pytest.mark.browser
def test_reset_button_reappears_after_post_oauth_refresh(app_clean: str, page: Page) -> None:
    """After the Reset → Refresh-with-OAuth cycle, the Reset button must
    reappear without a page reload once /test/connect lands ok.

    Simulates the bug scenario:
    1. Source starts WITHOUT OAuth state → Reset button hidden.
    2. Operator clicks Refresh → /test/connect stub returns ok (we
       cannot drive a real OAuth popup in a browser test, so we stub
       the response). BEFORE the response lands, we mutate the seeded
       source server-side to add OAuth state — simulating what the
       real OAuth flow would do (write tokens via the SDK's callback
       handler).
    3. The success-callback refetches GET /api/mcp-sources/{id}; the
       refetched response carries oauth_active=true; the Reset button
       gets injected into the DOM.

    The auto-popup branch is NOT exercised by this test because driving
    a real OAuth flow requires an in-repo OAuth fixture (deferred per
    flight log). What this test verifies is the targeted UI behavior:
    after a successful /test/connect that flips oauth_active, the Reset
    button appears without reload.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "reset-post-oauth",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},  # no OAuth state initially
        },
    )

    # Stub the per-id GET endpoint to return oauth_active=true so the
    # success-handler refetch sees the post-OAuth state. (We can't drive
    # the real OAuth flow in a browser test without an OAuth fixture —
    # what matters is that the success-callback's refetch + Reset-button
    # injection fires when oauth_active flips from false to true.)
    #
    # The initial mount fetches sources via the LIST endpoint
    # (/api/mcp-sources), not per-id, so the per-id stub only activates
    # for the post-test-connect refetch — exactly what we want.
    real_source = httpx.get(
        f"{app_clean}/api/mcp-sources/{sid}", timeout=5.0, headers=auth_headers_for(app_clean)
    ).json()
    post_oauth_get = dict(real_source)
    post_oauth_get["oauth_active"] = True

    test_connect_payload = {
        "status": "ok",
        "tools": [{"name": "echo", "description": "", "input_schema": {}}],
        "capabilities": {
            "tools": {},
            "resources": None,
            "prompts": None,
            "logging": None,
            "completions": None,
            "tasks": None,
        },
    }

    def handle_get(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(post_oauth_get),
        )

    def handle_test_connect(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(test_connect_payload),
        )

    page.route(f"**/api/mcp-sources/{sid}", handle_get)
    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle_test_connect)

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="mcp-test-connection"]')).to_be_visible(timeout=8000)

    # Pre-Refresh: no OAuth state → no Reset button.
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]')).to_have_count(0)

    # Click Refresh → success-handler issues a GET refetch → the stub
    # returns oauth_active=true → Reset button gets injected into the
    # connection-actions cluster.
    page.locator('[data-testid="mcp-test-connection"]').click()
    expect(page.locator('[data-testid="mcp-tools-list"]')).to_be_visible(timeout=4000)
    # After the success callback's GET resolves, the Reset button appears
    # without requiring a page reload.
    expect(
        page.locator('.mcp-connection-status-row [data-testid="reset-mcp-connection-btn"]')
    ).to_be_visible(timeout=4000)


@pytest.mark.browser
def test_test_sends_no_body_when_clean_and_a_body_when_dirty(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "body-rule",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    bodies = _intercept_test_connect(page, sid, {"status": "error", "error": "boom"})
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    expect(test_btn).to_be_visible(timeout=8000)

    test_btn.click()
    expect(page.locator('[data-testid="mcp-connection-error"]')).to_be_visible(timeout=4000)
    assert bodies == [None], bodies
    # A clean Test must not run the form validation that writes .editor-error.
    expect(page.locator(".editor-error")).to_have_text("")

    expect(test_btn).not_to_be_disabled(timeout=4000)
    page.locator('[data-field="url"]').fill("https://example.com/changed")
    test_btn.click()
    expect(test_btn).not_to_be_disabled(timeout=4000)
    assert len(bodies) == 2 and bodies[1] is not None
    assert json.loads(bodies[1])["config"]["url"] == "https://example.com/changed"


@pytest.mark.browser
@pytest.mark.parametrize(
    "reply",
    [
        {"status": "error", "error": "boom"},
        {"status": "auth_required", "consent_url": "https://example.com/consent"},
    ],
)
def test_every_test_outcome_refetches_the_mcp_list(app_clean: str, page: Page, reply: dict) -> None:
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "refetch-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    _intercept_test_connect(page, sid, reply)
    # A sign-in outcome would open a popup; the desktop-less test browser may block it,
    # which the editor tolerates. Neutralise it so the test stays about the refetch.
    page.add_init_script("window.open = function () { return null; };")
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    expect(test_btn).to_be_visible(timeout=8000)
    lists: list[str] = []
    page.on(
        "request",
        lambda req: (
            lists.append(req.url)
            if req.method == "GET" and req.url.split("?")[0].endswith("/api/mcp-sources")
            else None
        ),
    )
    test_btn.click()
    for _ in range(40):
        if lists:
            break
        page.wait_for_timeout(100)
    assert lists, "the MCP list was not refetched after the Test outcome"


@pytest.mark.browser
@pytest.mark.parametrize(
    ("label", "kw", "state"),
    [
        ("connected", {"cache": "tools"}, "connected"),
        ("none", {}, "none"),
        ("error", {"cache": "error"}, "error"),
        ("signin", {"secrets": {"dcr_credentials": {"client_id": "cid"}}}, "signin"),
    ],
)
def test_status_line_equals_mcp_state_for_each_seeded_state(
    app_clean: str, page: Page, label: str, kw: dict, state: str
) -> None:
    """Derived relationship: the editor's status line and App.usage.mcpState agree,
    and the line's words come from App.usage.mcpStateLabel."""
    if kw.get("cache") == "tools":
        kw = {**kw, "cache": _cache(last_check={"status": "ok", "at": __import__("time").time()})}
    elif kw.get("cache") == "error":
        kw = {
            **kw,
            "cache": _cache(
                tools=False, last_check={"status": "error", "at": __import__("time").time()}
            ),
        }
    sid = _seed_state(app_clean, f"state-{label}", **kw)
    _open(page, app_clean, sid)
    line = page.locator(_STATUS)
    expect(line).to_have_count(1)
    got = page.evaluate(
        """async (id) => {
          const src = await (await fetch('/api/mcp-sources/' + id)).json();
          const s = App.usage.mcpState(src);
          return {state: s.state, label: App.usage.mcpStateLabel(s.state)};
        }""",
        sid,
    )
    assert got["state"] == state
    expect(line).to_have_attribute("data-mcp-state", state)
    expect(line).to_contain_text(got["label"])
    # The LED is decorative: the words carry the state (defect 11).
    expect(page.locator('[data-testid="mcp-connection-led"]')).to_have_attribute(
        "aria-hidden", "true"
    )
    if state == "connected":
        expect(line).to_have_text(re.compile(r"Connected · checked \d{1,2}:\d{2} (AM|PM)"))
        expect(line).to_have_attribute("data-state", "success")


@pytest.mark.browser
def test_failed_test_keeps_last_connected_and_survives_reopen(app_clean: str, page: Page) -> None:
    """A9: a failed Test on a connected server reads "Couldn't connect · last connected
    {time}", also after reopening the editor."""
    sid = _seed_state(
        app_clean,
        "a9-source",
        url=_UNREACHABLE,
        cache=_cache(last_check={"status": "ok", "at": __import__("time").time() - 30}),
    )
    _open(page, app_clean, sid)
    line = page.locator(_STATUS)
    expect(line).to_contain_text("Connected")
    page.locator('[data-testid="mcp-test-connection"]').click()
    expect(line).to_have_text(
        re.compile(r"Couldn't connect · last connected \d{1,2}:\d{2} (AM|PM)"), timeout=15000
    )
    expect(page.locator('[data-testid="mcp-connection-error"]')).to_be_visible()
    _nav.goto_settled(page, app_clean, "library")
    _open(page, app_clean, sid)
    expect(page.locator(_STATUS)).to_have_text(
        re.compile(r"Couldn't connect · last connected \d{1,2}:\d{2} (AM|PM)")
    )


@pytest.mark.browser
def test_test_is_in_the_header_in_edit_mode_only_and_refresh_is_gone(
    app_clean: str, page: Page
) -> None:
    """B2: Test sits in the header cluster (after Save, the shell's order); no Refresh."""
    sid = _seed_state(app_clean, "b2-source")
    _open(page, app_clean, sid)
    test_btn = page.locator('.editor-header .form-actions [data-testid="mcp-test-connection"]')
    expect(test_btn).to_have_count(1)
    expect(test_btn).to_have_text("Test")
    # M31 F5 L10: the shell's cluster order, as in the provider editor: Cancel, Save, Test.
    follows = page.evaluate(
        "() => { const t = document.querySelector('[data-testid=\"mcp-test-connection\"]');"
        " return t.previousElementSibling === document.querySelector('.save-btn'); }"
    )
    assert follows
    expect(page.get_by_text("Refresh connection")).to_have_count(0)
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="mcp-test-connection"]')).to_have_count(0)


@pytest.mark.browser
def test_result_area_follows_the_status_line_and_is_hidden_at_rest(
    app_clean: str, page: Page
) -> None:
    """A8: the result area is in the Connection section, directly after the status row,
    hidden at rest and after a success; Tools has no result line and no count line."""
    sid = _seed_state(app_clean, "a8-source")
    _open(page, app_clean, sid)
    layout = page.evaluate(
        """() => {
          const line = document.querySelector('[data-testid="mcp-connection-status"]');
          const area = document.querySelector('[data-testid="mcp-test-status"]');
          const sec = area.closest('.editor-section');
          return {
            next: line.parentElement.nextElementSibling === area,
            section: sec.querySelector('.section-title').textContent,
            hidden: area.hidden,
            toolsHasArea: !!document.querySelector('[data-testid="mcp-tools-section"] [data-testid="mcp-test-status"]'),
          };
        }"""
    )
    assert layout == {"next": True, "section": "Connection", "hidden": True, "toolsHasArea": False}
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(_OK_TOOLS)
        ),
    )
    page.locator('[data-testid="mcp-test-connection"]').click()
    expect(
        page.locator('[data-testid="mcp-tools-list"] [data-testid="mcp-tool-item"]')
    ).to_have_count(len(_OK_TOOLS["tools"]), timeout=8000)
    expect(page.locator(_RESULT)).to_be_hidden()
    expect(page.get_by_text("Server exposes")).to_have_count(0)


@pytest.mark.browser
def test_tools_list_is_not_cleared_when_a_test_starts(app_clean: str, page: Page) -> None:
    """A9 (tools): a Test that is still running leaves the cached tools list in place."""
    sid = _seed_state(app_clean, "keep-tools", cache=_cache())
    _install_counter(page)
    held = _hold_requests(page, re.compile(rf".*/api/mcp-sources/{sid}/test/connect$"), "POST")
    _open(page, app_clean, sid)
    expect(
        page.locator('[data-testid="mcp-tools-list"] [data-testid="mcp-tool-item"]')
    ).to_have_count(1)
    page.locator('[data-testid="mcp-test-connection"]').click()
    _wait_held(page, held, "POST", f"/api/mcp-sources/{sid}/test/connect")
    expect(page.locator(_RESULT)).to_have_text("Testing connection…")
    expect(
        page.locator('[data-testid="mcp-tools-list"] [data-testid="mcp-tool-item"]')
    ).to_have_count(1)
    held[0].fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"status": "error", "error": "x"}),
    )
    expect(page.locator('[data-testid="mcp-connection-error"]')).to_be_visible()
    expect(
        page.locator('[data-testid="mcp-tools-list"] [data-testid="mcp-tool-item"]')
    ).to_have_count(1)


@pytest.mark.browser
def test_dirty_form_test_leaves_the_line_on_the_saved_record(app_clean: str, page: Page) -> None:
    """A Test on unsaved changes is labelled in the result area and records nothing."""
    sid = _seed_state(app_clean, "dirty-note")
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "error", "error": "MCPConnectionError: refused"}),
        ),
    )
    _open(page, app_clean, sid)
    expect(page.locator(_STATUS)).to_contain_text("Not connected")
    page.locator('[data-field="url"]').fill("https://example.com/other")
    page.locator('[data-testid="mcp-test-connection"]').click()
    expect(page.locator(_RESULT)).to_contain_text("Tested with your unsaved changes.")
    expect(page.locator('[data-testid="mcp-connection-error"]')).to_be_visible()
    expect(page.locator(_STATUS)).to_contain_text("Not connected")


@pytest.mark.browser
def test_invalid_dirty_form_test_makes_no_request_and_leaves_the_editor_error(
    app_clean: str, page: Page
) -> None:
    """Defect 9: a dirty form that cannot be sent shows its message in the result area,
    sends no request, and never writes the editor error."""
    sid = _seed_state(app_clean, "defect-9")
    _install_counter(page)
    _open(page, app_clean, sid)
    page.locator('[data-field="url"]').fill("")
    page.locator('[data-testid="mcp-test-connection"]').click()
    expect(page.locator(_RESULT)).to_contain_text("Enter the server's URL.", timeout=4000)
    _yield_macrotasks(page)
    assert _count(page, "POST", f"/api/mcp-sources/{sid}/test/connect") == 0
    expect(page.locator(".editor-error")).to_have_text("")
    expect(page.locator('[data-testid="mcp-test-connection"]')).not_to_be_disabled()


@pytest.mark.browser
@pytest.mark.parametrize(
    ("kind", "headline"),
    [
        (
            "stdio",
            "The server's command didn't start or stopped. Open Technical details for its output.",
        ),
        (
            "streamable-http",
            "Couldn't connect to this server. Check that it's running and that its address and "
            "headers are right, then try again.",
        ),
    ],
)
def test_connection_error_headline_follows_the_transport(
    app_clean: str, page: Page, kind: str, headline: str
) -> None:
    """A18: one headline per transport."""
    sid = (
        _seed_stdio(app_clean, "a18-stdio")
        if kind == "stdio"
        else _seed_http(app_clean, "a18-http")
    )
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "error", "error": "MCPConnectionError: Connection closed"}),
        ),
    )
    _open(page, app_clean, sid)
    page.locator('[data-testid="mcp-test-connection"]').click()
    expect(page.locator(".mcp-error-headline")).to_have_text(headline, timeout=8000)


@pytest.mark.browser
def test_reset_and_forget_predicates(app_clean: str, page: Page) -> None:
    """A7: Reset only when signed in; Forget for a cached HTTP server without a sign-in;
    neither for stdio; a cached non-OAuth server shows Forget and not Reset."""
    cases = {
        "oauth": _seed_state(app_clean, "p-oauth", secrets=_OAUTH_SECRETS, cache=_cache()),
        "cached": _seed_state(app_clean, "p-cached", cache=_cache()),
        "posture": _seed_state(
            app_clean, "p-posture", cache=_cache(tools=False, auth_posture={"kind": "no_auth"})
        ),
        "bare": _seed_state(app_clean, "p-bare"),
        "stdio": _seed_stdio(app_clean, "p-stdio"),
    }
    want = {
        "oauth": (1, 0),
        "cached": (0, 1),
        "posture": (0, 1),
        "bare": (0, 0),
        "stdio": (0, 0),
    }
    for key, sid in cases.items():
        _nav.goto_settled(page, app_clean, "library")
        _open(page, app_clean, sid)
        reset = page.locator('[data-testid="reset-mcp-connection-btn"]:not([hidden])')
        forget = page.locator('[data-testid="forget-mcp-connection-btn"]:not([hidden])')
        assert (reset.count(), forget.count()) == want[key], key


@pytest.mark.browser
def test_reset_patches_in_place_and_keeps_edits(app_clean: str, page: Page) -> None:
    """Defect 6 / A7: Reset arms as "Reset connection?", then clears the connection
    without a remount: the dirty field and the caption survive, the Tools list empties
    with the new hint, and focus lands on Test."""
    sid = _seed_state(app_clean, "reset-inplace", secrets=_OAUTH_SECRETS, cache=_cache())
    _open(page, app_clean, sid)
    reset = page.locator('[data-testid="reset-mcp-connection-btn"]')
    page.locator('[data-field="name"]').fill("renamed-unsaved")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    page.evaluate("() => { document.querySelector('.editor-title').__marker = 1; }")
    reset.click()
    expect(reset).to_have_text("Reset connection?")
    reset.click()
    expect(page.locator('[data-testid="reset-mcp-connection-btn"]:not([hidden])')).to_have_count(
        0, timeout=8000
    )
    expect(page.locator(_STATUS)).to_contain_text("Not connected")
    assert page.evaluate("() => document.querySelector('.editor-title').__marker") == 1
    expect(page.locator('[data-field="name"]')).to_have_value("renamed-unsaved")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    expect(page.locator('[data-testid="mcp-tools-list"]')).to_be_hidden()
    expect(page.locator('[data-testid="mcp-tools-section"]')).to_contain_text(
        "Press Test to load this server's tools."
    )
    expect(page.locator(".editor-error")).to_have_text("")
    expect(page.locator('[data-testid="mcp-test-connection"]')).to_be_focused()


@pytest.mark.browser
def test_forget_tools_list_patches_in_place(app_clean: str, page: Page) -> None:
    sid = _seed_state(app_clean, "forget-inplace", cache=_cache(auth_posture={"kind": "no_auth"}))
    _open(page, app_clean, sid)
    forget = page.locator('[data-testid="forget-mcp-connection-btn"]')
    expect(forget).to_have_text("Forget tools list")
    page.locator('[data-field="url"]').fill("https://example.com/unsaved")
    page.evaluate("() => { document.querySelector('.editor-title').__marker = 1; }")
    forget.click()
    expect(forget).to_have_text("Forget tools list?")
    forget.click()
    expect(forget).to_be_hidden(timeout=8000)
    expect(page.locator(_STATUS)).to_contain_text("Not connected")
    assert page.evaluate("() => document.querySelector('.editor-title').__marker") == 1
    expect(page.locator('[data-field="url"]')).to_have_value("https://example.com/unsaved")
    stored = _get_source(app_clean, sid)
    assert "_cache" not in stored["config"]


@pytest.mark.browser
@pytest.mark.parametrize("which", ["reset", "forget"])
def test_sign_in_session_holds_test_and_the_connection_buttons(
    app_clean: str, page: Page, which: str
) -> None:
    """DD4: during a consent session Test reads "Waiting for sign-in…" and is disabled,
    Reset and Forget are disabled, and Save stays live on a dirty form."""
    if which == "reset":
        sid = _seed_state(
            app_clean,
            "hold-reset",
            secrets={"dcr_credentials": {"client_id": "cid"}},
            cache=_cache(),
        )
    else:
        sid = _seed_state(app_clean, "hold-forget", cache=_cache(auth_posture={"kind": "no_auth"}))
    state = _stub_signin_routes(page, app_clean, sid)
    _open(page, app_clean, sid)
    _fake_open(page)
    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    page.locator('[data-field="name"]').fill(f"hold-{which}-edited")
    test_btn.click()
    expect(page.locator('[data-testid="mcp-consent-link-url"]')).to_be_visible(timeout=8000)
    expect(test_btn).to_have_text("Waiting for sign-in…")
    expect(test_btn).to_be_disabled()
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_enabled()
    button = page.locator(f'[data-testid="{which}-mcp-connection-btn"]')
    expect(button).to_be_disabled()
    expect(page.locator(_RESULT)).to_contain_text("Waiting for sign-in…")
    state["token"] = True
    expect(test_btn).to_have_text("Test", timeout=10000)
    expect(test_btn).not_to_be_disabled()


@pytest.mark.browser
def test_leaving_the_editor_during_a_session_restores_nothing_stale(
    app_clean: str, page: Page
) -> None:
    """A cancelled session (the failed message) restores Test's label and state."""
    sid = _seed_oauth_source(app_clean, "hold-cancel")
    _stub_signin_routes(page, app_clean, sid)
    _open_editor(page, app_clean, sid)
    _fake_open(page)
    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    test_btn.click()
    expect(test_btn).to_have_text("Waiting for sign-in…", timeout=8000)
    page.evaluate(
        "() => window.postMessage({type: 'mcp-oauth-result', status: 'failed',"
        " description: 'denied'}, window.location.origin)"
    )
    expect(test_btn).to_have_text("Test", timeout=8000)
    expect(test_btn).not_to_be_disabled()


@pytest.mark.browser
def test_clean_test_sets_the_line_from_the_outcome(app_clean: str, page: Page) -> None:
    """A clean Test sets the line optimistically and the refetch confirms it."""
    sid = _seed_state(app_clean, "optimistic")
    real = _get_source(app_clean, sid)
    served = {"cache": None}

    def handle_get(route):
        if route.request.method != "GET":
            return route.fallback()
        body = json.loads(json.dumps(real))
        if served["cache"]:
            body["config"]["_cache"] = served["cache"]
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route(re.compile(rf".*/api/mcp-sources/{re.escape(sid)}$"), handle_get)
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: (
            served.update(
                cache=_cache(last_check={"status": "ok", "at": __import__("time").time()})
            ),
            route.fulfill(status=200, content_type="application/json", body=json.dumps(_OK_TOOLS)),
        ),
    )
    _open(page, app_clean, sid)
    expect(page.locator(_STATUS)).to_contain_text("Not connected")
    page.locator('[data-testid="mcp-test-connection"]').click()
    expect(page.locator(_STATUS)).to_have_text(
        re.compile(r"Connected · checked \d{1,2}:\d{2} (AM|PM)"), timeout=8000
    )
    expect(page.locator(_STATUS)).to_have_attribute("data-mcp-state", "connected")


@pytest.fixture
def real_http_server():
    """The rich fixture MCP server on a real loopback socket (a subprocess)."""
    import os
    import subprocess
    import sys
    import time
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ, PYTHONPATH=str(root))
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tests.fixtures.mcp.rich_http_server",
            "--mode",
            "ok",
            "--port",
            "0",
        ],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        port = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and port is None:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line.startswith("PORT "):
                port = int(line.split()[1])
        assert port, "the fixture server did not report a port"
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


@pytest.mark.browser
def test_forget_then_test_brings_the_button_back_at_rest(
    app_clean: str, page: Page, real_http_server: str
) -> None:
    """Squawk 0371: after Forget and a real Test, the button is shown again, at rest."""
    sid = _seed_state(app_clean, "forget-then-test", url=real_http_server)
    _open(page, app_clean, sid)
    test_btn = page.locator('[data-testid="mcp-test-connection"]')
    forget = page.locator('[data-testid="forget-mcp-connection-btn"]')
    test_btn.click()
    expect(page.locator(_STATUS)).to_have_attribute("data-mcp-state", "connected", timeout=15000)
    expect(forget).to_be_visible()
    forget.click()
    forget.click()
    expect(forget).to_be_hidden(timeout=8000)
    expect(page.locator(_STATUS)).to_have_attribute("data-mcp-state", "none")
    test_btn.click()
    expect(page.locator(_STATUS)).to_have_attribute("data-mcp-state", "connected", timeout=15000)
    expect(forget).to_be_visible(timeout=8000)
    expect(forget).to_have_text("Forget tools list")
    assert "confirm-delete" not in (forget.get_attribute("class") or "")
