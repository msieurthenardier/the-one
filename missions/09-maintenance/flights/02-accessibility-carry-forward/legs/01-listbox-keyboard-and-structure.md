# Leg: 01-listbox-keyboard-and-structure

**Status**: landed
**Flight**: [Accessibility Carry-forward + F1 Tech-Debt Cleanup](../flight.md)

## Objective

Fix the chat welcome agent picker's keyboard semantics (currently has a roving-tabindex+arrow-key handler at `chat.js:184-198` that updates `tabindex` but NOT `aria-selected` — augment, don't rewrite). Restructure the session-list (drop `role="listbox"`/`role="option"` — interactive descendants are not allowed under `role="option"`). Verify the admin tools-grid is keyboard-accessible as-is (button-grid post-M08 F5; not a listbox).

## Context

The 2026-05-15 maintenance report's A.1 / A.4 findings clustered as "listbox options lack arrow-key navigation across 3 sites" + "listbox option contains a button." During F2 mission-design validation, the Architect spot-check determined tools-grid uses `role="list"` + `role="listitem"` (not a listbox — already a button-grid). Today's design-review pass on this leg surfaced additional precision required:

- **Welcome keydown handler already exists at `chat.js:184-198`** — not missing. What's actually missing is `aria-selected` toggling on arrow moves (current handler only flips `tabindex`). Augment in place.
- **Session-list `role="listbox"` is rendered in `chat.js:60`, NOT in `history-buckets.js`** — the container element with `<div class="session-list" role="listbox" aria-label="Chat sessions"></div>` is the shell rendered at chat-area init; history-buckets fills it. Both files need edits.
- **Session-item attribute is `data-id`** (set at `history-buckets.js:41` via `el.dataset.id = s.id`), NOT `data-session-id`. Three call sites read it (`chat.js:132`, `chat.js:707` indirectly, `tests/browser/test_flow_hash_routing.py:95`). Preserve the existing attribute name.
- **`highlightActiveSession` at `chat.js:129-136` uses `aria-selected`** — valid on `role="option"`, invalid on a plain `<button>` post-restructure. The semantic for "active item in a nav list" is `aria-current="page"` (matches `section-nav.js` pattern). Switch the toggle to `aria-current="page"`; update `history-buckets.js:40` and the dependent test assertions. **Rationale (cycle-2 review)**: `aria-current="page"` is defensible because the hash-router does change the URL (`#chat/sessions/<id>`) — each session view is page-like navigation. Alternative `aria-current="true"` is acceptable fallback but less specific.
- **THREE listbox-role assertions in `test_flow_keyboard.py`**: lines 50, 63, AND 67 (NOT just 50, 63 as the original spec said). Plus `test_session_delete_keyboard_reveal` at L90-100 assumes a specific shape that needs preserving.
- **Cross-file test impacts**: `tests/browser/test_flow_hash_routing.py:86, 95` query `.session-item[aria-selected="true"]` — switch to `aria-current="page"`. `tests/browser/test_flow_new_chat.py:77` asserts `role="listbox"` on `.chat-welcome-list` — SURVIVES (welcome stays a listbox); no edit. `tests/browser/test_flow_new_chat.py:196-201` uses `.session-item` then `.delete` — survives if class names preserved.
- **CSS `:focus-within` reveal at `components.css:123-124`** keys off `.list-item` — preserve that class on the new `<li>` so Tab-to-delete-button still reveals the delete affordance.

`areas/layout/section-nav.js:71-91` implements the canonical roving-tabindex pattern with arrow keys + `aria-current="page"`. One consumer needs roving-tabindex (welcome picker), no helper extraction needed.

## Inputs

