# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.searchList`` (M25 F4 L1, DD14,
A10): a combobox input over a grouped listbox, the agent picker's and the jump-to
palette's list. Covers the API (AC5), the ARIA model (AC6), keys and pointer (AC7)
and rendering and states (AC8).

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``
(no app spawn). Falls in the ``contracts`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._a11y_resolvers import assert_controls_labelled_and_described
from browser._ui_engines import load_harness
from browser.design_tokens import DARK, LIGHT
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

# Twelve agents: an empty query gives "Recently used" (3, repeating ids from
# "All agents") then "All agents" (12) and an empty "Pinned" group (dropped); a
# query gives one "{n} matching" group. Picks and source calls are recorded.
MOUNT_JS = """(opts) => {
  window.__picks = [];
  window.__calls = [];
  const names = ['Alpha', 'Bravo', 'Charlie', 'Delta', 'Echo', 'Foxtrot', 'Golf', 'Hotel',
                 'India', 'Juliet', 'Kilo', 'Lima'];
  const mk = (n) => ({id: n.toLowerCase(), label: n, description: 'The ' + n + ' agent, which has a long description that ellipsizes',
                      meta: 'model-' + n.toLowerCase(), metaMono: true,
                      lead: (() => { const s = document.createElement('span'); s.className = 'probe-lead'; return s; })(),
                      dataset: {agent: n.toLowerCase()}});
  const all = names.map(mk);
  window.__source = (q) => {
    window.__calls.push(q);
    const t = q.trim().toLowerCase();
    if (!t) return [
      {id: 'recent', label: 'Recently used', items: [mk('Charlie'), mk('Alpha'), mk('Kilo')]},
      {id: 'pinned', label: 'Pinned', items: []},
      {id: 'all', label: 'All agents', items: all.map((a) => mk(a.label))},
    ];
    const hits = all.filter((a) => a.label.toLowerCase().indexOf(t) !== -1).map((a) => mk(a.label));
    return [{id: 'matching', label: hits.length + ' matching', items: hits}];
  };
  const root = document.getElementById('harness-root');
  const outer = document.createElement('div');
  outer.id = 'sl-outer';
  outer.style.cssText = 'height: 260px; overflow: auto; width: 520px;';
  const spacer = document.createElement('div');
  spacer.style.height = '40px';
  outer.appendChild(spacer);
  root.appendChild(outer);
  const c = App.ui.searchList(Object.assign({
    label: 'Find an agent', placeholder: 'Find an agent by name',
    source: (q) => window.__source(q),
    emptyText: (q) => 'No agents match "' + q.trim() + '".',
    onPick: (item) => window.__picks.push(item.id),
    testid: 'sl-root', inputTestid: 'sl-input', rowTestid: 'sl-row',
  }, opts || {}));
  c.el.style.height = '200px';
  outer.appendChild(c.el);
  const tail = document.createElement('div');
  tail.style.height = '400px';
  outer.appendChild(tail);
  window.__sl = c;
  return true;
}"""


def _mount(page: Page, opts: str = "{}", theme: str = "dark") -> None:
    load_harness(page, theme)
    page.evaluate(f"({MOUNT_JS})({opts})")


def _state(page: Page) -> dict:
    return page.evaluate(
        """() => {
          const input = window.__sl.input;
          const rows = Array.from(document.querySelectorAll('[role=option]'));
          const ad = input.getAttribute('aria-activedescendant');
          const active = ad ? document.getElementById(ad) : null;
          return {
            activeLabel: active ? active.querySelector('.ui-search-list-label').textContent : null,
            activeIndex: active ? rows.indexOf(active) : -1,
            selected: rows.filter((r) => r.getAttribute('aria-selected') === 'true').map((r) => rows.indexOf(r)),
            focusInInput: document.activeElement === input,
            getActive: window.__sl.getActive() && window.__sl.getActive().id,
          };
        }"""
    )


def _rgb(hex_: str) -> str:
    h = hex_.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgb({r}, {g}, {b})"


# ── AC5: the API ────────────────────────────────────────────────────────────


def test_api_shape_and_required_options(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    out = p.evaluate(
        """() => ({keys: Object.keys(window.__sl).sort(), input: window.__sl.input.tagName,
                   inEl: window.__sl.el.contains(window.__sl.input),
                   rootTestid: window.__sl.el.dataset.testid, inputTestid: window.__sl.input.dataset.testid,
                   rowTestids: Array.from(new Set(Array.from(document.querySelectorAll('[role=option]')).map((r) => r.dataset.testid))),
                   placeholder: window.__sl.input.placeholder, calls: window.__calls.slice()})"""
    )
    assert out["keys"] == ["destroy", "el", "getActive", "input", "refresh", "setActive"]
    assert out["input"] == "INPUT" and out["inEl"] is True
    assert (out["rootTestid"], out["inputTestid"], out["rowTestids"]) == (
        "sl-root",
        "sl-input",
        ["sl-row"],
    )
    assert out["placeholder"] == "Find an agent by name"
    assert out["calls"] == [""]  # source is called once on creation
    errors = p.evaluate(
        """() => ['label', 'source'].map((drop) => {
          const o = {label: 'L', source: () => []};
          delete o[drop];
          try { App.ui.searchList(o); return ''; } catch (e) { return e.message; }
        })"""
    )
    assert errors == [
        "App.ui.searchList: label is required",
        "App.ui.searchList: source must be a function",
    ]


def test_source_is_called_on_every_input_and_on_refresh(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_test_id("sl-input").press_sequentially("li")
    p.evaluate("() => window.__sl.refresh()")
    assert p.evaluate("() => window.__calls") == ["", "l", "li", "li"]


def test_item_testid_wins_over_row_testid_and_dataset_lands_on_the_row(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate(
        """() => { const s = window.__source;
          window.__source = (q) => { const g = s(q); g[0].items[0].testid = 'sl-own'; return g; };
          window.__sl.refresh(); }"""
    )
    out = p.evaluate(
        """() => { const rows = document.querySelectorAll('[role=option]');
          return [rows[0].dataset.testid, rows[1].dataset.testid, rows[0].dataset.agent]; }"""
    )
    assert out == ["sl-own", "sl-row", "charlie"]


# ── AC6: ARIA ───────────────────────────────────────────────────────────────


def test_combobox_listbox_group_and_option_aria(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    out = p.evaluate(
        """() => {
          const input = window.__sl.input;
          const lb = document.querySelector('[role=listbox]');
          const groups = Array.from(lb.querySelectorAll('[role=group]'));
          const rows = Array.from(lb.querySelectorAll('[role=option]'));
          const ids = rows.map((r) => r.id);
          return {
            role: input.getAttribute('role'), auto: input.getAttribute('aria-autocomplete'),
            expanded: input.getAttribute('aria-expanded'),
            controls: input.getAttribute('aria-controls') === lb.id && !!lb.id,
            activedescendant: input.getAttribute('aria-activedescendant') === rows[0].id,
            labelClass: input.labels[0].className, labelText: input.labels[0].textContent,
            lbName: lb.getAttribute('aria-label'),
            groups: groups.map((g) => [document.getElementById(g.getAttribute('aria-labelledby')).textContent,
                                       g.querySelectorAll('[role=option]').length]),
            captions: Array.from(lb.querySelectorAll('.ui-search-list-caption')).map((c) =>
              [c.getAttribute('role'), c.parentNode.getAttribute('role'), c.matches('[role=option]')]),
            uniqueIds: new Set(ids).size === ids.length && ids.every(Boolean),
            selected: rows.filter((r) => r.hasAttribute('aria-selected')).map((r) => [rows.indexOf(r), r.getAttribute('aria-selected')]),
            tabindex: rows.filter((r) => r.hasAttribute('tabindex')).length,
            rowTabIndex: rows[0].tabIndex,
          };
        }"""
    )
    assert (out["role"], out["auto"], out["expanded"]) == ("combobox", "list", "true")
    assert out["controls"] and out["activedescendant"]
    assert out["labelClass"] == "visually-hidden" and out["labelText"] == "Find an agent"
    assert out["lbName"] == "Find an agent"
    # The empty "Pinned" group is dropped: no caption without options.
    assert out["groups"] == [["Recently used", 3], ["All agents", 12]]
    assert out["captions"] == [["presentation", "group", False]] * 2
    # "Recently used" repeats item ids from "All agents"; every option id is unique.
    assert out["uniqueIds"] is True
    assert out["selected"] == [[0, "true"]]  # only the active row carries aria-selected
    assert out["tabindex"] == 0 and out["rowTabIndex"] == -1  # rows are never focusable
    assert_controls_labelled_and_described(p, "[data-testid=sl-root]")


def test_a_group_without_a_label_has_no_caption_or_group(engine_page: Page) -> None:
    _mount(engine_page, "{source: () => [{items: [{id: 'a', label: 'A'}, {id: 'b', label: 'B'}]}]}")
    out = engine_page.evaluate(
        """() => { const lb = document.querySelector('[role=listbox]');
          return [lb.querySelectorAll('[role=group]').length, lb.querySelectorAll('.ui-search-list-caption').length,
                  Array.from(lb.children).map((n) => n.getAttribute('role'))]; }"""
    )
    assert out == [0, 0, ["option", "option"]]


# ── AC7: keys and pointer ───────────────────────────────────────────────────


def test_arrows_move_across_groups_clamped_without_wrap(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_test_id("sl-input").focus()
    assert _state(p)["activeIndex"] == 0
    p.keyboard.press("ArrowUp")  # clamped at the start
    assert _state(p)["activeIndex"] == 0
    for _ in range(3):
        p.keyboard.press("ArrowDown")
    s = _state(p)
    assert (s["activeIndex"], s["activeLabel"], s["getActive"]) == (
        3,
        "Alpha",
        "alpha",
    )  # crossed into "All agents"
    assert s["selected"] == [3] and s["focusInInput"] is True
    for _ in range(20):
        p.keyboard.press("ArrowDown")
    assert _state(p)["activeIndex"] == 14  # clamped at the end, no wrap to 0
    p.keyboard.press("ArrowUp")
    assert _state(p)["activeIndex"] == 13


def test_enter_picks_the_active_option_and_prevents_default(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate(
        "() => { window.__defaults = []; window.__sl.el.addEventListener('keydown', (e) => window.__defaults.push([e.key, e.defaultPrevented])); }"
    )
    p.get_by_test_id("sl-input").focus()
    p.keyboard.press("ArrowDown")
    p.keyboard.press("Enter")
    assert p.evaluate("() => window.__picks") == ["alpha"]
    assert p.evaluate("() => window.__defaults") == [["ArrowDown", True], ["Enter", True]]


def test_enter_with_no_options_does_nothing(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate(
        "() => { window.__defaults = []; window.__sl.el.addEventListener('keydown', (e) => window.__defaults.push([e.key, e.defaultPrevented])); }"
    )
    p.get_by_test_id("sl-input").fill("zzz")
    p.get_by_test_id("sl-input").press("Enter")
    assert p.evaluate("() => window.__picks") == []
    assert p.evaluate("() => window.__defaults") == [["Enter", False]]


def test_home_end_and_escape_are_not_intercepted(engine_page: Page) -> None:
    """Home and End move the caret (the APG combobox pattern); Escape belongs to
    the containing modal. Neither moves the active option or is prevented."""
    _mount(engine_page)
    p = engine_page
    p.evaluate(
        "() => { window.__defaults = []; window.__sl.el.addEventListener('keydown', (e) => window.__defaults.push([e.key, e.defaultPrevented])); }"
    )
    inp = p.get_by_test_id("sl-input")
    inp.fill("a")  # one "{n} matching" group
    p.keyboard.press("ArrowDown")
    before = _state(p)["activeIndex"]
    assert before == 1
    p.evaluate("() => { window.__defaults = []; }")
    p.keyboard.press("Home")
    caret_home = p.evaluate("() => window.__sl.input.selectionStart")
    p.keyboard.press("End")
    caret_end = p.evaluate("() => window.__sl.input.selectionStart")
    p.keyboard.press("Escape")
    assert (caret_home, caret_end) == (0, 1)
    assert _state(p)["activeIndex"] == before
    assert p.evaluate("() => window.__defaults") == [
        ["Home", False],
        ["End", False],
        ["Escape", False],
    ]


def test_each_source_call_makes_the_first_option_active(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    inp = p.get_by_test_id("sl-input")
    inp.focus()
    p.keyboard.press("ArrowDown")
    p.keyboard.press("ArrowDown")
    inp.press_sequentially("e")
    s = _state(p)
    assert s["activeIndex"] == 0 and s["activeLabel"] == "Charlie"  # the first of "{n} matching"
    p.keyboard.press("ArrowDown")
    p.evaluate("() => window.__sl.refresh()")
    assert _state(p)["activeIndex"] == 0


def test_ime_composition_keys_are_ignored(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    out = p.evaluate(
        """() => {
          const input = window.__sl.input;
          const fire = (key, init, keyCode) => {
            const e = new KeyboardEvent('keydown', Object.assign({key, bubbles: true, cancelable: true}, init));
            if (keyCode) Object.defineProperty(e, 'keyCode', {get: () => keyCode});
            input.dispatchEvent(e);
            return e.defaultPrevented;
          };
          const prevented = [
            fire('ArrowDown', {isComposing: true}),
            fire('Enter', {isComposing: true}),
            fire('ArrowDown', {}, 229),
            fire('Enter', {}, 229),
          ];
          const ad = input.getAttribute('aria-activedescendant');
          const rows = Array.from(document.querySelectorAll('[role=option]'));
          return {prevented, index: rows.indexOf(document.getElementById(ad)), picks: window.__picks.slice()};
        }"""
    )
    assert out == {"prevented": [False] * 4, "index": 0, "picks": []}


def test_pointer_hover_activates_and_click_picks_keeping_focus(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_test_id("sl-input").focus()
    third = p.locator("[role=option]").nth(2)
    third.hover()
    s = _state(p)
    assert (s["activeIndex"], s["selected"]) == (2, [2])
    third.click()
    assert p.evaluate("() => window.__picks") == ["kilo"]
    assert _state(p)["focusInInput"] is True  # a row press never takes focus


def test_keyboard_scrolls_the_active_option_into_view_inside_the_listbox_only(
    engine_page: Page,
) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_test_id("sl-input").focus()
    p.evaluate("() => { document.getElementById('sl-outer').scrollTop = 30; }")
    for _ in range(12):
        p.keyboard.press("ArrowDown")
    out = p.evaluate(
        """() => {
          const lb = document.querySelector('[role=listbox]');
          const ad = window.__sl.input.getAttribute('aria-activedescendant');
          const r = document.getElementById(ad).getBoundingClientRect();
          const b = lb.getBoundingClientRect();
          return {lbScroll: lb.scrollTop, outer: document.getElementById('sl-outer').scrollTop,
                  doc: document.scrollingElement.scrollTop,
                  inView: r.top >= b.top - 0.5 && r.bottom <= b.bottom + 0.5};
        }"""
    )
    assert out["lbScroll"] > 0 and out["inView"] is True, out
    assert (out["outer"], out["doc"]) == (30, 0), out  # no ancestor scrolled
    for _ in range(14):
        p.keyboard.press("ArrowUp")
    back = p.evaluate(
        "() => [document.querySelector('[role=listbox]').scrollTop, document.getElementById('sl-outer').scrollTop]"
    )
    assert back == [0, 30]  # the first option brings its group caption back into view


def test_set_active_and_get_active(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.evaluate("() => window.__sl.setActive('lima')")
    s = _state(p)
    assert (s["activeLabel"], s["getActive"]) == ("Lima", "lima")
    p.evaluate("() => window.__sl.setActive('nope')")
    assert _state(p)["getActive"] == "lima"  # an unknown id is a no-op
    # A repeated id (Recently used / All agents) activates its first occurrence.
    p.evaluate("() => window.__sl.setActive('alpha')")
    assert _state(p)["activeIndex"] == 1


# ── AC8: rendering and states ───────────────────────────────────────────────


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_row_anatomy_and_active_style(engine_page: Page, theme: str) -> None:
    _mount(engine_page, theme=theme)
    palette = DARK if theme == "dark" else LIGHT
    p = engine_page
    p.evaluate(
        "() => { document.getElementById('harness-root').style.background = 'var(--surface)'; }"
    )
    out = p.evaluate(
        """() => {
          const rows = document.querySelectorAll('[role=option]');
          const probe = (row) => {
            const s = getComputedStyle(row);
            const label = row.querySelector('.ui-search-list-label');
            const desc = row.querySelector('.ui-search-list-description');
            const meta = row.querySelector('.ui-search-list-meta');
            const lead = row.querySelector('.ui-search-list-lead');
            const ls = getComputedStyle(label), ds = getComputedStyle(desc), ms = getComputedStyle(meta);
            const rb = row.getBoundingClientRect(), mb = meta.getBoundingClientRect(), db = desc.getBoundingClientRect();
            return {pad: s.padding, gap: s.columnGap, border: s.borderTopWidth + ' ' + s.borderTopStyle + ' ' + s.borderTopColor,
                    bg: s.backgroundColor,
                    leadHidden: lead.getAttribute('aria-hidden'), leadFirst: row.firstElementChild === lead,
                    label: [ls.fontWeight, ls.color, ls.fontSize],
                    desc: [ds.fontSize, ds.color, ds.textOverflow, ds.whiteSpace, ds.overflow],
                    descBelow: db.top >= label.getBoundingClientRect().bottom - 1,
                    meta: [ms.fontSize, ms.color, ms.fontFamily.indexOf('Mono') !== -1 || ms.fontFamily.indexOf('mono') !== -1],
                    metaRight: rb.right - mb.right};
          };
          return {active: probe(rows[0]), rest: probe(rows[1])};
        }"""
    )
    rest, active = out["rest"], out["active"]
    assert rest["pad"] == "10px 12px" and rest["gap"] == "12px", rest
    assert rest["border"] == "1px solid rgba(0, 0, 0, 0)" and rest["bg"] == "rgba(0, 0, 0, 0)", rest
    assert rest["leadHidden"] == "true" and rest["leadFirst"] is True
    assert rest["label"] == ["600", _rgb(palette["fg"]), "13px"], rest
    assert rest["desc"] == [
        "11px",
        _rgb(palette["fg_secondary"]),
        "ellipsis",
        "nowrap",
        "hidden",
    ], rest
    assert rest["descBelow"] is True
    assert rest["meta"] == ["11px", _rgb(palette["fg_muted"]), True], rest
    assert abs(rest["metaRight"] - 13) <= 1, rest  # right-aligned inside 12px padding + 1px border
    # The active row: a wash plus an --accent border; the meta takes --fg-secondary.
    assert active["border"] == f"1px solid {_rgb(palette['accent'])}", active
    assert active["bg"] not in ("rgba(0, 0, 0, 0)", rest["bg"]), active
    assert active["meta"][1] == _rgb(palette["fg_secondary"]), active


def test_meta_is_not_mono_without_meta_mono(engine_page: Page) -> None:
    _mount(engine_page, "{source: () => [{label: 'G', items: [{id: 'a', label: 'A', meta: 'm'}]}]}")
    fam = engine_page.evaluate(
        "() => getComputedStyle(document.querySelector('.ui-search-list-meta')).fontFamily"
    )
    assert "mono" not in fam.lower()


def test_empty_result_shows_the_empty_state_and_hides_the_listbox(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    p.get_by_test_id("sl-input").fill("  zzz ")
    out = p.evaluate(
        """() => {
          const lb = document.querySelector('[role=listbox]');
          const empty = document.querySelector('.ui-search-list-empty');
          return {lbHidden: lb.hidden, lbDisplay: getComputedStyle(lb).display,
                  emptyHidden: empty.hidden, emptyClass: empty.className,
                  title: empty.querySelector('.ui-empty-title').textContent,
                  ad: window.__sl.input.hasAttribute('aria-activedescendant'),
                  status: document.querySelector('.ui-search-list [role=status]').textContent,
                  active: window.__sl.getActive()};
        }"""
    )
    assert out["lbHidden"] is True and out["lbDisplay"] == "none"
    assert out["emptyHidden"] is False and "empty-state" in out["emptyClass"]
    assert out["title"] == 'No agents match "zzz".'
    assert out["ad"] is False and out["active"] is None
    assert out["status"] == 'No agents match "zzz".'
    # A2: no options, no popup: aria-expanded follows the listbox.
    assert p.get_by_test_id("sl-input").get_attribute("aria-expanded") == "false"
    p.get_by_test_id("sl-input").fill("")
    assert p.get_by_test_id("sl-input").get_attribute("aria-expanded") == "true"
    back = p.evaluate(
        """() => [document.querySelector('[role=listbox]').hidden, document.querySelector('.ui-search-list-empty').hidden,
                  window.__sl.input.hasAttribute('aria-activedescendant'),
                  document.querySelector('.ui-search-list [role=status]').textContent]"""
    )
    assert back == [False, True, True, ""]


def test_labels_are_text_never_html(engine_page: Page) -> None:
    _mount(
        engine_page,
        "{source: () => [{label: '<i>G</i>', items: [{id: 'a', label: '<b>x</b>', description: '<img src=x>', meta: '<u>m</u>'}]}]}",
    )
    out = engine_page.evaluate(
        """() => { const lb = document.querySelector('[role=listbox]');
          return [lb.querySelectorAll('b, i, img, u').length, lb.querySelector('.ui-search-list-label').textContent,
                  lb.querySelector('.ui-search-list-caption').textContent]; }"""
    )
    assert out == [0, "<b>x</b>", "<i>G</i>"]


def test_a_bad_item_throws_before_the_dom_changes(engine_page: Page) -> None:
    _mount(engine_page)
    p = engine_page
    before = p.evaluate("() => document.querySelectorAll('[role=option]').length")
    msg = p.evaluate(
        """() => { window.__source = () => [{label: 'G', items: [{id: 'a', label: 'A', lead: 'not a node'}]}];
          try { window.__sl.refresh(); return ''; } catch (e) { return e.message; } }"""
    )
    assert msg == "App.ui.searchList item a: lead must be a node"
    assert p.evaluate("() => document.querySelectorAll('[role=option]').length") == before


def test_installs_no_document_listener_and_destroy_unbinds(engine_page: Page) -> None:
    load_harness(engine_page)
    p = engine_page
    p.evaluate(
        """() => {
          window.__docListeners = 0;
          const add = EventTarget.prototype.addEventListener;
          EventTarget.prototype.addEventListener = function (t, l, o) {
            if (this === document || this === window || this === document.body) window.__docListeners += 1;
            return add.call(this, t, l, o);
          };
        }"""
    )
    p.evaluate(f"({MOUNT_JS})({{}})")
    p.get_by_test_id("sl-input").press_sequentially("a")
    p.keyboard.press("ArrowDown")
    p.locator("[role=option]").first.hover()
    assert p.evaluate("() => window.__docListeners") == 0
    p.evaluate("() => window.__sl.destroy()")
    calls = p.evaluate("() => window.__calls.length")
    p.get_by_test_id("sl-input").press_sequentially("b")
    p.keyboard.press("Enter")
    assert p.evaluate("() => window.__calls.length") == calls  # no source call after destroy
    assert p.evaluate("() => window.__picks") == []
    assert p.evaluate("() => document.querySelectorAll('[role=option]').length") == 0


def test_status_region_announces_the_result_count_while_filtering(engine_page: Page) -> None:
    """A3: blank query -> empty status; a filter -> "{n} results" / "1 result";
    none -> the empty text; clearing returns to empty."""
    _mount(engine_page)
    p = engine_page
    status = p.locator(".ui-search-list [role=status]")
    inp = p.get_by_test_id("sl-input")
    expect(status).to_have_text("")
    inp.fill("i")  # Delta, Hotel, India, Juliet, Kilo, Lima, Echo? (no) -> counted below
    n = p.locator("[role=option]").count()
    assert n > 1
    expect(status).to_have_text(f"{n} results")
    inp.fill("alpha")
    expect(status).to_have_text("1 result")
    inp.fill("zzz")
    expect(status).to_have_text('No agents match "zzz".')
    inp.fill("")
    expect(status).to_have_text("")


# ── M31 F4 L04d: the inline variant ─────────────────────────────────────────

INLINE_JS = """(opts) => {
  window.__q = '';
  const zones = [];
  for (let i = 0; i < 60; i++) zones.push({id: 'z' + i, label: 'Zone ' + i, description: 'Region/Zone_' + i,
    meta: 'UTC+' + (i % 12), metaMono: true, selected: i === 30});
  window.__sel = 'z30';
  window.__src = (q) => {
    const t = q.trim().toLowerCase();
    const hits = zones.filter((z) => !t || z.label.toLowerCase().indexOf(t) !== -1)
      .map((z) => Object.assign({}, z, {selected: z.id === window.__sel}));
    return [{id: 'g', label: 'Region', items: hits}];
  };
  const note = document.createElement('p'); note.id = 'sl-note'; note.textContent = 'Chosen: Zone 30';
  document.getElementById('harness-root').appendChild(note);
  const c = App.ui.searchList(Object.assign({label: 'Search zones', source: (q) => window.__src(q),
    inline: true, keepScroll: true, describedBy: note, testid: 'il-root', inputTestid: 'il-input'}, opts || {}));
  document.getElementById('harness-root').appendChild(c.el);
  window.__il = c;
  return true;
}"""


def _inline(page: Page, opts: str = "{}") -> None:
    load_harness(page, "dark")
    page.evaluate(f"({INLINE_JS})({opts})")


def test_inline_caps_the_listbox_and_marks_the_root(engine_page: Page) -> None:
    _inline(engine_page)
    out = engine_page.evaluate(
        """() => { const lb = document.querySelector('.ui-search-list-listbox'); const s = getComputedStyle(lb);
          return {cls: window.__il.el.className, max: s.maxHeight, oy: s.overflowY, h: lb.getBoundingClientRect().height,
                  desc: getComputedStyle(document.querySelector('.ui-search-list-description')).fontFamily}; }"""
    )
    assert out["cls"] == "ui-search-list ui-search-list--inline"
    assert out["max"] == "252px" and out["oy"] == "auto" and out["h"] <= 252
    assert "mono" in out["desc"].lower() or "monospace" in out["desc"].lower()


def test_modal_default_is_not_inline(engine_page: Page) -> None:
    _mount(engine_page)
    out = engine_page.evaluate(
        "() => [window.__sl.el.className, getComputedStyle(document.querySelector('.ui-search-list-listbox')).maxHeight]"
    )
    assert out == ["ui-search-list", "none"]


def test_described_by_accepts_a_node_or_an_id(engine_page: Page) -> None:
    _inline(engine_page)
    assert (
        engine_page.evaluate("() => window.__il.input.getAttribute('aria-describedby')")
        == "sl-note"
    )
    load_harness(engine_page, "dark")
    engine_page.evaluate(f"({INLINE_JS})({{describedBy: 'sl-note'}})")
    assert (
        engine_page.evaluate("() => window.__il.input.getAttribute('aria-describedby')")
        == "sl-note"
    )


def test_selected_row_has_check_lead_and_name_says_selected(engine_page: Page) -> None:
    _inline(engine_page)
    p = engine_page
    expect(p.get_by_role("option", name="Zone 30 (selected)")).to_have_count(1)
    expect(p.get_by_role("option", name="(selected)")).to_have_count(1)
    out = p.evaluate(
        """() => { const rows = Array.from(document.querySelectorAll('[role=option]'));
          const lead = (r) => r.querySelector('.ui-search-list-lead');
          return {leads: rows.every((r) => lead(r) && lead(r).getAttribute('aria-hidden') === 'true'),
                  checks: rows.filter((r) => lead(r).querySelector('svg')).length,
                  checkIdx: rows.findIndex((r) => lead(r).querySelector('svg')),
                  sizes: Array.from(new Set(rows.map((r) => { const b = lead(r).getBoundingClientRect(); return b.width + 'x' + b.height; }))),
                  labelLefts: Array.from(new Set(rows.map((r) => Math.round(r.querySelector('.ui-search-list-label').getBoundingClientRect().left))))}; }"""
    )
    assert out["leads"] and out["checks"] == 1 and out["checkIdx"] == 30
    assert out["sizes"] == ["16x16"] and len(out["labelLefts"]) == 1


def test_a_filtered_out_selection_shows_no_check(engine_page: Page) -> None:
    _inline(engine_page)
    engine_page.fill('[data-testid="il-input"]', "Zone 4")
    assert (
        engine_page.evaluate("() => document.querySelectorAll('.ui-search-list-lead svg').length")
        == 0
    )
    expect(engine_page.get_by_role("option", name="(selected)")).to_have_count(0)


def test_keep_scroll_restores_on_an_unchanged_query(engine_page: Page) -> None:
    _inline(engine_page)
    p = engine_page
    out = p.evaluate(
        """() => { const lb = document.querySelector('.ui-search-list-listbox');
          window.__il.setActive('z40', {scroll: 'none'});
          lb.scrollTop = 321;
          window.__il.refresh();
          return [lb.scrollTop, window.__il.getActive().id]; }"""
    )
    assert out == [321, "z40"]


def test_keep_scroll_resets_on_a_changed_query_or_a_vanished_id(engine_page: Page) -> None:
    _inline(engine_page)
    p = engine_page
    out = p.evaluate(
        """() => { const lb = document.querySelector('.ui-search-list-listbox');
          lb.scrollTop = 300;
          window.__il.input.value = 'Zone 1';
          window.__il.input.dispatchEvent(new Event('input'));
          const a = [lb.scrollTop, window.__il.getActive().id];
          window.__il.setActive('z19', {scroll: 'none'});
          lb.scrollTop = 40;
          window.__src = (q) => [{id: 'g', label: 'Region', items: [{id: 'only', label: 'Only'}]}];
          window.__il.refresh();
          return [a, [lb.scrollTop, window.__il.getActive().id]]; }"""
    )
    assert out[0][0] == 0 and out[0][1] == "z1"
    assert out[1] == [0, "only"]


def test_without_keep_scroll_a_refresh_resets(engine_page: Page) -> None:
    _inline(engine_page, "{keepScroll: false}")
    out = engine_page.evaluate(
        """() => { const lb = document.querySelector('.ui-search-list-listbox');
          lb.scrollTop = 200; window.__il.refresh(); return [lb.scrollTop, window.__il.getActive().id]; }"""
    )
    assert out == [0, "z0"]


def test_scroll_active_center_nearest_and_none(engine_page: Page) -> None:
    _inline(engine_page)
    p = engine_page
    out = p.evaluate(
        """() => { const lb = document.querySelector('.ui-search-list-listbox');
          const mid = () => { const r = document.querySelector('[role=option][aria-selected=true]').getBoundingClientRect();
            const b = lb.getBoundingClientRect(); return Math.abs((r.top + r.height / 2) - (b.top + lb.clientHeight / 2 + lb.clientTop)); };
          window.__il.setActive('z30');
          const centered = mid();
          lb.scrollTop = 0;
          window.__il.setActive('z30', {scroll: 'none'});
          const none = lb.scrollTop;
          window.__il.setActive('z30', {scroll: 'nearest'});
          const nearestTop = lb.scrollTop;
          return {centered, none, nearestTop}; }"""
    )
    assert out["centered"] <= 1.5
    assert out["none"] == 0 and out["nearestTop"] > 0


def test_arrow_keys_stay_nearest_even_with_center(engine_page: Page) -> None:
    _inline(engine_page)
    p = engine_page
    p.evaluate("() => { window.__il.setActive('z5', {scroll: 'none'}); }")
    p.focus('[data-testid="il-input"]')
    for _ in range(12):
        p.keyboard.press("ArrowDown")
    out = p.evaluate(
        """() => { const lb = document.querySelector('.ui-search-list-listbox');
          const r = document.querySelector('[role=option][aria-selected=true]').getBoundingClientRect(); const b = lb.getBoundingClientRect();
          return [window.__il.getActive().id, Math.round(b.bottom - r.bottom)]; }"""
    )
    assert out[0] == "z17" and 0 <= out[1] <= 2


def test_unfocused_list_paints_no_active_row_focused_does(engine_page: Page) -> None:
    _inline(engine_page)
    p = engine_page
    read = """() => { const r = document.querySelector('[role=option][aria-selected=true]'); const s = getComputedStyle(r);
      return [s.backgroundColor, s.borderTopColor]; }"""
    unfocused = p.evaluate(read)
    assert unfocused[0] == "rgba(0, 0, 0, 0)" and unfocused[1] == "rgba(0, 0, 0, 0)"
    p.focus('[data-testid="il-input"]')
    focused = p.evaluate(read)
    assert focused[0] != "rgba(0, 0, 0, 0)" and focused[1] != "rgba(0, 0, 0, 0)"


def test_inline_forced_colours_twin_exists_in_the_css_text() -> None:
    from browser._ui_engines import STATIC_DIR

    css = (STATIC_DIR / "css" / "components.css").read_text()
    anchor = css.index(
        "@media (forced-colors: active)", css.index(".ui-search-list--inline:not(:focus-within)")
    )
    twin = '.ui-search-list--inline:not(:focus-within) .ui-search-list-row[aria-selected="true"] { border-color: Canvas; }'
    assert twin in css[anchor:]
