# Leg: tokens-v3-both-themes

**Status**: completed
**Flight**: [Design Language v3 — Tokens and Type](../flight.md)

## Objective

Land the v3 token tables in `tokens.css` (both themes, designed separately), neutralize the retired effect categories in place, rewrite the `design_tokens.py` mirror with full-palette AA parametrization in `test_design_tokens_a11y.py`, and ship the probe-tested mirror↔CSS value-sync guard — all in one change validated by the contrast suite.

## Context

- Flight DDs: "Palette v3", "Retire-with-consumers (Leg 1 = neutralize)", "Spacing/radius/shadow system", "A11y machinery", "fg-faint exception re-evaluated", "mirror-sync guard lands in Leg 1".
- Current `tokens.css`: 469 lines, 81 token names × 2 theme blocks (`[data-theme="dark"]` ~34-239, `[data-theme="light"]` ~241-408), `:root` holds `color-scheme` + `--btn-v3-gradient`; `@media (prefers-reduced-motion)` collapses motion tokens (KEEP); `@media (prefers-reduced-transparency)` degrades retiring categories (leave for Leg 2a to delete — it still references tokens this leg keeps defined).
- Mirror: `tests/browser/design_tokens.py` (DARK/LIGHT dicts, snake_case keys, subset of tokens). Known stale: `fg_tertiary` dark `#666666` vs CSS `#999999`; exception test hardcodes fg-faint dark `#444444` vs CSS `#808080` (which PASSES AA ≈5:1 — the "deliberate exception" is phantom).
- Contrast suite: `tests/test_design_tokens_a11y.py` — 3 parametrized tests (body ≥4.5, large/UI ≥3.0, text-on-color per-pair) + 2 fg-faint exception band tests. `tests/test_token_definitions.py` asserts every `var()` in component CSS is defined (this is why retired names stay DEFINED with neutral values this leg).

## Inputs

- `the_one/interfaces/web/static/css/tokens.css`, `fonts.css` (read-only this leg — type unchanged)
- `tests/browser/design_tokens.py`, `tests/test_design_tokens_a11y.py`, `tests/test_ui_guards.py` (guard file to extend), `tests/_ui_guard_helpers.py`

## Outputs

### tokens.css v3 (both theme blocks rewritten)

**Retuned core tokens** (names unchanged; values below are the design targets — the contrast suite is the arbiter; adjust within role if a pair fails, and record final values in the flight log):

| Token | Dark v3 | Light v3 |
|---|---|---|
| `--bg` | `#101114` | `#ffffff` |
| `--surface` | `#17181c` | `#fafafa` |
| `--surface-elevated` | `#1c1d22` | `#f4f4f5` |
| `--surface-tool` | `#1c1d22` | `#f4f4f5` |
| `--surface-translucent` | `rgba(255,255,255,0.03)` | `rgba(24,24,27,0.03)` |
| `--border` | `#26272c` | `#e4e4e7` |
| `--border-hover` | `#33343b` | `#d4d4d8` |
| `--border-strong` | `#4a4b55` | `#a1a1aa` |
| `--fg` | `#ededf0` | `#18181b` |
| `--fg-secondary` | `#a1a3ad` | `#52525b` |
| `--fg-tertiary` | `#8f919c` | `#5f5f68` |
| `--fg-muted` | `#85878f` | `#6e6e77` |
| `--fg-faint` | `#6b6d78` | `#898993` |
| `--fg-on-accent` | `#101114` | `#ffffff` |
| `--fg-on-danger` | `#101114` | `#ffffff` |
| `--fg-tool-msg` | `#8f919c` | `#5f5f68` |
| `--accent` | `#a78bfa` | `#6d28d9` |
| `--accent-api` | `#22d3ee` (badge-tier) | `#0e7490` (badge-tier) |
| `--accent-translucent` | `rgba(167,139,250,0.10)` | `rgba(109,40,217,0.08)` |
| `--accent-translucent-hover` | `rgba(167,139,250,0.16)` | `rgba(109,40,217,0.13)` |
| `--status-success` | `#4ade80` | `#15803d` |
| `--status-warning` | `#fbbf24` | `#a16207` |
| `--status-danger` | `#f87171` | `#dc2626` |
| `--status-danger-muted` | `#d98c8c` | `#b45252` |
| `--code-block-bg` | `#0c0d10` | `#f4f4f5` |
| `--code-block-fg` | `#ededf0` | `#18181b` |

