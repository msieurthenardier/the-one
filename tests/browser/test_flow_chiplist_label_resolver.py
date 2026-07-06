"""Runtime DOM guard: chip-list ``label[for]`` resolves to a real control.

M17 F6 L3 (System / Admin re-skin — shared-helpers-and-chiplist leg).

The shared ``renderChipListEditor`` mounts a chip-list as a ``<div
class="chip-list-editor">`` whose only focusable, *labelable* element is the
inner ``<input class="chip-list-input">``. Before this leg a ``<label for="X">``
targeted the WRAPPER (a ``<div>``, which is NOT a labelable element) — and in
the mcp-server-editor the label targeted a PLACEHOLDER ``<div id="X">`` that
``mountChipListEditors`` replaces via ``outerHTML=`` (stripping the id), so the
association dangled at RUNTIME even though it looked wired in source.

The static ``test_ui_guards.py`` label-association guard scans source and
provably CANNOT catch a mount-time id strip. This browser guard mounts the two
chip-list-bearing editors and asserts, via the DOM's own ``HTMLLabelElement
.control`` resolver (which returns null for a non-labelable / missing target),
that every chip-list ``label[for]`` resolves to the real ``.chip-list-input``.

Covers both cross-area consumers of the fix:
- admin tools-editor (``fetch_url`` — WebConfig array fields render via
  ``renderField`` → ``renderChipListEditor`` with ``controlId=tef-{name}``);
- studio mcp-server-editor (``mf-args`` + ``mf-sandbox-writable-paths`` — the
  placeholder-div repoint site, ``controlId=mf-{name}``).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

# JS run in the page: for each expected id, resolve the <label for=id> through
# the DOM's HTMLLabelElement.control property (null when the target is missing
# or not a labelable element) and report what getElementById(id) points at.
_RESOLVE_JS = """(ids) => ids.map((id) => {
    const label = document.querySelector('label[for="' + id + '"]');
    const control = label ? label.control : null;
    const byId = document.getElementById(id);
    return {
        id: id,
        labelFound: !!label,
        controlResolved: !!control,
        controlTag: control ? control.tagName : null,
        controlClass: control ? control.className : null,
        byIdTag: byId ? byId.tagName : null,
    };
})"""


def _assert_labels_resolve_to_chip_input(page: Page, ids: list[str]) -> None:
    """Every ``<label for=id>`` must resolve (via label.control) to the real
    focusable ``.chip-list-input``, not the non-labelable wrapper div."""
    results = page.evaluate(_RESOLVE_JS, ids)
    for r in results:
        assert r["labelFound"], f'no <label for="{r["id"]}"> present in the mounted DOM'
        assert r["controlResolved"], (
            f'label[for="{r["id"]}"] resolves to NO labelable control at runtime '
            f"(getElementById tag={r['byIdTag']}) — the chip-list label[for] dangle "
            "regressed (F5 carry-forward / F6 L3 systemic fix)"
        )
        assert r["controlTag"] == "INPUT", (
            f'label[for="{r["id"]}"] control is <{r["controlTag"]}>, expected the '
            f"<input class=chip-list-input> (got class={r['controlClass']!r})"
        )
        assert "chip-list-input" in (r["controlClass"] or ""), (
            f'label[for="{r["id"]}"] control is not the .chip-list-input '
            f"(class={r['controlClass']!r})"
        )


@pytest.mark.browser
def test_admin_tools_editor_chiplist_labels_resolve(app_clean: str, page: Page) -> None:
    """The admin tools-editor's WebConfig array fields (``host_allowlist`` et al.)
    render chip-lists via the shared ``renderField``; each ``label[for=tef-{name}]``
    must resolve to the real ``.chip-list-input`` in the mounted tree."""
    page.goto(f"{app_clean}#admin/tools/fetch_url")
    expect(page.locator(".editor-title")).to_have_text("fetch_url", timeout=8000)
    # The three WebConfig array fields render as chip-lists.
    for fname in ("host_allowlist", "host_denylist", "extra_allowed_hosts"):
        expect(
            page.locator(f'.tools-editor-field[data-field-name="{fname}"] .chip-list-input')
        ).to_have_count(1)
    _assert_labels_resolve_to_chip_input(
        page,
        ["tef-host_allowlist", "tef-host_denylist", "tef-extra_allowed_hosts"],
    )


@pytest.mark.browser
def test_mcp_server_editor_chiplist_labels_resolve(app_clean: str, page: Page) -> None:
    """The studio mcp-server-editor's stdio chip-lists (``args`` +
    ``sandbox-writable-paths``) are the TRUE mount-time strip site: the label
    targeted a placeholder ``<div id="mf-{name}">`` that ``mountChipListEditors``
    replaces via ``outerHTML=``. Post-fix, ``controlId`` lands the id on the real
    ``.chip-list-input`` and the placeholder div carries no id."""
    page.goto(f"{app_clean}#studio/mcp-sources/new")
    expect(page.locator('[data-testid="save-mcp-source-btn"]')).to_be_visible(timeout=8000)
    # Stdio exposes the args + sandbox-writable-paths chip-lists.
    page.locator('[data-field="type"]').select_option("stdio")
    expect(page.locator('label[for="mf-args"]')).to_be_visible(timeout=5000)
    # Both chip-lists are mounted (mountChipListEditors replaced the placeholders).
    for field in ("args", "sandbox-writable-paths"):
        expect(
            page.locator(f'[data-field="{field}"].chip-list-editor .chip-list-input')
        ).to_have_count(1)
    _assert_labels_resolve_to_chip_input(page, ["mf-args", "mf-sandbox-writable-paths"])
