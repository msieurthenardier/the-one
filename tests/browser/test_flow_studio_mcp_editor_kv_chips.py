# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""MCP source editor browser tests: chip lists and the key/value tables.

Split from test_flow_studio_mcp_editor.py (squawk 0271); shared helpers live in
browser/_mcp_editor.py."""

from __future__ import annotations

import json

import pytest
from browser import _nav
from browser._mcp_editor import (
    _expect_clean,
    _get_source,
    _http_source,
    _kv_add,
    _kv_key,
    _kv_row_by_key,
    _kv_rows,
    _kv_sens_label,
    _kv_title,
    _kv_val,
    _list_sources,
    _open_source,
    _save_edit,
    _seed_mcp_source,
)
from playwright.sync_api import Page, expect


def _seed_kv_shape(app_clean: str) -> str:
    return _seed_mcp_source(
        app_clean,
        _http_source(
            "kv-shape", headers={"X-Plain": "v"}, secrets={"X-Api-Key": "abc12345678-4567"}
        ),
    )


def _add_chip(page: Page, field: str, text: str) -> None:
    box = page.locator(f'[data-field="{field}"].chip-list-editor .chip-list-input')
    box.fill(text)
    box.press("Enter")


def _kv_sens_input(row):
    return row.locator("td").nth(2).locator("input[type=checkbox]")


def _kv_remove(row):
    return row.locator("td").nth(3).locator("button")


def _case_rename_no_retype(page: Page) -> None:
    _kv_key(_kv_row_by_key(page, "X-Sec")).fill("X-Renamed")


def _case_new_sensitive_empty(page: Page) -> None:
    _kv_add(page, "X-Empty", "", sensitive=True)


def _case_blank_row(page: Page) -> None:
    page.locator('[data-testid="kv-add-row-btn"]').click()
    _kv_val(_kv_row_by_key(page, "X-Plain")).fill("changed")


def _case_spaced_key(page: Page) -> None:
    _kv_add(page, "  X-Spaced  ", "v")


def _case_mixed_order(page: Page) -> None:
    _kv_add(page, "X-S2", "second-secret-4321", sensitive=True)
    _kv_add(page, "X-P2", "plain2")


# ── F9 L1: KV-table polish (empty-state thead hide + studio toggle/trash) ──


@pytest.mark.browser
def test_kv_thead_hidden_when_table_is_empty(app_clean: str, page: Page) -> None:
    """Empty kv-table → the column headers (thead) are hidden.

    Newly-created streamable-http source with no headers/secrets should land in
    edit-mode with zero kv-rows; the column headers (Key/Value/Sensitive) must
    NOT be visible in this empty state.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "empty-kv",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    rows = _kv_rows(page)
    expect(rows).to_have_count(0)
    thead = page.get_by_test_id("mcp-kv-table").locator("thead")
    expect(thead).to_be_hidden()


