# Leg: 06-retune-accent-api-and-alignment

**Status**: landed
**Flight**: [Design Language — Glass + Control Panel](../flight.md)

## Objective

Closing leg. Execute the 10-step ordered close: retune `--accent-api` in aesthetic context, mirror to Python a11y if values changed, three-dimensional grep sweep, WCAG audit, `make rebuild`, `make _ensure-playwright`, regenerate visual snapshot baselines, walk operator through HAT, codify the Mission 08 F2 Design Language Layer in `agents.md`, run a stability re-run on the snapshots.

## Type

Mixed: autonomous steps 1-7 + 9-10; interactive step 8 (HAT).

## 10-Step Close Sequence

1. **`--accent-api` retune** → **No change**. Resolution: the aesthetic justifies keeping the recycled-cyan values (`#22d3ee` dark / `#0e7490` light). Teal complements violet, distinguishes "data channel" semantics from primary brand, already audited (3 parametrizations from Flight 1 Leg 02). The flight artifact's open question is closed with "keep as-is."
2. **Python a11y mirror** → No change needed (no token value changed).
3. **Three-dimensional grep sweep** → Clean. `grep -E '#[0-9a-fA-F]{3,6}\b' tokens.css` returns 82 hits — ALL legitimate token values, no stale brand-aligned hex. `grep -rIn -i 'teal\|cyan\|nexus' agents.md CLAUDE.md interfaces/web/static/css/` returns only properly-annotated historical context (tokens.css retune narrative at the top of file, CLAUDE.md:89, agents.md retune story) plus one intentional non-brand cyan token (`--badge-filesystem: #008b8b` for the filesystem tool category badge). No cleanup needed.
4. **WCAG audit** → `pytest tests/test_design_tokens_a11y.py -v` → 45 passed in 0.06s. All load-bearing contrast pairs continue to meet AA.
5. **`make rebuild`** → `verify-serving` confirmed all 19 admin sub-modules served (200), including the 9 design-language section modules added in Leg 02.
6. **`make _ensure-playwright`** → Chromium browser cache restored after rebuild (named volume survives rebuild but deps get wiped).
7. **`UPDATE_SNAPSHOTS=1 pytest -m pixel`** → 10/12 baselines regenerated cleanly. The 2 failures (`chat_with_messages` × dark + light) are the **pre-existing Flight 1 Known Issue** — `app_with_agent` fixture's `.session-agent-badge` populates empty due to a seeder/auto-session-join race in `chat.js`. Matches Flight 1's outcome exactly; deferred to Flight 5 (Chat Response Trace) which will touch the same code path.
8. **HAT walkthrough** → Operator surveyed both themes across Chat / Studio / Admin / Design Language gallery / popover / modal. Operator: "I think we're good for this flight." No tactical fixes surfaced. Vibe legs' cumulative result holds.
9. **`agents.md` Mission 08 F2 Design Language Layer** → ~75-line subsection inserted before `### Color contrast (WCAG AA)`. Documents the new token catalog (12 glass / bezel / motion tokens), composition rules (full-glass vs mini-glass vs input-recessed, asymmetric in/out motion, glass + panel-shadow-glow substitution), button-family V3b treatment supersession of M04 pattern #2, and new vocabulary entries for `.checkbox-primary`, `.indicator-led`, `.telemetry-strip`, `.chip` retune. Existing `### Affordance patterns` section preserved as the M04 layer documentation.
10. **Stability re-run** → `pytest -m pixel` (no UPDATE_SNAPSHOTS) → 10/12 stable. Same 2 pre-existing failures. Narrow gate: 56 passed in 0.86s.

## Acceptance Criteria

- [x] `--accent-api` decision made (keep — no retune needed)
- [x] Python a11y mirror current
- [x] Three-dimensional grep sweep clean
- [x] WCAG audit green (45 parametrizations pass)
- [x] `make rebuild` clean (`verify-serving` 200 across all 19 admin sub-modules)
- [x] Playwright Chromium re-installed
- [x] 10/12 visual snapshot baselines regenerated and stable on re-run (2 blocked by Flight 1 Known Issue)
- [x] HAT walkthrough complete; operator confirmed
- [x] `agents.md` Mission 08 F2 Design Language Layer subsection added (~75 lines, real reference section)
- [x] Narrow test gate green: 56 passed
- [x] Flight log updated with leg progress entry; leg status set to `landed`

## Files Affected

- `the_one/agents.md` — new `### Mission 08 Flight 02 — Design Language Layer (glass + bezel + motion)` subsection inserted before `### Color contrast`
- `missions/08-gleepglorp-rebrand/flights/02-design-language/flight.md` — checkpoints ticked, status to `landed`
- `missions/08-gleepglorp-rebrand/flights/02-design-language/flight-log.md` — leg 06 progress entry
- `missions/08-gleepglorp-rebrand/flights/02-design-language/legs/06-retune-accent-api-and-alignment.md` — this artifact
- `missions/08-gleepglorp-rebrand/mission.md` — flight checkbox ticked (handled at flight close)
- `tests/browser/__snapshots__/` — 10 visual snapshot baselines regenerated locally (gitignored per user-global convention)

---

## Post-Completion Checklist

- [x] All 10 close steps executed
- [x] Operator HAT-confirmed
- [x] WCAG audit + narrow gate green
- [x] Snapshot baselines regenerated (10/12 — 2 by Flight 1 Known Issue)
- [x] agents.md updated
- [x] Leg status `landed`
- [x] Flight log updated
