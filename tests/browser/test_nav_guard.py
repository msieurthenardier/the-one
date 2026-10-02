"""Unified leave guard (``App.nav``) tests (M25 F2 L5, DD5).

Covers the guard object itself, the router adapter, every leave path, the
teardown-only discard, the link interceptor, focus after Stay/Continue, the
no-phantom-prompt invariant and ``beforeunload``.

Waits are state-driven (route, element or flag) -- no fixed sleeps except the
negative "no second dialog" windows.
"""

from __future__ import annotations

import re
import time

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.conftest import credentialed_context
from browser.seeders import SeededApp, seed_mock_agent, seed_mock_provider
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

DIALOG = '[data-testid="confirm-dialog-overlay"]'
STAY = '[data-testid="modal-cancel-btn"]'
CONTINUE = '[data-testid="modal-confirm-btn"]'
DESC = '[data-field="description"]'


# ── helpers ──────────────────────────────────────────────────────────────────


def _post(base: str, path: str, payload: dict) -> dict:
    r = httpx.post(base + path, json=payload, headers=auth_headers_for(base), timeout=5.0)
    assert r.status_code in (200, 201), f"{path}: {r.status_code} {r.text}"
    return r.json()


def _no_second_dialog(page: Page) -> None:
    page.wait_for_timeout(300)  # negative assertion window
    expect(page.locator(DIALOG)).to_have_count(0)


def _is_dirty(page: Page) -> bool:
    return page.evaluate("App.nav.isDirty()")


def _wait_dirty(page: Page, value: bool = True) -> None:
    page.wait_for_function("v => App.nav.isDirty() === v", arg=value)


def _open_agent(page: Page, app: SeededApp) -> str:
    """Open the seeded agent's editor (an intent click) and return its route."""
    _nav.goto_settled(page, app.base_url, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    page.locator('[data-testid="agent-item"]').first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    route = f"agents/{_nav.seg(app.agent_name)}/general"
    _nav.expect_route(page, route)
    return route


def _dirty_agent(page: Page) -> None:
    desc = page.locator(DESC)
    desc.click()
    desc.fill("dirty edit")
    _wait_dirty(page)


def _dirty_open_agent(page: Page, app: SeededApp) -> str:
    route = _open_agent(page, app)
    _dirty_agent(page)
    return route


def _active_id(page: Page) -> str | None:
    return page.evaluate("document.activeElement && document.activeElement.id")


# ── AC1: App.nav ─────────────────────────────────────────────────────────────


def test_register_source_replaces_and_isdirty_is_any(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "agents")
    out = page.evaluate(
        """() => {
          const n = App.nav;
          const before = n._sources().map(s => s.areaId);
          n.registerSource('t', { isDirty: () => false, discard() {} });
          const a = n.isDirty();
          n.registerSource('t', { isDirty: () => true, discard() {} });
          const b = n.isDirty();
          const count = n._sources().filter(s => s.areaId === 't').length;
          n.registerSource('t', { isDirty: () => false, discard() {} });
          return { before, a, b, count, after: n.isDirty(), pending: n.isPending() };
        }"""
    )
    assert "studio" in out["before"]
    assert (out["a"], out["b"], out["count"], out["after"], out["pending"]) == (
        False,
        True,
        1,
        False,
        False,
    )


def test_confirm_leave_clean_resolves_true_without_dialog(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "agents")
    assert page.evaluate("App.nav.confirmLeave({})") is True
    expect(page.locator(DIALOG)).to_have_count(0)


def test_confirm_leave_stay_continue_throwing_discard_and_join(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "agents")
    page.evaluate(
        """() => {
          window.__discards = 0;
          window.__flag = true;
          App.nav.registerSource('t', {
            isDirty: () => window.__flag,
            discard() { window.__discards++; window.__flag = false; throw new Error('boom'); }
          });
          window.__p1 = App.nav.confirmLeave({ caller: 'x' });
          window.__p2 = App.nav.confirmLeave({ caller: 'x' });
        }"""
    )
    # Repeated calls from the same non-router caller get the SAME promise; a
    # different caller (or the router) while pending resolves Stay.
    assert page.evaluate("window.__p1 === window.__p2") is True
    assert page.evaluate("App.nav.isPending()") is True
    assert page.evaluate("App.nav.confirmLeave({ caller: 'y' })") is False
    assert page.evaluate("App.nav.confirmLeave({ router: true })") is False
    expect(page.locator(DIALOG)).to_have_count(1)
    expect(page.locator(".modal-dialog-title")).to_have_text("Unsaved changes")
    expect(page.locator(STAY)).to_be_focused()

    page.locator(STAY).click()
    assert page.evaluate("window.__p1") is False
    assert page.evaluate("[window.__discards, App.nav.isPending()]") == [0, False]

    # Continue: a throwing discard still resolves true (and ran exactly once).
    page.evaluate("() => { window.__flag = true; window.__p1 = App.nav.confirmLeave({}); }")
    page.locator(CONTINUE).click()
    assert page.evaluate("window.__p1") is True
    assert page.evaluate("window.__discards") == 1
    assert _is_dirty(page) is False


# ── AC2: router adapter ──────────────────────────────────────────────────────


def test_clean_go_commits_in_the_same_tick(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "agents")
    route = page.evaluate(
        """() => {
          App.router.go('settings/providers');
          return App.router.current().route;  // read synchronously, no await
        }"""
    )
    assert route == "settings/providers"


def test_go_while_inline_nav_dialog_pending_resolves_stay_and_does_not_join(
    app_with_agent: SeededApp, page: Page
) -> None:
    _dirty_open_agent(page, app_with_agent)
    page.locator('[data-testid="new-agent-btn"]').first.dispatch_event(
        "click"
    )  # hidden while editing: drive the handler directly
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)

    # A rail-equivalent go() while that dialog is pending is Stay: it never joins.
    assert page.evaluate("App.router.go('library/mcp')") is False
    assert page.evaluate("App.router.isDeciding()") is False
    expect(page.locator(DIALOG)).to_have_count(1)

    # Continue runs ONLY the create-mode action: the URL never went to Library.
    page.locator(CONTINUE).click()
    name = page.locator('[data-field="name"]')
    expect(name).to_be_visible(timeout=8000)
    expect(name).to_have_value("")
    assert page.evaluate("App.router.current().destination") == "agents"
    _no_second_dialog(page)