@pytest.mark.browser
def test_kv_thead_reveals_when_first_row_added(app_clean: str, page: Page) -> None:
    """Adding the first kv row reveals the thead; removing it hides it again."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "reveal-thead",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    thead = page.get_by_test_id("mcp-kv-table").locator("thead")
    expect(thead).to_be_hidden()

    # Add a row → the thead shows.
    page.locator('[data-testid="kv-add-row-btn"]').click()
    expect(_kv_rows(page)).to_have_count(1)
    expect(thead).to_be_visible()

    # Remove the row → the thead hides again.
    _kv_remove(_kv_rows(page).first).click()
    expect(_kv_rows(page)).to_have_count(0)
    expect(thead).to_be_hidden()


@pytest.mark.browser
def test_kv_sensitive_header_name_and_toggletip(app_clean: str, page: Page) -> None:
    """A13: the Sensitive column header is named exactly "Sensitive" (its info button's
    name and description do not join it); the info button is a press-only toggletip."""
    sid = _seed_kv_shape(app_clean)
    _open_source(page, app_clean, sid)
    table = page.get_by_test_id("mcp-kv-table")
    header = table.get_by_role("columnheader", name="Sensitive", exact=True)
    expect(header).to_be_visible()
    info = header.get_by_role("button", name="More information about Sensitive")
    expect(info).to_be_visible()
    assert info.get_attribute("title") is None
    expect(info).to_have_attribute("aria-expanded", "false")
    info.click()
    expect(info).to_have_attribute("aria-expanded", "true")
    expect(header.locator(".ui-info-bubble")).to_contain_text("stored encrypted")
    page.keyboard.press("Escape")
    expect(info).to_have_attribute("aria-expanded", "false")


@pytest.mark.browser
def test_kv_row_controls_name_their_row(app_clean: str, page: Page) -> None:
    """A11: the table is named like its section; each row's controls name the row; the
    switch is role=switch; the eye has aria-pressed; the remove button names the key."""
    sid = _seed_kv_shape(app_clean)
    _open_source(page, app_clean, sid)
    table = page.get_by_test_id("mcp-kv-table")
    expect(table).to_have_accessible_name("Headers")
    expect(_kv_title(page)).to_have_text("Headers")
    expect(page.get_by_label("Key, row 1", exact=True)).to_have_value("X-Plain")
    expect(page.get_by_label("Value, row 2", exact=True)).to_have_value("***...4567")
    switch = page.get_by_role("switch", name="Sensitive, row 2")
    expect(switch).to_be_checked()
    expect(page.get_by_role("switch", name="Sensitive, row 1")).not_to_be_checked()
    expect(page.get_by_role("button", name="Remove X-Plain")).to_be_visible()
    expect(page.get_by_role("button", name="Remove X-Api-Key")).to_be_visible()

    # A stored secret has no eye and carries the hint; a new sensitive row has the eye.
    # An empty sensitive row is a plain new secret cell, so its eye is the normal one.
    page.locator('[data-testid="kv-add-row-btn"]').click()
    page.get_by_label("Key, row 3", exact=True).fill("X-New")
    page.get_by_role("switch", name="Sensitive, row 3").check(force=True)
    eye = page.get_by_role("button", name="Show value, row 3")
    expect(eye).to_have_attribute("aria-pressed", "false")
    eye.click()
    expect(page.get_by_role("button", name="Hide value, row 3")).to_have_attribute(
        "aria-pressed", "true"
    )
    expect(page.get_by_role("button", name="Remove X-New")).to_be_visible()
    # An empty key names the row by number.
    page.locator('[data-testid="kv-add-row-btn"]').click()
    expect(page.get_by_role("button", name="Remove row 4")).to_be_visible()


@pytest.mark.browser
def test_kv_stored_row_hint_and_rename_hint(app_clean: str, page: Page) -> None:
    """B5 and defect 15 in the editor: a stored row says the secret is stored; renaming
    its key clears the value and asks for it again."""
    sid = _seed_kv_shape(app_clean)
    _open_source(page, app_clean, sid)
    row = _kv_row_by_key(page, "X-Api-Key")
    expect(_kv_val(row)).to_have_value("***...4567")
    hint = row.locator(".ui-secret-hint")
    expect(hint).to_be_visible()
    expect(hint).not_to_have_text("")
    _kv_key(row).fill("X-Api-Key2")
    expect(_kv_val(row)).to_have_value("")
    expect(row.locator(".ui-secret-hint")).to_have_text(
        "Sensitive values must be re-entered when the key changes."
    )


@pytest.mark.browser
def test_kv_remove_name_follows_a_typed_key(app_clean: str, page: Page) -> None:
    """Squawk 0269: the row's remove button is named for the key as typed, not the old key."""
    sid = _seed_kv_shape(app_clean)
    _open_source(page, app_clean, sid)
    row = _kv_row_by_key(page, "X-Plain")
    expect(page.get_by_role("button", name="Remove X-Plain")).to_have_count(1)
    _kv_key(row).fill("X-Typed")
    expect(page.get_by_role("button", name="Remove X-Typed")).to_have_count(1)
    expect(page.get_by_role("button", name="Remove X-Plain")).to_have_count(0)


