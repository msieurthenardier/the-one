# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.infoButton`` and the form-control
extensions of M31 F1 L4: the ``info`` option on ``field``, ``toggle`` and ``checkbox``,
``dataset`` passthrough, ``name`` on the choice controls and ``setDisabled``.

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

DESC = "A larger window allows longer chats"


def _mount(page: Page, js: str):
    load_harness(page)
    return page.evaluate(js)


def test_info_button_dom_and_name(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const i = App.ui.infoButton({description: 'A larger window allows longer chats', label: 'Context Window', testid: 'info-1'});
          document.getElementById('harness-root').appendChild(i.el);
          const d = document.getElementById(i.descriptionId);
          return {wrap: i.el.tagName + '.' + i.el.className, btn: i.button.className, type: i.button.type,
                  title: i.button.getAttribute('title') === null ? '' : 'has-title', aria: i.button.getAttribute('aria-label'),
                  tid: i.button.getAttribute('data-testid'), desc: d.textContent, descCls: d.className,
                  svg: i.button.querySelectorAll('svg.ui-icon.ui-icon--sm').length, parent: d.parentNode === i.el};
        }""",
    )
    assert out == {
        "wrap": "SPAN.ui-info", "btn": "field-info-icon", "type": "button", "title": "",
        "aria": "More information about Context Window", "tid": "info-1", "desc": DESC, "descCls": "visually-hidden", "svg": 1,
        "parent": True,
    }  # fmt: skip
    expect(
        engine_page.get_by_role("button", name="More information about Context Window")
    ).to_have_count(1)


def test_info_button_requires_description_and_tab_reaches_it(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    msg = page.evaluate(
        "() => { try { App.ui.infoButton({}); return ''; } catch (e) { return e.message; } }"
    )
    assert "description is required" in msg
    page.evaluate(
        """() => {
          const root = document.getElementById('harness-root');
          const b = document.createElement('button'); b.textContent = 'before'; b.id = 'before';
          root.appendChild(b);
          root.appendChild(App.ui.infoButton({description: 'Help text'}).el);
        }"""
    )
    page.locator("#before").focus()
    page.keyboard.press("Tab")
    assert (
        page.evaluate("() => document.activeElement.getAttribute('aria-label')")
        == "More information"
    )


def test_field_info_layout_and_describedby(engine_page: Page) -> None:
    page = engine_page
    out = _mount(
        page,
        """() => {
          const c = App.ui.textInput({testid: 'num'});
          const f = App.ui.field({label: 'Context Window', control: c, info: 'A larger window allows longer chats', hint: 'Tokens'});
          document.getElementById('harness-root').appendChild(f.el);
          const head = f.el.firstElementChild;
          const label = head.querySelector('label');
          const info = head.querySelector('button.field-info-icon');
          return {head: head.className, kids: Array.from(head.children).map((k) => k.tagName),
                  nested: label.contains(info), forId: label.htmlFor === c.id,
                  ids: c.getAttribute('aria-describedby').split(' ').length,
                  firstDesc: document.getElementById(c.getAttribute('aria-describedby').split(' ')[0]).textContent};
        }""",
    )
    assert out == {
        "head": "field-group-label", "kids": ["LABEL", "SPAN"], "nested": False, "forId": True,
        "ids": 2, "firstDesc": DESC,
    }  # fmt: skip
    expect(page.get_by_label("Context Window", exact=True)).to_have_count(1)
    expect(page.get_by_role("textbox", name="Context Window")).to_have_accessible_description(
        "A larger window allows longer chats Tokens"
    )


def test_field_info_with_hidden_label_keeps_button_visible(engine_page: Page) -> None:
    page = engine_page
    _mount(
        page,
        """() => {
          const f = App.ui.field({label: 'Secret', labelHidden: true, control: App.ui.textInput(), info: 'Why'});
          document.getElementById('harness-root').appendChild(f.el);
        }""",
    )
    expect(page.get_by_role("button", name="More information about Secret")).to_be_visible()
    expect(page.locator(".field-group-label > label")).to_have_class("visually-hidden")


def test_toggle_and_checkbox_info(engine_page: Page) -> None:
    page = engine_page
    out = _mount(
        page,
        """() => {
          const t = App.ui.toggle({label: 'Extended thinking', info: 'Reasons step by step', hint: 'Needs Sonnet'});
          const c = App.ui.checkbox({label: 'Agree', info: 'Why agree', name: 'agree', dataset: {field: 'x.y', testid: 'ignored'}, testid: 'cb'});
          const root = document.getElementById('harness-root');
          root.appendChild(t.el); root.appendChild(c.el);
          const ids = t.control.getAttribute('aria-describedby').split(' ');
          const label = t.el.querySelector('label');
          return {ids: ids.length, first: document.getElementById(ids[0]).textContent,
                  second: document.getElementById(ids[1]).textContent,
                  nested: !!label.querySelector('button'),
                  order: Array.from(t.el.querySelector('.ui-choice-head').children).map((k) => k.tagName),
                  name: c.control.name, field: c.control.dataset.field, tid: c.control.getAttribute('data-testid'),
                  cbDesc: c.control.getAttribute('aria-describedby') === c.el.querySelector('.ui-info > span').id};
        }""",
    )
    assert out == {
        "ids": 2, "first": "Reasons step by step", "second": "Needs Sonnet", "nested": False,
        "order": ["LABEL", "SPAN"], "name": "agree", "field": "x.y", "tid": "cb", "cbDesc": True,
    }  # fmt: skip
    sw = page.get_by_role("switch", name="Extended thinking")
    expect(sw).to_have_accessible_description("Reasons step by step Needs Sonnet")
    sw.focus()
    page.keyboard.press("Tab")
    assert (
        page.evaluate("() => document.activeElement.getAttribute('aria-label')")
        == "More information about Extended thinking"
    )


def test_dataset_passthrough_on_every_native_control(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const d = {field: 'config.num_ctx', testid: 'nope'};
          const nodes = [
            App.ui.textInput({dataset: d, testid: 'a'}),
            App.ui.textarea({dataset: d, testid: 'b'}),
            App.ui.select({dataset: d, options: [{value: '1', label: 'One'}], testid: 'c'}),
            App.ui.checkbox({label: 'x', dataset: d, testid: 'd'}).control,
            App.ui.toggle({label: 'y', dataset: d, testid: 'e'}).control,
            App.ui.textInput({dataset: d})
          ];
          return nodes.map((n) => [n.dataset.field, n.getAttribute('data-testid')]);
        }""",
    )
    assert out == [
        ["config.num_ctx", "a"], ["config.num_ctx", "b"], ["config.num_ctx", "c"],
        ["config.num_ctx", "d"], ["config.num_ctx", "e"], ["config.num_ctx", None],
    ]  # fmt: skip


