# Leg: headings-contrast-motion

**Status**: completed
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

## Scope (design-review decision)
**A5 is scoped to `connector-editor.js` only** — the M11 connector-editor surface this flight covers. `section-title` `<div>`s also exist in `general-tab.js`, `provider-editor.js`, `mcp-server-editor.js`, `tools-editor.js`, `system-page.js`, and `history-buckets.js`; promoting those is **out of scope** (tracked as an A5-remainder follow-up — note in the flight log, not fixed here). Similarly, A7 fixes `studio.css` only; `components.css` has its own hardcoded transition literals — out-of-scope residual, note it.

## Acceptance Criteria
- [x] All **10** connector-editor section titles render as `<h2 class="section-title">` (incl. the "Danger Zone" title keeping `danger-zone-title`), under the editor's single `<h1>` — logical heading order, verified live (`<h1>`→10×`<h2>`, 0 `div.section-title`)
- [x] Visual unchanged — `.section-title` (components.css:333) sets font explicitly; no extra reset needed
- [x] `.discoverable-dropdown-item--focused` gets `outline: 2px solid var(--accent); outline-offset: -2px` — ≥3:1 vs surface, distinct from `:hover`
- [x] `studio.css`'s 13 `0.15s` literals → `var(--motion-fast)`; the two `0.2s` `.tool-switch` literals → new **`--motion-medium: 200ms`** (added to both theme blocks AND the `prefers-reduced-motion` zeroing block) — behavior-preserving
- [x] `pytest tests/test_design_tokens_a11y.py` and `tests/test_token_definitions.py` green — 48 passed (`--motion-medium` defined)
- [x] Browser assertion confirms the section titles are `<h2>` — `test_connector_editor_section_titles_are_h2`

## Verification Steps
- DOM check / browser test: connector section titles are `<h2>`; heading order is `<h1>`→`<h2>`s
- Manual: keyboard-navigate the discoverable-dropdown, confirm the focused option is unambiguously visible and distinct from hover
- Manual with `prefers-reduced-motion: reduce`: studio.css transitions (incl. `.tool-switch`) are suppressed
- `pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py -q` green

## Implementation Guidance

1. **A5 — headings** — change the **10** connector-editor `section-title` `<div>`s (incl. ~655 "Danger Zone", which also has `danger-zone-title` — keep both classes) to `<h2>`, keeping `class="section-title"`. The `.section-title` rule lives in `components.css:333` and sets font explicitly, so the visual is identical with no reset. Verify no selector targets `div.section-title` (confirmed none exist).
2. **A6 — focus indicator** — in `studio.css:1566-1569`, add `outline: 2px solid var(--accent)` (plus a small offset if needed) to `.discoverable-dropdown-item--focused` so it's ≥3:1 vs `var(--surface)` and clearly distinct from `:hover`. (`test_design_tokens_a11y.py` already asserts accent-on-surface ≥3:1 both themes, so `var(--accent)` is safe.)
3. **A7 — reduced-motion (token route)** — replace `studio.css`'s `0.15s` literals with `var(--motion-fast)`. For the two `0.2s` `.tool-switch` rules (~60-61): `--motion-fast`=150ms and `--motion-base`=250ms match neither, so **add a new `--motion-medium: 200ms`** to `tokens.css` (alongside the existing motion tokens, both theme blocks if applicable) AND add it to the `prefers-reduced-motion` zeroing block (~417-426); then use `var(--motion-medium)` for those two. This preserves the 200ms duration exactly while making it reduced-motion-aware.

## Edge Cases
- **Heading styling drift** — none expected (the `.section-title` class wins over UA `<h2>` defaults); verify visually anyway.
- **Token names** — only reference defined `--motion-*` tokens; the new `--motion-medium` must be defined in `tokens.css` (and zeroed in the reduced-motion block) before use, or `test_token_definitions.py` fails.
- **Out-of-scope residuals** — `components.css` hardcoded transition literals and the app-wide `section-title` divs are NOT fixed here; log them as A5/A7-remainder follow-ups.

## Files Affected
- `the_one/interfaces/web/static/js/areas/studio/connector-editor.js` - 10 section titles → `<h2>`
- `the_one/interfaces/web/static/css/studio.css` - dropdown focus outline; `0.15s`→`var(--motion-fast)`, `0.2s`→`var(--motion-medium)`
- `the_one/interfaces/web/static/css/tokens.css` - add `--motion-medium: 200ms` (+ reduced-motion zeroing)
- `tests/browser/test_flow_studio_connector_editor.py` - `<h2>` heading assertion

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] If final leg of flight:
  - [x] Update flight.md status to `landed`
  - [x] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