# ── AC3: paths ───────────────────────────────────────────────────────────────


def test_item_selection_while_dirty_one_dialog(app_with_agent: SeededApp, page: Page) -> None:
    seed_mock_agent(app_with_agent.base_url, app_with_agent.provider_id, name="second-agent")
    _nav.goto_settled(page, app_with_agent.base_url, "agents")
    expect(_nav.destination_panel(page, "agents")).to_be_visible(timeout=8000)
    page.locator('[data-testid="agent-item"]', has_text="test-agent").first.click()
    expect(page.locator(".editor-title")).to_have_text("test-agent", timeout=8000)
    route = _nav.current_route(page)
    _dirty_agent(page)

    # The tile list is hidden while an editor is open: drive the tile's handler directly.
    page.locator('[data-testid="agent-item"]', has_text="second-agent").first.dispatch_event(
        "click"
    )
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    _no_second_dialog(page)
    expect(page.locator(DESC)).to_have_value("dirty edit")
    _nav.expect_route(page, route)

    # The tile list is hidden while an editor is open: drive the tile's handler directly.
    page.locator('[data-testid="agent-item"]', has_text="second-agent").first.dispatch_event(
        "click"
    )
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    expect(page.locator(".editor-title")).to_have_text("second-agent", timeout=8000)
    _nav.expect_route(page, f"agents/{_nav.seg('second-agent')}/general")
    _no_second_dialog(page)
    assert _is_dirty(page) is False


