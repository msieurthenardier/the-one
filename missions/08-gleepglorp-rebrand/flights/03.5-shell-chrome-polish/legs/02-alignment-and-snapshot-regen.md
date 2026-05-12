# Leg: 02-alignment-and-snapshot-regen

**Status**: completed
**Flight**: [Shell Chrome Polish](../flight.md)

## Objective

Closing alignment leg for Flight 3.5 — 10-step ordered close (per the Flight 2 Leg 06 + Flight 3 Leg 07 template). Pre-close grep sweep, WCAG audit, rebuild, playwright dep refresh, snapshot baseline regen, operator HAT × 2 themes × 8 pages, agents.md Mission 08 F3.5 subsection codifying the new shell-chrome vocabulary + the 2 Flight 3 debrief docs carry-forwards, stability re-run, final narrow gate, status + commit.

## Outputs

**`agents.md` Mission 08 F3.5 subsection added** (~75 lines) — codifies:
- The 6 new shell tokens + their dark/light values (`--shell-chamfer`, `--shell-frame-fill`, `--shell-content-fill`, `--shell-frame-glow`, `--shell-chrome-bg`, plus `--bg-gradient` rebinding).
- `color-scheme: dark/light` per theme block for UA chrome (scrollbars) parity.
- Six composition rules: nested-clip L-bracket on `#main-content`, directional inner glow, top-edge content fade-mask via `mask-image`, no `backdrop-filter` on viewport-edge chrome, unified L-shaped chrome housing with sheen on topbar only, body bg matches chrome.
- Cross-cutting structural rules (chrome surfaces drop their separators, section-nav drops border-bottom, sidebar adds 10px top padding).
- Two new affordance vocabulary entries from the Flight 3 debrief carry-forwards: topbar `<img>` CLS contract + legacy class-as-JS-handle pattern.

**Status transitions**: Leg 02 → `completed`; Flight 3.5 → `landed`; mission Flight 3.5 checkbox ticked.

## Acceptance Criteria

- [x] **Pre-close grep sweep clean** — 0 iteration scaffolding leftover; 0 panel-shadow-glow; no surprise nav-bg/sidebar-bg consumers; no hex leaks outside tokens.css/fonts.css.
- [x] **WCAG audit green**: 45/45 in 0.05s. New `--shell-chrome-bg` base colors aren't parametrized in the audit yet — logged as a Flight 3.5 debrief follow-up.
- [x] **`make rebuild` clean** (all assets served).
- [x] **Playwright deps re-installed** (cache wiped by rebuild — same Flight 1 Action Item #4 pattern).
- [x] **Snapshot regen** — 10/12 baselines regenerated cleanly. 2 carried-forward `chat_with_messages` × dark/light failures (Flight 1 Known Issue, `app_with_agent` fixture's `.session-agent-badge` race; deferred to Flight 5 per the mission Known Issues).
- [x] **HAT walkthrough** — operator confirmed both themes × 8 pages clean.
- [x] **`agents.md` Mission 08 F3.5 subsection** added with Flight 3 carry-forward docs folded in.
- [x] **Snapshot stability re-run** without `UPDATE_SNAPSHOTS=1` — 10/12 identical (baselines stable).
- [x] **Final narrow gate** — 56/56 in 0.83s.
- [x] **Flight status** → `landed`; mission Flight 3.5 checkbox ticked.

## Files Modified

- `the_one/agents.md` — Mission 08 F3.5 subsection inserted before `### Color contrast (WCAG AA)`
- `missions/08-gleepglorp-rebrand/flights/03.5-shell-chrome-polish/flight.md` — status `in-flight` → `landed`; both legs + checkpoints ticked
- `missions/08-gleepglorp-rebrand/mission.md` — Flight 3.5 checkbox ticked
- Snapshot baselines regenerated locally (gitignored — not committed)

## Citation Audit

4 citations verified at leg close:
- `agents.md` Mission 08 F3.5 Shell Chrome Polish Layer subsection — verified inserted before `### Color contrast (WCAG AA)` at line ~669.
- `tokens.css` — verified `--shell-chamfer`, `--shell-frame-fill`, `--shell-content-fill`, `--shell-frame-glow`, `--shell-chrome-bg` defined per theme; `--bg-gradient` rebound to `var(--shell-chrome-bg)` in both themes; `color-scheme: dark/light` set per theme block.
- `base.css` — verified `#main-content` nested-clip L-bracket; `#app-topbar` + `#app-sidebar` shared chrome bg; `.content-panel` mask-image; sidebar `padding-top: 10px`; topbar dead `position: relative` removed.
- `components.css` — verified `.section-nav { border-bottom: 0 }` applies to both themes.

All citations clean.
