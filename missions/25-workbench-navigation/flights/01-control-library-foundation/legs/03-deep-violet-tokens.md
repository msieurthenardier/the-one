# Leg: deep-violet-tokens

**Status**: completed
**Flight**: [Control Library Foundation](../flight.md)

## Objective

Land the approved deep-violet treatment app-wide through tokens and CSS, and bring
control boundaries to non-text AA. Every pair introduced or changed is gated in both
themes, and every migrated CSS site is pinned to its gated pair.

## Context

- Flight decisions implemented here: **DD6** (tokens, fill migration rule, button
  treatment, size modifiers, `.btn-icon`, overrides), **DD7** (contrast gates, the dark
  band exception, control boundaries, housekeeping comments) and **DD15** rows A1, A4–A7.
  Read DD6 and DD7 in `flight.md` in full; they are the spec. This leg restates only what
  is needed to verify.
- Approved source: `reference/boards/Buttons.dc.html` (the `.deep` rules and the
  per-theme `--x-violet*` vars) and `reference/reference-spec.md` §11 (Buttons: Deep
  violet). The spec's §15 A-items for this flight are disposed in DD15.
- This leg is independent of the mechanism spike: pure tokens, CSS and gates. It adds no
  JS beyond what a CSS-only change needs, which is none.
- Prior lessons (M17 debriefs):
  - **Soft-fill contrast failed three times.** Gate the composite pair when the leg is
    written, not after a review finds it.
  - **Ask what sits on surfaces whose colours change.** Every text, tick or thumb drawn
    on a moved fill moves with it (DD6 rule).
  - **JS strings can reference CSS variables.** `test_js_string_css_var_refs_are_defined`
    covers them. Grep JS for `--accent` too, for inline styles that paint a control fill.
  - **Grep counts run high.** Classify each hit by reading the rule, not by counting.
- The mirror `tests/browser/design_tokens.py` (`DARK`, `LIGHT`) must be updated in the
  same change. `test_design_token_mirror_in_sync` and the SC2 completeness net
  (`test_sc2_every_fg_role_token_is_gated_or_exempt`) enforce it.
- Visual snapshots (`-m pixel`) are gitignored and local-only; they will differ. They are
  not a gate and must not be committed.

## Inputs

- `the_one/interfaces/web/static/css/tokens.css`:
  - dark block `[data-theme="dark"]` (line 54), light block (line 188);
  - `--accent` at lines 95/221;
  - `--fg-on-accent` at lines 86/215;
  - `--border-strong` at lines 71/201;
  - `--fg-faint` and its "never interactive affordances" comment at lines 74/85 and
    204/214.
- `components.css`:
  - `.skip-link` (lines 15-27);
  - `.checkbox-primary` (lines 331-364; `:checked` at 346-357, `:hover` border at 345);
  - the button block (lines 393-535: `.btn-outlined-primary` 404-432,
    `.btn-filled-primary` 434-454, `.btn-ghost` 456-482, `.btn-muted-destructive`
    484-511, size modifiers 524-526, svg sizing 532-535);
  - `.save-btn` (lines 984-986), `.delete-btn` (line 1010).
- `admin.css`:
  - `.admin-theme-option.active` (lines 79-84);
  - `.tool-enable-switch-track` and thumb (lines 270-300+, both areas);
  - `.admin-pf-pull-fill` (line 161), a meter that stays on `--accent`.
- `studio.css`:
  - `.tool-actions .btn-outlined-primary` (line 63);
  - `.tool-switch` (lines 65-75; indeterminate at 72-75, which stays on `--accent`);
  - `.chip-attached` (line 397);
  - `.mcp-refresh-tools-btn` (line 407), `.mcp-source-tile-row1 .mcp-refresh-tools-btn`
    (lines 473-476);
  - the area button override (line 62).
- `chat.css`:
  - `.context-bar` (line 119), a meter that stays on `--accent`;
  - `.msg-pending-approval-approve` (lines ~520-526).