@pytest.mark.browser
def test_kv_rename_hint_and_eye_clear_after_save_with_empty_value(
    app_clean: str, page: Page
) -> None:
    """Squawk 0270: a saved rename with an empty value leaves no stale rename hint."""
    sid = _seed_kv_shape(app_clean)
    _open_source(page, app_clean, sid)
    row = _kv_row_by_key(page, "X-Api-Key")
    _kv_key(row).fill("X-Api-Key2")
    expect(row.locator(".ui-secret-hint")).to_have_text(
        "Sensitive values must be re-entered when the key changes."
    )
    _save_edit(page)
    expect(
        page.locator(".ui-secret-hint", has_text="Sensitive values must be re-entered")
    ).to_have_count(0)
    # An empty sensitive row is a plain new secret cell, so its eye is the normal one.


@pytest.mark.browser
def test_kv_section_has_no_sideways_scroll_at_1024(app_clean: str, page: Page) -> None:
    """A12: at the supported minimum width the section does not scroll sideways."""
    page.set_viewport_size({"width": 1024, "height": 800})
    sid = _seed_kv_shape(app_clean)
    _open_source(page, app_clean, sid)
    fits = page.evaluate(
        "() => { const s = document.querySelector('[data-testid=\"mcp-env-headers-section\"]');"
        " return s.scrollWidth <= s.clientWidth; }"
    )
    assert fits, "the env and headers section scrolls sideways at 1024"


@pytest.mark.browser
def test_kv_empty_value_says_set_per_agent_and_the_hint_is_shown(
    app_clean: str, page: Page
) -> None:
    """Sortie 09 DD3 (operator HAT): an empty value input keeps the placeholder "value"
    and the table carries one hint line (the section description) that follows the
    table type."""
    sid = _seed_kv_shape(app_clean)
    _open_source(page, app_clean, sid)
    _kv_add(page, "X-Blank", "")
    row = _kv_row_by_key(page, "X-Blank")
    expect(_kv_val(row)).to_have_attribute("placeholder", "value")
    hint = page.get_by_test_id("mcp-env-headers-hint")
    expect(hint).to_have_count(1)
    expect(hint).to_have_text("Optionally override headers in agent settings.")
    page.locator('[data-field="type"]').select_option("stdio")
    expect(hint).to_have_text("Optionally override environment variables in agent settings.")


@pytest.mark.browser
def test_kv_remove_row_uses_trash_icon(app_clean: str, page: Page) -> None:
    """Per-row remove control renders the trash icon, not a text button or close-x icon."""
    sid = _seed_kv_shape(app_clean)
    _open_source(page, app_clean, sid)
    remove_btn = page.get_by_role("button", name="Remove X-Plain")
    expect(remove_btn).to_be_visible()
    expect(remove_btn.locator("svg")).to_be_visible()


@pytest.mark.browser
def test_kv_sensitive_toggle_is_the_library_switch(app_clean: str, page: Page) -> None:
    """The per-row Sensitive control is App.ui.toggle (a role=switch); clicking its label
    flips it and the value switches between a text and a password field."""
    sid = _seed_mcp_source(app_clean, _http_source("toggle-sensitive", headers={"X-Plain": "v"}))
    _open_source(page, app_clean, sid)
    row = _kv_rows(page).first
    expect(row.locator(".ui-toggle .ui-toggle-track")).to_be_visible()
    switch = page.get_by_role("switch", name="Sensitive, row 1")
    expect(switch).not_to_be_checked()
    expect(_kv_val(row)).to_have_attribute("type", "text")
    _kv_sens_label(row).click()
    expect(switch).to_be_checked()
    expect(_kv_val(row)).to_have_attribute("type", "password")


