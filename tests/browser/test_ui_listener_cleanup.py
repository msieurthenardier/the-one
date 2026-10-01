# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Listener-cleanup evidence for the control-library mechanism decision (M25 F1 L2,
DD1 criterion 6), kept as a regression net for the committed factories.

The spike compared the factory list pane with a throwaway light-DOM custom element;
that element is deleted (evidence: the flight log's "Control-library mechanism"
decision). What remains tests committed code: after the host container is wiped with
``textContent = ''`` and no ``destroy()`` call, no document-level listener from the
factory is outstanding and no handler touches a detached node, and the
instrumentation itself is proven by a deliberately leaky control (negative control).
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

SETUP_JS = """() => {
  window.__selected = [];
  window.__spec = function () {
    const sel = (item) => window.__selected.push(item.id);
    return {
      title: 'Agents', testid: 'sp-root', emptyText: 'No agents match',
      filter: {label: 'Filter agents', testid: 'sp-filter'},
      selectedId: 'beta',
      items: [
        {id: 'alpha', label: 'Alpha', meta: 'first', onSelect: sel, testid: 'sp-row-alpha'},
        {id: 'beta', label: 'Beta', meta: 'second', href: '#beta', testid: 'sp-row-beta'},
        {id: 'gamma', label: 'Gamma', meta: 'third', onSelect: sel},
      ],
    };
  };
  return true;
}"""

# Criterion 6 instrumentation: wraps (add|remove)EventListener, recording
# registrations on document/window/body keyed by (target, type, listener,
# capture); honours once and signal. A separate probe counts attribute/focus/
# append calls that land on a detached node while armed.
INSTRUMENT_JS = """() => {
  const live = new Map();
  const ids = new WeakMap();
  let n = 0;
  const idOf = (l) => { if (!ids.has(l)) ids.set(l, ++n); return ids.get(l); };
  const tname = (t) => (t === document ? 'document' : t === window ? 'window' : t === document.body ? 'body' : null);
  const parse = (o) => (typeof o === 'boolean' ? {capture: o} : (o || {}));
  const add = EventTarget.prototype.addEventListener;
  const rem = EventTarget.prototype.removeEventListener;
  EventTarget.prototype.addEventListener = function (type, listener, options) {
    const name = tname(this);
    if (name && listener) {
      const o = parse(options);
      if (!(o.signal && o.signal.aborted)) {
        const key = [name, type, idOf(listener), !!o.capture].join('|');
        if (!live.has(key)) {
          live.set(key, {target: name, type, capture: !!o.capture, once: !!o.once, armedAt: window.__armed ? 'post' : 'pre'});
          if (o.once) add.call(this, type, () => live.delete(key), {capture: !!o.capture, once: true});
          if (o.signal) o.signal.addEventListener('abort', () => live.delete(key), {once: true});
        }
      }
    }
    return add.call(this, type, listener, options);
  };
  EventTarget.prototype.removeEventListener = function (type, listener, options) {
    const name = tname(this);
    if (name && listener) live.delete([name, type, idOf(listener), !!parse(options).capture].join('|'));
    return rem.call(this, type, listener, options);
  };
  window.__live = () => Array.from(live.values());
  window.__armed = false;
  window.__detachedTouches = 0;
  const touch = (proto, method) => {
    const orig = proto[method];
    proto[method] = function () {
      if (window.__armed && !this.isConnected) window.__detachedTouches += 1;
      return orig.apply(this, arguments);
    };
  };
  touch(HTMLElement.prototype, 'focus');
  touch(Element.prototype, 'setAttribute');
  touch(Element.prototype, 'removeAttribute');
  touch(Node.prototype, 'appendChild');
  touch(Node.prototype, 'insertBefore');
  return true;
}"""

LEAKY_JS = """() => {
  const host = document.getElementById('harness-root');
  const input = document.createElement('input');
  host.appendChild(input);
  document.addEventListener('keydown', function (e) { if (e.key === '/') input.focus(); });
  return true;
}"""


def _prepare(page: Page) -> None:
    load_harness(page)
    page.evaluate(SETUP_JS)


def _mount(page: Page) -> None:
    page.evaluate(
        "() => { const c = App.ui.listPane(window.__spec());"
        " document.getElementById('harness-root').appendChild(c.el); window.__pane = c; return true; }"
    )


