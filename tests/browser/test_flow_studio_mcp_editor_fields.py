# ruff: noqa: E501  (inline JS snippets are evaluated verbatim)
"""MCP source editor browser tests: sandbox, runtime dropdown and connection fields.

Split from test_flow_studio_mcp_editor.py (squawk 0271); shared helpers live in
browser/_mcp_editor.py."""

from __future__ import annotations

import json

import pytest
from browser import _nav
from browser._mcp_editor import (
    _kv_title,
    _list_sources,
    _seed_mcp_source,
)
from playwright.sync_api import Page, expect

_DELAY_MCP_LIST_JS = """
(() => {
  const orig = window.fetch.bind(window);
  window.fetch = (u, ...a) => {
    const s = String((u && u.url) || u);
    if (/\\/api\\/mcp-sources(\\?|$)/.test(s)) {
      return new Promise((r) => setTimeout(() => r(orig(u, ...a)), 10000));
    }
    return orig(u, ...a);
  };
})();
"""


_RUNTIME_LABELS = {
    "uvx": "Python package (uvx)",
    "npx -y": "Node package (npx)",
    "pipx run": "Python package (pipx)",
    "python": "Python module or script",
    "node": "Node script",
    "bash": "Shell script",
    "__custom__": "Other command\u2026",
}


_RUNTIME_HINT_WORDS = {
    "uvx": ("Python package", "PyPI"),
    "npx -y": ("Node package", "npm"),
    "pipx run": ("pipx", "PyPI"),
    "python": ("Python module or script", "-m"),
    "node": ("Node script", ".js"),
    "bash": ("shell script", "script path"),
    "__custom__": ("exactly as you type it",),
}


def _open_create_stdio(page: Page, base: str) -> None:
    _nav.goto_settled(page, base, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="type"]').select_option("stdio")


# ── F3 L5b: Sandbox section ───────────────────────────────────────────────


@pytest.mark.browser
def test_sandbox_section_renders_for_stdio_mode(app_clean: str, page: Page) -> None:
    """Selecting stdio reveals the Sandbox section with checkbox + chip-list."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("stdio")

    section = page.locator('[data-testid="mcp-sandbox-section"]')
    expect(section).to_be_visible()
    expect(section.locator('[data-field="sandbox-network-allowed"]')).to_be_visible()
    expect(
        section.locator('[data-field="sandbox-writable-paths"].chip-list-editor')
    ).to_be_visible()


@pytest.mark.browser
def test_sandbox_section_hidden_for_streamable_http_mode(app_clean: str, page: Page) -> None:
    """Selecting streamable-http hides the Sandbox section."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("streamable-http")

    section = page.locator('[data-testid="mcp-sandbox-section"]')
    expect(section).to_be_hidden()


@pytest.mark.browser
def test_sandbox_section_visibility_toggles_on_transport_switch(app_clean: str, page: Page) -> None:
    """Switch type stdio→streamable-http→stdio; Sandbox section follows."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    section = page.locator('[data-testid="mcp-sandbox-section"]')

    page.locator('[data-field="type"]').select_option("stdio")
    expect(section).to_be_visible()

    page.locator('[data-field="type"]').select_option("streamable-http")
    expect(section).to_be_hidden()

    page.locator('[data-field="type"]').select_option("stdio")
    expect(section).to_be_visible()


@pytest.mark.browser
def test_sandbox_save_round_trip(app_clean: str, page: Page) -> None:
    """Set network_allowed=true + writable_paths=[/data,/cache]; save; API GET round-trips."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("sandbox-stdio")
    page.locator('[data-field="type"]').select_option("stdio")
    # F9 L2 vibing: dropdown defaults to `uvx`; no explicit command needed.

    # Toggle network_allowed checkbox (use check() to be explicit).
    page.locator('[data-field="sandbox-network-allowed"]').check()
    # Add two writable paths via the chip-list input.
    paths_input = page.locator(
        '[data-field="sandbox-writable-paths"].chip-list-editor .chip-list-input'
    )
    paths_input.fill("/data")
    paths_input.press("Enter")
    paths_input.fill("/cache")
    paths_input.press("Enter")

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    sandbox_cfg = sources[0]["config"].get("sandbox")
    assert sandbox_cfg is not None
    assert sandbox_cfg["network_allowed"] is True
    assert sandbox_cfg["writable_paths"] == ["/data", "/cache"]


