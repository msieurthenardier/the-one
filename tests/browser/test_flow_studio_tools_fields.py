# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""Agent Tools tab on the shared field module (M31 F4 L05c).

``tools-tab.js`` and ``agent-form-data.js`` read the override fields through
``App.toolConfigFields`` (agent mode). Covers what moved with it:

- the hidden-override carry-over (a stored override on a setting the tool's
  ``config_fields`` hides survives a Save that opened the tool's panel);
- number validation (a field error as you type, and a refused Save);
- squawk 0223's rule, again, on the new module;
- A8 and A10 on the tab (humanised custom labels, inline boolean labels).
"""

from __future__ import annotations

import urllib.parse

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser


def _agent_url(base: str, name: str) -> str:
    return f"{base}/api/agents/{urllib.parse.quote(name)}"


def _put_overrides(base: str, name: str, overrides: dict | None) -> str:
    headers = auth_headers_for(base)
    url = _agent_url(base, name)
    cfg = httpx.get(url, timeout=5.0, headers=headers).json()
    cfg["tool_overrides"] = overrides
    r = httpx.put(url, json=cfg, timeout=5.0, headers=headers)
    assert r.status_code == 200, r.text
    return url


def _stored(base: str, url: str) -> dict:
    return httpx.get(url, timeout=5.0, headers=auth_headers_for(base)).json()["tool_overrides"]


def _open_tools(page: Page, base: str, name: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(urllib.parse.quote(name))}/tools")
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


def _open_panel(page: Page, category: str, tool: str):
    tile = page.locator(f'.ui-group-tile[data-category="{category}"]')
    expect(tile).to_be_visible(timeout=8000)
    expand = tile.locator(".ui-group-tile-expand")
    if expand.get_attribute("aria-expanded") != "true":
        expand.click()
        expect(expand).to_have_attribute("aria-expanded", "true", timeout=2000)
    panel = page.locator(f'details.ui-tool-row[data-tool="{tool}"]')
    panel.locator(".ui-tool-row-affordance").click()
    expect(panel.locator("[data-tool-override-field]").first).to_be_visible(timeout=8000)
    return panel


def _add_chip(panel, field: str, value: str) -> None:
    chips = panel.locator(f'.chip-list-editor[data-tool-override-field="{field}"]')
    expect(chips).to_be_visible(timeout=5000)
    inp = chips.locator(".chip-list-input")
    inp.fill(value)
    inp.press("Enter")


def _save(page: Page) -> None:
    save = page.locator('[data-testid="save-agent-btn"]')
    expect(save).to_be_enabled(timeout=5000)
    save.click()
    expect(save).to_be_disabled(timeout=5000)


# ── The hidden-override carry-over ──────────────────────────────────────


def test_save_keeps_a_stored_override_on_a_setting_the_tool_hides(
    app_with_agent: SeededApp, page: Page
) -> None:
    """delete_file never reads file contents, so its panel does not show
    read_size_cap_bytes. A stored override on it must survive a Save that opened
    the panel and changed another field."""
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    url = _put_overrides(base, name, {"delete_file": {"read_size_cap_bytes": 51200}})
    _open_tools(page, base, name)
    panel = _open_panel(page, "Filesystem", "delete_file")
    assert panel.locator('[data-tool-override-field="read_size_cap_bytes"]').count() == 0
    _add_chip(panel, "path_denylist", "/mine")
    _save(page)
    ov = _stored(base, url)
    assert ov["delete_file"]["read_size_cap_bytes"] == 51200
    assert "/mine" in ov["delete_file"]["path_denylist"]


def test_clearing_a_shown_field_still_drops_its_override(
    app_with_agent: SeededApp, page: Page
) -> None:
    """The carry-over covers only keys with NO rendered field: an override on a
    shown setting that the operator blanks is cleared, as before."""
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    url = _put_overrides(
        base,
        name,
        {
            "http_request": {"timeout_seconds_max": 60},
            "delete_file": {"read_size_cap_bytes": 51200},
        },
    )
    _open_tools(page, base, name)
    panel = _open_panel(page, "Web", "http_request")
    field = panel.locator('input[data-tool-override-field="timeout_seconds_max"]')
    field.fill("")
    _add_chip(panel, "host_denylist", "x.example")
    _save(page)
    ov = _stored(base, url)
    assert "timeout_seconds_max" not in ov["http_request"]
    assert ov["delete_file"] == {"read_size_cap_bytes": 51200}  # an unopened tool: untouched


# ── Number validation ───────────────────────────────────────────────────


def _count_agent_puts(page: Page) -> list:
    puts: list = []
    page.on(
        "request",
        lambda r: puts.append(r) if r.method == "PUT" and "/api/agents/" in r.url else None,
    )
    return puts


@pytest.mark.parametrize("typed", ["1.5", "12abc"])
def test_a_bad_number_shows_a_field_error_and_refuses_the_save(
    app_with_agent: SeededApp, page: Page, typed: str
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    url = _put_overrides(base, name, None)
    _open_tools(page, base, name)
    panel = _open_panel(page, "Web", "http_request")
    field = panel.locator('input[data-tool-override-field="timeout_seconds_max"]')
    expect(field).to_have_attribute("inputmode", "numeric")
    puts = _count_agent_puts(page)
    field.fill(typed)
    error = panel.locator("[data-field-name='timeout_seconds_max'] .field-error")
    expect(error).to_have_text("Enter a whole number.")
    expect(field).to_have_attribute("aria-invalid", "true")
    # Collapse the panel, then Save: the Save opens it and focuses the field.
    panel.locator(".ui-tool-row-affordance").click()
    expect(panel.locator(".ui-tool-row-body")).not_to_be_visible()
    page.locator('[data-testid="save-agent-btn"]').click()
    expect(page.locator(".editor-error")).to_contain_text("http_request")
    expect(page.locator(".editor-error")).to_contain_text("Enter a whole number.")
    expect(field).to_be_visible()
    expect(field).to_be_focused()
    page.wait_for_timeout(300)
    assert puts == [], "no PUT may be sent while an override is invalid"
    assert _stored(base, url) in (None, {})


@pytest.mark.parametrize(
    ("typed", "message"),
    [("-5", "Must be 1 or more"), ("0", "Must be 1 or more"), ("99999", "Must be at most")],
)
def test_an_out_of_range_number_is_refused_with_no_put(
    app_with_agent: SeededApp, page: Page, typed: str, message: str
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    url = _put_overrides(base, name, None)
    _open_tools(page, base, name)
    panel = _open_panel(page, "Web", "http_request")
    field = panel.locator('input[data-tool-override-field="timeout_seconds_max"]')
    puts = _count_agent_puts(page)
    field.fill(typed)
    error = panel.locator("[data-field-name='timeout_seconds_max'] .field-error")
    expect(error).to_contain_text(message)
    panel.locator(".ui-tool-row-affordance").click()
    expect(panel.locator(".ui-tool-row-body")).not_to_be_visible()
    page.locator('[data-testid="save-agent-btn"]').click()
    expect(page.locator(".editor-error")).to_contain_text(message)
    expect(field).to_be_focused()
    page.wait_for_timeout(300)
    assert puts == [], "no PUT may be sent while an override is out of range"
    assert _stored(base, url) in (None, {})


def test_a_valid_number_blank_and_a_fixed_value_save(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    # No app-wide seeding: the maximum is typed below the inherited default timeout, which
    # follows it (sortie 07 DD2/DD9: an inherited field is not sent).
    url = _put_overrides(base, name, None)
    _open_tools(page, base, name)
    panel = _open_panel(page, "Web", "http_request")
    field = panel.locator('input[data-tool-override-field="timeout_seconds_max"]')
    error = panel.locator("[data-field-name='timeout_seconds_max'] .field-error")
    field.fill("12abc")
    expect(error).to_have_count(1)
    field.fill("12")  # fixing it clears the error
    expect(error).to_have_count(0)
    expect(field).not_to_have_attribute("aria-invalid", "true")
    _add_chip(panel, "host_denylist", "x.example")
    _save(page)
    assert _stored(base, url)["http_request"] == {
        "timeout_seconds_max": 12,
        "host_denylist": ["x.example"],
    }
    # Blank is skipped.
    field.fill("")
    _add_chip(panel, "host_denylist", "y.example")
    _save(page)
    assert _stored(base, url)["http_request"] == {"host_denylist": ["x.example", "y.example"]}


# ── Squawk 0223 on the new module ───────────────────────────────────────


def test_a_description_only_save_sends_no_tool_overrides(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    stored = {"read_file": {"path_denylist": ["/secret"]}}
    url = _put_overrides(base, name, stored)
    _nav.goto(page, base, f"agents/{_nav.seg(urllib.parse.quote(name))}")  # General: no panel
    bodies: list[str] = []
    page.on(
        "request",
        lambda r: (
            bodies.append(r.post_data or "")
            if r.method == "PUT" and "/api/agents/" in r.url
            else None
        ),
    )
    page.locator('[data-field="description"]').first.fill("only the description")
    _save(page)
    assert len(bodies) == 1
    assert "tool_overrides" not in bodies[0]
    assert _stored(base, url) == stored


def test_opening_one_panel_keeps_the_other_tools_stored_overrides(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    url = _put_overrides(
        base,
        name,
        {"read_file": {"path_denylist": ["/secret"]}, "grep": {"allow_binary_files": False}},
    )
    _open_tools(page, base, name)
    _add_chip(_open_panel(page, "Web", "http_request"), "host_denylist", "z.example")
    _save(page)
    ov = _stored(base, url)
    assert ov["read_file"] == {"path_denylist": ["/secret"]}
    assert ov["grep"] == {"allow_binary_files": False}
    assert ov["http_request"]["host_denylist"] == ["z.example"]


# ── A8 and A10 on the tab ───────────────────────────────────────────────


def test_a_custom_preset_is_humanised_and_a_boolean_label_is_inline(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    # grep reads file contents, so its panel shows the size cap (a dropdown) and the
    # boolean. 262144 is a preset; 2097152 is not, and reads as 2MB.
    _put_overrides(base, name, {"grep": {"read_size_cap_bytes": 524288}})
    _open_tools(page, base, name)
    panel = _open_panel(page, "Filesystem", "grep")
    select = panel.locator('select[data-tool-override-field="read_size_cap_bytes"]')
    expect(select).to_have_value("524288")
    labels = select.locator("option").all_inner_texts()
    assert not any("—" in label or "Opus" in label for label in labels), labels
    assert "1MB (default)" in labels
    # The boolean: one inline label wrapping the input, no stacked field group.
    boolean = panel.locator('input[data-tool-override-field="allow_binary_files"]')
    expect(boolean).to_be_visible()
    row = boolean.locator("xpath=ancestor::*[contains(@class,'tool-override-field')][1]")
    assert row.locator("label").first.inner_text().strip() == "Allow binary files"
    assert row.locator("label input").count() == 1
    assert row.locator(".field-group").count() == 0
