# Leg: 05-flow-test-provider-setup

**Status**: completed
**Flight**: [Browser Test Foundation](../flight.md)

## Objective

Add the first end-to-end browser flow test: starting from an empty DB, drive a real Chromium session through the UI to (1) confirm the first-start setup banner appears in Chat, (2) navigate to Admin → LLM Providers and add a `mock` provider via the form, (3) click Test Connection and confirm success, (4) verify the new provider shows in the list with a `mock` badge, (5) navigate back to Chat and confirm the banner now says "No agents configured." Add `data-testid` attributes to load-bearing UI elements so the test survives F2/F3 redesigns.

## Context

- This is the first **flow** test against the live app — until now, browser tests were toolchain validation (smoke) or fixture validation (app/seeders). Legs 06-07 follow the same pattern for the agent-CRUD and chat flows.
- Per the flight design (see `flight.md` "Selector strategy"): each flow leg adds 3-5 `data-testid` attributes to load-bearing elements so tests survive F2/F3 redesign without re-selectoring. This is on-budget and prevents the regression net from dissolving the moment F2 starts.
- **Leg 02 outcome**: `mock` provider type is gated by `THE_ONE_DEV_MODE=true`. The `app_clean` fixture from leg 03 already sets this, so the `mock` option is visible in the provider-type dropdown.
- **Leg 04 outcome**: `app_with_provider`/`app_with_agent` fixtures exist for legs 06-07. This leg uses `app_clean` (empty DB) because the test IS the provider-setup flow.
- **Banner location**: `chat.js:196-228` (`checkSetupState()`) creates a `<div class="chat-no-providers">` banner with one of three texts depending on whether providers and agents exist.
- **Provider form**: `admin.js:438-520` (`renderProviderForm` / `_renderProviderFormImpl`). Has `id="pf-name"`, `id="pf-type"`, `id="pf-base-url"`, `id="pf-api-key"` (existing stable selectors). Save button is `.admin-pf-save`. Test Connection button is `.admin-pf-test` (only visible in edit mode — appears after Create).
- **Mock type form behavior**: Per leg 02, `TYPE_DEFAULTS["mock"] = { showBaseUrl: false, showApiKey: false }` — selecting `mock` hides both base_url and api_key inputs. The test exploits this (only fills name + selects type).
- **Area navigation**: Hash-based (`#chat`, `#admin`). Per the mission's open question on routing, this WILL be extended in F3 to support sub-paths. For now, `page.goto(f"{base_url}#admin")` is the cleanest test mechanism. F3 may need to update the test, which is fine.
- **Admin sub-category navigation**: Admin defaults to "general" category; the "LLM Providers" category requires a click. Selector: `.admin-category-item` with text "LLM Providers".
- **Test Connection result for mock**: Per leg 02 `test_provider` branch, returns `{"status": "ok", "detail": "Mock provider (dev mode)"}`. UI shows this in `.admin-pf-test-result`.

## Inputs

- Branch `flight/01-browser-test-foundation`, legs 01-04 landed (uncommitted)
- `tests/browser/conftest.py` has `app_clean`, `browser`, `page`, plus `app_with_provider`/`app_with_agent` fixtures
- Existing selectors verified to be stable for this test (`#pf-name`, `#pf-type`, `.admin-pf-save`, `.admin-pf-test`, `.chat-no-providers`, `.admin-category-item`, `.admin-provider-add-btn`, `.admin-provider-edit-btn`, `.admin-provider-card`, `.admin-pf-test-result`)
- Test baseline: 350 passed, 13 deselected (post-leg-04)

## Outputs

- `tests/browser/test_flow_provider_setup.py` (new) — single end-to-end flow test
- `the_one/interfaces/web/static/js/areas/chat.js` — add `data-testid="setup-banner"` to the `.chat-no-providers` banner element
- `the_one/interfaces/web/static/js/areas/admin.js` — add `data-testid` attributes to:
  - The "+ Add Provider" button (`data-testid="add-provider-btn"`)
  - The `.admin-provider-card` repeater (`data-testid="provider-card"`)
  - The Save button (`data-testid="save-provider-btn"`)
  - The Test Connection button (`data-testid="test-connection-btn"`)
- (Total `data-testid` attributes added: 5 — within the 3-5 budget per flow leg)

## Acceptance Criteria

### data-testid attributes
- [x] `chat.js` line ~216 (`bannerEl.className = 'chat-no-providers';`) is followed by `bannerEl.setAttribute('data-testid', 'setup-banner');` (or equivalent — applied at element creation)
- [x] `admin.js` `.admin-provider-add-btn` element is rendered with `data-testid="add-provider-btn"` (in the HTML string)
- [x] `admin.js` `.admin-provider-card` element is rendered with `data-testid="provider-card"` (in the HTML string)
- [x] `admin.js` `.admin-pf-save` element is rendered with `data-testid="save-provider-btn"`
- [x] `admin.js` `.admin-pf-test` element is rendered with `data-testid="test-connection-btn"`

