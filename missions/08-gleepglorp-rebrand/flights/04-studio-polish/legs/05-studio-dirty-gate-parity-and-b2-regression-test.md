# Leg: 05-studio-dirty-gate-parity-and-b2-regression-test

**Status**: landed
**Flight**: [Studio Polish](../flight.md)
**Mode**: Autonomous (Flight Director spawns Developer)

## Objective

Bring Studio's cross-area dirty-gate hook to parity with Admin's by extracting Studio's existing inline `dirty && inEditor` predicate into a `_confirmLeaveImpl(proceed, abort)` closure and exposing it on the area descriptor as `confirmLeave`. Verify that Studio's async-fetch continuations are already stale-then-guarded (audit + gap-fill). Lock both behaviors against regression with a new parametrized Playwright B2 test covering admin and studio cross-area dirty paths.

## Context

**Background**: Flight 3 Leg 06 introduced the `confirmLeave` cross-area dirty-gate hook on the area-descriptor interface (consumed by `app.js:switchTo` before deactivating the outgoing area). Admin implemented the hook. Studio was deferred to Flight 4 because Studio's dirty-state was newer and the cost wasn't amortizable across one flight. Flight 4 has rolled it in as Leg 05.

**Relevant prior-leg outcomes**:
- Legs 01 + 02 + 03 landed (Leg 01 + 02 committed; Leg 03 uncommitted per agentic-workflow's "single review + commit at flight end" rule).
- Substantial uncommitted working-tree edits exist on `studio.css`, `mcp-server-editor.js`, `mcps-tab.js`, `tools-tab.js`, `general-tab.js`, `admin.css`, `api.py`, `mcp/client.py`, plus 3 test-file mock extensions + a new `test_connect_captures_meta` test. **Leg 05's surfaces (`studio.js`, `admin.js`, new `tests/browser/test_flow_cross_area_dirty_gate.py`) do NOT overlap with these uncommitted edits.** Preserve the existing diff untouched.
- Leg 04 (custom dropdown) was SKIPPED per operator decision; no impact on Leg 05.

**Architect-design-review-corrected scope** (from flight.md Design Decisions):
- Studio ALREADY has the inline gate. This leg is EXTRACTION + EXPOSURE, not from-scratch infrastructure.
- The `inEditor` predicate covers BOTH agent-editor and mcp-server-editor mounted contexts — exact mirror of the existing inline gate.
- Stale-then audit: Studio already guards `fetchMcpSources_()` (3 sites) + `fetchMcpSourceTypes()` (1 site) + `loadAll()` continuation (1 site). The Architect review explicitly framed Leg 05's stale-then work as "verify + gap-fill" — actual gaps may be zero.

## Inputs

Files that must exist (verified at design time):
- `the_one/interfaces/web/static/js/areas/studio.js` — Studio area implementation with the inline gate to extract.
- `the_one/interfaces/web/static/js/areas/admin.js` — Admin's canonical `_confirmLeaveImpl` + `confirmLeave` pattern to mirror.
- `the_one/interfaces/web/static/js/app.js` — cross-area gate consumer (`switchTo` → `currentArea.confirmLeave(performCrossAreaSwitch, rollback)`).
- `the_one/interfaces/web/static/js/dialog.js` (or wherever `App.confirmDialog` lives) — dialog primitive used by both areas.
- `tests/browser/conftest.py` — Playwright fixture definitions (`app_with_agent`, `app_with_provider`).
- `tests/browser/seeders.py` — `SeededApp`, `seed_mock_agent`, etc.
- `tests/browser/test_flow_dirty_confirm.py` — existing same-area dirty-confirm test patterns to mirror for cross-area.

State that must be true:
- Working tree carries the Leg 02 + 03 uncommitted edits (per the flight-log Leg 03 close-out entry). Leg 05's edits compose on top WITHOUT touching those files.
- Flight 04 branch (`flight/04-studio-polish`) is checked out.
- Docker container `the-one` is running and serves the app at the base URL used by the browser fixtures.

## Outputs

After this leg completes:

**Modified files**:
- `the_one/interfaces/web/static/js/areas/studio.js`:
  - New `self._confirmLeaveImpl = function (proceed, abort) { ... }` closure assigned inside `init()` over the local `dirty` flag.
  - New `confirmLeave: function (proceed, abort) { ... }` method on the area descriptor (delegates to `_confirmLeaveImpl` if defined, else `proceed()`).
  - Inline sidebar `onSelect` gate at `studio.js:301-308` refactored to call `self._confirmLeaveImpl(commit, function () {})` for DRY — same gate logic, one source of truth (matches admin's pattern).
  - Stale-then guard additions IF the audit surfaces gaps (Architect framing says expected gap count ≈ 0; document audit findings in the flight log).

**New files**:
- `tests/browser/test_flow_cross_area_dirty_gate.py` — parametrized Playwright tests covering admin + studio cross-area dirty paths.

**Behavior changes**:
- Studio's cross-area navigation (topbar click / browser back-forward / hash typing) now invokes the dirty-gate dialog when an editor is dirty, matching admin's behavior.
- Same-area sidebar navigation in Studio continues to invoke the dialog (no behavior change for that path; just refactored to call the same impl).
- New Playwright test file locks both areas' cross-area dirty paths against regression.

## Acceptance Criteria

- [ ] **Sub-task A — `_confirmLeaveImpl` closure exists in `studio.js`'s `init()`** with signature `function (proceed, abort)`. Predicate matches the existing inline gate verbatim: `(self._activeSection === 'agents' && self._selectedAgent) || (self._activeSection === 'mcp-sources' && mcpSourceFormMode)`. When dirty && inEditor: `App.confirmDialog({ onConfirm: proceed, onCancel: abort })`. Otherwise: `proceed()`. (Grep-verifiable: `grep -n "_confirmLeaveImpl" the_one/interfaces/web/static/js/areas/studio.js` returns ≥1 match.)

- [ ] **Sub-task A — `confirmLeave` method on the studio area descriptor**, pattern-matching admin's shape at `admin.js:748-754 — "confirmLeave: function (proceed, abort)"`. Delegates to `_confirmLeaveImpl` if defined, else `proceed()`. (Grep-verifiable: `grep -n "^\s*confirmLeave: function" the_one/interfaces/web/static/js/areas/studio.js` returns 1 match.)

- [ ] **Sub-task A — Inline sidebar gate refactored to delegate**. The previous inline gate at `studio.js:301-308 — "if (dirty && inEditingContext)"` now calls `self._confirmLeaveImpl(commit, function () {})` (single source of truth — matches admin's setCategory which also routes through `_confirmLeaveImpl`). Grep-verifiable: the original `App.confirmDialog({ onConfirm: commit })` inline call is gone from the sidebar `onSelect` callback; replaced by a `_confirmLeaveImpl` call.

- [ ] **Sub-task B — Stale-then audit documented in the flight log**. Audit covers ALL `.then(` callbacks in `studio.js` (run `grep -n '\.then(' the_one/interfaces/web/static/js/areas/studio.js` to enumerate). Known sites to confirm:
  - `loadAll()` continuation at the bottom of `init()` (`studio.js:tail — "loadAll().then(function ()"`) — already guards `self._activeSection === 'agents'`; verify still guards correctly.
  - MCP-editor mount-path Promise resolutions inside `renderMcpSourcesSection` — already includes a guard at `studio.js:355 — "self._activeSection !== 'mcp-sources'"`.
  - `tryConsumePendingMcpSource()` continuation (called from `fetchMcpSources_().then(...)`) — **expected to be unguarded per design-review pass** (the `.then` after `fetchMcpSources_()` resolves fires unconditionally, regardless of whether the user has navigated away). Investigate whether `tryConsumePendingMcpSource` is idempotent on a stale section. If not, add a guard at the `.then` callback's top: `if (self._activeSection !== 'mcp-sources') return;`.
  - `fetchMcpSources_()` internal continuations at `studio.js:470, 475, 484` — confirm guards intact.
  - Any other `.then(` callbacks the grep surfaces — classify each.
  - Document each continuation in the flight log: `<file:line> — already guarded | needs guard | not async`.

- [ ] **Sub-task B — Any unguarded continuations gap-filled** with `if (self._activeSection !== '<expected>') return;` at the top of the `.then` callback. Per design review, expected gap count is ~1 (the `tryConsumePendingMcpSource` site). If actual count differs, document the difference in the flight log with the reasoning.

- [ ] **Sub-task C — New test file `tests/browser/test_flow_cross_area_dirty_gate.py`** exists with 4 parametrized test invocations (2 base tests × 2 areas):
  - `test_dirty_editor_topbar_cancel_keeps_state[admin]`: open admin provider editor → dirty the form → click `#studio` topbar button → confirm dialog appears → click Cancel → URL has rolled back to admin's prior hash → dirty editor still mounted.
  - `test_dirty_editor_topbar_cancel_keeps_state[studio]`: open studio agent editor → dirty → click `#admin` topbar → cancel → URL rolled back to studio → dirty editor still mounted.
  - `test_dirty_editor_topbar_confirm_navigates_cleanly[admin]`: open admin editor → dirty → topbar → Confirm → URL is studio → return to admin → assert non-stale UI (no leaked editor mount).
  - `test_dirty_editor_topbar_confirm_navigates_cleanly[studio]`: open studio editor → dirty → topbar → Confirm → URL is admin → return to studio → assert non-stale UI.

- [ ] **Sub-task C — All 4 parametrized test invocations pass** when run with `docker exec the-one pytest tests/browser/test_flow_cross_area_dirty_gate.py -x -q --timeout 30 -m browser`.

- [ ] **No regression in existing same-area dirty-confirm tests**: `docker exec the-one pytest tests/browser/test_flow_dirty_confirm.py -x -q --timeout 30 -m browser` stays green (24 tests pre-Leg-05; must still pass).

- [ ] **Narrow test gate stays green**: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 30` passes.

- [ ] **MCP/OAuth regression sweep stays green**: `docker exec the-one pytest tests/test_mcp_client.py tests/test_mcp_stdio_test_connect.py tests/test_mcp_connection_reset.py tests/test_oauth_test_connection_endpoint.py tests/test_oauth_secrets_api.py -x -q --timeout 30` returns 100 passed (the Leg 03 baseline).

- [ ] **Existing uncommitted working-tree edits from Legs 02 + 03 preserved untouched**. Diff verifiable: `git status` shows the same modified files post-leg as pre-leg (plus the new files Leg 05 adds: `studio.js` modifications + new `tests/browser/test_flow_cross_area_dirty_gate.py`). No revert / rewrite of any file the prior legs already modified.

- [ ] **Flight log updated** with: stale-then audit findings (per-continuation status), implementation summary (closures + descriptor methods + delegated inline gate), test results, and any anomalies.

- [ ] **No commit per agentic-workflow spec** — Developer signals `[HANDOFF:review-needed]` when implementation is complete; commit deferred to flight-end review.

## Verification Steps

1. **Grep sentinels** for Sub-task A:
   - `grep -c "_confirmLeaveImpl" the_one/interfaces/web/static/js/areas/studio.js` → expect ≥2 (closure definition + at least one delegated caller).
   - `grep -E "^\s*confirmLeave:\s*function" the_one/interfaces/web/static/js/areas/studio.js` → expect 1 match.
   - `grep "App.confirmDialog" the_one/interfaces/web/static/js/areas/studio.js` → expect ≤1 occurrence (inside `_confirmLeaveImpl`; the previous inline gate's call should be gone). If the file has other `App.confirmDialog` calls for non-leave-gate flows (e.g., delete confirmations), allow >1 but verify the sidebar `onSelect` no longer calls it directly.

2. **Manual rebuild + smoke check** (operator-eyeballed but Developer self-verifies as part of the leg):
   - `make rebuild`.
   - Open Studio, edit an agent, make the form dirty.
   - Click the `#admin` topbar button — confirm dialog should appear (NEW behavior — pre-leg this navigated without prompting).
   - Click Cancel — URL should roll back to studio; dirty editor still mounted.
   - Repeat with mcp-sources editor (create a new MCP source, dirty the form, click topbar).
   - Repeat same flow starting from admin (provider editor → studio topbar → confirm/cancel).

3. **Run the new Playwright test**: `docker exec the-one pytest tests/browser/test_flow_cross_area_dirty_gate.py -x -q --timeout 30 -m browser` → expect 4 passed.

4. **Run the existing same-area dirty-confirm regression suite**: `docker exec the-one pytest tests/browser/test_flow_dirty_confirm.py -x -q --timeout 30 -m browser` → expect 24 passed (no regression).

5. **Narrow gate**: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 30`.

6. **MCP/OAuth regression sweep**: `docker exec the-one pytest tests/test_mcp_client.py tests/test_mcp_stdio_test_connect.py tests/test_mcp_connection_reset.py tests/test_oauth_test_connection_endpoint.py tests/test_oauth_secrets_api.py -x -q --timeout 30` → expect 100 passed.

7. **Working-tree preservation check**: `git status` should show the SAME modified files as pre-leg-05 (the Leg 02 + 03 uncommitted set), PLUS:
   - `the_one/interfaces/web/static/js/areas/studio.js` (modified — the only Leg-05 modification to an existing file)
   - `tests/browser/test_flow_cross_area_dirty_gate.py` (new file)
   - No other diffs.

## Implementation Guidance

**Phase 1 — Sub-task A: extract + expose**

Read the current state at `the_one/interfaces/web/static/js/areas/studio.js`:
- The inline gate is in the `setActiveSection`/sidebar `onSelect` callback. Current shape (lines 295-309):

  ```js
  onSelect: function (section) {
    var commit = function () { setActiveSection(section); };
    var inEditingContext =
      (self._activeSection === 'agents' && self._selectedAgent) ||
      (self._activeSection === 'mcp-sources' && mcpSourceFormMode);
    if (dirty && inEditingContext) {
      App.confirmDialog({ onConfirm: commit });
    } else {
      commit();
    }
  },
  ```

- The area descriptor's tail currently ends with `activate` + `deactivate` methods (NO `confirmLeave`).

Implementation:

1. **Inside `init()` (after `dirty` is declared in scope), add `_confirmLeaveImpl`**:

   ```js
   // F4 L5: confirmLeave wired here so it can close over the local `dirty` flag.
   // Gate semantics mirror admin.js's _confirmLeaveImpl (admin.js:625-636): dirty
   // AND in-editor → confirm dialog; otherwise → proceed immediately. The
   // `inEditor` predicate covers BOTH editor mount contexts.
   self._confirmLeaveImpl = function (proceed, abort) {
     var inEditor =
       (self._activeSection === 'agents' && self._selectedAgent) ||
       (self._activeSection === 'mcp-sources' && mcpSourceFormMode);
     if (dirty && inEditor) {
       App.confirmDialog({ onConfirm: proceed, onCancel: abort });
     } else {
       proceed();
     }
   };
   ```

   Placement guidance: anywhere inside `init()` after the local `dirty` flag is declared. A natural site is alongside other `self.*` closures (e.g. near `self._tryConsumePendingSelect = ...` near the tail of `init()`).

2. **Refactor the inline sidebar gate** at `studio.js:onSelect — "if (dirty && inEditingContext)"` to delegate:

   ```js
   onSelect: function (section) {
     var commit = function () { setActiveSection(section); };
     self._confirmLeaveImpl(commit, function () {});
   },
   ```

   The empty-function abort is intentional — same-area sidebar nav doesn't need to roll back state on cancel (the dialog just closes; the section nav button never updates the active section unless `commit` fires).

3. **Add `confirmLeave` method to the area descriptor** (the object literal whose tail is at `studio.js:1899-1902` with `activate` + `deactivate`). Insert BEFORE `deactivate`:

   ```js
   // F4 L5: confirmLeave — cross-area dirty-gate hook consumed by
   // app.js:switchTo before deactivating the outgoing area on cross-area
   // navigation. Mirrors admin.js:748-754. The `_confirmLeaveImpl` handle
   // is attached inside `init()` so it can close over the local `dirty`
   // flag; this descriptor method just routes through it.
   confirmLeave: function (proceed, abort) {
     if (this._confirmLeaveImpl) {
       this._confirmLeaveImpl(proceed, abort);
     } else {
       proceed();
     }
   },
   ```

**Phase 2 — Sub-task B: stale-then audit**

Walk through every `.then(` callback in `studio.js` and classify:

- `studio.js:tail — "loadAll().then(function ()"` — final continuation in `init()`. Already guards `self._activeSection === 'agents'`. Status: ✅ guarded.
- `studio.js:355 — "if (mcpSourceFormMode == null || self._activeSection !== 'mcp-sources') return;"` — already guarded.
- `studio.js:470, 475, 484` — `fetchMcpSources_()` continuations. Confirm guarded.

Additional sites to audit (the Developer should run `grep -n '\.then(' the_one/interfaces/web/static/js/areas/studio.js` to enumerate ALL `.then` sites):

- Any `.then(` callback inside agent-editor mount path.
- Any `.then(` callback inside save / load / refresh flows triggered from the editor.

For each unguarded continuation found, add an `if (self._activeSection !== '<expected>') return;` at the top of the callback. The expected section value depends on which editor mount path the continuation belongs to (`agents` vs `mcp-sources`).

**Document findings in the flight log** under a section header like `### Leg 05 — Stale-then audit results`. Format:

| Continuation | Status | Resolution |
|---|---|---|
| `studio.js:NNN — "snippet"` | guarded \| unguarded | "intact" \| "added guard for activeSection != 'X'" |

If zero gaps found: explicit statement: "Audited N continuations; all already guarded. No gap-fill required."

**Phase 3 — Sub-task C: Playwright B2 test**

Study the existing patterns in `tests/browser/test_flow_dirty_confirm.py`:
- Fixture: `app_with_agent` (seeded SeededApp + a test agent) and `app_with_provider` (seeded SeededApp + a test provider).
- Helper: `_wait_editor_ready(page)` waits for the editor to mount.
- Helper: `_make_dirty(page)` types into the description field to dirty the form.
- Modal locators: `[data-testid="confirm-dialog-overlay"]`, `[data-testid="modal-cancel-btn"]`, `[data-testid="modal-confirm-btn"]`.
- Topbar locator: `#app-topbar .app-picker-button[data-area="<id>"]`.

Create `tests/browser/test_flow_cross_area_dirty_gate.py` with this skeleton:

```python
"""End-to-end flow tests: cross-area dirty-gate (F4 L5).

Covers the confirmLeave hook on the area descriptor consumed by
app.js:switchTo before deactivating the outgoing area. Both admin and
studio expose the hook (admin shipped in F3 L06; studio gains parity in
F4 L05). One parametrized test file amortizes fixture setup across both
areas.

Test matrix (2 base tests × 2 areas):
  - dirty_editor_topbar_cancel_keeps_state
  - dirty_editor_topbar_confirm_navigates_cleanly

Both parametrize across (area_id, fixture_name, editor_setup, dirty_helper).
"""

from __future__ import annotations

import urllib.parse

import pytest
from browser.seeders import SeededApp  # plus any area-specific helpers
from playwright.sync_api import Page, expect


# Per-area setup helpers — these abstract over the differences between
# admin's provider-editor entry path and studio's agent-editor entry path
# so the parametrized tests can run the same body for both.

def _setup_studio_editor(page: Page, base_url: str) -> None:
    """Navigate to studio + open the seeded agent in the editor."""
    page.goto(f"{base_url}#studio")
    expect(page.locator(".section-nav-header")).to_have_text("Studio", timeout=8000)
    editor_hidden = page.evaluate(
        "() => document.querySelector('.studio-editor')?.classList.contains('is-hidden')"
    )
    if editor_hidden:
        page.locator("button.entity-tile").first.click()
    expect(page.locator('[data-testid="tab-general"]')).to_be_visible(timeout=8000)


def _setup_admin_editor(page: Page, base_url: str, provider_id: str) -> None:
    """Deep-link directly to admin provider editor — avoids tile-click
    ordering nondeterminism. Mirrors test_flow_provider_dirty_confirm.py:30's
    direct-hash-route pattern."""
    page.goto(f"{base_url}#admin/providers/{provider_id}")
    expect(page.locator(".section-nav-header")).to_have_text("Administration", timeout=8000)
    # The provider-editor's Name field (#pf-name) is the canonical
    # always-rendered signal — it appears for every provider type. Admin
    # uses ID selectors; studio's agent-editor uses data-field selectors.
    expect(page.locator('#pf-name')).to_be_visible(timeout=8000)


def _dirty_studio_form(page: Page) -> None:
    """Type into the studio agent-editor description field."""
    desc = page.locator('[data-field="description"]')
    desc.click()
    desc.fill("dirty edit " + str(id(page))[:6])


def _dirty_admin_form(page: Page) -> None:
    """Type into the admin provider-editor's Name field. Same selector as
    test_flow_provider_dirty_confirm.py:36's `name_input = page.locator("#pf-name")`
    — always-rendered text input on every provider type. (Admin's
    provider editor uses ID selectors; studio's tabbed agent editor uses
    data-field selectors. Both patterns coexist in the codebase.)"""
    name_field = page.locator('#pf-name')
    name_field.click()
    name_field.fill("dirty edit " + str(id(page))[:6])


# Parametrize across both areas. Each parametrize entry pairs a name with
# its setup + dirty helpers + cross-area target. The setup signature
# differs slightly between areas (admin needs the provider_id from the
# fixture); the test body uses functools.partial-style helpers in setup
# to abstract over this.
AREA_MATRIX = [
    pytest.param(
        "studio",
        "app_with_agent",
        # studio setup takes just base_url
        lambda page, app: _setup_studio_editor(page, app.base_url),
        _dirty_studio_form,
        "admin",
        id="studio",
    ),
    pytest.param(
        "admin",
        "app_with_provider",
        # admin setup needs the provider_id for the direct deep-link
        lambda page, app: _setup_admin_editor(page, app.base_url, app.provider_id),
        _dirty_admin_form,
        "studio",
        id="admin",
    ),
]


@pytest.mark.browser
@pytest.mark.parametrize("area,fixture_name,setup,dirty,target", AREA_MATRIX)
def test_dirty_editor_topbar_cancel_keeps_state(
    request, area, fixture_name, setup, dirty, target, page: Page
) -> None:
    """Cross-area topbar click while dirty → confirm dialog → cancel →
    URL rolls back to source area, editor still mounted."""
    seeded = request.getfixturevalue(fixture_name)

    setup(page, seeded)
    initial_hash = page.evaluate("location.hash")
    dirty(page)

    topbar_target = page.locator(f'#app-topbar .app-picker-button[data-area="{target}"]')
    topbar_target.click()

    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()
    page.locator('[data-testid="modal-cancel-btn"]').click()

    expect(overlay).to_have_count(0)
    # URL rolled back to source area.
    assert page.evaluate("location.hash") == initial_hash
    # Editor still mounted (use an area-agnostic editor-mount signal — the
    # presence of the cross-area target's content panel ACTIVE would be
    # the regression we're testing against, so assert NOT active instead).
    target_panel_active = page.evaluate(
        f"() => !!document.querySelector('#main-content .area-{target}.active')"
    )
    assert not target_panel_active, f"Expected to still be on {area}, but {target} panel is active."


@pytest.mark.browser
@pytest.mark.parametrize("area,fixture_name,setup,dirty,target", AREA_MATRIX)
def test_dirty_editor_topbar_confirm_navigates_cleanly(
    request, area, fixture_name, setup, dirty, target, page: Page
) -> None:
    """Cross-area topbar click while dirty → confirm dialog → confirm →
    URL is target area → return to source area → no stale editor mount."""
    seeded = request.getfixturevalue(fixture_name)

    setup(page, seeded)
    dirty(page)

    page.locator(f'#app-topbar .app-picker-button[data-area="{target}"]').click()

    overlay = page.locator('[data-testid="confirm-dialog-overlay"]')
    expect(overlay).to_be_visible()
    page.locator('[data-testid="modal-confirm-btn"]').click()

    expect(overlay).to_have_count(0)
    # URL is target area.
    target_hash = page.evaluate("location.hash")
    assert target_hash.startswith(f"#{target}"), \
        f"Expected hash to start with #{target}, got {target_hash}"

    # Return to source area via topbar.
    page.locator(f'#app-topbar .app-picker-button[data-area="{area}"]').click()

    # No dialog should appear on the return navigation (the original dirty
    # editor is GONE; the source area should re-mount clean — verifies the
    # stale-then guard).
    expect(page.locator('[data-testid="confirm-dialog-overlay"]')).to_have_count(0)

    # Source-area content panel is active.
    source_panel_active = page.evaluate(
        f"() => !!document.querySelector('#main-content .area-{area}.active')"
    )
    assert source_panel_active, f"Expected {area} content panel active after return."
```

The Developer agent should:
1. Run the file once and verify all 4 parametrized invocations pass.
2. If admin's editor mount signal or dirty-field selector needs adjustment, use the existing `test_flow_admin_*.py` files in `tests/browser/` as references for canonical selectors.
3. If a test fails because admin's `confirmLeave` isn't wired the same way as Studio after Leg 05 (unlikely — admin's hook is from F3 L06 and should be stable), report the failure and fix the test setup. Do NOT modify admin's gate to make a test pass.

**Phase 4 — Smoke + final test sweep**

Run the verification commands listed in the Verification Steps section. All must be green before signaling `[HANDOFF:review-needed]`.

## Edge Cases

- **Sidebar nav from the inline-refactored gate**: the new delegation passes `function () {}` as the `abort` callback. Verify cancelling the dialog from the sidebar correctly leaves the active section unchanged (the cancelled `commit` never fires, so `setActiveSection` is never called — the section button click's other side effects, if any, must not have already mutated state). The existing same-area dirty-confirm tests cover this scenario; running them after the refactor catches regressions here.

- **`_confirmLeaveImpl` accessed before `init()` runs**: theoretically `app.js:switchTo` could call `confirmLeave` before Studio's `init()` has fired (first-time activation). The descriptor's `confirmLeave` guards with `if (this._confirmLeaveImpl)` and falls through to `proceed()` — matches admin's pattern. No additional handling needed.

- **Studio activated from an already-dirty state via hash-route**: deep-link directly to `#studio/agents/<name>/general` while another tab is dirty. `dirty` is initialized to `false` in `init()`, so the new mount starts clean. Cross-area nav from this mount obeys the same gate. No edge case here.

- **Multiple dialogs from same-area + cross-area races**: the singleton `App.confirmDialog` enforces no-second-open (see `test_singleton_modal_second_call_warns` in `test_flow_dirty_confirm.py`). Verify the cross-area gate doesn't fight the sidebar gate if a user manages to trigger both in rapid succession; the singleton prevents this.

- **`app_with_agent` fixture's `.session-agent-badge` doesn't populate** (mission Known Issue) — not relevant to Leg 05 tests. The cross-area tests open the agent editor via tile click; the chat session-agent-badge is unrelated to this flow. Document if relevant in the test file's docstring.

- **Admin provider-editor dirty-source field selector**: the existing `test_flow_admin_*.py` files use specific data-field hooks. The Developer agent should identify the canonical always-rendered text input in the provider editor (likely `data-field="display_name"` or `data-field="base_url"`) and use it consistently for `_dirty_admin_form`.

- **Working-tree preservation**: the Developer must NOT touch any file under the Legs 02 + 03 uncommitted set. Concrete list: `the_one/interfaces/web/static/css/studio.css`, `the_one/interfaces/web/static/css/admin.css`, `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js`, `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js`, `the_one/interfaces/web/static/js/areas/studio/tools-tab.js`, `the_one/interfaces/web/static/js/areas/studio/general-tab.js`, `the_one/interfaces/web/api.py`, `the_one/mcp/client.py`, `tests/test_mcp_client.py`, `tests/test_mcp_stdio_test_connect.py`, `tests/test_mcp_connection_reset.py`, `tests/test_oauth_test_connection_endpoint.py`. **Verify with `git status` at the start AND at the end** that the same files (and only those files, plus Leg 05's additions) are modified. If any of these are mistakenly touched, the Developer must `git checkout HEAD -- <file>` to revert ONLY the unintended modifications (preserving the Legs 02 + 03 uncommitted diff). Note: `tests/test_oauth_secrets_api.py` is NOT in the Legs 02 + 03 uncommitted set (it's part of the regression sweep but was unmodified by prior legs) — touching it is also out-of-scope for Leg 05.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio.js` — `_confirmLeaveImpl` closure + `confirmLeave` descriptor method + inline gate delegation refactor + (potentially) stale-then guards if the audit surfaces gaps.
- `tests/browser/test_flow_cross_area_dirty_gate.py` — new file, 2 parametrized tests × 2 areas.
- `missions/08-gleepglorp-rebrand/flights/04-studio-polish/flight-log.md` — append a "Leg 05 — confirmLeave parity + B2 regression test" entry summarizing the implementation + stale-then audit findings + test results.

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified (grep sentinels + manual smoke + test passes)
- [ ] Stale-then audit complete with findings documented in the flight log (per-continuation status table)
- [ ] New Playwright test file added and all 4 parametrized invocations pass
- [ ] Existing same-area dirty-confirm tests still pass (24 tests, no regression)
- [ ] Narrow gate green (4-module gate)
- [ ] MCP/OAuth regression sweep green (100 passed)
- [ ] Working-tree preservation verified: `git status` shows the Legs 02 + 03 uncommitted set + Leg 05's additions ONLY (no accidental edits to prior-leg files)
- [ ] Flight log updated with Leg 05 progress entry
- [ ] Leg status set to `landed` in this file's header
- [ ] Leg 05 checked off in `flight.md`
- [ ] **Do NOT commit per agentic-workflow spec** — accumulating with Legs 02 + 03 uncommitted edits for flight-end review/commit. Signal `[HANDOFF:review-needed]` when done.

## Citation Audit

Citations in this artifact verified against current HEAD code at design time (2026-05-13):

| Citation | Form | Resolution |
|---|---|---|
| `studio.js:295-309` (sidebar onSelect inline gate) | line + snippet | **Drifted from flight spec's `:301-303` — corrected to `:295-309`** for the full callback span. Inline gate predicate at `:301-308`. Durable locator: `"if (dirty && inEditingContext)"` + `"(self._activeSection === 'agents' && self._selectedAgent)"`. |
| `studio.js:355 — "self._activeSection !== 'mcp-sources'"` | line + snippet | OK at HEAD. Already-guarded MCP-editor mount continuation. |
| `studio.js:470, 475, 484` (`fetchMcpSources_()` continuations) | line | Inherited from flight spec; not re-verified line-by-line here (the Developer's audit will confirm during implementation). Durable form: `"fetchMcpSources_"` grep + manual inspection of the surrounding `.then` callbacks. |
| `studio.js:tail — "loadAll().then(function ()"` (final `init()` continuation) | symbol + snippet | OK at HEAD — confirmed at the file tail (last ~15 lines of `init()`). Guards `self._activeSection === 'agents'`. |
| `studio.js:1899-1902 — "activate: function () { ... deactivate: function () {}"` (descriptor tail — `confirmLeave` insertion point) | line + snippet | **Corrected during design review pass.** Initial draft cited `:756-758` which is actually inside `fetchProviderModelCaps` machinery, NOT the area descriptor. Actual descriptor tail at HEAD is at lines 1899-1902. Insertion point: BEFORE `deactivate` (which is the very last property of the area-descriptor object literal). |
| `admin.js:625-636 — "self._confirmLeaveImpl = function"` | line + snippet | OK at HEAD. Canonical extract-closure pattern. |
| `admin.js:748-754 — "confirmLeave: function (proceed, abort)"` | line + snippet | OK at HEAD. Canonical descriptor-method pattern. |
| `app.js:81-169` (cross-area gate consumer in `switchTo`) | line range | OK at HEAD. Lines 146-167 specifically house the `confirmLeave` invocation. |
| `app.js:153 — "typeof areas[currentId].confirmLeave === 'function'"` | line + snippet | OK at HEAD. The guard that determines whether the gate runs. |
| `tests/browser/test_flow_dirty_confirm.py` (24 existing tests) | file reference | OK at HEAD. Pattern reference for fixture / locator conventions. |
| `tests/browser/seeders.py:SeededApp` + `seed_mock_agent` | symbol | OK at HEAD (imported by `test_flow_dirty_confirm.py`). |
| `tests/browser/conftest.py` (fixture definitions for `app_with_agent`, `app_with_provider`) | file reference | OK at HEAD — referenced by existing browser tests. |
| `mission.md` Known Issue: `app_with_agent` `.session-agent-badge` doesn't populate | non-source reference | Out of scope for Leg 05 (chat-only fixture issue; Leg 05 tests use Studio + Admin editors). |

13 citations verified clean; 2 drifts corrected (the flight spec's `:301-303` for the inline gate was off — actual span is `:295-309` for the full `onSelect` callback, gate condition starts at line 304; the initial draft's `:756-758` for the descriptor tail was wrong — actual span is `:1899-1902`). Both corrections applied during design-review pass 1.

**Additional findings from design review** (incorporated above):
- `_dirty_admin_form` selector confirmed: `#pf-name` (the canonical always-rendered text input on every provider type; matches `test_flow_provider_dirty_confirm.py:36 — "name_input = page.locator(\"#pf-name\")"`). Admin uses ID selectors; studio's tabbed agent editor uses data-field selectors — both patterns coexist in the codebase. (Pass-2 review caught an initial draft that incorrectly cited `[data-field="name"]` for the admin field.)
- `_setup_admin_editor` refactored to use direct hash-route `#admin/providers/{provider_id}` instead of tile-click — avoids tile-ordering nondeterminism.
- Stale-then audit expected gap count revised from "≈0" to "~1": the `tryConsumePendingMcpSource` continuation that fires after `fetchMcpSources_().then(...)` is unguarded and a real gap candidate.
- AREA_MATRIX lambdas updated to pass the full fixture object (not just `base_url`) so the admin setup can extract `provider_id`.
