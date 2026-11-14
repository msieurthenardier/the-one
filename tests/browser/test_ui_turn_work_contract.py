# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.turnWork`` (sortie 16 L01, flight DD1-DD4,
DD7): the per-turn work group. States and labels, the dots timer, the count text, the live
activity and preview (tail, two lines, text only), items, the "Operator only" chip and the
accessible name. Chromium and WebKit through ``engine_page`` + ``load_harness``; falls in the
``contracts-chat`` lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

COUNT_JS = """() => {
  window.__live = new Set();
  const si = window.setInterval.bind(window), ci = window.clearInterval.bind(window);
  window.setInterval = (fn, ms) => { const id = si(fn, ms); window.__live.add(id); return id; };
  window.clearInterval = (id) => { window.__live.delete(id); ci(id); };
}"""

STATES = {
    "working": "Working",
    "done": "Work",
    "stopped": "Stopped",
    "error": "Ended with an error",
    "step-limit": "Paused at the step limit",
    "sign-in": "Waiting for sign-in",
}


def _load(page: Page, reduced: bool = False) -> None:
    page.emulate_media(reduced_motion="reduce" if reduced else "no-preference")
    page.clock.install()
    load_harness(page)
    page.evaluate(COUNT_JS)


def _mount(page: Page, state: str | None = None, width: int = 400) -> None:
    page.evaluate(
        """([state, width]) => {
          const frame = document.createElement('div');
          frame.style.cssText = 'display: flex; flex-direction: column; width: ' + width + 'px;';
          const opts = {testid: 'tw', previewTestid: 'tw-preview'};
          if (state) opts.state = state;
          window.__t = App.ui.turnWork(opts);
          frame.appendChild(__t.el);
          document.getElementById('harness-root').appendChild(frame);
        }""",
        [state, width],
    )


def _name(page: Page) -> str:
    return page.evaluate("() => __t.el.querySelector('summary').getAttribute('aria-label')")


def _count(page: Page) -> str:
    return page.evaluate("() => __t.el.querySelector('.ui-turn-work-count').textContent")


def _live(page: Page) -> int:
    return page.evaluate("() => __live.size")


