"""End-to-end flow tests: the agent editor's Knowledge (attach) tab
(Mission 24, Flight 6, Leg 3 — DD-2, DD-3, DD-4, DD-13, L3-D1..L3-D7).

Covers: AC-1 (real attach surface, stub gone), AC-2 (row toggle + the
server-derived tool name, read never computed), AC-3 (toggle -> save
writes exactly the checked ids, including the legitimate "detach
everything" empty save), AC-4 (kb_ids survives a save from an unrelated
tab — squawk 0050's net), AC-5 (a failed knowledge-base fetch renders the
load-failure state, no `data-kb-list-loaded` marker, and `kb_ids` omitted
from the PUT body entirely), AC-6/AC-7 (an ungated-prefix `disabled_tools`
entry — `kb__...` and `mcp__...` — survives an unrelated Studio save in
all three of `collectFormData`'s branches), AC-8 (the inverse: an explicit
API removal of a disabled_tools entry is not silently reintroduced by the
next Studio save — the ratchet DD-13 exists to avoid), AC-9 (create mode
attaches with no stored-entry union, since there is no selected agent to
read one from), AC-10 (a knowledge base created mid-session appears in the
attach tab without a page reload — DD-15), AC-11 (the detail view's Name +
Description edit form — M24 F06 L05, L5-D2, replacing the F06 L03
rename-only affordance — reuses the inventory create form's advisory hint
+ empty-name refusal for the name field), AC-12 (after a rename, the
attach tab's row shows the NEW derived tool name and the agent's
`disabled_tools` entry has already moved to match — Leg 2's rewrite,
observed through this surface). Squawk 0090 adds one more: a FAILED
fresh-agent `GET /api/agents/{name}` must refuse the save rather than
let the ungated-prefix union re-emit a pre-rename `kb__...__search`
entry from the stale cached agent.

AC-5's "route.request.method" filter and its `post_data_json` usage are
NEW patterns in this file — no prior `tests/browser/` file reads a
request body (see the leg's Citation Audit). `post_data_json` is a
PROPERTY on the Python sync `Request` object (not a method — no call
parens), unlike the JS API's `postDataJSON()`; the leg's own citation used
parens loosely. The filter matters here for
a reason specific to this leg: `doSelect`'s L3-D3 fresh-agent GET hits the
exact same path (`/api/agents/{name}`) as the save's PUT, and both fire
during this test's flow (the GET at every re-select, the PUT at Save) —
an unfiltered glob would intercept both and read the wrong request's body
intermittently.
"""

from __future__ import annotations

import re

import httpx
import pytest
from browser._credential_registry import auth_headers_for
from browser.seeders import SeededApp
from playwright.sync_api import Page, expect

# ── API-side helpers (mirror seeders.py's direct-HTTP idiom) ────────────────


def _get_agent(base_url: str, name: str) -> dict:
    r = httpx.get(f"{base_url}/api/agents/{name}", headers=auth_headers_for(base_url), timeout=5.0)
    assert r.status_code == 200, f"GET agent failed: {r.status_code} {r.text}"
    return r.json()


def _put_agent_full(base_url: str, name: str, **overrides: object) -> dict:
    """Seed fields on an existing agent via a FULL-body PUT.

    `update_agent` validates `AgentConfig.model_validate(data)` with NO
    merge against the stored row (only `kb_ids`, `mcp_overrides` and
    `self_revision_requires_approval` are preserved on omission per Leg 2 /
    the existing precedent) — a partial body would silently reset every
    other field (`provider_config_id`, `llm_model`, ...) to its Pydantic
    default. Round-trip the full GET body with the desired overrides
    layered on top, exactly as an operator's own next full save would.
    """
    current = _get_agent(base_url, name)
    current.update(overrides)
    r = httpx.put(
        f"{base_url}/api/agents/{name}",
        headers=auth_headers_for(base_url),
        json=current,
        timeout=5.0,
    )
    assert r.status_code == 200, f"PUT agent failed: {r.status_code} {r.text}"
    return r.json()


def _create_kb(base_url: str, name: str) -> dict:
    r = httpx.post(
        f"{base_url}/api/knowledge-bases",
        headers=auth_headers_for(base_url),
        json={"name": name},
        timeout=5.0,
    )
    assert r.status_code == 201, f"create KB failed: {r.status_code} {r.text}"
    return r.json()