def test_editor_back_guarded_but_create_cancel_is_not(
    app_with_agent: SeededApp, page: Page
) -> None:
    _dirty_open_agent(page, app_with_agent)
    page.locator('[data-testid="back-agent-btn"]').click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    _no_second_dialog(page)
    expect(page.locator(DESC)).to_have_value("dirty edit")
    page.locator('[data-testid="back-agent-btn"]').click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _nav.expect_route(page, "agents")
    expect(page.locator('[data-testid="tab-general"]')).to_have_count(0)

    # Create-mode Cancel (abandoning a NEW item) stays unguarded even when dirty.
    page.locator('[data-testid="new-agent-btn"]').first.click()
    name = page.locator('[data-field="name"]')
    expect(name).to_be_visible(timeout=8000)
    name.fill("half-made")
    _wait_dirty(page)
    page.locator('[data-testid="cancel-agent-btn"]').click()
    _no_second_dialog(page)
    expect(name).to_have_count(0)
    assert _is_dirty(page) is False


def test_legacy_hash_link_in_content_redirects_and_is_guarded(
    app_with_agent: SeededApp, page: Page
) -> None:
    route = _dirty_open_agent(page, app_with_agent)
    legacy = _nav.legacy_hash("library/mcp")
    page.evaluate(
        """href => {
          const a = document.createElement('a');
          a.id = 'probe-link'; a.href = href; a.textContent = 'mcp';
          document.body.appendChild(a);
        }""",
        legacy,
    )
    page.locator("#probe-link").click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    _no_second_dialog(page)
    _nav.expect_route(page, route)
    expect(page.locator(DESC)).to_have_value("dirty edit")

    page.locator("#probe-link").click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    _nav.expect_route(page, "library/mcp")  # the legacy href redirected
    _no_second_dialog(page)


def test_connector_back_goes_through_app_nav(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "library/connectors")
    page.locator('[data-testid="new-connector-btn"]').click()
    name = page.locator('[data-field="name"]')
    expect(name).to_be_visible(timeout=8000)
    name.fill("half-made-connector")
    _wait_dirty(page)

    page.locator('[data-testid="back-connector-btn"]').click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    _no_second_dialog(page)
    expect(name).to_have_value("half-made-connector")
    _nav.expect_route(page, "library/connectors")

    page.locator('[data-testid="back-connector-btn"]').click()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    expect(page.locator('[data-testid="new-connector-btn"]')).to_be_visible(timeout=8000)
    expect(name).to_have_count(0)
    assert _is_dirty(page) is False
    _no_second_dialog(page)


def test_agent_enter_create_mode_goes_through_app_nav(
    app_with_agent: SeededApp, page: Page
) -> None:
    route = _dirty_open_agent(page, app_with_agent)
    page.locator('[data-testid="new-agent-btn"]').first.dispatch_event("click")
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(STAY).click()
    _no_second_dialog(page)
    expect(page.locator(DESC)).to_have_value("dirty edit")
    _nav.expect_route(page, route)

    page.locator('[data-testid="new-agent-btn"]').first.dispatch_event("click")
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    name = page.locator('[data-field="name"]')
    expect(name).to_be_visible(timeout=8000)
    expect(name).to_have_value("")
    assert _is_dirty(page) is False
    _no_second_dialog(page)


# ── AC4: discard is real ─────────────────────────────────────────────────────


def _setup_agent(app: SeededApp, page: Page):
    return {
        "base": app.base_url,
        "list": "agents",
        "item": f"agents/{_nav.seg(app.agent_name)}/general",
        "field": DESC,
    }


def _setup_provider(app: SeededApp, page: Page):
    return {
        "base": app.base_url,
        "list": "settings/providers",
        "item": f"settings/providers/{_nav.seg(app.provider_id)}",
        "field": "#pf-name",
    }


def _setup_kb(app: SeededApp, page: Page):
    kb = _post(app.base_url, "/api/knowledge-bases", {"name": "Saved KB"})
    return {
        "base": app.base_url,
        "list": "library/knowledge",
        "item": f"library/knowledge/{_nav.seg(kb['id'])}",
        "field": '[data-testid="kb-name-input"]',
    }


