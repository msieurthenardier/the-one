# Leg: vocabulary-core

**Status**: completed
**Flight**: [Shell and Shared Components](../flight.md)

## Objective

Rebuild the core component vocabulary in components.css on the v3 tokens — buttons, form fields (incl. the shared `.field-select` styling + chat agent-select seam touch), tabs (deleting the last chamfer + its guard allowance), tiles/cards, and table/list treatment — migrate all 35 `--panel-radius*` consumer refs (+ delete the 4 alias definitions), and re-author the corresponding design-gallery sections.

## Context

Parent flight DDs are authoritative: "Component vocabulary conventions", "Dropdown (a) + chat seam", "Tabs without the L-bracket", "Guard bookkeeping" (delta 2: `CLIP_PATH_POLYGON_ALLOWANCE` deletes here). Verified citations: tab `::before` chamfer block at `components.css:~756-769` (selected via `.tab[aria-selected="true"]`); chat select at `chat.js:138` (`class="agent-select"`) + bespoke rules `chat.css:29-31`; panel-radius refs components 14 / chat 7 / admin 7 / studio 7 + 4 defs in tokens.css.

## Outputs

- components.css: button variants (primary/secondary/ghost/danger — 32px, `--radius-sm`, flat fills, pinned focus; one primary per region documented); field styles (label-above, inline validation classes, `.field-select` shared styling); tabs (chamfer `::before` deleted; selected = 2px accent bottom-border keyed off `aria-selected`; hover = fg shift); tiles/cards (surface + hairline + `--radius-md`; hover `--border-hover`; selected accent border); table/list rows (40-44px, hairline separators only, hover surface shift)
- chat.js:138 gains `field-select` class; `chat.css:29-31` bespoke select rules deleted (justified diff)
- All `var(--panel-radius)`/`var(--panel-radius-sm)` → `var(--radius-sm)`/`4px→--space-1`-appropriate mapping (35 refs, four files); alias definitions deleted from tokens.css both themes; mirror unaffected (aliases unmirrored)
- `tests/test_ui_guards.py`: `CLIP_PATH_POLYGON_ALLOWANCE["components.css"]` entry deleted (guard demands it once the polygon goes)
- Gallery: buttons-section.js, fields-section.js, tabs-section.js, surfaces-section.js re-authored to showcase the new vocabulary (createElement only — no sink diffs)

## Acceptance Criteria

- [x] `grep -E "clip-path|--panel-radius" the_one/interfaces/web/static/css/*.css` → zero
- [x] Guard/token/a11y slice green (`tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -x --timeout 60`) — allowance removal verified by the guard itself (93 passed)
- [x] Both themes visually verified on 8485 (gallery + one real surface per component family); focus states evidenced via CDP page per doctrine
- [x] Keyboard: tabs remain arrow-key operable; selects focusable with pinned focus ring [a11y gate]
- [x] `make test-unit` green (3721 passed); targeted browser slice green (`test_flow_admin_tools_editor.py test_studio_mcps_tab.py test_flow_hash_routing.py` via run-tests.sh -m browser -x --timeout 180 — 34 passed)
- [x] ruff clean; registry/sink guards green (expected diffs: none for testids; sink baseline unchanged; chat.js diff justified in flight log)

## Implementation Guidance

1. Work components.css family by family; adopt `--space-*` where literals map exactly.
2. Tab treatment: delete the `::before` block wholesale; add the bottom-border selected rule; verify no layout jump (reserve the 2px with transparent border on unselected).
3. panel-radius: mechanical sed-able migration; verify each file's count to zero.
4. Gallery sections: mirror the real component classes — the gallery IS the acceptance surface.

## Edge Cases

- A component family styled differently per-area (found during work): normalize into components.css; leave a flight-log note (SC3 evidence).
- Tabs used outside expected markup: grep `role="tab"` first.

---

## Citation Audit

All citations verified by the F3 first/second-pass architect reviews (2026-07-03, same day).

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Flight-log entry (incl. per-file panel-radius zeroing + justified JS diffs)
- [x] Leg status `landed`; checked off in flight.md
