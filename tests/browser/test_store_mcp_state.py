"""``App.usage.mcpState`` / ``mcpStateLabel`` (leg 08a, DD6).

The one client-side derivation of an MCP server's connection state, read by the
editor (leg 08b) and the Library list (leg 11).  A table over ``has_access_token`` x
``oauth_active`` x ``_cache.last_check`` x cached tools, each row's expected state
written out.  ``checkedAt`` is in SECONDS.
"""

from __future__ import annotations

import pytest
from browser import _nav
from playwright.sync_api import Page

TOOLS = [{"name": "a"}, {"name": "b"}]


def _src(*, token=False, oauth=False, lc=None, tools=True, last_updated=None, cache=True):
    if not cache:
        return {"config": {}, "has_access_token": token, "oauth_active": oauth}
    c: dict = {}
    if tools:
        c["tools"] = TOOLS
    if lc is not None:
        c["last_check"] = lc
    if last_updated is not None:
        c["last_updated"] = last_updated
    return {"config": {"_cache": c}, "has_access_token": token, "oauth_active": oauth}


def _lc(status):
    return {"status": status, "at": 1000.5}


# (source, expected state, expected tools, expected checkedAt)
CASES = {
    "no cache": (_src(cache=False), "none", None, None),
    "empty cache": (_src(tools=False), "none", None, None),
    "pre-flight: tools, no last_check": (_src(last_updated=500.0), "connected", 2, 500.0),
    "ok + tools": (_src(lc=_lc("ok"), last_updated=500.0), "connected", 2, 1000.5),
    "ok, no tools": (_src(lc=_lc("ok"), tools=False), "none", None, 1000.5),
    "error + tools": (_src(lc=_lc("error")), "error", 2, 1000.5),
    "error, no tools": (_src(lc=_lc("error"), tools=False), "error", None, 1000.5),
    "auth_required, no token": (_src(lc=_lc("auth_required")), "signin", 2, 1000.5),
    "auth_required, no token, no tools": (
        _src(lc=_lc("auth_required"), tools=False),
        "signin",
        None,
        1000.5,
    ),
    "stale auth_required with a token and tools": (
        _src(lc=_lc("auth_required"), token=True),
        "connected",
        2,
        1000.5,
    ),
    "auth_required with a token, no tools": (
        _src(lc=_lc("auth_required"), token=True, tools=False),
        "none",
        None,
        1000.5,
    ),
    "oauth_active, no token": (_src(oauth=True), "signin", 2, None),
    "oauth_active, no token, last ok": (_src(oauth=True, lc=_lc("ok")), "signin", 2, 1000.5),
    "oauth_active, no token, last error": (_src(oauth=True, lc=_lc("error")), "signin", 2, 1000.5),
    "oauth_active with a token, tools": (_src(oauth=True, token=True), "connected", 2, None),
    "oauth_active with a token, error": (
        _src(oauth=True, token=True, lc=_lc("error")),
        "error",
        2,
        1000.5,
    ),
    "token only, no cache": (_src(token=True, cache=False), "none", None, None),
}


@pytest.mark.browser
def test_mcp_state_table(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "library")
    page.wait_for_function("() => !!(window.App && App.usage && App.usage.mcpState)")
    got = page.evaluate(
        "(rows) => rows.map(r => App.usage.mcpState(r))", [v[0] for v in CASES.values()]
    )
    for (name, (_s, state, tools, at)), res in zip(CASES.items(), got, strict=True):
        assert res == {"state": state, "tools": tools, "checkedAt": at}, name


@pytest.mark.browser
def test_mcp_state_tolerates_missing_input_and_labels(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "library")
    page.wait_for_function("() => !!(window.App && App.usage && App.usage.mcpState)")
    res = page.evaluate(
        """() => ({
          n: App.usage.mcpState(null),
          u: App.usage.mcpState(undefined),
          badlc: App.usage.mcpState({config: {_cache: {last_check: 'x'}}}),
          labels: ['signin', 'error', 'connected', 'none'].map(App.usage.mcpStateLabel),
        })"""
    )
    none = {"state": "none", "tools": None, "checkedAt": None}
    assert res["n"] == none and res["u"] == none and res["badlc"] == none
    assert res["labels"] == ["Sign-in needed", "Couldn't connect", "Connected", "Not connected"]
