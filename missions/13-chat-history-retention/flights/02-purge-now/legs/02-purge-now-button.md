# Leg: purge-now-button

**Status**: completed
**Flight**: [Purge Now](../flight.md)

## Objective

Add a "Purge now" control to the General-tab Danger Zone that calls `DELETE /api/agents/{name}/chat/sessions` only after a two-step confirm — wired through the three-file callback chain (`general-tab.js` render → `agent-editor.js` forward → `studio.js` handler) — and bundle the two DD6 shared-surface pull-ins (the `collectFormData` retention inline comment and the `system_prompt` textarea accessibility label).

## Context

- **Flight DD3** — reuse the canonical `App.confirmDelete` arm-then-fire helper (`confirm.js:38`), exactly as the Danger-Zone Delete Agent button does (`studio.js:handleDeleteEditor`), with a distinct `confirmLabel: 'Confirm Purge?'`. The button **must** contain a `<span data-confirm-title>Purge now</span>` child — `App.confirmDelete` swaps the label via the `[data-confirm-title]` selector (`confirm.js:44`); without that span the first click arms silently with no visible label change, and the behavior test's arm-not-fire step (step 3) becomes unobservable.
- **Keeps the agent selected** — `handlePurgeHistory` mirrors `handleDeleteEditor` but only the agent's *history* is removed, not the agent: it does NOT call `selectAgent`/`renderEmptyEditor`/`loadAll()` (the agent list is unchanged). It flashes the deleted count in place.
- **DD2a (accepted boundary)** — the endpoint deletes DB rows only; in-memory `_sessions` are not evicted. Out of scope for this leg; no frontend concern.
- **DD6 shared-surface bundle** — while in `studio.js` and `general-tab.js` for the purge button, also land (a) the inline comment at the `chat_history_retention_days` `collectFormData` branch (`studio.js:1930-1932`) and (b) a real `<label for>` for the `system_prompt` textarea (`general-tab.js:113`, currently no label association — WCAG 1.3.1/4.1.2).
- This is Leg 2 of 2 — the final autonomous leg. It depends on Leg 1's endpoint (`DELETE /api/agents/{name}/chat/sessions` → `{"status": "ok", "deleted": N}`), which is landed.
- **Callback-chain note**: the wiring bridge is `agent-editor.js:154-157` (the `renderGeneralTab(...)` call currently threads only `onTestProvider` + `onDelete`). Without adding `onPurge` there, the callback never reaches `general-tab.js` — this is the load-bearing forward, **not** the `studio.js` options bag alone.

## Inputs

What exists before this leg runs:
- `general-tab.js` — Danger-Zone block at `:128-139` (delete button at `:135-137` with `<span data-confirm-title>Delete Agent</span>`, `data-testid="delete-agent-btn"`); button wiring at `:147-150`; System-Prompt section at `:111-115` (bare `<textarea data-field="system_prompt">` at `:113`, no `id`/`<label for>`).
- `agent-editor.js` — `renderGeneralTab(...)` call at `:154-157` (threads `onTestProvider`, `onDelete`); callbacks doc-comment at `:31`.
- `studio.js` — `renderAgentEditor` options bag at `:1502-1513` (`onDelete: handleDeleteEditor` at `:1505`); `handleDeleteEditor(deleteBtn)` at `:1616-1643`; `collectFormData` retention branch at `:1930-1932`.
- `confirm.js` — `App.confirmDelete(itemEl, onConfirm, opts)` at `:38`; label swap via `[data-confirm-title]` at `:44`.
- Leg 1's `DELETE /api/agents/{name}/chat/sessions` endpoint (landed).
- Browser-test pattern: `tests/browser/test_flow_agent_tabs.py` (`@pytest.mark.browser`, `app_with_agent` SeededApp + `page` fixtures, `data-testid` locators).

## Outputs

What exists after this leg completes:
- A "Purge now" button in the General-tab Danger Zone (existing agents only), label/testid-distinct from Delete Agent, carrying a `<span data-confirm-title>Purge now</span>` child, wired to `callbacks.onPurge`.
- `onPurge` forwarded through `agent-editor.js` to `general-tab.js`, and registered in the `studio.js` options bag.
- `handlePurgeHistory` in `studio.js` — two-step confirm → `DELETE` the agent's sessions → flash count, agent stays selected.
- DD6 inline comment at the `collectFormData` retention branch.
- `system_prompt` textarea with `id="studio-system-prompt"` and an associated `<label for="studio-system-prompt">System Prompt</label>`.
- A browser test asserting the Purge-now button's Danger-Zone placement, label-distinctness, and `data-confirm-title` span.

