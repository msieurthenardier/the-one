# Leg: 06-flow-test-agent-crud

**Status**: completed
**Flight**: [Browser Test Foundation](../flight.md)

## Objective

Add the second end-to-end browser flow test: starting from an app pre-seeded with a `mock` provider (no agents), drive Chromium through the Studio agent CRUD flow — create an agent, see it in the sidebar, edit a field and save, then delete it. Add `data-testid` attributes to the load-bearing Studio elements so the test survives F2/F3 redesigns.

## Context

- This is the second flow test (legs 05/07 are the others). Uses the `app_with_provider` fixture from leg 04 (mock provider already created via API; no agents yet).
- Per the flight design (see `flight.md` "Selector strategy"): each flow leg adds 3-5 `data-testid` attributes. This leg targets Studio elements that the test interacts with.
- **Studio editor structure** (verified): `studio.js:1-680`
  - Sidebar `+` button: `.new-agent-btn` (line 30) — enters create mode
  - Empty state: `.agent-empty` (line 81) "No agents yet. Click + to create one."
  - Agent list items: `.agent-item` (line 88) with `data-name="<name>"`. Inline delete `×` is `.agent-item-delete` (line 98) — uses two-click confirm pattern at line 132.
  - Editor "New Agent" header (line 197) for create mode; agent name + Delete Agent button (line 200) for edit mode
  - Form fields: `[data-field="name"]` (line 209, only in create), `[data-field="description"]` (line 211), `#studio-provider` (line 219), `#studio-model` (line 238), `[data-field="system_prompt"]` (line 251)
  - Save button: `.save-btn` (line 308) — text "Create" in create mode, "Save" in edit mode
  - Delete button (in editor header): `.delete-btn` (line 200) — uses two-click confirm pattern at line 410-430
- **Save flow** (`save()` function at studio.js:612-676):
  - Create (line 616-644): POSTs `/api/agents`, then `loadAll()` re-fetches, then `selectAgent(found)` switches the editor into edit mode for the new agent
  - Update (line 645-675): PUTs `/api/agents/{name}`, then `loadAll()`, then re-renders editor
- **Provider dropdown auto-selects first provider** when no `provider_config_id` set (line 175-176): the create form will start with the mock provider already selected
- **Model dropdown** (`fetchModelsForProvider`, line 322-364): fires on provider-change, populates from `/api/providers/{id}/models`. For mock provider, returns `[{"id": "mock-default", "name": "mock-default"}]` per leg 02. Auto-fetches on initial render if `provider_config_id` is set (line 384-388).
- **Leg 05 deviation note**: Implementing Developer found and fixed an admin.js validation bug. Be aware that studio.js may have similar bugs — test will surface them. Do not modify studio.js to "make the test work" except to add `data-testid` attributes; if a real UX bug surfaces, fix it as a deliberate inline fix and document.

## Inputs

- Branch `flight/01-browser-test-foundation`, legs 01-05 landed (uncommitted)
- `tests/browser/conftest.py` has `app_with_provider` fixture (subprocess + 1 mock provider, no agents)
- `tests/browser/seeders.py` has `SeededApp` dataclass with `base_url`, `provider_id`
- Studio selectors verified above
- Test baseline: 350 passed, 14 deselected (post-leg-05)

## Outputs

- `tests/browser/test_flow_agent_crud.py` (new) — single end-to-end agent CRUD flow test
- `the_one/interfaces/web/static/js/areas/studio.js` — add `data-testid` attributes to:
  - `.new-agent-btn` → `data-testid="new-agent-btn"`
  - `.agent-item` (sidebar items, repeater) → `data-testid="agent-item"`
  - `.save-btn` (editor save/create) → `data-testid="save-agent-btn"`
  - `.delete-btn` (editor delete) → `data-testid="delete-agent-btn"`
  - `.agent-empty` (empty state) → `data-testid="agent-empty"`
