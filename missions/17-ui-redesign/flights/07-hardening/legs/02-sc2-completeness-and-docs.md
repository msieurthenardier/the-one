# Leg: sc2-completeness-and-docs

**Status**: completed
**Flight**: [Hardening & Mission-End Acceptance](../flight.md)

## Objective

Close the SC2 contrast-completeness hole (make "covering ALL palette tokens with documented exceptions" machine-true) and bring the SC9 docs fully current with the v3 language + the mission's methodology assets.

## Scope (flight DDs authoritative)

- **SC2 CSS-driven completeness assertion** (architect P2 — NOT mirror-driven): the a11y audit (test_design_tokens_a11y.py) gates a curated fg-role set; completeness is prose-asserted, not coded. The mirror-sync guard (test_ui_guards.py:346) is strictly mirror→CSS, so a literal-hex fg token in tokens.css absent from the mirror slips both nets. **Add a completeness assertion that enumerates from `tokens.css` via `parse_tokens_css_theme_blocks()`** (tests/_ui_guard_helpers.py:528): for every literal-hex `--fg*/--accent*/--status*/--code-block*` token, assert it is either GATED in test_design_tokens_a11y.py OR in a documented exclusion allow-list. Document the non-text exclusions (border/hairline, nav-bg, hover-surface, focus-ring color, `--accent-translucent` raw, standalone `--surface-tool`) with the rationale (contrast is defined only for an fg-on-bg pair; structural tokens have no standalone ratio). Keep the `--fg-faint` 3.0-4.5 deliberate exception. Probe-test the assertion (plant a fake ungated `--fg-*` hex → it must fail naming the token; revert). (Optionally also make the mirror-sync guard bidirectional — a nice-to-have.)
- **SC9 docs currency** — confirm + top up (do NOT rewrite what's already v3):
  - `the_one/agents.md` "## Design system" (lines ~1243-1279, already v3): confirm the coverage sentence matches the final F3-F6 gates; add the `.field-group` + shared `.field-group-label` vocabulary; the **static+runtime label-guard pattern** (F6 methodology asset — static source-scan + runtime DOM guard for `outerHTML`/re-mount label associations); the `.section-title` element-scoped convention (F6, h2 heading vs div/label quiet-label).
  - Design-gallery sections (js/areas/admin/design-language/*-section.js): eyeball each renders the shipped v3 primitives (tokens/buttons/fields[.field-group]/surfaces/tabs/status/modal/markdown/typography[section-title convention]).
  - `CLAUDE.md`: confirm testing/design notes point at the v3 agents.md section + the browser lanes; ADD a testing note — **reviewers use canonical `make test-unit`, NEVER `-m live`** (the test_aiat.py live tests default THE_ONE_TEST_URL to localhost:8484, the operator's PROD app).
- No product-source changes beyond the new test + docs (agents.md/CLAUDE.md are docs; gallery is dev-only). Keep make test-unit + the guard suite green.

## Acceptance Criteria

- [x] SC2 completeness assertion added (CSS-driven, off parse_tokens_css_theme_blocks), probe-tested (fake ungated fg token fails naming it); the non-text exclusion allow-list documented with rationale; `--fg-faint` exception preserved; make test-unit green
- [x] agents.md design section confirmed v3-current + topped up (.field-group vocabulary, static+runtime guard pattern, section-title convention)
- [x] design-gallery sections eyeball-verified rendering v3 primitives (note any stale section)
- [x] CLAUDE.md: never-`-m live` reviewer note added; design/testing notes v3-current
- [x] ruff clean; guard suite green; no stale v2/alien language remains in the three doc surfaces (grep for glow/glass/bezel/chamfer/`// SECTION`/pixel-font in agents.md design section + CLAUDE.md — should be only retired-context mentions)

## Post-Completion Checklist

- [x] Criteria verified; flight-log entry; leg `landed`; checked off in flight.md
