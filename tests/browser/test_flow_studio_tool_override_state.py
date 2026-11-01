"""Sortie 07 leg 4: the agent Tools tab stores only what the operator changes.

Inherited vs own fields (DD9), Reset, the clipped-field line and its fixes, the
unchanged-own-number exemption, a 422 landing on its field, and the Shell/Python/
download paths note (DD10).
"""

from __future__ import annotations

import json
import urllib.parse

import httpx
import pytest
from browser import _nav
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp, seed_tool_config
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

STATE = '[data-testid="tool-override-state"]'
RESET = '[data-testid="tool-override-reset"]'
CLIPPED = '[data-testid="tool-override-clipped"]'
USE_NARROWED = '[data-testid="tool-override-use-narrowed"]'
CLIPPED_RESET = '[data-testid="tool-override-clipped-reset"]'
NOTE = '[data-testid="tool-override-note"]'


def _agent_url(base: str, name: str) -> str:
    return f"{base}/api/agents/{urllib.parse.quote(name)}"


def _agent(base: str, name: str) -> dict:
    return httpx.get(_agent_url(base, name), timeout=5.0, headers=auth_headers_for(base)).json()


def _put_agent(base: str, name: str, **changes) -> None:
    cfg = _agent(base, name)
    cfg.update(changes)
    r = httpx.put(_agent_url(base, name), json=cfg, timeout=5.0, headers=auth_headers_for(base))
    assert r.status_code == 200, r.text


def _stored(base: str, name: str):
    return _agent(base, name)["tool_overrides"]


def _open_tools(page: Page, base: str, name: str) -> None:
    _nav.goto(page, base, f"agents/{_nav.seg(urllib.parse.quote(name))}/tools")
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )


def _open_panel(page: Page, tool: str):
    row = page.locator(f'details.ui-tool-row[data-tool="{tool}"]')
    tile = page.locator(".ui-group-tile", has=row)
    expect(tile).to_be_visible(timeout=8000)
    expand = tile.locator(".ui-group-tile-expand")
    if expand.get_attribute("aria-expanded") != "true":
        expand.click()
        expect(expand).to_have_attribute("aria-expanded", "true", timeout=2000)
    row.locator(".ui-tool-row-affordance").click()
    expect(row.locator("[data-tool-override-field]").first).to_be_visible(timeout=8000)
    return row


def _field(panel, name: str):
    return panel.locator(f"[data-field-name='{name}']")


def _control(panel, name: str):
    return panel.locator(f"[data-tool-override-field='{name}']")


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


def _change_description(page: Page, text: str) -> None:
    """Edit the description (a General-tab field) from wherever the editor is."""
    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-field="description"]').first.fill(text)


def _put_bodies(page: Page) -> list[dict]:
    bodies: list[dict] = []

    def on_request(r) -> None:
        if r.method == "PUT" and "/api/agents/" in r.url and r.post_data:
            bodies.append(json.loads(r.post_data))

    page.on("request", on_request)
    return bodies


def _stub_posture(page: Page, value) -> None:
    """Make GET /api/config report ``value`` as execution_sandbox (the key is dropped for
    ``None``), whatever this host's own posture is."""

    def handler(route) -> None:
        resp = route.fetch()
        body = resp.json()
        if value is None:
            body.pop("execution_sandbox", None)
        else:
            body["execution_sandbox"] = value
        route.fulfill(response=resp, json=body)

    page.route("**/api/config", handler)


# -- AC1 ---------------------------------------------------------------------


