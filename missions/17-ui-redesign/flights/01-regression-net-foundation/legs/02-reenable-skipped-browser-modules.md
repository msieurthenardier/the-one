# Leg: reenable-skipped-browser-modules

**Status**: completed
**Flight**: [Regression-Net Foundation](../flight.md)

## Objective

Re-enable the five module-skipped browser test modules: rewrite the three pre-rebrand-assertion modules against current markup, and root-cause/fix the two `.new-entity-btn` visibility-failure modules (timeboxed, with a dispositioned deferral path).

## Context

- Flight DD "Hang modules: timebox, then defer with teeth."
- The five modules (all `pytestmark = pytest.mark.skip`):
  - **Rewrite class**: `tests/browser/test_flow_studio_tools_overrides.py` (asserts the retired per-tool `<details>` override panel; Studio Tools tab is now per-category tiles), `tests/browser/test_studio_mcps_tab.py` (pre-rebrand MCPs-tab assertions), `tests/browser/test_flow_provider_grid.py` (pre-rebrand provider-grid assertions).
  - **Root-cause class**: `tests/browser/test_flow_agent_crud.py`, `tests/browser/test_flow_provider_setup.py` — skip reasons say "hangs, root cause unidentified", but header comments record the modern symptom: deterministic Playwright DOM-visibility failure on `.new-entity-btn` (60+ retries × 500ms then timeout).
- **Root cause (design-review verified, 2026-07-03)**: `components.css:719 — ".page-header:has(+ .entity-tile-grid > .empty-canvas) .new-entity-btn:not(.is-expanded) { display: none; }"` — in EMPTY state the header CTA is `display:none`; the create affordance moves to a different button, the in-canvas `-empty` variant (`new-agent-btn-empty`, `new-provider-btn-empty`). Both failing tests start empty (`app_clean`; `app_with_provider` seeds a provider but zero agents) and click the header testid (`test_flow_agent_crud.py:46`, `test_flow_provider_setup.py:50`) — Playwright retries the hidden element until timeout ("60+ retries × 500ms"). The JS documents the behavior (`studio.js:399-400`, `providers-grid.js:35-37` comments). The fix is a locator swap to the `-empty` variant at empty-state points. NOTE: Playwright treats `opacity:0` as visible, so the hover-reveal label treatment (`components.css:679`) is NOT the test breaker — it is only the a11y/discoverability concern below. The stale "hover-reveal opacity" suspect note in flight.md's design decisions and the modules' "root cause unidentified" header comments must be corrected as part of this leg.
- **Mid-test variant flips**: after a create succeeds, the grid is populated — the header CTA appears and the `-empty` variant disappears. Locators must not be reused across that state boundary.
- **Product-defect angle**: the create affordance moving between two different buttons depending on state (`components.css:719`) plus the icon-only hover-reveal label at rest (`components.css:679`) are discoverability/a11y concerns (touch SC5). Product fix belongs to Flight 3's component rebuild — NOT this leg. This leg fixes tests to target the current DOM honestly and logs the Known Issue citing both rules, primarily :719.

## Inputs

- The five test modules above; `tests/browser/conftest.py`, `tests/browser/seeders.py` fixtures
- Current markup: `the_one/interfaces/web/static/js/areas/studio.js` (agents grid + tools tiles), `areas/studio/mcps-tab.js`, `areas/admin/providers-grid.js`, `areas/studio/connectors-grid.js`
- Leg 01's registry `docs/ui-testid-registry.md` (if landed) for canonical testids

## Outputs

- All five modules with module-level skips removed and tests passing — OR the two root-cause-class modules re-skipped with updated reasons naming Flight 3 (per flight DD), if the timebox expires without a green run
- Updated header comments reflecting reality (no stale "root cause unidentified" text)
- Mission Known Issues entry for the icon-only CTA discoverability concern (with `components.css` citation), assigned to Flight 3
- If the empty-vs-populated `new-entity-btn` variant split caused test confusion, a comment in the affected tests documenting which variant each asserts

## Acceptance Criteria