- `the_one/interfaces/web/static/js/areas/layout/section-nav.js:71-91` — canonical roving-tabindex pattern (Architect verified line range is exact)
- `the_one/interfaces/web/static/js/areas/chat/welcome.js` — agent picker DOM build; `role="listbox"` + `role="option"`; `tabindex` shape correct; `aria-selected` initialized but never toggled
- `the_one/interfaces/web/static/js/areas/chat.js`:
  - **`:60`** — renders `<div class="session-list" role="listbox" aria-label="Chat sessions"></div>` (THE listbox container)
  - **`:129-136`** — `highlightActiveSession`: toggles `aria-selected` on `.session-item` (must switch to `aria-current="page"`)
  - **`:132`** — reads `items[i].dataset.id` (preserve `data-id` attribute)
  - **`:184-198`** — existing welcome-picker keydown handler (ArrowUp/Down/Home/End + roving-tabindex; ADD aria-selected toggling here)
  - **`:707`** — `.closest('.session-item')` lookup (CSS class preserved)
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js`:
  - **`:35-82`** — full session-item rendering block (NOT just 35-68; the keydown handler at L71-80 is in the same range)
  - **`:40`** — sets `aria-selected` (switch to `aria-current="page"` for active item)
  - **`:41`** — `el.dataset.id = s.id` (preserve `data-id`)
  - **`:71-80`** — `el.addEventListener('keydown', ...)` with `e.target !== el` bail (under restructure with session-button as the focusable element, this guard may be redundant — review during edit)
- `the_one/interfaces/web/static/js/areas/admin/tools-grid.js:62, :101` — `role="listitem"` + `role="list"` (verify-only — Architect confirmed; no edit)
- `the_one/interfaces/web/static/css/components.css:123-124` — `.list-item:hover .list-item-delete, .list-item:focus-within .list-item-delete { display: block; }` (preserve `.list-item` class on new `<li>`)
- `tests/browser/test_flow_keyboard.py`:
  - **`:50, 63, 67`** — THREE listbox-role assertions on session-list (Architect-corrected from original spec's "50, 63")
  - **`:90-100`** — `test_session_delete_keyboard_reveal` (post-restructure: preserve `.list-item` class so `:focus-within` reveal still works)
- `tests/browser/test_flow_hash_routing.py:86, 95` — queries `.session-item[aria-selected="true"]` and `.session-item[data-id="..."][aria-selected="true"]` (switch `aria-selected` → `aria-current="page"`)
- `tests/browser/test_flow_new_chat.py:77` — asserts `role="listbox"` on `.chat-welcome-list` (SURVIVES; no edit — welcome stays a listbox)
- `tests/browser/test_flow_new_chat.py:196-201` — uses `.session-item` + `.delete` selectors (SURVIVES if class names preserved)
- `tests/browser/__pycache__/conftest` patterns (read once for keyboard-test fixtures)
- `.gitignore` — verify pixel-snapshot directory is gitignored before relying on the convention

## Outputs

- `chat.js:184-198` augmented to also toggle `aria-selected="true"` on focus target + `"false"` on prior. Attribution comment naming `section-nav.js` added. **Pre-decided** (cycle-2 design review): the handler STAYS in `chat.js` for now — re-homing to `welcome.js` is a cohesion improvement but is M10-candidate refactoring, not in scope for this leg.
- `chat.js:60` container `<div class="session-list" role="listbox" ...>` → `<nav class="session-list" aria-label="Chat sessions">` (drop listbox semantic; nav landmark replaces it)
- `chat.js:129-136 highlightActiveSession` toggles `aria-current="page"` instead of `aria-selected`
- `history-buckets.js`: drop `role="option"`; restructure each item to `<li class="list-item"><button class="session-item" data-id="...">Title</button><button class="list-item-delete" aria-label="Delete session">×</button></li>` (preserve `data-id` attribute name; preserve `.list-item` class for CSS `:focus-within` reveal); switch the line-40 `aria-selected` → `aria-current="page"` for the active item; review the L71-80 keydown bail guard for post-restructure relevance
- `tests/browser/test_flow_keyboard.py`: 3 listbox-role assertions (L50, 63, 67) updated; `test_session_delete_keyboard_reveal` (L90-100) updated to match new shape
- `tests/browser/test_flow_hash_routing.py:86, 95`: queries updated to `aria-current="page"`
- `admin/tools-grid.js`: NO code change (verification only)
- Manual keyboard testing performed and documented in `flight-log.md`

## Acceptance Criteria

- [ ] Welcome agent picker: Tab into listbox → first option focused → ArrowDown → focus moves + `aria-selected="true"` shifts to new option + `"false"` on prior → Enter activates. Verify both via manual keyboard test AND (if time permits) a browser-test assertion modeled on `test_admin_category_keyboard_select` in `test_flow_keyboard.py`.
- [ ] Session list: `chat.js:60` container is `<nav>` (not `role="listbox"`); items are `<button class="session-item" data-id="...">` (NOT `role="option"`; `data-id` attribute preserved); delete `<button>` is a SIBLING `<button>` inside the same `<li class="list-item">`; `aria-current="page"` toggles on the active item (not `aria-selected`).
- [ ] Admin tools-grid: Tab into grid → tiles focusable via inner `<button>`; Enter activates; no keyboard trap. No `role` change. Verification documented in flight log (manual; no test added).
- [ ] WCAG 2.1.1 (Keyboard) satisfied across all three surfaces.
- [ ] WCAG 4.1.2 (Name, Role, Value) satisfied — no nested interactive elements inside `role="option"`.
- [ ] `tests/browser/test_flow_keyboard.py` updated: all 3 listbox-role assertions (L50, 63, 67) match the new shape; `test_session_delete_keyboard_reveal` (L90-100) passes with the preserved `.list-item` class enabling `:focus-within` reveal.
- [ ] `tests/browser/test_flow_hash_routing.py:86, 95` updated to query `aria-current="page"` (not `aria-selected="true"`).
- [ ] `tests/browser/test_flow_new_chat.py` unchanged (welcome listbox role survives; `.session-item` class preserved).
- [ ] Browser tests for chat / admin surfaces pass: `make test-browser` exit 0.
- [ ] Broad pytest unchanged at 1700 passed (host + container).
- [ ] Ruff baselines preserved (0/0).

## Verification Steps

- `cd /home/cprch/projects/the-one && grep -rn 'role="listbox"\|role="option"' the_one/interfaces/web/static/js/` — only the welcome listbox/options should match (the session-list container at chat.js:60 should no longer match). Tools-grid uses `role="list"`/`role="listitem"`; not affected.
- `cd /home/cprch/projects/the-one && grep -rn "aria-selected" the_one/interfaces/web/static/js/areas/chat/` — welcome.js options retain `aria-selected` (legitimate listbox semantic); session-related sites should not match (replaced by `aria-current`)
- `cd /home/cprch/projects/the-one && grep -n "data-session-id" the_one/interfaces/web/static/js/ tests/` — empty (we preserved `data-id`, did not rename)
- `cd /home/cprch/projects/the-one && grep -rn 'list-item-delete' the_one/interfaces/web/static/js/` — delete button is a sibling, not a child of an `option`
- `cd /home/cprch/projects/the-one && grep -n '\.list-item\b' the_one/interfaces/web/static/css/components.css the_one/interfaces/web/static/js/areas/chat/history-buckets.js` — `.list-item` class preserved on the `<li>` and CSS `:focus-within` rule still applies
- `cd /home/cprch/projects/the-one && grep -nE 'snapshot|pixel' .gitignore` — confirm pixel-snapshot directory is gitignored before relying on the regenerate-and-don't-commit convention
- Manual: Chat → Welcome canvas → keyboard test (Tab in, ArrowDown moves with aria-selected, Enter activates)
- Manual: Chat → focus session sidebar → keyboard test (Tab/Shift+Tab through items; Tab through session-button then sibling delete-button)
- Manual: Admin → Tools → keyboard test (Tab cycles through button-grid tiles; Enter activates; no trap)
- `cd /home/cprch/projects/the-one && make test-browser` — exits 0 (Chromium auto-restored via existing `_ensure-playwright`)
- `cd /home/cprch/projects/the-one && pytest --tb=no -q` (host) — 1700 passed
- `cd /home/cprch/projects/the-one && docker exec the-one pytest --tb=no -q --ignore=tests/browser` — 1700 passed
- `cd /home/cprch/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/` — both exit 0

## Implementation Guidance

Order: enumerate-tests-up-front → augment welcome handler → restructure session-list → verify tools-grid → manual + automated test.

1. **Enumerate cross-file test impacts UP FRONT** (Architect: do this BEFORE editing, not after)
   - `grep -rn 'role.*listbox\|getByRole.*listbox' tests/browser/` — full sweep
   - `grep -rn '\.session-item\|data-session-id\|data-id.*session\|aria-selected.*true.*session\|session.*aria-selected' tests/browser/` — find all assertions touching the session-item shape
   - Expected hits (per Architect F2 design review):
     - `test_flow_keyboard.py:50, 63, 67` — three listbox-role assertions on session-list (`role="listbox"` and `role="option"`)
     - `test_flow_keyboard.py:90-100` — `test_session_delete_keyboard_reveal` (`:focus-within` reveal)
     - `test_flow_hash_routing.py:86, 95` — `[aria-selected="true"]` selectors
     - `test_flow_new_chat.py:77` — asserts `role="listbox"` on `.chat-welcome-list` (SURVIVES — welcome stays a listbox; NO edit)
     - `test_flow_new_chat.py:196-201` — uses `.session-item` + `.delete` (SURVIVES — class names preserved)
   - Document any hits beyond this list in flight log Anomalies BEFORE proceeding.

2. **Read the reference pattern**
   - `the_one/interfaces/web/static/js/areas/layout/section-nav.js:71-91` — roving-tabindex + arrow-key + `aria-current="page"` (Architect verified the line range)

3. **Augment the welcome-picker keydown handler at `chat.js:184-198`**
   - Read the existing handler (it covers ArrowUp/Down/Home/End and flips `tabindex`)
   - Augment: also toggle `aria-selected="true"` on the new focus target and `aria-selected="false"` on the prior focus target. Use `event.target.setAttribute(...)` and `previouslyFocused.setAttribute(...)`.
   - Add an attribution comment: `// Pattern: roving-tabindex with arrow keys. See section-nav.js:71-91 for the canonical implementation.`
   - **Optional re-homing**: consider moving the handler from `chat.js:184-198` into `welcome.js` (which currently only builds the DOM). Cleaner cohesion. Either is fine — document the choice in flight log Decisions.
   - Verify: load Chat → welcome canvas → ArrowDown → DOM inspector shows `aria-selected` flipping AND `tabindex` flipping in lockstep.