def test_choice_name_and_set_disabled(engine_page: Page) -> None:
    out = _mount(
        engine_page,
        """() => {
          const t = App.ui.toggle({label: 'T', name: 'tg'});
          const c = App.ui.checkbox({label: 'C'});
          const root = document.getElementById('harness-root');
          root.appendChild(t.el); root.appendChild(c.el);
          const before = [t.el.classList.contains('is-disabled'), c.el.classList.contains('is-disabled')];
          t.setDisabled(true); c.setDisabled(true);
          const during = [t.control.disabled, c.control.disabled, t.el.classList.contains('is-disabled'), c.el.classList.contains('is-disabled')];
          t.setDisabled(false); c.setDisabled(false);
          return {name: t.control.name, before, during,
                  after: [t.control.disabled, c.control.disabled, t.el.classList.contains('is-disabled'), c.el.classList.contains('is-disabled')]};
        }""",
    )
    assert out == {
        "name": "tg", "before": [False, False], "during": [True, True, True, True],
        "after": [False, False, False, False],
    }  # fmt: skip


# ── M31 F2 L5 (squawk 0221): the press-only toggletip ─────────────────────

MOUNT_TIP = """() => {
  const root = document.getElementById('harness-root');
  const a = App.ui.infoButton({description: 'A larger window allows longer chats', label: 'Context Window', testid: 'tip-a'});
  const b = App.ui.infoButton({description: 'Second description', label: 'Other', testid: 'tip-b'});
  const out = document.createElement('button'); out.id = 'outside'; out.textContent = 'outside';
  root.appendChild(a.el); root.appendChild(b.el); root.appendChild(out);
  window.__a = a; window.__b = b;
}"""


def _bubble(page: Page, testid: str):
    return page.locator(
        f"#{page.locator(f'[data-testid={testid}]').get_attribute('aria-controls')}"
    )