@pytest.mark.browser
def test_sandbox_edit_round_trip_populates_fields(app_clean: str, page: Page) -> None:
    """Pre-seed source with sandbox config; open in edit; fields populated."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "sandboxed",
            "type": "stdio",
            "config": {
                "command": "x",
                "sandbox": {"network_allowed": True, "writable_paths": ["/x"]},
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    expect(page.locator('[data-field="sandbox-network-allowed"]')).to_be_checked()
    chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(chips).to_have_count(1)
    expect(chips.first).to_contain_text("/x")
    # M31 F5 L06 (A14, ledger rows 14 and 34): the library chip list. The fill is the
    # same accent-translucent; the remove x is the muted --fg-secondary, no longer accent.
    look = chips.first.evaluate(
        """(el) => { const t = (v, prop) => { const p = document.createElement('span'); p.style[prop] = 'var(' + v + ')';
            el.appendChild(p); const r = getComputedStyle(p)[prop]; p.remove(); return r; };
          return {bg: getComputedStyle(el).backgroundColor, want: t('--accent-translucent', 'backgroundColor'),
            rm: getComputedStyle(el.querySelector('.ui-chip-remove')).color, wantRm: t('--fg-secondary', 'color')}; }"""
    )
    assert look["bg"] == look["want"] and look["rm"] == look["wantRm"], look


@pytest.mark.browser
def test_sandbox_empty_defaults_for_new_stdio_source(app_clean: str, page: Page) -> None:
    """New stdio source: checkbox checked (network-on by default) + chip-list empty.

    F9 L2 vibing: the lazy-install runtimes shipped in L2 D2 (uvx, npx,
    pipx run) all REQUIRE network egress on first spawn to fetch packages
    from PyPI/npm. Defaulting `network_allowed=False` was a footgun — a
    fresh stdio source's first Refresh would fail. The form-default flips
    to `True` for new sources only; existing sources preserve their
    stored value.
    """
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("stdio")
    expect(page.locator('[data-field="sandbox-network-allowed"]')).to_be_checked()
    chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(chips).to_have_count(0)


@pytest.mark.browser
def test_sandbox_save_emits_explicit_defaults(app_clean: str, page: Page) -> None:
    """New stdio source saved without touching Sandbox section emits explicit defaults.

    F9 L2 vibing: form-default for new sources is ``network_allowed=True``
    so lazy-install runtimes can fetch their packages on first spawn.
    """
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("default-sandbox")
    page.locator('[data-field="type"]').select_option("stdio")
    # F9 L2 vibing: dropdown defaults to `uvx`; no explicit command needed.
    # Do NOT touch the Sandbox section.

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    sandbox_cfg = sources[0]["config"].get("sandbox")
    # Explicit defaults emitted (NOT omitted) — matches L1b validator
    # contract. ``network_allowed`` defaults to True for new sources
    # (F9 L2 vibing default flip); ``writable_paths`` stays empty.
    assert sandbox_cfg == {"network_allowed": True, "writable_paths": []}


@pytest.mark.browser
def test_streamable_http_source_has_no_sandbox_key(app_clean: str, page: Page) -> None:
    """streamable-http source created via the editor has no config.sandbox."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("remote-no-sandbox")
    page.locator('[data-field="type"]').select_option("streamable-http")
    page.locator('[data-field="url"]').fill("https://example.com/mcp")

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    assert "sandbox" not in sources[0]["config"]


