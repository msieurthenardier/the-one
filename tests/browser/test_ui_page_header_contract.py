# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for ``App.ui.pageHeader`` and the ``editorShell`` page
variant / ``inset: 'none'`` options (M31 F4 L04a). Chromium and WebKit; ``contracts-controls``.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page

pytestmark = pytest.mark.browser

MOUNT = """([ancestor, opts]) => {
  const root = document.getElementById('harness-root');
  const wrap = document.createElement('div');
  if (ancestor) wrap.className = ancestor;
  root.appendChild(wrap);
  window.__h = App.ui.pageHeader(Object.assign({title: 'Appearance', testid: 'ph'}, opts || {}));
  wrap.appendChild(window.__h.el);
  return true;
}"""


def _mount(page: Page, ancestor: str | None = None, opts: str = "null") -> None:
    load_harness(page)
    page.evaluate(f"(a) => ({MOUNT})([a, {opts}])", ancestor)


def test_dom_shape_and_setters(engine_page: Page) -> None:
    _mount(
        engine_page,
        None,
        "{headingId: 'hid', intro: 'Pick one.', titleClassName: 'extra', actions: Object.assign(document.createElement('button'), {textContent: 'Go'})}",
    )
    out = engine_page.evaluate(
        """() => {
          const h = window.__h, el = h.el;
          const text = el.querySelector('.ui-page-header-text');
          return {
            cls: el.className, tid: el.getAttribute('data-testid'),
            kids: Array.from(el.children).map((k) => k.tagName + '.' + k.className),
            textKids: Array.from(text.children).map((k) => k.tagName + '.' + k.className),
            title: [h.titleEl.tagName, h.titleEl.className, h.titleEl.id, h.titleEl.tabIndex, h.titleEl.textContent],
            actionsEl: h.actionsEl === el.querySelector('.ui-page-header-actions'),
            btn: h.actionsEl.firstElementChild.tagName
          };
        }"""
    )
    assert out["cls"] == "page-header ui-page-header"
    assert out["tid"] == "ph"
    assert out["kids"] == ["DIV.ui-page-header-text", "DIV.ui-page-header-actions"]
    assert out["textKids"] == ["H1.page-title extra", "P.ui-page-header-intro"]
    assert out["title"] == ["H1", "page-title extra", "hid", -1, "Appearance"]
    assert out["actionsEl"] and out["btn"] == "BUTTON"
    engine_page.evaluate("() => { __h.setTitle('Prompts'); __h.setIntro('New intro'); }")
    assert engine_page.evaluate(
        "() => [__h.titleEl.textContent, __h.el.querySelector('.ui-page-header-intro').textContent]"
    ) == ["Prompts", "New intro"]
    engine_page.evaluate("() => __h.setIntro(null)")
    assert (
        engine_page.evaluate("() => __h.el.querySelectorAll('.ui-page-header-intro').length") == 0
    )
    assert engine_page.get_by_role("heading", name="Prompts", level=1).count() == 1


def test_no_actions_no_slot_and_requires_title(engine_page: Page) -> None:
    _mount(engine_page)
    assert engine_page.evaluate(
        "() => [__h.actionsEl, __h.el.querySelectorAll('.ui-page-header-actions').length, __h.el.querySelectorAll('.ui-page-header-intro').length]"
    ) == [None, 0, 0]
    assert engine_page.evaluate(
        "() => { try { App.ui.pageHeader({}); return 'ok'; } catch (e) { return e.message; } }"
    ).startswith("App.ui.pageHeader")


@pytest.mark.parametrize(
    ("ancestor", "want"),
    [(None, "16px 32px"), ("area-studio", "16px 32px"), ("area-admin", "16px 32px")],
)
def test_geometry_bare_and_under_areas(engine_page: Page, ancestor: str | None, want: str) -> None:
    _mount(engine_page, ancestor)
    got = engine_page.evaluate(
        "() => { const c = getComputedStyle(__h.el); return [c.paddingTop, c.paddingRight, c.paddingBottom, c.paddingLeft, c.display, c.alignItems]; }"
    )
    v, h = want.split()
    assert got == [v, h, v, h, "flex", "center"]


def test_actions_sit_at_the_right_end_of_the_row(engine_page: Page) -> None:
    _mount(
        engine_page,
        "area-admin",
        "{actions: Object.assign(document.createElement('button'), {textContent: 'Go'})}",
    )
    box = engine_page.evaluate(
        """() => { const r = __h.el.getBoundingClientRect(), a = __h.actionsEl.getBoundingClientRect(), t = __h.titleEl.getBoundingClientRect();
          return {right: Math.round(r.right - a.right), titleLeft: t.left < a.left, sameRow: a.top < t.bottom && a.bottom > t.top}; }"""
    )
    assert box["right"] == 32 and box["titleLeft"] and box["sameRow"]


# --- editorShell page variant and inset ------------------------------------------------

