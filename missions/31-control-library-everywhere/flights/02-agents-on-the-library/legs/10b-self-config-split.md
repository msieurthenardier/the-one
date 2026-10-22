# Leg: self-config-split

**Status**: completed
**Flight**: [Agents on the library](../flight.md)

## Objective
Split `self-configuration-tab.js` (about 1415 lines, more after 10a) into four modules, with **no behaviour or DOM change**. The modules share one per-mount context object. This is a pure restructure, like legs 02-03: any visible or test change is a defect.

## Context
- **Flight decisions:** DD1 (the restructure rules: pins are retargeted, never relaxed), DD7 (the split sizes), DD10.
- **Leg 10a has landed:** the tab has `setAgent`, local refetches with a generation counter, and the `pendingAction` bridge consumed by its own re-render. Read its flight-log entry.
- **The surface is security-sensitive** (CLAUDE.md "Self-configuration surface"; SECURITY-MODEL.md). Moving the code must not change any branch.

## Acceptance Criteria
- [ ] **Four modules plus the entry**, each ≤ 800 lines (`wc -l`). Target sizes from the design review (cycle 2 added the fourth module: without it the status module was about 770 lines before 10a's additions, and it isolates the most sensitive code):
  - `self-config-status.js` (about 450): the panel frame, the enable and approval-mode switches and status lines, the `actionStatus` focus bridge, the initial loads and refetches;
  - `self-config-external.js` (about 300): the external credentials (grant, list, rotate, revoke) and the token reveal;
  - `self-config-revisions.js` (about 350): the pending queue, the cards, approve, dismiss, the stale panel and override, and the diff helpers (`commonPrefixLen` … `renderDiffedValues`);
  - `self-config-history.js` (about 250): the history list, restore nodes and LEDs, and the timestamp formatters.

  The split points can move, but the size limit is binding. The public entry `App.studio.renderSelfConfigurationTab(panel, agent, callbacks)` and the handle it returns (`{setAgent, destroy}`, from 10a) stay one function on one name, so `agent-editor.js` is unchanged.
- [ ] **A shared context, not globals.** The modules communicate through one object built per mount: the panel, the agent, the callbacks, the generation counter, `actionStatus`, the mount-local `pendingAction` (10a), and the refetch functions. Modules read `ctx.agent` at call time, and `setAgent` updates it. No new `window.App` state beyond the four module namespaces.
- [ ] **The security logic moves, with identifier rewrites only.** A closure variable becomes a ctx field (for example `pendingAction` → `ctx.pendingAction`). Each rewrite is listed in the flight log. The condition lines, the `onApproveRevision(..., true)` call and the `side` lines stay byte-identical. This covers these branches:
  - the stale result handling and the override path (`onApproveRevision(name, id, true)` only from the override button);
  - restore only on `applied` revisions, with `side`;
  - the token reveal and its hide paths;
  - credential mint, rotate and revoke not calling `onSelfConfigChanged`.
- [ ] **Script order and pins.** `index.html` loads the four modules before the entry file. `tests/test_index_asset_cache_busting.py`'s script count pin (`== 86` at `:95` at the cycle-2 review; re-read it at leg start) is raised by 4, with the reason in the flight log. Sink and allowance rows for `self-configuration-tab.js` are **rekeyed** to the module each piece moved to, with the same totals (the printed dicts; no total rises).
- [ ] **No behaviour change:** the four self-configuration test files, 10a's DD9-3 tests and the agents lane pass with **no test edits**.
- [ ] **Captures:** `agent-self-configuration` to `…/m31-f2-after-10b/`, byte-identical in layout to the 10a state.
- [ ] **Gates:** `make test-unit`; the static guards and ownership checks; the `agents` lane under netns.
- [ ] **Docs:** `the_one/agents.md` gets the four modules and the shared context.

## Verification Steps
- `wc -l` on the four modules and the entry.
- `git diff --stat` and a read of the moved security branches (moves only).
- The lane above with no test file changed.

## Implementation Guidance
1. Map every function in the file to a module, and list what each one reads from the render closure: that list is the shared context.
2. Move the history first (fewest dependencies), then the revisions, then the external credentials, then leave the status with the entry.
3. Run the four test files after each move.

## Edge Cases
- **Closures over render-local variables** (for example `agent`, `setBusy`, the error lines) become context fields or function arguments. None becomes module-level state.
- **The diff helpers are pure:** they move as they are.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/self-configuration-tab.js` and four new modules.
- `the_one/interfaces/web/static/index.html`, `tests/test_index_asset_cache_busting.py`.
- `tests/_ui_ownership_allowance.py`, `tests/test_ui_guards.py` (rekeyed rows).
- `the_one/agents.md`.

## Citation Audit
Function map checked at writing (2026-10-21, pre-10a): `self-configuration-tab.js` helpers `:114-191`, `renderSelfConfigurationTab` `:193`, `renderState` `:579`, `renderApprovalState` `:613`, `renderCard` `:643`, `renderQueue` `:845`, `renderRestoreNodeRow` `:891`, `renderHistory` `:960`, the external credentials `:1122-1380`, the initial load `:1380-1412`. Re-map at leg start (10a changes the file). Cycle-2 review (2026-10-21): approve with changes; applied above (identifier rewrites, the fourth module, the pin).

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
