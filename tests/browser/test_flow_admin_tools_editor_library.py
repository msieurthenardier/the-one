"""M31 F4 legs 07a and 07b: the Built-in tools editor's frame, fields and errors on the library.

Defects found in planning (DD8), each written to fail on the pre-leg editor:

* 4  the Enabled control is a ``role=switch`` named "Enabled for all agents" with its label
     visible (it read "Disabled for all agents, not checked");
* 9  an error is announced once: exactly one ``role=alert`` region receives text, and a
     field's validation message is not repeated at editor level.

And the frame (B2, A9, A12, A13, A14, B3), the ``show_if`` reveal with hidden rows still
submitted, and the error placement rule (DD3): a 422 that names a field goes on the field,
the rest at editor level.
"""

from __future__ import annotations

import pytest
from browser import _nav
from playwright.sync_api import Page, Route, expect

ITEM = ".area-admin .settings-item"

ALERT_OBSERVER_JS = """() => {
  window.__alerts = new Set();
  const root = document.querySelector('.settings-item');
  new MutationObserver((records) => {
    for (const r of records) {
      const nodes = [...r.addedNodes];
      const texty = r.type === 'characterData' || nodes.some((n) => (n.textContent || '').trim());
      if (!texty) continue;
      const el = r.target.nodeType === 1 ? r.target : r.target.parentElement;
      const alert = el && el.closest('[role="alert"]');
      if (alert) window.__alerts.add(alert);
      for (const n of nodes) {
        if (n.nodeType === 1 && n.matches('[role="alert"]') && (n.textContent || '').trim()) {
          window.__alerts.add(n);
        }
      }
    }
  }).observe(root, {childList: true, subtree: true, characterData: true});
}"""


def _open(page: Page, base: str, tool: str) -> None:
    _nav.goto(page, base, f"settings/tools/{tool}")
    expect(page.locator(".editor-title")).to_have_text(tool, timeout=8000)


def _alerts_with_text(page: Page) -> int:
    page.wait_for_timeout(100)  # let the observer's records be delivered
    return page.evaluate("() => window.__alerts.size")


def _visible_alert_texts(page: Page) -> list[str]:
    return page.evaluate(
        """() => [...document.querySelectorAll('.settings-item [role="alert"]')]
            .map((e) => e.textContent.trim()).filter(Boolean)"""
    )


def _fulfil_put(page: Page, status: int, body: str) -> None:
    def handler(route: Route) -> None:
        if route.request.method == "PUT":
            route.fulfill(status=status, content_type="application/json", body=body)
        else:
            route.continue_()

    page.route("**/api/tools/configs/**", handler)


# ── DD8-4 and A9 ─────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_enabled_control_is_a_named_switch_with_a_visible_label(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "web_search")
    switch = page.get_by_role("switch", name="Enabled for all agents")
    expect(switch).to_have_count(1)
    expect(switch).to_be_checked()
    expect(switch).to_have_attribute("data-field", "enabled")
    # The visible label is on one line beside the switch (A9).
    label = page.locator(f'{ITEM} label:has(input[data-field="enabled"])')
    expect(label).to_contain_text("Enabled for all agents")
    box = label.bounding_box()
    line = page.evaluate(
        "(sel) => parseFloat(getComputedStyle(document.querySelector(sel)).lineHeight) || 20",
        f'{ITEM} label:has(input[data-field="enabled"]) .ui-choice-text',
    )
    assert box is not None and box["height"] < line * 2.2, box
    # Its name does not change with its state: the role carries the state.
    switch.evaluate("e => e.click()")
    expect(switch).not_to_be_checked()
    expect(page.get_by_role("switch", name="Enabled for all agents")).to_have_count(1)


# ── DD8-9 ────────────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_a_model_level_422_is_announced_once_at_editor_level(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "fetch_url")
    page.evaluate(ALERT_OBSERVER_JS)
    page.locator('input[data-field="timeout_seconds_max"]').fill("10")
    page.locator('[data-testid="save-tool-btn"]').click()
    error = page.locator(f"{ITEM} .editor-error")
    expect(error).to_contain_text("timeout_seconds_default", timeout=5000)
    assert "Value error" not in error.inner_text()
    assert _alerts_with_text(page) == 1
    assert len(_visible_alert_texts(page)) == 1


@pytest.mark.browser
def test_a_500_is_announced_once(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "web_search")
    _fulfil_put(page, 500, '{"detail": "Disk is full"}')
    page.evaluate(ALERT_OBSERVER_JS)
    page.locator('[data-field="search_backend"]').select_option("searxng")
    page.locator('[data-testid="save-tool-btn"]').click()
    expect(page.locator(f"{ITEM} .editor-error")).to_have_text("Disk is full", timeout=5000)
    assert _alerts_with_text(page) == 1
    # Save is available again, and the form is still dirty.
    expect(page.locator('[data-testid="save-tool-btn"]')).to_be_enabled()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")


@pytest.mark.browser
def test_a_field_422_goes_on_the_field_and_is_not_repeated(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "fetch_url")
    page.evaluate(ALERT_OBSERVER_JS)
    page.locator('input[data-field="redirect_cap"]').fill("-1")
    page.locator('[data-testid="save-tool-btn"]').click()
    field = page.locator('input[data-field="redirect_cap"]')
    expect(field).to_have_attribute("aria-invalid", "true", timeout=5000)
    row = page.locator(f'{ITEM} .tools-editor-field[data-field-name="redirect_cap"]')
    expect(row).to_contain_text("Must be 0 or more")
    # Nothing at editor level, and no second copy of the message anywhere.
    expect(page.locator(f"{ITEM} .editor-error")).to_have_text("")
    texts = _visible_alert_texts(page)
    assert texts.count("Must be 0 or more") == 1, texts
    assert _alerts_with_text(page) == 1
    # Typing into the field clears its error.
    field.fill("3")
    expect(field).not_to_have_attribute("aria-invalid", "true")
    expect(row).not_to_contain_text("Must be 0 or more")


