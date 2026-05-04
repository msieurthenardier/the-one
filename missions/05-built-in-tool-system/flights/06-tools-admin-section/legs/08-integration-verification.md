# Leg: 08-integration-verification

**Status**: landed
**Flight**: [Tools Admin Section](../flight.md)

## Objective

Final integration sweep before the L0-L8 batch goes to the first Reviewer. Verifies (a) the full unit + browser test suites are green, (b) F6 regression sweeps return zero unexpected matches, (c) the F4 + F5 surfaces still work end-to-end, (d) mission Open Questions are closed. Includes one targeted fix from L7's discovery: 2 pre-existing failures in `tests/browser/test_flow_agent_tabs.py::test_refresh_on_{knowledge,tools}_tab_persists` that race the L5-introduced async `refreshToolConfigsCache().then(renderEditor)` wrapper. **NO documentation updates** in this leg — that's L9 post-Reviewer (per F6 Decision 12).

## Context

- **F6 Decision 12** (two-Reviewer-pass batching): L8 is the last leg before the first Reviewer pass over the L0-L8 batch. Documentation deferred to L9.
- **L7 deviation**: 2 tests in `test_flow_agent_tabs.py` race the L5 async editor mount. The L7 leg flagged these as pre-existing failures introduced by L5's `refreshToolConfigsCache().then(renderEditor)` wrapper around the editor mount. The `_wait_editor_ready` helper at line 29 doesn't wait for the deep-linked tab's intended content to render — it only waits for `tab-general` to be visible, then proceeds. Deep-link tests for `/knowledge` and `/tools` then assert on the tab-specific content with an 8s timeout that's not enough.
- **Fix scope**: minimal — patch `_wait_editor_ready` to optionally accept an expected tab id (defaults to `general`) and wait for that tab's `aria-selected="true"` before returning. The 2 failing tests pass `tab-knowledge` and `tab-tools` respectively. All other call sites pass nothing → default `general` → behavior unchanged.
- **Mission Open Questions**: F6 closes the "Tools admin section placement" question (resolved: peer to System / LLM Providers). The mission has no other F6-scoped open questions to mark.
- **Regression sweep targets**:
  - L0: schema v9 column exists; existing tool_configs rows decode `enabled=True`.
  - L1: 4 admin endpoints respond; factory excludes operator-disabled tools.
  - L2: admin grid renders with category tabs.
  - L3: per-tool editor saves; dirty/cancel/back gates work.
  - L4: test buttons fire the right endpoints with custom inputs.
  - L5: Studio override panels lazy-load; tool_overrides round-trips.
  - L6 inline fixes: 500→422 PUT, error banner, info icons, custom test inputs, "Built-in Tools" label, iOS-toggle position fix, chip-list studio styling.
  - L7: 41 browser tests pass.
  - F1-F5 surfaces: filesystem tools, execution tools, web tools, all unchanged.

## Inputs

- `tests/browser/test_flow_agent_tabs.py:29-44` — the `_wait_editor_ready` helper to widen.
- All L0-L7 source + tests (the verification target).
- `Makefile:103-121` — test targets (`test-unit`, `test-browser`, `test-pixel`, `test-live`).

## Outputs

### Fix — `tests/browser/test_flow_agent_tabs.py`

Widen `_wait_editor_ready(page, expected_tab='general')` to accept an expected tab id and await its `aria-selected="true"` after the existing assertions:

```python
def _wait_editor_ready(page: Page, expected_tab: str = 'general') -> None:
    """Wait for the agent editor to be the visible child in the main panel.
    
    expected_tab: which tab is expected to be active after the editor mounts.
    Defaults to 'general' for tests that select an agent without specifying
    a tab. Deep-link tests (/knowledge, /tools) override this so the helper
    waits for the deep-linked tab's `aria-selected="true"` before returning,
    avoiding the race with L5's async `refreshToolConfigsCache().then(renderEditor)`
    wrapper.
    """
    expect(page.locator(".section-nav-header")).to_have_text("Studio", timeout=8000)
    editor_hidden = page.evaluate(
        "() => document.querySelector('.studio-editor')?.classList.contains('is-hidden')"
    )
    if editor_hidden:
        page.locator("button.entity-tile").first.click()
    expect(page.locator(f'[data-testid="tab-{expected_tab}"]')).to_be_visible(timeout=8000)
    # Wait for the expected tab to be active (handles the L5 async editor-mount race)
    expect(page.locator(f'[data-testid="tab-{expected_tab}"]')).to_have_attribute(
        "aria-selected", "true", timeout=8000
    )
```

Update the 2 failing tests:
- `test_refresh_on_knowledge_tab_persists`: change `_wait_editor_ready(page)` → `_wait_editor_ready(page, expected_tab='knowledge')`.
- `test_refresh_on_tools_tab_persists`: same → `expected_tab='tools'`.

All other call sites (`_wait_editor_ready(page)`) unchanged — default `'general'` matches their existing semantics.

### Mission Open Questions update — `missions/05-built-in-tool-system/mission.md`

Mark the F6 open question as resolved if not already. Look for "Tools admin section placement" or similar; mark `[x]` with note "Resolved in F6 (peer to System / LLM Providers per Decision 1)".

### Verification block — runs only, no code output

Run the full verification block in this leg's Verification Steps section. Paste the relevant pytest summaries + grep counts into the L8 flight log entry.

### Regression sweep — grep counts

