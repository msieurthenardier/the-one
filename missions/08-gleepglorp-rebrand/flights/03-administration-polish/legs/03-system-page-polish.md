# Leg: 03-system-page-polish

**Status**: ready
**Flight**: [Administration Polish](../flight.md)

## Objective

Polish the System page (Appearance / Encryption / Base Prompt) to the Flight 2 design language. Apply glass / bezel / V3b / motion vocabulary to the theme toggle, warning callout, base-prompt code block, and flash feedback affordances. **Interactive vibe leg** — operator drives aesthetic judgment; Flight Director presents options, applies changes, re-renders, iterates.

## Context

- **System page is the simplest of the 3 polish pages**: 3 sections in a single column, no editor sub-modules, ~110 lines of JS + ~30 lines of dedicated CSS. Good warm-up for the polish cadence before Providers (complex editor) and Tools (tabbed grid).
- **Substrate**: Leg 01 just landed; `--panel-radius-sm` now 4px (down from 6px), `--btn-v3-gradient` token available, `--panel-shadow-glow` ripped. The theme-toggle container's `border-radius` is one of the consumers that just tightened from 6px → 4px — verify visually.
- **One Mission Known Issue touched here**: theme-toggle's current `box-shadow: 0 0 8px var(--accent-glow)` on the active option is a glow remnant that should be ripped when adding accent-translucent (per flight design + Architect feedback: avoid muddy double-glow).
- **WCAG guard**: Warning callout's `var(--status-warning-bg-soft-2)` background is an audited contrast pair with `var(--status-warning)` text. Keep the background; only add bezel-inset. If the operator wants to replace the background with a glass tint, re-run the audit mid-leg before continuing.

## Inputs

What exists before this leg runs:

- `the_one/interfaces/web/static/js/areas/admin/system-page.js` (111 lines) — renders 3 sections + wires theme toggle (delegates to `App.theme.renderToggle`) + wires encryption rotate flow.
- `the_one/interfaces/web/static/css/admin.css:20-48` — System panel CSS:
  - `.admin-system-section` (`:21-22`): 16px vertical padding + 1px top border between sections (first section: no border, no top padding).
  - `.admin-system-text` (`:23`): body-sm color: fg-secondary.
  - `.admin-system-warning` (`:24`): `--status-warning-bg-soft-2` bg + `--status-warning-border` border + 6px radius + 10px 14px padding + body-sm + `--status-warning` color. **WCAG-audited pair.**
  - `.admin-system-flash` (`:25-27`): 12px margin-top + body-sm + min-height 20px; `.success` adds `--status-success` color + semibold; `.error` adds `--status-danger` color.
  - `.admin-base-prompt` (`:28-43`): `var(--surface)` bg + 1px border + `--panel-radius-sm` radius (now 4px) + 12px 14px padding + mono + body-sm + 1.5 line-height + 24rem max-height + overflow-y auto.
  - `.admin-theme-toggle` (`:44`): segmented-control container — 1px border + `--panel-radius-sm` radius (now 4px) + 2px padding + `var(--surface)` bg.
  - `.admin-theme-option` (`:45`): transparent bg + no border + 6px 16px padding + `fg-secondary` color + body-sm + 4px radius + 200ms transitions.
  - `.admin-theme-option:hover` (`:46`): `fg` color.
  - `.admin-theme-option.active` (`:47`): `var(--accent)` bg + `fg-on-accent` color + semibold + **`box-shadow: 0 0 8px var(--accent-glow)`** (the glow remnant to rip).
  - `.admin-theme-option:focus-visible` (`:48`): 2px accent outline + accent-glow `box-shadow: 0 0 0 3px`.
- The theme-toggle's actual `<button>` rendering lives in `App.theme.renderToggle` (in `static/js/theme.js` — out of polish scope; we only touch CSS unless the operator decides JS-side markup needs touching).
- `--bezel-shadow-mini` defined in `tokens.css` (2-layer directional inset shadow).
- `--bezel-shadow-inset` defined in `tokens.css` (recessed-input treatment used by `.field-input` family).
- `--accent-translucent` defined in `tokens.css` per theme (rgba accent at low alpha).

## Outputs

What exists after this leg completes:

- Theme toggle reads as a bezel-mini segmented control with on-brand active state (no double-glow); operator confirms aesthetic.
- Warning callout carries `--bezel-shadow-inset` for recessed feel; WCAG-audited contrast preserved.
- Base-prompt code block carries `--bezel-shadow-inset` for "recessed code well" feel matching `.field-input` family.
- Flash feedback affordances verified on-brand (decision: stay text-only or elevate with LED dot — operator picks).
- Section dividers + spacing rhythm verified visually.
- Leg artifact + flight-log entry capture iteration trail.

## Acceptance Criteria

This is a vibe leg. Acceptance is operator-confirmed rather than mechanically-verified. The criteria are:

- [ ] **Theme toggle** — operator confirms the segmented control reads on-brand (bezel-mini container; active option treated per operator's chosen direction; focus + hover states verified)
- [ ] **Warning callout** — operator confirms it reads on-brand without WCAG regression (background unchanged from audited pair; bezel-inset applied; if operator overrides and changes background, mid-leg WCAG audit re-run captures the result)
- [ ] **Base-prompt code block** — operator confirms it reads as a recessed code well consistent with `.field-input` family
- [ ] **Flash feedback** — operator confirms current treatment is on-brand or specifies what to add (LED dot, glass surface, etc.)
- [ ] **Section spacing + dividers** — operator confirms the rhythm reads correctly (or specifies retune)
- [ ] All scaffolding / iteration variants removed (no `--temp-iter-*`, `.iter-*`, or `-v{N}` leftover classes in CSS or JS)
- [ ] WCAG audit green at leg close: `docker exec the-one pytest tests/test_design_tokens_a11y.py -v` returns 45/45
- [ ] Narrow test gate green at leg close: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 30` returns 56/56
- [ ] Leg artifact + flight-log entry capture final values + iteration narrative

## Verification Steps

How to confirm each criterion is met:

1. **Load `#admin/system` in both light + dark themes**, walk through each section, confirm operator's on-brand assessment.
2. **Run WCAG audit + narrow gate** at leg close (after final iteration).
3. **Iteration-cleanup grep**: `grep -rEn '(--temp-iter|\.iter-|-v[0-9]+ ' the_one/interfaces/web/static/css/admin.css` returns nothing.

## Implementation Guidance

Vibe legs are operator-driven; this section is a **suggested iteration order**, not a script. The Flight Director presents options for each surface and applies the operator's pick; the operator may reorder, skip, or expand the list.

**Suggested order** (simple-to-complex, dependency-light to dependency-heavy):

1. **Theme toggle** (most visually prominent + has a working assumption from flight design).
2. **Base-prompt code block** (mechanical — apply `--bezel-shadow-inset` and confirm).
3. **Warning callout** (mechanical with WCAG guard).
4. **Flash feedback** (decide: text-only or elevate).
5. **Section spacing + dividers** (cross-cutting cleanup — verify everything reads coherently in context).

Per Flight 2 vibe-leg cadence:
- Present 2-4 concrete options per micro-iteration (e.g., "active option as full accent fill vs accent-translucent vs glass surface").
- Apply the operator's pick, re-render via `make rebuild` or by-touching-files-then-page-reload (depending on what's faster for the change), iterate.
- After N iterations on the same micro-axis (~5-6 max per Flight 2 debrief), check in: "is this still serving the leg objective, or are we exploring?"
- Capture iteration trail in flight log after leg close (not mid-stream — preserves vibe flow).

## Edge Cases

- **`--panel-radius-sm` retune**: Leg 01 just changed this from 6px → 4px. The theme-toggle container + base-prompt block both use `--panel-radius-sm`. Verify the 2px tightening reads on-brand; if it feels too tight, the retune can be reverted (or a separate `--admin-radius` slot introduced).
- **`App.theme.renderToggle` markup**: lives in `static/js/theme.js`; we shouldn't need to touch it unless operator wants to change the button markup structure. Polish via CSS only is the default.
- **iOS toggle dependency**: System page doesn't use the iOS toggle (only Tools and Studio MCPs do). Out of scope for this leg.
- **Encryption flash positioning**: the `.admin-system-flash` element is inside the Encryption section's `.admin-system-section`. If polish moves it elsewhere (e.g., page-level toast), that's a structural change — pause and surface.
- **Theme toggle re-render on theme change**: the toggle component re-renders when the active theme changes (clicking a non-active option flips the data-theme attribute, which cascades through CSS). If a CSS change introduces a transition that animates the active-option change, verify it doesn't conflict with the theme-swap cascade.

## Files Affected

- `the_one/interfaces/web/static/css/admin.css` — primarily `:20-48` (System panel rules). Specifically: `.admin-theme-toggle`, `.admin-theme-option`/`.active`/`:focus-visible`, `.admin-system-warning`, `.admin-base-prompt`, possibly `.admin-system-flash` variants. Section divider rule (`.admin-system-section`) may stay or retune.
- Possibly `the_one/interfaces/web/static/js/areas/admin/system-page.js` if the operator wants markup-level changes (e.g., adding a LED dot to flash feedback). Default: CSS-only.
- `missions/08-gleepglorp-rebrand/flights/03-administration-polish/flight-log.md` — append leg-progress entry post-iteration.
- `missions/08-gleepglorp-rebrand/flights/03-administration-polish/legs/02-system-page-polish.md` — status `ready` → `in-flight` → `landed`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All vibe acceptance criteria operator-confirmed
- [ ] WCAG audit green (`45/45`)
- [ ] Narrow gate green (`56/56`)
- [ ] No iteration leftovers (grep clean)
- [ ] Flight log updated with leg progress entry (iteration trail captured)
- [ ] Set this leg's status to `landed` (NOT `completed`; `completed` is set by commit step)
- [ ] Do NOT check off this leg in flight.md (deferred to commit step)
- [ ] Commit (per user's per-leg-commit cadence — different from Flight 2's batch-at-close)
- [ ] Signal `[COMPLETE:leg]`

## Citation Audit

7 citations verified against current code at leg design time (commit `75864da` on `flight/03-administration-polish`):

- `system-page.js:111` lines — verified: 3-section structure (Appearance / Encryption / Base Prompt) with `mountThemeToggle` delegating to `App.theme.renderToggle`.
- `admin.css:20-48` — verified: all System-section CSS rules present at the cited lines; `.admin-theme-option.active` at `:47` carries the `box-shadow: 0 0 8px var(--accent-glow)` glow remnant.
- `admin.css:28-43` `.admin-base-prompt` — verified: `<pre>` block treatment with `var(--surface)` bg + 1px border + `--panel-radius-sm` (now 4px post-Leg-01) + mono + body-sm + 24rem max-height.
- `--bezel-shadow-mini` + `--bezel-shadow-inset` in `tokens.css` — verified: both tokens present per theme block.
- `--accent-translucent` in `tokens.css` — verified: per-theme rgba accent.

All citations clean. No mirror updates needed (no contrast-pair changes planned at design time).