# ── UI-side helpers ──────────────────────────────────────────────────────────


def _open_agent_editor(base_url: str, page: Page) -> None:
    page.goto(f"{base_url}#studio")
    expect(page.locator('.section-nav[aria-label="Agent Studio sections"]')).to_be_visible(
        timeout=8000
    )
    editor_hidden = page.evaluate(
        "() => document.querySelector('.studio-editor')?.classList.contains('is-hidden')"
    )
    if editor_hidden:
        page.locator("button.entity-tile").first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)


def _reselect_agent(page: Page) -> None:
    """Return to the agents grid and click the same (only) tile again —
    the real operator affordance that re-triggers `doSelect`'s edit-mount
    refresh (L3-D1's knowledge-base refresh, L3-D3's fresh-agent fetch).
    Only safe to call when the editor is NOT dirty (no confirm dialog)."""
    page.locator('[data-testid="back-agent-btn"]').click()
    page.locator("button.entity-tile").first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)


def _open_knowledge_tab(page: Page) -> None:
    page.locator('[data-testid="tab-knowledge"]').click()
    expect(page.locator('[data-testid="agent-knowledge-tab"]')).to_be_visible(timeout=8000)


def _save(page: Page) -> None:
    save_btn = page.locator('[data-testid="save-agent-btn"]')
    expect(save_btn).to_be_enabled(timeout=5000)
    save_btn.click()
    expect(save_btn).to_be_disabled(timeout=5000)


def _set_tool_checkboxes(page: Page, checked_names: set[str]) -> None:
    """Set every built-in tool checkbox's checked state to match
    membership in `checked_names`, dispatching a real 'change' event per
    flipped checkbox so studio.js's dirty-tracking listener fires. The
    Tools tab builds every checkbox up front — hidden until its category
    tile is expanded (tools-tab.js) — so this reaches every checkbox
    without expanding anything, and works regardless of which tab is
    currently visible (collectFormData's own toggle walk is likewise
    tab-agnostic)."""
    page.evaluate(
        """(checkedNames) => {
            document.querySelectorAll('input[type="checkbox"][data-tool]').forEach((cb) => {
                var shouldCheck = checkedNames.indexOf(cb.dataset.tool) !== -1;
                if (cb.checked !== shouldCheck) {
                    cb.checked = shouldCheck;
                    cb.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
        }""",
        list(checked_names),
    )


def _set_kb_toggle(locator, checked: bool) -> None:  # noqa: ANN001
    """Flip a `[data-kb-toggle]` checkbox's checked state and fire a real
    'change' event. The checkbox is visually hidden behind the `.tool-
    switch` sibling span (mirrors the built-in Tools tab / MCPs tab
    pattern — `.area-studio .tool-toggle { display: none; }`), so a plain
    Playwright `.check()`/`.uncheck()` times out waiting for visibility;
    `test_studio_mcps_tab.py::test_*` establishes this exact evaluate +
    dispatch precedent for the sibling `data-mcp-source-toggle`."""
    locator.evaluate(
        "(el, checked) => { el.checked = checked; "
        "el.dispatchEvent(new Event('change', { bubbles: true })); }",
        checked,
    )


def _all_tool_names(page: Page) -> list[str]:
    return page.evaluate(
        "Array.from(document.querySelectorAll('input[type=\"checkbox\"][data-tool]'))"
        ".map((cb) => cb.dataset.tool)"
    )


@pytest.mark.browser
def test_stub_testid_absent_from_editor(app_with_agent: SeededApp, page: Page) -> None:
    """AC-1: the retired stub testid is gone from the rendered surface."""
    _open_agent_editor(app_with_agent.base_url, page)
    _open_knowledge_tab(page)

    expect(page.locator('[data-testid="agent-knowledge-tab-stub"]')).to_have_count(0)
    expect(page.locator('[data-testid="agent-knowledge-tab"]')).to_be_visible()