4. **Restructure session-list — TWO files**
   - **(a) `chat.js:60`**: change the container from `<div class="session-list" role="listbox" aria-label="Chat sessions">` to `<nav class="session-list" aria-label="Chat sessions">` (drop `<div>` + `role="listbox"`; use `<nav>` landmark). The `.session-list` class is preserved for CSS.
   - **(b) `chat.js:129-136 highlightActiveSession`**: change `aria-selected` toggles to `aria-current="page"` on the active session button; remove `aria-current` from others. Method: use `el.setAttribute('aria-current', 'page')` and `el.removeAttribute('aria-current')` on inactive items.
   - **(c) `history-buckets.js:35-82`**: read the FULL range. Refactor each item to:
     ```html
     <li class="list-item">
       <button class="session-item" data-id="..." aria-current="page-if-active">Title</button>
       <button class="list-item-delete" aria-label="Delete session">×</button>
     </li>
     ```
     - `data-id` attribute name preserved (NOT renamed to `data-session-id`)
     - `.list-item` class on `<li>` preserved (CSS `:focus-within` reveal at `components.css:123-124`)
     - `aria-current="page"` set only on the active session (from `history-buckets.js:40` switch)
     - Drop `role="option"` from items
     - Review the keydown bail guard at L71-80 — under the new shape, the focusable element is the session-button directly. The bail (`if (e.target !== el) return`) may be redundant; remove or rewrite to match the new topology. Document the decision in flight log.
   - **(d) Insert the `<ul>` wrapper**: between the `<nav>` container and the `<li>` items. Either `history-buckets.js` builds it, OR `chat.js:60` already creates `<nav>...<ul>...</ul></nav>` — pick one location and keep the responsibility contract clean.

