"""Living-reference guard for the dev-mode Design language page (M25 F1 L6, DD10).

Every ``App.ui`` factory has a ``[data-ui-demo]`` root with a dark and a light pane;
panes paint their own theme background; the shared resolver passes over every demo
root; the menu demo opens and closes by keyboard in the real page. Chromium only: the
WebKit pass over the same page is the probe in ``scripts/webkitgtk_probe.py``.
Falls in the ``contracts`` browser lane (``app_clean`` spawns with dev mode on).
"""

from __future__ import annotations

import re

import pytest
from browser import _nav
from browser._a11y_resolvers import assert_controls_labelled_and_described
from browser.design_tokens import DARK, LIGHT
from playwright.sync_api import Page, expect

from tests._ui_guard_helpers import UI_DIR

pytestmark = pytest.mark.browser

FACTORY = re.compile(r"^\s*App\.ui\.(?!util\b)(\w+)\s*=\s*function\b", re.MULTILINE)


def _factories() -> list[str]:
    names: set[str] = set()
    for path in UI_DIR.glob("*.js"):
        names.update(FACTORY.findall(path.read_text()))
    return sorted(names)


def _hex_to_rgb(value: str) -> str:
    h = value.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgb({r}, {g}, {b})"


@pytest.fixture
def reference_page(app_clean: str, page: Page) -> Page:
    _nav.goto(page, app_clean, "settings/design-language")
    page.wait_for_selector("[data-ui-demo]")
    return page


def test_every_factory_has_exactly_one_demo_root(reference_page: Page) -> None:
    roots = reference_page.eval_on_selector_all(
        "[data-ui-demo]", "els => els.map(e => e.getAttribute('data-ui-demo'))"
    )
    assert sorted(roots) == _factories()


def test_each_root_has_both_panes_with_theme_background(reference_page: Page) -> None:
    result = reference_page.evaluate(
        """() => Array.from(document.querySelectorAll('[data-ui-demo]')).map(root => {
          const panes = {};
          root.querySelectorAll(':scope > [data-theme]').forEach(p => {
            panes[p.getAttribute('data-theme')] = getComputedStyle(p).backgroundColor;
          });
          return [root.getAttribute('data-ui-demo'), panes];
        })"""
    )
    assert result
    for name, panes in result:
        assert set(panes) == {"dark", "light"}, name
        assert panes["dark"] == _hex_to_rgb(DARK["bg"]), name
        assert panes["light"] == _hex_to_rgb(LIGHT["bg"]), name


def test_resolver_passes_over_every_demo_root(reference_page: Page) -> None:
    assert_controls_labelled_and_described(reference_page, "[data-ui-demo]")


def test_menu_demo_opens_and_closes_by_keyboard(reference_page: Page) -> None:
    trigger = reference_page.locator(
        '[data-ui-demo="menu"] [data-theme="dark"] button[aria-haspopup="menu"]'
    ).first
    trigger.scroll_into_view_if_needed()
    trigger.focus()
    expect(trigger).to_have_attribute("aria-expanded", "false")
    reference_page.keyboard.press("Enter")
    expect(trigger).to_have_attribute("aria-expanded", "true")
    expect(reference_page.locator('[role="menu"]:not([hidden])')).to_have_count(1)
    reference_page.keyboard.press("Escape")
    expect(trigger).to_have_attribute("aria-expanded", "false")
    expect(trigger).to_be_focused()


def test_list_and_nav_demos_render_in_both_themes_without_console_errors(
    app_clean: str, page: Page
) -> None:
    """M25 F3 L1 (AC5): the Agents-style and Library-style list panes and the
    navGroups demo render in the dark and the light pane, with no console error
    or uncaught exception while the page loads."""
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    _nav.goto(page, app_clean, "settings/design-language")
    page.wait_for_selector('[data-ui-demo="navGroups"]')
    out = page.evaluate(
        """() => ['dark', 'light'].map((theme) => {
          const pane = (f) =>
            document.querySelector(`[data-ui-demo="${f}"] > [data-theme="${theme}"]`);
          const lists = Array.from(pane('listPane').querySelectorAll('.ui-list-pane'));
          const agents = lists.find((l) => l.classList.contains('ui-list-pane-style-agents'));
          const library = lists.find((l) => l.classList.contains('ui-list-pane-style-library'));
          const body = agents.querySelector('.ui-list-pane-body');
          const nav = pane('navGroups').querySelector('nav');
          return {
            theme,
            agentRows: agents.querySelectorAll('.ui-list-pane-row').length,
            count: agents.querySelector('.ui-list-pane-total').textContent,
            scrolls: body.scrollHeight > body.clientHeight,
            intro: !!library.querySelector('.ui-list-pane-intro'),
            emptyLines: library.querySelectorAll('.ui-list-pane-group-empty').length,
            nav: nav.getAttribute('aria-label'),
            navGroups: nav.querySelectorAll('.ui-nav-groups-caption').length,
            current: nav.querySelectorAll('[aria-current="page"]').length,
          };
        })"""
    )
    for pane in out:
        assert (
            pane["agentRows"] >= 30
            and pane["count"] == f"{pane['agentRows']} of {pane['agentRows']}"
        )
        assert pane["scrolls"] is True, pane  # the 300px column's body is the scroller
        assert pane["intro"] is True and pane["emptyLines"] == 1, pane
        assert pane["nav"] == f"Settings demo ({pane['theme']})", pane
        assert pane["navGroups"] == 4 and pane["current"] == 1, pane
    # M25 F3 L4a: the Library-style demo's button calls scrollToGroup: the
    # Connectors group comes into view, and only the pane's body scrolls.
    for theme in ("dark", "light"):
        demo = page.locator(f'[data-ui-demo="listPane"] > [data-theme="{theme}"]')
        demo.get_by_role("button", name="Scroll to Connectors").click()
        scrolled = demo.evaluate(
            """(pane) => {
              const lib = pane.querySelector('.ui-list-pane-style-library');
              const body = lib.querySelector('.ui-list-pane-body');
              const cap = Array.from(lib.querySelectorAll('.ui-list-pane-caption'))
                .find((n) => n.textContent === 'Connectors');
              const b = body.getBoundingClientRect(), g = cap.parentElement.getBoundingClientRect();
              return {scrollTop: body.scrollTop, inView: g.top >= b.top - 0.5 && g.top < b.bottom};
            }"""
        )
        assert scrolled["scrollTop"] > 0 and scrolled["inView"], (theme, scrolled)
    assert errors == []
