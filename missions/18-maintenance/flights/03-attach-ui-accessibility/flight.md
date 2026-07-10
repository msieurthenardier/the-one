# Flight: Attach-UI accessibility

**Status**: ready
**Mission**: [Post-Mission-16 Maintenance](../../mission.md)

## Contributing to Criteria
- [ ] Attach-UI a11y gaps closed: live-region (A1), distinguishing names (A2), remove-glyph contrast (A3)

---

## Pre-Flight

### Objective
Close the WCAG 2.1 AA gaps the Accessibility Reviewer found on the new Mission-16
chat image-attach UI — one coherent pass over `chat.js` + `components.css`.

### Open Questions
N/A.

### Design Decisions
N/A (maintenance) — the attach UI is otherwise solid (real buttons, aria-labels,
focus-visible, alt text); these are targeted additions.

### Prerequisites
- [x] Mission-16 F12 attach UI landed (`chat.js` staging + chicklets)

### Pre-Flight Checklist
- [x] Open questions — N/A
- [x] Design decisions — N/A
- [x] Prerequisites verified
- [x] Validation approach defined (browser/DOM assertions; NOT pixel snapshots)
- [ ] Legs defined (during `/agentic-workflow`)

---

## In-Flight

### Technical Approach

**Leg 1 — Attach-UI accessibility pass (A1 + A2 + A3, one coherent leg).**

- **A1 — live-region on the staging region (4.1.3 AA).** `attachmentsEl`
  (`chat.js:262`, `data-testid="chat-attachments"`) is rebuilt via `innerHTML` on
  every mutation with no `role="status"`/`aria-live`, so SR users get no feedback
  on stage / silent non-image drop / remove. Add `role="status"` or
  `aria-live="polite"` to the container (or emit a one-line polite announcement on
  each mutation) — mirror the project's own `pending-queued-chip`
  (`chat.js:61`, already `aria-live="polite"`). Coordinate with the Flight 2 size/
  count cap so a rejected oversized file is also announced.
- **A2 — distinguishing accessible names (4.1.2 Level A).** Every thumbnail gets
  identical `alt="Staged image attachment"` (`chat.js:167`) and every remove button
  identical `aria-label="Remove attached image"` (`chat.js:180`); with multi-image
  staging a user can't tell which remove button removes which image. Interpolate an
  index (or filename if available): e.g. `alt="Staged image N"`,
  `aria-label="Remove attached image N"`. This is the Level-A failure — highest a11y
  priority in the leg.
- **A3 — remove-glyph contrast (1.4.3 AA).** `.chip-remove` resting color
  `--status-danger-muted` over `--accent-translucent` ≈ 4.14:1 in light theme
  (< 4.5:1; hover + dark pass). Use `--status-danger` for the resting color
  (`components.css:587`), re-verify ≥ 4.5:1 in light.

Tests: extend `tests/browser/test_flow_chat_image_attach.py` (or a sibling) with
functional/DOM assertions — the staging region has a live-region role; staged
images/remove buttons carry index-distinguished names. **Functional/DOM assertions
only — NOT pixel snapshots** (snapshot baselines are gitignored, not committed).
A3's contrast is a token change; assert the resolved color/token, not a screenshot.

*(Deferred — advisory, not this leg: A4 `.chip-remove` transition bypassing
reduced-motion — AAA, pre-existing shared component. Carry as an advisory.)*

### Checkpoints
- [ ] Staging region announces stage/remove to SR (live-region present)
- [ ] Each staged image + remove button has a distinguishing accessible name
- [ ] Remove glyph ≥ 4.5:1 in light theme

### Adaptation Criteria
**Divert if**: adding the live-region introduces double-announcement with an
existing chat-status region — reconcile to one polite region.
**Acceptable variations**: index vs filename in the accessible name.

### Legs
> Planned one at a time during `/agentic-workflow`.
- [ ] `attach-ui-a11y-pass` — live-region + distinguishing names + remove-glyph contrast (A1/A2/A3)

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (browser DOM assertions)
- [ ] `docs/ui-testid-registry.md` updated if any testid added

### Verification
DOM assertions confirm the live-region + distinguishing names; the remove glyph
meets contrast in light theme; suite green.
