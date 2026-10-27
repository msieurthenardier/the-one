# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""MCP source editor browser tests: the Server section and the tools list.

Split from test_flow_studio_mcp_editor.py (squawk 0271); shared helpers live in
browser/_mcp_editor.py."""

from __future__ import annotations

import json
import re

import pytest
from browser import _nav
from browser._mcp_editor import (
    _LONG_DESC,
    _get_source,
    _info_cache,
    _open_source,
    _seed_mcp_source,
    _seed_state,
)
from playwright.sync_api import Page, expect

_SRV = '[data-testid="mcp-server-info-section"]'


_TOOL = '[data-testid="mcp-tool-item"]'


def _open_with_cache(page: Page, base: str, cache: dict, name: str = "info-src") -> str:
    sid = _seed_state(base, name, cache=cache)
    _open_source(page, base, sid)
    return sid


# ── Squawk 0010: server_info websiteUrl / icon src scheme allow-list ──────


@pytest.mark.browser
def test_server_info_website_and_icon_reject_unsafe_schemes(app_clean: str, page: Page) -> None:
    """serverInfo.websiteUrl and icons[0].src come straight from the MCP
    server's initialize() response — an untrusted third party. A hostile
    javascript: websiteUrl must never become a live href, and a non-http
    icon src must never become a live <img src>: the <img> is dropped
    entirely, and the website row falls back to inert text so the operator
    can still see what the server claimed without it being clickable.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "hostile-server-info-source",
            "type": "streamable-http",
            "config": {
                "url": "https://example.com/mcp",
                "_cache": {
                    "server_info": {
                        "name": "hostile",
                        "title": "Hostile Server",
                        "websiteUrl": "javascript:alert(document.cookie)",
                        "icons": [{"src": "javascript:alert(1)", "mimeType": "image/png"}],
                    },
                    "capabilities": {"tools": {}},
                },
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    section = page.locator('[data-testid="mcp-server-info-section"]')
    expect(section).to_be_visible()

    # Icon: hostile src never reaches an <img> element — dropped entirely,
    # not rendered with a neutered/placeholder src.
    expect(section.locator('[data-testid="mcp-server-icon"]')).to_have_count(0)

    # websiteUrl: no <a> element carries the hostile scheme; the raw string
    # still renders as inert text.
    website = section.locator('[data-testid="mcp-server-website"]')
    expect(website).to_be_visible()
    expect(website.locator("a")).to_have_count(0)
    expect(website).to_contain_text("javascript:alert(document.cookie)")


@pytest.mark.browser
def test_server_info_website_and_icon_allow_https(app_clean: str, page: Page) -> None:
    """The allow-list isn't a blanket drop — a benign https: websiteUrl and
    icon src still render as a live link/image."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "benign-server-info-source",
            "type": "streamable-http",
            "config": {
                "url": "https://example.com/mcp",
                "_cache": {
                    "server_info": {
                        "name": "benign",
                        "title": "Benign Server",
                        "websiteUrl": "https://example.com/about",
                        "icons": [{"src": "https://example.com/icon.png", "mimeType": "image/png"}],
                    },
                    "capabilities": {"tools": {}},
                },
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    section = page.locator('[data-testid="mcp-server-info-section"]')
    expect(section).to_be_visible()

    icon = section.locator('[data-testid="mcp-server-icon"]')
    expect(icon).to_have_count(1)
    expect(icon).to_have_attribute("src", "https://example.com/icon.png")

    link = section.locator('[data-testid="mcp-server-website"] a')
    expect(link).to_have_count(1)
    expect(link).to_have_attribute("href", "https://example.com/about")


# ── Squawk 0102: Server section repaints after Refresh connection ────────


@pytest.mark.browser
def test_server_info_section_repaints_after_refresh(app_clean: str, page: Page) -> None:
    """A Refresh connection that brings back a new serverInfo version must
    repaint the Server section in place — without the operator leaving and
    re-entering the editor (squawk 0102: the section was mount-only, so it
    kept the old version while the tools list repainted).

    Seeds a source with no cache, so the first Refresh exercises the
    insert-above-Tools path and the second exercises the replace path.
    /test/connect and the success-handler's per-id GET refetch are stubbed
    (same pattern as test_reset_button_reappears_after_post_oauth_refresh);
    the GET serves whatever version the "server" currently reports. Initial
    mount reads the LIST endpoint, so the per-id stub only answers the
    post-refresh refetch.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "server-info-repaint",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    real_source = _get_source(app_clean, sid)
    reported = {"version": "0.3.0"}

    def handle_get(route):
        refreshed = json.loads(json.dumps(real_source))
        refreshed["config"]["_cache"] = {
            "tools": [{"name": "echo", "description": "", "input_schema": {}}],
            "server_info": {"name": "sonos", "title": "Sonos MCP", "version": reported["version"]},
            "capabilities": {"tools": {}},
            "last_updated": "2026-09-30T00:00:00Z",
        }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(refreshed))

    def handle_test_connect(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "status": "ok",
                    "tools": [{"name": "echo", "description": "", "input_schema": {}}],
                    "capabilities": {"tools": {}},
                }
            ),
        )

    page.route(f"**/api/mcp-sources/{sid}", handle_get)
    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle_test_connect)

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    refresh_btn = page.locator('[data-testid="mcp-test-connection"]')
    expect(refresh_btn).to_be_visible(timeout=8000)
    section = page.locator('[data-testid="mcp-server-info-section"]')
    expect(section).to_be_hidden()

    # First refresh: the section shows, directly above the Tools section.
    refresh_btn.click()
    expect(section).to_be_visible(timeout=4000)
    expect(section.locator('[data-testid="mcp-server-version"]')).to_contain_text("0.3.0")
    expect(
        page.locator('[data-testid="mcp-server-info-section"] + [data-testid="mcp-tools-section"]')
    ).to_have_count(1)

    # The server is upgraded; refresh again without leaving the editor.
    reported["version"] = "0.5.0"
    expect(refresh_btn).not_to_be_disabled(timeout=4000)
    refresh_btn.click()
    expect(section.locator('[data-testid="mcp-server-version"]')).to_contain_text(
        "0.5.0", timeout=4000
    )
    expect(section).to_have_count(1)
    expect(section.locator('[data-testid="mcp-server-version"]')).not_to_contain_text("0.3.0")


