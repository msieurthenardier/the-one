# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""Shared helpers for the MCP source editor browser tests (the split files test_flow_studio_mcp_editor_*.py)."""

from __future__ import annotations

import json
import re

import httpx
from browser import _nav
from browser._credential_registry import auth_headers_for
from playwright.sync_api import Page, expect


def _seed_mcp_source(base_url: str, payload: dict) -> str:
    r = httpx.post(
        f"{base_url}/api/mcp-sources", json=payload, timeout=5.0, headers=auth_headers_for(base_url)
    )
    assert r.status_code in (200, 201), f"seed failed: {r.status_code} {r.text}"
    return r.json()["id"]


def _get_source(base_url: str, sid: str) -> dict:
    r = httpx.get(
        f"{base_url}/api/mcp-sources/{sid}", timeout=5.0, headers=auth_headers_for(base_url)
    )
    assert r.status_code == 200, f"get failed: {r.status_code} {r.text}"
    return r.json()


def _list_sources(base_url: str) -> list[dict]:
    r = httpx.get(f"{base_url}/api/mcp-sources", timeout=5.0, headers=auth_headers_for(base_url))
    assert r.status_code == 200
    return r.json()


def _kv_title(page: Page):
    return page.locator('[data-testid="mcp-env-headers-section"] .section-title')


_CONSENT_URL = "https://idp.example.com/authorize?state=ST&client_id=x"


_OK_TOOLS = {
    "status": "ok",
    "tools": [{"name": "echo", "description": "", "input_schema": {}}],
    "capabilities": {"tools": {}},
}


def _seed_oauth_source(base_url: str, name: str) -> str:
    return _seed_mcp_source(
        base_url,
        {
            "name": name,
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )


def _stub_signin_routes(page: Page, base_url: str, sid: str) -> dict:
    """First /test/connect answers auth_required, later ones ok; the per-id GET
    (the editor's token poll) reports ``has_access_token`` from ``state``."""
    state = {"token": False, "connects": 0, "polls": 0}
    real = _get_source(base_url, sid)

    def handle_connect(route):
        state["connects"] += 1
        body = (
            {"status": "auth_required", "consent_url": _CONSENT_URL}
            if state["connects"] == 1
            else _OK_TOOLS
        )
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def handle_get(route):
        if route.request.method != "GET":
            return route.continue_()
        state["polls"] += 1
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({**real, "has_access_token": state["token"]}),
        )

    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle_connect)
    page.route(re.compile(rf".*/api/mcp-sources/{re.escape(sid)}$"), handle_get)
    return state


def _open_editor(page: Page, base_url: str, sid: str) -> None:
    _nav.goto_settled(page, base_url, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="mcp-test-connection"]')).to_be_visible(timeout=8000)


_COUNTER_JS = """() => {
  window.__reqs = [];
  const orig = window.fetch;
  window.fetch = function (input, init) {
    try {
      const url = new URL(typeof input === 'string' ? input : input.url, location.href);
      const m = (init && init.method) || (input && input.method) || 'GET';
      window.__reqs.push({m: m, p: url.pathname});
    } catch (e) { /* counting only */ }
    return orig.apply(this, arguments);
  };
}"""


_ED = "App.areas.find(a => a.id === 'studio')._currentMcpEditor()"


_YIELD_JS = "() => new Promise(r => setTimeout(() => setTimeout(() => setTimeout(r, 0), 0), 0))"


def _install_counter(page: Page) -> None:
    page.add_init_script(f"({_COUNTER_JS})()")


def _count(page: Page, method: str, path: str) -> int:
    return page.evaluate(
        "([m, p]) => (window.__reqs || []).filter(r => r.m === m && r.p === p).length",
        [method, path],
    )


def _yield_macrotasks(page: Page) -> None:
    page.evaluate(_YIELD_JS)


def _seed_http(base_url: str, name: str, **extra) -> str:  # noqa: ANN003
    return _seed_mcp_source(
        base_url,
        {
            "name": name,
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": extra.get("secrets", {}),
        },
    )


def _seed_stdio(base_url: str, name: str) -> str:
    return _seed_mcp_source(
        base_url,
        {"name": name, "type": "stdio", "config": {"command": "echo", "env": {}}, "secrets": {}},
    )


def _hold_requests(page: Page, pattern, method: str) -> list:
    """Hold every request matching *pattern* + *method*; others continue."""
    held: list = []

    def handler(route):
        if route.request.method == method:
            held.append(route)
        else:
            route.fallback()

    page.route(pattern, handler)
    return held


