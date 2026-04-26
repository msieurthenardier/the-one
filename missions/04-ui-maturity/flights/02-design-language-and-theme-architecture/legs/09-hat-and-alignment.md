# Leg: 09-hat-and-alignment

**Status**: landed
**Flight**: [Design Language & Theme Architecture](../flight.md)

## Objective

Interactive Human Acceptance Test for F2's design language. Flight Director guides the user through dark + light themes in all three areas (Chat / Studio / Admin), captures aesthetic feedback, fixes anything that feels off (color tweaks, spacing adjustments, alpha bumps, glow intensities, etc.) inline. User explicitly approves before flight closes.

## Context

- This is the FINAL leg of F2. After it lands, flight-level code review and commit happen.
- All 8 autonomous legs (01-08) landed: token system, NEXUS-style design language, Geist typography, Lucide icons, designed light theme, WCAG AA compliance, 12 visual snapshot baselines, design-system docs.
- HAT is the formal aesthetic feedback gate per F2 mission planning ("we'll definitely want the hat at the end").
- **Per agentic-workflow protocol**: the Flight Director guides verification step-by-step; no Developer/Reviewer agents spawned for execution. Issues caught during HAT get fixed inline (Flight Director may spawn focused Developer agents for code changes if needed), then re-verified before moving on.

## Inputs

- Branch `flight/02-design-language-and-theme-architecture`, legs 01-08 landed (uncommitted)
- Container deployable via `docker compose up -d --build`
- Test baseline: 387 unit + 20 browser tests passing
- HAT-candidate notes accumulated across legs 03/06/07/08 (in flight-log.md):
  - Glow blur radii (12px / 8px / 6px / 3px) — first-pass values, may want tuning
  - Active-state translucent fill alpha (8% dark / 10% light) — may need bump
  - Bg gradient end stop (70% in dark) — could be 100%
  - Cyan choice (Tailwind cyan-400 dark / cyan-700 light) — alternatives available
  - `.msg.user.api` purple bubble: cyan glow suppressed, possibly want purple-tinted glow
  - Section header `// ` prefix opacity (0.6) — may want full opacity
  - chip-add dashed border — could go solid for consistency
  - Drop-shadow blur radius `4px 12px` in light — may want stronger
  - Light-mode tool descriptions slate-blue tone (`--fg-muted: #64748b`) — designed but worth user confirmation

## HAT Steps

The Flight Director walks the user through these verification steps one at a time. Each step has a specific thing to verify; user reports back, FD records and fixes inline if needed.

### Setup

1. **Deploy fresh build**: `docker compose up -d --build` — confirm container comes up, app responds at http://localhost:8484
2. **Open in browser**: confirm app loads, dark theme is default

### Dark theme walk-through

3. **Nav rail**: 3 SVG icons (chat speech bubble, studio bot, admin gear). Active state cyan. Confirm icons are right size, color reads cyan, transitions smooth.
4. **Chat area, empty state**: confirm "Getting started" banner is visible, looks right on the design language. Setup banner readable.
5. **Send a chat message** (need agent first — quick setup: navigate to Admin → LLM Providers → Add Provider → pick `Mock (dev)` → save → Test Connection → Cancel back; navigate to Studio → click `+` → name "test" → select mock provider → select mock-default → save; back to Chat → send "hello"). Observe assistant message bubble, telemetry, send button.
6. **Studio editor**: confirm `// IDENTITY`, `// LLM CONFIGURATION`, `// SYSTEM PROMPT`, `// TOOLS` section headers in cyan Geist Mono. Form fields, focus rings.
7. **Admin → LLM Providers**: provider card with badge, hover glow, edit/delete buttons (cyan vs neutral disambiguation).
8. **Admin → System**: Rotate Encryption Key button, layout, hierarchy.

### Light theme walk-through

9. **Toggle to light**: in DevTools console, `App.theme.set('light')`. Confirm it applies live without reload.
10. **Same areas in light**: chat empty, chat with messages, studio editor, admin providers, admin system. Compare aesthetic quality to dark — does it feel like a coherent variant or a flip?
11. **Active sidebar items in light**: cyan border + light cyan fill + drop-shadow elevation. Confirm visible and reads as "active".
12. **Section headers `// ` in light**: cyan, recessive. Does the opacity feel right or too dim?

### Theme switcher behavior

