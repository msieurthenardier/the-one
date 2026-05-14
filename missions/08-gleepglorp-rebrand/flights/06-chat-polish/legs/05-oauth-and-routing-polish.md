# Leg: oauth-and-routing-polish

**Status**: completed
**Flight**: [Chat Polish](../flight.md)

## Objective

Polish the OAuth `auth_required` consent affordance: add a small attribution line ABOVE the existing `btn-filled-primary` Login button so the button's *why* is explicit before the *what*, per the flight spec's pre-authorized "attribution near it" polish. Document the dispositions for the two HAT-deferred questions (auto-open trace shell + chat-surface routing/nav fixes) so L06 HAT enters with a clear "what's left to confirm" surface. The auto-open decision and any chat-surface routing issues are EXPLICITLY deferred to L06 HAT per the flight spec — this leg adds nothing on those axes and instead enumerates what the HAT must confirm. Out of scope per flight spec: restyling the Login button itself; relitigating the live-vs-replay namespace contract; any cross-area routing work (those route to F7 triage).

## Context

- **Design Decision (flight.md)**: "OAuth consent button visual treatment → Resolved: the existing `btn-filled-primary` styling continues to suffice; F6's polish leg may iterate on placement within the trace shell (e.g., spacing, **attribution near it**) but does NOT restyle the button itself." This leg picks the "attribution near it" half of the operator-pre-authorized scope.
- **Design Decision (flight.md)**: "OAuth `auth_required` auto-open trace shell → Resolved: REVISIT during F6 HAT (mission convention is operator-judgment for visibility-of-affordance questions). Default: leave behavior as-is per L04 HAT Scenario 8. If F6 HAT discovers real visibility issues, apply the 1-line `details.open = true` fix in `getOrCreateTrace`'s `auth_required` path." This leg does NOT change auto-open behavior — that's an L06 HAT decision.
- **Design Decision (flight.md)**: "Routing fixes scoped to chat surface only → routing/navigation issues SURFACED during F6's polish legs are fixed in scope; cross-area issues that touch other surfaces get logged as KIs for the F7 UI Performance Audit flight's triage." Recon during L03 / L04 surfaced ZERO chat-surface routing defects, and the autonomous-leg surface area cannot exercise deep-link / refresh / back-button behavior the way a human HAT can. L05 records this disposition explicitly.
- **Current Login-button render** (`the_one/interfaces/web/static/js/areas/chat.js:506-538`): `renderLoginRequiredButton(data)` constructs a `<button class="btn-filled-primary login-required-btn">` with text `"Login required for " + label`, where `label = source_name || sourceNames[source_id] || source_id || '<unknown>'`. The button is mounted via `App.chat.appendToTrace(authTrace, btn)` (path 1) OR direct `messagesEl.appendChild(btn)` (path 2, legacy/null fallback for synthetic test events).
- **Trace body shape** (`the_one/interfaces/web/static/js/areas/chat/trace-shell.js:50-59`): `appendToTrace(traceEl, msgEl)` appends a child to `.trace-body` and increments the `.trace-count` span. The count is structural ("how many items in this trace"); adding an attribution line as a separate child would increment the count by an additional 1 per auth_required event. That is undesirable — the attribution is sub-rendering of the button, not a separate trace item.
- **Solution shape**: wrap the attribution + button in a SINGLE container `<div class="login-required-group">` and append THAT to the trace body. `appendToTrace` then increments by 1 per auth_required event regardless of how many sub-elements the group contains. The legacy direct-append-to-messages path (`messagesEl.appendChild(btn)`) is also updated to append the group instead of the bare button — keeping the two paths shape-compatible.
- **Existing CSS targets** (`chat.css:156-158, 214`):
  - `.area-chat .trace-shell .trace-body .login-required-btn { align-self: flex-start; }` — trace-mounted button
  - `.area-chat .messages .login-required-btn { align-self: flex-start; }` — legacy direct-append button
  - Both stay as-is; the new wrapper `.login-required-group` also gets `align-self: flex-start` rules at the same two scopes so the group hugs the left edge in both mount paths.
- **F5 L02 carry-forward**: the `parent_message_id` plumbing through `_auth_required_event_from_metadata` is what binds the auth_required event to its trace shell. L05 does NOT touch that contract — only the in-trace rendering shape changes.

## Inputs

