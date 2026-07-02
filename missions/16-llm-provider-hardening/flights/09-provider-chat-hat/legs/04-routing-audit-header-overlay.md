# Leg: routing-audit-header-overlay

**Status**: completed
**Flight**: [HAT — Provider Chat Sweep](../flight.md)

> **Completed (2026-07-02).** Routing-audit trigger moved to the header row
> (right-justified) opening a centered overlay; inline panel removed. Verified live on
> the dev instance by the operator ("pass"); 7 browser tests green. Merged to `main`;
> ships in the next installer build.

## Objective
Move the routing-audit inspector's trigger to the top chat header row (right-justified,
beside the agent label + New-chat button) and open its content in a reasonably-sized
overlay instead of an inline `<details>` panel above the composer.

## Context
- HAT finding **F09-06** (operator request; not a defect).
- Current: `routing-audit-panel.js` `create()` builds a `<details>`; `chat.js:192-193`
  inserts it between `.messages` and `.input-area`. Rendered/wired on session join
  (`chat.js:1078-1079`), Refresh + entries live in `.routing-audit-body`.
- The chat header is `<div class="header"><h2 class="session-agent-badge">…</h2>
  <button class="new-chat-header">…</button></div>` (`chat.js:162`), a flexbox
  (`chat.css:60`, `display:flex; align-items:center; gap:8px`).
- A modal primitive exists: `.modal-overlay`/`.modal-dialog` (glass, centered, sized) in
  `components.css:1176-1216`. `App.confirmDialog` (`dialog.js`) is confirm-specific
  (title+message), so reuse the **CSS classes** for a custom-content overlay rather than
  that API.

## Inputs
- `the_one/interfaces/web/static/js/areas/chat/routing-audit-panel.js`
- `the_one/interfaces/web/static/js/areas/chat.js` (header build `:162`, panel mount
  `:192-193`, render/wire `:1078-1079`)
- `the_one/interfaces/web/static/css/chat.css` (`.header` `:60`; existing
  `.routing-audit-*` rules `:213-260`), `components.css` (`.modal-overlay/.modal-dialog`)
- `tests/browser/test_flow_chat_routing_audit_panel.py`

## Outputs
- A compact **"Routing audit"** trigger button in the header row, right-justified.
- The audit content (Refresh + entries/empty-state) shown in a centered, reasonably-sized
  overlay (reusing modal styling), dismissible via ✕ / ESC / overlay click.
- The inline `<details>` panel between `.messages` and `.input-area` is removed.

## Acceptance Criteria
- [ ] The routing-audit trigger sits in the top header row (same row as the agent label and
      New-chat button) and is **right-justified**; the agent label stays left.
- [ ] Clicking (or Enter/Space on) the trigger opens an overlay that is **centered and
      reasonably sized (not full width)**, containing the Refresh control and the routing
      entries (or the "No routing decisions yet" empty state).
- [ ] The overlay closes on ✕, ESC, and overlay-backdrop click; focus is managed
      accessibly (focus moves into the dialog on open and returns to the trigger on close);
      the trigger has an accessible name.
- [ ] Refresh still fetches the session and re-renders entries; render on session-join still
      works; per-session wiring intact (opening for a different session shows its entries).
- [ ] The old inline panel above the composer is gone.
- [ ] `make test-browser` passes (update `test_flow_chat_routing_audit_panel.py` to the new
      header-trigger + overlay structure — DOM assertions, no snapshots); `node --check` clean.

## Implementation Guidance
1. **routing-audit-panel.js** — split the current single `<details>` into:
   (a) a **trigger button** factory (or a small header control), and (b) a **modal** node
   containing the header (title + Refresh) and the `.routing-audit-body`. Keep `render`,
   `refresh`, `wireRefresh` operating on the body inside the modal (same `data-testid`s so
   tests/keying stay stable where possible). Add open/close helpers: open appends/show the
   overlay, traps focus, wires ESC + backdrop-click + ✕; close restores focus to the trigger.
   Reuse `.modal-overlay`/`.modal-dialog` classes (add a `routing-audit-modal` modifier for
   sizing if needed). Keep it a singleton (one overlay at a time).
2. **chat.js** — build/insert the trigger into the header row (after the New-chat button, or
   grouped with it on the right). Mount the overlay lazily (append to the area/body on open)
   or once, hidden. Replace the `:192-193` inline insert. Update `:1078-1079` so render +
   wireRefresh target the new structure. Right-justify: e.g. `margin-left:auto` on the first
   right-side control so the agent label stays left and the buttons group right.
3. **chat.css** — add header-trigger styling (match `.new-chat-header` affordance) and any
   `routing-audit-modal` sizing (max-width ~ 640–820px, max-height with internal scroll).
   Remove/retire the old inline-panel positioning rules that no longer apply (keep the
   row/badge/expansion styles used inside the overlay body).
4. **Tests** — update `test_flow_chat_routing_audit_panel.py`: trigger is in the header;
   clicking opens the overlay; entries/empty-state render inside it; ESC/✕ closes; Refresh
   works. DOM assertions only.

## Edge Cases
- **No session / welcome screen**: don't show a broken trigger before a session exists (the
  header only renders with a session — keep that gating).
- **Session switch while overlay open**: closing/reopening should reflect the current
  session's entries (wireRefresh is per-session; ensure the open handler reads current state).
- **Empty entries**: overlay still opens and shows the empty state.
- **Narrow viewport**: overlay stays within viewport (max-width + margins), body scrolls.

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat/routing-audit-panel.js`
- `the_one/interfaces/web/static/js/areas/chat.js`
- `the_one/interfaces/web/static/css/chat.css` (+ reuse `components.css` modal classes)
- `tests/browser/test_flow_chat_routing_audit_panel.py`

---

## Post-Completion Checklist
- [ ] Acceptance criteria verified (browser test)
- [ ] Update flight-log.md (F09-06 resolved)
- [ ] Set leg status `completed` (after verify on dev instance / build)
- [ ] Check off / add this leg in flight.md
- [ ] Commit (own build or batched)