@pytest.mark.browser
def test_headers_section_lands_above_server_and_tools_sections(app_clean: str, page: Page) -> None:
    """B1 (M31 F5 L10, reverses the F9 L1 order): for streamable-http sources the Headers
    section appears ABOVE the Server and Tools sections in DOM order."""
    sid = _seed_mcp_source(app_clean, _http_source("section-order-source"))
    _open_source(page, app_clean, sid)
    tools_title = page.locator('[data-testid="mcp-tools-section"] .section-title')
    expect(tools_title).to_have_text("Tools")
    expect(_kv_title(page)).to_have_text("Headers")
    same_order = page.evaluate(
        "() => {"
        "  var t = document.querySelector('[data-testid=\"mcp-tools-section\"] .section-title');"
        "  var h = document.querySelector('[data-testid=\"mcp-env-headers-section\"] .section-title');"
        "  if (!t || !h) return false;"
        "  return !!(h.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING);"
        "}"
    )
    assert same_order, "Headers section must come before the Tools section in DOM order"


@pytest.mark.browser
def test_kv_type_switch_moves_the_rows(app_clean: str, page: Page) -> None:
    """A type switch with rows entered moves them under the new label (env becomes
    headers), keeping a sensitive row sensitive."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="type"]').select_option("stdio")
    _kv_add(page, "TOKEN", "abc", sensitive=True)
    page.locator('[data-field="type"]').select_option("streamable-http")
    expect(_kv_title(page)).to_have_text("Headers")
    expect(page.get_by_test_id("mcp-kv-table")).to_have_accessible_name("Headers")
    row = _kv_rows(page).first
    expect(_kv_key(row)).to_have_value("TOKEN")
    expect(_kv_val(row)).to_have_value("abc")
    expect(_kv_sens_input(row)).to_be_checked()
    expect(_kv_rows(page)).to_have_count(1)


@pytest.mark.browser
def test_payload_create_npx_y_args_and_writable_path(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="name"]').fill("payload-npx")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command-runtime"]').select_option("npx -y")
    _add_chip(page, "args", "@scope/pkg")
    _add_chip(page, "args", "--flag")
    _add_chip(page, "sandbox-writable-paths", "/data/work")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    cfg = _list_sources(app_clean)[0]["config"]
    assert cfg["command"] == "npx"
    assert cfg["args"] == ["-y", "@scope/pkg", "--flag"]
    assert cfg["sandbox"]["writable_paths"] == ["/data/work"]
    assert cfg["sandbox"]["network_allowed"] is True


@pytest.mark.browser
def test_payload_create_pipx_run_args_and_writable_paths(app_clean: str, page: Page) -> None:
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="name"]').fill("payload-pipx")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command-runtime"]').select_option("pipx run")
    _add_chip(page, "args", "mcp-server-time")
    _add_chip(page, "sandbox-writable-paths", "/a")
    _add_chip(page, "sandbox-writable-paths", "/b")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    cfg = _list_sources(app_clean)[0]["config"]
    assert cfg["command"] == "pipx"
    assert cfg["args"] == ["run", "mcp-server-time"]
    assert cfg["sandbox"]["writable_paths"] == ["/a", "/b"]


@pytest.mark.browser
def test_payload_edit_name_only_keeps_npx_args(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "payload-keep",
            "type": "stdio",
            "config": {
                "command": "npx",
                "args": ["-y", "pkg", "--flag"],
                "sandbox": {"network_allowed": True, "writable_paths": ["/w"]},
            },
            "secrets": {},
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="name"]').fill("payload-keep-renamed")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    src = _get_source(app_clean, sid)
    assert src["name"] == "payload-keep-renamed"
    assert src["config"]["command"] == "npx"
    assert src["config"]["args"] == ["-y", "pkg", "--flag"]
    assert src["config"]["sandbox"]["writable_paths"] == ["/w"]


@pytest.mark.browser
def test_payload_edit_adds_chip(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "payload-add",
            "type": "stdio",
            "config": {"command": "pipx", "args": ["run", "pkg"]},
            "secrets": {},
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    _add_chip(page, "args", "--verbose")
    _add_chip(page, "sandbox-writable-paths", "/scratch")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    cfg = _get_source(app_clean, sid)["config"]
    assert cfg["command"] == "pipx"
    assert cfg["args"] == ["run", "pkg", "--verbose"]
    assert cfg["sandbox"]["writable_paths"] == ["/scratch"]


@pytest.mark.browser
def test_payload_other_command_with_args(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "payload-other",
            "type": "stdio",
            "config": {"command": "bash /app/x.sh", "args": ["--one"]},
            "secrets": {},
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    expect(page.locator('[data-testid="mcp-command-custom"]')).to_have_value("bash /app/x.sh")
    _add_chip(page, "args", "--two")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    cfg = _get_source(app_clean, sid)["config"]
    assert cfg["command"] == "bash /app/x.sh"
    assert cfg["args"] == ["--one", "--two"]


@pytest.mark.browser
def test_stored_network_off_cancel_returns_it_to_off(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "net-off",
            "type": "stdio",
            "config": {"command": "x", "sandbox": {"network_allowed": False, "writable_paths": []}},
            "secrets": {},
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    net = page.locator('[data-field="sandbox-network-allowed"]')
    expect(net).not_to_be_checked()
    page.locator('label[for="mf-sandbox-network-allowed"]').click()
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).not_to_be_disabled()
    page.locator('[data-testid="cancel-mcp-source-btn"]').click()
    expect(net).not_to_be_checked()
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_disabled()


# Defect 7 (DD9): a chip edit after Cancel was not tracked (the re-mounted lists had
# a no-op onChange).


@pytest.mark.browser
@pytest.mark.parametrize("field", ["args", "sandbox-writable-paths"])
def test_chip_edit_after_cancel_is_tracked_as_dirty(app_clean: str, page: Page, field: str) -> None:
    config: dict = {"command": "uvx", "args": ["a", "b"]}
    if field == "sandbox-writable-paths":
        config = {
            "command": "uvx",
            "sandbox": {"network_allowed": True, "writable_paths": ["/a", "/b"]},
        }
    sid = _seed_mcp_source(
        app_clean, {"name": "defect-7", "type": "stdio", "config": config, "secrets": {}}
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    save = page.locator('[data-testid="save-mcp-source-btn"]')
    expect(save).to_be_visible(timeout=8000)
    chips = page.locator(f'[data-field="{field}"].chip-list-editor .chip')
    expect(chips).to_have_count(2)

    chips.nth(0).locator("button").click()
    expect(save).not_to_be_disabled()
    page.locator('[data-testid="cancel-mcp-source-btn"]').click()
    expect(save).to_be_disabled()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("")
    expect(chips).to_have_count(2)

    chips.nth(1).locator("button").click()
    expect(save).not_to_be_disabled()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    _add_chip(page, field, "/c")
    expect(chips).to_have_count(2)


@pytest.mark.browser
def test_payload_1_sensitive_header_created_through_the_ui(app_clean: str, page: Page) -> None:
    """A sensitive header typed in the create form lands in `secrets` (masked on GET),
    never in `config.headers`; a name-only edit after a reload keeps it."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="name"]').fill("payload-1")
    page.locator('[data-field="type"]').select_option("streamable-http")
    page.locator('[data-field="url"]').fill("http://127.0.0.1:9/mcp")
    _kv_add(page, "Authorization", "Bearer-aaaa-1111", sensitive=True)
    _kv_add(page, "X-Plain", "plain-value")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    sid = sources[0]["id"]
    src = _get_source(app_clean, sid)
    assert src["secrets"] == {"Authorization": "***...1111"}
    assert src["config"]["headers"] == {"X-Plain": "plain-value"}

    # Reload, change only the name, Save: the secret is still stored, masked.
    _open_source(page, app_clean, sid)
    page.locator('[data-field="name"]').fill("payload-1-renamed")
    _save_edit(page)
    src = _get_source(app_clean, sid)
    assert src["name"] == "payload-1-renamed"
    assert src["secrets"] == {"Authorization": "***...1111"}
    assert "Authorization" not in src["config"]["headers"]


