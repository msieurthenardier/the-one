# Squawk 0007: Add `--status-success-bg-soft` token and apply it to `.diff-add`

**Status**: escalated
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-26
**Completed**: —

## Report

The Mission 21 Flight 2 HAT restyle added before→after diff highlighting on the
self-configuration tab. Deletions render on a `--status-danger-bg-soft`
background; **additions get color + underline only**, because the design system
defines `-bg-soft` variants for warning and danger but **not** for success. The
result is WCAG-safe (the underline carries meaning, never color alone) but
visually asymmetric. Define `--status-success-bg-soft` in the token layer
(mirroring the warning/danger `-bg-soft` derivation, for both light and dark
themes) and apply it to `.diff-add` so additions and deletions read
symmetrically. No behavior change; purely presentational.

## Evidence

- `the_one/interfaces/web/static/css/studio.css` — `.diff-del` uses
  `--status-danger` + `--status-danger-bg-soft`; `.diff-add` uses
  `--status-success` + underline (no background) with an inline comment noting the
  missing token.
- Token layer: `tokens.css` defines `--status-warning-bg-soft` and
  `--status-danger-bg-soft` under both `[data-theme="dark"]` and
  `[data-theme="light"]`, but no `--status-success-bg-soft`. A token-mirror test
  (`tests/browser/` design-token check) enforces light/dark palette lockstep, so
  the new token must be added to both themes.
- Mission 21 Flight 2 debrief, "What Could Be Improved → Technical".

## Corrective Action

**Escalated — not completed as a squawk.** A literal mirror of the
danger-derivation (same hue as `--status-success`, same alpha as
`--status-danger-bg-soft`: dark `0.08`, light `0.06`) was drafted and
verified, then **reverted**, because it reproduces the exact AA failure
the report asked this fix to avoid:

- Drafted: dark `--status-success-bg-soft: rgba(74, 222, 128, 0.08)`;
  light `--status-success-bg-soft: rgba(21, 128, 61, 0.06)`; `.diff-add`
  gained `background: var(--status-success-bg-soft)` alongside the
  existing color + underline, mirroring `.diff-del`'s structure exactly.
- Contrast check (WCAG relative-luminance formula, light-theme
  `--status-success` `#15803d` text over the composited fill, all three
  ladder surfaces):
  - on `--bg` (`#ffffff`): fill `rgb(241,247,243)` → **4.62:1** (passes)
  - on `--surface` (`#fafafa`): fill `rgb(236,243,239)` → **4.45:1**
    (fails body AA, threshold 4.5:1)
  - on `--surface-elevated` (`#f4f4f5`): fill `rgb(231,237,234)` →
    **4.23:1** (fails body AA)
  - Dark theme is not at risk: worst case (surface-elevated) is
    **8.28:1**.
- Root cause: light-theme `--status-success` (`#15803d`) already sits at
  a thin margin against the plain ladder (4.56:1 worst-case, on
  surface-elevated, vs. body AA's 4.5:1 floor — see `tokens.css`'s
  status-color header comment). Green's low weight in the WCAG
  luminance formula (0.7152 vs. red's 0.2126) means *any* self-tinted
  wash — even alpha `0.01` — erodes that margin below 4.5:1 on two of
  three surfaces; alpha would need to drop to ≈0 to clear (verified:
  `0.02` still fails at 4.46:1, `0.01` barely clears at 4.51:1 — not a
  usable wash). Deepening `--status-success` (the fix danger/warning
  used — M17 F3/F5) or hand-picking a bespoke alpha are both **design
  decisions** (they change a status color used elsewhere, or introduce
  an undocumented one-off derivation) — outside this squawk's
  qualification gate ("no design decisions"; `CLAUDE.md` →
  `docs/squawks.md`).
- Both CSS files were reverted to their pre-squawk committed state
  (`git checkout --` on `tokens.css` and `studio.css`); tree is clean —
  `git diff` against HEAD for both files is empty.
- Recommendation: escalate to a flight (or fold into the next
  design-system flight) to either (a) deepen light-theme
  `--status-success` following the danger/warning precedent (retune,
  re-gate in `test_design_tokens_a11y.py`, update the mirror in
  `tests/browser/design_tokens.py`), or (b) accept the asymmetry and
  close this as won't-fix with a comment explaining why success has no
  `-bg-soft` variant.

## Verification

- Token-mirror / design-token test
  (`tests/test_ui_guards.py::test_design_token_mirror_in_sync`,
  `tests/test_token_definitions.py`): **passed** against the drafted
  (pre-revert) CSS — 2 passed.
- `tests/test_design_tokens_a11y.py` (full file, drafted CSS): **1
  failed, 146 passed** —
  `test_sc2_every_fg_role_token_is_gated_or_exempt` flagged
  `--status-success-bg-soft` in both themes as an rgba wash with no
  registered `_CONTRAST_EXEMPT` entry (expected — that entry is exactly
  the kind of judgment call this squawk can't make, since the honest
  entry would have to document a real AA failure rather than an
  exemption rationale like danger/warning's).
- Manual AA contrast for the light-theme composite: see Corrective
  Action above (4.62 / **4.45 (fail)** / **4.23 (fail)** on
  bg/surface/surface-elevated).
- Because the change was reverted, the browser test run
  (`THE_ONE_DEV_MODE=true PYTHON=.venv/bin/python bash
  scripts/run-tests.sh -m browser tests/test_design_tokens_a11y.py
  tests/browser/test_studio_self_configuration_history.py -x --timeout
  120 -q`) and `ruff check . && ruff format --check .` were **not**
  run against a shipped change — the working tree is byte-identical to
  the pre-squawk commit for both target files, so no verification
  against a modified tree is meaningful. (`ruff` was not needed: no
  Python was touched, and the CSS revert leaves nothing to lint/format.)

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
## Disposition

**Escalated** (2026-08-29, turnaround 2026-08-29): failed qualification criterion 2 — *no design
decisions*. The literal fix (mirror `--status-danger-bg-soft`'s derivation at the same alpha)
drops light-theme `--status-success` text (`#15803d`, 4.56:1 today) below WCAG AA on the
composited wash — 4.45:1 on `--surface`, 4.23:1 on `--surface-elevated` — and
`tests/test_design_tokens_a11y.py::test_sc2_every_fg_role_token_is_gated_or_exempt` correctly
refuses it. Green carries heavy luminance weight, so no self-tinted alpha clears AA; the only
honest fixes are (a) deepen the light-theme `--status-success` hue (the precedent danger and
warning took in M17 F3/F5), which re-touches every consumer of that token, or (b) accept the
asymmetry as won't-fix. Either is a design choice. Code reverted; nothing left in the tree.
→ No active mission covers design tokens. Recommended vehicle: a leg in the next UI-polish or
maintenance flight, framed as "deepen light-theme success hue for AA on soft washes" with the
contrast math above as its evidence; or close as won't-fix at the next maintenance review.