def _setup_ks(app: SeededApp, page: Page):
    return {
        "base": app.base_url,
        "list": "settings/general",
        "item": "settings/knowledge-indexing",
        "field": '[data-testid="knowledge-size-chars-input"]',
    }


@pytest.mark.parametrize("how", ["intent", "traversal"])
@pytest.mark.parametrize("setup", [_setup_agent, _setup_provider, _setup_kb, _setup_ks])
def test_discard_tears_down_and_reopen_shows_saved_value(
    app_with_agent: SeededApp, page: Page, setup, how: str
) -> None:
    cfg = setup(app_with_agent, page)
    _nav.goto_settled(page, cfg["base"], cfg["list"])
    page.evaluate("r => App.router.go(r)", cfg["item"])  # an intent: pushes
    field = page.locator(cfg["field"])
    expect(field).to_be_visible(timeout=8000)
    if setup is _setup_ks:  # the settings form paints empty, then hydrates from the server
        expect(field).not_to_have_value("", timeout=8000)
    saved = field.input_value()
    field.click()
    field.fill("0" if setup is _setup_ks else "dirty-value")
    _wait_dirty(page)

    if how == "intent":
        page.evaluate("r => { window.__leave = App.router.go(r); }", cfg["list"])
    else:
        page.go_back()
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    expect(field).to_have_count(0, timeout=8000)  # the editor is torn down
    assert _is_dirty(page) is False
    _no_second_dialog(page)

    if how == "intent":
        page.evaluate("r => App.router.go(r)", cfg["item"])
    else:
        page.go_forward()
    expect(page.locator(cfg["field"])).to_be_visible(timeout=8000)
    expect(page.locator(cfg["field"])).to_have_value(saved)
    assert _is_dirty(page) is False


def test_form_edits_do_not_mutate_the_cached_agent(app_with_agent: SeededApp, page: Page) -> None:
    _open_agent(page, app_with_agent)
    page.evaluate(
        """() => {
          const s = App.areas.find(a => a.id === 'studio');
          window.__orig = s._selectedAgent;
          window.__snap = JSON.stringify(s._selectedAgent);
        }"""
    )
    _dirty_agent(page)
    page.locator('[data-testid="tab-tools"]').click()
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute("aria-selected", "true")
    page.locator('[data-testid="tab-general"]').click()
    out = page.evaluate(
        """() => {
          const s = App.areas.find(a => a.id === 'studio');
          return { same: s._selectedAgent === window.__orig,
                   unchanged: JSON.stringify(s._selectedAgent) === window.__snap };
        }"""
    )
    assert out == {"same": True, "unchanged": True}


# ── AC5: link interceptor ────────────────────────────────────────────────────

_ANCHOR_JS = """
([id, href, attrs]) => {
  const a = document.createElement('a');
  a.id = id; a.setAttribute('href', href);
  for (const [k, v] of Object.entries(attrs || {})) a.setAttribute(k, v);
  const icon = document.createElement('span');
  icon.className = 'probe-icon'; icon.textContent = '*';
  a.appendChild(icon);
  a.appendChild(document.createTextNode(' link'));
  document.body.appendChild(a);
}
"""


def test_route_link_uses_go_with_anchor_opener_even_with_icon_child(
    app_clean: str, page: Page
) -> None:
    _nav.goto_settled(page, app_clean, "agents")
    page.evaluate(_ANCHOR_JS, ["probe", _nav.href("settings/providers"), {}])
    length = page.evaluate("history.length")
    page.evaluate(
        """() => {
          window.__opener = null;
          const go = App.router.go;
          App.router.go = function (r, o) {
            window.__opener = o && o.opener && o.opener.id;
            return go.apply(this, arguments);
          };
        }"""
    )
    page.locator("#probe .probe-icon").click()  # the click lands on the child
    _nav.expect_route(page, "settings/providers")
    assert page.evaluate("window.__opener") == "probe"
    assert page.evaluate("history.length") == length + 1