## Acceptance Criteria
- [x] A "Purge now" button renders in the General-tab Danger Zone for existing agents (not in create mode), with `data-testid="purge-history-btn"`, a `data-name` attribute, and a `<span data-confirm-title>Purge now</span>` child.
- [x] The Purge-now button is visually and textually **distinct** from the Delete Agent button (distinct visible text and `data-testid`; an operator cannot confuse "wipe history" with "delete the agent").
- [x] Clicking Purge now once **arms** (label swaps to "Confirm Purge?" via `App.confirmDelete`) without issuing any DELETE; a second click within the window fires `DELETE /api/agents/{name}/chat/sessions`.
- [x] On success the deleted count is flashed (`App.showFlash(editorEl, msg, false)` — `isError=false`) and the agent stays selected (no `loadAll()`/`selectAgent`/`renderEmptyEditor`); on transport failure the UI reverts via `revertFn()` and an error flash shows (`isError=true`).
- [x] `onPurge` is forwarded in `agent-editor.js`'s `renderGeneralTab(...)` call and registered in `studio.js`'s `renderAgentEditor` options bag — the callback reaches `general-tab.js`.
- [x] DD6: an inline comment is added at the `collectFormData` `chat_history_retention_days` branch explaining the raw-value-preservation (no `|| default`) choice; the `system_prompt` textarea has `id="studio-system-prompt"` with a matching `<label for="studio-system-prompt">System Prompt</label>`.
- [x] A browser test (`@pytest.mark.browser`) asserts the Purge-now button is present in the Danger Zone, distinct from Delete Agent, and carries the `data-confirm-title` span. The browser suite passes (no regression).
- [x] `ruff check` + `ruff format --check` clean on any touched Python (the browser test); JS edits follow existing file style.

## Verification Steps
- `docker exec the-one pytest tests/browser/<new-test-file>.py -x --timeout 60 -m browser -q` — the new browser test passes. *(The `-m browser` marker is required: `pyproject.toml` addopts deselects `browser` by default, so a bare `pytest tests/browser/...` runs zero tests.)*
- `docker exec the-one pytest tests/browser -x --timeout 60 -m browser -q` — full browser suite green (no regression); pre-existing skips stay skipped.
- Manual/behavior (deferred to flight-level behavior test `agent-purge-now-clears-history`): the two-step confirm → history-gone flow.
- `docker exec the-one ruff check tests/browser/<new-test-file>.py` and `ruff format --check` — clean.

## Implementation Guidance

1. **`general-tab.js` — add the Purge-now button** inside the `if (!isCreate)` Danger-Zone block (`:132-139`), after the Delete Agent button (`:137`), before the closing `</div>` (`:138`):
   ```js
   // Carries `delete-btn` in ADDITION to `purge-history-btn` so it inherits
   // the shared destructive armed-state styling (`.delete-btn.confirm-delete`
   // → red, components.css:1000) — NOT because it deletes the agent. Distinct
   // visible text + data-testid keep it unmistakable from Delete Agent.
   html += '<button type="button" class="btn-muted-destructive delete-btn purge-history-btn" ' +
     'data-testid="purge-history-btn" data-name="' + escapeAttr(cfg.name || '') + '">' +
     '<span data-confirm-title>Purge now</span></button>';
   ```
   - Distinct `data-testid` and visible text from Delete Agent (criterion 2); distinctness is carried by text + testid, NOT color. The button intentionally shares the `delete-btn` class so the destructive **armed** state (red background on `.confirm-delete`, `components.css:1000`) renders on the second-click window — without it, an armed destructive control would lose its standard danger cue (the label still swaps to "Confirm Purge?", but the red emphasis would be absent). (Exact label/placement/wording is a Flight-4 UX-polish concern — "Acceptable variations" in the flight.)
   - **Wiring order is load-bearing**: the Delete Agent button is emitted first (`:135-137`), so the existing `panel.querySelector('.delete-btn')` (`:147`) still resolves to Delete Agent, not the purge button. Do NOT reorder the two buttons. The purge wiring keys on the unique `.purge-history-btn` selector.
   - **Wire it** alongside the existing delete-btn wiring (`:147-150`):
     ```js
     var purgeBtn = panel.querySelector('.purge-history-btn');
     if (purgeBtn && callbacks.onPurge) {
       purgeBtn.addEventListener('click', function () { callbacks.onPurge(purgeBtn); });
     }
     ```

