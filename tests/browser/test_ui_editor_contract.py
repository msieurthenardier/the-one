# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Engine-parametrized contract tests for the editor family of M31 F1 L4:
``App.ui.editorShell``, ``App.ui.section`` and ``App.ui.dangerZone``.

Every test runs in Chromium and WebKit through ``engine_page`` + ``load_harness``.
Falls in the ``contracts`` browser lane.
"""

from __future__ import annotations

import pytest
from browser._ui_engines import load_harness
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

MOUNT_SHELL = """(extra) => {
  window.__calls = [];
  const o = Object.assign({
    breadcrumb: {label: 'Library', href: '/library-root', trail: ' / Model providers'},
    title: 'My provider',
    subtitle: 'ollama · http://x',
    testid: 'hdr',
    actions: {
      cancel: {testid: 'c-btn', onClick: () => window.__calls.push('cancel')},
      save: {testid: 's-btn', onClick: () => window.__calls.push('save')},
      test: {testid: 't-btn', onClick: () => window.__calls.push('test')}
    }
  }, extra || {});
  window.__shell = App.ui.editorShell(o);
  document.getElementById('harness-root').appendChild(window.__shell.el);
  return true;
}"""


def _mount(page: Page, extra: str = "null", theme: str = "dark") -> None:
    load_harness(page, theme)
    page.evaluate(f"({MOUNT_SHELL})({extra})")


def test_shell_dom_shape_and_classes(engine_page: Page) -> None:
    _mount(engine_page)
    out = engine_page.evaluate(
        """() => {
          const h = window.__shell.el;
          const text = h.querySelector('.editor-header-text');
          const a = text.querySelector('.editor-breadcrumb > a.editor-breadcrumb-link');
          const acts = h.querySelector('.form-actions');
          return {
            root: h.className, tid: h.getAttribute('data-testid'),
            textKids: Array.from(text.children).map((k) => k.tagName + '.' + k.className),
            title: [text.querySelector('.editor-title').tagName, text.querySelector('.editor-title').tabIndex],
            crumb: [a.getAttribute('href'), a.textContent, a.getAttribute('data-testid'), a.parentNode.textContent],
            actKids: Array.from(acts.children).map((k) => k.tagName + '.' + k.className),
            unsaved: [acts.firstElementChild.getAttribute('role'), acts.firstElementChild.getAttribute('data-testid')],
            cancel: [window.__shell.cancelButton.disabled, window.__shell.saveButton.disabled],
            test: [window.__shell.testButton.querySelectorAll('svg[aria-hidden="true"]').length,
                   window.__shell.testButton.textContent, window.__shell.testButton.classList.contains('btn-sm')]
          };
        }"""
    )
    assert out["root"] == "editor-header"
    assert out["tid"] == "hdr"
    assert out["textKids"] == [
        "DIV.editor-breadcrumb", "H1.editor-title", "P.editor-subtitle",
    ]  # fmt: skip
    assert out["title"] == ["H1", -1]
    assert out["crumb"] == [
        "/library-root",
        "Library",
        "editor-breadcrumb-link",
        "Library / Model providers",
    ]
    assert out["actKids"] == [
        "SPAN.editor-unsaved",
        "BUTTON.btn-outlined-primary cancel-btn",
        "BUTTON.btn-filled-primary save-btn",
        "BUTTON.btn-outlined-primary",
        "SPAN.editor-error",
    ]
    assert out["unsaved"] == ["status", "editor-unsaved"]
    assert out["cancel"] == [True, True]
    assert out["test"] == [1, "Test", False]


def test_shell_roles_and_names(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    expect(page.get_by_role("link", name="Library")).to_have_attribute("href", "/library-root")
    expect(page.get_by_role("heading", level=1, name="My provider")).to_have_count(1)
    expect(page.get_by_role("button", name="Cancel")).to_have_count(1)
    expect(page.get_by_role("button", name="Save")).to_have_count(1)
    expect(page.get_by_role("button", name="Test", exact=True)).to_have_count(1)
    expect(page.get_by_role("status")).to_have_count(1)


def test_shell_h2_variant_and_trailing_link_breadcrumb(engine_page: Page) -> None:
    page = engine_page
    _mount(
        page,
        "{titleLevel: 2, breadcrumb: {lead: 'Settings / ', label: 'Built-in tools', href: '/tools-root'}, subtitle: null, actions: {save: {label: 'Create'}}}",
    )
    expect(page.get_by_role("heading", level=2, name="My provider")).to_have_count(1)
    out = page.evaluate(
        """() => {
          const c = document.querySelector('.editor-breadcrumb');
          return [c.firstChild.nodeType, c.firstChild.textContent, c.lastElementChild.textContent,
                  c.childNodes.length, !!document.querySelector('.editor-subtitle'),
                  window.__shell.cancelButton, window.__shell.testButton, window.__shell.saveButton.textContent];
        }"""
    )
    assert out == [3, "Settings / ", "Built-in tools", 2, False, None, None, "Create"]


def test_shell_attaches_no_handler_to_the_link(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    out = page.evaluate(
        """() => {
          const a = document.querySelector('.editor-breadcrumb-link');
          let prevented = null;
          document.addEventListener('click', (e) => { prevented = e.defaultPrevented; e.preventDefault(); }, {once: true});
          a.click();
          return prevented;
        }"""
    )
    assert out is False


def test_shell_setters(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    sh = "window.__shell"

    def state():
        return page.evaluate(
            f"""() => ({{
              caption: document.querySelector('.editor-unsaved').textContent,
              save: {sh}.saveButton.disabled, cancel: {sh}.cancelButton.disabled, test: {sh}.testButton.disabled,
              err: document.querySelector('.editor-error').textContent
            }})"""
        )

    assert state() == {"caption": "", "save": True, "cancel": True, "test": False, "err": ""}
    page.evaluate(f"{sh}.setDirty(true)")
    assert state() == {
        "caption": "Unsaved changes",
        "save": False,
        "cancel": False,
        "test": False,
        "err": "",
    }
    page.evaluate(f"{sh}.setBusy(true)")
    assert state() == {
        "caption": "Unsaved changes",
        "save": True,
        "cancel": True,
        "test": True,
        "err": "",
    }
    page.evaluate(f"{sh}.setBusy(false); {sh}.setError('Boom')")
    assert state()["err"] == "Boom" and state()["save"] is False
    page.evaluate(f"{sh}.setDirty(false); {sh}.setError(null)")
    assert state() == {"caption": "", "save": True, "cancel": True, "test": False, "err": ""}
    page.evaluate(
        f"{sh}.setSaveLabel('Create'); {sh}.setTitle('Renamed'); {sh}.setSubtitle('new sub')"
    )
    out = page.evaluate(
        f"() => [{sh}.saveButton.textContent, {sh}.titleEl.textContent, document.querySelector('.editor-subtitle').textContent]"
    )
    assert out == ["Create", "Renamed", "new sub"]
    page.evaluate(f"{sh}.setSubtitle(null)")
    expect(page.locator(".editor-subtitle")).to_have_count(0)
    page.evaluate(f"{sh}.setSubtitle('back')")
    expect(page.locator(".editor-subtitle")).to_have_text("back")


def test_shell_cancel_enabled_when_clean_and_focus_title(engine_page: Page) -> None:
    page = engine_page
    _mount(
        page,
        "{actions: {cancel: {enabledWhenClean: true, testid: 'c'}, save: {testid: 's'}}}",
    )
    assert page.evaluate(
        "() => [window.__shell.cancelButton.disabled, window.__shell.saveButton.disabled]"
    ) == [False, True]
    page.evaluate("window.__shell.setDirty(true); window.__shell.setDirty(false)")
    assert page.evaluate("() => window.__shell.cancelButton.disabled") is False
    page.evaluate("window.__shell.setBusy(true)")
    assert page.evaluate("() => window.__shell.cancelButton.disabled") is True
    page.evaluate("window.__shell.setBusy(false); window.__shell.focusTitle()")
    assert page.evaluate("() => document.activeElement === window.__shell.titleEl") is True
    page.evaluate("window.__shell.setTitle('Still focused')")
    assert page.evaluate("() => document.activeElement === window.__shell.titleEl") is True


def test_shell_extras_after_title_and_requirements(engine_page: Page) -> None:
    page = engine_page
    _mount(
        page,
        """{afterTitle: Object.assign(document.createElement('div'), {id: 'led', textContent: 'LED'}),
            actions: {save: {}, extra: [Object.assign(document.createElement('button'), {id: 'chat-x', textContent: 'Chat'})],
                      test: {className: 'custom-test'}}}""",
    )
    out = page.evaluate(
        """() => [Array.from(document.querySelector('.editor-header-text').children).map((k) => k.id || k.tagName),
                  Array.from(document.querySelector('.form-actions').children).map((k) => k.id || k.className.split(' ')[0]),
                  window.__shell.testButton.className]"""
    )
    assert out[0] == ["DIV", "H1", "led", "P"]
    assert out[1][:3] == ["editor-unsaved", "chat-x", "btn-filled-primary"]
    assert "custom-test" in out[2] and "test-provider-btn" not in out[2]
    msg = page.evaluate(
        "() => { try { App.ui.editorShell({title: 't'}); return ''; } catch (e) { return e.message; } }"
    )
    assert "save" in msg
    msg = page.evaluate(
        "() => { try { App.ui.editorShell({actions: {save: {}}}); return ''; } catch (e) { return e.message; } }"
    )
    assert "title" in msg


def test_shell_tab_order(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    page.evaluate("window.__shell.setDirty(true)")
    order = []
    page.locator(".editor-breadcrumb-link").focus()
    order.append(page.evaluate("() => document.activeElement.textContent"))
    for _ in range(3):
        page.keyboard.press("Tab")
        order.append(page.evaluate("() => document.activeElement.textContent"))
    assert order == ["Library", "Cancel", "Save", "Test"]
    # With nothing dirty, Cancel and Save are disabled and skipped.
    page.evaluate("window.__shell.setDirty(false)")
    page.locator(".editor-breadcrumb-link").focus()
    page.keyboard.press("Tab")
    assert page.evaluate("() => document.activeElement.textContent") == "Test"


def test_shell_test_button_matches_cancel_and_save(engine_page: Page) -> None:
    page = engine_page
    _mount(page)
    out = page.evaluate(
        """() => {
          const m = (b) => { const c = getComputedStyle(b); return [c.height, c.fontSize,
            c.paddingTop, c.paddingBottom]; };
          const t = window.__shell.testButton;
          const c = document.querySelector('.cancel-btn');
          const s = document.querySelector('.save-btn');
          return {t: m(t), c: m(c), s: m(s), icon: !!t.querySelector('svg'),
                  name: t.textContent.trim(), label: t.getAttribute('aria-label')};
        }"""
    )
    assert out["t"] == out["c"] == out["s"]
    assert out["icon"] and out["name"] == "Test"
    assert out["label"] in (None, "Test")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_shell_matches_legacy_provider_header_metrics(engine_page: Page, theme: str) -> None:
    page = engine_page
    _mount(page, theme=theme)
    out = page.evaluate(
        """() => {
          const root = document.getElementById('harness-root');
          const legacy = document.createElement('div');
          legacy.innerHTML = '<div class="editor-header"><div class="editor-header-text">' +
            '<div class="editor-breadcrumb"><a class="editor-breadcrumb-link" href="/library-root">Library</a> / Model providers</div>' +
            '<h1 class="editor-title" tabindex="-1">My provider</h1><p class="editor-subtitle">ollama · http://x</p></div>' +
            '<div class="form-actions"><span class="editor-unsaved" role="status"></span>' +
            '<button type="button" class="btn-outlined-primary cancel-btn" disabled>Cancel</button>' +
            '<button type="button" class="btn-filled-primary save-btn" disabled>Save</button>' +
            '<span class="editor-error"></span></div></div>';
          root.appendChild(legacy);
          const pick = (scope) => {
            const cs = (sel) => getComputedStyle(scope.querySelector(sel));
            return {
              titleSize: cs('.editor-title').fontSize, titleWeight: cs('.editor-title').fontWeight,
              crumb: cs('.editor-breadcrumb').fontSize, sub: cs('.editor-subtitle').fontSize,
              gap: cs('.form-actions').columnGap, pad: cs('.editor-header').padding,
              saveH: cs('.save-btn').height, saveBg: cs('.save-btn').backgroundColor,
              cancelH: cs('.cancel-btn').height, cancelBorder: cs('.cancel-btn').borderTopColor
            };
          };
          return [pick(window.__shell.el.parentNode), pick(legacy)];
        }"""
    )
    assert out[0] == out[1]


def test_section_dom(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    out = page.evaluate(
        """() => {
          const child = document.createElement('div'); child.id = 'kid';
          const s = App.ui.section({title: 'Connection', titleTag: 'h2', description: 'Where it lives', testid: 'sec',
                                    className: 'admin-pf-models', children: [child]});
          const plain = App.ui.section({title: 'Plain'});
          document.getElementById('harness-root').appendChild(s.el);
          document.getElementById('harness-root').appendChild(plain.el);
          s.body.appendChild(Object.assign(document.createElement('span'), {id: 'late'}));
          s.setTitle('Renamed');
          let bad = '';
          try { App.ui.section({title: 'x', titleTag: 'h1'}); } catch (e) { bad = e.message; }
          return {cls: s.el.className, tid: s.el.getAttribute('data-testid'),
                  kids: Array.from(s.el.children).map((k) => k.tagName + '.' + k.className + '#' + k.id),
                  plainTitle: plain.el.firstElementChild.tagName, bodyIsEl: s.body === s.el, bad: bad};
        }"""
    )
    assert out["cls"] == "editor-section admin-pf-models"
    assert out["tid"] == "sec"
    assert out["kids"] == [
        "H2.section-title#", "P.section-description#", "DIV.#kid", "SPAN.#late",
    ]  # fmt: skip
    assert out["plainTitle"] == "DIV"
    assert out["bad"]
    expect(page.get_by_role("heading", level=2, name="Renamed")).to_have_count(1)


def _mount_danger(page: Page, extra: str = "{}") -> None:
    load_harness(page)
    page.evaluate(
        f"""() => {{
          window.__dz = [];
          window.__zone = App.ui.dangerZone(Object.assign({{
            action: {{label: 'Delete Provider', testid: 'del', revertMs: 400, dataset: {{name: 'p1'}},
                     onConfirm: (revert) => {{ window.__dz.push('commit'); window.__revert = revert; }}}},
            notice: {{testid: 'blocked'}}
          }}, {extra}));
          document.getElementById('harness-root').appendChild(window.__zone.el);
        }}"""
    )


def test_danger_zone_dom(engine_page: Page) -> None:
    page = engine_page
    _mount_danger(page)
    out = page.evaluate(
        """() => {
          const z = window.__zone, b = z.button;
          const n = z.el.querySelector('.action-blocked-message');
          return {root: z.el.className, title: [z.el.firstElementChild.className, z.el.firstElementChild.textContent],
                  btn: b.className, tid: b.getAttribute('data-testid'), name: b.dataset.name,
                  kids: Array.from(b.children).map((k) => k.tagName + '.' + (k.getAttribute('class') || '')),
                  iconSize: b.querySelector('svg').getBoundingClientRect().width,
                  label: b.querySelector('[data-confirm-title]').textContent,
                  notice: [n.className, n.getAttribute('role'), n.getAttribute('aria-live'), n.hidden, n.getAttribute('data-testid'), n.parentNode === z.el]};
        }"""
    )
    assert out["root"] == "editor-section danger-zone"
    assert out["title"] == ["section-title danger-zone-title", "Danger Zone"]
    assert out["btn"] == "btn-muted-destructive delete-btn"
    assert out["tid"] == "del" and out["name"] == "p1"
    assert out["kids"][0].startswith("svg.ui-icon") and out["kids"][1] == "SPAN."
    assert out["iconSize"] == 16
    assert out["label"] == "Delete Provider"
    assert out["notice"] == [
        "action-blocked-message banner banner-error",
        "alert",
        None,
        False,
        "blocked",
        True,
    ]
    expect(page.get_by_role("button", name="Delete Provider")).to_have_count(1)


def test_danger_zone_arm_commit_and_lapse(engine_page: Page) -> None:
    page = engine_page
    _mount_danger(page)
    btn = page.get_by_test_id("del")
    btn.click()
    expect(btn).to_have_class("btn-muted-destructive delete-btn confirm-delete")
    expect(btn.locator("[data-confirm-title]")).to_have_text("Confirm delete?")
    assert page.evaluate("() => window.__dz") == []
    btn.click()
    assert page.evaluate("() => window.__dz") == ["commit"]
    page.evaluate("window.__revert()")
    expect(btn.locator("[data-confirm-title]")).to_have_text("Delete Provider")
    # Lapse: arm and wait past revertMs.
    btn.click()
    expect(btn).to_have_class("btn-muted-destructive delete-btn confirm-lapsed", timeout=5000)
    expect(btn.locator("[data-confirm-title]")).to_have_text("Delete Provider")
    expect(btn.locator("svg")).to_have_count(1)


def test_danger_zone_custom_label_notice_and_disable(engine_page: Page) -> None:
    page = engine_page
    _mount_danger(
        page,
        "{title: 'Remove', action: {label: 'Remove it', confirmLabel: 'Sure?', revertMs: 5000}}",
    )
    expect(page.locator(".danger-zone-title")).to_have_text("Remove")
    page.get_by_role("button", name="Remove it").click()
    expect(page.locator("[data-confirm-title]")).to_have_text("Sure?")
    notice = page.locator(".action-blocked-message")
    # The alert region is in the accessibility tree before any text is set, takes no space.
    expect(page.get_by_role("alert")).to_have_count(1)
    assert (
        page.evaluate(
            "() => document.querySelector('.action-blocked-message').getBoundingClientRect().height"
        )
        == 0
    )
    assert notice.get_attribute("hidden") is None and notice.get_attribute("aria-live") is None
    page.evaluate("window.__zone.setNotice('Used by agent a, b')")
    expect(notice).to_be_visible()
    expect(notice).to_have_text("Used by agent a, b")
    page.evaluate("window.__zone.setNotice(null)")
    expect(notice).to_be_hidden()
    page.evaluate("window.__zone.setDisabled(true)")
    assert page.evaluate("() => window.__zone.button.disabled") is True
    page.evaluate("window.__zone.setDisabled(false)")
    assert page.evaluate("() => window.__zone.button.disabled") is False


def test_danger_zone_without_notice(engine_page: Page) -> None:
    page = engine_page
    load_harness(page)
    out = page.evaluate(
        """() => { const z = App.ui.dangerZone({action: {label: 'Go'}}); z.setNotice('ignored');
                   return [!!z.el.querySelector('.action-blocked-message'), z.el.children.length]; }"""
    )
    assert out == [False, 2]


# ── dangerZone: actions (M31 F2 L4) ─────────────────────────────────────────

MOUNT_ZONE_ACTIONS = """(extra) => {
  window.__dz = [];
  window.__zone = App.ui.dangerZone(Object.assign({
    actions: [
      {label: 'Delete agent', testid: 'del-agent', revertMs: 400, onConfirm: () => window.__dz.push('agent')},
      {label: 'Clear history', testid: 'clear-hist', icon: 'refresh', confirmLabel: 'Really clear?', revertMs: 400,
       beforeArm: (proceed) => { window.__dz.push('before'); if (window.__allow) proceed(); },
       onConfirm: () => window.__dz.push('history')}
    ],
    notice: {testid: 'blocked'}
  }, extra || {}));
  document.getElementById('harness-root').appendChild(window.__zone.el);
  return true;
}"""


def _mount_actions(page: Page, extra: str = "null") -> None:
    load_harness(page)
    page.evaluate(f"({MOUNT_ZONE_ACTIONS})({extra})")


def test_danger_zone_actions_render_in_order_with_icons_and_notice_last(engine_page: Page) -> None:
    _mount_actions(engine_page)
    out = engine_page.evaluate(
        """() => {
          const z = window.__zone;
          return {kids: Array.from(z.el.children).map((k) => k.tagName + '.' + k.className),
            tids: z.buttons.map((b) => b.getAttribute('data-testid')), first: z.button === z.buttons[0],
            labels: z.buttons.map((b) => b.querySelector('[data-confirm-title]').textContent),
            icons: z.buttons.map((b) => b.querySelector('svg').getBoundingClientRect().width),
            api: Object.keys(z).sort()};
        }"""
    )
    assert out["kids"] == [
        "DIV.section-title danger-zone-title", "BUTTON.btn-muted-destructive delete-btn",
        "BUTTON.btn-muted-destructive delete-btn", "DIV.action-blocked-message banner banner-error",
    ]  # fmt: skip
    assert out["tids"] == ["del-agent", "clear-hist"] and out["first"] is True
    assert out["labels"] == ["Delete agent", "Clear history"] and out["icons"] == [16, 16]
    assert out["api"] == ["button", "buttons", "el", "setDisabled", "setNotice"]


def test_danger_zone_action_buttons_have_equal_height_and_gap(engine_page: Page) -> None:
    _mount_actions(engine_page)
    out = engine_page.evaluate(
        """() => { const r = window.__zone.buttons.map((b) => b.getBoundingClientRect());
          return {h: r.map((x) => x.height), gap: r[1].left - r[0].right, top: r.map((x) => x.top)}; }"""
    )
    assert len(set(out["h"])) == 1 and out["h"][0] > 0  # equal height
    assert out["gap"] > 0  # side by side, not touching


def test_danger_zone_actions_each_arm_and_commit_on_their_own(engine_page: Page) -> None:
    _mount_actions(engine_page)
    p = engine_page
    p.get_by_test_id("del-agent").click()
    expect(p.get_by_test_id("del-agent").locator("[data-confirm-title]")).to_have_text(
        "Confirm delete?"
    )
    expect(p.get_by_test_id("clear-hist").locator("[data-confirm-title]")).to_have_text(
        "Clear history"
    )
    p.get_by_test_id("del-agent").click()
    assert p.evaluate("() => window.__dz") == ["agent"]


def test_danger_zone_per_action_before_arm_gates_only_its_own_first_click(
    engine_page: Page,
) -> None:
    _mount_actions(engine_page)
    p = engine_page
    hist = p.get_by_test_id("clear-hist")
    hist.click()  # beforeArm runs and does not proceed: not armed
    assert p.evaluate("() => window.__dz") == ["before"]
    expect(hist.locator("[data-confirm-title]")).to_have_text("Clear history")
    p.evaluate("window.__allow = true")
    hist.click()
    expect(hist.locator("[data-confirm-title]")).to_have_text("Really clear?")
    hist.click()  # the second click commits without asking again
    assert p.evaluate("() => window.__dz") == ["before", "before", "history"]
    # The first action has no beforeArm: arming works with a single click.
    p.get_by_test_id("del-agent").click()
    expect(p.get_by_test_id("del-agent")).to_have_class(
        "btn-muted-destructive delete-btn confirm-delete"
    )


def test_danger_zone_set_disabled_all_or_by_index(engine_page: Page) -> None:
    _mount_actions(engine_page)
    p = engine_page
    p.evaluate("window.__zone.setDisabled(true, 1)")
    assert p.evaluate("() => window.__zone.buttons.map((b) => b.disabled)") == [False, True]
    p.evaluate("window.__zone.setDisabled(true)")
    assert p.evaluate("() => window.__zone.buttons.map((b) => b.disabled)") == [True, True]
    p.evaluate("window.__zone.setDisabled(false, 0)")
    assert p.evaluate("() => window.__zone.buttons.map((b) => b.disabled)") == [False, True]
    p.evaluate("window.__zone.setDisabled(false)")
    assert p.evaluate("() => window.__zone.buttons.map((b) => b.disabled)") == [False, False]


def test_danger_zone_singular_action_form_is_the_one_item_form(engine_page: Page) -> None:
    _mount_danger(engine_page)
    assert engine_page.evaluate(
        "() => [window.__zone.buttons.length, window.__zone.buttons[0] === window.__zone.button]"
    ) == [1, True]