@pytest.mark.browser
def test_payload_2_reload_shows_the_stored_secret_as_sensitive(app_clean: str, page: Page) -> None:
    """After a reload the stored secret row is sensitive and carries the GET mask."""
    sid = _seed_mcp_source(
        app_clean, _http_source("payload-2", secrets={"X-Api-Key": "abcd-1234-wxyz"})
    )
    _open_source(page, app_clean, sid)
    row = _kv_row_by_key(page, "X-Api-Key")
    expect(_kv_val(row)).to_have_value("***...wxyz")
    expect(_kv_sens_input(row)).to_be_checked()
    expect(_kv_val(row)).to_have_attribute("type", "password")


@pytest.mark.browser
def test_payload_3_name_only_edit_keeps_the_secret(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(
        app_clean, _http_source("payload-3", secrets={"Authorization": "Bearer-keep-5555"})
    )
    _open_source(page, app_clean, sid)
    page.locator('[data-field="name"]').fill("payload-3-b")
    _save_edit(page)
    src = _get_source(app_clean, sid)
    assert src["secrets"] == {"Authorization": "***...5555"}
    assert src["config"]["headers"] == {}


@pytest.mark.browser
def test_payload_4_retyped_value_replaces_the_secret(app_clean: str, page: Page) -> None:
    sid = _seed_mcp_source(
        app_clean,
        _http_source(
            "payload-4",
            secrets={"Authorization": "Bearer-old-aaaa", "X-Api-Key": "other-secret-bbbb"},
        ),
    )
    _open_source(page, app_clean, sid)
    _kv_val(_kv_row_by_key(page, "Authorization")).fill("Bearer-new-cccc")
    _save_edit(page)
    src = _get_source(app_clean, sid)
    assert src["secrets"]["Authorization"] == "***...cccc"
    assert src["secrets"]["X-Api-Key"] == "***...bbbb"


@pytest.mark.browser
def test_payload_5_unticking_sensitive_clears_the_value(app_clean: str, page: Page) -> None:
    """Unticking Sensitive on a stored row drops it from `secrets`; the plaintext value
    is the cleared '' and never mask text."""
    sid = _seed_mcp_source(
        app_clean, _http_source("payload-5", secrets={"X-Token": "tok-secret-7777"})
    )
    _open_source(page, app_clean, sid)
    row = _kv_row_by_key(page, "X-Token")
    _kv_sens_label(row).click()
    expect(_kv_val(row)).to_have_value("")
    _save_edit(page)
    src = _get_source(app_clean, sid)
    assert "X-Token" not in src["secrets"]
    assert src["config"]["headers"]["X-Token"] == ""


@pytest.mark.browser
def test_payload_6_renaming_a_stored_secret_never_carries_the_secret(
    app_clean: str, page: Page
) -> None:
    """Defect 15: a renamed stored key must not send the mask under the new name (the
    server would drop it and delete the old secret silently). The old key is omitted, so
    it is deleted; the new key is stored with the empty value the operator left."""
    sid = _seed_mcp_source(
        app_clean, _http_source("payload-6", secrets={"X-Old": "old-secret-8888"})
    )
    _open_source(page, app_clean, sid)
    row = _kv_row_by_key(page, "X-Old")
    _kv_key(row).fill("X-New")
    expect(_kv_val(row)).to_have_value("")
    _save_edit(page)
    src = _get_source(app_clean, sid)
    assert "X-Old" not in src["secrets"]
    assert src["secrets"].get("X-New") == "", src["secrets"]
    assert "__MASKED__" not in json.dumps(src)
    assert "8888" not in json.dumps(src)


@pytest.mark.browser
def test_payload_7_secret_saved_in_edit_mode_is_remasked(app_clean: str, page: Page) -> None:
    """Defect 4: a secret typed and saved in edit mode shows its stored mask afterwards, so
    unticking Sensitive clears it instead of moving the secret into plaintext."""
    sid = _seed_mcp_source(app_clean, _http_source("payload-7", headers={"X-Plain": "p"}))
    _open_source(page, app_clean, sid)
    row = _kv_add(page, "X-Token", "tokenvalue-wxyz", sensitive=True)
    _save_edit(page)
    assert _get_source(app_clean, sid)["secrets"] == {"X-Token": "***...wxyz"}
    row = _kv_row_by_key(page, "X-Token")
    expect(_kv_val(row)).to_have_value("***...wxyz")

    _kv_sens_label(row).click()
    expect(_kv_val(row)).to_have_value("")
    _save_edit(page)
    src = _get_source(app_clean, sid)
    assert "X-Token" not in src["secrets"]
    assert src["config"]["headers"]["X-Token"] == ""
    assert "wxyz" not in json.dumps(src)


@pytest.mark.browser
def test_payload_8_test_body_carries_the_sentinel_never_the_mask(
    app_clean: str, page: Page
) -> None:
    sid = _seed_mcp_source(
        app_clean,
        _http_source(
            "payload-8", headers={"X-Plain": "p"}, secrets={"Authorization": "Bearer-test-9999"}
        ),
    )
    bodies: list[str] = []

    def handle(route):
        bodies.append(route.request.post_data or "")
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "ok", "tools": [], "capabilities": {}}),
        )

    page.route(f"**/api/mcp-sources/{sid}/test/connect", handle)
    _open_source(page, app_clean, sid)
    _kv_val(_kv_row_by_key(page, "X-Plain")).fill("changed")  # a dirty form
    page.locator('[data-testid="mcp-test-connection"]').click()
    for _ in range(40):
        if bodies:
            break
        page.wait_for_timeout(100)
    assert bodies, "no test/connect request seen"
    body = json.loads(bodies[0])
    assert body["secrets"] == {"Authorization": "__MASKED__"}
    assert "***" not in bodies[0]