Files that exist before this leg runs:
- `the_one/interfaces/web/static/js/areas/chat.js` — `renderLoginRequiredButton` at lines 506-538 (button-only render); mounts via `appendToTrace` (line 533) or direct `messagesEl.appendChild` fallback (line 535)
- `the_one/interfaces/web/static/js/areas/chat/trace-shell.js` — `appendToTrace(traceEl, msgEl)` accepts any element; appends to `.trace-body` and increments the count by 1
- `the_one/interfaces/web/static/css/chat.css` — `.trace-shell .trace-body .login-required-btn` rule at line 156-158; `.messages .login-required-btn` rule at line 214

State that must be true:
- L04 (`message-stream-polish`) landed; broad pytest 1627p/4s/370d exit 0; browser suite 315p/35s preserved
- Container running; host `make rebuild` reachable

## Outputs

Files modified:
- `the_one/interfaces/web/static/js/areas/chat.js` — `renderLoginRequiredButton` builds a wrapper `<div class="login-required-group">`, appends the attribution line `<div class="login-required-attribution">Authorization required to continue.</div>` first, then the existing button, and mounts the WRAPPER (not the bare button) via either `appendToTrace` or `messagesEl.appendChild`
- `the_one/interfaces/web/static/css/chat.css` — adds `.area-chat .trace-shell .trace-body .login-required-group { ... }` (align-self: flex-start; display: flex; flex-direction: column; gap: 4px), `.area-chat .messages .login-required-group { ... }` (same align-self), and `.area-chat .login-required-attribution { ... }` (muted body-sm font, optionally italic)

State after:
- The Login button is visually preceded by a single muted attribution line explaining WHY the button appeared, making the affordance self-documenting even when collapsed/expanded trace state is ambiguous to the user
- The trace-count value increments by 1 per `auth_required` event (NOT 2) — the wrapper preserves the original count semantics
- Both mount paths (trace and legacy direct) render the group identically
- No restyle of the Login button itself — `btn-filled-primary` styling preserved exactly
- L06 HAT enters with a clear "remaining decisions" surface: (a) auto-open trace shell on auth_required, (b) chat-surface routing/nav verification, (c) any deferred bugs surfaced during HAT
- Broad pytest: 1627p/4s/370d preserved
- Browser suite: 315/35 preserved (no new selectors or class names that would conflict with existing test assertions)

## Acceptance Criteria

- [ ] `the_one/interfaces/web/static/js/areas/chat.js` — `renderLoginRequiredButton` constructs a wrapper `<div class="login-required-group" data-source-id="...">` (data-source-id mirrored to the wrapper so the existing `clearLoginRequiredButton`-style cleanup still works against the wrapper or button — see Implementation step 2)
- [ ] The wrapper contains, in order: (1) a `<div class="login-required-attribution">Authorization required to continue.</div>` element, (2) the existing `<button class="btn-filled-primary login-required-btn">` with all its current `data-*` attributes and click handler preserved
- [ ] The button's existing text remains EXACTLY `"Login required for " + label` — NO change to the button label
- [ ] The button's existing `data-source-id`, `data-tool-call-id`, `data-resource-metadata-url`, `data-consent-url` attributes remain on the BUTTON (not the wrapper) — preserving any external test or runtime code that queries them
- [ ] The mount call uses the wrapper, not the bare button: `appendToTrace(authTrace, group)` and `messagesEl.appendChild(group)` respectively
- [ ] `clearLoginRequiredButton` (actual chat.js range: lines 370-391; uses `querySelectorAll` + a loop, NOT `querySelector`) is updated to remove the WRAPPER when present. For each matched button: walk up to `closest('.login-required-group')`; if found, capture the wrapper's `.parentNode` as `parent` (the `.trace-body` or `.messages` container), then remove the wrapper; if no wrapper parent (legacy event, pre-L05 DOM), capture the button's `.parentNode` and remove the button. After removal, the EXISTING empty-trace-shell cleanup logic at chat.js:380-389 (check `parent.classList.contains('trace-body')` and `parent.children.length === 0`; drop the enclosing `.trace-shell` and clear `traceShells[key]`) MUST continue to fire — that's L03's "no empty chrome lingering" guarantee. The L05 edit retargets WHAT is removed but does NOT touch the empty-shell cleanup logic.
- [ ] Empty-trace-shell cleanup (chat.js:380-389) still fires after wrapper removal — when the wrapper was the only child of `.trace-body`, the enclosing `.trace-shell` is removed AND `traceShells[key]` is cleared from the registry. Verify by: synthesizing a single-auth_required-event scenario, calling `clearLoginRequiredButton` for that source_id, and asserting the trace shell is gone from the DOM and `traceShells` registry has no entry for the parent_message_id
- [ ] `the_one/interfaces/web/static/css/chat.css` — adds three new rules:
  - `.area-chat .trace-shell .trace-body .login-required-group { align-self: flex-start; display: flex; flex-direction: column; gap: 4px; }`
  - `.area-chat .messages .login-required-group { align-self: flex-start; display: flex; flex-direction: column; gap: 4px; }`
  - `.area-chat .login-required-attribution { color: var(--fg-muted); font-size: var(--font-size-body-sm); font-style: italic; }` (the muted-italic treatment is the chat surface's existing "secondary informational" vocabulary; the WCAG check is the same calculation as L03's `.session-list-empty` — if `--fg-muted` fails AA against the trace-body background in either theme, fall back to `--fg-secondary`)
