# Leg: 02-chat-a11y-baseline

**Status**: completed
**Flight**: [Pre-Mission-06 Quick Wins](../flight.md)

## Objective

Bring the chat surface and tool-form info-icon pattern to WCAG 2.1 AA keyboard + screen reader baseline by adding a live region to the chat message log, an accessible name to the chat input, and converting the field-info-icon `<span>` to a focusable `<button>` element with `aria-describedby`.

## Context

Maintenance report findings A.1, A.2, A.3 (see `maintenance/2026-05-04.md`).

- **A.1**: Chat message log at `the_one/interfaces/web/static/js/areas/chat.js:71` — the `<div class="messages">` container has NO `aria-live`, NO `role="log"`, NO `role="region"`. Agent replies appended via `messagesEl.appendChild(...)` are silent to assistive tech. WCAG 4.1.3 fail.
- **A.2**: Chat input at `chat.js:73` — `<input data-testid="chat-input" placeholder="Type a message..." autocomplete="off" />` has no label/aria-label/aria-labelledby. Placeholder is not an accessible name. WCAG 1.3.1, 4.1.2 fail.
- **A.3**: Info-icon tooltips at `tools-form-helpers.js:109` and `tools-editor.js:179` — `<span class="field-info-icon" title="..." aria-label="...">` is mouse-only (`title` is mouse hover-only); `aria-label` on a non-focusable, non-interactive `<span>` is largely ignored by screen readers. Field descriptions — the only place schema docstrings surface — are unreachable for keyboard or screen-reader users. WCAG 1.3.1, 2.1.1, 4.1.2 fail.

Cross-reference with M04 F4 debrief: HAT-shipped chat surfaces (render-pacing, etc.) explicitly noted as untested at the unit/a11y level. This leg absorbs that gap for the highest-impact items.

A flight-design decision was made to convert the `<span>` to a real `<button type="button">`. See flight.md Design Decisions for rationale.

## Inputs

- `the_one/interfaces/web/static/js/areas/chat.js` (existing; chat surface module)
- `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js` (existing; shared form module from F6)
- `the_one/interfaces/web/static/js/areas/admin/tools-editor.js` (existing; admin tools editor)
- `the_one/interfaces/web/static/css/components.css` and/or `admin.css` (existing; field-info-icon styling)

## Outputs

- Chat message log container has `role="log" aria-live="polite" aria-relevant="additions" aria-atomic="false"`
- Chat input has `aria-label="Message"` (visually hidden label optional, aria-label is sufficient)
- `field-info-icon` rendered as `<button type="button" class="field-info-icon" aria-describedby="<field-id>-desc">` plus a hidden `<span id="<field-id>-desc">` containing the description text
- CSS adjusted for the new `<button>` element to preserve existing visual chrome
- Browser tests updated where they previously asserted on `<span>` shape

## Acceptance Criteria