def test_toggletip_press_opens_announces_and_has_role_structure(engine_page: Page) -> None:
    page = engine_page
    _mount(page, MOUNT_TIP)
    btn = page.locator("[data-testid=tip-a]")
    assert btn.get_attribute("title") is None
    expect(btn).to_have_attribute("aria-expanded", "false")
    bubble = _bubble(page, "tip-a")
    expect(bubble).to_be_hidden()
    assert bubble.get_attribute("class") == "ui-info-bubble"
    btn.click()
    expect(btn).to_have_attribute("aria-expanded", "true")
    expect(bubble).to_be_visible()
    # Announced once: the bubble's own live region carries the text.
    live = bubble.locator("[role=status][aria-live=polite]")
    expect(live).to_have_text(DESC)
    # The button controls the bubble, the bubble sits inside span.ui-info.
    assert page.evaluate(
        "() => window.__a.el.contains(document.getElementById(window.__a.button.getAttribute('aria-controls')))"
    )
    # The hidden description is still there for aria-describedby.
    assert (
        page.evaluate("() => document.getElementById(window.__a.descriptionId).textContent") == DESC
    )
    # Anchored below the button without shifting layout.
    box = btn.bounding_box()
    bbox = bubble.bounding_box()
    assert bbox["y"] >= box["y"] + box["height"] - 1
    assert bbox["width"] <= 281


def test_toggletip_keyboard_toggle_and_escape_keep_focus(engine_page: Page) -> None:
    page = engine_page
    _mount(page, MOUNT_TIP)
    btn = page.locator("[data-testid=tip-a]")
    bubble = _bubble(page, "tip-a")
    btn.focus()
    page.keyboard.press("Enter")
    expect(bubble).to_be_visible()
    page.keyboard.press("Escape")
    expect(bubble).to_be_hidden()
    expect(btn).to_have_attribute("aria-expanded", "false")
    assert page.evaluate("() => document.activeElement === window.__a.button")
    page.keyboard.press("Space")
    expect(bubble).to_be_visible()
    page.keyboard.press("Space")
    expect(bubble).to_be_hidden()
    assert page.evaluate("() => document.activeElement === window.__a.button")


def test_toggletip_outside_press_closes_and_no_listener_remains(engine_page: Page) -> None:
    page = engine_page
    _mount(page, MOUNT_TIP)
    page.evaluate(
        """() => {
          window.__adds = []; window.__removes = [];
          const add = document.addEventListener.bind(document);
          const rem = document.removeEventListener.bind(document);
          document.addEventListener = (t, h, c) => { window.__adds.push(t); return add(t, h, c); };
          document.removeEventListener = (t, h, c) => { window.__removes.push(t); return rem(t, h, c); };
        }"""
    )
    btn = page.locator("[data-testid=tip-a]")
    bubble = _bubble(page, "tip-a")
    btn.click()
    expect(bubble).to_be_visible()
    page.locator("#outside").click()
    expect(bubble).to_be_hidden()
    assert page.evaluate("() => window.__adds.slice().sort().join()") == "keydown,pointerdown"
    assert page.evaluate("() => window.__removes.slice().sort().join()") == "keydown,pointerdown"
    # After close an outside press and Escape do nothing (and re-add nothing).
    page.locator("#outside").click()
    page.keyboard.press("Escape")
    assert page.evaluate("() => window.__adds.length") == 2
    # Press the button again to close, then destroy while open removes the listeners.
    btn.click()
    btn.click()
    expect(bubble).to_be_hidden()
    btn.click()
    page.evaluate("() => window.__a.destroy()")
    expect(bubble).to_be_hidden()
    assert page.evaluate("() => window.__adds.length") == page.evaluate(
        "() => window.__removes.length"
    )


def test_toggletip_only_one_open_at_a_time(engine_page: Page) -> None:
    page = engine_page
    _mount(page, MOUNT_TIP)
    page.locator("[data-testid=tip-a]").click()
    expect(_bubble(page, "tip-a")).to_be_visible()
    page.locator("[data-testid=tip-b]").click()
    expect(_bubble(page, "tip-b")).to_be_visible()
    expect(_bubble(page, "tip-a")).to_be_hidden()
    expect(page.locator("[data-testid=tip-a]")).to_have_attribute("aria-expanded", "false")


def test_toggletip_tab_order_is_unchanged(engine_page: Page) -> None:
    page = engine_page
    _mount(page, MOUNT_TIP)
    page.locator("[data-testid=tip-a]").click()
    # Open or closed, Tab goes from the button straight to the next button.
    page.locator("[data-testid=tip-a]").focus()
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement === window.__b.button")
    # Focus left the first wrapper: its bubble closed.
    expect(_bubble(page, "tip-a")).to_be_hidden()
    page.keyboard.press("Shift+Tab")
    assert page.evaluate("() => document.activeElement === window.__a.button")
    assert (
        page.evaluate(
            "() => document.querySelectorAll('.ui-info-bubble button, .ui-info-bubble a, .ui-info-bubble [tabindex]').length"
        )
        == 0
    )


