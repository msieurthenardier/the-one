# Leg: consumer-sweep (2a)

**Status**: completed
**Flight**: [Design Language v3 — Tokens and Type](../flight.md)

## Objective

Remove every retired-category reference from `components.css`, `chat.css`, `studio.css`, and `admin.css`; quiet the `.section-title` treatment; then delete the neutralized alias tokens and the dead `prefers-reduced-transparency` block from `tokens.css`.

## Context

- Flight DDs: "Retire-with-consumers (Leg 2a)", "Section markers quieted", "Focus system pinned", "Type discipline".
- Depends on Leg 1 (landed): retired tokens currently neutralized, so every removal here is visually near-invariant — the effects are already off; this leg removes the dead weight and locks the door.
- Blast radius (verified at flight design): `var(--glass-*)` 45 + `backdrop-filter` 14; `var(--*glow*)` 50; `var(--bezel-*)` 26; `btn-v3-gradient` 6; `panel-shadow` 1 — concentrated components.css (glow 27-family, bezel 18, glass 19), studio.css (glass 22), chat.css (glow 11), admin.css (glow 4, bezel 3, btn-v3 2). base.css is Leg 2b — do NOT touch base.css in this leg.
- `test_token_definitions.py` gates the ordering: consumers must be gone from the four files BEFORE the alias deletion (base.css still references shell tokens after this leg — therefore delete ONLY the aliases whose consumers are fully gone: glass/glow/bezel/btn-v3-gradient/panel-shadow/fg-on-accent-muted. Shell tokens stay defined until Leg 2b removes base.css's references, then Leg 2b deletes them.)

## Inputs

- Leg 1's landed tokens.css (neutralized aliases present)
- The four component CSS files; `the_one/interfaces/web/static/js/areas/admin/design-language/status-section.js` (ALL-CAPS text)

## Outputs

- Zero references to glass/glow/bezel/btn-v3-gradient/panel-shadow tokens and zero `backdrop-filter` declarations in the four CSS files
- Rewritten declarations follow the quiet system: where a removed effect was load-bearing for hierarchy, substitute per these rules —
  - glass surface → `background: var(--surface)` (or `--surface-elevated` where layered above surface) + `border: 1px solid var(--border)`
  - glow hover/active ring → border-color shift to `var(--border-hover)` or `--accent` for selected states; NO new shadows
  - `:focus-visible` glow halo → the pinned form: `outline: 2px solid var(--accent); outline-offset: 2px` (drop the box-shadow halo member; keep any non-halo members of composite lists). **Three sanctioned variants** (design-review): (a) inset rings keep their NEGATIVE outline-offset (`components.css:154`, `chat.css:596` — the ring must stay inside clipping/scroll containers; drop only the glow); (b) destructive controls keep a DANGER-colored outline (`chat.css:571` `.btn-stop-turn` → `outline: 2px solid var(--status-danger)`, glow member dropped — semantic color is meaningful); (c) 1px-outline form fields (`components.css:202/222/242`, `chat.css:565`, `studio.css:40`) normalize to the 2px pinned form — an intended, visible form-field change.
  - bezel depth → nothing (hairline borders already delineate) — delete the declaration
  - btn-v3 gradient wash → flat `var(--accent)` fill (primary) or `var(--surface)` + border (secondary) per the button's role
  - **floating surfaces (toasts included)** → `var(--shadow-popover)` + surface + border: `.app-flash` (components.css:3-5) is a toast whose only elevation was glow — it takes the popover shadow (decision: toasts float, so the two-shadow system covers them)
  - **LED/status-dot glows** (components.css:937-939, 962-964) → delete; flat dots (paired with their text labels, color is never the only signal)
- `.section-title` quieted: `::before` "//"" pseudo-element deleted; treatment becomes sans (`var(--font-family-sans)`), `var(--font-size-body-sm)`, weight 500, `var(--fg-secondary)`, no letter-spacing/uppercase; `status-section.js` hardcoded ALL-CAPS strings ("SYSTEM"/"AGENTS"/"MCP") converted to normal case; stale `// PROMPT`-style comments in admin/chat/studio CSS+JS cleaned where encountered
- tokens.css: glass/glow/bezel/btn-v3-gradient/panel-shadow/fg-on-accent-muted definitions DELETED (both themes); `prefers-reduced-transparency` block DELETED; shell tokens retained (Leg 2b's)
- **`the_one/interfaces/web/api.py` OAuth-callback inline CSS** (design-review catch — `test_token_definitions.py` scans only static/css, so this consumer is invisible to the suite): `box-shadow: var(--panel-shadow)` at ~api.py:2148 → `var(--shadow-popover)` (floating card); `var(--shell-bg)` → `var(--bg)`; the `::before { content: "//" }` eyebrow → deleted (marker quieting applies here too — one edit while in the block)
- **`tokens-section.js` gallery: drop the single `'--accent-glow'` entry** (line ~23) — otherwise the gallery renders an undefined-token swatch between this leg and Leg 3, tripping this leg's own visual pass; justify the (JS) diff in the flight log per flight DD (createElement-based file — no sink-baseline impact)
- Stale retired-vocabulary comments cleaned in **components.css (356-360, 393, 574, 905)**, studio.css (388-391, 507-511, 1499-1502), `mcps-tab.js:100-101`, `connectors-tab.js:144` — leftover names in comments could trip Leg 3's banned-token guard
- Declarations touched in this sweep adopt spacing/radius tokens where a literal maps exactly (opportunistic, not exhaustive)

## Acceptance Criteria

- [x] `grep -En "var\(--(glass|accent-glow|status-[a-z]+-glow|bezel|btn-v3|panel-shadow|fg-on-accent-muted)" the_one/interfaces/web/static/css/{components,chat,studio,admin}.css the_one/interfaces/web/api.py` → zero matches; same for `backdrop-filter` (catches `-webkit-` variants as substring)
- [x] `grep -c "var(--" the_one/interfaces/web/static/css/tokens.css` internal-chain check: no remaining tokens.css definition references a deleted family (guards against a Leg-1 deviation chaining a kept token onto a deleted one — the definitions test never scans tokens.css itself)
- [x] Those token definitions absent from tokens.css; `prefers-reduced-transparency` block gone; shell tokens still defined
- [x] `.venv/bin/python -m pytest tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_guards.py -x --timeout 60` green
- [x] Every `:focus-visible` rule in the four files matches the pinned form (grep-verifiable: no `box-shadow` mentioning accent in a focus rule)
- [x] `make restart` + goldfinch visual pass: both themes, all three areas — no unstyled/broken surfaces, `//` markers gone, section titles read quiet
- [x] `make test-unit` green; targeted browser slice green: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_studio_mcps_tab.py tests/browser/test_theme_toggle_cleanup.py tests/browser/test_flow_hash_routing.py -m browser -x --timeout 180` (mcps-tab replaces the data:-URL smoke module — it exercises `.mcp-source-tile`, this sweep's heaviest glass+bezel target)
- [x] `ruff check` / `ruff format --check` clean; testid/sink guards green (JS edits limited to: status-section.js text case, tokens-section.js glow-entry removal, comment cleanups in mcps-tab.js/connectors-tab.js — none touch testids or sinks)

## Verification Steps

- The greps above; the pytest commands; visual pass with evidence captures (both themes; printToPDF fallback per doctrine); record per-file before/after declaration counts in the flight log

## Implementation Guidance

1. Sweep file by file: components → chat → studio → admin. For each hit, decide delete vs substitute per the Outputs rules; when a whole declaration's only purpose was the retired effect, delete the declaration (not just the var).
2. `.section-title`: single edit site (components.css:332-353) + the modifier margin overrides in admin/chat/studio are unaffected; `.danger-zone-title` color modifier composes fine. status-section.js: "MCP" stays an acronym; convert "SYSTEM"→"System", "AGENTS"→"Agents"; adjacent telemetry VALUE strings ("ONLINE", "3 ACTIVE") also convert to normal case (quiet system — caps carry no meaning there).
3. After the four files are clean, delete the alias definitions + reduced-transparency block from tokens.css in the same working session, then re-run test_token_definitions.py.
4. Update the mirror ONLY if a deleted token was mirrored (glow entries may be — check design_tokens.py; keep the mirror-sync guard green).
5. Do NOT touch base.css (Leg 2b) or fonts.css.

## Edge Cases

- **A composite box-shadow mixing bezel + glow + a legitimate shadow**: keep only legitimate members; if none remain, delete the declaration.
- **Glass on modals/popovers**: these are "floating" surfaces — they take `var(--shadow-popover)`/`var(--shadow-modal)` per the two-shadow system, plus surface + border.
- **A visual regression that reads as broken (not just quieter)**: fix forward within the quiet rules; if a surface loses ALL hierarchy (indistinguishable nested panels), introduce `--surface-elevated` steps rather than shadows.

## Files Affected

- `the_one/interfaces/web/static/css/{components,chat,studio,admin}.css` — swept
- `the_one/interfaces/web/static/css/tokens.css` — alias + block deletion
- `the_one/interfaces/web/static/js/areas/admin/design-language/status-section.js` — text case
- `tests/browser/design_tokens.py` — only if a mirrored token is deleted

---

## Citation Audit

Blast-radius counts and concentration per flight-design architect verification (2026-07-03); `.section-title` at components.css:332-352 and the ALL-CAPS strings at status-section.js:32-40 verified by the same review; ordering constraint (`test_token_definitions.py` regex fires on any reference to a deleted token) verified twice (F2 first-pass review; leg-01 design review).

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Update flight-log.md with leg progress entry (incl. per-file counts)
- [x] Set this leg's status to `landed`
- [x] Check off this leg in flight.md