@pytest.mark.browser
def test_payload_9_cancel_after_save_restores_the_saved_rows(app_clean: str, page: Page) -> None:
    """H1: Cancel after a Save goes back to what was saved: the saved secret stays (masked),
    and a key deleted before the Save does not come back."""
    sid = _seed_mcp_source(
        app_clean, _http_source("payload-9", headers={"X-Gone": "g", "X-Keep": "k"})
    )
    _open_source(page, app_clean, sid)
    _kv_remove(_kv_row_by_key(page, "X-Gone")).click()
    _kv_add(page, "X-New", "newsecret-1234", sensitive=True)
    _save_edit(page)

    _kv_val(_kv_row_by_key(page, "X-Keep")).fill("kk")
    page.locator('[data-testid="cancel-mcp-source-btn"]').click()

    rows = _kv_rows(page)
    expect(rows).to_have_count(2)
    keys = sorted(_kv_key(rows.nth(i)).input_value() for i in range(2))
    assert keys == ["X-Keep", "X-New"], keys
    expect(_kv_val(_kv_row_by_key(page, "X-Keep"))).to_have_value("k")
    expect(_kv_val(_kv_row_by_key(page, "X-New"))).to_have_value("***...1234")
    _expect_clean(page)


@pytest.mark.browser
def test_payload_10_edit_during_an_in_flight_save_stays_dirty(app_clean: str, page: Page) -> None:
    """H2: a row edited while the PUT is held keeps its text and the form stays dirty."""
    sid = _seed_mcp_source(app_clean, _http_source("payload-10", headers={"X-A": "a", "X-B": "b"}))
    held: list = []

    def handle(route):
        if route.request.method == "PUT":
            held.append(route)
        else:
            route.continue_()

    page.route(f"**/api/mcp-sources/{sid}", handle)
    _open_source(page, app_clean, sid)
    _kv_val(_kv_row_by_key(page, "X-A")).fill("a1")
    page.locator('[data-testid="save-mcp-source-btn"]').click()
    for _ in range(40):
        if held:
            break
        page.wait_for_timeout(100)
    assert held, "the PUT was not issued"
    _kv_val(_kv_row_by_key(page, "X-B")).fill("b-edited-during")
    held[0].continue_()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)

    expect(_kv_val(_kv_row_by_key(page, "X-B"))).to_have_value("b-edited-during")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_enabled()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    assert _get_source(app_clean, sid)["config"]["headers"]["X-A"] == "a1"