SHELL = """([extra, ancestor]) => {
  const root = document.getElementById('harness-root');
  const wrap = document.createElement('div');
  if (ancestor) wrap.className = ancestor;
  root.appendChild(wrap);
  window.__calls = [];
  const o = Object.assign({
    variant: 'page', title: 'Knowledge indexing', subtitle: 'Defaults.', testid: 'hdr',
    actions: {
      cancel: {testid: 'c-btn', onClick: () => window.__calls.push('cancel')},
      save: {testid: 's-btn', onClick: () => window.__calls.push('save')}
    }
  }, extra || {});
  window.__shell = App.ui.editorShell(o);
  wrap.appendChild(window.__shell.el);
  return true;
}"""


def _shell(page: Page, extra: str = "null", ancestor: str | None = None) -> None:
    load_harness(page)
    page.evaluate(f"(a) => ({SHELL})([{extra}, a])", ancestor)


def test_page_variant_header_shape(engine_page: Page) -> None:
    _shell(engine_page)
    out = engine_page.evaluate(
        """() => {
          const s = __shell, t = s.titleEl;
          return {
            root: s.el.className, tid: s.el.getAttribute('data-testid'),
            title: [t.tagName, t.className, t.tabIndex],
            kids: Array.from(s.el.children).map((k) => k.className),
            intro: s.el.querySelector('.ui-page-header-intro').textContent,
            acts: Array.from(s.el.querySelector('.form-actions').children).map((k) => k.tagName + '.' + k.className),
            lastChild: s.el.lastElementChild.className,
            inActionsSlot: s.el.querySelector('.ui-page-header-actions > .form-actions') !== null,
            matches: [t.matches('.editor-title'), t.matches('.page-title'), t.matches('[tabindex="-1"]')]
          };
        }"""
    )
    assert out["root"] == "page-header ui-page-header ui-editor-shell-header"
    assert out["tid"] == "hdr"
    assert out["title"] == ["H1", "page-title editor-title", -1]
    assert out["kids"] == [
        "ui-page-header-text",
        "ui-page-header-actions",
        "editor-error ui-editor-error-row",
    ]
    assert out["intro"] == "Defaults."
    assert out["acts"][0] == "SPAN.editor-unsaved" and out["acts"][-1] != "SPAN.editor-error"
    assert out["lastChild"] == "editor-error ui-editor-error-row"
    assert out["inActionsSlot"] and out["matches"] == [True, True, True]


def test_page_variant_behaves_like_the_default_variant(engine_page: Page) -> None:
    _shell(engine_page)
    engine_page.evaluate("() => __shell.focusTitle()")
    assert engine_page.evaluate("() => document.activeElement === __shell.titleEl") is True
    st = "() => [__shell.cancelButton.disabled, __shell.saveButton.disabled, __shell.el.querySelector('.editor-unsaved').textContent]"
    assert engine_page.evaluate(st) == [True, True, ""]
    engine_page.evaluate("() => __shell.setDirty(true)")
    assert engine_page.evaluate(st) == [False, False, "Unsaved changes"]
    engine_page.evaluate("() => __shell.setBusy(true)")
    assert engine_page.evaluate(st)[:2] == [True, True]
    engine_page.evaluate(
        "() => { __shell.setBusy(false); __shell.setError('Boom'); __shell.setTitle('Renamed'); __shell.setSubtitle('Other'); __shell.setSaveLabel('Apply'); }"
    )
    assert engine_page.evaluate(
        "() => [__shell.el.querySelector('.editor-error').textContent, __shell.titleEl.textContent, __shell.el.querySelector('.ui-page-header-intro').textContent, __shell.saveButton.textContent]"
    ) == ["Boom", "Renamed", "Other", "Apply"]
    engine_page.evaluate("() => __shell.setSubtitle(null)")
    assert (
        engine_page.evaluate("() => __shell.el.querySelectorAll('.ui-page-header-intro').length")
        == 0
    )
    engine_page.get_by_test_id("s-btn").click()
    assert engine_page.evaluate("() => window.__calls") == ["save"]


def test_page_variant_actions_and_caption_share_the_header_row(engine_page: Page) -> None:
    _shell(engine_page, "{}", "area-admin")
    engine_page.evaluate("() => __shell.setDirty(true)")
    box = engine_page.evaluate(
        """() => { const h = __shell.el.getBoundingClientRect();
          const rect = (e) => e.getBoundingClientRect();
          const t = rect(__shell.titleEl), s = rect(__shell.saveButton), u = rect(__shell.el.querySelector('.editor-unsaved'));
          const within = (r) => r.top >= h.top && r.bottom <= h.bottom && r.left >= h.left && r.right <= h.right;
          return {within: [within(t), within(s), within(u)], rows: [s.top < t.bottom && s.bottom > t.top, u.top < t.bottom && u.bottom > t.top], saveRight: s.left > t.left}; }"""
    )
    assert box["within"] == [True, True, True]
    assert box["rows"] == [True, True] and box["saveRight"]