def test_toggletip_in_a_modal_escape_closes_only_the_bubble(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          window.__closed = [];
          const i = App.ui.infoButton({description: 'Modal help', label: 'Thing', testid: 'tip-m'});
          const opener = document.createElement('button'); opener.textContent = 'o';
          document.getElementById('harness-root').appendChild(opener);
          const m = App.ui.modal({title: 'Sample', body: i.el, testid: 'm-dialog', cancelValue: 'cancelled',
            actions: [{label: 'Go', variant: 'primary', value: 'go', testid: 'm-go'}],
            onClose: (v) => window.__closed.push(v)});
          m.open(opener);
        }"""
    )
    btn = page.locator("[data-testid=tip-m]")
    btn.click()
    bubble = _bubble(page, "tip-m")
    expect(bubble).to_be_visible()
    page.keyboard.press("Escape")
    expect(bubble).to_be_hidden()
    expect(page.locator("[data-testid=m-dialog]")).to_be_visible()
    assert page.evaluate("() => window.__closed.length") == 0
    page.keyboard.press("Escape")
    expect(page.locator("[data-testid=m-dialog]")).to_have_count(0)
    assert page.evaluate("() => window.__closed") == ["cancelled"]


def test_toggletip_inside_summary_does_not_toggle_details(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          const root = document.getElementById('harness-root');
          const d = document.createElement('details'); d.id = 'dt';
          const s = document.createElement('summary'); s.appendChild(document.createTextNode('Overrides '));
          s.appendChild(App.ui.infoButton({description: 'Inside summary', label: 'Row', testid: 'tip-s'}).el);
          d.appendChild(s); d.appendChild(document.createTextNode('panel'));
          root.appendChild(d);
        }"""
    )
    page.locator("[data-testid=tip-s]").click()
    expect(_bubble(page, "tip-s")).to_be_visible()
    assert page.evaluate("() => document.getElementById('dt').open") is False


def test_toggletip_bubble_styling_uses_tokens(engine_page: Page) -> None:
    page = engine_page
    _mount(page, MOUNT_TIP)
    page.locator("[data-testid=tip-a]").click()
    got = _bubble(page, "tip-a").evaluate(
        """e => { const cs = getComputedStyle(e); const probe = document.createElement('div');
          probe.style.background = 'var(--surface-elevated)'; document.getElementById('harness-root').appendChild(probe);
          const bg = getComputedStyle(probe).backgroundColor; probe.remove();
          return {bg: cs.backgroundColor === bg, pos: cs.position, bw: cs.borderTopWidth, sh: cs.boxShadow !== 'none'}; }"""
    )
    assert got == {"bg": True, "pos": "absolute", "bw": "1px", "sh": True}


def test_toggletip_flips_above_near_the_viewport_bottom(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    page.evaluate(
        """() => {
          const root = document.getElementById('harness-root');
          const pad = document.createElement('div'); pad.style.height = (window.innerHeight - 40) + 'px';
          root.appendChild(pad);
          root.appendChild(App.ui.infoButton({description: 'A long description that wraps onto several lines in the bubble so it cannot fit below the button here', label: 'Low', testid: 'tip-low'}).el);
        }"""
    )
    page.locator("[data-testid=tip-low]").click()
    bubble = _bubble(page, "tip-low")
    expect(bubble).to_be_visible()
    box = bubble.bounding_box()
    vh = page.evaluate("() => window.innerHeight")
    assert box["y"] + box["height"] <= vh + 1


def test_bubble_typography_is_self_contained(engine_page: Page) -> None:
    """HAT (M31 F5): a toggletip inside an uppercase, letter-spaced container (a kv table header,
    a section eyebrow) must not inherit that: the bubble's own rule resets it."""
    page = engine_page
    load_harness(page)
    out = page.evaluate(
        """() => {
          const host = document.createElement('div');
          host.style.cssText = 'text-transform: uppercase; letter-spacing: 3px; font-weight: 700; font-family: monospace';
          const i = App.ui.infoButton({description: 'Mixed case description', label: 'Sensitive'});
          host.appendChild(i.el);
          document.getElementById('harness-root').appendChild(host);
          i.button.click();
          const b = i.el.querySelector('.ui-info-bubble');
          const cs = getComputedStyle(b);
          return {open: !!b, tt: cs.textTransform, ls: cs.letterSpacing, fw: cs.fontWeight, ff: cs.fontFamily};
        }"""
    )
    assert out["open"] is True
    assert out["tt"] == "none"
    assert out["ls"] in ("normal", "0px")
    assert out["fw"] == "400"
    assert "monospace" not in out["ff"].split(",")[0]