5. **Verify tools-grid is keyboard-accessible (no edit)**
   - Read `tools-grid.js` around lines 62 and 101 to confirm the button-grid structure (`role="list"` + `role="listitem"` + inner `<button>`)
   - Open Admin → Tools in browser; Tab through tiles, confirm each `<button>` is focusable, Enter activates, no keyboard trap
   - Document outcome in flight log (single-line verification note)

6. **Update affected tests**
   - **`tests/browser/test_flow_keyboard.py`**:
     - Lines 50, 63, 67: change `role="listbox"`/`role="option"` assertions to match the new shape. Either query `<nav class="session-list">` directly, or use `page.locator(".session-list")` and assert tag is `nav`.
     - Lines 90-100 (`test_session_delete_keyboard_reveal`): verify the test still works after restructure. The `.list-item:focus-within .list-item-delete` reveal CSS rule still applies because we preserved `.list-item`. Adjust selectors if the test's `.session-item` locator behavior changes.
   - **`tests/browser/test_flow_hash_routing.py:86, 95`**:
     - L86: `.session-item[aria-selected="true"]` → `.session-item[aria-current="page"]`
     - L95: `.session-item[data-id="${session_id}"][aria-selected="true"]` → `.session-item[data-id="${session_id}"][aria-current="page"]`
   - **`tests/browser/test_flow_new_chat.py:77`**: NO EDIT (welcome listbox survives)
   - **`tests/browser/test_flow_new_chat.py:196-201`**: NO EDIT (class names preserved); verify by running the file once
   - Run targeted: `make test-browser` (or `docker exec the-one pytest tests/browser/test_flow_keyboard.py tests/browser/test_flow_hash_routing.py tests/browser/test_flow_new_chat.py -q`)

7. **Run broad pytest + ruff to confirm no regression**
   - `pytest --tb=no -q` (host) → 1700 passed
   - `docker exec the-one pytest --tb=no -q --ignore=tests/browser` → 1700 passed
   - `ruff check the_one/ tests/ && ruff format --check the_one/ tests/` → exit 0