2. **`general-tab.js` — DD6 a11y label** for the System Prompt textarea (`:111-115`). Replace the bare `section-title` + textarea with a real label association, consistent with the `field-row`/`<label for>` idiom the Behavior inputs use:
   ```js
   html += '<div class="editor-section"><div class="section-title">System Prompt</div>';
   html += '<label for="studio-system-prompt" class="visually-hidden">System Prompt</label>';
   html += '<textarea id="studio-system-prompt" class="field-textarea" data-field="system_prompt" rows="8" placeholder="Instructions for the agent...">' +
     escapeHtml(cfg.system_prompt || '') + '</textarea>';
   html += '</div>';
   ```
   - Uses the project's existing **`.visually-hidden`** global utility (defined under `@layer areas` in `static/css/admin.css:505` and `static/css/chat.css:382`) — **not** `sr-only`, which does not exist in this codebase. The section already shows a visible "System Prompt" title, so a visually-hidden label gives the programmatic `<label for>`/`id` association (WCAG 1.3.1/4.1.2) without a duplicate **visible** label. Do **not** introduce a second visible "System Prompt" label.
   - Fallback only if `.visually-hidden` were somehow unavailable: give the existing visible title an `id` and point the textarea at it via `aria-labelledby`. The criterion is a programmatic label association; `.visually-hidden` is the verified primary mechanism here.

3. **`agent-editor.js` — forward `onPurge`** in the `renderGeneralTab(...)` call (`:154-157`):
   ```js
   window.App.studio.renderGeneralTab(generalPanel, agent, providers, {
     onTestProvider: callbacks.onTestProvider,
     onDelete: callbacks.onDelete,
     onPurge: callbacks.onPurge
   });
   ```
   - Also add `onPurge` to the callbacks doc-comment at `:31` for consistency.