- (5 testids added — within the 3-5 budget per flow leg)

## Acceptance Criteria

### data-testid attributes

- [x] `studio.js:30` `.new-agent-btn` HTML rendered with `data-testid="new-agent-btn"`
- [x] `studio.js:88` `.agent-item` element gets `data-testid="agent-item"` set via `el.setAttribute(...)` (since this is `createElement`-based, not an HTML string)
- [x] `studio.js:308` `.save-btn` HTML rendered with `data-testid="save-agent-btn"`
- [x] `studio.js:200` `.delete-btn` HTML rendered with `data-testid="delete-agent-btn"`
- [x] `studio.js:81` `.agent-empty` element gets `data-testid="agent-empty"` set via `setAttribute`

### Test

- [x] `tests/browser/test_flow_agent_crud.py` exists with one `@pytest.mark.browser` test: `test_studio_agent_crud_flow`
- [x] Test uses `app_with_provider` and `page` fixtures
- [x] Test asserts the following sequence:
  1. Open `#studio` → empty state visible (`[data-testid="agent-empty"]` with text "No agents yet")
  2. Click `[data-testid="new-agent-btn"]` (the `+`) → editor shows "New Agent"
  3. Fill `[data-field="name"]` with "test-agent"
  4. Fill `[data-field="description"]` with "An agent for tests"
  5. Provider dropdown (`#studio-provider`) auto-selects the seeded mock provider
  6. Wait for `#studio-model` to populate (model "mock-default" appears as an option)
  7. Select option "mock-default" in `#studio-model`
  8. Fill `[data-field="system_prompt"]` with "You are a test agent."
  9. Click `[data-testid="save-agent-btn"]` (the Create button)
  10. Sidebar now contains `[data-testid="agent-item"]` with name "test-agent"
  11. Editor switches to edit mode — `.editor-title` reads "test-agent", `[data-testid="delete-agent-btn"]` is visible
  12. **Edit**: change `[data-field="description"]` to "Edited description"
  13. Click `[data-testid="save-agent-btn"]` (now reads "Save") → wait for re-render → description input value is "Edited description"
  14. **Delete**: click `[data-testid="delete-agent-btn"]` once (two-click confirm pattern) → text becomes "Confirm Delete?"
  15. Click `[data-testid="delete-agent-btn"]` again → DELETE fires → agent removed from sidebar → empty state visible again

### Suite-level

- [x] `pytest -m browser tests/browser/ -v` shows 7 passed (smoke + 2 app-fixture + 2 seeder + 2 flow)
- [x] Default `pytest tests/`: 350 passed, 15 deselected (was 14; +1)
- [x] No existing test regressions
- [x] `ruff check tests/browser/` and `ruff format --check tests/browser/` clean

## Verification Steps

1. **Test passes**: `pytest -m browser tests/browser/test_flow_agent_crud.py -v --timeout=60`
2. **Repeat-run stability** (3 consecutive runs):
   ```bash
   for i in 1 2 3; do pytest -m browser tests/browser/test_flow_agent_crud.py -q --timeout=60 || { echo "FAIL $i"; exit 1; }; done
   ```
3. **No regression**: `pytest tests/ --tb=short -q --timeout=60` → 350 passed, 15 deselected
4. **All browser tests**: `pytest -m browser tests/browser/ -v --timeout=60` → 7 passed
5. **Lint/format**: `ruff check tests/browser/ && ruff format --check tests/browser/`
6. **Manual sanity (optional)**: Run `THE_ONE_DEV_MODE=true the-one serve`, manually create a mock provider, then walk through the agent CRUD flow

## Implementation Guidance

### 1. Add `data-testid` attributes to studio.js

Two patterns are used in the file:
- **HTML-string rendering** (sidebar header, editor): add `data-testid="..."` directly in the string
- **`createElement` rendering** (agent list items, empty state): use `.setAttribute('data-testid', '...')` after creation