@pytest.mark.browser
def test_attach_toggle_save_detach_and_tool_name_read_from_server(
    app_with_agent: SeededApp, page: Page
) -> None:
    """AC-2, AC-3, AC-4: a row renders with an unchecked toggle and a
    placeholder tool name; attaching + saving writes exactly the checked
    id; the tool name shown afterward is read verbatim from
    `kb_tool_names`, never derived client-side; an unrelated-tab save
    leaves `kb_ids` unchanged; detaching + saving sends the legitimate
    empty `[]`."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    assert agent_name is not None
    kb = _create_kb(base_url, "Attach KB")

    _open_agent_editor(base_url, page)
    _open_knowledge_tab(page)

    row = page.locator(f'[data-testid="agent-knowledge-row-{kb["id"]}"]')
    expect(row).to_be_visible(timeout=5000)
    toggle = page.locator(f'[data-testid="agent-knowledge-toggle-{kb["id"]}"]')
    expect(toggle).not_to_be_checked()
    tool_name_el = page.locator(f'[data-testid="agent-knowledge-tool-name-{kb["id"]}"]')
    # L3-D2: not yet attached — an explicit placeholder, never a guess.
    expect(tool_name_el).to_have_text("attach to see the tool name")
    expect(tool_name_el).to_have_class(re.compile(r"\bagent-knowledge-row-tool-name-placeholder\b"))

    _set_kb_toggle(toggle, True)
    _save(page)

    body = _get_agent(base_url, agent_name)
    assert body.get("kb_ids") == [kb["id"]], (
        f"expected kb_ids=[{kb['id']!r}], got {body.get('kb_ids')!r}"
    )
    expected_tool_name = (body.get("kb_tool_names") or {}).get(kb["id"])
    assert expected_tool_name, (
        f"expected a kb_tool_names entry for {kb['id']!r}, got {body.get('kb_tool_names')!r}"
    )

    # Re-mount the editor (L3-D1's edit-mount refresh) and confirm the row
    # now shows the SERVER-DERIVED name, byte-identical to the API field —
    # not a client-side guess.
    _reselect_agent(page)
    _open_knowledge_tab(page)
    tool_name_el = page.locator(f'[data-testid="agent-knowledge-tool-name-{kb["id"]}"]')
    expect(tool_name_el).to_have_text(expected_tool_name)
    expect(tool_name_el).not_to_have_class(
        re.compile(r"\bagent-knowledge-row-tool-name-placeholder\b")
    )
    expect(page.locator(f'[data-testid="agent-knowledge-toggle-{kb["id"]}"]')).to_be_checked()

    # AC-4: a save from the General tab (never revisiting Knowledge) must
    # leave kb_ids unchanged.
    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-field="description"]').fill("touched from an unrelated tab")
    _save(page)
    body = _get_agent(base_url, agent_name)
    assert body.get("kb_ids") == [kb["id"]], (
        f"kb_ids changed from an unrelated-tab save: {body.get('kb_ids')!r}"
    )

    # AC-3: unchecking and saving sends the legitimate empty "[]" —
    # detach-everything, not an omission.
    _open_knowledge_tab(page)
    _set_kb_toggle(page.locator(f'[data-testid="agent-knowledge-toggle-{kb["id"]}"]'), False)
    _save(page)
    body = _get_agent(base_url, agent_name)
    assert body.get("kb_ids") == [], f"expected kb_ids=[] after detach, got {body.get('kb_ids')!r}"


@pytest.mark.browser
def test_failed_fetch_shows_load_error_and_omits_kb_ids_from_save(
    app_with_agent: SeededApp, page: Page
) -> None:
    """AC-5: a failed `/api/knowledge-bases` fetch renders the explicit
    load-failure state (even with a populated prior cache), carries no
    `data-kb-list-loaded` marker, and the next save omits `kb_ids` from
    the PUT body entirely — the server-side preserve (Leg 2 AC-7) then
    keeps the stored value instead of squawk 0050's `kb_ids: []` wipe."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    assert agent_name is not None
    kb = _create_kb(base_url, "Preexisting KB")
    # Attach it up front via a full-body PUT so there IS a populated prior
    # cache/attachment for the failed refresh to (correctly) not blank.
    _put_agent_full(base_url, agent_name, kb_ids=[kb["id"]])

    # First mount healthy, so the section-local cache is populated...
    _open_agent_editor(base_url, page)
    _open_knowledge_tab(page)
    expect(page.locator(f'[data-testid="agent-knowledge-row-{kb["id"]}"]')).to_be_visible(
        timeout=5000
    )

    # ...then stub the NEXT knowledge-bases fetch to fail and re-select.
    page.route(
        "**/api/knowledge-bases",
        lambda route: route.fulfill(status=500, content_type="text/plain", body="err"),
    )
    _reselect_agent(page)
    _open_knowledge_tab(page)

    error_el = page.locator('[data-testid="agent-knowledge-load-error"]')
    expect(error_el).to_be_visible(timeout=5000)
    loaded_marker = page.locator('[data-testid="agent-knowledge-tab"][data-kb-list-loaded="true"]')
    expect(loaded_marker).to_have_count(0)

    # Stop failing the knowledge-bases route BEFORE saving — collectFormData
    # reads the marker from the DOM as already rendered (the load-failure
    # state above), which does not change just because the network stub is
    # lifted, so this does not weaken the payload assertion below. What it
    # DOES fix: `save()`'s own post-PUT `loadAll()` refresh (unrelated to
    # this leg — squawk 0014's existing rejection path) would otherwise
    # reject too, on the same still-stubbed route, and never reach the
    # `.then()` that disables the Save button — a self-inflicted hang this
    # test must not manufacture.
    page.unroute("**/api/knowledge-bases")

    # AC-5's payload half: intercept the PUT (never the GET fresh-agent
    # refetch — same path — hence the method filter) and inspect the body.
    put_bodies: list[dict] = []

    def _capture_put(route) -> None:  # noqa: ANN001
        if route.request.method == "PUT":
            put_bodies.append(route.request.post_data_json)
        route.continue_()

    page.route(f"**/api/agents/{agent_name}", _capture_put)

    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-field="description"]').fill("save while kb list is broken")
    _save(page)

    assert len(put_bodies) == 1, f"expected exactly one PUT, got {len(put_bodies)}"
    assert "kb_ids" not in put_bodies[0], (
        f"kb_ids must be OMITTED, got {put_bodies[0].get('kb_ids')!r}"
    )

    # Server-side preserve (Leg 2 AC-7) kept the stored attachment.
    page.unroute(f"**/api/agents/{agent_name}")
    body = _get_agent(base_url, agent_name)
    assert body.get("kb_ids") == [kb["id"]], (
        f"expected the stored kb_ids to survive the omission, got {body.get('kb_ids')!r}"
    )


