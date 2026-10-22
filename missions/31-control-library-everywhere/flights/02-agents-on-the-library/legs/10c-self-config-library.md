# Leg: self-config-library

**Status**: completed
**Flight**: [Agents on the library](../flight.md)

## Objective
Move the four Self-configuration modules (from leg 10b) onto library controls, with today's testids and wording. Every self-configuration module ends with zero sinks and zero allowance rows. The security properties are unchanged and are pinned by tests.

## Context
- **Flight decisions:** DD4 (1, the switch), DD7 (Self-configuration), DD8, DD10.
- **Legs 10a and 10b have landed:** the tab patches through `setAgent`, refetches locally, and is split into `self-config-status.js`, `self-config-external.js`, `self-config-revisions.js` and `self-config-history.js` around a shared context. Read their flight-log entries.
- **Today's pieces off the library:** two `.tool-enable-switch` switches (enable and approval mode); five or more status and alert lines; five `empty-state`s; revision-card buttons; restore LEDs (`.indicator-led`); a history `<details>`; the grant input and button; a hand-rolled copy-once token reveal with its own clipboard code; revoke through `App.confirmDelete`.
- **Tests:** the four self-configuration files (heavily testid-based; some comments mention `.tool-enable-switch`), plus 10a's DD9-3 tests.

## Acceptance Criteria
- [ ] **On the library**, keeping today's testids and text:
  - **The two switches are `App.ui.toggle`**: the switch first, the label beside it, and the info button where today has one (DD4 item 1). The visible label text is today's `aria-label`, shown visibly as DD7 says. The `testid` option already lands on `toggle.control` (`choice.js` about `:115-141`), but that becomes a 1px clipped input. So these five test call sites change from `.click()` on the testid to `get_by_role('switch', name=…)` with a click on the track (as `test_flow_agent_notes.py:112` needed `click(force=True)`):
    - `test_studio_self_configuration_tab.py:49,58,93`;
    - `_queue.py:211`;
    - `_external.py:365`.
  - **Status and alert lines** are `App.ui.status`. `App.ui.status` always draws an LED (`feedback.js` about `:131-158`), which would be a visible change on about 7 lines outside DD4. Add a `led: false` option (with a contract case in both engines and the catalogue row updated) and use it where today has no LED. For `role="alert"` lines, use the `role` option leg 09 added (or add it, if leg 09 did not).
  - **Empty states** are `App.ui.emptyState` (with `titleTag: 'p'` where a heading would be wrong). Today's empty states are plain inline text, not the centred bold `emptyState` look. **`App.ui.emptyState` gains an inline variant** (for example `variant: 'inline'`: left-aligned, regular weight, secondary ink, no extra padding), owned by the factory's CSS, with a contract case in both engines and the catalogue row. **Leg 09's consumer override moves onto it:** `css/studio.css` `.rules-notes-empty > p` and the `rules-notes-empty` class in `rules-notes-tab.js` are removed, and Rules and notes uses the variant. The leg 09 capture must stay pixel-identical. No consumer CSS may restyle a library control's inner nodes (FD ruling, 2026-10-21).
  - **Section headings** (`editor-section`/`section-title`, 5 each) are `App.ui.section({titleTag: 'h3'})`.
  - **Buttons:** every `btn-*` button is `App.ui.button`, with today's `aria-label`s and testids. That covers grant, copy, dismiss, rotate, restore, and the revision cards' approve, dismiss and override. The revision cards keep their structure.
  - **Restore LEDs** are `App.ui.status` variants.
  - **The history** stays a native `<details class="advanced-collapsible">`. There is no `App.ui.disclosure`, and `advanced-collapsible` is not an owned class. The Flight 1 DD8 focus ring applies.
  - **The grant input** is `App.ui.field`/`input`.
  - **Revoke** uses `App.ui.confirm` on a library button, with today's labels and `aria-label`, and the shared `ui-confirm-live` announcement.