**`.new-agent-btn`** (sidebar header, line 30 — HTML string):

```javascript
'<button class="new-agent-btn" data-testid="new-agent-btn">+</button>' +
```

**`.agent-empty`** (line 80-83 — createElement):

```javascript
var empty = document.createElement('div');
empty.className = 'agent-empty';
empty.setAttribute('data-testid', 'agent-empty');
empty.textContent = 'No agents yet. Click + to create one.';
agentListEl.appendChild(empty);
```

**`.agent-item`** (line 88 — createElement, in the `for` loop):

```javascript
var el = document.createElement('div');
el.className = 'agent-item' + (selectedAgent && selectedAgent.name === agent.name && !createMode ? ' active' : '');
el.dataset.name = agent.name;
el.setAttribute('data-testid', 'agent-item');
```

**`.delete-btn`** (line 200 — HTML string in editor header):

```javascript
html += '<button class="delete-btn" data-testid="delete-agent-btn" data-name="' + escapeHtml(cfg.name) + '">Delete Agent</button>';
```

**`.save-btn`** (line 308 — HTML string in editor actions):

```javascript
html += '<button class="save-btn clean" data-testid="save-agent-btn">' + (isCreate ? 'Create' : 'Save') + '</button>';
```

### 2. Create `tests/browser/test_flow_agent_crud.py`

```python
"""End-to-end flow test: Studio agent CRUD.

Drives a real Chromium session through the agent lifecycle:
- Empty Studio (mock provider already seeded by fixture)
- Click + to create an agent
- Fill form (name, description, provider, model, system prompt)
- Click Create — agent appears in sidebar, editor switches to edit mode
- Edit description, click Save — change persists
- Click Delete (two-click confirm) — agent removed, empty state restored
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from browser.seeders import SeededApp


@pytest.mark.browser
def test_studio_agent_crud_flow(app_with_provider: SeededApp, page: Page) -> None:
    base_url = app_with_provider.base_url

    # 1. Open Studio. Empty state shows "No agents yet".
    page.goto(f"{base_url}#studio")
    empty = page.locator('[data-testid="agent-empty"]')
    expect(empty).to_be_visible()
    expect(empty).to_contain_text("No agents yet")

    # 2. Click + to enter create mode.
    page.locator('[data-testid="new-agent-btn"]').click()
    expect(page.locator(".editor-title")).to_have_text("New Agent")

    # 3-4. Fill name and description.
    page.locator('[data-field="name"]').fill("test-agent")
    page.locator('[data-field="description"]').fill("An agent for tests")

    # 5. Provider dropdown auto-selected (only one — the seeded mock provider).
    expect(page.locator("#studio-provider")).to_have_value(app_with_provider.provider_id)

    # 6-7. Wait for model dropdown to populate; select "mock-default".
    #      The fetch fires on initial render via fetchModelsForProvider.
    expect(page.locator('#studio-model option[value="mock-default"]')).to_be_attached(
        timeout=5000
    )
    page.locator("#studio-model").select_option("mock-default")

    # 8. Fill system prompt.
    page.locator('[data-field="system_prompt"]').fill("You are a test agent.")

    # 9. Click Create.
    page.locator('[data-testid="save-agent-btn"]').click()

    # 10. Sidebar contains exactly one new agent item with our name.
    agent_item = page.locator('[data-testid="agent-item"]')
    expect(agent_item).to_have_count(1)
    expect(agent_item).to_contain_text("test-agent")

    # 11. Editor switched to edit mode — title shows agent name, Delete Agent visible.
    expect(page.locator(".editor-title")).to_have_text("test-agent")
    delete_btn = page.locator('[data-testid="delete-agent-btn"]')
    expect(delete_btn).to_be_visible()
    expect(delete_btn).to_have_text("Delete Agent")

    # 12-13. Edit description, save, verify persisted (re-render keeps the value).
    description_input = page.locator('[data-field="description"]')
    description_input.fill("Edited description")
    page.locator('[data-testid="save-agent-btn"]').click()
    # After save, editor re-renders with updated agent. Description still set.
    expect(page.locator('[data-field="description"]')).to_have_value(
        "Edited description", timeout=5000
    )

    # 14. First click on Delete — confirm state ("Confirm Delete?").
    delete_btn.click()
    expect(delete_btn).to_have_text("Confirm Delete?")

    # 15. Second click — DELETE fires, agent removed, empty state returns.
    delete_btn.click()
    expect(empty).to_be_visible(timeout=5000)
    expect(empty).to_contain_text("No agents yet")
    # Agent item gone from sidebar; editor returns to its empty state.
    expect(page.locator('[data-testid="agent-item"]')).to_have_count(0)
    expect(page.locator(".editor-empty")).to_be_visible()
```