- `-bg-soft`/`-border` status soft tokens: retune to quiet washes consistent with the ladders (leg implementer derives; suite + visual check arbitrate).
- Badge tokens (`--badge-*`): unchanged.
- Nav/panel/sidebar tokens: retune to the neutral ladders (e.g. `--sidebar-bg` gets an explicit color, not `transparent` — M04 flagged intent-hiding); `--panel-radius: var(--radius-sm)`, `--panel-radius-sm: 4px` kept as compat aliases.
- Motion + density tokens: unchanged.
- **fg-faint decision (design-review ratios, locked)**: faint stays an HONEST deliberate exception at **≥3.0 on bg, surface, AND surface-elevated** in both themes — a faint tier pinned at 4.5 stops being faint and collides with muted (the AA-passing hex would sit above the muted target, inverting the ladder). Dark `#6b6d78` passes (3.67/3.45/3.27); light is `#898993` (≈3.15 worst-case). The phantom sub-AA tests are DELETED and replaced with band tests asserting `3.0 ≤ ratio < 4.5` on all three surfaces per theme, each carrying `# DELIBERATE EXCEPTION` comments restating the consumer rule (de-emphasized annotations only — `.msg-attribution`, telemetry labels — never body prose or interactive affordances).
- **fg-muted retuned above the review's failing values**: dark `#85878f` (5.27/4.95/4.69 on bg/surface/surface-elevated), light `#6e6e77` (5.05/4.84/4.59) — the current suite already asserts muted-on-surface AA, and `.pending-queued-chip` (chat.css:580) makes muted-on-surface-elevated a real pair; both gates now clear.
- **`--fg-on-accent-muted` retired, not retuned**: zero consumers anywhere (definitions only). Neutralize this leg (`= var(--fg-on-accent)`), delete in Leg 2a. Its cross-theme "verify both accents" edge case is dropped (cross-theme pairs never co-occur on a rendered page).

**New tokens (both blocks or `:root` as appropriate — spacing/radius/shadows are theme-agnostic → `:root`)**: `--space-1: 4px` … `--space-8: 64px` (4/8/12/16/24/32/48/64); `--radius-sm: 6px`, `--radius-md: 8px`, `--radius-lg: 12px`; `--shadow-popover: 0 4px 12px rgb(0 0 0 / 0.10)`, `--shadow-modal: 0 8px 30px rgb(0 0 0 / 0.18)` (dark theme may deepen alphas slightly — elevation in dark = lighter surface, not bigger shadow).