@pytest.mark.browser
def test_server_facts_rows_and_order(app_clean: str, page: Page) -> None:
    """A16 (with B10): Version, Protocol, Offers, Website as facts, in that order; Offers
    capitalised; the protocol kept as a fact."""
    cache = _info_cache()
    cache["server_info"]["websiteUrl"] = "https://example.com/about"
    _open_with_cache(page, app_clean, cache)
    section = page.locator(_SRV)
    expect(section).to_be_visible()
    expect(section.locator(".section-title")).to_have_text("Server")
    expect(section.locator('[data-testid="mcp-server-title"]')).to_have_text("Sonos MCP")
    expect(section.locator('[data-testid="mcp-server-subtitle"]')).to_have_text("sonos")
    labels = section.locator(".ui-facts-label").all_inner_texts()
    assert labels == ["Version", "Protocol", "Offers", "Website"], labels
    expect(section.locator('[data-testid="mcp-server-version"] dd')).to_have_text("1.4.2")
    expect(section.locator('[data-testid="mcp-server-protocol"] dd')).to_have_text("2026-07-28")
    expect(section.locator('[data-testid="mcp-server-offers"] dd')).to_have_text(
        "Tools, Resources, Prompts"
    )
    assert "▸" not in section.inner_text()
    # No old "v1.4.2 · protocol" line, no "Server supports:" prose.
    expect(section).not_to_contain_text("Server supports")
    expect(section).not_to_contain_text("·")


@pytest.mark.browser
def test_server_facts_degenerate_inputs(app_clean: str, page: Page) -> None:
    """No version, no website, empty capabilities, no instructions, no metadata: only the
    rows with values show; an empty capabilities object reads 'Nothing announced'."""
    cache = {"server_info": {"name": "bare"}, "capabilities": {}, "tools": []}
    _open_with_cache(page, app_clean, cache, "bare-info")
    section = page.locator(_SRV)
    expect(section).to_be_visible()
    labels = section.locator(".ui-facts-label").all_inner_texts()
    assert labels == ["Offers"], labels
    expect(section.locator('[data-testid="mcp-server-offers"] dd')).to_have_text(
        "Nothing announced"
    )
    expect(section.locator('[data-testid="mcp-server-title"]')).to_have_text("bare")
    expect(section.locator('[data-testid="mcp-server-subtitle"]')).to_be_hidden()
    expect(section.locator('[data-testid="mcp-server-instructions"]')).to_be_hidden()
    expect(section.locator('[data-testid="mcp-server-meta"]')).to_be_hidden()
    expect(section.locator('[data-testid="mcp-server-icon"]')).to_have_count(0)