@pytest.mark.browser
def test_disabled_tools_union_survives_three_branches(
    app_with_agent: SeededApp, page: Page
) -> None:
    """AC-6, AC-7: a `kb__...__search` AND an `mcp__...` entry in
    `disabled_tools` both survive an unrelated Studio save in each of
    `collectFormData`'s three branches (all tools on; a minority disabled;
    a majority disabled) — `mcp_overrides` (a disjoint field) is
    unaffected throughout."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    assert agent_name is not None
    kb_entry = "kb__attach-union-test__deadbeef1234__search"
    mcp_entry = "mcp__some_source__some_tool"
    _put_agent_full(base_url, agent_name, disabled_tools=[kb_entry, mcp_entry])

    _open_agent_editor(base_url, page)
    all_names = _all_tool_names(page)
    assert len(all_names) >= 3, "need at least 3 built-in tools for a real majority/minority split"

    # Branch 1: all tools on (allOn -> data.disabled_tools = union only).
    _set_tool_checkboxes(page, set(all_names))
    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-field="description"]').fill("branch 1: all tools on")
    _save(page)
    body = _get_agent(base_url, agent_name)
    assert kb_entry in body.get("disabled_tools", []), body.get("disabled_tools")
    assert mcp_entry in body.get("disabled_tools", []), body.get("disabled_tools")
    assert not (body.get("mcp_overrides") or {}), body.get("mcp_overrides")

    # Branch 2: majority disabled (enabledNames.length <= disabledNames.length).
    _reselect_agent(page)
    _set_tool_checkboxes(page, {all_names[0]})
    _save(page)
    body = _get_agent(base_url, agent_name)
    assert kb_entry in body.get("disabled_tools", []), body.get("disabled_tools")
    assert mcp_entry in body.get("disabled_tools", []), body.get("disabled_tools")
    assert not (body.get("mcp_overrides") or {}), body.get("mcp_overrides")

    # Branch 3: minority disabled (else branch — disabledNames appended).
    _reselect_agent(page)
    _set_tool_checkboxes(page, set(all_names) - {all_names[0]})
    _save(page)
    body = _get_agent(base_url, agent_name)
    assert kb_entry in body.get("disabled_tools", []), body.get("disabled_tools")
    assert mcp_entry in body.get("disabled_tools", []), body.get("disabled_tools")
    assert not (body.get("mcp_overrides") or {}), body.get("mcp_overrides")


@pytest.mark.browser
def test_explicit_api_removal_of_disabled_tool_is_not_reintroduced(
    app_with_agent: SeededApp, page: Page
) -> None:
    """AC-8 — DD-13's inverse: an explicit `PUT` that omits a
    previously-disabled `kb__` name removes it, and the NEXT Studio save
    does not silently put it back. A survival-only net (AC-6 above) would
    pass against exactly the ratchet this decision exists to avoid."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    assert agent_name is not None
    kb_entry = "kb__removal-test__cafebabe5678__search"
    _put_agent_full(base_url, agent_name, disabled_tools=[kb_entry])
    body = _get_agent(base_url, agent_name)
    assert kb_entry in body["disabled_tools"]

    # The un-disable path: an explicit API PUT with the entry omitted.
    _put_agent_full(base_url, agent_name, disabled_tools=[])
    body = _get_agent(base_url, agent_name)
    assert kb_entry not in body["disabled_tools"], "explicit removal did not take"

    # Re-mount the editor AFTER the removal (L3-D3: the union must read the
    # freshly fetched agent) and save from an unrelated tab.
    _open_agent_editor(base_url, page)
    page.locator('[data-field="description"]').fill("save after explicit removal")
    _save(page)

    body = _get_agent(base_url, agent_name)
    assert kb_entry not in body.get("disabled_tools", []), (
        f"a removed disabled_tools entry was silently reintroduced: {body.get('disabled_tools')!r}"
    )