def test_interceptor_skips_modified_nonprimary_target_download_and_element_links(
    app_clean: str, page: Page
) -> None:
    _nav.goto_settled(page, app_clean, "agents")
    href = _nav.href("settings/providers")
    page.evaluate(_ANCHOR_JS, ["plain", href, {}])
    page.evaluate(_ANCHOR_JS, ["blank", href, {"target": "_blank"}])
    page.evaluate(_ANCHOR_JS, ["dl", href, {"download": ""}])
    page.evaluate(_ANCHOR_JS, ["skip", "#main-content", {}])
    page.evaluate(_ANCHOR_JS, ["bare", "#", {}])
    page.evaluate(_ANCHOR_JS, ["unknown", "#installation", {}])
    # Synthetic clicks never navigate; defaultPrevented reports whether the
    # interceptor claimed the click. Handlers are neutralised so a "not
    # intercepted" click cannot navigate the test page away.
    out = page.evaluate(
        """() => {
          const fire = (id, init) => {
            const a = document.getElementById(id);
            const base = { bubbles: true, cancelable: true };
            const e = new MouseEvent('click', Object.assign(base, init || {}));
            a.dispatchEvent(e);
            return e.defaultPrevented;
          };
          const res = {
            plain: fire('plain'),
            ctrl: fire('plain', { ctrlKey: true }),
            meta: fire('plain', { metaKey: true }),
            shift: fire('plain', { shiftKey: true }),
            middle: fire('plain', { button: 1 }),
            blank: fire('blank'),
            dl: fire('dl'),
          };
          return res;
        }"""
    )
    # Only the plain primary click was claimed (and it navigated).
    assert out["plain"] is True
    assert [out[k] for k in ("ctrl", "meta", "shift", "middle", "blank", "dl")] == [False] * 6
    _nav.expect_route(page, "settings/providers")

    hash_before = page.evaluate("location.hash")
    length = page.evaluate("history.length")
    fire = """id => {
      const e = new MouseEvent('click', { bubbles: true, cancelable: true });
      document.getElementById(id).dispatchEvent(e);
      return e.defaultPrevented;
    }"""
    # A bare # and an unknown fragment are swallowed: no hash change, no entry.
    assert page.evaluate(fire, "bare") is True
    assert page.evaluate(fire, "unknown") is True
    assert page.evaluate("[location.hash, history.length]") == [hash_before, length]
    # #main-content stays native (the browser performs the fragment navigation).
    assert page.evaluate(fire, "skip") is False
    page.wait_for_function("location.hash === '#main-content'")


def test_chat_message_links_bare_unknown_and_route(app_clean: str, page: Page) -> None:
    provider_id = seed_mock_provider(
        app_clean,
        config={
            "response": {
                "content": (
                    "[bare](#) [frag](#installation) [route]("
                    + _nav.href("settings/providers")
                    + ")"
                )
            }
        },
    )
    agent = seed_mock_agent(app_clean, provider_id)
    _nav.goto_settled(page, app_clean, "chats")
    page.locator(".chat-welcome-item").filter(has_text=agent).click()
    expect(page.locator(".session-agent-badge")).to_have_text(agent, timeout=8000)
    page.locator('[data-testid="chat-input"]').fill("hi")
    page.locator('[data-testid="chat-send-btn"]').click()
    bubble = page.locator('[data-testid="message"].assistant').last
    expect(bubble.locator("a")).to_have_count(3, timeout=10000)
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_enabled(timeout=10000)

    # The session join canonicalises the URL to chats/{id}; wait for it so the
    # before/after comparison below measures only the link clicks.
    _nav.wait_for_route_prefix(page, "chats/")
    hash_before = page.evaluate("location.hash")
    length = page.evaluate("history.length")
    bubble.locator("a", has_text="bare").click()
    bubble.locator("a", has_text="frag").click()
    assert page.evaluate("[location.hash, history.length]") == [hash_before, length]

    bubble.locator("a", has_text="route").click()
    _nav.expect_route(page, "settings/providers")


# ── AC6: focus (both engines) ────────────────────────────────────────────────