@pytest.mark.browser
def test_sandbox_checkbox_toggle_marks_form_dirty(app_clean: str, page: Page) -> None:
    """Toggling the sandbox checkbox enables Save (form dirty)."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "edit-toggle",
            "type": "stdio",
            "config": {"command": "x", "sandbox": {"network_allowed": False, "writable_paths": []}},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    save_btn = page.locator('[data-testid="save-mcp-source-btn"]')
    expect(save_btn).to_be_visible(timeout=8000)
    expect(save_btn).to_be_disabled()

    page.locator('label[for="mf-sandbox-network-allowed"]').click()
    expect(save_btn).not_to_be_disabled()


@pytest.mark.browser
def test_sandbox_chip_add_remove_marks_form_dirty(app_clean: str, page: Page) -> None:
    """Adding/removing a sandbox writable_paths chip marks the form dirty."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "edit-chips",
            "type": "stdio",
            "config": {"command": "x", "sandbox": {"network_allowed": False, "writable_paths": []}},
            "secrets": {},
        },
    )

    # The editor mounts only after GET /api/mcp-sources resolves (deep-link
    # hydration waits on the list); under load that response can outlast a
    # fixed 8s `expect`. Wait for the app's fetch activity to go quiet first.
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    save_btn = page.locator('[data-testid="save-mcp-source-btn"]')
    expect(save_btn).to_be_visible(timeout=8000)
    expect(save_btn).to_be_disabled()

    paths_input = page.locator(
        '[data-field="sandbox-writable-paths"].chip-list-editor .chip-list-input'
    )
    paths_input.fill("/data")
    paths_input.press("Enter")
    expect(save_btn).not_to_be_disabled()

    # Remove the chip we just added — form remains dirty (different from
    # the initial empty-list snapshot? actually equal, so back to clean).
    # Re-add a different chip then remove to verify remove fires dirty.
    paths_input.fill("/extra")
    paths_input.press("Enter")
    chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(chips).to_have_count(2)
    # Remove /data (first chip)
    chips.nth(0).locator(".ui-chip-remove").click()
    # Save still enabled (form still dirty: list now has /extra not just nothing).
    expect(save_btn).not_to_be_disabled()


@pytest.mark.browser
def test_sandbox_cancel_revert_restores_state(app_clean: str, page: Page) -> None:
    """Edit existing source's sandbox state then Cancel — fields restore."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "edit-revert",
            "type": "stdio",
            "config": {
                "command": "x",
                "sandbox": {"network_allowed": True, "writable_paths": ["/x"]},
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Pre-cancel state: checkbox checked, single chip /x.
    expect(page.locator('[data-field="sandbox-network-allowed"]')).to_be_checked()
    initial_chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(initial_chips).to_have_count(1)

    # Mutate: uncheck + remove the chip.
    page.locator('label[for="mf-sandbox-network-allowed"]').click()
    initial_chips.first.locator(".ui-chip-remove").click()
    after_chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(after_chips).to_have_count(0)

    cancel_btn = page.locator('[data-testid="cancel-mcp-source-btn"]')
    expect(cancel_btn).not_to_be_disabled()
    cancel_btn.click()

    # Post-cancel: checkbox checked again, /x chip restored.
    expect(page.locator('[data-field="sandbox-network-allowed"]')).to_be_checked()
    restored_chips = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor .chip')
    expect(restored_chips).to_have_count(1)
    expect(restored_chips.first).to_contain_text("/x")


# ─── F9 L2 vibing: stdio command-runtime dropdown ───────────────────────


@pytest.mark.browser
def test_stdio_command_runtime_default_selection_is_uvx(app_clean: str, page: Page) -> None:
    """New stdio source: dropdown defaults to `uvx`, the Custom-command
    free-text field is hidden, and the helper text under args reads the
    uvx hint."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="type"]').select_option("stdio")

    runtime = page.locator('[data-testid="mcp-command-runtime"]')
    expect(runtime).to_be_visible()
    expect(runtime).to_have_value("uvx")

    # Custom row is hidden (uvx is a canonical runtime).
    custom_row = page.locator(".mcp-command-custom-row")
    expect(custom_row).to_be_hidden()

    # Helper text reflects uvx hint copy.
    hint = page.locator('[data-testid="mcp-command-hint"]')
    expect(hint).to_be_visible()
    expect(hint).to_contain_text("Runs a Python package from PyPI")
    expect(hint).to_contain_text("Put the package name in Arguments")