@pytest.mark.browser
def test_edit_right_after_a_save_keeps_save_enabled(app_clean: str, page: Page) -> None:
    """Squawk 0279: an edit made the moment a held save lands (toast still showing) leaves the
    form dirty with Save and Cancel enabled; no busy flag outlives the response."""
    sid = _seed_mcp_source(app_clean, _http_source("after-save", headers={"X-A": "a"}))
    held: list = []

    def handle(route):
        if route.request.method == "PUT":
            held.append(route)
        else:
            route.continue_()

    page.route(f"**/api/mcp-sources/{sid}", handle)
    _open_source(page, app_clean, sid)
    _kv_val(_kv_row_by_key(page, "X-A")).fill("a1")
    save = page.locator('[data-testid="save-mcp-source-btn"]')
    save.click()
    for _ in range(40):
        if held:
            break
        page.wait_for_timeout(100)
    assert held, "the PUT was not issued"
    expect(save).to_be_disabled()
    held[0].continue_()
    expect(page.locator(".app-flash")).to_be_visible(timeout=8000)
    _kv_val(_kv_row_by_key(page, "X-A")).fill("a2")
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    expect(save).to_be_enabled()
    expect(page.locator('[data-testid="cancel-mcp-source-btn"]')).to_be_enabled()


@pytest.mark.browser
@pytest.mark.parametrize(
    "case",
    [
        _case_rename_no_retype,
        _case_new_sensitive_empty,
        _case_blank_row,
        _case_spaced_key,
        _case_mixed_order,
    ],
    ids=lambda f: f.__name__[6:],
)
def test_payload_11_form_is_clean_after_save(app_clean: str, page: Page, case) -> None:
    sid = _seed_mcp_source(
        app_clean,
        _http_source("payload-11", headers={"X-Plain": "p"}, secrets={"X-Sec": "sec-value-0001"}),
    )
    _open_source(page, app_clean, sid)
    case(page)
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_enabled()
    _save_edit(page)
    _expect_clean(page)