- [x] Zero module-level `pytest.mark.skip` in `tests/browser/` other than (at most) the two root-cause-class modules under the deferral path — zero remain, all five re-enabled
- [x] The three rewrite-class modules pass: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_flow_studio_tools_overrides.py tests/browser/test_studio_mcps_tab.py tests/browser/test_flow_provider_grid.py -m browser -x --timeout 180` — 29 passed
- [x] Root-cause class: both modules pass the same way (no deferral needed); flight.md's "Hang modules" design decision updated with the verified `components.css:719` root cause
- [x] Full browser suite passes: `make test-browser` (excluding only dispositioned skips) — 532 passed, 0 failed, 6 pre-existing per-test skips in other modules, 12 deselected (pixel)
- [x] No product-source changes under `the_one/`; no product defect blocked the rewrites (`git status` confirms tests + artifacts only)
- [x] Mission Known Issues updated with the icon-only CTA concern
- [x] `ruff check` / `ruff format --check` clean on the leg's files (pre-existing drift in six unrelated files remains out of scope per Leg 01 deviation note)

## Verification Steps

- Run the targeted command per criterion 2; expect all pass
- `grep -rn "pytestmark = pytest.mark.skip" tests/browser/` — expect ≤2 hits, both with Flight-3-linked reasons (or 0 hits)
- `make test-browser` green end-to-end
- Confirm mission.md Known Issues contains the CTA entry

## Implementation Guidance

1. **Start with the root-cause class**: remove the skip from `test_flow_provider_setup.py`, run it alone via `scripts/run-tests.sh`, confirm the recorded failure, then apply the locator fix: at empty-state points target the `-empty` variant (`page.locator('[data-testid="new-provider-btn-empty"]')` — match the files' existing `page.locator('[data-testid=...]')` style, not `get_by_test_id`); after a create lands, switch to the header testid. Correct the module header comments AND flight.md's stale "hover-reveal opacity" suspect wording (design decision "Hang modules") to the `components.css:719` display:none mechanism. While in `test_flow_agent_crud.py`, consider softening the brittle exact-class assertion at line 97 (`to_have_class("studio-editor is-hidden")`) to a regex on `is-hidden`.
2. **Timebox**: the fix is expected to be a small locator swap; if the modules still fail for reasons beyond this after honest effort (~a working session), apply the deferral path (new skip reason naming Flight 3 + the actual observed root cause + flight.md note) and move on.
3. **Rewrite class**: read the current DOM-producing JS for each surface first; rewrite assertions to target current structure via testids from the registry. Preserve each test's *intent* (what user-visible behavior it guards) — listed in each module's docstrings/comments. Where the old test asserted retired UX (per-tool `<details>` panels), rewrite to assert the equivalent current UX (per-category tiles → tile detail view). WARNING: the same empty-state pitfall lives here — `test_flow_provider_grid.py:35` asserts header `new-provider-btn` visibility on `app_clean`, which `components.css:719` guarantees to fail; empty-state assertions must seed data first or assert the `-empty` variant / assert the header CTA is intentionally hidden.
4. **Fixtures**: reuse `SeededApp`/`seed_tool_config`/`app_clean` fixtures as-is; do not fork conftest patterns.
5. **Run discipline** (CLAUDE.md): browser tests ONLY via `scripts/run-tests.sh` (or `make test-browser`) — never bare pytest (orphaned Chromium/uvicorn children). Iterate per-file with `-x --timeout 180`; full suite once at leg end.

## Edge Cases

- **A rewrite reveals a real product regression** (feature broken, not just markup drift): stop per Adaptation Criteria — log to flight log + mission Known Issues; do not "fix" product code in this leg.
- **Flaky pass** (passes alone, fails in suite): investigate test isolation (the F5 L01 conftest SQLite-isolation fix history suggests DB state bleed); fix in test code only.
- **`get_by_test_id` default attribute**: Playwright's default is `data-testid` — no configuration change needed; verify conftest doesn't override it.

## Files Affected

- `tests/browser/test_flow_agent_crud.py` — skip removed or re-dispositioned; locators fixed
- `tests/browser/test_flow_provider_setup.py` — same
- `tests/browser/test_flow_studio_tools_overrides.py` — rewritten
- `tests/browser/test_studio_mcps_tab.py` — rewritten
- `tests/browser/test_flow_provider_grid.py` — rewritten
- `missions/17-ui-redesign/mission.md` — Known Issues entry
- `missions/17-ui-redesign/flights/01-regression-net-foundation/flight.md` — Flight-3 note if deferral used

---

## Citation Audit

Verified at leg design time (2026-07-03), root-cause citations re-verified by design review: all five skip markers present with quoted reasons; causal rule `components.css:719 — ".page-header:has(+ .entity-tile-grid > .empty-canvas) .new-entity-btn:not(.is-expanded) { display: none; }"` confirmed; a11y-concern rule `components.css:679 — ".new-entity-btn span { opacity: 0"` confirmed (non-causal for tests — Playwright treats opacity:0 as visible); failing click sites `test_flow_agent_crud.py:46`, `test_flow_provider_setup.py:50` (testid locators, header variant); brittle assertion `test_flow_agent_crud.py:97`; empty-state pitfall `test_flow_provider_grid.py:35`; testids and `-empty` variants confirmed in `studio.js:401`, `providers-grid.js:38`, `mcp-servers-grid.js:48`, `connectors-grid.js:50,73`; JS comments documenting the hiding behavior at `studio.js:399-400`, `providers-grid.js:35-37`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (batch flight commits per agentic-workflow)
- [x] Check off this leg in flight.md