@pytest.mark.browser
def test_stdio_command_runtime_switching_updates_hint_and_saves(app_clean: str, page: Page) -> None:
    """Switching the dropdown selection updates the helper text and the
    saved (command, args) pair splits a 2-token runtime per option (b).

    `pipx run` saves as command='pipx', args=['run', ...userArgs] —
    NOT command='pipx run' verbatim, which would FileNotFoundError on
    spawn (the dropdown literal is not a binary)."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("pipx-source")
    page.locator('[data-field="type"]').select_option("stdio")

    page.locator('[data-field="command-runtime"]').select_option("pipx run")
    hint = page.locator('[data-testid="mcp-command-hint"]')
    expect(hint).to_contain_text("with pipx")

    # Custom row stays hidden for canonical runtimes.
    expect(page.locator(".mcp-command-custom-row")).to_be_hidden()

    # Add a user arg via the chip-list (the package name).
    args_input = page.locator('[data-field="args"].chip-list-editor .chip-list-input')
    args_input.fill("mcp-server-time")
    args_input.press("Enter")

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    cfg = sources[0]["config"]
    # Option (b): command is just `pipx`; args carry the implicit `run`
    # plus the operator's typed args.
    assert cfg["command"] == "pipx"
    assert cfg["args"] == ["run", "mcp-server-time"]


@pytest.mark.browser
def test_stdio_command_runtime_pipx_run_round_trip_collapses_to_dropdown(
    app_clean: str, page: Page
) -> None:
    """Pre-seed a source with command='pipx', args=['run', ...]; reopening
    the editor collapses that pair back into the `pipx run` dropdown
    selection, and the chip-list shows only the operator's args (the
    implicit `run` is stripped from the displayed chips)."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "pipx-roundtrip",
            "type": "stdio",
            "config": {
                "command": "pipx",
                "args": ["run", "mcp-server-time"],
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Dropdown re-collapses to the `pipx run` literal.
    expect(page.locator('[data-field="command-runtime"]')).to_have_value("pipx run")
    # Custom-command row is hidden (canonical runtime).
    expect(page.locator(".mcp-command-custom-row")).to_be_hidden()

    # Args chip-list shows ONLY the operator's package name — the
    # implicit `run` is hidden from the editable chips.
    chips = page.locator('[data-field="args"].chip-list-editor .chip')
    expect(chips).to_have_count(1)
    expect(chips.first).to_contain_text("mcp-server-time")


@pytest.mark.browser
def test_stdio_command_runtime_custom_escape_round_trips(app_clean: str, page: Page) -> None:
    """Selecting Custom… reveals the free-text input. Operator types a
    bare command; save persists it to config.command verbatim; reopen
    the source and the dropdown lands on Custom… with the saved value
    restored to the free-text field."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("custom-cmd-source")
    page.locator('[data-field="type"]').select_option("stdio")

    page.locator('[data-field="command-runtime"]').select_option("__custom__")
    custom_row = page.locator(".mcp-command-custom-row")
    expect(custom_row).to_be_visible()

    page.locator('[data-testid="mcp-command-custom"]').fill("bash /app/foo.sh")

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    assert sources[0]["config"]["command"] == "bash /app/foo.sh"
    sid = sources[0]["id"]

    # Reload the editor; dropdown should land on Custom… with the saved
    # value visible in the free-text field.
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    expect(page.locator('[data-field="command-runtime"]')).to_have_value("__custom__")
    expect(page.locator(".mcp-command-custom-row")).to_be_visible()
    expect(page.locator('[data-testid="mcp-command-custom"]')).to_have_value("bash /app/foo.sh")


@pytest.mark.browser
def test_stdio_command_runtime_round_trip_canonical_uvx(app_clean: str, page: Page) -> None:
    """Pre-seed a source with config.command='uvx' (matches one of the
    canonical runtime literals); reopening the editor lands the dropdown
    on `uvx` selected, the Custom-command row is hidden, and the
    free-text field is empty (no leakage of the canonical literal into
    Custom…)."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "uvx-canonical",
            "type": "stdio",
            "config": {"command": "uvx", "args": ["mcp-server-time"]},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    expect(page.locator('[data-field="command-runtime"]')).to_have_value("uvx")
    expect(page.locator(".mcp-command-custom-row")).to_be_hidden()
    # Free-text input stays empty when dropdown is on a canonical runtime.
    expect(page.locator('[data-testid="mcp-command-custom"]')).to_have_value("")
    # Operator's args still surface in the chip-list.
    chips = page.locator('[data-field="args"].chip-list-editor .chip')
    expect(chips).to_have_count(1)
    expect(chips.first).to_contain_text("mcp-server-time")


@pytest.mark.browser
def test_stdio_command_runtime_round_trip_custom_value(app_clean: str, page: Page) -> None:
    """Pre-seed a source with config.command='bash /app/x.sh' (no
    canonical match); reopening lands the dropdown on Custom… with the
    saved value populated in the free-text input."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "custom-bash-source",
            "type": "stdio",
            "config": {"command": "bash /app/x.sh"},
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    expect(page.locator('[data-field="command-runtime"]')).to_have_value("__custom__")
    expect(page.locator(".mcp-command-custom-row")).to_be_visible()
    expect(page.locator('[data-testid="mcp-command-custom"]')).to_have_value("bash /app/x.sh")


@pytest.mark.browser
def test_stdio_command_runtime_npx_y_save_split(app_clean: str, page: Page) -> None:
    """Selecting `npx -y` and saving splits the literal into
    command='npx', args=['-y', ...userArgs] (option (b) per leg spec).
    The implicit `-y` lives in args; the saved command is just `npx`."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    page.locator('[data-field="name"]').fill("npx-y-source")
    page.locator('[data-field="type"]').select_option("stdio")
    page.locator('[data-field="command-runtime"]').select_option("npx -y")

    # Add a user arg via the chip-list (the package name).
    args_input = page.locator('[data-field="args"].chip-list-editor .chip-list-input')
    args_input.fill("@modelcontextprotocol/server-everything")
    args_input.press("Enter")

    page.locator('[data-testid="save-mcp-source-btn"]').click()
    expect(page.locator(".editor-section.danger-zone")).to_be_visible(timeout=8000)

    sources = _list_sources(app_clean)
    assert len(sources) == 1
    cfg = sources[0]["config"]
    # Option (b): command is just `npx`; args carry the implicit `-y`
    # plus the operator's typed args.
    assert cfg["command"] == "npx"
    assert cfg["args"] == ["-y", "@modelcontextprotocol/server-everything"]


@pytest.mark.browser
def test_stdio_command_runtime_npx_y_round_trip_collapses_to_dropdown(
    app_clean: str, page: Page
) -> None:
    """Pre-seed a source with command='npx', args=['-y', ...]; reopening
    the editor collapses that pair back into the `npx -y` dropdown
    selection, and the chip-list shows only the operator's args (the
    implicit `-y` is stripped from the displayed chips)."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "npx-y-roundtrip",
            "type": "stdio",
            "config": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-everything"],
            },
            "secrets": {},
        },
    )

    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)

    # Dropdown re-collapses to the `npx -y` literal.
    expect(page.locator('[data-field="command-runtime"]')).to_have_value("npx -y")
    # Custom-command row is hidden (canonical runtime).
    expect(page.locator(".mcp-command-custom-row")).to_be_hidden()

    # Args chip-list shows ONLY the operator's package name — the
    # implicit `-y` is hidden from the editable chips.
    chips = page.locator('[data-field="args"].chip-list-editor .chip')
    expect(chips).to_have_count(1)
    expect(chips.first).to_contain_text("@modelcontextprotocol/server-everything")


@pytest.mark.browser
def test_deep_linked_editor_mounts_after_slow_list_fetch(app_clean: str, page: Page) -> None:
    """A deep-linked MCP editor mounts only after GET /api/mcp-sources resolves.

    With that list held for 10s the editor still mounts (the app waits, it does
    not drop the pending id), and goto_settled returns only once it has.
    """
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "slow-list",
            "type": "stdio",
            "config": {"command": "x", "env": {}},
            "secrets": {},
        },
    )
    page.add_init_script(_DELAY_MCP_LIST_JS)
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=1000)


@pytest.mark.browser
def test_library_editor_connection_error_plain_headline(app_clean: str, page: Page) -> None:
    """DD19: Test connection's error shows a plain headline with the raw text
    under a collapsed "Technical details"; no "✗ Error:" prefix."""
    raw_error = (
        "MCPConnectionError: MCP connect failed: cancelled during initialize "
        "(cross-task cleanup deadlock; original cause likely transport error or "
        "malformed initial response): Cancelled via cancel scope 29abb186b90"
    )
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "dd19-lib-source",
            "type": "streamable-http",
            "config": {"url": "https://example.com/mcp"},
            "secrets": {},
        },
    )
    page.route(
        f"**/api/mcp-sources/{sid}/test/connect",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "error", "error": raw_error}),
        ),
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="mcp-test-connection"]').click()

    status_panel = page.locator('[data-testid="mcp-test-status"]')
    err = status_panel.locator('[data-testid="mcp-connection-error"]')
    expect(err).to_be_visible(timeout=4000)
    expect(err).to_contain_text("Couldn't connect to this server.")
    expect(status_panel).not_to_contain_text("✗ Error")
    # WCAG 4.1.3: the status line announces the failure; the result area's block
    # carries no second (assertive) live role.
    assert err.get_attribute("role") is None
    assert err.locator("details").evaluate("el => el.open") is False
    expect(err.locator("summary")).to_have_text("Technical details")
    expect(err.locator('[data-testid="mcp-error-raw"]')).not_to_be_visible()
    err.locator("summary").click()
    assert err.locator('[data-testid="mcp-error-raw"]').inner_text() == raw_error


@pytest.mark.browser
def test_type_and_runtime_labels_are_plain(app_clean: str, page: Page) -> None:
    """B3: plain option labels, the type placeholder, and the placeholder absent from the list."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    type_sel = page.locator("#mf-type")
    expect(type_sel).to_be_visible(timeout=8000)
    labels = type_sel.evaluate(
        "el => Array.from(el.options).map(o => ({v: o.value, t: o.textContent, hidden: o.hidden}))"
    )
    placeholder = [o for o in labels if o["v"] == ""][0]
    assert placeholder["t"] == "Choose how it connects" and placeholder["hidden"] is True
    assert [o["t"] for o in labels if o["v"]] == ["Local program (stdio)", "Remote server (HTTP)"]
    # Nothing is chosen yet: the closed select shows the placeholder.
    assert type_sel.evaluate("el => el.options[el.selectedIndex].textContent") == (
        "Choose how it connects"
    )
    page.locator('[data-field="type"]').select_option("stdio")
    runtime = page.locator("#mf-command-runtime")
    got = runtime.evaluate("el => Array.from(el.options).map(o => [o.value, o.textContent])")
    assert dict(got) == _RUNTIME_LABELS


@pytest.mark.browser
@pytest.mark.parametrize("runtime", list(_RUNTIME_LABELS))
def test_runtime_hint_matches_its_option_and_is_linked(
    app_clean: str, page: Page, runtime: str
) -> None:
    """A5: the hint sits under Command, follows the option, is linked by aria-describedby,
    and carries no backtick, 'operator', 'container' or 'Fetched +'."""
    _open_create_stdio(page, app_clean)
    page.locator("#mf-command-runtime").select_option(runtime)
    hint = page.locator('[data-testid="mcp-command-hint"]')
    expect(hint).to_be_visible()
    text = hint.inner_text()
    for word in _RUNTIME_HINT_WORDS[runtime]:
        assert word in text, (runtime, text)
    for banned in ("`", "operator", "container", "Fetched +"):
        assert banned not in text, (runtime, text)
    hint_id = hint.get_attribute("id")
    assert hint_id
    assert hint_id in (page.locator("#mf-command-runtime").get_attribute("aria-describedby") or "")
    # Under Command (inside its field group), not under Arguments.
    assert hint.evaluate("el => el.parentElement.querySelector('label').textContent") == "Command"


@pytest.mark.browser
def test_connection_field_labels_and_order(app_clean: str, page: Page) -> None:
    """A3's field share: sentence case; DOM order Name, Type, Command, Custom, cwd, Arguments, URL."""
    _open_create_stdio(page, app_clean)
    ids = page.evaluate(
        "() => Array.from(document.querySelectorAll('.mcp-connection-fields .field-group'))"
        ".map(g => g.querySelector('label').textContent)"
    )
    assert ids == [
        "Name",
        "Type",
        "Command",
        "Custom command",
        "Working directory",
        "Arguments",
        "URL",
    ]
    expect(page.locator("#mf-name")).to_have_attribute("placeholder", "My MCP server")


@pytest.mark.browser
def test_create_with_no_type_shows_only_name_and_type(app_clean: str, page: Page) -> None:
    """A17: with no type chosen, the editor's form fields are Name and Type; Env and Sandbox
    are hidden; choosing a type reveals its sections, and an empty name is fine."""
    _nav.goto_settled(page, app_clean, "library/mcp/~new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    main = page.locator("#main-content")
    expect(main.get_by_role("textbox")).to_have_count(1)
    expect(main.get_by_role("textbox", name="Name")).to_have_count(1)
    expect(main.get_by_role("combobox")).to_have_count(1)
    expect(main.get_by_role("combobox", name="Type")).to_have_count(1)
    expect(page.locator('[data-testid="mcp-sandbox-section"]')).to_be_hidden()
    expect(page.locator('[data-testid="mcp-env-headers-section"]')).to_be_hidden()
    # The Connection title, the header and the create-mode Cancel remain.
    expect(main.get_by_text("Connection", exact=True)).to_be_visible()
    expect(page.locator('[data-testid="cancel-mcp-source-btn"]')).to_be_visible()

    page.locator('[data-field="type"]').select_option("stdio")
    expect(page.locator('[data-testid="mcp-sandbox-section"]')).to_be_visible()
    expect(page.locator('[data-testid="mcp-env-headers-section"]')).to_be_visible()
    page.locator('[data-field="type"]').select_option("streamable-http")
    expect(page.locator('[data-testid="mcp-sandbox-section"]')).to_be_hidden()
    expect(page.locator('[data-testid="mcp-env-headers-section"]')).to_be_visible()
    expect(_kv_title(page)).to_have_text("Headers")


@pytest.mark.browser
def test_network_switch_is_a_labelled_inline_switch_and_marks_dirty(
    app_clean: str, page: Page
) -> None:
    """A10: role=switch named 'Allow network access', label inline, a hint, Space toggles,
    and a toggle marks the form dirty."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "switch-src",
            "type": "stdio",
            "config": {"command": "x", "sandbox": {"network_allowed": True, "writable_paths": []}},
            "secrets": {},
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    save = page.locator('[data-testid="save-mcp-source-btn"]')
    expect(save).to_be_visible(timeout=8000)
    sw = page.get_by_role("switch", name="Allow network access")
    expect(sw).to_have_count(1)
    expect(sw).to_have_attribute("id", "mf-sandbox-network-allowed")
    expect(sw).to_be_checked()
    desc_id = sw.get_attribute("aria-describedby")
    assert desc_id and "uvx, npx and pipx run" in page.locator(f"#{desc_id}").inner_text()
    # The label text sits on the same row as the track (inline), not stacked above it.
    boxes = page.evaluate(
        "() => { const l = document.querySelector('label[for=\"mf-sandbox-network-allowed\"]');"
        " const t = l.querySelector('.ui-toggle-track'), x = l.querySelector('.ui-choice-text');"
        " const a = t.getBoundingClientRect(), b = x.getBoundingClientRect();"
        " return {ta: a.top, tb: a.bottom, xa: b.top, xb: b.bottom}; }"
    )
    assert boxes["xa"] < boxes["tb"] and boxes["xb"] > boxes["ta"], boxes
    expect(save).to_be_disabled()
    sw.focus()
    page.keyboard.press("Space")
    expect(sw).not_to_be_checked()
    expect(save).not_to_be_disabled()
    expect(page.locator('[data-testid="editor-unsaved"]')).to_have_text("Unsaved changes")
    page.keyboard.press("Space")
    expect(sw).to_be_checked()
    expect(save).to_be_disabled()


@pytest.mark.browser
def test_long_chip_values_use_the_middle_ellipsis(app_clean: str, page: Page) -> None:
    """B4: a 90-character argument and an 87-character path keep their full value in the
    accessible name and on hover, and show a shortened middle."""
    long_arg = "a" * 40 + "-middle-" + "z" * 42
    long_path = "/" + "p" * 40 + "/" + "q" * 45
    assert len(long_arg) == 90 and len(long_path) == 87
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "long-chips",
            "type": "stdio",
            "config": {
                "command": "uvx",
                "args": [long_arg],
                "sandbox": {"network_allowed": True, "writable_paths": [long_path]},
            },
            "secrets": {},
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    for field, full in (("args", long_arg), ("sandbox-writable-paths", long_path)):
        chip = page.locator(f'[data-field="{field}"].chip-list-editor .chip')
        expect(chip).to_have_count(1)
        assert chip.get_attribute("data-value") == full
        assert chip.get_attribute("title") == full
        shown = chip.locator(".ui-chip-text").inner_text()
        assert "\u2026" in shown and len(shown) < len(full)
        expect(chip.get_by_role("button", name=f"Remove {full}")).to_have_count(1)


@pytest.mark.browser
def test_chip_input_keys_still_work_in_both_lists(app_clean: str, page: Page) -> None:
    """DD10: Enter and comma commit, a pasted comma list splits, Backspace removes the last
    chip; the select keeps its native typeahead."""
    _open_create_stdio(page, app_clean)
    save = page.locator('[data-testid="save-mcp-source-btn"]')
    args = page.locator('[data-field="args"].chip-list-editor')
    box = args.locator(".chip-list-input")
    box.fill("one")
    box.press("Enter")
    box.fill("two")
    box.press(",")
    expect(args.locator(".chip")).to_have_count(2)
    box.press("Backspace")
    expect(args.locator(".chip")).to_have_count(1)
    expect(save).not_to_be_disabled()
    paths = page.locator('[data-field="sandbox-writable-paths"].chip-list-editor')
    pbox = paths.locator(".chip-list-input")
    pbox.focus()
    pbox.evaluate(
        "el => { const d = new DataTransfer(); d.setData('text', '/a,/b');"
        " el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: d, bubbles: true,"
        " cancelable: true})); }"
    )
    expect(paths.locator(".chip")).to_have_count(2)
    # Native typeahead on the runtime select: typing "N" lands on the first N option.
    sel = page.locator("#mf-command-runtime")
    sel.focus()
    page.keyboard.type("Shell")
    expect(sel).to_have_value("bash")


@pytest.mark.browser
def test_switching_type_keeps_args_and_cancel_reverts_visibility(
    app_clean: str, page: Page
) -> None:
    """Edge: args survive a type switch; Cancel restores the stored type's rows."""
    sid = _seed_mcp_source(
        app_clean,
        {
            "name": "switcher",
            "type": "stdio",
            "config": {"command": "uvx", "args": ["pkg"]},
            "secrets": {},
        },
    )
    _nav.goto_settled(page, app_clean, f"library/mcp/{_nav.seg(sid)}")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-field="type"]').select_option("streamable-http")
    expect(page.locator("#mf-url")).to_be_visible()
    expect(page.locator("#mf-args")).to_be_hidden()
    expect(page.locator('[data-testid="mcp-sandbox-section"]')).to_be_hidden()
    page.locator('[data-field="type"]').select_option("stdio")
    expect(page.locator('[data-field="args"].chip-list-editor .chip')).to_have_count(1)
    page.locator('[data-field="type"]').select_option("streamable-http")
    page.locator('[data-testid="cancel-mcp-source-btn"]').click()
    expect(page.locator('[data-field="type"]')).to_have_value("stdio")
    expect(page.locator("#mf-url")).to_be_hidden()
    expect(page.locator("#mf-args")).to_be_visible()
    expect(page.locator('[data-testid="mcp-sandbox-section"]')).to_be_visible()
    expect(_kv_title(page)).to_have_text("Environment variables")