def _wait_held(page: Page, held: list, method: str, path: str) -> None:
    page.wait_for_function(
        "([m, p]) => (window.__reqs || []).some(r => r.m === m && r.p === p)", arg=[method, path]
    )
    for _ in range(100):
        if held:
            return
        page.evaluate("() => new Promise(r => setTimeout(r, 20))")
    raise AssertionError("request was not held")


def _fake_open(page: Page) -> None:
    page.evaluate("() => { window.open = () => null; }")


def _kv_rows(page: Page):
    return page.locator('[data-testid="mcp-kv-table"] tbody tr')


def _kv_key(row):
    return row.locator("td").nth(0).locator("input")


def _kv_val(row):
    return row.locator("td").nth(1).locator("input").first


def _kv_sens_label(row):
    return row.locator("td").nth(2).locator("label").first


def _kv_add(page: Page, key: str, value: str, sensitive: bool = False):
    """Click Add row and fill the new last row; returns the row."""
    before = _kv_rows(page).count()
    page.locator('[data-testid="kv-add-row-btn"]').click()
    expect(_kv_rows(page)).to_have_count(before + 1)
    row = _kv_rows(page).nth(before)
    if key:
        _kv_key(row).fill(key)
    if value:
        _kv_val(row).fill(value)
    if sensitive:
        _kv_sens_label(row).click()
    return row


def _kv_row_by_key(page: Page, key: str):
    rows = _kv_rows(page)
    for i in range(rows.count()):
        if _kv_key(rows.nth(i)).input_value() == key:
            return rows.nth(i)
    raise AssertionError(f"no kv row with key {key!r}")


def _open_source(page: Page, base_url: str, sid: str) -> None:
    _nav.goto_settled(page, base_url, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)


def _save_edit(page: Page) -> None:
    """Click Save on an edit-mode editor and wait for the saved flash."""
    page.locator(".app-flash").evaluate_all("els => els.forEach(e => e.remove())")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)


def _expect_clean(page: Page) -> None:
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_disabled()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("")


def _http_source(name: str, headers: dict | None = None, secrets: dict | None = None) -> dict:
    return {
        "name": name,
        "type": "streamable-http",
        "config": {"url": "https://example.com/mcp", "headers": dict(headers or {})},
        "secrets": dict(secrets or {}),
    }


_RESULT = '[data-testid="mcp-test-status"]'


def _cache(tools: bool = True, **extra) -> dict:  # noqa: ANN003
    cache: dict = {"last_updated": __import__("time").time() - 30, **extra}
    if tools:
        cache["tools"] = [{"name": "echo", "description": "", "input_schema": {}}]
        cache["capabilities"] = {"tools": {}}
    return cache


def _seed_state(base_url: str, name: str, **kw) -> str:  # noqa: ANN003
    url = kw.pop("url", "https://example.com/mcp")
    return _seed_mcp_source(
        base_url,
        {
            "name": name,
            "type": "streamable-http",
            "config": {"url": url, **({"_cache": kw["cache"]} if "cache" in kw else {})},
            "secrets": kw.get("secrets", {}),
        },
    )


def _open(page: Page, base: str, sid: str) -> None:
    _nav.goto_settled(page, base, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)


_LONG_DESC = "Fetches a resource and returns the body. " * 4  # 164 chars, over the 100 cut


def _info_cache(**extra) -> dict:  # noqa: ANN003
    cache = {
        "server_info": {"name": "sonos", "title": "Sonos MCP", "version": "1.4.2"},
        "protocol_version": "2026-07-28",
        "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
        "tools": [
            {"name": "short", "description": "Plays a song.", "input_schema": {}},
            {
                "name": "long",
                "description": _LONG_DESC,
                "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
            },
            {"name": "bare", "description": "", "input_schema": {}},
        ],
        "last_updated": __import__("time").time() - 30,
    }
    cache.update(extra)
    return cache


# The Arguments rows (sortie 18): one row is one argument.
ARGS_ROWS = '[data-testid="mcp-args-row"]'
ARGS_INPUTS = '[data-testid="mcp-args-input"]'


def args_add(page: Page, value: str | None = None) -> None:
    """Click Add row and, when ``value`` is given, type it into the new row (Add focuses it)."""
    page.locator('[data-testid="mcp-args-add-row-btn"]').click()
    if value is not None:
        page.locator(ARGS_INPUTS).last.fill(value)


def args_values(page: Page) -> list[str]:
    """The argument rows' input values, in display order."""
    return page.locator(ARGS_INPUTS).evaluate_all("els => els.map(e => e.value)")


def args_click(page: Page, kind: str, n: int) -> None:
    """Click row ``n``'s (1-based) ``kind`` button: ``move-up``, ``move-down`` or ``remove``."""
    page.locator(ARGS_ROWS).nth(n - 1).locator(f'[data-testid="mcp-args-{kind}"]').click()