def test_cleanup_wiping_host_leaves_no_listener(engine_page: Page) -> None:
    """Criterion 6: wipe the host with textContent = '' (no destroy call); no
    outstanding document-level listener, and no handler touches a detached node."""
    _prepare(engine_page)
    p = engine_page
    p.evaluate(INSTRUMENT_JS)
    baseline = p.evaluate("() => window.__live().length")
    _mount(p)
    p.get_by_test_id("sp-filter").fill("al")
    p.get_by_test_id("sp-row-alpha").focus()
    p.keyboard.press("ArrowDown")
    assert p.evaluate("() => window.__live()") == []  # the factory installs none while mounted
    p.evaluate("() => { document.getElementById('harness-root').textContent = ''; return true; }")
    after = p.evaluate("() => window.__live()")
    assert len(after) == baseline == 0, after
    p.evaluate("() => { window.__armed = true; return true; }")
    for key in ["/", "ArrowDown", "Escape", "Home"]:
        p.evaluate(
            "(k) => { document.dispatchEvent(new KeyboardEvent('keydown', {key: k, bubbles: true})); return true; }",
            key,
        )
    p.evaluate(
        "() => { document.dispatchEvent(new MouseEvent('click', {bubbles: true})); return true; }"
    )
    assert p.evaluate("() => window.__detachedTouches") == 0


def test_cleanup_negative_control_reports_a_leaky_control(engine_page: Page) -> None:
    """The instrumentation must catch a control that leaks (else a pass means nothing)."""
    load_harness(engine_page)
    p = engine_page
    p.evaluate(INSTRUMENT_JS)
    p.evaluate(LEAKY_JS)
    assert [(r["target"], r["type"]) for r in p.evaluate("() => window.__live()")] == [
        ("document", "keydown")
    ]
    p.evaluate("() => { document.getElementById('harness-root').textContent = ''; return true; }")
    assert len(p.evaluate("() => window.__live()")) == 1  # still outstanding after the wipe
    p.evaluate("() => { window.__armed = true; return true; }")
    p.evaluate(
        "() => { document.dispatchEvent(new KeyboardEvent('keydown', {key: '/'})); return true; }"
    )
    assert p.evaluate("() => window.__detachedTouches") >= 1  # and it acts on a detached node


def test_instrumentation_honours_once_and_signal_and_remove(engine_page: Page) -> None:
    load_harness(engine_page)
    p = engine_page
    p.evaluate(INSTRUMENT_JS)
    out = p.evaluate(
        """() => {
          const f = () => {};
          document.addEventListener('keydown', f, {once: true});
          const c = new AbortController();
          document.addEventListener('click', f, {signal: c.signal});
          document.addEventListener('keyup', f, true);
          const before = window.__live().length;
          document.dispatchEvent(new KeyboardEvent('keydown'));   // once consumed
          c.abort();                                             // signal aborted
          document.removeEventListener('keyup', f, true);         // explicit removal, same capture
          return [before, window.__live().length];
        }"""
    )
    assert out == [3, 0]


# ── menu (M25 F1 L5) ────────────────────────────────────────────────────────

MENU_MOUNT_JS = (
    "() => { const c = App.ui.menu({trigger: {label: 'Actions', testid: 'cl-trigger'},"
    " items: [{label: 'One', onSelect: () => {}}, {label: 'Two', onSelect: () => {}}]});"
    " document.getElementById('harness-root').appendChild(c.el); window.__menu = c; return true; }"
)


def test_menu_closed_has_zero_document_listeners(engine_page: Page) -> None:
    load_harness(engine_page)
    p = engine_page
    p.evaluate(INSTRUMENT_JS)
    p.evaluate(MENU_MOUNT_JS)
    assert p.evaluate("() => window.__live()") == []  # mounted, closed
    p.get_by_test_id("cl-trigger").click()
    live = p.evaluate("() => window.__live()")
    assert [(r["target"], r["type"], r["capture"]) for r in live] == [
        ("document", "pointerdown", True)
    ]
    p.keyboard.press("Escape")
    assert p.evaluate("() => window.__live()") == []  # closing removes it


def test_menu_open_then_host_wiped_leaves_nothing_outstanding(engine_page: Page) -> None:
    """Wipe the host with textContent = '' while open and no destroy(); one document
    pointerdown must leave zero outstanding listeners and touch no detached node."""
    load_harness(engine_page)
    p = engine_page
    p.evaluate(INSTRUMENT_JS)
    p.evaluate(MENU_MOUNT_JS)
    p.get_by_test_id("cl-trigger").click()
    assert len(p.evaluate("() => window.__live()")) == 1
    p.evaluate("() => { document.getElementById('harness-root').textContent = ''; return true; }")
    p.evaluate("() => { window.__armed = true; return true; }")
    p.evaluate(
        "() => { document.dispatchEvent(new MouseEvent('pointerdown', {bubbles: true})); return true; }"
    )
    assert p.evaluate("() => window.__live()") == []
    assert p.evaluate("() => window.__detachedTouches") == 0
    # the stale module-scope reference does not block or break the next menu
    p.evaluate(
        "() => { const c = App.ui.menu({trigger: {label: 'Next'}, items: [{label: 'x', onSelect: () => {}}]});"
        " document.getElementById('harness-root').appendChild(c.el); c.open('first'); window.__n = c.isOpen(); return true; }"
    )
    assert p.evaluate("() => window.__n") is True