### Test
- [x] `tests/browser/test_flow_provider_setup.py` exists with one `@pytest.mark.browser` test: `test_first_start_provider_setup_flow`
- [x] Test uses `app_clean` and `page` fixtures
- [x] Test asserts the following sequence (note: after Create succeeds, `admin.js:665-670` auto-switches the form to edit mode — the test exploits this rather than navigating back to the list first):
  1. Open `app_clean` base URL → setup banner has `data-testid="setup-banner"` and text containing "Getting started"
  2. Navigate to `#admin`, click the "LLM Providers" category
  3. Click `[data-testid="add-provider-btn"]`
  4. Fill `#pf-name` with "Mock Test"
  5. Select option "mock" in `#pf-type` (auto-hides `#pf-base-url` and `#pf-api-key`)
  6. Click `[data-testid="save-provider-btn"]` (Create button)
  7. Form auto-switches to edit mode — `.admin-title` reads "Edit Provider", `[data-testid="test-connection-btn"]` becomes visible
  8. Click `[data-testid="test-connection-btn"]`
  9. `.admin-pf-test-result` contains "Mock" (success state from leg-02 mock test_provider branch)
  10. Click `.admin-pf-cancel` to return to the provider list
  11. `[data-testid="provider-card"]` is visible with name "Mock Test" and `.admin-provider-badge` text "mock"
  12. Navigate to `#chat`, banner now contains "No agents"

### Suite-level
- [x] `pytest -m browser tests/browser/ -v` shows 6 passed (smoke + 2 app-fixture + 2 seeder + 1 flow)
- [x] Default `pytest tests/`: 350 passed, 14 deselected (was 13; +1 from new flow test)
- [x] Existing tests still pass; no regressions
- [x] `ruff check tests/browser/` and `ruff format --check tests/browser/` clean

## Verification Steps

1. **Test passes**: `pytest -m browser tests/browser/test_flow_provider_setup.py -v --timeout=60`
2. **Repeat-run stability**: 3 consecutive successful runs
   ```bash
   for i in 1 2 3; do pytest -m browser tests/browser/test_flow_provider_setup.py -q --timeout=60 || { echo "FAIL $i"; exit 1; }; done
   ```
3. **No regression**: `pytest tests/ --tb=short -q --timeout=60` → 350 passed, 14 deselected
4. **All browser tests pass**: `pytest -m browser tests/browser/ -v --timeout=60` → 6 passed
5. **Lint/format**: `ruff check tests/browser/ && ruff format --check tests/browser/`
6. **Manual sanity (optional)**: Run `THE_ONE_DEV_MODE=true the-one serve` and walk through the same flow in a real browser to confirm the test mirrors actual UX

## Implementation Guidance

### 1. Add `data-testid` attributes

**`the_one/interfaces/web/static/js/areas/chat.js`**: In `checkSetupState()` (line 196-228), after the line that creates the banner div:

```javascript
bannerEl = document.createElement('div');
bannerEl.className = 'chat-no-providers';
bannerEl.setAttribute('data-testid', 'setup-banner');
messagesEl.parentNode.insertBefore(bannerEl, messagesEl);
```

**`the_one/interfaces/web/static/js/areas/admin.js`**:

In `renderProvidersPanel()` (line ~289), update the Add button HTML:

```javascript
'<button class="admin-provider-add-btn" data-testid="add-provider-btn">+ Add Provider</button>'
```

In `renderProviderList()` (line ~338), update the card HTML:

```javascript
'<div class="admin-provider-card" role="listitem" data-testid="provider-card" data-id="' + escapeAttr(p.id) + '">'
```