def test_open_every_panel_leaves_the_editor_clean_and_saves_nothing(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _open_tools(page, base, name)
    for tool in ("http_request", "read_file", "delete_file"):
        _open_panel(page, tool)
    save = page.locator('[data-testid="save-agent-btn"]')
    expect(save).to_be_disabled()
    expect(page.locator('[data-testid="editor-unsaved"]')).not_to_have_text("Unsaved changes")
    # Re-derive the dirty state with the panels open: an edit and its undo is clean, so
    # opening the panels moved neither the payload nor the snapshot.
    _change_description(page, "temporary")
    expect(save).to_be_enabled()
    page.locator('[data-field="description"]').first.fill(_agent(base, name)["description"])
    expect(save).to_be_disabled()
    expect(page.locator('[data-testid="editor-unsaved"]')).not_to_have_text("Unsaved changes")
    # An unrelated change saves without a tool_overrides entry anywhere.
    bodies = _put_bodies(page)
    _change_description(page, "only the description")
    _save(page)
    assert bodies and "tool_overrides" not in bodies[-1]
    assert _stored(base, name) in (None, {})


def test_own_fields_read_back_exactly_as_before(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    stored = {
        "read_file": {"path_denylist": ["/mine"]},
        "http_request": {"timeout_seconds_max": 20},
    }
    _put_agent(base, name, tool_overrides=stored)
    _open_tools(page, base, name)
    _open_panel(page, "read_file")
    _open_panel(page, "http_request")
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_disabled()
    _change_description(page, "changed")
    _save(page)
    assert _stored(base, name) == stored


# -- AC2, AC3, AC4 ------------------------------------------------------------


def test_inherited_own_and_reset(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    seed_tool_config(base, "http_request", config={"timeout_seconds_max": 60})
    _open_tools(page, base, name)
    panel = _open_panel(page, "http_request")
    field = _field(panel, "timeout_seconds_max")
    control = _control(panel, "timeout_seconds_max")
    # Inherited: the app-wide value, named in text, no Reset.
    expect(control).to_have_value("60")
    expect(control).to_have_attribute("data-tool-override-state", "inherited")
    expect(field.locator(STATE)).to_have_text("Inherited from Settings")
    expect(field.locator(RESET)).to_be_hidden()
    # Typing the same value still pins it: edited means own.
    control.fill("60")
    expect(control).to_have_attribute("data-tool-override-state", "own")
    expect(field.locator(STATE)).to_have_text("This agent's own")
    _save(page)
    assert _stored(base, name) == {"http_request": {"timeout_seconds_max": 60}}
    # Reset: inherited again, named, focus on the field, and Save removes the key.
    reset = field.locator(RESET)
    expect(reset).to_have_attribute("aria-label", "Reset Maximum timeout to inherited")
    reset.click()
    expect(control).to_have_attribute("data-tool-override-state", "inherited")
    expect(field.locator(STATE)).to_have_text("Inherited from Settings")
    expect(control).to_have_value("60")
    expect(control).to_be_focused()
    _save(page)
    assert _stored(base, name) in (None, {})


def test_a_denied_list_stores_the_additions_only(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    seed_tool_config(base, "read_file", config={"path_denylist": ["/ops"]})
    _open_tools(page, base, name)
    panel = _open_panel(page, "read_file")
    _add_chip(panel, "path_denylist", "/mine")
    expect(_control(panel, "path_denylist")).to_have_attribute("data-tool-override-state", "own")
    _save(page)
    assert _stored(base, name) == {"read_file": {"path_denylist": ["/mine"]}}
    # Removing the only added chip returns the field to inherited, and Save drops the key.
    chip = _control(panel, "path_denylist").locator(".chip", has_text="/mine")
    chip.locator(".ui-chip-remove").click()
    expect(_control(panel, "path_denylist")).to_have_attribute(
        "data-tool-override-state", "inherited"
    )
    _save(page)
    assert _stored(base, name) in (None, {})


def test_lowering_only_the_maximum_below_the_default_saves(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    seed_tool_config(base, "http_request", config={"timeout_seconds_default": 30})
    _open_tools(page, base, name)
    panel = _open_panel(page, "http_request")
    _control(panel, "timeout_seconds_max").fill("10")
    _save(page)
    assert _stored(base, name) == {"http_request": {"timeout_seconds_max": 10}}


# -- AC5 -----------------------------------------------------------------------


def _clipped_agent(base: str, name: str) -> None:
    """An override that fit, then an app-wide list that no longer holds all of it."""
    seed_tool_config(base, "http_request", config={"extra_allowed_hosts": ["a.com", "b.com"]})
    _put_agent(
        base, name, tool_overrides={"http_request": {"extra_allowed_hosts": ["a.com", "b.com"]}}
    )
    seed_tool_config(base, "http_request", config={"extra_allowed_hosts": ["a.com"]})


def test_the_clipped_line_use_narrowed_value(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _clipped_agent(base, name)
    assert [n["field"] for n in _agent(base, name)["notices"]] == ["extra_allowed_hosts"]
    _open_tools(page, base, name)
    panel = _open_panel(page, "http_request")
    line = panel.locator(CLIPPED)
    expect(line).to_have_text("Narrowed by the app-wide setting: b.com no longer applies.")
    panel.locator(USE_NARROWED).click()
    expect(line).to_have_count(0)
    chips = _control(panel, "extra_allowed_hosts").locator(".chip")
    expect(chips).to_have_count(1)
    expect(chips.first).to_contain_text("a.com")
    # The fix stays hidden after an unrelated change re-renders nothing back.
    _change_description(page, "x")
    expect(line).to_have_count(0)
    _save(page)
    assert _stored(base, name) == {"http_request": {"extra_allowed_hosts": ["a.com"]}}
    assert _agent(base, name)["notices"] == []
    expect(line).to_have_count(0)


def test_the_clipped_line_reset_and_cancel(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _clipped_agent(base, name)
    _open_tools(page, base, name)
    panel = _open_panel(page, "http_request")
    panel.locator(CLIPPED_RESET).click()
    expect(panel.locator(CLIPPED)).to_have_count(0)
    expect(_control(panel, "extra_allowed_hosts")).to_have_attribute(
        "data-tool-override-state", "inherited"
    )
    # Cancel restores the stored state, and the line with it.
    page.locator('[data-testid="cancel-agent-btn"]').click()
    panel = _open_panel(page, "http_request")
    expect(panel.locator(CLIPPED)).to_have_count(1)
    # Reset again and save: the key is gone and so is the notice.
    panel.locator(CLIPPED_RESET).click()
    _save(page)
    assert _stored(base, name) in (None, {})
    assert _agent(base, name)["notices"] == []


def test_a_no_hosts_clip_offers_only_reset(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    seed_tool_config(base, "http_request", config={"host_allowlist": ["a.com"]})
    _put_agent(base, name, tool_overrides={"http_request": {"host_allowlist": ["a.com"]}})
    seed_tool_config(base, "http_request", config={"host_allowlist": ["z.com"]})
    notices = _agent(base, name)["notices"]
    assert [(n["field"], n["effective"]) for n in notices] == [("host_allowlist", ["none.invalid"])]
    _open_tools(page, base, name)
    panel = _open_panel(page, "http_request")
    expect(panel.locator(CLIPPED)).to_contain_text("turn this tool off for this agent")
    expect(panel.locator(USE_NARROWED)).to_have_count(0)
    expect(panel.locator(CLIPPED_RESET)).to_have_count(1)
    expect(panel).not_to_contain_text("none.invalid")


# -- AC6 -----------------------------------------------------------------------


def test_an_unchanged_own_number_never_blocks_save(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    seed_tool_config(base, "http_request", config={"timeout_seconds_max": 120})
    _put_agent(base, name, tool_overrides={"http_request": {"timeout_seconds_max": 60}})
    seed_tool_config(base, "http_request", config={"timeout_seconds_max": 30})
    _open_tools(page, base, name)
    panel = _open_panel(page, "http_request")
    control = _control(panel, "timeout_seconds_max")
    expect(control).to_have_value("60")
    expect(_field(panel, "timeout_seconds_max").locator(".field-error")).to_have_count(0)
    _change_description(page, "unrelated")
    _save(page)
    assert _agent(base, name)["description"] == "unrelated"
    page.locator('[data-testid="tab-tools"]').click()
    # Editing the number to another value above the new maximum is held to the range.
    bodies = _put_bodies(page)
    control.fill("45")
    expect(_field(panel, "timeout_seconds_max").locator(".field-error")).to_contain_text(
        "Must be at most 30"
    )
    page.locator('[data-testid="save-agent-btn"]').click()
    expect(page.locator(".editor-error")).to_contain_text("Must be at most 30")
    page.wait_for_timeout(300)
    assert bodies == []


# -- AC7 -----------------------------------------------------------------------


def test_a_422_lands_on_its_field_and_selects_the_tab(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _open_tools(page, base, name)
    panel = _open_panel(page, "read_file")
    _add_chip(panel, "path_allowlist", "/opt/outside-sortie07")
    # Leave the tab: the refusal brings the operator back to the field.
    page.locator('[data-testid="tab-general"]').click()
    _save_expecting_refusal(page)
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute("aria-selected", "true")
    error = _field(panel, "path_allowlist").locator(".field-error")
    expect(error).to_contain_text("/opt/outside-sortie07")
    expect(_control(panel, "path_allowlist").locator(".chip-list-input")).to_be_focused()
    assert _stored(base, name) in (None, {})


def _save_expecting_refusal(page: Page) -> None:
    page.locator('[data-testid="save-agent-btn"]').click()


def _refuse_with(page: Page, loc: list[str], msg: str) -> None:
    def handler(route) -> None:
        if route.request.method != "PUT":
            route.continue_()
            return
        route.fulfill(
            status=422,
            json={"detail": [{"type": "tool_override", "loc": loc, "msg": msg}]},
        )

    page.route("**/api/agents/*", handler)


def test_a_422_on_a_panel_never_opened_opens_it(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _open_tools(page, base, name)
    _refuse_with(page, ["tool_overrides", "grep", "allow_binary_files"], "Binary files are off.")
    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-field="description"]').first.fill("x")
    _save_expecting_refusal(page)
    expect(page.locator('[data-testid="tab-tools"]')).to_have_attribute("aria-selected", "true")
    row = page.locator('details.ui-tool-row[data-tool="grep"]')
    expect(row).to_have_attribute("open", "")
    expect(row).to_contain_text("Binary files are off.")


def test_a_422_on_an_unknown_tool_goes_in_the_header(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _open_tools(page, base, name)
    _refuse_with(page, ["tool_overrides", "no_such_tool"], "No tool is named no_such_tool.")
    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-field="description"]').first.fill("x")
    _save_expecting_refusal(page)
    expect(page.locator(".editor-error")).to_contain_text("No tool is named no_such_tool.")
    expect(page.locator('[data-testid="tab-general"]')).to_have_attribute("aria-selected", "true")


# -- AC9 -----------------------------------------------------------------------

_BWRAP = "run in an empty sandbox"
_PASSTHROUGH = "aren't limited by any paths"


@pytest.mark.parametrize(
    ("posture", "words"), [("bubblewrap", _BWRAP), ("passthrough", _PASSTHROUGH)]
)
def test_the_paths_note_follows_the_posture(
    app_with_agent: SeededApp, page: Page, posture: str, words: str
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _stub_posture(page, posture)
    _open_tools(page, base, name)
    panel = _open_panel(page, "read_file")
    for field in ("path_allowlist", "path_denylist"):
        expect(_field(panel, field).locator(NOTE)).to_contain_text(words)
    # Not on a field that is not a paths field.
    expect(_field(panel, "read_size_cap_bytes").locator(NOTE)).to_have_count(0)


def test_the_paths_note_needs_an_enabled_tool(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _put_agent(base, name, enabled_tools=["read_file", "shell"], disabled_tools=[])
    _stub_posture(page, "bubblewrap")
    _open_tools(page, base, name)
    panel = _open_panel(page, "read_file")
    expect(panel.locator(NOTE)).to_have_count(2)
    # Switching the one tool off for this agent withdraws the note at once.
    tile = page.locator(".ui-group-tile", has=page.locator('details[data-tool="shell"]'))
    expand = tile.locator(".ui-group-tile-expand")
    if expand.get_attribute("aria-expanded") != "true":
        expand.click()
    page.locator('input[data-tool="shell"]').uncheck()
    expect(panel.locator(NOTE)).to_have_count(0)
    page.locator('input[data-tool="shell"]').check()
    expect(panel.locator(NOTE)).to_have_count(2)


def test_the_paths_note_needs_the_tool_enabled_app_wide(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _put_agent(base, name, enabled_tools=["read_file", "shell"], disabled_tools=[])
    seed_tool_config(base, "shell", enabled=False)
    _stub_posture(page, "bubblewrap")
    _open_tools(page, base, name)
    panel = _open_panel(page, "read_file")
    expect(panel.locator(NOTE)).to_have_count(0)


@pytest.mark.parametrize("posture", [None, "something-else"])
def test_no_note_for_an_unknown_posture(
    app_with_agent: SeededApp, page: Page, posture: str | None
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _stub_posture(page, posture)
    _open_tools(page, base, name)
    panel = _open_panel(page, "read_file")
    expect(panel.locator(NOTE)).to_have_count(0)


# -- Flight review fix pass ----------------------------------------------------


def test_a_cleared_allow_list_is_inherited_at_once(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _put_agent(base, name, tool_overrides={"read_file": {"path_allowlist": ["~/docs"]}})
    _open_tools(page, base, name)
    panel = _open_panel(page, "read_file")
    control = _control(panel, "path_allowlist")
    expect(control).to_have_attribute("data-tool-override-state", "own")
    expect(control.locator(".chip")).to_have_count(1)
    control.locator(".chip", has_text="~/docs").locator(".ui-chip-remove").click()
    # Inherited at once: the app-wide list is shown, the state says so, no Reset, and the
    # change is announced with focus on the chip input.
    expect(control).to_have_attribute("data-tool-override-state", "inherited")
    expect(page.locator('[data-testid="tool-override-live"]')).to_have_text(
        "Using the inherited list"
    )
    expect(control.locator(".chip-list-input")).to_be_focused()
    expect(_field(panel, "path_allowlist").locator(STATE)).to_have_text("Inherited from Settings")
    expect(_field(panel, "path_allowlist").locator(RESET)).to_be_hidden()
    expect(control.locator(".chip")).to_have_count(1)
    expect(control.locator(".chip")).not_to_contain_text("docs")
    # The stored map had an own value, so the editor is dirty and Save removes it.
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_enabled()
    _save(page)
    assert _stored(base, name) in (None, {})


def _number_setup(app_with_agent: SeededApp, page: Page):
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    seed_tool_config(base, "http_request", config={"timeout_seconds_max": 60})
    _put_agent(base, name, tool_overrides={"http_request": {"timeout_seconds_max": 20}})
    _open_tools(page, base, name)
    panel = _open_panel(page, "http_request")
    return base, name, panel, _control(panel, "timeout_seconds_max")


def _backspace_to_empty(control) -> None:
    control.click()
    control.press("End")
    control.press("Backspace")
    control.press("Backspace")


def test_a_cleared_number_stays_empty_while_typing_then_retyped_is_own(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, name, panel, control = _number_setup(app_with_agent, page)
    expect(control).to_have_value("20")
    _backspace_to_empty(control)
    # Inherited, but the text is left alone: nothing is written back mid-typing.
    expect(control).to_have_attribute("data-tool-override-state", "inherited")
    expect(control).to_have_value("")
    expect(_field(panel, "timeout_seconds_max").locator(STATE)).to_have_text(
        "Inherited from Settings"
    )
    expect(_field(panel, "timeout_seconds_max").locator(RESET)).to_be_hidden()
    control.press("3")
    control.press("0")
    expect(control).to_have_value("30")
    expect(control).to_have_attribute("data-tool-override-state", "own")
    expect(_field(panel, "timeout_seconds_max").locator(RESET)).to_be_visible()
    _save(page)
    assert _stored(base, name) == {"http_request": {"timeout_seconds_max": 30}}


def test_an_emptied_number_takes_the_inherited_value_on_blur(
    app_with_agent: SeededApp, page: Page
) -> None:
    base, name, panel, control = _number_setup(app_with_agent, page)
    _backspace_to_empty(control)
    expect(control).to_have_value("")
    control.blur()
    expect(control).to_have_value("60")
    expect(control).to_have_attribute("data-tool-override-state", "inherited")
    expect(page.locator('[data-testid="tool-override-live"]')).to_have_text(
        "Using the inherited value, 60"
    )
    expect(_field(panel, "timeout_seconds_max").locator(RESET)).to_be_hidden()
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_enabled()
    _save(page)
    assert _stored(base, name) in (None, {})


def test_a_number_error_keeps_the_described_by_ids(app_with_agent: SeededApp, page: Page) -> None:
    _base, _name, panel, control = _number_setup(app_with_agent, page)
    control.fill("2.5")
    expect(_field(panel, "timeout_seconds_max").locator(".field-error")).to_be_visible()
    texts = [t for _id, t in _described(control)]
    assert all(t is not None for t in texts)
    assert any("own" in t or "Inherited" in t for t in texts), texts


def test_clearing_an_inherited_field_stays_clean(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    seed_tool_config(base, "http_request", config={"timeout_seconds_max": 60})
    _open_tools(page, base, name)
    panel = _open_panel(page, "http_request")
    control = _control(panel, "timeout_seconds_max")
    control.fill("")
    expect(control).to_have_attribute("data-tool-override-state", "inherited")
    expect(page.locator('[data-testid="save-agent-btn"]')).to_be_disabled()


_DESCRIBED = """(el) => (el.getAttribute('aria-describedby') || '').split(/\\s+/).filter(Boolean)
  .map((id) => { const n = document.getElementById(id); return [id, n ? n.textContent : null]; })"""


def _described(control) -> list[list]:
    """The texts a chip list's input (or a plain control) is described by."""
    inner = control.locator(".chip-list-input")
    return (inner if inner.count() else control).evaluate(_DESCRIBED)


def test_the_note_and_clipped_line_are_in_aria_describedby(
    app_with_agent: SeededApp, page: Page
) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _clipped_agent(base, name)
    _stub_posture(page, "bubblewrap")
    _open_tools(page, base, name)
    panel = _open_panel(page, "http_request")
    control = _control(panel, "extra_allowed_hosts")
    texts = [t for _id, t in _described(control)]
    assert all(t is not None for t in texts), "an id points at nothing"
    assert any("Narrowed by the app-wide setting" in t for t in texts)
    assert any("Inherited" in t or "own" in t for t in texts), texts  # the hint stays
    # Using the narrowed value removes the clipped line and its id.
    panel.locator(USE_NARROWED).click()
    expect(panel.locator(CLIPPED)).to_have_count(0)
    after = _described(control)
    assert all(t is not None for _id, t in after), "an id points at nothing"
    assert not any("Narrowed by" in t for _id, t in after)
    # The paths note joins and leaves with its element.
    read = _open_panel(page, "read_file")
    paths = _control(read, "path_allowlist")
    expect(_field(read, "path_allowlist").locator(NOTE)).to_have_count(1)
    with_note = _described(paths)
    assert all(t is not None for _id, t in with_note)
    note_text = _field(read, "path_allowlist").locator(NOTE).text_content()
    assert any(t == note_text for _id, t in with_note)
    # An edit (which rewrites the hint) keeps the note described.
    _add_chip(read, "path_allowlist", "~/x")
    after_edit = _described(paths)
    assert all(t is not None for _id, t in after_edit)
    assert any(t == note_text for _id, t in after_edit)


def test_use_narrowed_and_reset_announce_politely(app_with_agent: SeededApp, page: Page) -> None:
    name = app_with_agent.agent_name
    assert name is not None
    base = app_with_agent.base_url
    _clipped_agent(base, name)
    _open_tools(page, base, name)
    panel = _open_panel(page, "http_request")
    live = page.locator('[data-testid="tool-override-live"]')
    expect(live).to_have_attribute("role", "status")
    panel.locator(USE_NARROWED).click()
    expect(live).to_have_text("Using the narrowed value")
    _field(panel, "extra_allowed_hosts").locator(RESET).click()
    expect(live).to_have_text("Reset to inherited")
    # One persistent node, reused.
    expect(live).to_have_count(1)