- [ ] **The token reveal is `App.ui.copyField`** with copy-once semantics:
  - create the field with **no** `value`, then call `setValue(token)`: `textInput` sets the value as a property, never as an attribute. Never pass `dataset.field`, because `collectFormData` sweeps `.field-input`;
  - `liveEl` is the tab's announcement line, and `doneText` is "Token copied to the clipboard.";
  - the reveal's explanatory text is linked with `aria-describedby` on both the field's `.input` and its `.button`, set after creation;
  - focus after a reveal stays on the copy control (`copyTestid`, as `_external.py:121` expects);
  - the visible "Copied" / "Copy failed" button text is new (DD4's copy feedback) and is recorded in the captures;
  - the token is cleared with `setValue('')` and the reveal hidden: on dismiss, on disable (10a), and on `destroy` (the slot's destroy, so a new identity). It is also cleared when the tab is deactivated, through named hooks: `setActiveTab` leaving `self-configuration` calls `selfConfig.deactivate()`, and studio's area `deactivate` (`studio.js` about `:734`) calls it too. `deactivate` is added to the tab's handle;
  - the hand-rolled clipboard code is removed.
- [ ] **Security properties unchanged and pinned:**
  - the token is never written into an attribute, `title`, `data-*`, or a log line. A browser test reveals a token, then asserts that no attribute anywhere in the document contains it (`document.querySelectorAll('*')` over every attribute), and that it is gone after dismiss;
  - approve stays fail-closed against staleness; `?override=true` only from the override button;
  - restore targets only `applied` revisions;
  - nothing in the tab can change a field except through today's routes.
- [ ] **Focus after an action** is unchanged: the `self-configuration-action-status` line, as 10a left it.
- [ ] **Zero:** the four modules and the entry have no rows in `HTML_SINK_ALLOWANCE`, `DYNAMIC_SINK_BASELINE` or `OWNERSHIP_ALLOWANCE` (lowered from the printed dicts). Dead self-configuration CSS (`.tool-enable-switch` rules used only here, the old reveal and LED rules) is removed if no consumer remains; any remaining consumer is named in the flight log.
- [ ] **Tests:** the four self-configuration files, the DD9-3 tests and the new token-attribute test pass. The selectors that change are listed from a grep.
- [ ] **Captures:** `agent-self-configuration` to `…/m31-f2-after-10c/`. The expected differences are the DD4 switch (item 1) and the copy button's "Copied" feedback. Anything else is listed with its DD line, or fixed.
- [ ] **Gates:** `make test-unit`; the static guards and ownership checks; the `agents` lane under netns; the contracts lane with WebKit required (`status` gains `led: false`).
- [ ] **Docs:** `the_one/agents.md`'s self-configuration UI notes. CLAUDE.md's Self-configuration paragraph only if a UI fact it states changed.

## Verification Steps
- `grep -n "innerHTML\|outerHTML\|insertAdjacentHTML\|tool-enable-switch\|navigator.clipboard"` on the five self-configuration files (the entry and four modules) returns nothing.
- The token-attribute test.
- The lanes above.

## Implementation Guidance
1. History (LEDs), then revisions (buttons, empty states), then status (switches, lines, sections), then the external credentials (grant, revoke, the token reveal last).
2. Run the matching test file after each module.
3. Captures, allowances, docs.

## Edge Cases
- **Self-configuration disabled:** the enable switch and its explanation only.
- **A stale pending revision:** approve shows today's stale error and override panel.
- **Rotation success:** the token reveal shows the new token; rotation still skips `onSelfConfigChanged`.
- **The tab deactivated with a token showing:** the token is cleared; returning shows no token.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/self-configuration-tab.js`, `self-config-{status,external,revisions,history}.js`, `agent-editor-controller.js` and `areas/studio.js` (the deactivate hooks), possibly `css/studio.css`, `js/ui/feedback.js` (`led: false`; the `role` option if leg 09 did not add it), `tests/browser/test_ui_*` (the status contract case), `docs/ui-control-inventory.md`.
- `tests/browser/test_studio_self_configuration_*.py` (selectors only), plus the token-attribute test.
- `tests/_ui_ownership_allowance.py`, `tests/test_ui_guards.py`, `the_one/agents.md`.

## Citation Audit
From the leg 10 design review (2026-10-21): the reveal and clipboard code (about `:1140-1171` pre-split), the switches (about `:248-310`), the history `<details>` (about `:379`). Re-locate by symbol at leg start (10a and 10b move them). Cycle-2 review (2026-10-21): approve with changes; applied above (the switch test call sites, `led: false`, the native disclosure, sections and buttons, the token-clearing hooks, the copyField details).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