- `tests/test_design_tokens_a11y.py`:
  - `test_text_on_color` (line 222);
  - `test_status_text_passes_body_aa` (line 234);
  - `test_danger_text_on_soft_fill_passes_body_aa` (line 277);
  - `test_editor_error_banner_consumes_the_gated_danger_pair` (line 363), the usage-pin
    model;
  - `test_tool_switch_indeterminate_thumb_holds_ui_contrast` (line 450);
  - `test_fg_faint_band_exception` (line 634);
  - `_CONTRAST_EXEMPT` (line 708) and the completeness net (line 752).
- `tests/browser/design_tokens.py`
- `tests/browser/test_deep_violet_computed_styles.py`: new. (`DARK` lines 60-125, `LIGHT` lines 134-202).
- `the_one/agents.md` "Design language v3" (from about line 1594): the buttons, accent
  and colour-contrast bullets.

## Outputs

- **Tokens.** `tokens.css` gains, in both theme blocks:
  - `--accent-fill`, `--accent-fill-hover`, `--fg-on-accent-fill` (DD6 values);
  - `--control-border` (a hex chosen by this leg, DD7).

  Each has a short comment stating its role and that it is gated.
- **Mirror.** `design_tokens.py` gains the same keys in `DARK` and `LIGHT`.
- **CSS.**
  - Every solid control fill site is migrated per the DD6 rule.
  - The four button treatments are restyled.
  - `.btn-icon` is added.
  - The overrides are reconciled.
  - The checkbox and the three toggle kinds get `--control-border` off-state boundaries
    and thumbs that pass in both states.
- **Gates.**
  - New contrast gates per the DD7 table.
  - The dark-only band exception.
  - Boundary gates.
  - CSS usage pins for every migrated or bounded site.
  - The housekeeping comment updates.
- **Docs.**
  - `agents.md` Design language section: deep violet, the fill-token roles, button
    variants and modifiers, `.btn-icon`, control boundaries, the updated accent rule.
  - The dev-mode design-language **tokens** section lists the new tokens (one array edit
    in `tokens-section.js`).
  - The **buttons** section shows `.btn-icon`, with the existing rows unchanged.
- **Flight log.** A leg entry with the classified list of every `var(--accent)` fill hit
  (moved, or stays with a reason).

## Acceptance Criteria

- [x] **AC1 — Tokens.** `--accent-fill`, `--accent-fill-hover` and `--fg-on-accent-fill`
  exist in **both** theme blocks with exactly the DD6 values:

  | Token | Dark | Light |
  |---|---|---|
  | `--accent-fill` | `#7c3aed` | `#6d28d9` |
  | `--accent-fill-hover` | `#6d28d9` | `#5b21b6` |
  | `--fg-on-accent-fill` | `#ffffff` | `#ffffff` |

  Two control tokens are added in both blocks:
  - `--control-border`: dark `#6e717a` (3.87/3.64/3.45 against bg/surface/elevated),
    light `#868690` (3.60/3.45/3.28). These were computed at design review; re-verify
    them in the gates.
  - `--control-thumb`: `#ffffff` in both themes. It is the toggle thumb in **both**
    states, so the off state does not semantically reuse an "on-accent" token.

  All five are in `DARK` and `LIGHT` in `tests/browser/design_tokens.py`.
  `test_design_token_mirror_in_sync` passes.