@pytest.mark.parametrize("via", ["rail", "link", "back"])
def test_focus_after_stay_and_continue(engine_browser, app_with_agent: SeededApp, via: str) -> None:
    context = credentialed_context(engine_browser, app_with_agent.base_url)
    page = context.new_page()
    try:
        _open_agent(page, app_with_agent)
        _dirty_agent(page)
        if via == "link":
            page.evaluate(_ANCHOR_JS, ["probe", _nav.href("library/mcp"), {}])

        def trigger() -> None:
            if via == "rail":
                _nav.destination_locator(page, "library").click()
            elif via == "link":
                page.locator("#probe").click()
            else:
                page.go_back()

        trigger()
        expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
        page.locator(STAY).click()
        expect(page.locator(DIALOG)).to_have_count(0)
        # Stay: focus returns to the opener.
        if via == "rail":
            page.wait_for_function("document.activeElement.dataset.testid === 'rail-library'")
        elif via == "link":
            page.wait_for_function("document.activeElement.id === 'probe'")
        else:
            page.wait_for_function("document.activeElement.matches('[data-field=\"description\"]')")

        trigger()
        expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
        page.locator(CONTINUE).click()
        # Continue: #main-content takes focus AFTER the commit.
        expect(page.locator(DIALOG)).to_have_count(0)
        page.wait_for_function(
            "document.activeElement && document.activeElement.id === 'main-content'"
        )
        assert _is_dirty(page) is False
        if via == "back":
            _nav.expect_route(page, "agents")
        else:
            expect(page.locator('[data-testid="tab-general"]')).to_have_count(0, timeout=8000)
    finally:
        context.close()


# ── AC8: no phantom prompts ──────────────────────────────────────────────────


def _confirm_delete(page: Page, button, api_fragment: str) -> None:
    """Arm then commit a two-step delete, waiting for the DELETE response."""
    button.click()
    expect(button).to_have_class(re.compile(r"\bconfirm-delete\b"))
    with page.expect_response(
        lambda r: api_fragment in r.url and r.request.method == "DELETE"
    ) as resp:
        button.click()
    assert resp.value.status in (200, 204)


def _assert_leaves_silently(page: Page) -> None:
    assert _is_dirty(page) is False
    assert page.evaluate("App.router.go('chats')") is True  # resolves with no dialog
    _no_second_dialog(page)


def test_no_phantom_after_agent_save_and_delete(app_with_agent: SeededApp, page: Page) -> None:
    _open_agent(page, app_with_agent)
    _dirty_agent(page)
    save_btn = page.locator('[data-testid="save-agent-btn"]')
    save_btn.click()
    page.wait_for_function("() => !App.nav.isDirty()")
    expect(page.locator(DESC)).to_have_value("dirty edit")
    # The save chain re-renders the editor asynchronously; its clean Save button
    # marks the END of it (a stale continuation could otherwise re-select the
    # agent we are about to delete).
    expect(save_btn).to_be_disabled(timeout=8000)
    _dirty_agent(page)
    delete_btn = page.locator('[data-testid="delete-agent-btn"]')
    _confirm_delete(page, delete_btn, "/api/agents/")
    expect(page.locator('[data-testid="tab-general"]')).to_have_count(0, timeout=8000)
    _assert_leaves_silently(page)


def test_no_phantom_after_mcp_source_save_and_delete(app_clean: str, page: Page) -> None:
    sid = _post(
        app_clean,
        "/api/mcp-sources",
        {"name": "phantom", "type": "stdio", "config": {"command": "x", "env": {}}},
    )["id"]
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    name = page.locator('[data-field="name"]')
    expect(name).to_be_visible(timeout=8000)
    name.fill("phantom-2")
    _wait_dirty(page)
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    page.wait_for_function("() => !App.nav.isDirty()")
    name.fill("phantom-3")
    _wait_dirty(page)
    delete_btn = page.locator('[data-testid="delete-mcp-source-btn"]')
    _confirm_delete(page, delete_btn, "/api/mcp-sources/")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_have_count(0, timeout=8000)
    _assert_leaves_silently(page)