> **Why `to_be_attached` for the model option**: The model dropdown is async-populated by `fetchModelsForProvider`. `to_be_visible()` may not work because `<option>` elements are technically inside their `<select>` and Playwright's visibility model treats them oddly. `to_be_attached` waits for the element to exist in the DOM, which is what we need before `select_option`.

> **Why `to_have_value` rather than `to_contain_text` for inputs**: Form inputs use `value`, not text content. `to_have_value` is the correct Playwright assertion.

> **Two-click delete pattern**: studio.js:410-430 wraps the second click in a 3s timeout window. The test clicks twice in immediate sequence (well within the window). If the test ever flakes on this, consider asserting "Confirm Delete?" before the second click to add a real wait.

### 3. Run verification

```bash
pytest -m browser tests/browser/test_flow_agent_crud.py -v --timeout=60
pytest -m browser tests/browser/ -v --timeout=60
pytest tests/ --tb=short -q --timeout=60
ruff check tests/browser/
ruff format --check tests/browser/
```

### 4. Repeat-run stability check

```bash
for i in 1 2 3; do
  pytest -m browser tests/browser/test_flow_agent_crud.py -q --timeout=60 \
    || { echo "FAILED on run $i"; exit 1; }
done
```

If any run fails, diagnose specifically — most likely culprits are async race on model-dropdown population (use `to_be_attached` with longer timeout) or the two-click delete pattern (verify the "Confirm Delete?" wait between clicks).

## Edge Cases

- **`fetchModelsForProvider` race on form open**: The form renders before the model fetch completes. Playwright's `select_option("mock-default")` auto-waits for the option to exist via `to_be_attached`, but if the test ever observes a "Choose a model" disabled option being matched, the model fetch hasn't completed yet. Add an explicit wait.

- **Provider auto-select assumption**: The test asserts `#studio-provider` has value `app_with_provider.provider_id` immediately. This works because `cfg.provider_config_id` defaults to `allProviders[0].id` when there's no agent (line 176). If a future change makes the dropdown require explicit user selection, this assertion would fail — the fix is to call `select_option(...)` explicitly.

- **`save-btn` class change after save**: The save button class is `save-btn clean` initially, becomes `save-btn dirty` when the user types, becomes `save-btn clean` again after save. The `[data-testid="save-agent-btn"]` selector is stable across these changes.

- **`createMode = false` after Create**: Once the agent is created, `createMode` is reset and `selectAgent(found)` re-renders the editor in edit mode. The Name input no longer appears (line 208 — only rendered when `isCreate`). The test doesn't try to interact with `[data-field="name"]` after create.

- **Two-click delete timing**: studio.js:426-429 has a 3000ms timeout that resets the confirm state. The test's two clicks are back-to-back (sub-100ms), well within the window. If the test process is slow (high system load), the second click could miss the window — but this would be a pathological case.

- **`loadAll()` after delete**: After successful DELETE, `loadAll()` re-fetches `/api/agents` (now empty), `renderAgentList()` shows empty state, then `renderEmptyEditor()` shows "Select an agent or click + to create one." in the editor area. The test asserts the empty state in the sidebar (`[data-testid="agent-empty"]`).

