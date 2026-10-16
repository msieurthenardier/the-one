# Leg: provider-signin-and-close

**Status**: completed
**Flight**: [Library completion and a stateful pilot](../flight.md)

## Objective
Finish the provider pilot:
- rebuild the plan sign-in machinery and the token-expiry line on library controls, removing the provider's consent-block fork;
- bring `provider-editor.js` and `providers-section.js` to zero HTML-string sinks and zero reuse-check allowance rows;
- take the "after" capture set and compare it with the "before" set;
- run the full gate and re-budget the lanes (flight DD13);
- update the docs for the whole pilot.

## Context
- Split from `provider-editor-pilot` (leg 07) at design review, 2026-10-15. Leg 07 rebuilt the editor core on the library and left `wirePlanSignIn`, `buildConsentBlock` and `renderTokenExpiry` working as before, re-attached through handles. Read leg 07's artifact (including its addenda) and its flight-log entry first.
- Flight decisions: DD1, DD8 (the canonical versions), DD11, DD13.
- Today's machinery: `wirePlanSignIn` (`provider-editor.js` about `:421-732`, three states, `renderState` clearing `body.innerHTML`), `buildConsentBlock` (about `:630-700`), Reset through `App.confirmDelete` with "Confirm Reset?" (about `:615-625`), `renderTokenExpiry` (about `:354`), live on `App.time.onChange` (about `:855-860`). Re-locate by symbol after leg 07.

## Inputs
- Legs 01-07 landed. The "before" set is in `$HOME/.cache/the-one-ui-capture/m31-f1-before/`.

## Outputs
- `provider-editor.js` with no sinks and no allowance rows. The `ui-capture` "after" set is recorded. `scripts/run-tests.sh` budgets are updated. Docs and the catalogue are updated.

## Acceptance Criteria
- [ ] **Plan sign-in** is rebuilt from library controls in all three states, through a per-state builder that patches one `body` node (`replaceChildren`).
  - The awaiting-code state uses `App.ui.consentLink(url, {surface: 'chat', urlTestid, openTestid, copyTestid})`, with the provider's existing `plan-signin-consent*` testids. This keeps the copy announcement "Link copied" (leg 05) and makes Open a real link.
  - The code input and "Confirm code" are library controls.
  - Reset uses `App.ui.confirm` with the armed label "Confirm reset?" and gets the armed style (DD8).
  - The flash on sign-in success stays ("Signed in to Anthropic").
  - `buildConsentBlock` is deleted.
- [ ] **Token expiry.** The line keeps `data-testid=provider-token-expiry`, `data-state` (`ok`, `soon`, `past`), its text and its live update on `App.time.onChange`. It is built with library controls (for example `App.ui.status` mapping ok→success, soon→warning, past→danger, or the field hint). Any visible change is recorded against DD8's status line.
- [ ] **Zero.** `provider-editor.js` and `providers-section.js` have no `innerHTML`, `outerHTML` or `insertAdjacentHTML`, no rows in `HTML_SINK_ALLOWANCE` or `DYNAMIC_SINK_BASELINE`, and no rows in `OWNERSHIP_ALLOWANCE`. In particular they have no `App.icon(`, `App.showFlash(`, `App.confirmDelete(` or `App.consentLink.` calls and no owned class literals.
- [ ] **Tests:**
  - `test_flow_provider_plan_signin.py` and `test_flow_provider_plan_token.py` are updated: the copy feedback is the button's "Copied" plus the announcement "Link copied" (leg 05), the consent testids are kept, and the reset armed label is "Confirm reset?" (case-insensitive tests already pass).
  - A browser test pins create → Sign in → edit auto-start (`pendingAutoSignInId`) **before** the machinery is touched.
  - The `providers`, `settings`, `agents`, `routing`, `shared` and `contracts` lanes pass under netns, as do `make test-unit`, the static guards and `test_ui_ownership.py`.