def test_no_phantom_after_provider_save_and_delete(
    app_with_provider: SeededApp, page: Page
) -> None:
    _nav.goto_settled(
        page,
        app_with_provider.base_url,
        f"settings/providers/{_nav.seg(app_with_provider.provider_id)}",
    )
    name = page.locator("#pf-name")
    expect(name).to_be_visible(timeout=8000)
    name.fill("phantom-provider")
    _wait_dirty(page)
    page.locator('[data-testid="save-provider-btn"]').click()
    page.wait_for_function("() => !App.nav.isDirty()")
    name.fill("phantom-provider-2")
    _wait_dirty(page)
    delete_btn = page.locator('[data-testid="delete-provider-btn"]')
    _confirm_delete(page, delete_btn, "/api/providers/")
    expect(page.locator("#pf-name")).to_have_count(0, timeout=8000)
    _assert_leaves_silently(page)


def test_stale_dirty_flag_with_no_editor_raises_neither_guard_nor_beforeunload(
    app_clean: str, page: Page
) -> None:
    _nav.goto_settled(page, app_clean, "agents")
    page.evaluate("() => { App.areas.find(a => a.id === 'studio')._dirty = true; }")
    assert page.evaluate("App.areas.find(a => a.id === 'studio')._dirty") is True
    assert _is_dirty(page) is False
    prevented = page.evaluate(
        """() => {
          const e = new Event('beforeunload', { cancelable: true });
          window.dispatchEvent(e);
          return e.defaultPrevented;
        }"""
    )
    assert prevented is False
    assert page.evaluate("App.router.go('settings/providers')") is True
    _no_second_dialog(page)


def test_discard_during_inflight_provider_save_does_not_resurrect_the_editor(
    app_with_provider: SeededApp, page: Page
) -> None:
    held: list = []
    pid = app_with_provider.provider_id
    page.route(
        f"**/api/providers/{pid}",
        lambda route: held.append(route) if route.request.method == "PUT" else route.continue_(),
    )
    _nav.goto_settled(page, app_with_provider.base_url, f"settings/providers/{_nav.seg(pid)}")
    name = page.locator("#pf-name")
    expect(name).to_be_visible(timeout=8000)
    name.fill("inflight")
    _wait_dirty(page)
    page.locator('[data-testid="save-provider-btn"]').click()
    deadline = time.monotonic() + 15
    while not held and time.monotonic() < deadline:  # the PUT reaches the route handler
        page.wait_for_timeout(50)
    assert held, "the save PUT never reached the route handler"

    page.evaluate(
        "() => { window.__leave = App.router.go("
        "App.router.href({destination: 'settings', section: 'general'})); }"
    )
    expect(page.locator(DIALOG)).to_have_count(1, timeout=8000)
    page.locator(CONTINUE).click()
    expect(page.locator("#pf-name")).to_have_count(0, timeout=8000)

    # The save now resolves after the discard: the editor must stay gone.
    with page.expect_response(lambda r: r.request.method == "PUT" and pid in r.url):
        held[0].continue_()
    page.wait_for_timeout(300)  # negative window: nothing may re-mount
    expect(page.locator("#pf-name")).to_have_count(0)
    assert page.evaluate("App.areas.find(a => a.id === 'admin')._providerFormMode") is None
    assert _is_dirty(page) is False


# ── AC9: beforeunload (Chromium only; WebKit gives no equivalent guarantee) ──


def test_beforeunload_prompts_when_dirty_and_not_when_clean(
    app_with_agent: SeededApp, page: Page
) -> None:
    seen: list[str] = []
    page.on("dialog", lambda d: (seen.append(d.type), d.accept()))

    # Clean: a user gesture, then reload -> no prompt.
    _open_agent(page, app_with_agent)
    page.locator('[data-testid="tab-general"]').click()
    page.reload()
    page.wait_for_function("() => !!(window.App && App.router && App.router.current())")
    assert seen == []

    # Dirty with REAL input (a user gesture is required), then reload.
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)
    desc = page.locator(DESC)
    desc.click()
    page.keyboard.type("x")
    _wait_dirty(page)
    page.reload()
    assert seen == ["beforeunload"]
