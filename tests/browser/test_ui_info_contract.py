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
                  title: i.button.title, aria: i.button.getAttribute('aria-label'),
                  tid: i.button.getAttribute('data-testid'), desc: d.textContent, descCls: d.className,
                  svg: i.button.querySelectorAll('svg.ui-icon.ui-icon--sm').length, parent: d.parentNode === i.el};
        }""",
    )
    assert out == {
        "wrap": "SPAN.ui-info", "btn": "field-info-icon", "type": "button", "title": DESC,
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