def test_page_variant_throws(engine_page: Page) -> None:
    load_harness(engine_page)
    for extra, frag in [
        ("breadcrumb: {label: 'X', href: '#x'}", "breadcrumb"),
        ("titleLevel: 2", "h1"),
        ("variant: 'wide'", "variant"),
        ("inset: 'wide'", "inset"),
    ]:
        msg = engine_page.evaluate(
            f"() => {{ try {{ App.ui.editorShell({{variant: 'page', title: 'T', actions: {{save: {{}}}}, {extra}}}); return ''; }} catch (e) {{ return e.message; }} }}"
        )
        assert frag in msg, (extra, msg)


def test_default_variant_header_dom_is_pinned(engine_page: Page) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(
        """() => {
          const s = App.ui.editorShell({title: 'T', subtitle: 'S', testid: 'd', actions: {cancel: {}, save: {}}});
          const acts = s.el.querySelector('.form-actions');
          return {root: s.el.className, kids: Array.from(s.el.children).map((k) => k.className),
            first: [acts.firstElementChild.tagName, acts.firstElementChild.getAttribute('role')],
            last: acts.lastElementChild.className, errLast: s.el.lastElementChild.className, h: s.titleEl.tagName + '.' + s.titleEl.className,
            ui: s.el.querySelectorAll('.ui-page-header, .page-title').length};
        }"""
    )
    assert out["root"] == "editor-header ui-editor-shell-header"
    assert out["kids"] == ["editor-header-text", "form-actions", "editor-error ui-editor-error-row"]
    assert out["first"] == ["SPAN", "status"] and out["last"] == "btn-filled-primary save-btn"
    assert out["errLast"] == "editor-error ui-editor-error-row"
    assert out["h"] == "H1.editor-title" and out["ui"] == 0


@pytest.mark.parametrize("ancestor", ["area-admin", "area-studio"])
@pytest.mark.parametrize("variant", ["default", "page"])
def test_inset_none_removes_horizontal_padding_under_area_admin(
    engine_page: Page, variant: str, ancestor: str
) -> None:
    # No !important on the flush modifier (M31 F4 L11): it must win on specificity alone.
    _shell(engine_page, f"{{variant: '{variant}', inset: 'none', title: 'T'}}", ancestor)
    got = engine_page.evaluate(
        "() => { const c = getComputedStyle(__shell.el); return [c.paddingLeft, c.paddingRight, __shell.el.classList.contains('editor-header--flush'), c.paddingTop]; }"
    )
    assert got[:3] == ["0px", "0px", True]
    _shell(engine_page, f"{{variant: '{variant}', title: 'T'}}", ancestor)
    plain = engine_page.evaluate("() => getComputedStyle(__shell.el).paddingLeft")
    assert plain != "0px"


@pytest.mark.parametrize("ancestor", ["area-studio", "area-admin"])
def test_section_inset_none_under_areas(engine_page: Page, ancestor: str) -> None:
    load_harness(engine_page)
    out = engine_page.evaluate(
        """(a) => {
          const wrap = document.createElement('div'); wrap.className = a;
          document.getElementById('harness-root').appendChild(wrap);
          const flush = App.ui.section({title: 'T', inset: 'none'});
          const plain = App.ui.section({title: 'T'});
          wrap.appendChild(flush.el); wrap.appendChild(plain.el);
          const pad = (e) => [getComputedStyle(e).paddingLeft, getComputedStyle(e).paddingRight];
          let thrown = '';
          try { App.ui.section({inset: 'x'}); } catch (e) { thrown = e.message; }
          return {flush: pad(flush.el), plain: pad(plain.el), cls: flush.el.className, thrown};
        }""",
        ancestor,
    )
    assert out["flush"] == ["0px", "0px"]
    assert out["plain"] != ["0px", "0px"] or ancestor == "area-admin"
    assert "editor-section--flush" in out["cls"]
    assert "inset" in out["thrown"]


def test_shell_exposes_error_el_and_subtitle_testid(engine_page: Page) -> None:
    """M31 F4 L10: errorEl is the shell's error span (so a caller can give it a testid
    without a class query) and subtitleTestid lands on the intro / subtitle paragraph, in
    both variants."""
    load_harness(engine_page)
    out = engine_page.evaluate(
        """() => {
          const mk = (variant) => App.ui.editorShell({
            variant, title: 'T', subtitle: 'Sub', subtitleTestid: 'sub-id',
            errorRole: 'alert', actions: {save: {onClick() {}}}});
          const a = mk('page'), b = mk('default');
          a.setError('boom');
          return {
            page: [a.errorEl.className, a.errorEl.textContent, a.errorEl.getAttribute('role'),
                   a.el.querySelector('[data-testid="sub-id"]').textContent],
            plain: b.el.querySelector('[data-testid="sub-id"]').className
          };
        }"""
    )
    assert out["page"] == ["editor-error ui-editor-error-row", "boom", "alert", "Sub"]
    assert out["plain"] == "editor-subtitle"
