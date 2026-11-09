# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.message`` (M31 F6 L04, flight DD4) with
its ``attribution`` and ``relabel`` sub-entries: every role and modifier, ``body`` versus
``text``, the operator-only label and chip, the peer label, the streaming
``appendText`` / ``commit`` / ``finalize`` sequence, the attribution's time label and Copy
reply, and a 200-character unbroken word. The clipboard is stubbed in both engines (the
harness page has no clipboard permission) and a fake clock drives the 2-second revert.
Chromium and WebKit through ``engine_page`` + ``load_harness``; falls in the
``contracts-chat`` lane.
"""

from __future__ import annotations

import json

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

STUB_OK = """() => {
  window.written = [];
  Object.defineProperty(navigator, 'clipboard', {configurable: true,
    value: {writeText: (t) => { window.written.push(t); return Promise.resolve(); }}});
}"""

# A column frame like the message log: bubbles are flex items, as in the app.
FRAME_JS = """() => {
  const frame = document.createElement('div');
  frame.id = 'frame';
  frame.style.cssText = 'display: flex; flex-direction: column; gap: 12px; width: 600px;';
  document.getElementById('harness-root').appendChild(frame);
}"""


def _load(page: Page) -> None:
    page.clock.install()
    load_harness(page)
    page.evaluate(FRAME_JS)


def _msg(page: Page, opts: dict) -> None:
    page.evaluate(
        """(opts) => {
          window.__m = App.ui.message(Object.assign({testid: 'm-root'}, opts));
          document.getElementById('frame').appendChild(__m.el);
        }""",
        opts,
    )


def _cls(page: Page) -> str:
    return page.evaluate("() => __m.el.className")


def test_each_role_gets_its_class_and_testid(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    for role in ("user", "assistant", "tool", "system"):
        _msg(page, {"role": role, "text": "Hi"})
        assert _cls(page) == f"ui-message ui-message--{role}"
        expect(page.get_by_test_id("m-root").last).to_have_text("Hi")
        page.evaluate("() => __m.el.remove()")
    err = page.evaluate(
        "() => { try { App.ui.message({role: 'robot'}); return null; } catch (e) { return e.message; } }"
    )
    assert "unknown role" in err
    err = page.evaluate(
        "() => { try { App.ui.message({role: 'user', source: 'x'}); return null; } catch (e) { return e.message; } }"
    )
    assert "unknown source" in err


def test_roles_have_distinct_alignment_and_the_old_look(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    out = {}
    for role in ("user", "assistant", "tool", "system"):
        _msg(page, {"role": role, "text": "Hi"})
        out[role] = page.evaluate(
            "() => { const s = getComputedStyle(__m.el); return [s.alignSelf, s.maxWidth, s.whiteSpace, s.fontFamily.toLowerCase().includes('mono')]; }"
        )
        page.evaluate("() => __m.el.remove()")
    assert out["user"][0] == "flex-end" and out["user"][1] == "85%"
    assert (
        out["assistant"][0] == "flex-start"
        and out["tool"][0] == "flex-start"
        and out["system"][0] == "center"
    )
    assert out["tool"][3] is True and out["user"][3] is False
    assert all(v[2] == "pre-wrap" for v in out.values())


def test_api_source_and_error_tone_modifiers(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _msg(page, {"role": "user", "source": "api", "text": "Injected"})
    assert _cls(page) == "ui-message ui-message--user ui-message--api"
    api_bg = page.evaluate("() => getComputedStyle(__m.el).backgroundColor")
    page.evaluate("() => __m.el.remove()")
    _msg(page, {"role": "user", "text": "Mine"})
    assert page.evaluate("() => getComputedStyle(__m.el).backgroundColor") != api_bg
    page.evaluate("() => __m.el.remove()")
    _msg(page, {"role": "tool", "tone": "error", "text": "boom"})
    assert _cls(page) == "ui-message ui-message--tool ui-message--error"
    plain = page.evaluate("() => getComputedStyle(__m.el).borderLeftColor")
    page.evaluate("() => __m.el.remove()")
    _msg(page, {"role": "tool", "text": "fine"})
    assert page.evaluate("() => getComputedStyle(__m.el).borderLeftColor") != plain
    err = page.evaluate(
        "() => { try { App.ui.message({role: 'tool', tone: 'x'}); return null; } catch (e) { return e.message; } }"
    )
    assert "unknown tone" in err


def test_peer_bubble_is_left_aligned_with_a_visually_hidden_label(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _msg(page, {"role": "user", "peerName": "Dana", "text": "Hello there"})
    assert _cls(page) == "ui-message ui-message--user ui-message--peer"
    assert page.evaluate("() => getComputedStyle(__m.el).alignSelf") == "flex-start"
    label = page.locator(".ui-message-peer-label")
    expect(label).to_have_text("From Dana: ")
    assert (
        page.evaluate("() => __m.el.querySelector('.ui-message-peer-label').className")
        == "ui-message-peer-label visually-hidden"
    )
    assert (
        page.evaluate(
            "() => { const r = __m.el.querySelector('.ui-message-peer-label').getBoundingClientRect(); return r.width <= 1 && r.height <= 1; }"
        )
        is True
    )
    assert page.evaluate("() => __m.el.lastChild.nodeValue") == "Hello there"
    assert page.evaluate("() => __m.el.textContent") == "From Dana: Hello there"


def test_operator_only_label_chip_and_the_user_exemption(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _msg(page, {"role": "assistant", "visibility": "operator", "text": "Private"})
    assert _cls(page) == "ui-message ui-message--assistant ui-message--operator-only"
    expect(page.locator(".ui-message-operator-label")).to_have_text("[operator-only]")
    assert page.evaluate("() => __m.el.getAttribute('data-visibility')") == "operator"
    assert page.evaluate("() => getComputedStyle(__m.el).borderLeftWidth") == "3px"
    page.evaluate("() => __m.el.remove()")
    _msg(
        page,
        {
            "role": "tool",
            "visibility": "operator",
            "visibilityStyle": "chip",
            "visibilityLabel": "Operator only",
            "text": "result",
        },
    )
    assert page.locator(".ui-message-operator-chip .chip").count() == 1
    expect(page.locator(".ui-message-operator-chip")).to_have_text("Operator only")
    assert page.locator(".ui-message-operator-label").count() == 0
    page.evaluate("() => __m.el.remove()")
    # the operator's own message carries no marker, but the value is still recorded
    _msg(page, {"role": "user", "visibility": "operator", "text": "Mine"})
    assert _cls(page) == "ui-message ui-message--user"
    assert page.evaluate("() => __m.el.getAttribute('data-visibility')") == "operator"
    assert page.evaluate("() => __m.el.children.length") == 0
    err = page.evaluate(
        "() => { try { App.ui.message({role: 'tool', visibilityStyle: 'x'}); return null; } catch (e) { return e.message; } }"
    )
    assert "unknown visibilityStyle" in err


def test_body_wins_over_text_and_text_is_never_html(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    page.evaluate(
        """() => {
          const p = document.createElement('p'); p.textContent = 'rendered';
          window.__m = App.ui.message({role: 'assistant', body: p, text: 'ignored', testid: 'm-root'});
          document.getElementById('frame').appendChild(__m.el);
        }"""
    )
    assert page.evaluate("() => __m.el.innerHTML") == "<p>rendered</p>"
    page.evaluate("() => __m.el.remove()")
    _msg(page, {"role": "user", "text": "<img src=x onerror=alert(1)>"})
    assert page.evaluate("() => __m.el.querySelectorAll('img').length") == 0
    assert page.evaluate("() => __m.el.textContent") == "<img src=x onerror=alert(1)>"


def test_empty_text_and_a_200_character_word(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _msg(page, {"role": "user", "text": ""})
    assert page.evaluate("() => __m.el.childNodes.length") == 0
    page.evaluate("() => __m.el.remove()")
    for role in ("user", "assistant", "tool"):
        _msg(page, {"role": role, "text": "x" * 200})
        assert page.evaluate("() => __m.el.scrollWidth <= __m.el.clientWidth + 1") is True
        assert (
            page.evaluate(
                "() => __m.el.getBoundingClientRect().width <= document.getElementById('frame').clientWidth"
            )
            is True
        )
        page.evaluate("() => __m.el.remove()")


def test_assistant_markdown_descendants_are_styled(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    page.evaluate(
        """() => {
          const body = document.createDocumentFragment();
          const p = document.createElement('p'); p.textContent = 'para';
          const pre = document.createElement('pre'); const code = document.createElement('code'); code.textContent = 'x = 1'; pre.appendChild(code);
          const inline = document.createElement('p'); const c2 = document.createElement('code'); c2.textContent = 'y'; inline.appendChild(c2);
          body.appendChild(p); body.appendChild(pre); body.appendChild(inline);
          window.__m = App.ui.message({role: 'assistant', body: body, testid: 'm-root'});
          document.getElementById('frame').appendChild(__m.el);
        }"""
    )
    out = page.evaluate(
        """() => {
          const q = (s) => getComputedStyle(__m.el.querySelector(s));
          return {firstMargin: q('p').marginTop, preFamily: q('pre').fontFamily, preOverflow: q('pre').overflowX,
                  inlinePad: getComputedStyle(__m.el.querySelectorAll('code')[1]).paddingLeft, preCodePad: q('pre code').paddingLeft};
        }"""
    )
    assert out["firstMargin"] == "0px" and out["preOverflow"] == "auto"
    assert out["inlinePad"] == "5px" and out["preCodePad"] == "0px"


def test_streaming_tail_stays_last_and_appendtext_extends_it(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _msg(page, {"role": "assistant", "streaming": True})
    assert page.evaluate("() => __m.el.lastChild.nodeType === 3 && __m.tail() === ''") is True
    page.evaluate("() => { __m.appendText('Hel'); __m.appendText('lo'); }")
    assert page.evaluate("() => __m.tail()") == "Hello"
    assert page.evaluate("() => __m.el.textContent") == "Hello"
    page.evaluate("() => __m.el.remove()")
    # with an operator marker and a peer label, the tail is still the last child
    _msg(
        page, {"role": "assistant", "streaming": True, "visibility": "operator", "peerName": "Dana"}
    )
    page.evaluate("() => __m.appendText('x')")
    assert page.evaluate("() => __m.el.lastChild.nodeValue") == "x"
    assert page.evaluate(
        "() => Array.from(__m.el.childNodes).map((n) => n.nodeType === 3 ? '#text' : n.className)"
    ) == [
        "ui-message-operator-label",
        "ui-message-peer-label visually-hidden",
        "#text",
    ]


def test_commit_inserts_before_the_tail_and_consumes_characters(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _msg(page, {"role": "assistant", "streaming": True})
    out = page.evaluate(
        """() => {
          __m.appendText('para one\\n\\nnext');
          const f = document.createDocumentFragment();
          const p = document.createElement('p'); p.textContent = 'para one'; f.appendChild(p);
          __m.commit(f, 10);
          const afterCommit = [__m.el.innerHTML, __m.tail()];
          __m.commit(document.createDocumentFragment(), 4);  // empty fragment: nothing consumed
          __m.commit(null, 4);                                // null: nothing consumed
          return [afterCommit, __m.tail()];
        }"""
    )
    assert out[0] == ["<p>para one</p>next", "next"] and out[1] == "next"


def test_finalize_removes_the_tail_appends_and_freezes(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _msg(page, {"role": "assistant", "streaming": True})
    out = page.evaluate(
        """() => {
          __m.appendText('raw');
          const f = document.createDocumentFragment();
          const p = document.createElement('p'); p.textContent = 'final'; f.appendChild(p);
          __m.finalize(f);
          __m.appendText('late'); __m.commit(document.createDocumentFragment(), 1); __m.finalize(null);  // all no-ops
          return [__m.el.innerHTML, __m.tail()];
        }"""
    )
    assert out == ["<p>final</p>", ""]


def test_finalize_with_nothing_removes_even_an_empty_tail_and_double_finalize_is_safe(
    engine_page: Page,
) -> None:
    page = engine_page
    _load(page)
    _msg(page, {"role": "assistant", "streaming": True, "visibility": "operator"})
    page.evaluate("() => { __m.finalize(null); __m.finalize(null); }")
    assert page.evaluate("() => __m.el.childNodes.length") == 1  # only the operator label remains
    _msg(page, {"role": "user", "text": "plain"})  # not streaming: these are no-ops
    page.evaluate(
        "() => { __m.appendText('x'); __m.commit(document.createDocumentFragment(), 1); __m.finalize(null); __m.destroy(); __m.destroy(); }"
    )
    assert (
        page.evaluate("() => __m.el.textContent") == "plain"
        and page.evaluate("() => __m.tail()") == ""
    )


HOLD_JS = """() => {
  window.__hold = document.createElement('div');
  window.__hold.setAttribute('data-hold', '1');
  window.__frag = (text) => {
    const f = document.createDocumentFragment();
    const p = document.createElement('p'); p.textContent = text; f.appendChild(p);
    return f;
  };
  window.__shape = () => Array.from(__m.el.childNodes).map(
    (n) => n.nodeType === 3 ? '#' + n.nodeValue : n.tagName.toLowerCase() + (n.textContent ? ':' + n.textContent : ''));
}"""


def test_tail_hold_shows_only_the_prefix_and_keeps_the_full_tail(engine_page: Page) -> None:
    """AC4: with a hold the text node shows tail.slice(0, offset), the node follows it, tail()
    is the full logical text, appendText extends it, and el.lastChild is the hold node."""
    page = engine_page
    _load(page)
    _msg(page, {"role": "assistant", "streaming": True})
    page.evaluate(HOLD_JS)
    out = page.evaluate(
        """() => {
          __m.appendText('abc```chart');
          __m.setTailHold(3, __hold);
          const a = [__shape(), __m.tail(), __m.el.lastChild === __hold];
          __m.appendText('\\n{"type"');
          const b = [__shape(), __m.tail()];
          __m.setTailHold(3, __hold);  // idempotent: same node, same offset
          const c = [__shape(), __hold.parentNode === __m.el];
          __m.setTailHold(0, null);
          const d = [__shape(), __m.tail(), __hold.parentNode];
          return [a, b, c, d];
        }"""
    )
    assert out[0] == [["#abc", "div"], "abc```chart", True]
    assert out[1] == [["#abc", "div"], 'abc```chart\n{"type"']
    assert out[2] == [["#abc", "div"], True]
    assert out[3] == [['#abc```chart\n{"type"'], 'abc```chart\n{"type"', None]


def test_tail_hold_idempotent_call_does_not_reinsert_the_node(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    _msg(page, {"role": "assistant", "streaming": True})
    page.evaluate(HOLD_JS)
    removed = page.evaluate(
        """() => {
          __m.appendText('xy');
          __m.setTailHold(1, __hold);
          let moves = 0;
          const obs = new MutationObserver((recs) => { moves += recs.length; });
          obs.observe(__m.el, {childList: true});
          __m.setTailHold(1, __hold);
          __m.setTailHold(1, __hold);
          return new Promise((res) => setTimeout(() => { obs.disconnect(); res(moves); }, 0));
        }"""
    )
    assert removed == 0


def test_tail_hold_commit_past_the_offset_clears_it_and_within_shifts_it(
    engine_page: Page,
) -> None:
    """AC4: consumed > offset clears (node removed, not destroyed); consumed <= offset shifts."""
    page = engine_page
    _load(page)
    _msg(page, {"role": "assistant", "streaming": True})
    page.evaluate(HOLD_JS)
    out = page.evaluate(
        """() => {
          __m.appendText('one\\n\\ntwo```chart\\n{');
          __m.setTailHold(8, __hold);          // 'one\\n\\ntwo'
          __m.commit(__frag('one'), 5);        // consumed 5 <= 8: shifts to 3
          const a = [__shape(), __m.tail(), __hold.parentNode === __m.el];
          __m.commit(__frag('two'), 4);        // consumed 4 > 3: clears
          const b = [__shape(), __m.tail(), __hold.parentNode];
          const stillUsable = typeof __hold.remove === 'function';
          return [a, b, stillUsable];
        }"""
    )
    assert out[0] == [["p:one", "#two", "div"], "two```chart\n{", True]
    assert out[1] == [["p:one", "p:two", "#``chart\n{"], "``chart\n{", None]
    assert out[2] is True


def test_tail_hold_empty_fragment_commit_leaves_the_offset_unshifted(engine_page: Page) -> None:
    """AC4: the early return for an empty or null fragment happens BEFORE the hold shift."""
    page = engine_page
    _load(page)
    _msg(page, {"role": "assistant", "streaming": True})
    page.evaluate(HOLD_JS)
    out = page.evaluate(
        """() => {
          __m.appendText('  ```chart\\n{');
          __m.setTailHold(2, __hold);
          __m.commit(document.createDocumentFragment(), 2);
          __m.commit(null, 2);
          __m.appendText('x');
          return [__shape(), __m.tail()];
        }"""
    )
    assert out == [["#  ", "div"], "  ```chart\n{x"]


def test_tail_hold_finalize_clears_a_stale_hold_first(engine_page: Page) -> None:
    """AC4: finalize clears the hold before appending (also a hold left by drainPacing)."""
    page = engine_page
    _load(page)
    _msg(page, {"role": "assistant", "streaming": True})
    page.evaluate(HOLD_JS)
    out = page.evaluate(
        """() => {
          __m.appendText('t```chart\\n{');
          __m.setTailHold(1, __hold);
          __m.appendText('"a"');   // appended without a commit, as drainPacing does
          __m.finalize(__frag('done'));
          return [__m.el.innerHTML, __hold.parentNode, __m.tail()];
        }"""
    )
    assert out == ["<p>done</p>", None, ""]


def test_tail_hold_without_a_hold_writes_the_text_node_exactly_as_before(
    engine_page: Page,
) -> None:
    page = engine_page
    _load(page)
    _msg(page, {"role": "assistant", "streaming": True})
    out = page.evaluate(
        """() => {
          __m.appendText('a'); __m.appendText('b');
          return [__m.el.lastChild.nodeType, __m.el.lastChild.nodeValue, __m.el.childNodes.length];
        }"""
    )
    assert out == [3, "ab", 1]


def test_attribution_sides_time_label_and_degenerate_inputs(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    out = page.evaluate(
        """() => {
          const frame = document.getElementById('frame');
          const mk = (o) => { const a = App.ui.message.attribution(o); frame.appendChild(a.el); return a; };
          const you = mk({side: 'you', name: 'You', timeLabel: '3:45 PM', ts: '2026-10-27T15:45:00Z'});
          const agent = mk({side: 'agent', name: 'Helper'});
          const peer = mk({side: 'peer', name: 'Dana', timeLabel: ''});
          window.__you = you; window.__agent = agent;
          const ts = (a) => a.el.querySelector('.ui-message-attribution-ts');
          return {
            cls: [you.el.className, agent.el.className, peer.el.className],
            text: [you.el.textContent, agent.el.textContent, peer.el.textContent],
            tsAttr: ts(you).getAttribute('data-ts'), agentTs: ts(agent), peerTs: ts(peer),
            align: [getComputedStyle(you.el).alignSelf, getComputedStyle(agent.el).alignSelf, getComputedStyle(peer.el).alignSelf],
            err: (() => { try { App.ui.message.attribution({side: 'x'}); return null; } catch (e) { return e.message; } })(),
          };
        }"""
    )
    assert out["cls"] == [
        "ui-message-attribution ui-message-attribution--you",
        "ui-message-attribution ui-message-attribution--agent",
        "ui-message-attribution ui-message-attribution--peer",
    ]
    assert out["text"] == ["You · 3:45 PM", "Helper", "Dana"]
    assert (
        out["tsAttr"] == "2026-10-27T15:45:00Z" and out["agentTs"] is None and out["peerTs"] is None
    )
    assert out["align"] == ["flex-end", "flex-start", "flex-start"]
    assert "unknown side" in out["err"]
    # setTimeLabel adds, changes and removes the time without a stray separator
    page.evaluate("() => __agent.setTimeLabel('4:00 PM')")
    assert page.evaluate("() => __agent.el.textContent") == "Helper · 4:00 PM"
    page.evaluate("() => __agent.setTimeLabel('4:01 PM')")
    assert page.evaluate("() => __agent.el.textContent") == "Helper · 4:01 PM"
    page.evaluate("() => __agent.setTimeLabel(null)")
    assert page.evaluate("() => __agent.el.textContent") == "Helper"
    assert page.evaluate("() => __agent.el.childNodes.length") == 1
    page.evaluate("() => __you.setTimeLabel('')")
    assert page.evaluate("() => __you.el.textContent") == "You"


def test_relabel_rewords_every_time_and_skips_null(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    out = page.evaluate(
        """() => {
          const frame = document.getElementById('frame');
          for (const ts of ['a', 'b', 'c']) {
            frame.appendChild(App.ui.message.attribution({side: 'agent', name: ts.toUpperCase(), timeLabel: 'old', ts}).el);
          }
          frame.appendChild(App.ui.message.attribution({side: 'agent', name: 'D'}).el);  // no time: untouched
          const seen = [];
          App.ui.message.relabel(frame, (ts) => { seen.push(ts); return ts === 'b' ? null : 'new ' + ts; });
          App.ui.message.relabel(null, () => 'x'); App.ui.message.relabel(frame, null);
          return {seen, text: Array.from(frame.children).map((n) => n.textContent)};
        }"""
    )
    assert out["seen"] == ["a", "b", "c"]
    assert out["text"] == ["A · new a", "B · old", "C · new c", "D"]


def test_copy_reply_button_copies_the_given_text_confirms_and_reverts(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    page.evaluate(STUB_OK)
    page.evaluate(
        """() => {
          window.__a = App.ui.message.attribution({side: 'agent', name: 'Helper', timeLabel: '3:45 PM',
            copyText: 'stored **markdown**', copyTestid: 'a-copy'});
          document.getElementById('frame').appendChild(__a.el);
        }"""
    )
    btn = page.get_by_role("button", name="Copy reply")
    expect(btn).to_have_count(1)
    assert page.evaluate("() => __a.el.querySelectorAll('svg').length") == 1
    btn.click()
    expect(page.get_by_role("button", name="Copied")).to_have_count(1)
    assert page.evaluate("() => window.written") == ["stored **markdown**"]
    page.clock.run_for(2100)
    expect(page.get_by_role("button", name="Copy reply")).to_have_count(1)
    # setCopy retargets without a second button, and null removes the node it owns
    page.evaluate("() => __a.setCopy(() => 'second')")
    assert page.get_by_test_id("a-copy").count() == 1
    page.get_by_role("button", name="Copy reply").click()
    assert page.evaluate("() => window.written") == ["stored **markdown**", "second"]
    page.clock.run_for(2100)
    page.evaluate("() => __a.setCopy(null)")
    assert page.get_by_role("button").count() == 0
    assert page.evaluate("() => __a.el.textContent") == "Helper · 3:45 PM"
    page.evaluate("() => __a.setCopy('again')")
    assert page.get_by_role("button", name="Copy reply").count() == 1


def test_copy_reply_with_a_shared_live_node_carries_no_status_span_of_its_own(
    engine_page: Page,
) -> None:
    page = engine_page
    _load(page)
    page.evaluate(STUB_OK)
    page.evaluate(
        """() => {
          window.__live = document.createElement('div');
          __live.setAttribute('role', 'status'); __live.className = 'visually-hidden'; __live.id = 'shared-live';
          document.body.appendChild(__live);
          const frame = document.getElementById('frame');
          window.__a1 = App.ui.message.attribution({side: 'agent', name: 'A', copyText: 'one', liveEl: __live, copyTestid: 'c1'});
          window.__a2 = App.ui.message.attribution({side: 'agent', name: 'B', copyText: 'two', liveEl: __live, copyTestid: 'c2'});
          frame.appendChild(__a1.el); frame.appendChild(__a2.el);
        }"""
    )
    assert page.locator("#frame [role=status]").count() == 0
    assert (
        page.evaluate(
            "() => __a1.el.querySelector('button') !== null && __a1.el.querySelector('.ui-copy') === null"
        )
        is True
    )
    page.get_by_test_id("c2").click()
    expect(page.locator("#shared-live")).to_have_text("Copied")
    assert page.evaluate("() => window.written") == ["two"]


def test_attribution_without_copy_has_no_button_and_a_live_node_is_optional(
    engine_page: Page,
) -> None:
    page = engine_page
    _load(page)
    page.evaluate(
        "() => document.getElementById('frame').appendChild(App.ui.message.attribution({side: 'you', name: 'You'}).el)"
    )
    assert page.get_by_role("button").count() == 0
    assert (
        json.dumps(page.evaluate("() => document.getElementById('frame').textContent")) == '"You"'
    )


def test_marker_chip_on_any_role_and_validation(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    for role in ("user", "assistant"):
        _msg(page, {"role": role, "text": "Body", "marker": {"label": "Routine"}})
        assert page.locator(".ui-message-marker-chip .chip").count() == 1
        expect(page.locator(".ui-message-marker-chip")).to_have_text("Routine")
        assert page.evaluate("() => __m.el.textContent") == "RoutineBody"
        page.evaluate("() => __m.el.remove()")
    # order: operator chip, marker chip, peer label, body
    _msg(
        page,
        {
            "role": "tool",
            "visibility": "operator",
            "visibilityStyle": "chip",
            "marker": {"label": "Routine"},
            "peerName": "Dana",
            "text": "x",
        },
    )
    kids = page.evaluate("() => Array.from(__m.el.children).map(c => c.className.split(' ')[0])")
    assert kids == ["ui-message-operator-chip", "ui-message-marker-chip", "ui-message-peer-label"]
    page.evaluate("() => __m.el.remove()")
    # no marker: nothing extra; null/undefined are no-ops
    _msg(page, {"role": "user", "text": "Plain", "marker": None})
    assert page.locator(".ui-message-marker-chip").count() == 0
    page.evaluate("() => __m.el.remove()")
    for bad in ({"label": ""}, {"label": 3}, {}, "Routine"):
        err = page.evaluate(
            "(bad) => { try { App.ui.message({role: 'user', marker: bad}); return null; } catch (e) { return e.message; } }",
            bad,
        )
        assert err and "marker" in err
