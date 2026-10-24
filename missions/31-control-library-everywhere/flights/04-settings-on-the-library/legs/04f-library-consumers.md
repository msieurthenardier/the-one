# Leg: library-consumers

**Status**: landed
**Flight**: [Settings on the library](../flight.md)

## Objective
Move the Agents and Library users of the banner and the code block onto `App.ui.banner` and `App.ui.codeBlock` (built in legs 04a and 04b), carry `dangerZone`'s notice through the banner's persistent live mode, and land squawk 0236 (the provider editor's Save is not busy).

## Context
- **Flight decisions:** DD4 (the banner's and code block's consumers), DD12 (legacy class names stay emitted; ownership hands over in legs 08b and 10, so no allowance change here), DD5 (busy), DD9 (0236 absorbed), DD11.
- **Banner users outside Settings** (planning grep):
  - `provider-editor.js:220`: `plan-signin-error banner banner-error`;
  - `self-config-revisions.js:218`: `revision-stale-warning banner banner-warning`;
  - `self-config-external.js:120`: `self-configuration-external-token-reveal banner banner-warning`;
  - `ui/editor.js:283`: `dangerZone`'s `action-blocked-message banner banner-error`, a `role=alert` region kept rendered while empty (`.action-blocked-message:empty`). It is library code, so composing `App.ui.banner` with `live: 'alert'` is a library change in a consumer leg. That is allowed here because the banner's persistent live mode was built for it in 04a. No new option may be added in this leg.
- **Code block users outside Settings:**
  - `self-config-revisions.js:131`, `:143`, `:228`, `:238` (`revision-value code-block`);
  - `self-config-history.js:135`, `:272`, `:278`.

  Check each element's tag. If any is not a `pre`, moving it to `codeBlock` (a `pre`) changes its whitespace handling. A visible difference is a ledger row; avoid it with `codeBlock`'s defaults if possible. The area classes (`revision-value`, `restore-node-value`, `history-entry-*`) stay as the caller's `className`, if `codeBlock` takes one; check 04a's signature, and do not add an option here.
- **Squawk 0236:** the provider editor's `performSave` (`provider-editor.js` about `:346`) calls `fetchJson` with no busy state, so a double-click on Create creates the provider twice. Fix: `h.shell.setBusy(true)` before the request and `setBusy(false)` in both outcomes (the connector precedent, Flight 3 DD8-2). Test first: a double-click on Create with a held POST produces exactly one POST.
- **The remount side-effect inventory (DD5)** does not apply. No editor changes its mount model here.

## Inputs
- Legs 04a-04e landed (`banner` from 04a, `codeBlock` from 04b, the emitted-class guard from 04c).
- The files above.

## Outputs
- The three Library banners and the `dangerZone` notice on `App.ui.banner`; the seven self-configuration code blocks on `App.ui.codeBlock`.
- `provider-editor.js` Save busy (0236), with its test; squawk 0236 completed.
- Captures of `plan-signin-awaiting-code`, `agent-self-configuration` and every `dangerZone` host available in `ui_capture.py`, compared with leg 01's before set (expected identical).
- The catalogue's banner and code block rows list these consumers.

## Acceptance Criteria
1. `git grep -nE "banner( |-)" the_one/interfaces/web/static/js/areas/studio` shows no hand-built banner class strings. The three sites build `App.ui.banner`, and their testids and roles are unchanged: the plan sign-in error is still announced as before (check its role today and keep it).
2. `dangerZone`'s notice is a composed banner in persistent live mode:
   - it is `role=alert`, kept rendered while empty;
   - its testid option and `setNotice(text|null)` behave as before;
   - the existing `dangerZone` contract tests pass unchanged, plus one new assertion that the notice is the banner (it carries `ui-banner`).
3. The seven self-configuration code blocks use `App.ui.codeBlock`, with their area classes and testids kept. `agent-tabs` passes unchanged.
4. **0236:** a double-click on the provider Create, with the POST held, sends exactly one POST (the test fails on today's code, recorded). Save, Cancel and Test are disabled while it is in flight, and everything is restored on success and on failure. The `providers` lane passes.
5. **Captures** of the touched surfaces match the before set, or each difference is a ledger row.
6. `OWNERSHIP_ALLOWANCE` and `HTML_SINK_ALLOWANCE` are unchanged, or smaller. The emitted-class guard passes.
7. Lanes `providers`, `agent-tabs`, `agents`, `library`, `knowledge`, `mcp`, `contracts-controls` and `contracts-overlay` pass, at most 3 at a time. Every `dangerZone` host is covered.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_ui_control_inventory.py tests/test_ui_emitted_classes.py tests/test_design_tokens_a11y.py -q -x --timeout 120`.
- The lanes above under `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1`.
- The capture compare with `scripts/ui_capture.py` and the PIL diff.
- `make test-unit` once.

## Implementation Guidance
1. Write the 0236 failing test first, then the fix.
2. Move the banners one at a time, checking each one's role and live behaviour against today's.
3. Move the `dangerZone` notice, and run every lane with a `dangerZone` host.
4. Move the code blocks.
5. Capture, compare, update the catalogue, `agents.md` and the flight log.

## Edge Cases
- **The plan sign-in error banner** may be shown or hidden by toggling `hidden` today. Keep the same show and hide mechanism (`show`/`hide`), so the tests that check visibility keep passing.
- **`self-config-external.js`'s token reveal banner** holds a secret token. Make sure the banner's `set` uses `textContent` and never markup, and that it is cleared in the same places as today (disable, tab leave, new identity: CLAUDE.md "Self-configuration surface").

## Files Affected
- `static/js/areas/studio/provider-editor.js`, `self-config-revisions.js`, `self-config-external.js`, `self-config-history.js`, `static/js/ui/editor.js` (the `dangerZone` notice).
- Their browser tests; a new 0236 test in the `providers` lane.
- `docs/ui-control-inventory.md`, `the_one/agents.md`, `squawks/0236-*`, the flight log.

## Citation Audit
Checked at `512616b` (FD grep):
- `provider-editor.js:220`; `self-config-revisions.js:218`, `:131`, `:143`, `:228`, `:238`; `self-config-external.js:120`; `self-config-history.js:135`, `:272`, `:278`; `editor.js:283`: verified.
- `provider-editor.js` about `:346` `performSave` with `App.api.fetchJson` and no busy state: verified (FD read).

## Design Review Amendments (cycle 1, 2026-10-23)
These override the body where they conflict.
- **`dangerZone`'s notice:**
  - The two string pins in `tests/browser/test_ui_editor_contract.py` (`:360` `"action-blocked-message banner banner-error"` and `:466` `"DIV.action-blocked-message banner banner-error"`) are **updated** to the new className, which is where the `ui-banner` assertion goes.
  - The banner's `live: 'alert'` must set only `role=alert`, with no `aria-live` and no `hidden` (`:407` asserts both absent). If 04a's banner adds either, raise it; do not loosen the pin.
  - The notice stays a direct child of `z.el`, with its testid unchanged and `className: 'action-blocked-message'` kept: `components.css` about `:1561-1565` documents it as the empty-collapse and query handle.
  - The body's `provider-editor.js:379` citation is stale; there is no such query.
- **0236, following the connector precedent** (`connector-editor.js` about `:644/680/692`; test `test_studio_connector_editor.py:408-452`):
  - `setBusy(true)` runs **after** `collectFormData` returns a payload, so a validation failure never leaves the form busy;
  - `.catch` → `setBusy(false)`;
  - an edit success → `setBusy(false)` after `checkDirty()`;
  - a **create** success stays busy, because the create-to-edit remount replaces the shell;
  - `performSave` is also used by the create-mode plan sign-in button, which gets the same fix and its own test line.
  - **The test** (providers lane, `test_flow_provider_editor.py`): `el.click(); el.click()` inside one `evaluate`, with `POST /api/providers` held through `page.route`, then fulfilled with 201 and, separately, 500. Assert exactly one POST and the provider count through the API. On the failure path, Save, Cancel and Test are re-enabled.
- **Code blocks:**
  - The four diffed blocks (`self-config-revisions.js:131/143`, `self-config-history.js:272/278`) are filled by `renderDiffedValues`/`applyDiffSpans` with `diff-del`/`diff-add` spans. They use `App.ui.codeBlock({…}).el` as the container passed to those functions, with `trim` off. Their overflow region is evaluated on attach only. That is accepted; record it.
  - The other three (`:228`, `:238`, history `:135`) use `text:`.
  - Testids (`revision-base`, `revision-proposed`, `revision-current`, `revision-stale-proposed`) go through `testid`; area classes go through `className`.
  - **Leg 04b must make `trim` default to false** (amended there), so displayed text is byte-identical unless a caller opts in.
- **The token reveal banner** (`self-config-external.js:119-125`) is built with `children` (the warning `p`, a `copyField`, the URL and the dismiss button).
  - Never call `set()` or `setChildren()` on it after build: that would wipe the token field.
  - Clearing stays `hideTokenReveal` (`banner.hide()` plus `tokenField.setValue('')`) on dismiss, disable, destroy, tab leave and a new identity, and `show()`/`hide()` must toggle the `hidden` attribute (the tests use `to_be_hidden`).
  - Keep `tabIndex=-1` (set on `banner.el`), and the `id`/`aria-describedby` on the warning `p`.
  - The redundant `aria-live="polite"` on a `role=status` element is dropped (record it).
- **The plan sign-in error** (`provider-editor.js:219`, toggled by `showError`/`clearError` at about `:586-592`): `banner({tone: 'error', role: 'status', hidden: true, className: 'plan-signin-error', testid})`, with `set(msg)` plus `show()`, and `set('')` plus `hide()`. `h.planErr` is `banner.el`.
- **The stale-revision warning** is a `<p role=alert>` today and becomes a `div`. That is a ledger row. Build a fresh banner per render (the panel is rebuilt).
- **AC7 names the four `dangerZone` hosts:** `general-tab.js:217` (agents), `provider-editor.js:249` (providers), `knowledge-detail.js:293` (knowledge), `connector-editor.js:574` (library).
- **AC1's guard** also greps for `'banner banner-` and `className: '…banner` literals under `areas/studio`.
- **Order:** the `editor.js` change and its two pin updates land together, before the other lanes run.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