@pytest.mark.browser
def test_a_422_naming_no_rendered_field_shows_at_editor_level(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "web_search")
    _fulfil_put(
        page,
        422,
        '{"detail": [{"loc": ["body", "config", "no_such_field"], "msg": "Input should be a valid'
        ' integer, unable to parse", "type": "int_parsing"}]}',
    )
    page.evaluate(ALERT_OBSERVER_JS)
    page.locator('[data-field="search_backend"]').select_option("searxng")
    page.locator('[data-testid="save-tool-btn"]').click()
    expect(page.locator(f"{ITEM} .editor-error")).to_contain_text(
        "Must be a whole number", timeout=5000
    )
    assert _alerts_with_text(page) == 1
    expect(page.locator(f'{ITEM} [aria-invalid="true"]')).to_have_count(0)


# ── The frame (B2, A13, A14, A12, B3) ────────────────────────────────────────


@pytest.mark.browser
def test_frame_breadcrumb_title_subtitle_and_prompt(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "web_search")
    crumb = page.locator(f"{ITEM} .editor-breadcrumb")
    expect(crumb).to_have_text("Settings / Built-in tools")
    link = crumb.locator("a.editor-breadcrumb-link")
    expect(link).to_have_text("Built-in tools")
    expect(link).to_have_attribute("href", _nav.href("settings/tools"))
    # One h1 on the page (the Settings page header); the tool title is an h2 at the
    # Library editors' size (B2).
    expect(page.locator("h1:visible")).to_have_count(1)
    title = page.locator(f"{ITEM} h2.editor-title")
    expect(title).to_have_text("web_search")
    size = title.evaluate("e => getComputedStyle(e).fontSize")
    token = page.evaluate(
        "() => { const p = document.createElement('p');"
        " p.style.fontSize = 'var(--font-size-h2)'; document.body.appendChild(p);"
        " const s = getComputedStyle(p).fontSize; p.remove(); return s; }"
    )
    assert size == token, (size, token)
    expect(page.locator(f"{ITEM} .editor-subtitle")).to_have_text("Web")  # A13
    # The prompt is a code block in its own section, below the header (A14).
    prompt = page.locator(f'{ITEM} .editor-section:has(> .section-title:text-is("Prompt"))')
    expect(prompt.locator("pre.code-block")).to_contain_text("Search the web")
    assert page.locator(f"{ITEM} .editor-header pre").count() == 0


@pytest.mark.browser
def test_prompt_block_does_not_reflow_when_the_editor_becomes_dirty(
    app_clean: str, page: Page
) -> None:
    _open(page, app_clean, "web_search")
    block = page.locator(f"{ITEM} pre.code-block")
    expect(block).to_be_visible()
    before = block.bounding_box()
    page.locator('[data-field="search_backend"]').select_option("searxng")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    after = block.bounding_box()
    assert before is not None and after is not None
    assert before["width"] == after["width"] and before["x"] == after["x"], (before, after)


@pytest.mark.browser
def test_a_tool_with_no_settings_says_so_in_plain_left_aligned_text(
    app_clean: str, page: Page
) -> None:
    _open(page, app_clean, "shell_session_close")
    note = page.locator(f'{ITEM} :text-is("No additional configuration.")')
    expect(note).to_have_count(1)
    align = note.evaluate("e => getComputedStyle(e).textAlign")
    assert align in ("start", "left"), align
    colour = note.evaluate("e => getComputedStyle(e).color")
    ink = page.evaluate(
        "() => { const p = document.createElement('p'); p.style.color = 'var(--fg)';"
        " document.body.appendChild(p); const c = getComputedStyle(p).color; p.remove();"
        " return c; }"
    )
    assert colour != ink, "the note reads as muted text"


@pytest.mark.browser
def test_field_widths_fill_the_column_and_numbers_are_short(app_clean: str, page: Page) -> None:
    _open(page, app_clean, "fetch_url")
    section = page.locator(f'{ITEM} .editor-section:has(> .section-title:text-is("Configuration"))')
    column = section.bounding_box()
    text = page.locator('input[data-field="default_user_agent"]').bounding_box()
    number = page.locator('input[data-field="redirect_cap"]').bounding_box()
    assert column is not None and text is not None and number is not None
    assert text["width"] > column["width"] * 0.8, (text, column)
    assert number["width"] < 300, number


# ── show_if (AC6) ────────────────────────────────────────────────────────────


@pytest.mark.browser
def test_a_show_if_hidden_row_is_still_submitted(app_clean: str, page: Page) -> None:
    import httpx
    from browser._credential_registry import auth_headers_for

    _open(page, app_clean, "web_search")
    backend = page.locator('[data-field="search_backend"]')
    backend.select_option("brave")
    page.locator('input[data-field="brave_api_key"]').fill("BSA-hidden-but-kept-9876")
    backend.select_option("tavily")
    expect(
        page.locator(f'{ITEM} .tools-editor-field[data-field-name="brave_api_key"]')
    ).to_be_hidden()
    page.locator('[data-testid="save-tool-btn"]').click()
    expect(page.locator('[data-testid="save-tool-btn"]')).to_be_disabled(timeout=5000)
    stored = httpx.get(
        f"{app_clean}/api/tools/configs/web_search",
        timeout=5.0,
        headers=auth_headers_for(app_clean),
    ).json()["config"]
    assert stored["search_backend"] == "tavily"
    assert stored["brave_api_key"].endswith("9876"), stored["brave_api_key"]