- [x] **AC2 — Fill migration.**
  - Every CSS rule that paints a **control** with a solid `var(--accent)` fill uses
    `var(--accent-fill)`, including any paired `border-color: var(--accent)`.
  - Every text, tick or thumb colour drawn on such a fill uses `var(--fg-on-accent-fill)`.
  - The fill sites include, at least: `.btn-filled-primary`, `.checkbox-primary:checked`
    and its tick, `.skip-link`, `.admin-theme-option.active`, both
    `.tool-enable-switch` on-state tracks and thumbs, the `.tool-switch` on-state, and
    `.msg-pending-approval-approve`. `.chip-attached` drops the `white` fallback.
  - These stay on `--accent`, with the reason recorded in the flight log:
    `.context-bar`, `.admin-pf-pull-fill`, the indeterminate `.tool-switch` thumb, and
    every border, outline, link, wash or focus use.
  - The paired borders move too: `.msg-pending-approval-approve` (`chat.css:525`) and
    `.chip-attached`.
  - The flight log lists every `var(--accent)` **and** `var(--fg-on-accent)` hit in
    `static/css/*.css` and in JS strings, with its classification. The known
    `--fg-on-accent` consumers that **stay**:
    - `.msg.user.api` on `--accent-api` (`chat.css:149`), now the remaining real
      consumer of the `fg_on_accent`×`accent_api` gate;
    - `.msg-pending-approval-badge--approved` on `--status-success` (`chat.css:557`);
    - the base `.admin-provider-badge` and `.admin-tool-badge` colours (`admin.css:98,
      211`), whose modifiers override them.
- [x] **AC3 — Buttons.** The four variants render per DD6:
  - **primary**: `--accent-fill`, white label, hover `--accent-fill-hover`, no opacity
    hover;
  - **secondary**: `--surface-elevated` fill, `--border` hairline, `--fg` label, hover
    border `--border-strong`;
  - **ghost**: transparent, `--fg-secondary`, hover `--surface-elevated` and `--fg`;
  - **danger**: transparent, `--status-danger-muted` hairline, `--status-danger` label,
    hover `--status-danger-bg-soft`.

  Shared values: height 32px, padding `0 12px`, radius `--radius-sm`, label
  `--font-size-body` at `--font-weight-medium`, svg 16px. Focus ring and disabled are
  unchanged.

  Hover details:
  - Secondary hover changes **only** the border; danger hover changes **only** the fill.
    The current border-to-`--status-danger` and fill/`--border-hover` hover changes are
    dropped.
  - Every variant transitions `background-color`, `border-color` and `opacity` on the
    motion tokens. Today the primary transitions only `opacity`.
  - Size modifiers must not set a font-weight.
- [x] **AC4 — Modifiers and icon-only.**
  - `.btn-sm`, `.btn-lg` and `.btn-xl` keep their heights, padding and label sizes, and
    take the medium weight.
  - New `.btn-icon` makes a 32×32 button with zero padding and a 16px svg, and a 24×24
    one with a **14px** svg when combined with `.btn-sm`.
- [x] **AC5 — Overrides reconciled.** The actual contradictions to fix:
  - `.save-btn` (`components.css:984`): pins `padding: 6px 16px` and `font-size:
    body-sm`. Remove both, so DD6's `0 12px` and 13px apply.
  - `.delete-btn` (`components.css:1010`): pins padding, a 6px radius and `body-sm`.
    Align it to DD6. The **armed** state's semibold (`.delete-btn.confirm-delete`,
    `:1011`, and `.admin-pf-model-delete-confirm`, `admin.css:98`) is a deliberate
    solid-danger state and **stays**, with a comment saying so.
  - `.mcp-refresh-tools-btn` (`studio.css:407`): pins `body-sm`. Remove it.

  Compact rows stay CSS-only as **documented exceptions**. Each keeps its compact size
  with a CSS comment naming DD6 and why, and the flight log lists them:
  - `.tool-actions .btn-outlined-primary` (`studio.css:63`; line 62 is its comment);
  - the tile-row `.mcp-source-tile-row1 .mcp-refresh-tools-btn` (`studio.css:473`).

  No JS markup changes in this leg: editor internals are out of scope.