- [ ] Existing rules at `chat.css:158-160` and `chat.css:214` (the bare `.login-required-btn align-self: flex-start` rules) STAY — they continue to apply if any test fixture or legacy code injects a bare button without the wrapper
- [ ] The trace-count value in the trace shell summary increments by 1 per auth_required event (verify via the existing `tests/test_app_websocket_pause_resume.py` auth_required scenarios — those tests' assertions should not see a count of 2 where they previously saw 1; if any do, the test was previously incorrect and the fix is to update them in scope, NOT to revert the wrapper approach)
- [ ] FD Notes section in `flight-log.md` records the L05 dispositions on the three deferred items: (a) auto-open trace shell → stays deferred to L06 HAT, (b) chat-surface routing/nav → no defects surfaced during L03/L04, L06 HAT enumerates the verification surface, (c) opportunistic bug fixes → none surfaced; document explicitly so the L06 HAT scope is bounded
- [ ] Broad pytest exits code 0 with 1627p/4s/370d (UNCHANGED from L04)
- [ ] Browser suite preserved at 315 passing / 35 skipped

## Verification Steps

- **DOM shape (live)**: trigger an auth_required scenario (or use the dev-mode mock provider's auth_required test path); inspect-element on the trace shell; confirm structure is `<div class="trace-shell"><details><summary>...</summary><div class="trace-body"><div class="login-required-group"><div class="login-required-attribution">Authorization required to continue.</div><button class="btn-filled-primary login-required-btn">Login required for {source_name}</button></div></div></details></div>`
- **Trace count = 1**: in the same scenario, verify the `.trace-count` span reads `1` not `2` (one item in the trace body, not two)
- **Attribution is muted + non-interactive**: confirm the attribution `<div>` has no role / tabindex / click handler — purely informational; keyboard tab order skips it
- **Button click still works**: click the Login button; the existing `startLoginFlow(data)` handler fires; the OAuth popup opens as before
- **Clear-and-re-render idempotency**: in the WS-reconnect cycle (or via `clearLoginRequiredButton` directly), confirm the wrapper is removed cleanly — no orphaned attribution `<div>` left behind in the DOM after the button is cleared
- **Both mount paths render identically**: synthesize a legacy null-`parent_message_id` auth_required event via a test fixture; confirm `messagesEl.appendChild(group)` produces the same DOM shape as the trace-mounted path
- **WCAG contrast on `.login-required-attribution`**: same calculation as L03's `.session-list-empty` — `--fg-muted` against the trace-body's effective background (which inherits from `.messages` → page background). If `--fg-muted` fails AA at body-sm in EITHER theme, swap to `--fg-secondary` per the leg-authorized fallback (same pattern L03 used). Light theme is the likely failure mode per L03's empirical finding.
- **Broad pytest**: `docker exec the-one pytest -x --timeout 30` exits 0 with 1627p/4s/370d.
- **Browser suite**: `docker exec the-one pytest -m browser --timeout 60 --tb=line` returns 315/35.
- **Test-fixture scan**: `grep -rn "login-required-btn" tests/` — if any test queries the button directly with no expectation of a wrapper ancestor, the test still passes (the button is still present, the click handler still fires, the data-attributes are still on the button). If any test queries via `.firstChild` or sibling position assertions, update in scope.
- **FD Notes entry**: `flight-log.md` "Flight Director Notes" section includes the L05 disposition record before the leg lands.

## Implementation Guidance

1. **Edit `the_one/interfaces/web/static/js/areas/chat.js` `renderLoginRequiredButton` (lines 506-538)**:

   ```javascript
   // BEFORE (abbreviated)
   function renderLoginRequiredButton(data) {
     clearLoginRequiredButton(data);
     if (data.source_id && data.source_name) {
       sourceNames[data.source_id] = data.source_name;
     }
     var btn = document.createElement('button');
     btn.type = 'button';
     btn.className = 'btn-filled-primary login-required-btn';
     btn.dataset.sourceId = data.source_id || '';
     // ... (label / textContent / click handler unchanged)
     var authTrace = getOrCreateTrace(data.parent_message_id);
     if (authTrace) {
       App.chat.appendToTrace(authTrace, btn);
     } else {
       messagesEl.appendChild(btn);
     }
     messagesEl.scrollTop = messagesEl.scrollHeight;
   }

   // AFTER
   function renderLoginRequiredButton(data) {
     clearLoginRequiredButton(data);
     if (data.source_id && data.source_name) {
       sourceNames[data.source_id] = data.source_name;
     }
     // Wrapper groups the attribution + button so appendToTrace increments
     // the trace-count by 1 per auth_required event (NOT 2).
     var group = document.createElement('div');
     group.className = 'login-required-group';
     group.dataset.sourceId = data.source_id || '';

     var attr = document.createElement('div');
     attr.className = 'login-required-attribution';
     attr.textContent = 'Authorization required to continue.';
     group.appendChild(attr);

     var btn = document.createElement('button');
     btn.type = 'button';
     btn.className = 'btn-filled-primary login-required-btn';
     btn.dataset.sourceId = data.source_id || '';
     btn.dataset.toolCallId = data.tool_call_id || '';
     btn.dataset.resourceMetadataUrl = data.resource_metadata_url || '';
     if (data.consent_url) btn.dataset.consentUrl = data.consent_url;
     var label = data.source_name
       || (data.source_id && sourceNames[data.source_id])
       || data.source_id
       || '<unknown>';
     btn.textContent = 'Login required for ' + label;
     btn.addEventListener('click', function () {
       startLoginFlow(data);
     });
     group.appendChild(btn);

     var authTrace = getOrCreateTrace(data.parent_message_id);
     if (authTrace) {
       App.chat.appendToTrace(authTrace, group);
     } else {
       messagesEl.appendChild(group);
     }
     messagesEl.scrollTop = messagesEl.scrollHeight;
   }
   ```

2. **Update `clearLoginRequiredButton` (actual chat.js range: 370-391)** to remove the wrapper when present while PRESERVING the existing `querySelectorAll`+loop pattern AND the empty-trace-shell cleanup at lines 380-389. Cycle-1 design review confirmed: no OAuth-popup-cleanup logic exists in the current body — but the loop structure and empty-shell cleanup ARE there and MUST be retained. Pattern:

   ```javascript
   // BEFORE (chat.js:370-391, full body)
   function clearLoginRequiredButton(data) {
     var sid = data && data.source_id ? data.source_id : null;
     var sel = sid
       ? '.login-required-btn[data-source-id="' + cssEscape(sid) + '"]'
       : '.login-required-btn';
     var existing = messagesEl.querySelectorAll(sel);
     for (var i = 0; i < existing.length; i++) {
       var btn = existing[i];
       var parent = btn.parentNode;
       if (parent) parent.removeChild(btn);
       // L03: if the button was inside a now-empty trace-body, also drop
       // the enclosing trace shell so an empty chrome doesn't linger.
       if (parent && parent.classList && parent.classList.contains('trace-body') && parent.children.length === 0) {
         var shell = parent.closest('.trace-shell');
         if (shell && shell.parentNode) {
           var key = shell.dataset.parentMsgId;
           shell.parentNode.removeChild(shell);
           if (key) delete traceShells[key];
         }
       }
     }
   }

   // AFTER
   function clearLoginRequiredButton(data) {
     var sid = data && data.source_id ? data.source_id : null;
     var sel = sid
       ? '.login-required-btn[data-source-id="' + cssEscape(sid) + '"]'
       : '.login-required-btn';
     var existing = messagesEl.querySelectorAll(sel);
     for (var i = 0; i < existing.length; i++) {
       var btn = existing[i];
       // L05: prefer removing the wrapper when present (post-L05 DOM);
       // fall back to the bare button (legacy / pre-L05 / test-synthesized).
       var group = btn.closest('.login-required-group');
       var toRemove = group || btn;
       var parent = toRemove.parentNode;
       if (parent) parent.removeChild(toRemove);
       // L03: if the removal left an empty trace-body, also drop the
       // enclosing trace shell so an empty chrome doesn't linger.
       // (Unchanged from pre-L05 — the wrapper sits inside .trace-body
       // exactly like the bare button did, so `parent` is still the
       // .trace-body in the trace-mount path.)
       if (parent && parent.classList && parent.classList.contains('trace-body') && parent.children.length === 0) {
         var shell = parent.closest('.trace-shell');
         if (shell && shell.parentNode) {
           var key = shell.dataset.parentMsgId;
           shell.parentNode.removeChild(shell);
           if (key) delete traceShells[key];
         }
       }
     }
   }
   ```

   The diff is small: capture `var group = btn.closest('.login-required-group');` → choose `toRemove = group || btn` → remove `toRemove` and use ITS parent for the empty-shell check. Everything else stays byte-identical.

3. **Edit `the_one/interfaces/web/static/css/chat.css`** — append three new rules near the existing `.login-required-btn` rules (around lines 156-158 and 214). Place the trace-scope rule next to the existing trace-scope button rule; the messages-scope rule next to the existing messages-scope button rule; the attribution rule can go at either scope (it's the same in both mount paths). Suggested form:

   ```css
   /* Inside .trace-shell .trace-body — same align-self as the bare button rule */
   .area-chat .trace-shell .trace-body .login-required-group {
     align-self: flex-start;
     display: flex;
     flex-direction: column;
     gap: 4px;
   }
   /* Direct-mount fallback (legacy auth_required events without parent_message_id) */
   .area-chat .messages .login-required-group {
     align-self: flex-start;
     display: flex;
     flex-direction: column;
     gap: 4px;
   }
   /* Attribution line — muted, italic, sibling to the button */
   .area-chat .login-required-attribution {
     color: var(--fg-muted);
     font-size: var(--font-size-body-sm);
     font-style: italic;
   }
   ```

   **WCAG fallback**: per L03's empirical finding, `--fg-muted` failed AA against `--sidebar-bg` in the light theme. The trace-body's effective background inherits from the assistant message bubble's `--surface-translucent` over the page `bg-gradient` — different background than L03's case. Test with browser devtools contrast picker in BOTH themes before signoff. If `--fg-muted` fails, swap to `var(--fg-secondary)` and document the swap in the flight log (mirror L03's documentation pattern).

4. **Run host `make rebuild`**, then `make _ensure-playwright` if Chromium was wiped (per L03/L04 pattern).

5. **Run targeted browser tests first**, then broad suite:

   ```bash
   docker exec the-one pytest tests/browser/test_flow_chat.py -x --timeout 60 -v
   docker exec the-one pytest tests/test_app_websocket_pause_resume.py -x --timeout 30 -v
   docker exec the-one pytest -x --timeout 30
   docker exec the-one pytest -m browser --timeout 60 --tb=line
   ```

   The `test_app_websocket_pause_resume.py` file is the primary auth_required-shape integration test; verify any trace-count assertions still hold (the wrapper preserves count=1 per event).

6. **Document L05 dispositions in flight-log.md FD Notes** (Flight Director Notes) section. Add a subsection like:

   ```markdown
   ### 2026-05-14 — L05 dispositions on HAT-deferred items

   - **Auto-open trace shell on auth_required**: stays deferred to L06 HAT per flight spec's "default: leave behavior as-is per L04 HAT Scenario 8" disposition. L05 does NOT change `getOrCreateTrace`'s auth_required path. If the operator surfaces a real visibility concern at HAT, the 1-line `details.open = true` fix can land inline during the HAT cycle.
   - **Chat-surface routing/nav fixes**: no defects surfaced during L03 / L04 autonomous-mode polish or implementation. The autonomous-leg surface area cannot exercise deep-link / refresh / back-button behavior the way a human HAT can. L06 HAT enumerates the verification surface (deep-link to `#chat/sessions/{id}` resolves; hard-refresh on a session preserves visible state; browser back/forward through sessions is sensible; new-session URL clear and re-set works). Any defects surfaced at HAT get inline fixes or KI'd to F7 per the flight spec's "Routing fixes scoped to chat surface only" decision.
   - **Opportunistic bug fixes**: none surfaced during L03 / L04 polish work. Scope at HAT is the standard "fix-in-scope if quick, log as KI otherwise" pattern.
   ```

7. **Do NOT commit** — Flight Director batches all 5 leg commits after L05.

## Edge Cases

- **`clearLoginRequiredButton` legacy DOM**: a WS-reconnect cycle could replay an auth_required event whose previous render produced a bare button (pre-L05 DOM). The `closest('.login-required-group')` fallback returns `null`; the code then removes the bare button. Verify the fallback covers this. The previous logic at chat.js:374 was already shape-agnostic ("remove what was queried"); the new logic preserves that.
- **Trace-count assertions in tests**: `tests/test_app_websocket_pause_resume.py` asserts auth_required events fire under specific scenarios. If any test queries the trace-count value directly and asserts `2` (which would have been wrong even pre-L05 since the button was ONE element in the trace body), update in scope. More likely: tests query `tool_call_id` or event presence, not trace-count.
- **The `closest()` API**: standard since IE11+. The codebase already uses it elsewhere (`grep "closest(" the_one/interfaces/web/static/js/`); no polyfill needed.
- **The wrapper takes `data-source-id`**: the existing `clearLoginRequiredButton` query was `.login-required-btn[data-source-id="..."]`. The wrapper also gets `data-source-id` (so a future cleanup query could match the wrapper directly), but the existing query still works because the button retains its own `data-source-id`. Both are correct.
- **Attribution text localization**: hardcoded English string. The project has no i18n today (verified by `grep -rn "i18n\|gettext\|locale" the_one/interfaces/web/static/`). Localization is out of scope for F6.
- **Inline vs block attribution**: chose `<div>` over `<span>` to take a flex line of its own; the wrapper's `flex-direction: column` makes either work, but `<div>` matches the existing `msg-attribution` pattern (chat.css:160-163) where the chat surface uses block-level attribution lines.
- **OAuth popup-cleanup logic in `clearLoginRequiredButton`**: cycle-1 review confirmed NO popup-cleanup logic exists in the current body (chat.js:370-391) — the function only does DOM removal + the L03 empty-trace-shell cleanup. The L05 edit preserves that cleanup verbatim and only changes WHAT is removed (wrapper vs bare button).

## Files Affected

- `the_one/interfaces/web/static/js/areas/chat.js` — wrap `renderLoginRequiredButton` output in `.login-required-group` with an attribution `<div>`; update `clearLoginRequiredButton` to remove the wrapper when present
- `the_one/interfaces/web/static/css/chat.css` — add three new rules (trace-scope group, messages-scope group, attribution); existing `.login-required-btn` rules stay
- `missions/08-gleepglorp-rebrand/flights/06-chat-polish/flight-log.md` — append L05 dispositions on the three HAT-deferred items in the FD Notes section

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (broad pytest exit 0 with 1627p/4s/370d; browser suite 315/35 preserved)
- [ ] Update flight-log.md with leg progress entry AND with the L05 dispositions on HAT-deferred items (Implementation step 6)
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md yet — that happens during the POST-L05 commit batch (which the Flight Director runs after this leg lands)
- [ ] Do NOT commit — Flight Director batches commits after L05

---

## Citation Audit

7 source-code citations verified against current code at leg design time:
- `the_one/interfaces/web/static/js/areas/chat.js:506-538 — "renderLoginRequiredButton"` — OK
- `the_one/interfaces/web/static/js/areas/chat.js:370-391 — "clearLoginRequiredButton"` — OK (cycle-1 verified the exact range; uses `querySelectorAll` + for-loop with the L03 empty-trace-shell cleanup at lines 380-389)
- `the_one/interfaces/web/static/js/areas/chat.js:533 — "App.chat.appendToTrace(authTrace, btn)"` — OK
- `the_one/interfaces/web/static/js/areas/chat/trace-shell.js:50-59 — "appendToTrace"` — OK
- `the_one/interfaces/web/static/css/chat.css:156-158 — ".trace-shell .trace-body .login-required-btn"` — OK
- `the_one/interfaces/web/static/css/chat.css:214 — ".messages .login-required-btn"` — OK (cycle-1 re-verified; this line is unchanged after L03/L04 edits)
- `the_one/interfaces/web/static/css/chat.css:160-163 — ".msg-attribution" / ".msg-attribution.from-you"` (reference pattern for block-level attribution) — OK