@pytest.mark.browser
def test_create_mode_attach_sends_no_stored_union(app_with_provider: SeededApp, page: Page) -> None:
    """AC-9: creating an agent (no selected agent to read a union from)
    can still attach a knowledge base via the row toggle, and the created
    agent's disabled_tools carries no stored-entry union artifact (there
    was nothing to union from)."""
    base_url = app_with_provider.base_url
    kb = _create_kb(base_url, "Create-mode KB")

    page.goto(f"{base_url}#studio")
    page.locator('[data-testid="new-agent-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("New Agent")
    page.locator('[data-field="name"]').fill("create-mode-attach-agent")
    expect(page.locator("#studio-provider")).to_have_value(app_with_provider.provider_id)
    expect(page.locator('#studio-model option[value="mock-default"]')).to_be_attached(timeout=5000)
    page.locator("#studio-model").select_option("mock-default")

    _open_knowledge_tab(page)
    row = page.locator(f'[data-testid="agent-knowledge-row-{kb["id"]}"]')
    expect(row).to_be_visible(timeout=5000)
    # L3-D2: agent is null in create-mode — no tool name to read, ever.
    expect(page.locator(f'[data-testid="agent-knowledge-tool-name-{kb["id"]}"]')).to_have_text(
        "attach to see the tool name"
    )
    _set_kb_toggle(page.locator(f'[data-testid="agent-knowledge-toggle-{kb["id"]}"]'), True)

    _save(page)
    expect(page.locator(".editor-title")).to_have_text("create-mode-attach-agent", timeout=5000)

    body = _get_agent(base_url, "create-mode-attach-agent")
    assert body.get("kb_ids") == [kb["id"]], body.get("kb_ids")
    assert body.get("disabled_tools") == [], (
        f"create-mode save must carry no stored-entry union, got {body.get('disabled_tools')!r}"
    )


@pytest.mark.browser
def test_kb_created_mid_session_appears_without_reload(
    app_with_agent: SeededApp, page: Page
) -> None:
    """AC-10 (DD-15): a knowledge base created after the editor's first
    mount is present in the attach tab on the next mount, in the SAME
    browser session — no `page.reload()`."""
    base_url = app_with_agent.base_url
    _open_agent_editor(base_url, page)
    _open_knowledge_tab(page)
    expect(page.locator('[data-testid="agent-knowledge-empty-state"]')).to_be_visible(timeout=5000)

    kb = _create_kb(base_url, "Mid-Session KB")

    _reselect_agent(page)
    _open_knowledge_tab(page)
    expect(page.locator(f'[data-testid="agent-knowledge-row-{kb["id"]}"]')).to_be_visible(
        timeout=5000
    )


@pytest.mark.browser
def test_rename_hint_and_empty_refusal_mirror_create_form(app_clean: str, page: Page) -> None:
    """AC-11: the always-live Name field's (M24 F06 L06 restyle, L6-D1 —
    replaces the L5-D2 edit-form toggle, itself a replacement of the F06
    L03 rename-only affordance) 43-code-point advisory hint and empty-name
    refusal behave exactly like the inventory create form's (Leg 1) —
    empty refused client-side, over-length warned but accepted."""
    kb = _create_kb(app_clean, "Rename Me")
    page.goto(f"{app_clean}#studio/knowledge/{kb['id']}")
    expect(page.locator('[data-testid="back-knowledge-btn"]')).to_be_visible(timeout=8000)

    name_input = page.locator('[data-testid="kb-name-input"]')
    hint = page.locator('[data-testid="kb-name-hint"]')
    expect(name_input).to_be_visible()
    expect(hint).to_be_hidden()

    rename_requests: list[str] = []

    def _on_request(request) -> None:  # noqa: ANN001
        if request.method == "PUT" and request.url.endswith(f"/api/knowledge-bases/{kb['id']}"):
            rename_requests.append(request.url)

    page.on("request", _on_request)

    # Empty name: refused client-side, no request sent.
    name_input.fill("")
    page.locator('[data-testid="save-knowledge-btn"]').click()
    expect(page.locator(".editor-error")).to_have_text("Name is required.")
    assert rename_requests == []

    # Over-length name: advisory hint shows, save still succeeds.
    long_name = "r" * 50
    name_input.fill(long_name)
    expect(hint).to_be_visible()
    page.locator('[data-testid="save-knowledge-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text(long_name, timeout=5000)
    assert len(rename_requests) == 1


@pytest.mark.browser
def test_rename_updates_tool_name_and_disabled_tools_on_agent_editor(
    app_with_agent: SeededApp, page: Page
) -> None:
    """AC-12: after a rename, reopening the agent editor shows the NEW
    derived tool name on the row, and the agent's `disabled_tools` entry
    has already moved to match it — Leg 2's cross-entity rewrite (DD-5),
    observed through this surface."""
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    assert agent_name is not None
    kb = _create_kb(base_url, "Pre-Rename Name")
    _put_agent_full(base_url, agent_name, kb_ids=[kb["id"]])
    body = _get_agent(base_url, agent_name)
    old_tool_name = body["kb_tool_names"][kb["id"]]
    # Disable it via the API — there's no UI for this (DD-13's rationale:
    # the Studio form cannot render an ungated-prefix name).
    _put_agent_full(base_url, agent_name, disabled_tools=[old_tool_name])

    # Rename via the inventory's own UI control (M24 F06 L06's always-live
    # Name + Description fields, restyling M24 F06 L05's edit form, itself
    # a replacement of the F06 L03 rename-only affordance).
    page.goto(f"{base_url}#studio/knowledge/{kb['id']}")
    expect(page.locator('[data-testid="back-knowledge-btn"]')).to_be_visible(timeout=8000)
    page.locator('[data-testid="kb-name-input"]').fill("Post-Rename Name")
    page.locator('[data-testid="save-knowledge-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("Post-Rename Name", timeout=5000)

    body = _get_agent(base_url, agent_name)
    new_tool_name = body["kb_tool_names"][kb["id"]]
    assert new_tool_name != old_tool_name, "rename did not move the derived tool name"
    disabled_tools = body["disabled_tools"]
    assert new_tool_name in disabled_tools, (
        f"expected the rewritten name {new_tool_name!r} in disabled_tools, got {disabled_tools!r}"
    )
    assert old_tool_name not in disabled_tools

    # Reopen the agent editor: the row shows the NEW name.
    _open_agent_editor(base_url, page)
    _open_knowledge_tab(page)
    tool_name_el = page.locator(f'[data-testid="agent-knowledge-tool-name-{kb["id"]}"]')
    expect(tool_name_el).to_have_text(new_tool_name, timeout=5000)


@pytest.mark.browser
def test_attached_tool_name_survives_unrelated_in_session_save(
    app_with_agent: SeededApp, page: Page
) -> None:
    """kb-studio-round-trip remediation FIX 2 (run 2026-09-18-13-14-52,
    FINDING 7): after attaching a knowledge base and saving, an UNRELATED
    save from the General tab — same page, same session, no reload, no
    re-select — must not regress the already-attached row's derived tool
    name to the unattached placeholder while its toggle still reads on.

    Root cause was the post-save re-render running off `loadAll()`'s
    `GET /api/agents` (the LIST route), which deliberately omits
    `kb_tool_names` (L2-D5, to avoid an N+1 read on every page load) —
    structurally incapable of carrying the field — instead of the PUT's
    own response, which always carries it. `GET`/`PUT` on the single-agent
    route never lost the field; only the in-session re-render did, so a
    test that reloads or re-selects before reading the row would pass
    against the very defect it exists to catch.
    """
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    assert agent_name is not None
    kb = _create_kb(base_url, "Post-Save Freshness KB")

    _open_agent_editor(base_url, page)
    _open_knowledge_tab(page)
    toggle = page.locator(f'[data-testid="agent-knowledge-toggle-{kb["id"]}"]')
    _set_kb_toggle(toggle, True)
    _save(page)

    body = _get_agent(base_url, agent_name)
    expected_tool_name = (body.get("kb_tool_names") or {}).get(kb["id"])
    assert expected_tool_name, (
        f"expected a kb_tool_names entry for {kb['id']!r}, got {body.get('kb_tool_names')!r}"
    )
    # Row correctly resolved right after the attaching save itself.
    tool_name_el = page.locator(f'[data-testid="agent-knowledge-tool-name-{kb["id"]}"]')
    expect(tool_name_el).to_have_text(expected_tool_name, timeout=5000)

    # A second, UNRELATED save — General tab, never revisiting Knowledge
    # in between — in the SAME session (no page.reload, no re-select).
    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-field="description"]').fill("touched again, still same session")
    _save(page)

    # Read the row back immediately, without reselecting the agent — the
    # regression is specifically in this post-save re-render.
    page.locator('[data-testid="tab-knowledge"]').click()
    expect(page.locator('[data-testid="agent-knowledge-tab"]')).to_be_visible(timeout=5000)
    row = page.locator(f'[data-testid="agent-knowledge-row-{kb["id"]}"]')
    expect(row).to_be_visible(timeout=5000)
    expect(page.locator(f'[data-testid="agent-knowledge-toggle-{kb["id"]}"]')).to_be_checked()
    tool_name_el = page.locator(f'[data-testid="agent-knowledge-tool-name-{kb["id"]}"]')
    expect(tool_name_el).to_have_text(expected_tool_name)
    expect(tool_name_el).not_to_have_class(
        re.compile(r"\bagent-knowledge-row-tool-name-placeholder\b")
    )

    # The API's own data was never wrong at any point — the defect is
    # display-only.
    body = _get_agent(base_url, agent_name)
    assert (body.get("kb_tool_names") or {}).get(kb["id"]) == expected_tool_name
    assert body.get("kb_ids") == [kb["id"]]


@pytest.mark.browser
def test_failed_agent_fetch_refuses_save_instead_of_reemitting_stale_disabled_tool(
    app_with_agent: SeededApp, page: Page
) -> None:
    """Squawk 0090: when `doSelect`'s fresh `GET /api/agents/{name}` fails,
    the editor still renders from the stale cached agent (L3-D7) — but it
    must NOT save from it. The stale object is what
    `_storedUngatedDisabledNames()` unions into `disabled_tools`, so a
    save from it would re-emit the PRE-rename `kb__{old_slug}__…__search`
    entry over the post-rename one `rename_kb_tool_references` wrote,
    silently re-enabling a tool the operator deliberately disabled.

    Shape of the fix (and why it differs from AC-5's sibling above):
    `disabled_tools` has NO server-side preserve-on-omit path — omitting
    it would wipe every disabled tool, since `AgentConfig.disabled_tools`
    defaults to `[]` — so the save is REFUSED, with the load-failure
    affordance rendered, rather than the field omitted.

    The GET and the PUT share a path, so the single route handler here
    dispatches on `route.request.method` (the same reason AC-5's handler
    does).
    """
    base_url = app_with_agent.base_url
    agent_name = app_with_agent.agent_name
    assert agent_name is not None
    kb = _create_kb(base_url, "Stale Union Pre-Rename")
    _put_agent_full(base_url, agent_name, kb_ids=[kb["id"]])
    old_tool_name = _get_agent(base_url, agent_name)["kb_tool_names"][kb["id"]]
    # Disable it via the API — DD-13: the Studio form cannot render an
    # ungated-prefix name, so there is no UI for this.
    _put_agent_full(base_url, agent_name, disabled_tools=[old_tool_name])

    # Mount the editor while everything is healthy, so the in-page caches
    # (`self._agents`, `self._selectedAgent`) hold the PRE-rename entry.
    _open_agent_editor(base_url, page)
    _open_knowledge_tab(page)
    expect(page.locator(f'[data-testid="agent-knowledge-row-{kb["id"]}"]')).to_be_visible(
        timeout=5000
    )

    # Rename out-of-band (server-side only): the page's caches are now
    # stale in exactly the way the squawk describes, and the stored
    # `disabled_tools` entry has moved to the new name.
    r = httpx.put(
        f"{base_url}/api/knowledge-bases/{kb['id']}",
        headers=auth_headers_for(base_url),
        json={"name": "Stale Union Post-Rename"},
        timeout=5.0,
    )
    assert r.status_code == 200, f"rename KB failed: {r.status_code} {r.text}"
    body = _get_agent(base_url, agent_name)
    new_tool_name = body["kb_tool_names"][kb["id"]]
    assert new_tool_name != old_tool_name, "rename did not move the derived tool name"
    assert body["disabled_tools"] == [new_tool_name], (
        f"expected the rewrite to have already landed, got {body['disabled_tools']!r}"
    )

    # Fail the fresh-agent GET; record (and let through) any PUT.
    put_bodies: list[dict] = []

    def _fail_get_capture_put(route) -> None:  # noqa: ANN001
        if route.request.method == "GET":
            route.fulfill(status=500, content_type="text/plain", body="err")
            return
        if route.request.method == "PUT":
            put_bodies.append(route.request.post_data_json)
        route.continue_()

    page.route(f"**/api/agents/{agent_name}", _fail_get_capture_put)

    _reselect_agent(page)

    # The editor still renders (L3-D7) — and says so.
    expect(page.locator('[data-testid="agent-load-error"]')).to_be_visible(timeout=5000)

    # Dirty the form: Save stays disabled, unlike every healthy mount.
    page.locator('[data-testid="tab-general"]').click()
    page.locator('[data-field="description"]').fill("save attempt on a stale agent")
    save_btn = page.locator('[data-testid="save-agent-btn"]')
    expect(page.locator('[data-testid="cancel-agent-btn"]')).to_be_enabled(timeout=5000)
    expect(save_btn).to_be_disabled()

    # Second line of defence: force the button live and click it, so
    # `save()`'s own guard is the thing under test (a click on a disabled
    # button dispatches no event at all, which would prove nothing).
    # Re-enable and dispatch in ONE evaluate: a Playwright `.click()` blurs
    # the description input on its way in, whose `change` listener re-runs
    # `checkDirty` and re-disables the button between mousedown and mouseup
    # — so the browser never dispatches the click at all.
    save_btn.evaluate("(el) => { el.disabled = false; el.click(); }")
    expect(page.locator(".studio-editor .editor-error")).to_contain_text(
        "failed to load", timeout=5000
    )

    assert put_bodies == [], f"no PUT may be sent from a stale agent, got {put_bodies!r}"

    # The stored entry still names the POST-rename tool.
    page.unroute(f"**/api/agents/{agent_name}")
    body = _get_agent(base_url, agent_name)
    assert body["disabled_tools"] == [new_tool_name], (
        f"expected disabled_tools to still be [{new_tool_name!r}], got {body['disabled_tools']!r}"
    )
    assert old_tool_name not in body["disabled_tools"]