@pytest.mark.browser
def test_server_instructions_and_meta_are_disclosures(app_clean: str, page: Page) -> None:
    """A15: Instructions is a disclosure (no chevron text), its body keeps line breaks and is
    text only; Metadata holds the JSON in a code block."""
    cache = _info_cache(
        instructions="Line one\nLine <b>two</b>\n\nLine four",
        meta={"vendor": "acme"},
    )
    _open_with_cache(page, app_clean, cache, "instr-info")
    ins = page.locator('[data-testid="mcp-server-instructions"]')
    expect(ins).to_be_visible()
    assert ins.evaluate("el => el.tagName") == "DETAILS"
    assert ins.evaluate("el => el.open") is False
    expect(ins.locator("summary")).to_have_text("Instructions")
    ins.locator("summary").click()
    body = ins.locator('[data-testid="mcp-server-instructions-text"]')
    expect(body).to_be_visible()
    assert body.evaluate("el => el.textContent") == "Line one\nLine <b>two</b>\n\nLine four"
    assert body.evaluate("el => getComputedStyle(el).whiteSpace") == "pre-wrap"
    assert body.evaluate("el => el.querySelectorAll('b').length") == 0
    meta = page.locator('[data-testid="mcp-server-meta"]')
    meta.locator("summary").click()
    expect(meta.locator('[data-testid="mcp-server-meta-content"]')).to_have_text(
        json.dumps({"vendor": "acme"}, indent=2)
    )
    # Instructions is not styled as a section eyebrow: not uppercase, not a section title.
    assert ins.locator("summary").evaluate("el => getComputedStyle(el).textTransform") == "none"


@pytest.mark.browser
def test_tool_summary_description_once_and_sublabels(app_clean: str, page: Page) -> None:
    """A15: no chevron glyph in a tool's accessible name; the short description sits in the
    summary once and the body repeats it only when the full text is longer; sub-labels read
    'Description' and 'Input schema' in the field-label style."""
    _open_with_cache(page, app_clean, _info_cache(), "tool-info")
    items = page.locator(f'[data-testid="mcp-tools-list"] {_TOOL}')
    expect(items).to_have_count(3)
    short, long_, bare = items.nth(0), items.nth(1), items.nth(2)
    for it in (short, long_, bare):
        name = it.locator("summary").evaluate(
            "el => document.getElementById(el.getAttribute('aria-labelledby').split(' ')[0]).textContent"
        )
        assert "▸" not in name
    # Short description: in the summary, once; the body holds no Description label.
    expect(short.locator("summary")).to_contain_text("Plays a song.")
    short.locator("summary").click()
    assert short.locator(".mcp-info-label", has_text="Description").count() == 0
    assert short.inner_text().count("Plays a song.") == 1
    expect(short.locator(".mcp-info-label", has_text="Input schema")).to_be_visible()
    expect(short).to_contain_text("No input schema.")
    # Long description: cut in the summary, the full text in the body.
    long_.locator("summary").click()
    summary_text = long_.locator("summary").inner_text()
    assert "…" in summary_text and _LONG_DESC.strip() not in summary_text
    expect(long_.locator('[data-testid="mcp-tool-description"]')).to_have_text(_LONG_DESC.strip())
    expect(long_.locator('[data-testid="mcp-tool-schema"]')).to_be_visible()
    # No description at all: the body says so.
    bare.locator("summary").click()
    expect(bare).to_contain_text("No description provided.")
    # The sub-labels match a field label (size, weight).
    label = long_.locator(".mcp-info-label").first
    got = label.evaluate(
        "el => { const s = getComputedStyle(el); return [s.fontSize, s.fontWeight, s.textTransform]; }"
    )
    ref = page.locator('[data-field="name"]').evaluate(
        """el => { const l = el.closest('.field-group').querySelector('label');
        const s = getComputedStyle(l); return [s.fontSize, s.fontWeight, s.textTransform]; }"""
    )
    assert got == ref, (got, ref)