13. **`App.theme.set('auto')` in console**: confirm returns to OS preference (likely dark in your setup).
14. **`App.theme.set('dark')` in console**: confirm immediate switch.
15. **Reload the page**: confirm theme preference persists.

### Aesthetic judgment calls

For each item below, user gives a thumbs-up or specific tweak request. Flight Director applies tweaks inline (token retune in tokens.css):

16. **Cyan shade**: cyan-400 in dark, cyan-700 in light. Right shade or want different?
17. **Glow intensities**: panel glow 12px, button glow 8px, status dot 6px, focus ring 3px offset. Right or want stronger/weaker?
18. **Active-state translucent alpha**: 8% dark, 10% light. Subtle or strong enough?
19. **Body gradient subtlety**: top deep navy fading to near-black at 70% in dark; cool fade in light. Right or want more contrast?
20. **Section header `// ` opacity**: 0.6. Right or want full?
21. **`.msg.user.api` purple bubble**: shadow suppressed (cyan-on-purple = muddy). Want purple-tinted shadow instead?
22. **chip-add dashed border**: kept dashed (suggests "add" affordance). Right or want solid for consistency?
23. **Light-mode tool descriptions**: slate-blue tone (`#64748b` `--fg-muted`). Right or want neutral gray?

### Final approval

24. **Overall**: does the design language feel "production-grade"? Anything that feels off but you can't quite name? Last freeform feedback.
25. **Approval**: explicit yes/no to closing the flight.

## Acceptance Criteria

- [ ] All 25 HAT steps walked through with user
- [ ] Any aesthetic adjustments requested are applied inline (token retunes; component CSS overrides only if absolutely needed) and re-verified before moving on
- [ ] User gives explicit approval to close the flight
- [ ] All 12 visual snapshot baselines re-generated after any token retune (otherwise leg 08 baselines mismatch the final state)
- [ ] All tests still pass: `pytest tests/` 387 + any net additions; `pytest -m browser tests/browser/` 20
- [ ] Flight log captures the user's HAT feedback + each adjustment made

## Verification

Manual / interactive only — no automated test for "user is happy with the design".

## Implementation Guidance

Flight Director script:

```
1. "Run `docker compose up -d --build` and open http://localhost:8484. Tell me when you're seeing the app."
2. (wait for user)
3. "Look at the nav rail on the left. You should see 3 SVG icons (chat speech bubble, studio bot, admin gear). Click the cyan/active one — color and transitions look right?"
4. (wait for response)
5. ... etc through the 25 steps
```

For each adjustment:
1. User describes the change ("glow is too intense", "cyan should be deeper")
2. Flight Director identifies the relevant token (e.g., `--accent-glow` in tokens.css)
3. Edit the token value, save
4. User reloads, confirms or asks for further tweak
5. When user OKs the tweak, move to next step

If the change requires more than a token retune (e.g., adding a new selector override, changing a CSS rule), Flight Director may spawn a focused Developer agent for the change. After change lands, return to HAT and re-verify.

If many tokens get retuned, regenerate visual snapshot baselines at the end:
```bash
pytest -m browser tests/browser/test_visual_snapshots.py --snapshot-update
```

## Edge Cases

- **User wants substantial design changes**: if changes go beyond aesthetic tuning (e.g., "let's redo the layout"), discuss with user whether to abort the leg and create a new mission/flight, or scope down. F2's mandate is the design language — layout changes are F3 territory.
- **Snapshot updates after tweaks**: if more than 1-2 tokens change during HAT, regenerate ALL snapshots at the end (not just affected ones — easier to ensure baseline consistency).
- **Test count after HAT**: should match pre-HAT (387 unit + 20 browser) unless tests were added/removed during inline fixes.

## State-Machine Reachability Audit

No state changes. Pure aesthetic adjustment + user verification.

✓ Pass.

## Cache Freshness Contract

No new caches.

✓ Pass.

## Files Affected

- `tokens.css` — possibly small token-value retunes during HAT (target: minimal)
- `tests/browser/__snapshots__/*.png` — possibly regenerated if tokens retuned
- `flight-log.md` — HAT feedback + adjustments captured

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] User explicitly approves the design (step 25)
- [ ] All inline adjustments applied + re-verified
- [ ] Snapshot baselines regenerated if tokens changed
- [ ] All tests pass
- [ ] Flight log captures HAT feedback in detail
- [ ] Set this leg's status to `landed`
- [ ] Signal `[HANDOFF:review-needed]` (note: triggers flight-level review + commit, NOT a per-leg review)