- **`selectedAgent.name` after delete**: When deleting from the editor's Delete Agent button (`.delete-btn`, line 408-431), `selectedAgent = null` is set BEFORE `loadAll()` (line 414). So the editor is left in an "empty editor" state, not re-selecting another agent. The test verifies sidebar empty state but doesn't assert on the editor — could add `expect(page.locator(".editor-empty")).to_be_visible()` for completeness.

- **Confirm dialog on dirty discard**: `selectAgent` and `enterCreateMode` use `confirm()` (browser dialog) if `dirty=true` (lines 146, 158). The test never triggers this path because it always saves before switching modes. If a future test variant doesn't, it would need to register a Playwright dialog handler (`page.on("dialog", lambda d: d.accept())`).

- **Settings panel default**: Studio's right panel shows the editor; there's no "general/providers/system" sub-categorization like Admin. The test doesn't need any sub-navigation.

## State-Machine Reachability Audit

**State exercised**: agent count 0 → 1 (after Create) → 1 (after Save, no count change) → 0 (after Delete). Editor mode: empty → create → edit → empty.

Lower layers verified:
- DB: `agents` table has no FK to providers (M03 debrief intentional design — `agent_name` is free-text in `chat_sessions` to allow agent deletion without cascading session deletes). Mock provider deletion would not cascade to agent. ✓
- API: `POST /api/agents` accepts `provider_config_id` as an arbitrary string; no FK validation. ✓
- API: `DELETE /api/agents/{name}` returns 200; ChatSession refs to deleted agent become "agent_deleted" health status (M03 design). The test doesn't create sessions, so no orphan to worry about. ✓
- JS: `loadAll()` after delete refreshes both list and providers, ensuring sidebar reflects current state. ✓

No existing tests pin behavior this leg breaks. ✓ Pass.

## Cache Freshness Contract

**Cache 1 — `agents` JS variable in studio.js** (existing, not introduced by this leg):
- Source of truth: `/api/agents`
- Rebuild trigger: `loadAll()` called on every save (line 633, 660), every delete (line 121, 416), and on Studio area init
- Maximum staleness acceptable: until next save/delete/area-switch
- User-action invalidation map: create/edit/delete all trigger `loadAll()`. ✓ No mismatches.

**Cache 2 — `selectedAgent` JS variable** (existing):
- Source of truth: the most-recently-selected agent in `agents`
- Rebuild trigger: every `selectAgent()` call, set to `null` on delete
- Maximum staleness acceptable: until next user action that changes selection
- User-action invalidation map: select → set, delete → clear, create → set to created agent post-loadAll. ✓

**Cache 3 — `dirty` JS variable** (existing):
- Tracks unsaved form changes
- Reset to `false` on save success and on agent switch
- User-action invalidation: input/change events → `checkDirty` → set true; save success → false; switch agent → false (with confirm dialog if true)

**No new caches introduced.** ✓ Pass.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio.js` — 5 lines modified (3 HTML strings get `data-testid="..."`, 2 `setAttribute` calls added for createElement-based elements)
- `tests/browser/test_flow_agent_crud.py` — new (~80 LOC, 1 test)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing: `pytest tests/` shows 350 passed, 15 deselected; `pytest -m browser tests/browser/` shows 7 passed
- [x] 3 consecutive runs of the new flow test pass
- [x] `ruff check tests/browser/` and `ruff format --check tests/browser/` clean
- [x] Update flight-log.md with leg progress entry (status, what was done, any anomalies — note any UX bugs caught like leg 05's base_url validation issue)
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Do NOT check off this leg in flight.md (happens at flight-level commit time)
- [x] Do NOT commit (flight-level review and commit happen after the last autonomous leg)
- [x] Signal `[HANDOFF:review-needed]`