@pytest.mark.browser
def test_payload_12_cleared_stored_value_saves_empty(app_clean: str, page: Page) -> None:
    """Unchanged behaviour: clearing a stored secret's value and saving stores the key
    with an empty value; the row then shows the empty value (not stored mode)."""
    sid = _seed_mcp_source(
        app_clean, _http_source("payload-12", secrets={"X-Clear": "to-clear-2468"})
    )
    _open_source(page, app_clean, sid)
    row = _kv_row_by_key(page, "X-Clear")
    _kv_val(row).fill("")
    _save_edit(page)
    src = _get_source(app_clean, sid)
    assert src["secrets"] == {"X-Clear": ""}
    expect(_kv_val(_kv_row_by_key(page, "X-Clear"))).to_have_value("")


@pytest.mark.browser
def test_no_attribute_in_the_editor_holds_a_secret(app_clean: str, page: Page) -> None:
    """The mask tail and a typed secret travel only through .value, never an attribute."""
    sid = _seed_mcp_source(
        app_clean, _http_source("scan", secrets={"X-Stored": "stored-secret-9876"})
    )
    _open_source(page, app_clean, sid)
    scan = (
        "(needles) => { const hits = []; "
        "document.querySelectorAll('#main-content *').forEach(el => { "
        "for (const a of el.attributes) { "
        "for (const n of needles) if (a.value.includes(n)) hits.push(el.tagName + '@' + a.name); } }); "
        "return hits; }"
    )
    assert page.evaluate(scan, ["9876", "***"]) == []
    _kv_add(page, "X-Typed", "typed-secret-5432", sensitive=True)
    assert page.evaluate(scan, ["9876", "***", "5432", "typed-secret"]) == []
    _save_edit(page)
    assert page.evaluate(scan, ["9876", "***", "5432", "typed-secret"]) == []