- [x] **AC6 — Contrast gates** in `tests/test_design_tokens_a11y.py`, both themes unless
  stated:
  - `fg_on_accent_fill` on `accent_fill` and on `accent_fill_hover` ≥ 4.5, as new
    tuples in `test_text_on_color`;
  - `accent_fill` vs `bg` and `surface` ≥ 3.0, a new test, since `surface_elevated`
    cannot share `test_large_or_ui_passes_aa`'s three-surface list;
  - `accent_fill` vs `surface_elevated` ≥ 3.0 in **light**;
  - a **dark-only** band test asserting `2.9 ≤ ratio < 3.0` for `accent_fill` vs
    `surface_elevated`, with a `# DELIBERATE EXCEPTION` comment and the DD7 rationale;
  - a danger-only `status_danger` on `surface_elevated` ≥ 4.5, a new test, since the
    shared status test deliberately excludes elevated for success and warning;
  - a comment noting that `accent_fill_hover` vs surfaces is **not** gated: it is below
    3.0 in dark, and no state-bearing control uses it;
  - `"--control"` is added to `_FG_ROLE_PREFIXES`, with its rationale comment, so the SC2
    completeness net covers `--control-border` and `--control-thumb`;
  - the net passes with all five new tokens gated, not exempted.
- [x] **AC7 — Control boundaries.**
  - `--control-border` is ≥ 3.0 against `bg`, `surface` and `surface_elevated` in both
    themes, gated.
  - The unchecked `.checkbox-primary` border uses it. The off track of
    `.tool-enable-switch-track` (both areas) and of `.tool-switch` uses it.
  - Every toggle thumb (all three kinds) uses `--control-thumb` in both states. The named
    gated pairs are:
    - `control_thumb` on `control_border` (off): ≥ 3.0, about 4.88 dark and 3.60 light;
    - `control_thumb` on `accent_fill` (on): ≥ 3.0.
  - `control_border` slots into `test_large_or_ui_passes_aa`'s `fg_key` list.
  - The **indeterminate** `.tool-switch` track stays an accent wash with no boundary:
    the gated thumb carries that state. This is recorded as an accepted design note in
    the CSS comment and the flight log.
  - The checkbox `:hover` border keeps `--accent`, whose existing UI gate covers it.
  - The existing `test_tool_switch_indeterminate_thumb_holds_ui_contrast` still passes,
    unchanged in intent.
- [x] **AC8 — Usage pins.** For every migrated fill site, and for every boundary or thumb
  site, a source-grep unit test asserts the rule block consumes the gated tokens. These
  follow `test_editor_error_banner_consumes_the_gated_danger_pair`. Parametrize where
  that keeps it readable. A future edit that moves a fill without its ink fails a test.