8. **Regenerate local pixel-snapshot baselines** if the session-list restructure affected pixel-snapshot test surfaces
   - First confirm pixel-snapshot directory is gitignored: `grep -nE 'snapshot|pixel' .gitignore`
   - Use the project's regen target (likely something under `make test-pixel --update` or similar — locate in Makefile)
   - Baselines are local-only; do not commit

9. **Manual keyboard test**
   - Document outcome in `flight-log.md` Session Notes: which surfaces were tested, what was observed (especially the new `aria-selected` ↔ `aria-current` distinction working as expected), any anomalies

10. **Commit**
    - `git add the_one/interfaces/web/static/js/areas/chat/welcome.js the_one/interfaces/web/static/js/areas/chat.js the_one/interfaces/web/static/js/areas/chat/history-buckets.js tests/browser/test_flow_keyboard.py tests/browser/test_flow_hash_routing.py`
    - Add CSS file too if any selector was adjusted
    - Do NOT add `tools-grid.js` (no edit; verification-only)
    - Heredoc commit message:
      ```
      git commit -m "$(cat <<'EOF'
      flight/02: welcome picker aria-selected + session-list nav restructure
      
      Mission: 09
      EOF
      )"
      ```
    - Do NOT push. Flight uses end-of-flight commit pattern.
    - Update leg status `in-flight` → `landed`
    - Update flight-log.md with Leg Progress entry
    - Signal `[HANDOFF:review-needed]`

## Edge Cases

- **Welcome picker re-render mid-keyboard-navigation**: if a fresh agent list arrives mid-keyboard-flow (rare; agent CRUD), the focus state may reset. Acceptable — the welcome picker isn't a continuously-streaming surface; document if surfaced.
- **Session list hash-route deep link** (`#session/<id>`): preserve via `data-id` (NOT renamed); verified by `test_flow_hash_routing.py` post-edit.
- **`history-buckets.js:71-80` keydown bail**: this guard handled "let descendants handle their own keys." Under restructure with the session-button as the focusable element, the descendant case is the delete button — which has its own click handler. The guard may be safe to remove OR may need rephrasing. Investigate during edit.
- **`<ul>` placement** (pre-decided per cycle-2 design review): **chat.js owns the shell `<nav class="session-list" aria-label="Chat sessions"><ul></ul></nav>`; history-buckets.js fills the inner `<ul>` with `<li>` items.** This mirrors the existing pattern where chat.js owns the area's outer DOM and history-buckets fills the dynamic content. Don't split the contract differently.
- **Pixel-snapshot baseline regeneration**: confirm gitignore covers the snapshot directory before regenerating. If somehow the project commits baselines (it shouldn't per user-global instructions), surface the gap and stop.
- **Existing `aria-selected` toggling in welcome picker** (if any): if `chat.js:184-198` already toggles `aria-selected` (unlikely per Architect's read but verify), the augment becomes a no-op. Either way confirm at edit time.

## Files Affected

- `the_one/interfaces/web/static/js/areas/chat/welcome.js` — keydown attribution comment (and possibly the keydown handler itself if re-homed from chat.js)
- `the_one/interfaces/web/static/js/areas/chat.js` — L60 container shape change; L129-136 `highlightActiveSession` aria-selected → aria-current; L184-198 augment for aria-selected toggling (or re-home)
- `the_one/interfaces/web/static/js/areas/chat/history-buckets.js` — L35-82 full restructure to nav + ul + button + sibling-delete; preserve `data-id` + `.list-item` class
- `tests/browser/test_flow_keyboard.py` — L50, 63, 67 (three listbox-role assertions); L90-100 (test_session_delete_keyboard_reveal)
- `tests/browser/test_flow_hash_routing.py` — L86, 95 (aria-selected → aria-current)
- Possibly `the_one/interfaces/web/static/css/` (chat-area stylesheet) — selector adjustments if any
- `flight-log.md` — Leg Progress entry + Session Notes (manual keyboard test + welcome-handler home decision + history-buckets keydown-bail decision)
- **NOT modified** (verified during recon): `the_one/interfaces/web/static/js/areas/admin/tools-grid.js`, `tests/browser/test_flow_new_chat.py`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Manual keyboard test documented in flight log
- [ ] Three target browser tests pass (`make test-browser`)
- [ ] Broad pytest 1700 passed (host + container)
- [ ] Ruff 0/0 baseline preserved
- [ ] Pixel-snapshot baselines regenerated locally if needed
- [ ] Update `flight-log.md` with Leg Progress entry
- [ ] Set this leg's status to `landed`
- [ ] Commit all changes together (do NOT push; flight uses end-of-flight commit)