def test_structure_details_closed_and_the_root_attributes(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _mount(page)
    assert page.evaluate("() => __t.el.tagName") == "DIV"
    assert page.evaluate("() => __t.el.getAttribute('data-testid')") == "tw"
    assert page.evaluate("() => __t.el.getAttribute('data-state')") == "working"
    assert page.evaluate("() => __t.el.querySelector(':scope > details') !== null") is True
    assert page.evaluate("() => __t.el.querySelector('details').open") is False
    assert (
        page.evaluate(
            "() => __t.el.querySelector('.ui-turn-work-preview').getAttribute('data-testid')"
        )
        == "tw-preview"
    )
    for sel in (".ui-turn-work-count", ".ui-turn-work-now", ".ui-turn-work-preview"):
        assert (
            page.evaluate(f"() => __t.el.querySelector('{sel}').getAttribute('aria-hidden')")
            == "true"
        )
    # No state change and no add opens it.
    page.evaluate("() => { __t.add('narration', 'x'); __t.setState('done'); }")
    assert page.evaluate("() => __t.el.querySelector('details').open") is False


def test_every_state_sets_the_data_attribute_and_label_and_unknown_throws(
    engine_page: Page,
) -> None:
    page = engine_page
    _load(page)
    _mount(page)
    for name, label in STATES.items():
        page.evaluate("(n) => __t.setState(n)", name)
        assert page.evaluate("() => __t.el.getAttribute('data-state')") == name
        assert (
            page.evaluate("() => __t.el.querySelector('.ui-turn-work-label').textContent") == label
        )
        assert _name(page) == label
    err = page.evaluate(
        "() => { try { __t.setState('nope'); return null; } catch (e) { return e.message; } }"
    )
    assert "unknown state" in err
    assert page.evaluate("() => __t.el.getAttribute('data-state')") == "sign-in"
    err = page.evaluate(
        "() => { try { App.ui.turnWork({state: 'x'}); return null; } catch (e) { return e.message; } }"
    )
    assert "unknown state" in err


def test_details_toggles_by_keyboard_and_stays_closed_by_default_in_every_state(
    engine_page: Page,
) -> None:
    page = engine_page
    _load(page)
    _mount(page)
    page.evaluate("() => __t.add('narration', 'hello')")
    page.locator("summary.ui-turn-work-toggle").focus()
    page.keyboard.press("Enter")
    assert page.evaluate("() => __t.el.querySelector('details').open") is True
    page.keyboard.press("Space")
    assert page.evaluate("() => __t.el.querySelector('details').open") is False
    for name in STATES:
        page.evaluate("(n) => App.ui.turnWork({state: n}).el.querySelector('details').open", name)
        assert (
            page.evaluate(
                "(n) => App.ui.turnWork({state: n}).el.querySelector('details').open", name
            )
            is False
        )
    page.evaluate("() => __t.destroy()")


def test_the_dots_run_only_while_working_and_leaving_stops_the_timer(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _mount(page)
    assert (
        page.evaluate("() => __t.el.querySelector('.ui-turn-work-lead .ui-thinking-dots') !== null")
        is True
    )
    assert page.evaluate("() => __t.el.querySelector('.ui-turn-work-lead svg') === null") is True
    assert _live(page) == 1
    for state in ("done", "stopped", "error", "step-limit", "sign-in"):
        page.evaluate("() => __t.setState('working')")
        assert _live(page) == 1
        page.evaluate("(s) => __t.setState(s)", state)
        assert _live(page) == 0
        assert (
            page.evaluate("() => __t.el.querySelector('.ui-turn-work-lead svg') !== null") is True
        )
        assert page.evaluate("() => __t.el.querySelector('.ui-thinking-dots') === null") is True
    # A resumed sign-in: fresh dots replace the chevron.
    page.evaluate("() => __t.setState('working')")
    assert _live(page) == 1
    assert page.evaluate("() => __t.el.querySelector('.ui-turn-work-lead svg') === null") is True


def test_stop_dots_keeps_the_state_destroy_stops_and_resume_restarts(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _mount(page)
    page.evaluate("() => __t.stopDots()")
    assert _live(page) == 0
    assert page.evaluate("() => __t.el.getAttribute('data-state')") == "working"
    assert (
        page.evaluate("() => __t.el.querySelector('.ui-turn-work-lead').textContent.trim()") == "…"
    )
    page.evaluate("() => __t.stopDots()")  # repeating is harmless
    page.evaluate("() => { __t.setState('done'); __t.setState('working'); }")
    assert _live(page) == 1
    page.evaluate("() => { __t.destroy(); __t.destroy(); }")
    assert _live(page) == 0
    page.evaluate("() => { __t.setState('done'); __t.setState('working'); __t.setPreview('x'); }")
    assert _live(page) == 0  # no timer restarted after destroy


def test_reduced_motion_runs_no_interval(engine_page: Page) -> None:
    page = engine_page
    _load(page, reduced=True)
    _mount(page)
    assert _live(page) == 0
    page.clock.run_for(500)
    assert _live(page) == 0
    assert page.evaluate("() => __t.el.querySelector('.ui-thinking-dots').textContent") == " …"


def test_reduced_motion_zeroes_the_chevron_transition(engine_page: Page) -> None:
    page = engine_page
    js = "() => getComputedStyle(__t.el.querySelector('.ui-turn-work-lead svg')).transitionDuration"
    _load(page, reduced=False)
    _mount(page, "done")
    assert page.evaluate(js) == "0.15s"
    _load(page, reduced=True)
    _mount(page, "done")
    assert page.evaluate(js) == "0s"


def test_tool_call_count_text_and_the_thinking_rule(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _mount(page)
    assert _count(page) == ""
    page.evaluate("() => __t.setToolCalls(1)")
    assert _count(page) == "· 1 tool call"
    assert _name(page) == "Working, 1 tool call"
    page.evaluate("() => __t.setToolCalls(3)")
    assert _count(page) == "· 3 tool calls"
    page.evaluate("() => __t.setState('done')")
    assert _name(page) == "Work, 3 tool calls"
    for bad in ("-2", "'x'", "null", "NaN"):
        page.evaluate(f"() => __t.setToolCalls({bad})")
        assert _count(page) == ""
    # Zero calls: "thinking" only for done with a thinking item.
    page.evaluate("() => { window.__th = __t.add('thinking', 'hmm'); }")
    assert _count(page) == "· thinking"
    assert _name(page) == "Work, thinking"
    page.evaluate("() => __t.setState('stopped')")
    assert _count(page) == ""
    page.evaluate("() => __t.setState('done')")
    assert _count(page) == "· thinking"
    page.evaluate("() => __th.remove()")
    assert _count(page) == ""
    assert _name(page) == "Work"


def test_activity_and_preview_show_only_while_working_and_leaving_clears_them(
    engine_page: Page,
) -> None:
    page = engine_page
    _load(page)
    _mount(page)
    page.evaluate("() => { __t.setActivity('read_file'); __t.setPreview('Looking at the file'); }")
    assert (
        page.evaluate("() => __t.el.querySelector('.ui-turn-work-now').textContent") == "read_file"
    )
    assert page.evaluate("() => __t.el.querySelector('.ui-turn-work-preview').hidden") is False
    page.evaluate("() => __t.setState('done')")
    assert page.evaluate("() => __t.el.querySelector('.ui-turn-work-now').textContent") == ""
    assert page.evaluate("() => __t.el.querySelector('.ui-turn-work-preview').hidden") is True
    assert page.evaluate("() => __t.el.querySelector('.ui-turn-work-preview').textContent") == ""
    page.evaluate("() => { __t.setActivity('x'); __t.setPreview('y'); }")  # not working: nothing
    assert page.evaluate("() => __t.el.querySelector('.ui-turn-work-now').textContent") == ""
    assert page.evaluate("() => __t.el.querySelector('.ui-turn-work-preview').hidden") is True
    # Preview set before any state change, then done.
    _mount(page)
    page.evaluate("() => { __t.setPreview('early'); __t.setState('done'); }")
    assert page.evaluate("() => __t.el.querySelector('.ui-turn-work-preview').hidden") is True
    # null and empty hide it.
    _mount(page)
    page.evaluate("() => __t.setPreview('abc')")
    page.evaluate("() => __t.setPreview(null)")
    assert page.evaluate("() => __t.el.querySelector('.ui-turn-work-preview').hidden") is True
    page.evaluate("() => { __t.setPreview('abc'); __t.setPreview(''); }")
    assert page.evaluate("() => __t.el.querySelector('.ui-turn-work-preview').hidden") is True


def test_the_preview_shows_the_end_of_a_long_text_in_two_lines_and_never_markup(
    engine_page: Page,
) -> None:
    page = engine_page
    _load(page)
    _mount(page, width=300)
    page.evaluate(
        """() => {
          const filler = Array.from({length: 120}, (_, i) => 'word' + i).join('  \\n ');
          __t.setPreview('STARTMARK ' + filler + ' <b>ENDMARK</b>');
        }"""
    )
    text = page.evaluate("() => __t.el.querySelector('.ui-turn-work-preview').textContent")
    assert len(text) <= 400
    assert "STARTMARK" not in text and text.endswith("<b>ENDMARK</b>")
    assert "  " not in text and "\n" not in text
    assert page.evaluate("() => __t.el.querySelector('.ui-turn-work-preview b') === null") is True
    geo = page.evaluate(
        """() => {
          const box = __t.el.querySelector('.ui-turn-work-preview');
          const node = box.firstChild;
          const at = (needle) => {
            const i = node.data.indexOf(needle);
            const r = document.createRange();
            r.setStart(node, i); r.setEnd(node, i + needle.length);
            return r.getBoundingClientRect();
          };
          const b = box.getBoundingClientRect();
          const end = at('ENDMARK'), early = at(node.data.split(' ')[0]);
          const lh = parseFloat(getComputedStyle(box).lineHeight);
          return {top: b.top, bottom: b.bottom, height: b.height, lh,
                  endTop: end.top, endBottom: end.bottom, earlyBottom: early.bottom};
        }"""
    )
    assert geo["height"] <= 2 * geo["lh"] + 1
    assert geo["endTop"] >= geo["top"] - 1 and geo["endBottom"] <= geo["bottom"] + 1
    assert geo["earlyBottom"] <= geo["top"] + 1  # the early text is cut off above the box


def test_items_in_order_with_text_content_setcontent_and_remove(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _mount(page)
    assert page.evaluate("() => __t.isEmpty()") is True
    page.evaluate(
        """() => {
          window.__n = __t.add('narration', 'a <i>b</i>\\nc');
          window.__th = __t.add('thinking', '<u>deep</u>');
          const tool = document.createElement('div');
          tool.className = 'ui-message ui-message--tool'; tool.textContent = 'tool row';
          window.__tool = __t.add('tool', tool);
          const frag = document.createElement('p'); frag.textContent = 'rendered';
          window.__n2 = __t.add('narration', frag);
        }"""
    )
    assert page.evaluate("() => __t.isEmpty()") is False
    kinds = page.evaluate(
        "() => Array.from(__t.el.querySelectorAll('.ui-turn-work-body > .ui-turn-work-item')).map(e => e.getAttribute('data-kind'))"
    )
    assert kinds == ["narration", "thinking", "tool", "narration"]
    assert page.evaluate("() => __n.el.textContent") == "a <i>b</i>\nc"
    assert page.evaluate("() => __n.el.querySelector('i') === null") is True
    assert (
        page.evaluate("() => __th.el.querySelector('.ui-turn-work-thinking-label').textContent")
        == "Thinking"
    )
    assert (
        page.evaluate("() => __th.el.querySelector('.ui-turn-work-thinking-text').textContent")
        == "<u>deep</u>"
    )
    assert page.evaluate("() => __th.el.querySelector('u') === null") is True
    assert page.evaluate("() => __n.kind + __tool.kind") == "narrationtool"
    err = page.evaluate(
        "() => { try { __t.add('bogus', 'x'); return null; } catch (e) { return e.message; } }"
    )
    assert "unknown kind" in err
    # setContent keeps the node and position.
    page.evaluate("() => { window.__el = __n.el; __n.setContent('new text'); }")
    assert page.evaluate("() => __n.el === __el && __el.parentNode.firstChild === __el") is True
    assert page.evaluate("() => __el.textContent") == "new text"
    page.evaluate(
        "() => { const p = document.createElement('p'); p.textContent = 'node'; __n.setContent(p); }"
    )
    assert page.evaluate("() => __el.textContent") == "node"
    page.evaluate("() => __th.setContent('changed')")
    assert (
        page.evaluate("() => __th.el.querySelector('.ui-turn-work-thinking-text').textContent")
        == "changed"
    )
    # remove takes it out; repeating is harmless; isEmpty follows.
    page.evaluate(
        "() => { for (const i of [__n, __th, __tool, __n2]) { i.remove(); i.remove(); } }"
    )
    assert page.evaluate("() => __t.isEmpty()") is True
    assert page.evaluate("() => __t.el.querySelectorAll('.ui-turn-work-item').length") == 0


def test_operator_only_chip_and_the_accessible_name(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _mount(page)
    chips = ".ui-turn-work-chip:not([hidden])"
    assert page.evaluate(f"() => __t.el.querySelectorAll('{chips}').length") == 0
    page.evaluate(
        "() => { __t.setState('stopped'); __t.setToolCalls(1); __t.setOperatorOnly(true); }"
    )
    assert page.evaluate(f"() => __t.el.querySelectorAll('{chips}').length") == 1
    assert "Operator only" in page.evaluate(
        "() => __t.el.querySelector('.ui-turn-work-chip').textContent"
    )
    assert _name(page) == "Stopped, 1 tool call, operator only"
    page.evaluate("() => __t.setOperatorOnly(true)")  # repeating keeps one chip
    assert page.evaluate("() => __t.el.querySelectorAll('.ui-turn-work-chip .chip').length") == 1
    page.evaluate("() => __t.setOperatorOnly(false)")
    assert page.evaluate(f"() => __t.el.querySelectorAll('{chips}').length") == 0
    assert page.evaluate("() => __t.el.querySelector('.ui-turn-work-chip').textContent") == ""
    assert _name(page) == "Stopped, 1 tool call"
    page.evaluate("() => { __t.setState('working'); __t.setToolCalls(0); }")
    assert _name(page) == "Working"
    page.evaluate("() => { __t.setActivity('shell'); __t.setPreview('some text'); }")
    assert _name(page) == "Working"  # the live parts never enter the name


def test_node_is_never_removed_by_destroy_and_calls_after_destroy_do_not_throw(
    engine_page: Page,
) -> None:
    page = engine_page
    _load(page)
    _mount(page)
    page.evaluate("() => __t.destroy()")
    assert page.evaluate("() => __t.el.isConnected") is True
    page.evaluate(
        "() => { __t.setState('done'); __t.setToolCalls(2); __t.add('narration', 'x'); __t.setOperatorOnly(true); }"
    )
    assert _name(page) == "Work, 2 tool calls, operator only"