4. **`studio.js` — add `handlePurgeHistory`** mirroring `handleDeleteEditor` (`:1616-1643`), e.g. immediately after it:
   ```js
   function handlePurgeHistory(purgeBtn) {
     var name = self._selectedAgent ? self._selectedAgent.name : null;
     if (!name) return;
     App.confirmDelete(purgeBtn, function (btn, revertFn) {
       fetch('/api/agents/' + encodeURIComponent(name) + '/chat/sessions', { method: 'DELETE' })
         .then(function (r) {
           if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || 'Purge failed'); });
           return r.json();
         })
         .then(function (body) {
           var n = body && typeof body.deleted === 'number' ? body.deleted : 0;
           App.showFlash(editorEl, 'Purged ' + n + ' conversation' + (n === 1 ? '' : 's'), false);
         })
         .catch(function (err) {
           revertFn();
           App.showFlash(editorEl, (err && err.message) || 'Purge failed', true);
         });
     }, { confirmLabel: 'Confirm Purge?' });
   }
   ```
   - Reads `self._selectedAgent.name` like `handleDeleteEditor` (not the button's `data-name`).
   - Does NOT call `loadAll()`/`selectAgent`/`renderEmptyEditor` — agent stays selected (criterion 4). Confirm the exact `App.showFlash` signature against `handleDeleteEditor`'s usage (`studio.js:1640`) and match it.
   - **Register the callback** in the `renderAgentEditor` options bag near `onDelete` (`:1505`): add `onPurge: handlePurgeHistory,`.

5. **`studio.js` — DD6 inline comment** at the `collectFormData` retention branch (`:1930-1932`). Add a short comment above the `else if (key === 'chat_history_retention_days')` branch explaining that the raw parsed value is preserved (not coerced via `|| default`) so a typed out-of-range value (e.g. `0` or `400`) reaches the server and the 422 reject surfaces at the UI, rather than being silently clamped to the default client-side. (This is the contract the `agent-retention-setting-roundtrip` behavior-test lower-bound variant depends on.)

6. **Browser test** — add `tests/browser/test_flow_studio_purge_now_button.py` (or similar), mirroring `test_flow_agent_tabs.py`:
   - `@pytest.mark.browser`, use `app_with_agent` + `page`.
   - Navigate to Studio, select the seeded agent, ensure the General tab is active, scroll to the Danger Zone.
   - Assert `[data-testid="purge-history-btn"]` is visible, its text differs from `[data-testid="delete-agent-btn"]`, and it contains a `[data-confirm-title]` child reading "Purge now".
   - **Cheap arm assertion** (exercises the `data-confirm-title` wiring without entering the behavior-test's DELETE territory): click the purge button **once**, then assert the `[data-confirm-title]` child text changed to "Confirm Purge?". Do NOT click a second time (that would fire the DELETE — the behavior test owns the fire→history-gone flow). Seeding sessions is unnecessary for this DOM-level check.
   - This is a DOM/placement + arm check only — the full two-step confirm→gone flow is the behavior test's job, not duplicated here.

7. **Run** the browser suite (`-m browser`) and `ruff` on the new test file (Verification Steps). `make rebuild` is not required for JS/test edits — the container bind-mounts `./the_one` and `./tests` (confirmed in Leg 1).

## Edge Cases
- **Missing `data-confirm-title` span** → first click arms silently (no visible label change); the behavior test step 3 becomes unobservable. The span is mandatory (DD3) — covered by the browser test asserting its presence.
- **No selected agent** (`self._selectedAgent` null) → `handlePurgeHistory` no-ops, mirroring `handleDeleteEditor`.
- **Transport failure** → `revertFn()` restores the armed button to "Purge now" and an error flash shows (mirrors the delete path).
- **Create mode** → the Danger Zone (and thus Purge now) is not rendered (`if (!isCreate)`), so no purge affordance for an unsaved agent.
- **Label mechanism** → use the verified `.visually-hidden` utility (step 2); fall back to `aria-labelledby` against the existing visible title only if it were unavailable — never add a duplicate visible label.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/general-tab.js` — Purge-now button + wiring; `system_prompt` a11y label.
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — forward `onPurge`; doc-comment.
- `the_one/interfaces/web/static/js/areas/studio.js` — `handlePurgeHistory`; options-bag registration; DD6 retention comment.
- `tests/browser/test_flow_studio_purge_now_button.py` — new browser test (DOM/placement).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:** *(Under `/agentic-workflow`, this is the final autonomous leg — but commit is still deferred to the flight-level review. Do NOT commit at leg end; mark `landed`, update the flight log, hand off.)*

- [ ] All acceptance criteria verified
- [ ] Browser test passing (`-m browser`); full browser suite green; `ruff` clean
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT commit, do NOT mark the flight `landed`, do NOT check off the flight in mission.md — the Flight Director handles flight-level review, commit, and landing after this leg
- [ ] Signal `[HANDOFF:review-needed]`

## Citation Audit

8 citations verified against current code at leg design time:
- `general-tab.js:128-139` (Danger-Zone block; delete button `:135-137` with `data-confirm-title` span), `:147-150` (button wiring), `:111-115` (System-Prompt section; bare textarea `:113`) — OK.
- `agent-editor.js:154-157` (`renderGeneralTab` call threading `onTestProvider` + `onDelete`), `:31` (callbacks doc-comment) — OK.
- `studio.js:1502-1513` (options bag; `onDelete` `:1505`), `:1616-1643` (`handleDeleteEditor`), `:1930-1932` (`collectFormData` retention branch) — OK.
- `confirm.js:38` (`App.confirmDelete`), `:44` (`[data-confirm-title]` selector resolution), `:72` (the actual `textContent` label swap), `:52-53` (revert restore) — OK.
- `components.css:1000` (`.delete-btn.confirm-delete` armed red state) — OK; the purge button shares `delete-btn` to inherit it.
- `static/css/admin.css:505`, `static/css/chat.css:382` (`.visually-hidden` global utility under `@layer areas`) — OK (replaces the nonexistent `sr-only`).
- `static/js/app.js:266` (`App.showFlash(container, msg, isError)`) — OK; usage matches `handleDeleteEditor` (`studio.js:1640`).
- `tests/browser/conftest.py:236` (`app_with_agent` fixture) — OK.
- `tests/browser/test_flow_agent_tabs.py` (`@pytest.mark.browser` + `app_with_agent`/`page` pattern) — OK; `pyproject.toml:76` addopts deselects `browser` by default, marker at `:80` — OK.