Per the F6 spec's L8 sweep:
```bash
docker exec the-one rg -n 'enabled INTEGER NOT NULL DEFAULT 1' the_one/db/schema.py  # 1
docker exec the-one rg -n 'GET /api/tools/configs|PUT /api/tools/configs|POST.*tools/configs.*test' the_one/interfaces/web/api.py  # 4 routes (plus comments)
docker exec the-one rg -n 'renderToolsGrid|renderToolsEditor' the_one/interfaces/web/static/js/areas/admin/  # 2+
docker exec the-one rg -n 'tool-row-disabled|tool-name-strike' the_one/interfaces/web/static/  # 2+ (CSS + JS)
docker exec the-one rg -n '_enrich_schema_with_markers' the_one/interfaces/web/api.py  # 1+
docker exec the-one rg -n 'TOOL_CATEGORIES' the_one/interfaces/web/static/js/areas/admin/  # 2 (tools-grid.js + tools-editor.js per L3 deviation)
```

## Acceptance Criteria

- [x] `tests/browser/test_flow_agent_tabs.py::test_refresh_on_knowledge_tab_persists` passes.
- [x] `tests/browser/test_flow_agent_tabs.py::test_refresh_on_tools_tab_persists` passes.
- [x] All other tests in `test_flow_agent_tabs.py` still pass (the helper change is backward-compatible with default arg).
- [x] `make test-unit` is green (modulo the pre-existing CSS-token deselect from L0-L7).
- [x] `make test-browser` is fully green (NO pre-existing failures remaining).
- [x] `make test-pixel` runs cleanly (snapshots are local-only per user-global instruction; just verify the suite executes without infrastructure errors).
- [x] All 6 regression-sweep greps return their expected counts (or document deviations).
- [x] Mission Open Question for F6 (section placement) marked `[x]` if not already.
- [x] **No L0-L7 source code modified** EXCEPT the targeted `_wait_editor_ready` helper change (L7 deviation follow-up).
- [x] **No documentation updates** (CLAUDE.md, README, agents.md) — those are L9 post-Reviewer.
- [x] Flight log L8 entry written with verification results.

## Verification Steps

```bash
# 1. Targeted fix verification
docker exec the-one pytest tests/browser/test_flow_agent_tabs.py -m browser -x -v

# 2. Full browser suite
make test-browser

# 3. Full unit suite
docker exec the-one pytest tests/ -m 'not browser and not live and not pixel' -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined

# 4. Pixel suite (snapshot tests; baselines local-only)
make test-pixel || echo 'Pixel suite finished (baselines may regenerate; non-blocking)'

# 5. Regression sweep
docker exec the-one rg -n 'enabled INTEGER NOT NULL DEFAULT 1' the_one/db/schema.py
docker exec the-one rg -n 'GET /api/tools/configs|PUT /api/tools/configs|POST.*tools/configs.*test' the_one/interfaces/web/api.py
docker exec the-one rg -n 'renderToolsGrid|renderToolsEditor' the_one/interfaces/web/static/js/areas/admin/
docker exec the-one rg -n 'tool-row-disabled|tool-name-strike' the_one/interfaces/web/static/
docker exec the-one rg -n '_enrich_schema_with_markers' the_one/interfaces/web/api.py
docker exec the-one rg -n 'TOOL_CATEGORIES' the_one/interfaces/web/static/js/areas/admin/

# 6. AIAT smoke (live LLM, optional — only if a local LLM is available)
# make test-live  # comment if no live LLM provider configured
```

## Implementation Guidance

1. **Apply the `_wait_editor_ready` widening** at `tests/browser/test_flow_agent_tabs.py` first.
2. **Re-run the 2 previously-failing tests** to confirm they now pass.
3. **Re-run the full `test_flow_agent_tabs.py`** to verify backward-compat (default arg path unchanged).
4. **Run the full browser suite** (`make test-browser`) — should land at 254 passed (252 baseline + 2 newly-passing).
5. **Run the full unit suite** — should still land at 1048 passed (no change from L7).
6. **Run the regression sweep greps** — paste counts to flight log.
7. **Update mission Open Questions** if needed.
8. **Write the L8 flight log entry** summarizing pass counts + sweep results.

## Edge Cases

- **`expected_tab` arg backward-compat**: default `'general'` matches all existing call sites' semantics. Tests that select an agent without a deep-link land on General (the default tab). Helper widening is purely additive.
- **L7 introduced 41 new browser tests**; baseline before L7 was ~218 tests, so the post-L8 count should be 218 + 41 = 259. Verify the actual numbers match.
- **AIAT (live LLM) tests**: out of L8's hard-required scope. The mission has no F6 AIAT changes — F6 is admin UI, not agent-runtime tool changes. Skip if no local LLM is configured.
- **CSS-token test deselect**: pre-existing red from F1-F2. Continue deselecting; do NOT introduce new red.
- **Mission Open Questions**: only F6's specific question (section placement) is in scope. Other open questions (if any) belong to other flights.

## Files Affected

- `tests/browser/test_flow_agent_tabs.py` — widen `_wait_editor_ready` helper; update 2 deep-link test call sites.
- `missions/05-built-in-tool-system/mission.md` — mark F6 Open Question resolved (if not already).

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] `make test-browser` 100% green
- [x] `make test-unit` 100% green (modulo CSS-token deselect)
- [x] Regression sweep counts paste into flight log
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] (NOT final leg — do NOT update flight.md status, do NOT commit)
- [x] **Reviewer pass over L0-L8 batch comes NEXT** — flagged in flight log that the batch is ready