In `_renderProviderFormImpl()` (around line 515 — review found leg's line ref of ~494 was off; the function starts at line 461 but the Save button HTML is at ~515), update the Save button:

```javascript
html += '<button class="admin-pf-save" data-testid="save-provider-btn">' + (isEdit ? 'Save' : 'Create') + '</button>';
```

And the Test Connection button:

```javascript
if (isEdit) {
  html += '<button class="admin-pf-test" data-testid="test-connection-btn">Test Connection</button>';
}
```

> **Note**: All `data-testid` values are static strings (no template substitution). They are valid HTML5 (`data-*` attributes), have no styling impact, and survive F2/F3 redesigns even if the element gets renamed or moved.

### 2. Create `tests/browser/test_flow_provider_setup.py`

```python
"""End-to-end flow test: first-start provider setup.

Drives a real Chromium session through the empty-DB onboarding flow:
- See setup banner in Chat
- Navigate to Admin → LLM Providers
- Add a mock provider via the form
- Verify it appears in the list with a mock badge
- Edit it, click Test Connection, see success
- Navigate back to Chat, banner now says "No agents"
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_first_start_provider_setup_flow(app_clean: str, page: Page) -> None:
    base_url = app_clean

    # 1. Open app (defaults to #chat). Setup banner shows "Getting started".
    page.goto(base_url)
    setup_banner = page.locator('[data-testid="setup-banner"]')
    expect(setup_banner).to_be_visible()
    expect(setup_banner).to_contain_text("Getting started")

    # 2. Navigate to Admin → LLM Providers.
    page.goto(f"{base_url}#admin")
    page.locator(".admin-category-item", has_text="LLM Providers").click()

    # 3. Click + Add Provider.
    page.locator('[data-testid="add-provider-btn"]').click()

    # 4-5. Fill name, select mock type (auto-hides base_url and api_key inputs).
    page.locator("#pf-name").fill("Mock Test")
    page.locator("#pf-type").select_option("mock")

    # 6. Click Create.
    page.locator('[data-testid="save-provider-btn"]').click()

    # 7. Form auto-switches to edit mode after successful Create
    #    (admin.js:665-670). Confirm by waiting for the title and the
    #    Test Connection button (only rendered in edit mode).
    expect(page.locator(".admin-title")).to_have_text("Edit Provider")
    test_btn = page.locator('[data-testid="test-connection-btn"]')
    expect(test_btn).to_be_visible()

    # 8-9. Click Test Connection. The mock branch (leg 02) returns
    #      {"status": "ok", "detail": "Mock provider (dev mode)"}.
    test_btn.click()
    expect(page.locator(".admin-pf-test-result")).to_contain_text(
        "Mock", timeout=5000
    )

    # 10. Click Cancel to return to the provider list.
    page.locator(".admin-pf-cancel").click()

    # 11. Provider card visible with name "Mock Test" and mock badge.
    card = page.locator('[data-testid="provider-card"]')
    expect(card).to_be_visible()
    expect(card.locator(".admin-provider-name")).to_have_text("Mock Test")
    expect(card.locator(".admin-provider-badge")).to_have_text("mock")

    # 12. Navigate back to Chat. Banner now reflects the next setup gap.
    page.goto(f"{base_url}#chat")
    expect(setup_banner).to_be_visible()
    expect(setup_banner).to_contain_text("No agents")
```

> **Why `expect(...).to_contain_text(...)` not `assert page.locator(...).text_content() == ...`**: Playwright's `expect` auto-waits up to its timeout (default 5s) for the assertion to become true. This handles the async UI updates (form save POST, list refetch, area switch) without explicit `time.sleep` or `page.wait_for_*` boilerplate.

> **`#chat` vs default URL**: Loading `base_url` (no fragment) lands on `#chat` because `app.js` defaults to chat area. Both forms are equivalent.

### 3. Run verification

```bash
pytest -m browser tests/browser/test_flow_provider_setup.py -v --timeout=60
pytest -m browser tests/browser/ -v --timeout=60
pytest tests/ --tb=short -q --timeout=60
ruff check tests/browser/ the_one/interfaces/web/static/js/areas/
ruff format --check tests/browser/
```

> Note: ruff doesn't lint `.js` files. The `the_one/.../areas/` paths above won't produce ruff output; included for shell convenience but only the `.py` files are checked.

### 4. Repeat-run stability

```bash
for i in 1 2 3; do
  pytest -m browser tests/browser/test_flow_provider_setup.py -q --timeout=60 \
    || { echo "FAILED on run $i"; exit 1; }
done
echo "3 consecutive runs passed"
```

If any run fails (typically due to slow form-render or async-fetch races), increase the `expect` timeout for the affected assertion, OR add an explicit `page.wait_for_load_state("networkidle")` after navigation. Diagnose specifically — adding blanket sleeps masks real timing bugs.

## Edge Cases

- **`fetchProviderTypes()` race**: Per leg 02, the form gates render on `providerTypesReady.then(...)`. The first time the user opens the form, the fetch must complete before the dropdown is populated. Playwright's `page.locator("#pf-type").select_option("mock")` auto-waits for the option to exist — this handles the race implicitly. If it ever fails, add `page.wait_for_function("document.querySelector('#pf-type option[value=mock]')")`.

- **Hash navigation timing**: `page.goto(f"{base_url}#admin")` is treated by Playwright as a full navigation (loads the page) when the path differs OR a hash-only change when only the fragment changes. From `base_url` (chat) to `base_url#admin` is a hash-only change, so no full reload — but `App.activate()` for the admin area is triggered by the hashchange event. Playwright handles this correctly; the subsequent `.click()` waits for the target element to be present.

- **Banner element identity persists vs. recreates**: Looking at `chat.js:213-225`, the banner is created once when needed and removed when not. Re-opening chat after creating a provider triggers `checkSetupState()` again, which finds `providers.length === 1, agents.length === 0` and updates the banner text to "No agents configured…". The element identity may or may not be the same; the test uses the locator (which finds the current element each time), so identity doesn't matter.

- **Test isolation**: Each test gets a fresh `app_clean` subprocess with empty DB — no state bleed between flow tests. If F2 introduces persisted UI prefs (theme, last-viewed page) in localStorage, those would persist within a single browser context. The `page` fixture uses a fresh BrowserContext per test, so localStorage is also fresh.

- **`_renderProviderFormImpl` being delayed by promise**: `renderProviderForm(provider)` chains on `providerTypesReady.then(...)` then calls `_renderProviderFormImpl(provider)`. So when the test clicks `[data-testid="add-provider-btn"]` and then immediately tries to find `#pf-name`, there's an async gap. Playwright's auto-wait on `.fill()` handles this — it waits up to 30s for the element to be actionable.

- **Selector specificity for "+Add" button after click**: Once the user clicks `+Add Provider`, the panel re-renders to the form. The button is no longer present. Subsequent assertions in the same test must NOT try to interact with `[data-testid="add-provider-btn"]` again until the user navigates back to the list. The current test flow doesn't.

- **Cancel button class is stable**: Verified at admin.js:514 that `.admin-pf-cancel` is a static class on the Cancel button. The cancel handler resets `providerFormMode = null` and calls `renderProvidersPanel()`, which re-fetches and renders the list. Test relies on this exact flow.

- **Test Connection returns "Mock" in detail**: Per leg 02, the response is `{"status": "ok", "detail": "Mock provider (dev mode)"}`. The UI rendering of this in `.admin-pf-test-result` should include the word "Mock". If the rendering omits the detail and shows only the status, change the assertion to `to_contain_text("ok")` or check for absence of "error". Likely fine as-is; verify during implementation.

## State-Machine Reachability Audit

**State introduced/exercised**: empty DB → 1 provider DB. UI states: `setupIncomplete=true` (banner) → `setupIncomplete=false` (no banner, agent banner instead). 

Lower layers verified:
- DB CHECK constraint: `mock` allowed (leg 02 v6 migration). ✓
- API gating: `dev_mode=true` (leg 03 fixture sets it). ✓
- JS dropdown: `mock` option present in fetched types (leg 02). ✓
- `chat.js` setup banner re-evaluates on area activation (`activate()` calls `checkSetupState()` per `chat.js:284-296`). ✓

No existing tests pin behavior this leg breaks. ✓ Pass.

## Cache Freshness Contract

**Cache 1 — `bannerEl` JS variable** (existing, not introduced by this leg):
- Source of truth: `/api/providers` and `/api/agents` GET response counts
- Rebuild trigger: `checkSetupState()` called on area activate (`activate()` → `chat.js:284`)
- Maximum staleness acceptable: until next area-switch into Chat
- User-action invalidation map: creating a provider in Admin doesn't invalidate the banner immediately; the banner only updates on next switch into Chat (which the test exercises). This matches the M03 C-lite reactivity contract — flagged here for awareness, not a bug for this leg.

**Cache 2 — `providers` JS variable in admin.js** (existing, not introduced):
- Source of truth: `/api/providers`
- Rebuild trigger: `fetchProviders()` called on `renderProvidersPanel()` (which runs whenever the panel is rendered, e.g., after Cancel from edit form or category re-click)
- Maximum staleness acceptable: until next admin panel render
- User-action invalidation map: Create → switch to edit form (no list re-fetch needed since list is not visible). Cancel from edit → `renderProvidersPanel()` runs → list re-fetches. ✓ The test exercises this exact path (Create → Test Connection → Cancel → list now shows the new card).

**No new caches introduced.** ✓ Pass.

## Files Affected

- `the_one/interfaces/web/static/js/areas/chat.js` — 1 line added (`setAttribute` on banner)
- `the_one/interfaces/web/static/js/areas/admin.js` — 4 lines modified (data-testid attributes on add btn, card, save btn, test btn)
- `tests/browser/test_flow_provider_setup.py` — new (~70 LOC, 1 test)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing: `pytest tests/` shows 350 passed, 14 deselected; `pytest -m browser tests/browser/` shows 6 passed
- [x] 3 consecutive runs of the new flow test pass
- [x] `ruff check tests/browser/` and `ruff format --check tests/browser/` clean
- [x] Update flight-log.md with leg progress entry (status, what was done, any anomalies, per-test timing observation for the flow test)
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Do NOT check off this leg in flight.md (happens at flight-level commit time)
- [x] Do NOT commit (flight-level review and commit happen after the last autonomous leg)
- [x] Signal `[HANDOFF:review-needed]`