@pytest.mark.browser
def test_tool_names_and_descriptions_are_text_only(app_clean: str, page: Page) -> None:
    """Server-supplied tool text never becomes markup."""
    cache = _info_cache(
        tools=[
            {
                "name": "<img src=x onerror=window.__pwned=1>",
                "description": "<script>window.__pwned=1</script>\nsecond line " + "x" * 120,
                "input_schema": {"title": "<b>t</b>"},
            }
        ],
    )
    _open_with_cache(page, app_clean, cache, "xss-info")
    item = page.locator(_TOOL)
    expect(item).to_have_count(1)
    item.locator("summary").click()
    assert page.evaluate("() => window.__pwned") is None
    assert item.evaluate("el => el.querySelectorAll('img, script, b').length") == 0
    expect(item.locator("summary .ui-disclosure-text")).to_have_text(
        "<img src=x onerror=window.__pwned=1>"
    )


@pytest.mark.browser
def test_server_section_rejects_unsafe_website_and_icon_text_only(
    app_clean: str, page: Page
) -> None:
    """Squawk 0010 on the library: javascript: URLs never become href/src, and the rejected
    website still shows as inert text."""
    cache = _info_cache()
    cache["server_info"]["websiteUrl"] = "javascript:alert(1)"
    cache["server_info"]["icons"] = [{"src": "data:text/html,x", "mimeType": "image/png"}]
    _open_with_cache(page, app_clean, cache, "unsafe-info")
    section = page.locator(_SRV)
    expect(section.locator('[data-testid="mcp-server-icon"]')).to_have_count(0)
    expect(section.locator('[data-testid="mcp-server-website"] a')).to_have_count(0)
    expect(section.locator('[data-testid="mcp-server-website"]')).to_contain_text(
        "javascript:alert(1)"
    )


@pytest.mark.browser
def test_test_updates_server_section_in_place_and_keeps_open_state(
    app_clean: str, page: Page
) -> None:
    """Squawk 0102 without replacing the node: after a Test the Server section and an open
    Instructions disclosure and an open tool panel are the same elements, still open."""
    cache = _info_cache(instructions="Be kind.")
    sid = _open_with_cache(page, app_clean, cache, "inplace-info")
    real = _get_source(app_clean, sid)
    reported = {"version": "1.4.2"}

    def handle_get(route):
        if route.request.method != "GET":
            return route.fallback()
        body = json.loads(json.dumps(real))
        fresh = _info_cache(instructions="Be kind.")
        fresh["server_info"]["version"] = reported["version"]
        body["config"]["_cache"] = fresh
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route(re.compile(rf".*/api/mcp-sources/{re.escape(sid)}$"), handle_get)
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "ok", "tools": cache["tools"], "capabilities": {}}),
        ),
    )
    page.locator('[data-testid="mcp-server-instructions"] summary').click()
    page.locator(_TOOL).nth(1).locator("summary").click()
    page.evaluate(
        """() => {
          window.__srv = document.querySelector('[data-testid="mcp-server-info-section"]');
          window.__ins = document.querySelector('[data-testid="mcp-server-instructions"]');
          window.__tool = document.querySelectorAll('[data-testid="mcp-tool-item"]')[1];
        }"""
    )
    reported["version"] = "1.5.0"
    page.locator('[data-testid="mcp-test-connection"]').click()
    expect(page.locator('[data-testid="mcp-server-version"] dd')).to_have_text(
        "1.5.0", timeout=6000
    )
    same = page.evaluate(
        """() => ({
          srv: window.__srv === document.querySelector('[data-testid="mcp-server-info-section"]'),
          ins: window.__ins === document.querySelector('[data-testid="mcp-server-instructions"]'),
          insOpen: window.__ins.open,
          tool: window.__tool === document.querySelectorAll('[data-testid="mcp-tool-item"]')[1],
          toolOpen: window.__tool.open,
        })"""
    )
    assert same == {"srv": True, "ins": True, "insOpen": True, "tool": True, "toolOpen": True}


@pytest.mark.browser
def test_forget_hides_server_section_and_tools_show_hint(app_clean: str, page: Page) -> None:
    """Reset or Forget empties the tools list (the hint returns) and hides the Server section."""
    sid = _open_with_cache(page, app_clean, _info_cache(), "forget-info")
    assert sid
    expect(page.locator(_SRV)).to_be_visible()
    forget = page.locator('[data-testid="forget-mcp-connection-btn"]')
    forget.click()
    forget.click()
    expect(page.locator(_SRV)).to_be_hidden(timeout=6000)
    expect(page.locator('[data-testid="mcp-tools-list"]')).to_be_hidden()
    expect(page.locator('[data-testid="mcp-tools-section"]')).to_contain_text(
        "Press Test to load this server's tools."
    )
