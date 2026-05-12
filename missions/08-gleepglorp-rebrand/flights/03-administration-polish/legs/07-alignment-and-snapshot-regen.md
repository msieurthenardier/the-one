# Leg: 07-alignment-and-snapshot-regen

**Status**: completed
**Flight**: [Administration Polish](../flight.md)

## Objective

Closing alignment leg — execute the 10-step ordered close (per the Flight 2 Leg 06 pattern, adopted as a flight-design template for any flight touching tokens + primitives + snapshots): pre-close grep sweep, WCAG audit, rebuild, playwright dep refresh, snapshot baseline regen, operator HAT × 2 themes × all 8 pages (Admin + Chat + Studio), agents.md codification of new patterns, stability re-run, final narrow gate, status + commit.

## Context

- **Flight 3 introduced 4 new shared primitives + 2 cross-cutting structural rules** that need codification in `agents.md` before flight close: `.banner` + `.code-block` primitives (Leg 03); `confirmLeave(proceed, abort)` hook contract (Leg 06); body-overflow + flex-min-height structural rule (Leg 03); stale-then-guard pattern (Leg 06); chip-list-editor UX rules (Leg 05); topbar 3-button + brand-banner layout (Leg 02); Ollama-LED-consumer wire-up pattern (Leg 04). All documented under a new "Mission 08 Flight 03 Administration Polish Layer" subsection following the F2 precedent.
- **One operator-surfaced retune during HAT**: light-theme code-block contrast (black-bg + warning-orange text was readable in dark but too harsh in light against the page chrome). Solution: theme-aware `--code-block-bg` + `--code-block-fg` tokens. Dark retains terminal aesthetic; light composes `--surface-elevated` (slate-50) + `--fg` (slate-900) — already-audited pair (~17:1, AAA-grade). Mid-leg fix, not deferred.
- **Carried-forward Flight 1 Known Issue**: the `app_with_agent` fixture's `.session-agent-badge` race blocks 2/12 pixel snapshots (`chat_with_messages` × dark + light). Same outcome as Flights 1 and 2 — not a regression; deferred to Flight 5.
- **Playwright cache wiped twice** during the leg by intervening `make rebuild` calls (the named volume survives rebuild but the deps go missing — same pattern flagged in the Flight 1 debrief Action Item #4). Re-installed at steps 4 + post-step-7 to unblock snapshot regen + stability re-run.

## Inputs (pre-leg state)

- Flight 3 Legs 01-06 all committed (`75864da`, `dc20a9a`, `413c8d1`, `0d33bf0`, `416a04b`, `06d4527`).
- `agents.md` Mission 08 F2 Design Language Layer subsection in place (the F3 subsection inserts after it, before `### Color contrast (WCAG AA)`).
- Pixel snapshot baselines unchanged since Flight 2 Leg 06 (no per-leg regen during Legs 01-06; deferred to this closing leg).
- Code-block primitive (from Leg 03) used `#000` bg + `--status-warning` fg unconditionally; light-theme readability gap latent until operator HAT surfaced it.

## Outputs (post-leg state)

### `agents.md` Mission 08 F3 subsection (~80 lines added)

Inserted before `### Color contrast (WCAG AA)`. Documents:

- **New shared primitives**: `.banner` (3 variants — error/warning/info) with the lifted-from-`.action-blocked-message` shape; `.code-block` theme-aware via tokens (dark terminal aesthetic preserved, light gets AAA-grade legibility).
- **New cross-area contract**: `confirmLeave(proceed, abort)` hook on the area descriptor; consumed by `app.js switchTo()` before cross-area deactivation; admin implements it via `self._confirmLeaveImpl` closure on `dirty` flag. Covers topbar clicks, browser back/forward, direct hash typing uniformly.
- **Cross-cutting structural rules**: `body { overflow: hidden }` + `min-height: 0` flex-column chain (root cause + fix for body-level scrollbar pathology); stale-then guard for `area.activate()` async fetches (consumed by `populateProviderGrid` + `selectTool`).
- **New affordance vocabulary entries**: chip-list-editor UX (Tab/click-to-insert-before/Backspace-aware + `--accent` rest `.chip-remove`), topbar 3-flat-button + brand-banner layout, Ollama lifecycle `.indicator-led` consumer pattern.

### Light-theme code-block retune (operator-surfaced)

- **New tokens** in `tokens.css`: `--code-block-bg` + `--code-block-fg` per theme.
  - Dark: `--code-block-bg: #000` + `--code-block-fg: var(--status-warning)` (terminal aesthetic preserved)
  - Light: `--code-block-bg: var(--surface-elevated)` (slate-50) + `--code-block-fg: var(--fg)` (slate-900) — composes already-audited pair (~17:1, AAA)
- **`.code-block` rule** in `components.css`: consumes tokens + `border: 1px solid var(--border)` for "code well" framing in both themes (subtle in dark, more visible in light).

### Snapshot baselines

- 10/12 regenerated cleanly via `UPDATE_SNAPSHOTS=1 pytest -m pixel`.
- 2 `chat_with_messages` failures carried from Flight 1 Known Issue (`app_with_agent` fixture's `.session-agent-badge` race).
- Stability re-run without `UPDATE_SNAPSHOTS=1`: identical 10/12. Baselines stable.

### Status transitions

- Leg 07 status: `planning` → `completed` (this artifact).
- Flight 3 status: `in-flight` → `landed`.
- Mission 08: Flight 3 checkbox ticked.

## Acceptance Criteria

- [x] **Pre-close grep sweep clean** — `panel-shadow-glow` 0 hits; `admin-pf-model-dot` only the comment marker; `linear-gradient(to bottom` 0 in components.css; no hex literals outside tokens.css
- [x] **WCAG audit green**: 45/45 (twice — once pre-rebuild + once post-code-block-retune; no contrast changes)
- [x] **`make rebuild` clean** (twice — once after Leg 06 + once after code-block retune)
- [x] **Playwright deps re-installed** (twice — cache-wipe behavior matches Flight 1 debrief Action Item #4)
- [x] **Snapshot regen** — 10/12 baselines regenerated; 2 carried-forward Known Issue failures
- [x] **HAT walkthrough** — operator confirmed both themes × 8 pages (Chat / Studio / Admin × 4 sub-routes / Design Language)
- [x] **`agents.md` Mission 08 F3 subsection** added (~80 lines) documenting new primitives + hook + structural rules + affordance vocabulary
- [x] **Snapshot stability re-run** — 10/12 stable on rerun without `UPDATE_SNAPSHOTS=1`
- [x] **Final narrow gate** — 56/56 in 1.31s
- [x] **Flight status** → `landed`; mission Flight 3 checkbox ticked

## Files Modified

- `the_one/interfaces/web/static/css/tokens.css` — `--code-block-bg` + `--code-block-fg` per-theme tokens added
- `the_one/interfaces/web/static/css/components.css` — `.code-block` rule consumes tokens + adds 1px border
- `the_one/agents.md` — Mission 08 F3 subsection inserted (~80 lines)
- `missions/08-gleepglorp-rebrand/flights/03-administration-polish/flight.md` — status `in-flight` → `landed`; all 7 legs + 7 checkpoints ticked
- `missions/08-gleepglorp-rebrand/mission.md` — Flight 3 checkbox ticked
- Snapshot baselines under `tests/browser/__snapshots__/` regenerated locally (gitignored per project convention — not committed)

## Citation Audit

5 citations verified against current code at leg close:

- `tokens.css` per-theme blocks — verified: `--code-block-bg` + `--code-block-fg` defined in both, dark uses `#000` + `var(--status-warning)`, light uses `var(--surface-elevated)` + `var(--fg)`.
- `components.css .code-block` — verified: `background: var(--code-block-bg); color: var(--code-block-fg); border: 1px solid var(--border);` + existing padding/radius/mono/overflow rules preserved.
- `agents.md` Mission 08 F3 Administration Polish Layer subsection — verified inserted before `### Color contrast (WCAG AA)`.
- `flight.md` status — verified `landed`.
- `mission.md` Flight 3 entry — verified `[x]`.

All citations clean. No mirror updates needed (theme-aware tokens compose existing audited pairs).