- [x] Chat message log container in `chat.js:71` has `role="log"` + `aria-live="polite"` + `aria-relevant="additions"` + `aria-atomic="false"` set explicitly in the HTML string
- [x] Chat input in `chat.js:73` has `aria-label="Message"` attribute
- [x] `tools-form-helpers.js:109` and `tools-editor.js:179` render the info-icon as `<button type="button" class="field-info-icon" aria-describedby="<field-id>-desc">...</button>` with a sibling `<span id="<field-id>-desc" class="visually-hidden">{description}</span>`
- [x] Each field with a description has its input wired to the description span via `aria-describedby` (in addition to the button's `aria-describedby`)
- [x] The `<button>` is focusable (default Tab order) and the description is announced when focused
- [x] CSS `.field-info-icon` styling continues to render visually identically to current (no visible chrome change)
- [x] Existing browser test `tests/browser/test_flow_studio_tools_overrides.py` (or the admin-side equivalent) passes; if it asserted on `<span>` shape, update assertion to `<button>` shape
- [x] No regression in chat browser tests (`tests/browser/test_flow_*chat*.py`)
- [x] Manual keyboard verification: Tab from a tool-config input lands on the info-icon button; pressing Enter/Space does not navigate (button has no click handler — the description is read on focus via `aria-describedby`)

## Verification Steps

- `cd ~/projects/the-one && grep -n 'role="log"\|aria-live="polite"' the_one/interfaces/web/static/js/areas/chat.js` — confirms ARIA attrs in the message log
- `cd ~/projects/the-one && grep -n 'aria-label="Message"' the_one/interfaces/web/static/js/areas/chat.js` — confirms input label
- `cd ~/projects/the-one && grep -n 'field-info-icon' the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js the_one/interfaces/web/static/js/areas/admin/tools-editor.js` — confirms `<button>` element
- `cd ~/projects/the-one && pytest tests/browser/ -q` — all browser tests green
- Manual keyboard test: open the app in a browser, Tab through the chat surface (input is reachable and labelled "Message"), Tab through the admin tools editor (info-icons are reachable as buttons; their descriptions are announced)
- Manual screen-reader test (optional but recommended): with VoiceOver / NVDA / Orca enabled, send a chat message and verify the agent's reply is announced via the live region

## Implementation Guidance

1. **Chat message log live region (A.1)**
   - In `chat.js:71`, change the message-log container HTML from `'<div class="messages"></div>'` to `'<div class="messages" role="log" aria-live="polite" aria-relevant="additions" aria-atomic="false"></div>'`.
   - **Important — historical message replay**: when `renderHistory()` bulk-loads on session-join (loop at `chat.js:182-205`), set `messagesEl.setAttribute('aria-busy', 'true')` BEFORE the loop, then `removeAttribute('aria-busy')` AFTER. This prevents screen-reader replay of the entire history. **NOTE**: the streaming-receive path (`chat.js:501-523`, `assistant_chunk` handler) does NOT need `aria-busy` — one streamed chunk = one polite announcement is the correct UX (and `aria-live="polite"` coalesces well-behaved bursts). Apply `aria-busy` only around the synchronous `renderHistory` loop.

2. **Chat input accessible name (A.2)**
   - In `chat.js:73`, add `aria-label="Message"` to the input element string.
   - Optional: also add a visually-hidden `<label for="chat-input-id">Message</label>` for older screen readers; not required for AA but cheap.

3. **Field-info-icon as focusable button (A.3)**
   - In `tools-form-helpers.js:109-110` (the field-level info-icon), change the rendered HTML from:
     ```js
     '<span class="field-info-icon" title="' + descAttr + '" aria-label="' + descAttr + '">' + iconHtml + '</span>'
     ```
     to (concept):
     ```js
     '<button type="button" class="field-info-icon" title="' + descAttr + '" aria-describedby="' + idAttr + '-desc">' + iconHtml + '</button>' +
     '<span id="' + idAttr + '-desc" class="visually-hidden">' + escapeHtml(descAttr) + '</span>'
     ```
   - **Use the existing `idAttr` from `tools-form-helpers.js:89`** (`tef-<safeName>[-<toolName>]`) and append `-desc` (e.g. `tef-host_allowlist-desc`). This guarantees uniqueness across agent-mode renders that include `toolName`.
   - **KEEP the `title` attribute on the `<button>`** — it preserves the existing mouse-hover tooltip UX AND keeps the existing browser test (`tests/browser/test_flow_admin_tools_editor.py:126-130`) passing without modification (it asserts `icon.get_attribute("title")` is non-empty for three fields). `aria-describedby` provides the SR-accessible path; `title` provides the mouse path.
   - The input element should ALSO have `aria-describedby="<idAttr>-desc"` so that focusing the input announces the description (in addition to focusing the button). Both wired to the same span is intentional redundancy — the button-focused path serves keyboard-discovery, the input-focused path serves "I'm filling this field, what does it mean."
   - **`tools-editor.js:179`** is the per-tool **Test-connection section title** (`.section-title-row`), NOT a field-level icon — it has no `idAttr` in scope. Apply the same `<button>` pattern but use a section-scoped id like `test-connection-${name}-desc` where `${name}` is the tool name available in the editor scope. If the implementer determines this site is too divergent for the same pattern, leave it as a `<span>` (acceptable — it's one icon per tool, not field-density).
   - **Bundle A.4 freebie**: While editing `tools-form-helpers.js:282` (locked NarrowSuperset chip), change from `<span class="chip" data-locked="true">` to `<span class="chip" data-locked="true" aria-label="<value> (locked by operator)">` for cheap SR cue. Optional.
   - **Bundle A.5 freebie**: chip-list input in `tools-form-helpers.js:289` — add `aria-label="Add entry"`. Optional.

4. **CSS adjustments**
   - Existing `.field-info-icon` rule (in `admin.css` around lines 307-333) uses `display: inline-flex; align-items: center; justify-content: center; color: var(--fg-secondary)` — those still work for `<button>`. Native button styling needs reset:
     ```css
     .field-info-icon { background: none; border: 0; padding: 0; font: inherit; line-height: 1; color: inherit; cursor: help; /* …existing styles… */ }
     ```
     The `font: inherit; line-height: 1; color: inherit;` neutralizes browser button defaults that would otherwise leak through.
   - Verify `:focus-visible` styling exists for `.field-info-icon`; if not, add a focus ring consistent with project conventions.
   - Add `.visually-hidden` utility class — confirmed NOT already present in `the_one/interfaces/web/static/css/`. Add to `admin.css` (or a shared utility file):
     ```css
     .visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
     ```

5. **Browser test updates**
   - `tests/browser/test_flow_admin_tools_editor.py:126-130` asserts `icon.get_attribute("title")` is non-empty for three fields. **Because the implementation keeps `title=` on the `<button>` (per step 3), this test continues to pass without modification.** Verify via `pytest tests/browser/test_flow_admin_tools_editor.py -v -k tooltip`.
   - If any other existing browser test asserts on `field-info-icon` being a `<span>` element, update the selector to `button.field-info-icon` (or use `[class="field-info-icon"]` to be element-agnostic). Run `grep -rn "field-info-icon" tests/` to identify.
   - Add at least one regression test: `expect(page.locator("[role='log']")).to_be_visible()` in a chat browser test, confirming the live region exists.

## Edge Cases

- **Existing rendered messages on session-join**: must NOT trigger live-region replay. Use `aria-busy="true"` during bulk insert (see step 1).
- **Field descriptions containing HTML entities**: ensure they go through `escapeHtml()` before insertion into the description span (the existing code likely uses an `aria-label` raw string that's been escaped via `descAttr`; verify the parallel path for the new span).
- **Tab order**: the `<button>` will introduce additional Tab stops. If the form has many fields, this could increase Tab depth significantly. Verify keyboard navigation feels acceptable; if not, consider `tabindex="-1"` and rely on input's `aria-describedby` alone (but this loses the keyboard-discoverability win).
- **Screen-reader replay of historical messages**: the `aria-busy` toggle must not race the screen reader's announcement queue. Setting it via `setAttribute` before `appendChild` calls and removing AFTER the final `appendChild` is the correct ordering.

## Files Affected

- `the_one/interfaces/web/static/js/areas/chat.js` — message-log live region; input aria-label; aria-busy on bulk insert
- `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js` — field-info-icon as button; description span; (optional) chip aria-labels
- `the_one/interfaces/web/static/js/areas/admin/tools-editor.js` — same field-info-icon pattern (parallel site)
- `the_one/interfaces/web/static/css/admin.css` (or `components.css`) — `.field-info-icon` button reset; `.visually-hidden` utility
- 1+ browser test files for selector/assertion updates and live-region regression coverage

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (browser + unit)
- [ ] Manual keyboard verification performed
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: update flight.md status to `landed` and check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)