**Neutralized retired categories — one value per token, validity-checked against each token's consumer property** (design-review corrected; the reduced-transparency block at tokens.css:449-450 demonstrates the right shapes):
- `--accent-glow`, `--accent-glow-strong`, `--status-success-glow`, `--status-warning-glow`, `--status-danger-glow` → `transparent` (color positions)
- `--shell-frame-glow` → `transparent` (it is a **gradient color stop**, base.css:110-111 — `none` would invalidate the background)
- `--shell-topbar-sheen` → `none` (it is a **background layer** in a multi-layer shorthand, base.css:32 — a color in a non-final layer invalidates the declaration)
- `--glass-bg` → `var(--surface)`; `--glass-blur` → `0px`; `--glass-saturate` → `100%`; `--glass-border` → `var(--border)`; `--glass-gleam` → `none` (feeds `background-image:`); `--glass-highlight` → `transparent` (zero consumers)
- `--bezel-shadow`, `--bezel-shadow-mini`, `--bezel-shadow-inset` → `0 0 0 0 transparent` (valid `<shadow>` that composes in shadow LISTS — `none` is not a valid list member and would invalidate composites like `box-shadow: var(--bezel-shadow-mini), 0 0 0 3px var(--accent-glow)` at components.css:74 etc.)
- `--shell-chrome-bg` → `var(--surface)`; `--shell-bg` → `var(--bg)` (explicit — do not let it chain to chrome-bg's surface value); `--shell-frame-fill`/`--shell-content-fill` → `var(--bg)`; `--shell-chamfer` → `0px` (verified: the polygon degenerates to a full rectangle, valid clip-path)
- `--btn-v3-gradient` → `none`; `--panel-shadow` → `none`; `--fg-on-accent-muted` → `var(--fg-on-accent)`

### Test machinery

- `tests/browser/design_tokens.py`: rewritten DARK/LIGHT dicts mirroring every literal-hex palette token above (drop shell_chrome_bg if neutralized to var-indirection — document what's mirrored and why).
- `tests/test_design_tokens_a11y.py`: parametrization expanded to ALL fg×bg pairs the system uses (fg ladder × bg/surface/surface-elevated; on-color pairs; status × bg/surface) in both themes; phantom fg-faint exception tests deleted/replaced per the fresh derivation; update the prose comments that scope pairs.
- `tests/test_ui_guards.py` + helpers: new `test_design_token_mirror_in_sync` — **strip `@media` regions first** (tokens.css has THREE `[data-theme="dark"]` occurrences: the main block plus reduced-motion and reduced-transparency @media redefinitions; take only the top-level theme blocks), then parse `--name: value;` pairs. Guard direction is **mirror-driven**: for each mirror key, assert the CSS value matches (hex-normalized, case-insensitive) — a CSS-driven completeness sweep would drag in badge/nav hexes the mirror deliberately omits. Loud failure lists mismatched token/value pairs. **Probe-test**: temporarily change one hex in the mirror → test fails naming the token; revert.
- Refresh `design_tokens.py`'s stale docstring line references while rewriting.
- **Badge on-color pairs**: OUT of this leg's gate. Measure and RECORD each `--badge-*` × its badge-text color in the flight log; gating moves to Flight 3's badge component rebuild (badge values are unchanged this leg, so any failure is pre-existing).
- **Nav rail goes ladder-native (decision)**: light theme's rail is currently a dark-navy palette island (`#0f172a`); v3 retunes nav tokens to `var()` indirection onto the neutral ladders in BOTH themes (light rail in light theme — the quiet-instrument-panel look; M04's palette-island escape hatch is retired for the rail). This removes nav tokens from the literal-hex audit surface and simplifies the mirror. Flag prominently in the flight log — it is a visible design change.

## Acceptance Criteria

- [x] `tokens.css` v3 lands with BOTH theme blocks complete (no half-ported theme); all 81 pre-existing token names still defined (retired ones neutralized); new spacing/radius/shadow tokens defined
- [x] `.venv/bin/python -m pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_ui_guards.py -x --timeout 60` green
- [x] Full-palette parametrization: every literal-hex fg-role token is covered by at least one contrast assertion per theme; any exception annotated with a `# DELIBERATE EXCEPTION` comment and rationale
- [x] Mirror-sync guard green AND probe-verified (mutation test performed and reverted)
- [x] `make restart` then visual sanity via goldfinch on 8484: both themes render (toggle via the System page), no unstyled surfaces, glows/glass/bezels visually gone (neutralized)
- [x] `make test-unit` green
- [x] `ruff check` / `ruff format --check` clean

## Verification Steps

- Run the pytest command above; `make test-unit`
- Probe: mutate one mirror hex → guard fails naming token → revert
- Definition-name set diff vs HEAD: extract all `--name` definitions from tokens.css at HEAD and after the rewrite; assert the sets are equal modulo the documented additions (spacing/radius/shadows) — consumer-less tokens (`--glass-highlight`, `--panel-shadow`, `--fg-on-accent-muted`) aren't protected by `test_token_definitions.py`, so this diff is the only net catching their accidental loss before Leg 2a's deliberate deletion
- goldfinch: open tab to 8484, capture evidence of all three areas in dark then light (printToPDF fallback per apparatus doctrine if screenshots wedge); confirm quiet render; close own tab; restore theme preference to its pre-check value (record it first)

## Implementation Guidance

1. Rewrite tokens.css block by block: dark first, then light designed on its own merits (not flipped). Keep the file's structure (`@layer tokens`, `:root`, two theme blocks, reduced-motion block). LEAVE the reduced-transparency block intact (it references names this leg keeps; Leg 2a deletes it).
2. The neutralization values must be visually inert but definitionally valid CSS for every property they feed (e.g. a `box-shadow: var(--bezel-shadow)` consumer needs `none`, not `transparent`).
3. Mirror + parametrization + guard land in the SAME commit-unit as tokens.css (flight DD).
4. For the contrast math, reuse the existing `contrast_ratio` helpers in test_design_tokens_a11y.py.
5. Update `the_one/agents.md` ONLY where factually invalidated (e.g. audited-pairs description) — the full v3 rewrite of the design section is Leg 3's docs work; don't do it twice.
6. Record every final hex that differs from this leg's target table in the flight log (Decisions).

## Edge Cases

- **A target hex fails a pair**: adjust within the ladder role; if a whole role can't clear its gate, STOP per flight Adaptation Criteria (divert trigger).
- **Tokens referenced only by the reduced-transparency block**: keep defined this leg regardless.
- **`--fg-on-accent-muted`**: verify against BOTH themes' `--accent` fills; it rides accent surfaces.

## Files Affected

- `the_one/interfaces/web/static/css/tokens.css` — rewritten
- `tests/browser/design_tokens.py` — rewritten
- `tests/test_design_tokens_a11y.py` — parametrization expanded, exceptions re-derived
- `tests/test_ui_guards.py`, `tests/_ui_guard_helpers.py` — mirror-sync guard
- `the_one/agents.md` — only factual corrections (full rewrite in Leg 3)

---

## Citation Audit

tokens.css structure/line-ranges, mirror shape, suite structure, and the two mirror drifts verified by the mission-planning token map (2026-07-03) and re-verified by the Flight-2 first-pass architect review (same day, incl. the phantom-exception finding: dark `--fg-faint #808080` ≈5:1 vs test's `#444444`). `test_token_definitions.py` regex behavior (captures primary token in fallback form) verified by the same review.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Update flight-log.md with leg progress entry (incl. final hex decisions)
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