- [x] **AC9 — Housekeeping.** These comments and docstrings are updated so they stay
  true:
  - the comment on the existing `fg_on_accent`/`accent` gate (it keeps guarding the token
    but has no solid-fill consumer now), and `components.css:~200`'s "consumer today is
    `.btn-filled-primary`";
  - the button-block comment (`components.css:393-401`: "flat accent fill", "soft danger
    fill + muted danger border");
  - the `--accent` comments in `tokens.css` (around lines 92-94 and 219);
  - the danger-gate comment (around line 265);
  - the `test_status_text_passes_body_aa` docstring on surface-elevated;
  - the `.tool-enable-switch-track` CSS comment about `--border-strong`.
- [x] **AC10 — Docs.**
  - The `agents.md` Design language section describes:
    - deep violet and the fill tokens (`--accent-fill*` for solid control fills;
      `--accent` for focus, links, selection, washes and meters);
    - `--control-border`;
    - the four button variants and their modifiers;
    - `.btn-icon`;
    - the dark band exception.
  - The design-language tokens section shows the four new tokens.
  - The buttons section adds an icon-only row.
- [x] **AC10b — Automated computed-style test.**
  `tests/browser/test_deep_violet_computed_styles.py` (`shared` lane) uses `engine_page`
  plus `load_harness(page, theme)`, parametrized over both engines and both themes.
  - **Reduced motion.** It emulates `prefers-reduced-motion: reduce` (motion tokens
    collapse to 0, `tokens.css:326`), so hover reads are not mid-transition.
  - **What it mounts.** One button per variant, plus `.btn-sm`, `.btn-lg`, `.btn-icon`
    and `.btn-icon.btn-sm`, a checked and an unchecked `.checkbox-primary`, and an on and
    an off `.tool-enable-switch`.
  - **Area overrides.** The admin and studio toggles and compact rows are mounted inside
    `.area-admin`/`.area-studio` wrappers, so area-scoped rules apply.
  - **What it asserts.** Computed `background-color`, `color`, `border-color`,
    `font-size`, `font-weight`, `height`, `padding` and svg size. Each value is checked
    against the DD6 values and the mirror in `design_tokens.py`, with `rgb()` normalised.
  - **Hover.** It asserts the hover state for primary, secondary, ghost and danger via
    `page.hover()`.

  The dev-instance spot-check becomes a supplement only.
- [x] **AC11 — Gates pass:**
  - `make lint`;
  - `make test-unit`, which includes `tests/test_ui_guards.py`,
    `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py`;
  - **all four browser lanes**, each run separately: `--lane chat`, `--lane studio`,
    `--lane system`, `--lane shared`.

  Deep violet is app-wide CSS, so every lane is in the diff. A lane failure is rerun alone
  before being treated as a regression (the standing flake rule). A real failure is
  fixed, or raised as an anomaly.

## Verification Steps

- AC1, AC6, AC7, AC8, AC9:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_design_tokens_a11y.py tests/test_ui_guards.py tests/test_token_definitions.py -x --timeout 60`,
  then read the new tests.
- AC2: `grep -n 'var(--accent)\|var(--fg-on-accent)' the_one/interfaces/web/static/css/*.css`, cross-checked
  against the flight-log classification. Also
  `grep -rn "\-\-accent" the_one/interfaces/web/static/js | grep -v accent-` for JS
  inline fills.
- AC3–AC5, AC10b:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh -m browser tests/browser/test_deep_violet_computed_styles.py -x -rA`.
  It runs both engines and both themes. Optionally, as a supplement, spot-check the
  design-language buttons section on a dev instance (port 8485, scratch data dir, dev
  mode). Do not commit screenshots.
- AC10: read the doc diffs.
- AC11: run the listed commands; the flight log records pass counts and durations per
  lane.

## Implementation Guidance

1. **Tokens and mirror first.**
   - Add the tokens in both blocks, next to `--accent`.
   - Choose `--control-border` by computing ratios against `bg`, `surface` and
     `surface_elevated` in each theme. Pick the lowest-chroma neutral that clears 3.0
     with a small margin (≥3.1), so the boundary reads as a control edge, not as text.
   - Record the computed ratios in the flight log.
   - Update the mirror.
2. **Gates next** (AC6, AC7), written **before** the CSS migration. They fail until the
   tokens are right, which proves they gate.
3. **Migrate fills** (AC2). Read each `var(--accent)` hit and classify it. Apply the DD6
   rule, moving the fill, any paired border and the ink together.
4. **Buttons and modifiers** (AC3–AC5). The board's `.deep` rules are the source:
   - secondary hover changes only the border, not the fill;
   - danger at rest is transparent.

   Keep the existing `:focus-visible` and `:disabled` rules.
5. **Boundaries** (AC7). The admin toggle thumb rule applies to both states, so split it
   per state where needed.
6. **Usage pins** (AC8), **housekeeping** (AC9), **docs** (AC10).
7. **Full gates** (AC11). Run the lanes one at a time. A full lane run can take several
   minutes. Set `TEST_TIMEOUT` generously (e.g. `TEST_TIMEOUT=1800` for studio).

## Edge Cases

- **A browser test that asserts the old look.** The design review found none for button
  or toggle colours. If one surfaces (e.g. hover opacity), update it in this leg with a
  comment citing DD6. Do not weaken it.
- **`.chip-attached`** currently has `color: var(--fg-on-accent, white)`; drop the
  fallback and use `--fg-on-accent-fill`.
- **Light-theme `--accent` already equals the new light `--accent-fill`** (`#6d28d9`). The
  light theme still migrates by token name, so a later retune of either stays
  independent.
- **`--control-border` and the checkbox hover border** (`--accent`, light `#6d28d9`): both
  pass, and hover remains a visible change.
- **Concurrent edits with Leg 2.** Leg 2 touches `components.css` (list-pane CSS) and
  `index.html` in the same working tree. Use line-anchored edits, never full-file
  rewrites. Re-run the AC2 grep at the end, and classify any `var(--accent)` fill Leg 2
  introduced (e.g. a selected row). List-pane selection is a wash plus ring, which
  stays on `--accent`.
- **The secondary fill on a `--surface-elevated` tile** is invisible (a 1.1:1 hairline).
  WCAG 1.4.11 does not require a button boundary when the label is visible. Accept it,
  and log the design note.
- **The dark checkbox tick** changes from dark ink to white. This is an expected visible
  change.
- **The DD7 band exception** also covers `.chip-attached` on elevated tiles, which
  carries text; white on `accent_fill` is 5.70, so the text is fine. Mention it in the
  band-test comment.
- **Pixel snapshots** fail locally after this leg. Do not regenerate or commit them as
  part of the gate.

## Files Affected

- `the_one/interfaces/web/static/css/tokens.css`
- `the_one/interfaces/web/static/css/components.css`
- `the_one/interfaces/web/static/css/admin.css`
- `the_one/interfaces/web/static/css/studio.css`
- `the_one/interfaces/web/static/css/chat.css`
- `the_one/interfaces/web/static/js/areas/admin/design-language/tokens-section.js`,
  `buttons-section.js`: demo additions only.
- `tests/browser/design_tokens.py`
- `tests/test_design_tokens_a11y.py`
- `the_one/agents.md`
- `missions/25-workbench-navigation/flights/01-control-library-foundation/flight-log.md`

## Citation Audit

Checked against the flight branch at leg design (2026-09-30). Line numbers are
approximate where marked; anchor on the selector text:
- `admin.css:270-300`: the `.tool-enable-switch-track` off-state is `--border-strong`;
  the thumb `::after` is `--fg-on-accent` in both states; on-state `:checked` is
  `--accent` ✔
- `studio.css:63-75`: `.tool-actions .btn-outlined-primary` caption override;
  `.tool-switch` off `--surface-elevated`, thumb `--fg-tertiary`, on `--accent`,
  indeterminate thumb `--accent` ✔
- `studio.css:397`: `.chip-attached` uses `var(--fg-on-accent, white)` ✔
- `chat.css:119` `.context-bar`, `admin.css:161` `.admin-pf-pull-fill`: meters ✔
- `test_design_tokens_a11y.py`: test names and lines as listed in Inputs ✔

Design review (Developer, 2026-09-30) — "approve with changes". Applied:
- the automated computed-style test (AC10b), in both engines and both themes;
- AC5 rewritten to the real override contradictions, with compact rows kept as
  CSS-only documented exceptions;
- `--fg-on-accent` consumers classified;
- a `--control-thumb` token, with named thumb pairs and an accepted indeterminate
  track;
- the `--control-border` hexes chosen;
- `"--control"` added to the completeness-net prefixes;
- extra stale comments;
- hover and transition details;
- the `.btn-icon` svg sizes pinned;
- notes on the Leg 2 overlap.

---

## Post-Completion

Completion steps — status transitions, flight-log update, checking off in the parent
flight, and commit — are Flight Control protocol, driven by the execution workflow. Not
repeated here.
