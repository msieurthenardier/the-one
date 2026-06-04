# Leg: headings-contrast-motion

**Status**: ready
**Flight**: [Mission-11 UI Accessibility Pass](../flight.md)

## Objective
Promote the connector-editor section titles to programmatic headings (A5), give the custom-dropdown focused option a visible 3:1 focus indicator (A6), and make `studio.css` transitions honor `prefers-reduced-motion` (A7).

## Context
- Maintenance report 2026-06-04, findings **A5** (WCAG 1.3.1, A), **A6** (WCAG 1.4.11 / 2.4.7, AA), **A7** (WCAG 2.3.3, AAA).
- **A5**: the editor title is `<h1>` (`connector-editor.js:323`) but all ten section titles (Connection, Credentials, Session, Discord, Pairing, Direct Messages, Servers, Routing, Attached agents — `:365,385,404,618,2128,2230,2336,2566,3080`) are `<div class="section-title">`. SR users get one `<h1>` and no heading-navigable structure on a long form.
- **A6**: `.discoverable-dropdown-item--focused` (the `aria-activedescendant` target) uses the same `background: var(--accent-translucent)` as `:hover` with no outline (`studio.css:1566-1569`); the keyboard cursor may fall below 3:1 UI-component contrast.
- **A7**: `tokens.css:417-426` reduces motion only by zeroing `--motion-fast`/`--motion-base`, but `studio.css`'s 15 transitions use hardcoded `0.15s`/`0.2s` literals (e.g. `:60-61,184,216,326,484,607,1426`), so `prefers-reduced-motion` doesn't affect them. Short color/border tweaks, minor impact, but the project's own contract is silently violated.

## Inputs
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` (9 section-title sites).
- `the_one/interfaces/web/static/css/studio.css` (`:1566-1569` focus; the 15 hardcoded transitions).
- `the_one/interfaces/web/static/css/tokens.css:417-426` (reduced-motion token block, for reference).

## Outputs
- Section titles as `<h2>`; dropdown focus indicator at ≥3:1; studio.css transitions token-driven.

## Acceptance Criteria
- [ ] All 10 editor section titles render as `<h2>` (styled to match the current look), giving heading-navigable structure under the editor's `<h1>`
- [ ] The `--focused` dropdown item has a distinct visible indicator (outline or stronger background) meeting ≥3:1 against the menu surface, distinguishable from `:hover`
- [ ] `studio.css` transitions reference `var(--motion-fast)`/`var(--motion-base)` (or a `prefers-reduced-motion` block zeroes them), so reduced-motion users get no transition
- [ ] `pytest tests/test_design_tokens_a11y.py` and `tests/test_token_definitions.py` stay green (no undefined `var(--x)` introduced)

## Verification Steps
- DOM check / browser test: section titles are `<h2>`; heading order is logical (single `<h1>` → `<h2>`s)
- Manual: keyboard-navigate the discoverable-dropdown, confirm the focused option is unambiguously visible and distinct from hover
- Manual with `prefers-reduced-motion: reduce`: studio.css transitions are suppressed
- `pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py -q` green

## Implementation Guidance

1. **A5 — headings** — change the 9 `section-title` `<div>`s to `<h2>` (keep the `section-title` class for styling; add heading reset CSS if needed so they look identical). Verify no CSS selector depended on `div.section-title` specifically.
2. **A6 — focus indicator** — in `studio.css:1566-1569`, add a distinct `outline` (e.g. `2px solid var(--accent)`) or a stronger background to `.discoverable-dropdown-item--focused` so it's ≥3:1 and clearly different from `:hover`.
3. **A7 — reduced-motion** — replace the hardcoded `0.15s`/`0.2s` transition durations across studio.css's 15 sites with `var(--motion-fast)`/`var(--motion-base)`, OR add a `@media (prefers-reduced-motion: reduce)` block in studio.css zeroing those transitions. Prefer the token route (single source of truth) — confirm the tokens exist in `tokens.css` so `test_token_definitions.py` stays green.

## Edge Cases
- **Heading styling drift** — `<h2>` carries default margins/font; reset via the `section-title` class so the visual is unchanged.
- **Token names** — only use `--motion-*` tokens that are actually defined in `tokens.css`; an undefined `var()` would fail `test_token_definitions.py`.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` - section titles → `<h2>`
- `the_one/interfaces/web/static/css/studio.css` - dropdown focus indicator; transition durations → tokens
- `tests/browser/` or DOM-shape test - heading assertion (if one fits)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)
