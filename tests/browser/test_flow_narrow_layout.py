"""Narrow-window layout and single-overlay contract tests (Mission 38 Flight 1).

Covers the minimum desktop window client area ``624x321`` (640x360 outer), wide
``1280x800`` baseline, and below-624px plain-browser overflow safety across
Chromium and WebKit:

* Main pane width >= 360px, zero horizontal document scroll, rail fits height;
* Open chat keeps >= 3 visible transcript lines above ``.ui-composer`` at 321px;
* Bottom-right ``gg-corner-button`` never overlaps the scrolled last control;
* ``#app-sidebar`` overlay open/dismiss/navigation/resize lifecycle + focus return;
* At most one overlay (``#app-sidebar``, ``#chat-drawer``, ``#gleepglorp-drawer``)
  open at once below breakpoints, with focus moving into each opened overlay;
* Modals (Jump-to, Agent picker) fit within ``624x321``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from browser import _chats, _drawer, _lists, _nav
from browser.conftest import SeededApp, credentialed_context
from browser.seeders import (
    enable_notes,
    seed_connector,
    seed_knowledge_base,
    seed_mcp_source,
    seed_mock_agent,
    seed_mock_provider,
    seed_note,
    seed_secret,
    seed_session,
)
from playwright.sync_api import Browser, BrowserContext, Page, expect

from the_one.db.codec import encode_messages
from the_one.llm.base import Message

pytestmark = pytest.mark.browser

NARROW = {"width": 624, "height": 321}
WIDE = {"width": 1280, "height": 800}
TINY = {"width": 480, "height": 321}

SIDEBAR_TOGGLE = '[data-testid="rail-sidebar-toggle"]'
SIDEBAR_CLOSE = '[data-testid="narrow-sidebar-close"]'
CHAT_DRAWER = '[data-testid="chat-drawer"]'
CHAT_DRAWER_TOGGLE = '[data-testid="chat-drawer-toggle"]'


@contextmanager
def _error_watch(page: Page) -> Iterator[list[str]]:
    errors: list[str] = []

    def _on_pageerror(err) -> None:
        errors.append(f"pageerror: {err}")

    def _on_console(msg) -> None:
        if msg.type == "error":
            errors.append(f"console.error: {msg.text}")

    page.on("pageerror", _on_pageerror)
    page.on("console", _on_console)
    try:
        yield errors
    finally:
        page.remove_listener("pageerror", _on_pageerror)
        page.remove_listener("console", _on_console)


def _new_narrow_page(
    browser: Browser, base_url: str, viewport: dict[str, int] | None = None
) -> tuple[BrowserContext, Page]:
    ctx = credentialed_context(browser, base_url, viewport=viewport or NARROW)
    p = ctx.new_page()
    return ctx, p


def _assert_shell_bounds(
    page: Page, *, min_main_width: int = 360, expect_narrow: bool = True
) -> None:
    metrics = page.evaluate(
        """() => {
          const se = document.scrollingElement || document.documentElement;
          const row = document.querySelector('.app-shell-row');
          const rail = document.getElementById('app-rail');
          const main = document.getElementById('main-content');
          const sidebar = document.getElementById('app-sidebar');
          const toggle = document.querySelector('[data-testid="rail-sidebar-toggle"]');
          const jump = document.querySelector('[data-testid="rail-jump-to"]');
          const railButtons = Array.from(
            document.querySelectorAll('#app-rail a, #app-rail button')
          ).filter(el => !el.hidden && getComputedStyle(el).display !== 'none');
          const badRailBtns = railButtons.filter(el => {
            const r = el.getBoundingClientRect();
            return r.top < -1 || r.bottom > window.innerHeight + 1 || r.left < -1;
          }).map(el => el.getAttribute('data-testid') || el.textContent.trim());
          return {
            scrollWidth: se.scrollWidth,
            clientWidth: se.clientWidth,
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            dataNarrow: row ? row.getAttribute('data-narrow') : null,
            mainRect: main ? main.getBoundingClientRect().toJSON() : null,
            railRect: rail ? rail.getBoundingClientRect().toJSON() : null,
            sidebarVisible: !!(
              sidebar && getComputedStyle(sidebar).display !== 'none' && !sidebar.hidden
            ),
            toggleVisible: !!(
              toggle && !toggle.hidden && getComputedStyle(toggle).display !== 'none'
            ),
            jumpVisible: !!(jump && !jump.hidden && getComputedStyle(jump).display !== 'none'),
            badRailBtns,
          };
        }"""
    )
    assert metrics["scrollWidth"] <= metrics["clientWidth"], (
        f"horizontal overflow: {metrics['scrollWidth']} > {metrics['clientWidth']}"
    )
    main_rect = metrics["mainRect"]
    assert main_rect and main_rect["width"] >= min_main_width, f"main pane too narrow: {main_rect}"
    assert main_rect["right"] <= metrics["innerWidth"] + 1, f"main overflows right: {main_rect}"
    assert not metrics["badRailBtns"], f"rail controls clipped vertically: {metrics['badRailBtns']}"
    assert metrics["jumpVisible"], "Jump-to rail button should stay visible"
    if expect_narrow:
        assert metrics["dataNarrow"] == "true"
        assert metrics["toggleVisible"]
        assert not metrics["sidebarVisible"]
    else:
        assert metrics["dataNarrow"] is None
        assert not metrics["toggleVisible"]
        assert metrics["sidebarVisible"]


def _count_visible_transcript_lines(page: Page) -> int:
    return int(
        page.evaluate(
            """() => {
              const container = document.querySelector('.chat-instance .messages');
              const composer = document.querySelector('.chat-instance .ui-composer');
              if (!container || !composer) return 0;
              const cr = container.getBoundingClientRect();
              const compR = composer.getBoundingClientRect();
              const maxBottom = Math.min(cr.bottom, compR.top) + 1;
              const minTop = cr.top - 1;
              const bands = new Set();
              const msgs = container.querySelectorAll('[data-testid="message"]');
              for (const msg of msgs) {
                const walker = document.createTreeWalker(msg, NodeFilter.SHOW_TEXT);
                let node;
                while ((node = walker.nextNode())) {
                  if (!node.nodeValue || !node.nodeValue.trim()) continue;
                  const range = document.createRange();
                  range.selectNodeContents(node);
                  for (const r of range.getClientRects()) {
                    if (r.width < 1 || r.height < 1) continue;
                    if (r.top >= minTop && r.bottom <= maxBottom) {
                      bands.add(Math.round(r.top / 4));
                    }
                  }
                }
              }
              return bands.size;
            }"""
        )
    )


def _assert_last_control_not_covered(page: Page, *, route_hint: str) -> None:
    expect(page.locator(_drawer.BTN)).to_be_visible()
    result = page.evaluate(
        """() => {
          const candidates = [
            '.area-studio .tabpanel:not([hidden]):not(.ui-tabs--flush)',
            '.area-studio .studio-editor',
            '.area-studio .studio-section-content',
            '.area-admin .admin-content',
          ];
          const scrollers = [];
          for (const sel of candidates) {
            for (const el of document.querySelectorAll(sel)) {
              const st = getComputedStyle(el);
              if (el.getClientRects().length === 0) continue;
              if (
                st.overflowY === 'auto'
                || st.overflowY === 'scroll'
                || el.scrollHeight > el.clientHeight
              ) {
                scrollers.push(el);
              }
            }
          }
          // Prefer a scroller that actually scrolls; otherwise fall back to visible container.
          const scroller =
            scrollers.find(el => el.scrollHeight > el.clientHeight + 1) || scrollers[0] || null;
          if (!scroller) return { ok: false, reason: 'no container found' };
          scroller.scrollTop = scroller.scrollHeight;

          const activePanel = scroller.querySelector('.tabpanel:not([hidden])');
          const scope = activePanel || scroller;
          const seen = new Set();
          const controls = [];
          for (const el of scope.querySelectorAll(
            'button, a[href], summary, [role="switch"], '
            + 'input:not([type="hidden"]), select, textarea'
          )) {
            if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
            if (el.closest('[hidden], details:not([open]) > :not(summary)')) continue;
            const target =
              el.tagName === 'INPUT' && el.type === 'checkbox' && el.closest('label')
                ? el.closest('label')
                : el;
            if (seen.has(target)) continue;
            seen.add(target);
            const r = target.getBoundingClientRect();
            if (r.width >= 10 && r.height >= 10) controls.push(target);
          }
          if (!controls.length) return { ok: true, skipped: 'no interactive controls' };
          const last = controls[controls.length - 1];
          // First test max bottom scroll (where the bottom-most controls sit nearest
          // #gleepglorp-corner-button). Only if trailing read-only content pushed the
          // last control past the top of a short viewport, scroll it back to the bottom
          // of the visible area so scroll-padding-bottom clearance is also exercised.
          scroller.scrollTop = scroller.scrollHeight;
          let r = last.getBoundingClientRect();
          if (r.top < 0 || r.bottom > window.innerHeight) {
            last.scrollIntoView({ block: 'end', inline: 'nearest' });
            r = last.getBoundingClientRect();
          }
          const cx = Math.min(Math.max(r.left + r.width / 2, 1), window.innerWidth - 2);
          const cy = Math.min(Math.max(r.top + r.height / 2, 1), window.innerHeight - 2);
          const hit = document.elementFromPoint(cx, cy);
          const corner = document.querySelector('[data-testid="gg-corner-button"]');
          const hitsCorner = !!(corner && hit && (hit === corner || corner.contains(hit)));
          const hitsControl = !!(
            r.bottom > 0 && r.top < window.innerHeight && hit
            && (hit === last || last.contains(hit) || hit.contains(last))
          );
          return {
            ok: !hitsCorner && hitsControl,
            hitsCorner,
            hitsControl,
            tag: last.tagName,
            testid: last.getAttribute('data-testid'),
            lastRect: r.toJSON(),
            hitTag: hit ? hit.tagName : null,
            hitTestid: hit ? hit.getAttribute('data-testid') : null,
            cornerRect: corner ? corner.getBoundingClientRect().toJSON() : null,
            scrollTop: scroller.scrollTop,
            scrollHeight: scroller.scrollHeight,
            clientHeight: scroller.clientHeight,
          };
        }"""
    )
    assert result["ok"], f"{route_hint}: last control obscured at bottom scroll: {result}"


def _active_in(page: Page, selector: str) -> bool:
    return bool(
        page.evaluate(
            """(sel) => {
              const root = document.querySelector(sel);
              const act = document.activeElement;
              return !!(root && act && (act === root || root.contains(act)));
            }""",
            selector,
        )
    )


def _active_testid(page: Page) -> str | None:
    return page.evaluate(
        "() => document.activeElement ? document.activeElement.getAttribute('data-testid') : null"
    )


def _seed_workspace(base_url: str, data_dir) -> dict[str, str]:
    pid = seed_mock_provider(base_url, name="NarrowMock")
    agent = seed_mock_agent(base_url, pid, name="NarrowAgent", system_prompt="Be concise.")
    kb_id = seed_knowledge_base(base_url, name="NarrowKB", description="Sample base")
    mcp_id = seed_mcp_source(base_url, name="NarrowMCP", tools=["search", "fetch"])
    conn_id = seed_connector(base_url, name="NarrowConn", default_agent=agent)
    sec_id = seed_secret(base_url, name="NarrowSecret", description="Sample secret")
    enable_notes(base_url, agent, True)
    seed_note(data_dir, agent, "Keep responses short.")
    msgs = [
        Message.user("First question line one.\nFirst question line two."),
        Message.assistant(
            "Reply line one for viewport height check.\n"
            "Reply line two ensures wrapped text.\n"
            "Reply line three verifies three visible lines.\n"
            "Reply line four sits above the composer."
        ),
    ]
    sid = seed_session(
        base_url,
        agent,
        "Narrow chat",
        "2026-01-02T00:00:00Z",
        messages=encode_messages(msgs),
    )
    return {
        "pid": pid,
        "agent": agent,
        "kb_id": kb_id,
        "mcp_id": mcp_id,
        "conn_id": conn_id,
        "sec_id": sec_id,
        "sid": sid,
    }


def test_all_destinations_fit_narrow_wide_and_below_624(
    app_with_data_dir: tuple[str, object], browser: Browser
) -> None:
    base, data_dir = app_with_data_dir
    ids = _seed_workspace(base, data_dir)
    ctx, page = _new_narrow_page(browser, base, viewport=NARROW)
    try:
        with _error_watch(page) as errors:
            # Chats: open session (auto-joined), welcome & pending checked in separate flow below.
            _nav.goto_settled(page, base, f"chats/{ids['sid']}")
            _chats.expect_chat(page, ids["agent"], title="Narrow chat")
            _assert_shell_bounds(page, min_main_width=360, expect_narrow=True)

            # Pending chat at 624x321.
            _nav.goto_settled(page, base, f"chats/~new/{_nav.seg(ids['agent'])}")
            _chats.expect_chat(page, ids["agent"], title="New chat")
            _assert_shell_bounds(page, min_main_width=360, expect_narrow=True)

            # Agents root + all 6 tabs.
            _nav.goto_settled(page, base, "agents")
            expect(_lists.agents_empty_state(page)).to_be_visible()
            _assert_shell_bounds(page, min_main_width=360, expect_narrow=True)

            for tab in (
                "general",
                "rules-and-notes",
                "knowledge",
                "tools",
                "routines",
                "self-configuration",
            ):
                _nav.goto_settled(page, base, f"agents/{_nav.seg(ids['agent'])}/{tab}")
                tab_btn = page.locator(f"#agent-tab-{tab}")
                expect(tab_btn).to_be_visible()
                expect(tab_btn).to_have_attribute("aria-selected", "true")
                _assert_shell_bounds(page, min_main_width=360, expect_narrow=True)

            # Library root + all 5 entity editors.
            _nav.goto_settled(page, base, "library")
            expect(_lists.library_start(page)).to_be_visible()
            _assert_shell_bounds(page, min_main_width=360, expect_narrow=True)

            for lib_route in (
                f"library/providers/{ids['pid']}",
                f"library/knowledge/{ids['kb_id']}",
                f"library/mcp/{ids['mcp_id']}",
                f"library/connectors/{ids['conn_id']}",
                f"library/secrets/{ids['sec_id']}",
            ):
                _nav.goto_settled(page, base, lib_route)
                expect(page.locator(".editor-header:visible")).to_be_visible()
                _assert_shell_bounds(page, min_main_width=360, expect_narrow=True)

            # Settings: all 7 pages + Built-in tool editor.
            for section in _lists.SETTINGS_PAGES:
                _nav.goto_settled(page, base, f"settings/{section}")
                expect(_lists.settings_page_title(page)).to_have_text(
                    _lists.SETTINGS_PAGE_TITLES[section]
                )
                _assert_shell_bounds(page, min_main_width=360, expect_narrow=True)

            _nav.goto_settled(page, base, "settings/tools/fetch_url")
            expect(_lists.settings_item(page)).to_be_visible()
            _assert_shell_bounds(page, min_main_width=360, expect_narrow=True)

            # Wide baseline (1280x800): desktop layout preserved.
            page.set_viewport_size(WIDE)
            _nav.goto_settled(page, base, f"agents/{_nav.seg(ids['agent'])}/general")
            _assert_shell_bounds(page, min_main_width=360, expect_narrow=False)

            # Plain browser below 624px (480x321): scroll-free and crash-free, 56px rail.
            page.set_viewport_size(TINY)
            for small_route in (
                f"chats/{ids['sid']}",
                f"agents/{_nav.seg(ids['agent'])}/tools",
                "settings/tools",
            ):
                _nav.goto_settled(page, base, small_route)
                _assert_shell_bounds(page, min_main_width=360, expect_narrow=True)
                rail_w = page.evaluate(
                    "() => document.getElementById('app-rail').getBoundingClientRect().width"
                )
                assert rail_w <= 56.5, f"expected compact <=56px rail at 480px width, got {rail_w}"

            assert errors == []
    finally:
        ctx.close()


def test_chats_welcome_and_open_chat_three_lines_at_624x321(
    app_with_data_dir: tuple[str, object], browser: Browser
) -> None:
    base, data_dir = app_with_data_dir
    pid = seed_mock_provider(base, name="WelcomeMock")
    agent = seed_mock_agent(base, pid, name="WelcomeAgent")

    # Welcome screen (no sessions yet) fits 624x321 cleanly.
    ctx_w, page_w = _new_narrow_page(browser, base, viewport=NARROW)
    try:
        with _error_watch(page_w) as errors_w:
            _nav.goto_settled(page_w, base, "chats")
            expect(_chats.welcome(page_w)).to_be_visible()
            _assert_shell_bounds(page_w, min_main_width=360, expect_narrow=True)
            assert errors_w == []
    finally:
        ctx_w.close()

    # Open chat displays >= 3 visible transcript lines above .ui-composer at 624x321.
    msgs = [
        Message.user("Prompt line one.\nPrompt line two."),
        Message.assistant(
            "Line 1 of transcript above composer.\n"
            "Line 2 of transcript above composer.\n"
            "Line 3 of transcript above composer.\n"
            "Line 4 of transcript above composer.\n"
            "Line 5 of transcript above composer."
        ),
    ]
    sid = seed_session(
        base, agent, "Three lines check", "2026-01-03T00:00:00Z", messages=encode_messages(msgs)
    )
    ctx_c, page_c = _new_narrow_page(browser, base, viewport=NARROW)
    try:
        with _error_watch(page_c) as errors_c:
            _nav.goto_settled(page_c, base, f"chats/{sid}")
            _chats.expect_chat(page_c, agent, title="Three lines check")
            page_c.wait_for_function(
                "() => document.querySelectorAll"
                "('.chat-instance [data-testid=\"message\"]').length >= 2"
            )
            lines = _count_visible_transcript_lines(page_c)
            assert lines >= 3, f"expected >= 3 visible transcript lines at 624x321, saw {lines}"
            assert errors_c == []
    finally:
        ctx_c.close()


def test_last_control_clears_corner_button_at_624x321_and_1280x800(
    app_with_data_dir: tuple[str, object], browser: Browser
) -> None:
    base, data_dir = app_with_data_dir
    ids = _seed_workspace(base, data_dir)
    routes = (
        f"agents/{_nav.seg(ids['agent'])}/general",
        f"agents/{_nav.seg(ids['agent'])}/tools",
        f"agents/{_nav.seg(ids['agent'])}/self-configuration",
        f"library/providers/{ids['pid']}",
        f"library/knowledge/{ids['kb_id']}",
        "settings/tools",
        "settings/tools/fetch_url",
        "settings/knowledge-indexing",
    )
    ctx, page = _new_narrow_page(browser, base, viewport=NARROW)
    try:
        with _error_watch(page) as errors:
            for vp_name, vp in (("624x321", NARROW), ("1280x800", WIDE)):
                page.set_viewport_size(vp)
                for route in routes:
                    _nav.goto_settled(page, base, route)
                    _assert_last_control_not_covered(page, route_hint=f"{vp_name}:{route}")
            assert errors == []
    finally:
        ctx.close()


def test_sidebar_overlay_lifecycle_focus_and_live_resize(
    app_with_agent: SeededApp, browser: Browser
) -> None:
    base = app_with_agent.base_url
    ctx, page = _new_narrow_page(browser, base, viewport=NARROW)
    try:
        with _error_watch(page) as errors:
            _nav.goto_settled(page, base, "settings/tools")
            sidebar = page.locator("#app-sidebar")
            toggle = page.locator(SIDEBAR_TOGGLE)
            expect(toggle).to_be_visible()
            expect(toggle).to_have_attribute("aria-expanded", "false")
            expect(sidebar).to_be_hidden()

            # Open via rail toggle -> focus enters sidebar.
            toggle.click()
            expect(sidebar).to_be_visible()
            expect(sidebar).to_have_attribute("data-narrow-open", "true")
            expect(toggle).to_have_attribute("aria-expanded", "true")
            page.wait_for_function(
                "() => document.getElementById('app-sidebar').contains(document.activeElement)"
            )

            # Escape closes sidebar and returns focus to rail-sidebar-toggle.
            page.keyboard.press("Escape")
            expect(sidebar).to_be_hidden()
            expect(toggle).to_have_attribute("aria-expanded", "false")
            page.wait_for_function(
                "() => document.activeElement?.getAttribute('data-testid')"
                " === 'rail-sidebar-toggle'"
            )

            # Close button dismisses sidebar and returns focus to rail-sidebar-toggle.
            toggle.click()
            expect(sidebar).to_be_visible()
            page.locator(SIDEBAR_CLOSE).click()
            expect(sidebar).to_be_hidden()
            page.wait_for_function(
                "() => document.activeElement?.getAttribute('data-testid')"
                " === 'rail-sidebar-toggle'"
            )

            # Clicking #main-content outside sidebar dismisses overlay.
            toggle.click()
            expect(sidebar).to_be_visible()
            page.locator(".area-admin .page-title").click()
            expect(sidebar).to_be_hidden()

            # Navigating via sidebar link auto-closes sidebar on route commit.
            toggle.click()
            expect(sidebar).to_be_visible()
            _lists.open_settings_page(page, "appearance")
            expect(sidebar).to_be_hidden()

            # Live resize 624x321 -> 1280x800 docks sidebar & hides toggle; back undocks cleanly.
            toggle.click()
            expect(sidebar).to_be_visible()
            page.set_viewport_size(WIDE)
            expect(page.locator(".app-shell-row")).not_to_have_attribute("data-narrow", "true")
            _assert_shell_bounds(page, min_main_width=360, expect_narrow=False)
            expect(sidebar).not_to_have_attribute("data-narrow-open", "true")

            page.set_viewport_size(NARROW)
            expect(page.locator(".app-shell-row")).to_have_attribute("data-narrow", "true")
            _assert_shell_bounds(page, min_main_width=360, expect_narrow=True)
            assert errors == []
    finally:
        ctx.close()


def test_single_overlay_exclusivity_and_focus_handoff(
    app_with_data_dir: tuple[str, object], browser: Browser
) -> None:
    base, data_dir = app_with_data_dir
    ids = _seed_workspace(base, data_dir)
    ctx, page = _new_narrow_page(browser, base, viewport=NARROW)
    try:
        with _error_watch(page) as errors:
            # 1) Chats: #app-sidebar <-> #chat-drawer.
            _nav.goto_settled(page, base, f"chats/{ids['sid']}")
            sidebar = page.locator("#app-sidebar")
            chat_drawer = page.locator(CHAT_DRAWER)
            sidebar_toggle = page.locator(SIDEBAR_TOGGLE)
            chat_toggle = page.locator(CHAT_DRAWER_TOGGLE)

            expect(sidebar).to_be_hidden()
            expect(chat_drawer).to_be_hidden()

            sidebar_toggle.click()
            expect(sidebar).to_be_visible()
            assert _active_in(page, "#app-sidebar")

            # Opening #chat-drawer closes #app-sidebar and moves focus into #chat-drawer.
            chat_toggle.click()
            expect(chat_drawer).to_be_visible()
            expect(sidebar).to_be_hidden()
            assert _active_in(page, CHAT_DRAWER)

            # Escape closes #chat-drawer and returns focus to chat-drawer-toggle.
            page.keyboard.press("Escape")
            expect(chat_drawer).to_be_hidden()
            assert _active_testid(page) == "chat-drawer-toggle"

            # Reopen #chat-drawer, then opening #app-sidebar closes #chat-drawer.
            chat_toggle.click()
            expect(chat_drawer).to_be_visible()
            sidebar_toggle.click()
            expect(sidebar).to_be_visible()
            expect(chat_drawer).to_be_hidden()
            assert _active_in(page, "#app-sidebar")

            # 2) Agents: #app-sidebar <-> #gleepglorp-drawer.
            _nav.goto_settled(page, base, f"agents/{_nav.seg(ids['agent'])}/general")
            gg_drawer = page.locator(_drawer.DRAWER)
            gg_btn = page.locator(_drawer.BTN)
            expect(gg_drawer).to_be_hidden()
            expect(gg_btn).to_be_visible()

            sidebar_toggle.click()
            expect(sidebar).to_be_visible()
            assert _active_in(page, "#app-sidebar")

            # Opening #gleepglorp-drawer closes #app-sidebar and moves focus into drawer.
            gg_btn.click()
            expect(gg_drawer).to_be_visible()
            expect(sidebar).to_be_hidden()
            assert _active_in(page, _drawer.DRAWER)

            # Escape closes #gleepglorp-drawer and returns focus to gg-corner-button.
            page.keyboard.press("Escape")
            expect(gg_drawer).to_be_hidden()
            assert _active_testid(page) == "gg-corner-button"

            # Reopen #gleepglorp-drawer, then opening #app-sidebar closes it.
            gg_btn.click()
            expect(gg_drawer).to_be_visible()
            sidebar_toggle.click()
            expect(sidebar).to_be_visible()
            expect(gg_drawer).to_be_hidden()
            assert _active_in(page, "#app-sidebar")

            assert errors == []
    finally:
        ctx.close()


def test_modals_fit_inside_624x321(app_with_agent: SeededApp, browser: Browser) -> None:
    base = app_with_agent.base_url
    ctx, page = _new_narrow_page(browser, base, viewport=NARROW)
    try:
        with _error_watch(page) as errors:
            _nav.goto_settled(page, base, "chats")

            # Jump-to palette fits inside 624x321.
            page.locator('[data-testid="rail-jump-to"]').click()
            jump_dlg = page.locator('[data-testid="jump-to"]')
            expect(jump_dlg).to_be_visible()
            jump_box = jump_dlg.evaluate(
                "el => el.querySelector('.modal-dialog')?.getBoundingClientRect().toJSON()"
            )
            assert jump_box
            assert jump_box["left"] >= 0 and jump_box["right"] <= 624.5
            assert jump_box["top"] >= 0 and jump_box["bottom"] <= 321.5
            page.keyboard.press("Escape")
            expect(jump_dlg).to_be_hidden()
            assert _active_testid(page) == "rail-jump-to"

            # Agent picker modal fits inside 624x321.
            _chats.empty_new_button(page).click()
            picker = _chats.picker(page)
            expect(picker).to_be_visible()
            pick_box = picker.evaluate(
                "el => el.querySelector('.modal-dialog')?.getBoundingClientRect().toJSON()"
            )
            assert pick_box
            assert pick_box["left"] >= 0 and pick_box["right"] <= 624.5
            assert pick_box["top"] >= 0 and pick_box["bottom"] <= 321.5
            page.keyboard.press("Escape")
            expect(picker).to_be_hidden()

            assert errors == []
    finally:
        ctx.close()


def test_narrow_layout_and_overlays_multi_engine(
    app_with_agent: SeededApp, engine_browser: Browser
) -> None:
    """Chromium and WebKit both enforce narrow shell bounds, overlay exclusivity, and clearance."""
    base = app_with_agent.base_url
    ctx, page = _new_narrow_page(engine_browser, base, viewport=NARROW)
    try:
        with _error_watch(page) as errors:
            _nav.goto_settled(page, base, f"agents/{_nav.seg(app_with_agent.agent_name)}/tools")
            _assert_shell_bounds(page, min_main_width=360, expect_narrow=True)
            _assert_last_control_not_covered(page, route_hint="multi_engine:agent_tools")

            sidebar = page.locator("#app-sidebar")
            toggle = page.locator(SIDEBAR_TOGGLE)
            gg_drawer = page.locator(_drawer.DRAWER)
            gg_btn = page.locator(_drawer.BTN)

            toggle.click()
            expect(sidebar).to_be_visible()
            assert _active_in(page, "#app-sidebar")

            page.keyboard.press("Escape")
            expect(sidebar).to_be_hidden()
            assert _active_testid(page) == "rail-sidebar-toggle"

            toggle.click()
            expect(sidebar).to_be_visible()
            gg_btn.click()
            expect(gg_drawer).to_be_visible()
            expect(sidebar).to_be_hidden()
            assert _active_in(page, _drawer.DRAWER)

            assert errors == []
    finally:
        ctx.close()
