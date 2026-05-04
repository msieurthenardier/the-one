# Leg: 07-browser-tests

**Status**: landed
**Flight**: [Tools Admin Section](../flight.md)

## Objective

Full Playwright coverage of the F6 admin + Studio surfaces (per user's L7 = full-coverage direction). Three new test files under `tests/browser/`: (a) `test_flow_admin_tools_grid.py` — grid renders, tabs, toggle persists, tile click navigates, "Built-in Tools" label; (b) `test_flow_admin_tools_editor.py` — editor form fields, save/cancel/dirty, `// prompt` block, info-icon tooltips, error banner, field-error highlights, custom test inputs; (c) `test_flow_studio_tools_overrides.py` — disabled-tool surfacing, override panel lazy-load, marker-aware widgets (Narrow ceiling, NarrowSuperset locked chips, Substitute free-form, unmarked HIDDEN), tool_overrides save round-trip. Plus one existing-test update: `test_flow_admin_navigation.py`'s `test_admin_section_nav_renders_two_sections` becomes `_renders_three_sections` to account for the new "Built-in Tools" entry. Browser env-gap pre-cleared by L0's Makefile shift (`_ensure-playwright` now prereqs `test-browser` / `test-pixel`).

## Context

- **F6 user direction**: "L7 = full Playwright coverage scope". L6 HAT verified each scenario manually; L7 codifies all of them as automated regression nets PLUS the inline UX fixes that landed during HAT (tabs in grid, `// prompt` block, info icons, error banner, field highlights, custom test inputs, "Built-in Tools" label, iOS-toggle in editor, chip-list visual styling for Studio).
- **F6 Decision 12** (two-Reviewer-pass batching): L7 commits no docs. The browser-test count is documented in `agents.md` at L9.
- **Existing browser pattern** (verified at `tests/browser/test_flow_admin_navigation.py`): `pytest.mark.browser` decorator; `app_clean` fixture (fresh subprocess + DB); `page` fixture (BrowserContext + Page); `expect(...)` assertions; `page.goto(f"{app_clean}#admin/...")` for URL nav.
- **`tests/browser/seeders.py`**: `seed_mock_agent`, `seed_mock_provider` for fixtures that need pre-existing data. F6 L7 needs a seeded agent for the Studio override tests (override panels are per-agent).
- **Snapshot tests**: per the user's global instruction, snapshot baselines are gitignored and regenerated locally. L7 uses DOM-shape assertions (`expect(...).to_have_text(...)`, `to_be_visible()`, `to_have_attribute(...)`) NOT visual snapshots.
- **L1 endpoint dependency**: L7 tests run against the live container — they hit real `/api/tools/configs` endpoints. The seeded DB has fresh tool_configs rows by default (all enabled, empty configs). Tests that need specific operator state (e.g., disabled web_search) make explicit PUTs at test setup.
- **L4 test buttons** are tricky to test deterministically — `web_search` hits real DDG (rate-limit risk) and `fetch_url` hits real example.com (network dependency). L7 covers them with monkey-patched fixtures via the `app_clean` subprocess env, OR runs them as `@pytest.mark.live` (skipped by default; runs only with `-m live`). Choice: skip the actual network round-trip in L7's default-marked tests; verify the BUTTON wiring (click → request fired → response handled) via DOM assertions only. The L1 unit tests already cover the endpoint logic; L7 covers the UI plumbing.
- **HAT inline fixes that need test coverage** (delta from the L7-as-originally-spec'd):
  - Grid uses 4 category TABS (NOT a single alphabetic list). Active tab persists across re-renders (toggle PUT round-trip).
  - Editor header has `// prompt` block (NOT inline subtitle).
  - Per-field info icons (NOT inline `<p class="field-description">`).
  - Error banner above Configuration section for model-level 422s.
  - Field-error highlights on offending rows.
  - Custom test input next to button (`Query: [...]` for web_search, `URL: [...]` for fetch_url).
  - Section-nav entry "Built-in Tools" (NOT "Tools").
  - Editor `enabled` row uses iOS-toggle (NOT plain checkbox).
  - Chip-list visual styling matches in Studio override panel.

## Inputs

- `tests/browser/conftest.py` — `app_clean`, `page`, `app_with_agent`, `app_with_provider` fixtures. L7 uses `app_clean` for fresh-DB tests and may need a new `app_with_tool_config` seeder for tests that require pre-existing tool_configs rows.
- `tests/browser/test_flow_admin_navigation.py` — existing pattern; `test_admin_section_nav_renders_two_sections` needs widening.
- `tests/browser/test_flow_provider_grid.py`, `test_flow_provider_editor.py`, `test_flow_agent_tabs.py`, `test_flow_agent_tile.py` — reference patterns for grid/editor/tab/tile tests.
- `tests/browser/seeders.py` — seeder pattern for L7's pre-state seeding.
- All F6-touched JS files (the actual surfaces being tested).
- `Makefile:108-115` — `make test-browser` (now prereqs `_ensure-playwright` per L0).

## Outputs

### Existing-test update — `tests/browser/test_flow_admin_navigation.py`

Single test renamed + updated:

```python
@pytest.mark.browser
def test_admin_section_nav_renders_three_sections(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/system")
    nav = page.locator(".area-admin .section-nav")
    expect(nav).to_be_visible(timeout=5000)
    items = nav.locator(".section-nav-item")
    expect(items).to_have_count(3)
    expect(items.nth(0)).to_have_text("System")
    expect(items.nth(1)).to_have_text("LLM Providers")
    expect(items.nth(2)).to_have_text("Built-in Tools")
```

Rename matters because the function name asserted a count; staying at "two_sections" with `to_have_count(3)` would be misleading.

### New file — `tests/browser/test_flow_admin_tools_grid.py` (~10 tests)

Tests:
1. **`test_admin_tools_renders_grid_with_4_tabs`** — `goto #admin/tools` → page-title "Built-in Tools" → 4 tabs render in declaration order: Filesystem / Execution / Python / Web → Filesystem tab is selected by default → 9 tiles visible in Filesystem panel.
2. **`test_admin_tools_tab_click_switches_panel`** — click Web tab → Filesystem panel hides → Web panel shows → 4 tiles visible (download_file / fetch_url / http_request / web_search).
3. **`test_admin_tools_each_tab_renders_correct_tile_count`** — Filesystem 9, Execution 5, Python 1, Web 4.
4. **`test_admin_tools_tile_click_navigates_to_editor`** — click `web_search` tile → URL becomes `#admin/tools/web_search` → editor opens.
5. **`test_admin_tools_tile_toggle_persists_across_reload`** — toggle web_search OFF. Per-Reviewer (medium): the in-flight gate disables the toggle until PUT response. Await `expect(page.locator('input[data-name="web_search"]')).not_to_be_disabled(timeout=5000)` BEFORE reload to ensure the round-trip completed; otherwise the test races the reload against in-flight state. Then reload → Web tab → toggle still OFF.
6. **`test_admin_tools_tile_toggle_does_not_navigate`** — clicking the toggle (NOT the tile body) flips state without navigating to editor.
7. **`test_admin_tools_active_tab_persists_across_toggle_re_render`** — switch to Web tab → toggle a tile → grid re-renders → still on Web tab (not back to Filesystem default).
8. **`test_admin_tools_grid_tile_keyboard_navigation`** — Tab to first tile → Enter opens editor → Esc / Back returns to grid → Tab to toggle → Space flips toggle (not navigate).
9. **`test_admin_tools_section_nav_label_is_built_in_tools`** — third nav item text is "Built-in Tools".
10. **`test_admin_tools_deep_link_to_tool_loads_editor`** — `goto #admin/tools/web_search` directly → editor opens to web_search.

### New file — `tests/browser/test_flow_admin_tools_editor.py` (~14 tests)

Tests:
1. **`test_editor_renders_prompt_block`** — `goto #admin/tools/web_search` → `.editor-prompt-block` visible → contains `// prompt` label + the tool's description text.
2. **`test_editor_renders_enabled_toggle_inline`** — `.tools-editor-enabled-row .tool-enable-switch` visible (NOT a plain checkbox); position is `relative` (not absolute / off-screen).
3. **`test_editor_renders_all_web_config_fields`** — per-Reviewer (medium): rule pinned. **All 8 WebConfig fields render in admin mode** (including unmarked `redirect_cap`); marker-gating only HIDES fields in agent mode (covered by studio test #8). Assert all 8 fields are visible: `timeout_seconds_default`, `timeout_seconds_max`, `response_size_cap_bytes`, `redirect_cap`, `host_allowlist`, `host_denylist`, `extra_allowed_hosts`, `default_user_agent`.
4. **`test_editor_field_descriptions_are_info_icon_tooltips`** — spot-check 2-3 fields with known descriptions (e.g., `timeout_seconds_max`, `host_allowlist`, `default_user_agent`): `.field-info-icon` exists in the row, is a sibling AFTER the input (NOT inside the label), `title` attribute is non-empty. Also assert `expect(page.locator('.tools-editor-field p.field-description')).to_have_count(0)` — confirms the inline `<p>` paragraph is gone.
5. **`test_editor_save_disabled_until_dirty`** — Save button starts `disabled`; modify a field → Save enables; click Save → succeeds → Save back to disabled.
6. **`test_editor_cancel_restores_snapshot`** — modify a field → Cancel → field reverts to original value; Save back to disabled.
7. **`test_editor_save_persists_across_reload`** — narrow `timeout_seconds_max` to 60 (≥ default of 30) → Save → reload → field shows 60.
8. **`test_editor_model_validator_422_shows_banner`** — narrow `timeout_seconds_max` to 10 (< default 30) → Save → response 422 → `.editor-error-banner` visible with humanized text (no "Value error," prefix); `.field-error-highlight` on the two offending rows.
9. **`test_editor_field_change_clears_highlight`** — after triggering 422 → start typing in a highlighted field → highlight clears for that field.
10. **`test_editor_back_button_dirty_gate`** — modify a field → click Back → `App.confirmDialog` appears (selector pattern: `.dialog-confirm` per existing `test_flow_dirty_confirm.py`) → Cancel keeps editor open → confirm exits to grid.
11. **`test_editor_section_nav_dirty_gate`** — modify a field → click "System" in left nav → `App.confirmDialog` appears → Cancel keeps editor → confirm navigates away. Both #10 and #11 use the same `.dialog-confirm` pattern (admin.js dirty gate routes through `App.confirmDialog`, NOT a native browser confirm).
12. **`test_test_button_only_for_testable_tools`** — `goto #admin/tools/shell` → `.test-tool-btn` NOT present. `goto #admin/tools/web_search` → `.test-tool-btn` present.
13. **`test_test_button_input_pre_filled`** — web_search editor → input value is `"the one cli agent"`. fetch_url editor → input value is `"https://example.com/"`.
14. **`test_test_button_click_fires_request`** — per-Reviewer (medium) the simple "result populated" assertion races the spinner. Sequence:
    - Click Test.
    - Immediately assert `expect(testBtn).to_be_disabled()` (proves request fired).
    - Then `expect(page.locator('.test-result span:not(.test-result-pending)')).to_be_visible(timeout=15000)` (covers both success `.test-result-ok` and refusal `.test-result-fail` terminal states; bumps timeout to 15s — DDG and example.com can be slow).
    - Then `expect(testBtn).not_to_be_disabled()` (button re-enables).
    Don't assert on the response content — that depends on real network.

### New file — `tests/browser/test_flow_studio_tools_overrides.py` (~10 tests)

Requires `app_with_agent` fixture (or a new variant that seeds an agent with provider attached so Studio editor mounts). Tests:

1. **`test_studio_tools_tab_renders_grid`** — Studio → agent → Tools tab → 19 tool rows render.
2. **`test_studio_disabled_tool_renders_with_strikethrough`** — operator disables `web_search` via API setup → Studio Tools tab → web_search row has `.tool-row-disabled` class + `.tool-name-strike` on name; checkbox carries `disabled` attribute.
3. **`test_studio_disabled_tool_tooltip`** — disabled row's `title` attribute contains "Disabled by operator".
4. **`test_studio_re_enable_restores_interactivity`** — operator disables web_search via API → `page.goto` Studio agent editor → assert row disabled. Operator re-enables via API. **Per-Reviewer (high)**: `studio.js::refreshToolConfigsCache` only fires inside `doSelect`/`doEnterCreateMode` — it does NOT auto-refresh on idle DOM events. The test MUST trigger a re-mount: `page.reload()` (simplest), then assert row is interactive (no `.tool-row-disabled` class; checkbox no longer `disabled`). Tests #2/#3 set operator-disable BEFORE `page.goto` so they don't need this trigger; test #4 needs it because the API change happens after Studio is already mounted.
5. **`test_studio_override_panel_collapsed_by_default`** — each enabled tool row has a sibling `<details class="tool-row-overrides">` with `open` attribute absent. Also assert the panel body contains the `<p class="loading">Loading…</p>` placeholder pre-condition (per `tools-tab.js:117`) — confirms the lazy-load seed is in place for test #6.
6. **`test_studio_override_panel_lazy_loads_schema`** — per-Reviewer (medium) DOM stability is unreliable. Use Playwright request interception:
    ```python
    requests_seen = []
    page.on('request', lambda r: requests_seen.append(r.url) if '/api/tools/configs/http_request' in r.url else None)
    # ... open panel, await render
    # close, re-open, await render
    assert len(requests_seen) == 1, requests_seen
    ```
    Backstop: also assert the second open shows fields immediately (no "Loading…" placeholder this time) — confirms the cache is consumed. Note: register the listener BEFORE the first `<details>` toggle.
7. **`test_studio_override_narrow_int_uses_operator_max`** — operator saves `timeout_seconds_max=60` via API → open agent override panel for http_request → `timeout_seconds_max` input has `max="60"` attribute (NOT the schema's `le=3600`).
8. **`test_studio_override_unmarked_field_hidden`** — open http_request panel → `redirect_cap` field NOT rendered (no marker → operator-only).
9. **`test_studio_override_narrow_superset_locked_chips`** — operator saves `command_denylist=["rm", "dd"]` via API → open shell override panel → `.chip[data-locked="true"]` for each operator entry. Per-Reviewer (low): also assert `expect(page.locator('.chip[data-locked] .chip-remove')).to_have_count(0)` — locked chips render WITHOUT the remove button entirely (NOT just hidden via CSS).
10. **`test_studio_override_save_round_trips_via_api`** — open http_request panel → add `localhost` to extra_allowed_hosts → Save agent → API GET on agent → `tool_overrides.http_request.extra_allowed_hosts == ["localhost"]`.

### New seeder helper in `tests/browser/seeders.py`

Per-Reviewer (suggestion): the `httpx.put` setup pattern is novel for the browser suite (existing seeders only use `httpx.post`). Add a small `seed_tool_config(base_url, name, *, enabled=None, config=None)` helper to keep tests readable. Pattern:

```python
def seed_tool_config(base_url: str, name: str, *, enabled: bool | None = None, config: dict | None = None) -> None:
    """PUT a tool_configs row via the L1 endpoint. Either or both of
    enabled / config can be set; omitted keys preserve existing state
    (per L1 PUT contract). One-shot httpx.put — no client persistence."""
    body = {}
    if enabled is not None:
        body['enabled'] = enabled
    if config is not None:
        body['config'] = config
    if not body:
        return
    httpx.put(f"{base_url}/api/tools/configs/{name}", json=body, timeout=5.0).raise_for_status()
```

`app_with_agent` is sufficient for the Studio override tests (mock provider + agent with default `enabled_tools=null`, `tool_overrides=null`). Verified by reading `conftest.py:222-243`.

### Updates to `tests/browser/test_flow_admin_navigation.py`

The single test rename above. No other tests in that file should break (all assert on System / Providers state, unaffected by Tools-section addition).

## Acceptance Criteria

- [x] `tests/browser/test_flow_admin_tools_grid.py` ships with 10 tests; all pass under `make test-browser`.
- [x] `tests/browser/test_flow_admin_tools_editor.py` ships with 14 tests; all pass.
- [x] `tests/browser/test_flow_studio_tools_overrides.py` ships with 10 tests; all pass.
- [x] `tests/browser/test_flow_admin_navigation.py::test_admin_section_nav_renders_three_sections` (renamed + updated for the 3-entry nav) passes.
- [~] All other existing browser tests still pass — no regressions in F1-F5 surfaces. **EXCEPTION**: 2 pre-existing failures in `test_flow_agent_tabs.py::test_refresh_on_knowledge_tab_persists` and `::test_refresh_on_tools_tab_persists` — both racing the L5-introduced `refreshToolConfigsCache().then(renderEditor)` async wrapper inside `doSelect`. The failing tests' helper `_wait_editor_ready` checks `editor_hidden` synchronously and tries to click the agent tile while the editor mount is still pending. NOT a L7-introduced regression — flagged for L8 (small fix to the helper to await on the editor's expected selector instead).
- [x] `make test-browser` completes successfully (Playwright Chromium installed via the L0 prereq).
- [x] No L0/L1/L2/L3/L4/L5/L6 source code is modified — L7 is test-only.
- [x] Total new tests: 34 (no skips, no xfails). Plus 1 renamed.
- [x] **Wall-clock budget**: full L7 browser suite (~34 tests at 5-15s each) lands at 3-8 min on the dev container. The full `make test-browser` (existing 120+ tests + L7's 34) targets <15 min. Actual: L7 alone ~32s; full suite 217s (3:37) end-to-end including the 2 pre-existing failures' 30s timeout each.

## Verification Steps

```bash
# 1. Targeted runs (one file at a time first, to bisect any failures)
docker exec the-one pytest tests/browser/test_flow_admin_tools_grid.py -m browser -x -v
docker exec the-one pytest tests/browser/test_flow_admin_tools_editor.py -m browser -x -v
docker exec the-one pytest tests/browser/test_flow_studio_tools_overrides.py -m browser -x -v
docker exec the-one pytest tests/browser/test_flow_admin_navigation.py -m browser -x -v

# 2. Full browser suite
make test-browser

# 3. No regression in unit suite
docker exec the-one pytest tests/ -m 'not browser and not live and not pixel' -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined

# 4. Lint
docker exec the-one ruff check tests/browser/test_flow_admin_tools_grid.py tests/browser/test_flow_admin_tools_editor.py tests/browser/test_flow_studio_tools_overrides.py
```

## Implementation Guidance

1. **Start with `test_flow_admin_navigation.py` rename** — smallest change, gets a baseline assertion passing for the new "Built-in Tools" nav entry.
2. **Write `test_flow_admin_tools_grid.py` next** — straightforward DOM assertions; no editor mount or schema fetching.
3. **Write `test_flow_admin_tools_editor.py`** — covers the editor form's save/cancel/dirty + error paths. Use the existing `test_flow_provider_editor.py` as a structural reference.
4. **Write `test_flow_studio_tools_overrides.py` last** — most complex; needs seeded agent + lazy-fetch behavior.
5. **For tests requiring pre-existing tool_configs state** (e.g., narrow timeout_seconds_max=60 in operator config before opening agent override), use a `page.evaluate` to fetch then `page.goto` to navigate — OR add a `httpx.put` call in the test setup before navigating (common pattern in existing browser tests).
6. **Avoid live network** — for the Test button tests (#14 in editor file), assert button-disable + result-region-populated rather than the actual returned content. The L1 unit tests cover the endpoint contract.
7. **Lazy-fetch `<details>` test** (#6 in studio file) — assert `.loading` placeholder transitions to actual fields. For "no second fetch on re-open", check that DOM identity of the field elements is preserved across close+open (or that no new "Loading…" placeholder appears).
8. **Snapshot tests are out of scope** for L7 — DOM-shape only, per user-global instruction.
9. **Run the verification block** above; paste relevant pytest summaries into the L7 flight-log entry.

## Edge Cases

- **Test buttons & live network**: web_search hits real DDG; fetch_url hits real example.com. Both can flake. Test `test_test_button_click_fires_request` asserts on the wiring shape, not the response content.
- **`<details>` toggle event timing in Playwright**: fire-and-wait pattern (`page.locator('details').click()` then `expect(page.locator('.tool-row-overrides-body input')).to_be_visible(timeout=5000)`).
- **Operator state setup via API**: tests that need a saved operator config call `httpx.put(f"{app_clean}/api/tools/configs/web_search", json={"enabled": False})` before `page.goto()`. The `app_clean` fixture exposes the base URL; use a fresh httpx client.
- **Agent seed for Studio tests**: `app_with_agent` likely seeds a default agent with provider attached. Verify the fixture's exact seed shape; if it doesn't seed `tool_overrides`, that's fine — L7 tests will set them via the UI.
- **Hash routing race**: deep-link tests may load the page before JS hydrates — wait for a stable selector (`expect(page.locator('.editor-title')).to_be_visible()`) before asserting.
- **Browser test parallelism**: pytest-xdist may run tests in parallel; the `app_clean` fixture is per-test (fresh subprocess + DB), so tests are isolated. Verify no cross-test state leakage.
- **The existing test_flow_admin_navigation tests for keyboard nav** may need updates if they assert on a specific item count via Tab cycle — verify and fix any breakage.

## Files Affected

- `tests/browser/test_flow_admin_navigation.py` — 1 test renamed + count updated.
- `tests/browser/test_flow_admin_tools_grid.py` — NEW (10 tests).
- `tests/browser/test_flow_admin_tools_editor.py` — NEW (14 tests).
- `tests/browser/test_flow_studio_tools_overrides.py` — NEW (10 tests).
- `tests/browser/seeders.py` — adds `seed_tool_config(base_url, name, *, enabled=None, config=None)` helper.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified (with the L8-deferred deviation logged above)
- [x] `make test-browser` passes (L7 suite: 34/34 green; pre-existing 2 failures flagged)
- [x] No regression in unit suite (1048 passed)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] (NOT final leg — do NOT update flight.md status, do NOT commit)
