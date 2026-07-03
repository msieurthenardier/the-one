# Leg: shell-structure-dismantle (2b)

**Status**: completed
**Flight**: [Design Language v3 — Tokens and Type](../flight.md)

## Objective

Physically remove the alien shell structure from `base.css` — the chamfered `#main-content` L-bracket frame, inner-glow layer, content mask, topbar sheen, and brushed sidebar chrome — leaving a plain quiet shell (ladder backgrounds + hairline borders), then delete the now-unreferenced `--shell-*` tokens from `tokens.css`.

## Context

- Flight DDs: "Retire-with-consumers (Leg 2b)", "F2/F3 shell boundary" (F2 strips to plain; F3 rebuilds structure/semantics).
- Depends on: Leg 1 (shell tokens neutralized — the shell already renders visually quiet-ish) and Leg 2a (all non-shell retired families gone; api.py's `var(--shell-bg)` already swapped).
- base.css shell references (verified F2 design review): `--shell-bg`, `--shell-topbar-sheen`, `--shell-chrome-bg`×2, `--shell-frame-fill`, `--shell-chamfer`, `--shell-frame-glow`×2, `--shell-content-fill` — ALL shell consumers live in base.css (~lines 13-118: `#app-topbar` multi-layer background, `#app-sidebar` chrome, `#main-content` clip-path polygon + `::before` frame layer, `.content-panel` mask).
- The neutralized tokens make this visually low-risk: the chamfer is already 0px, sheen none, glows transparent. This leg removes the *machinery* (clip-paths, pseudo-element layers, masks, multi-layer backgrounds) so the CSS reads as simply as it renders.
- Divert trigger (flight): structural coupling bigger than a leg — e.g. layout geometry that depends on the frame pseudo-element's box. (Design review pre-resolved the likely suspects: nothing positions/stacks relative to `#main-content::before`; paint/scroll containment is carried by the surviving `overflow: hidden`; desktop module is clear of shell selectors.)
- **Sequencing (FD)**: implementation starts ONLY after Leg 2a's tokens.css edits are landed in the working tree — both legs edit adjacent tokens.css content (2a deletes the reduced-transparency block containing shell remnants at ~385-401).

## Inputs

- `the_one/interfaces/web/static/css/base.css` (145 lines); Leg 1's tokens.css

## Outputs

- base.css shell rules rewritten to the quiet system (inventory verified: body:10; topbar override 30-35; sidebar override 59-62; #main-content 84-93; ::before 100-122; .content-panel mask 129-137):
  - `body` (line 10): `background: var(--bg)`; KEEP the `overflow: hidden` scroll-trap comment at lines 4-9 (load-bearing documentation)
  - `#app-topbar` / `#app-sidebar`: **delete the two shell override rules** — this restores the base rules' semantic `var(--nav-bg)`/`var(--nav-border)`/`var(--sidebar-bg)` (v3 aliases of surface/border — the preferred vocabulary; do not hand-write literal surface/border)
  - `#main-content`: plain `background: var(--bg)`; NO clip-path, NO `::before` frame/glow layer; PRESERVE the layout-critical declarations: `flex: 1`, `display: flex` column, `min-width/min-height: 0`, `overflow: hidden`, `position: relative`
  - `.content-panel`: delete `mask-image` + `-webkit-mask-image`. **Known intentional delta**: the 8px top content fade ends — content renders fully opaque at the panel top edge (expected, not a regression; note for the visual pass)
  - Skip-link, landmarks, scroll behavior untouched
- tokens.css: all `--shell-*` definitions deleted (both themes and any @media remnants)
- Mirror/design_tokens.py: no change expected (shell tokens unmirrored after Leg 1) — verify

## Acceptance Criteria

- [x] `grep -n -- "--shell" the_one/interfaces/web/static/css/base.css` → zero; `grep -En "clip-path|mask-image" .../base.css` → zero (`.app-shell-row` at base.css:38 is a class name, pre-authorized to survive — it is not a token reference and the tightened grep no longer matches it)
- [x] **BEFORE deleting tokens**: `grep -n -- "--shell" the_one/interfaces/web/api.py` → zero matches (Leg 2a owns that swap; its AC grep alternation does NOT include shell, so verify here — the OAuth page loads only tokens.css and no test can catch a miss)
- [x] `grep -n -- "--shell" the_one/interfaces/web/static/css/tokens.css` → zero matches (incl. any @media remnants)
- [x] `.venv/bin/python -m pytest tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_guards.py -x --timeout 60` green (91 passed)
- [x] `THE_ONE_PORT=8485 make restart` + goldfinch visual pass on 8485: both themes — topbar/sidebar/main read as one quiet surface system with hairline separation; no layout shift artifacts (sidebar width 240, topbar height 48 unchanged); no clipped content at former chamfer corners
- [x] Targeted browser slice green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_flow_hash_routing.py tests/browser/test_flow_keyboard.py -m browser -x --timeout 180` (12 passed)
- [x] `make test-unit` green (3719 passed, 10 skipped); `ruff check`/`format --check` clean

## Verification Steps

- Greps above; pytest; visual evidence both themes (printToPDF fallback); flight-log entry with any structural surprises

## Implementation Guidance

1. Read base.css fully first; map each shell rule to its quiet replacement before editing.
2. Delete the `#main-content::before` layer entirely (it exists only for the frame/glow); confirm nothing else positions relative to it.
3. `.content-panel` mask-image: delete; verify scroll/overflow behavior unchanged.
4. Preserve the CSS custom-property *geometry* tokens still in use (`--sidebar-w`, `--topbar-h`).
5. Shell token deletion LAST, then re-run the definitions test.

## Edge Cases

- **The frame `::before` doubles as a stacking-context/scroll shim**: if removal changes scroll or z-order, fix within the leg via explicit `position`/`z-index` on the real elements; log it.
- **Windows/pywebview-specific styling** keyed to shell classes: grep `the_one/interfaces/desktop/` for shell selectors before assuming CSS-only.

## Files Affected

- `the_one/interfaces/web/static/css/base.css` — rewritten shell rules
- `the_one/interfaces/web/static/css/tokens.css` — shell definitions deleted

---

## Citation Audit

base.css shell-reference inventory and line ranges verified by the F2 first-pass architect review and Leg-2a design review (2026-07-03, both). Leg-1 flight log confirms neutralized values landed and `--shell-bg: var(--bg)` explicit.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg (`shell-structure-dismantle`) in flight.md