- [ ] **The "after" set:**
  - Run `scripts/ui_capture.py` (all surfaces) to `$HOME/.cache/the-one-ui-capture/m31-f1-after/`.
  - Read every before/after pair in both themes and record each visible difference in the flight log, with its DD8 line or squawk. Expected:
    - the Test button's size and icon;
    - the delete icon and armed label;
    - the switch style and its label placement;
    - the test-result LED;
    - the consent block's Open as a link.
  - An unexplained difference is fixed before landing.
- [ ] **DD13 re-budget:** the full gate runs with `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate`, in the background with an explicit timeout above the run's length. `scripts/run-tests.sh`'s budget table is updated for the `contracts` (and `providers`) lanes from the measured times, or the contracts lane is split if it exceeds 1.3× its budget. The lane times are recorded in the flight log.
- [ ] **Docs:** `the_one/agents.md`'s provider editor and Providers section notes describe the library build, and the "Control library" section lists `secretInput`. The catalogue rows for the provider surfaces are updated, as are the rows for the info icon, legacy toggle 1 and copy buttons, to show the provider sites as migrated.


## Verification Steps
- `grep -n "innerHTML\|outerHTML\|insertAdjacentHTML\|App.icon(\|App.showFlash(\|App.confirmDelete(\|App.consentLink\." the_one/interfaces/web/static/js/areas/studio/provider-editor.js the_one/interfaces/web/static/js/areas/studio/providers-section.js` returns nothing.
- `make test-unit`; the lanes, run in the background with `TEST_TIMEOUT`; then `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 TEST_TIMEOUT=3600 make gate`, in the background with a timeout above its length.
- The "after" captures, read pair by pair.

## Implementation Guidance
1. **Pin create → sign-in → edit auto-start** with a browser test, against the leg-07 code.
2. **Rebuild the three sign-in states** with a per-state builder over one `body` node:
   - The `plan-signin-error` node is built once per mount, **outside** the replaced content, so `showError` after a `startFlow` rejection (which runs after a re-render) is not lost.
   - Keep `requestCreateSave`, `pendingAutoSignInId` and `clearProviderSignInHandoff` unchanged.
3. **The consent link.**
   - `App.ui.consentLink(url, {surface: 'chat', urlTestid, openTestid, copyTestid})`: `surface` only picks the default testids and the root modifier class. The provider passes its own `plan-signin-consent*` testids.
   - Keep `openConsentPopup` for the automatic popup after `/oauth/start`, as today. The consent link's Open anchor (`target=_blank`, `rel=noopener noreferrer`) is the manual path, including in the desktop webview, where `window.open` may be refused without a user gesture.
4. **The token-expiry line** on library controls. The `App.time.onChange` owner stays the long-lived section element.
5. **Delete `buildConsentBlock`** and the provider-only consent CSS re-declarations (`studio.css` about `:1672`).
6. **Captures, gate, re-budget, docs.**

## Edge Cases
- **Sign-in while the editor is dirty:** keep today's behaviour (check it before changing anything).
- **A popup blocked** (`window.open` returns null): the consent link must already be visible, as today.
- **Reset armed when the state re-renders** (for example a poll lands): the armed button is replaced. Accept this as today, or keep the node. Document which.
- **The time-zone change while signed out** (no expiry line): no error.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/provider-editor.js`, `the_one/interfaces/web/static/css/studio.css`.
- `tests/browser/test_flow_provider_plan_signin.py`, `test_flow_provider_plan_token.py`, plus one new pin test.
- `tests/test_ui_guards.py`, `tests/_ui_ownership_allowance.py`.
- `scripts/run-tests.sh` (budgets).
- `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `the_one/agents.md`, `CLAUDE.md` (the provider-editor and capture notes).

## Citation Audit
Inherited from `07-provider-editor-pilot.md`'s audit (checked 2026-10-15 at `59992fd`). Line numbers shift after leg 07, so re-locate by symbol.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
