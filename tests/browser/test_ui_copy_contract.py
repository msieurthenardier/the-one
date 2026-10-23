# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.copyButton``, ``App.ui.copyField`` and
``App.ui.consentLink`` (M31 F1 L5). The clipboard is stubbed in both engines so they run the
same code; the fake clock drives the 2-second revert.

Falls in the ``contracts`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

STUB_OK = """() => {
  window.written = [];
  Object.defineProperty(navigator, 'clipboard', {configurable: true,
    value: {writeText: (t) => { window.written.push(t); return Promise.resolve(); }}});
}"""
STUB_FAIL = """() => {
  Object.defineProperty(navigator, 'clipboard', {configurable: true,
    value: {writeText: () => Promise.reject(new Error('denied'))}});
  window.execCalls = 0;
  document.execCommand = (cmd) => { window.execCalls++; return window.execResult; };
}"""


def _load(page: Page) -> None:
    page.clock.install()
    load_harness(page)


def test_copy_button_success_text_announcement_and_revert(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    page.evaluate(STUB_OK)
    page.evaluate(
        """() => {
          window.c = App.ui.copyButton({text: () => 'secret-value', testid: 'cp'});
          document.getElementById('harness-root').appendChild(c.el);
        }"""
    )
    btn = page.get_by_role("button", name="Copy", exact=True)
    assert page.evaluate("() => c.el.className") == "ui-copy"
    btn.click()
    expect(page.get_by_role("button", name="Copied", exact=True)).to_have_count(1)
    expect(page.locator(".ui-copy [role=status]")).to_have_text("Copied")
    assert page.evaluate("() => window.written") == ["secret-value"]
    assert page.get_by_test_id("cp").get_attribute("aria-label") is None
    page.clock.run_for(2100)
    expect(page.get_by_test_id("cp")).to_have_text("Copy")


def test_copy_button_failure_uses_fallback_then_reports(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    page.evaluate(STUB_FAIL)
    page.evaluate(
        """() => {
          window.execResult = false;
          const input = document.createElement('input'); input.value = 'abc';
          document.getElementById('harness-root').appendChild(input);
          window.c = App.ui.copyButton({text: 'abc', selectEl: input, testid: 'cp'});
          document.getElementById('harness-root').appendChild(c.el);
        }"""
    )
    page.get_by_test_id("cp").click()
    expect(page.get_by_test_id("cp")).to_have_text("Copy failed")
    expect(page.locator(".ui-copy [role=status]")).to_have_text("Copy failed")
    assert page.evaluate("() => window.execCalls") == 1
    page.clock.run_for(2100)
    expect(page.get_by_test_id("cp")).to_have_text("Copy")
    # the fallback succeeding after a rejected clipboard still reads "Copied"
    page.evaluate("() => { window.execResult = true; }")
    page.get_by_test_id("cp").click()
    expect(page.get_by_test_id("cp")).to_have_text("Copied")


def test_copy_button_icon_only_names_and_live_region_option(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    page.evaluate(STUB_OK)
    page.evaluate(
        """() => {
          const live = document.createElement('span'); live.setAttribute('role', 'status'); live.id = 'mine';
          const root = document.getElementById('harness-root');
          window.c = App.ui.copyButton({text: 'x', iconOnly: true, label: 'Copy token', liveEl: live,
            doneText: 'Token copied', testid: 'ic'});
          root.appendChild(c.el); root.appendChild(live);
        }"""
    )
    assert page.evaluate("() => c.el === c.button") is True
    btn = page.get_by_test_id("ic")
    expect(btn).to_have_attribute("aria-label", "Copy token")
    assert page.locator("[data-testid=ic] svg").count() == 1
    assert page.locator("[data-testid=ic] ~ [role=status]").count() == 1  # only the caller's region
    btn.click()
    expect(btn).to_have_attribute("aria-label", "Copied")
    expect(page.locator("#mine")).to_have_text("Token copied")
    page.clock.run_for(2100)
    expect(btn).to_have_attribute("aria-label", "Copy token")


def test_copy_field_dom_value_and_copy(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    page.evaluate(STUB_OK)
    out = page.evaluate(
        """() => {
          const extra = document.createElement('a'); extra.href = '#x'; extra.textContent = 'Open';
          window.f = App.ui.copyField({value: 'https://one.test/a', label: 'Address', extra: [extra],
            testid: 'cf-in', copyTestid: 'cf-copy'});
          document.getElementById('harness-root').appendChild(f.el);
          return {row: f.el.className, kids: Array.from(f.el.children).map((n) => n.tagName),
                  ro: f.input.readOnly, name: f.input.getAttribute('aria-label'), cls: f.input.className,
                  val: f.input.value, same: f.button === f.el.querySelector('button'),
                  font: getComputedStyle(f.input).fontFamily.toLowerCase().includes('mono')};
        }"""
    )
    assert out["row"] == "ui-copy-field ui-copy-field--mono"
    assert out["kids"] == ["INPUT", "A", "SPAN"]
    assert out["ro"] is True and out["name"] == "Address" and out["cls"].startswith("field-input")
    assert out["same"] is True and out["font"] is True
    page.get_by_test_id("cf-copy").click()
    assert page.evaluate("() => window.written") == ["https://one.test/a"]
    page.evaluate("() => f.setValue('https://one.test/b')")
    page.get_by_test_id("cf-copy").click()
    assert page.evaluate("() => window.written") == ["https://one.test/a", "https://one.test/b"]
    expect(page.get_by_role("textbox", name="Address")).to_have_value("https://one.test/b")


def test_copy_field_mono_false(engine_page: Page) -> None:
    load_harness(engine_page)
    cls = engine_page.evaluate(
        "() => App.ui.copyField({value: 'x', label: 'v', mono: false, rowClass: 'mine'}).el.className"
    )
    assert cls == "ui-copy-field mine"


def test_consent_link_safe_default_testids_and_classes(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    page.evaluate(STUB_OK)
    out = page.evaluate(
        """() => {
          const b = App.consentLink.build('https://auth.example/consent?x=1', {surface: 'mcp', sourceName: 'Goldfinch'});
          document.getElementById('harness-root').appendChild(b);
          const q = (s) => b.querySelector(s);
          return {same: App.consentLink === App.ui.consentLink, root: b.className,
            row: q('.consent-link-row').className, kids: Array.from(q('.consent-link-row').children).map((n) => n.tagName),
            url: q('.consent-link-url').getAttribute('data-testid'), open: q('.consent-link-open').getAttribute('data-testid'),
            copy: q('.consent-link-copy').getAttribute('data-testid'), name: q('.consent-link-url').getAttribute('aria-label'),
            live: q('.consent-link-live').getAttribute('role'), target: q('.consent-link-open').target,
            rel: q('.consent-link-open').rel, helpRef: q('.consent-link-open').getAttribute('aria-describedby') === q('.consent-link-help').id,
            focus: App.consentLink.focusTarget(b) === q('.consent-link-open'), copyCls: q('.consent-link-copy').className,
            fns: [typeof App.consentLink.isSafeUrl, typeof App.consentLink.focusTarget, typeof App.consentLink.build]};
        }"""
    )
    assert out["same"] is True and out["root"] == "consent-link consent-link--mcp"
    assert out["row"].split() == ["ui-copy-field", "ui-copy-field--mono", "consent-link-row"]
    assert out["kids"] == ["INPUT", "A", "BUTTON"]
    assert (out["url"], out["open"], out["copy"]) == (
        "mcp-consent-link-url",
        "mcp-consent-link-open",
        "mcp-consent-link-copy",
    )
    assert out["name"] == "Sign-in address for Goldfinch" and out["live"] == "status"
    assert (
        out["target"] == "_blank" and "noopener" in out["rel"] and out["helpRef"] and out["focus"]
    )
    assert "consent-link-copy" in out["copyCls"].split() and out["fns"] == ["function"] * 3
    page.locator(".consent-link-copy").click()
    expect(page.locator(".consent-link-copy")).to_have_text("Copied")
    expect(page.locator(".consent-link-live")).to_have_text("Link copied")
    assert page.locator(".consent-link-copy").get_attribute("aria-label") is None
    page.clock.run_for(2100)
    expect(page.locator(".consent-link-copy")).to_have_text("Copy")


def test_consent_link_chat_defaults_custom_ids_and_failure_text(engine_page: Page) -> None:
    page = engine_page
    _load(page)
    page.evaluate(STUB_FAIL)
    out = page.evaluate(
        """() => {
          window.execResult = false;
          const root = document.getElementById('harness-root');
          const a = App.ui.consentLink.build('http://auth.example/x');
          const b = App.ui.consentLink.build('https://auth.example/y', {urlTestid: 'u', openTestid: 'o', copyTestid: 'c'});
          root.appendChild(a); root.appendChild(b);
          const ids = (n) => ['.consent-link-url', '.consent-link-open', '.consent-link-copy'].map((s) => n.querySelector(s).getAttribute('data-testid'));
          return {a: ids(a), b: ids(b), aName: a.querySelector('.consent-link-url').getAttribute('aria-label'), aCls: a.className};
        }"""
    )
    assert out["a"] == ["chat-consent-link-url", "chat-consent-link-open", "chat-consent-link-copy"]
    assert out["b"] == ["u", "o", "c"] and out["aName"] == "Sign-in page URL"
    assert out["aCls"] == "consent-link consent-link--chat"
    page.get_by_test_id("chat-consent-link-copy").click()
    expect(page.get_by_test_id("chat-consent-link-copy")).to_have_text("Copy failed")
    expect(page.locator(".consent-link-live").first).to_have_text(
        "Copy failed — select the link and copy it"
    )


def test_consent_link_help_option(engine_page: Page) -> None:
    """opts.help: a string replaces the helper line, false omits it (and the open
    link's aria-describedby)."""
    page = engine_page
    _load(page)
    out = page.evaluate(
        """() => {
          const url = 'https://auth.example/z';
          const a = App.ui.consentLink.build(url, {help: 'Paste the code next.'});
          const b = App.ui.consentLink.build(url, {help: false});
          const c = App.ui.consentLink.build(url);
          const q = (n, s) => n.querySelector(s);
          return {aHelp: q(a, '.consent-link-help').textContent,
                  aDesc: q(a, '.consent-link-open').getAttribute('aria-describedby') === q(a, '.consent-link-help').id,
                  bHelp: b.querySelectorAll('.consent-link-help').length,
                  bDesc: q(b, '.consent-link-open').hasAttribute('aria-describedby'),
                  cHelp: q(c, '.consent-link-help').textContent.slice(0, 20)};
        }"""
    )
    assert out == {
        "aHelp": "Paste the code next.",
        "aDesc": True,
        "bHelp": 0,
        "bDesc": False,
        "cHelp": "Finish signing in in",
    }


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "ftp://x/y", "", "//evil.test"])
def test_consent_link_unsafe_url_renders_inert_notice(engine_page: Page, bad: str) -> None:
    page = engine_page
    load_harness(page)
    out = page.evaluate(
        """(bad) => {
          const b = App.ui.consentLink(bad, {surface: 'chat'});
          document.getElementById('harness-root').appendChild(b);
          return {safe: App.consentLink.isSafeUrl(bad), anchors: b.querySelectorAll('a, input, button').length,
                  note: b.querySelector('.consent-link-unsafe').textContent,
                  focus: App.consentLink.focusTarget(b) === b.querySelector('.consent-link-unsafe')};
        }""",
        bad,
    )
    assert out["safe"] is False and out["anchors"] == 0 and out["focus"] is True
    assert "isn't a web link" in out["note"]


def test_copy_field_button_label_and_feedback(engine_page: Page) -> None:
    """M31 F3 L03b: `buttonLabel` is the resting text and name; the name follows "Copied"."""
    page = engine_page
    _load(page)
    page.evaluate(STUB_OK)
    page.evaluate(
        """() => {
          window.f = App.ui.copyField({value: 'ABCD-1234', label: 'Pairing code', buttonLabel: 'Copy pairing code', copyTestid: 'pc'});
          document.getElementById('harness-root').appendChild(f.el);
        }"""
    )
    btn = page.get_by_test_id("pc")
    expect(page.get_by_role("button", name="Copy pairing code", exact=True)).to_have_count(1)
    assert btn.text_content() == "Copy pairing code" and btn.get_attribute("aria-label") is None
    btn.click()
    expect(page.get_by_role("button", name="Copied", exact=True)).to_have_count(1)
    assert btn.text_content() == "Copied" and btn.get_attribute("aria-label") is None
    page.clock.run_for(2100)
    expect(page.get_by_role("button", name="Copy pairing code", exact=True)).to_have_count(1)
    assert page.evaluate("() => window.written") == ["ABCD-1234"]
