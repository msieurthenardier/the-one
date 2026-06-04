# Flight Log: Mission-11 UI Accessibility Pass

**Flight**: [Mission-11 UI Accessibility Pass](flight.md)

## Summary
In progress. Three legs bringing the M11 connector-editor UI to WCAG Level-A operability + AA/AAA cleanup: L1 (A2 keyboard reorder via focusable handle + arrow keys, A3 named toggle), L2 (A1 live-status announcements, A4 presence labels), L3 (A5 section headings, A6 dropdown focus contrast, A7 reduced-motion). Plus a Witnessed behavior test for the keyboard-reorder + status-announcement flow, run after the legs land.

---

## Leg Progress

### Leg 01 — keyboard-reorder-and-toggle-name (2026-06-04)

**Files changed:**
- `connector-editor.js`: drag handle `role="button"` dropped; `tabindex="0"` + `aria-label="Reorder rule — use Arrow keys to move"` added. Persistent live region `<span class="visually-hidden" aria-live="polite" data-routing-live-region>` injected once into `renderRoutingRulesSection`. `_wireRoutingKeyboardReorder` added to `wireRoutingRulesEvents`: ArrowUp/ArrowDown with `preventDefault`, inline DOM mutation via `insertBefore` (mirrors drag path), `checkDirty()`, `handle.focus()` after swap, live-region text "Rule moved to position N of M" or "Rule is already first/last" at boundaries.
- `connectors-tab.js`: attach/enable toggle checkbox gets `aria-label="Attach <account.name>"` (A3 fix, mirrors "Always listen" pattern).
- `studio.css`: `:focus-visible` ring on `.connector-routing-drag-handle` (2px solid `--accent` + 3px `--accent-glow` shadow, matching studio input focus style).
- `tests/browser/test_flow_studio_connector_editor.py`: added `test_routing_rules_keyboard_reorder` (focus handle → ArrowDown → assert order changed + focus retained on moved handle + persistence after save) and `test_attach_toggle_accessible_name` (agent Connectors tab → tile visible → toggle aria-label = "Attach <name>").

**Test result:** `pytest -m browser tests/browser/test_flow_studio_connector_editor.py` — 22 passed (20 pre-existing + 2 new), 0 failed.
**Ruff:** `ruff check` and `ruff format --check` → clean.
**Rebuild:** `make rebuild` succeeded; container serving new JS/CSS confirmed.

### Leg 02 — live-region-and-labels (2026-06-04)

**Files changed:**
- `connector-editor.js`: `aria-live="polite"` added to the `connector-live-status-text` span (~2064); `role="alert"` added to the `connector-live-status-error-wrap` div (~2068). Both attributes land on the rendered-once, mutated-in-place nodes — no structural change. (Opportunistic) `aria-live="polite"` added to the `connector-test-message` span (~2094, Validate/doctor-probe row).
- `connector-form-discord.js`: presence-type `<select>` given `id="cf-discord-presence-type"` with a matching `<label for>` ("Activity type", visually-hidden); presence-name `<input>` given `id="cf-discord-presence-name"` with a matching `<label for>` ("Activity name", visually-hidden). No id collision with the existing `cf-discord-bot-token`. "Bot status" group label retained unchanged.
- `tests/browser/test_flow_studio_connector_discord_form.py`: added `test_presence_controls_have_accessible_names` (asserts `id`/`<label for>` wiring on both presence controls via DOM evaluation) and `test_live_status_region_aria_attributes` (asserts `aria-live="polite"` on the status text span and `role="alert"` on the error wrap via DOM evaluation).

**Test result:** `pytest -m browser tests/browser/test_flow_studio_connector_discord_form.py` — 12 passed (10 pre-existing + 2 new), 0 failed.
**Ruff:** `ruff check` and `ruff format --check` → clean.
**Rebuild:** `make rebuild` succeeded; container serving new JS confirmed.

### Leg 03 — headings-contrast-motion (2026-06-04)

**Files changed:**
- `connector-editor.js`: all 10 `section-title` `<div>`s promoted to `<h2>` — Connection (365), Credentials (385), Session (404), Discord (618), Danger Zone (655, retains `danger-zone-title` class), Pairing (2130), Direct Messages (2232), Servers (2338), Routing (2568), Attached agents (3141). Single `<h1>` editor title at ~323 unchanged.
- `studio.css`: `.discoverable-dropdown-item--focused` given `outline: 2px solid var(--accent); outline-offset: -2px` (A6 focus indicator ≥3:1 vs `--surface`, visually distinct from `:hover`). All 13 `0.15s` transition literals replaced with `var(--motion-fast)`; both `0.2s` `.tool-switch` literals replaced with `var(--motion-medium)` (A7 reduced-motion compliance).
- `tokens.css`: `--motion-medium: 200ms` added to dark theme block, light theme block, and `prefers-reduced-motion` zeroing block. Behavior-preserving — duration unchanged, now token-driven.
- `tests/browser/test_flow_studio_connector_editor.py`: added `test_connector_editor_section_titles_are_h2` (edit-mode: asserts `h1` count=1, `h2.section-title` for Connection/Credentials/Session/Danger Zone, `div.section-title` count=0).

**Out-of-scope residuals (noted for follow-up):**
- A5-remainder: `section-title` `<div>`s in `general-tab.js`, `provider-editor.js`, `mcp-server-editor.js`, `tools-editor.js`, `system-page.js`, `history-buckets.js` — 6 files, not fixed this flight.
- A7-remainder: `components.css` hardcoded transition literals — not touched.

**Test result:** `pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py` — 48 passed, 0 failed. `pytest -m browser tests/browser/test_flow_studio_connector_editor.py` — 23 passed (22 pre-existing + 1 new), 0 failed.
**Ruff:** `ruff check` and `ruff format --check` → clean.
**Rebuild:** `make rebuild` succeeded; container serving new JS/CSS confirmed.

---

## Flight Director Notes

### 2026-06-04 — Flight start
- Invoked via `/agentic-workflow` for `the-one` mission 12, flight 04 (M11 UI Accessibility Pass). Branched `flight/04-m11-accessibility-pass` off `main` (Flights 01–03 merged; main at 01ba286).
- Loaded phase file `.flightops/agent-crews/leg-execution.md`. **UI flight → the optional Accessibility Reviewer (Sonnet) joins the Reviewer in code review.** Developer spawns pinned to `model: sonnet`; Reviewers never Opus.
- **Open question resolved — A2 = focusable handle + arrow keys** (operator). Give the handle `tabindex=0` + ArrowUp/Down keydown reorder + visually-hidden live region for the new position; make `role="button"` genuinely operable. Keep drag for mouse; shared reorder logic.
- **Behavior test = author + run this flight** (operator), per the flight's regression-gate note. Spec authored inline during planning (Witnessed Executor+Validator), run via `/behavior-test` after the 3 legs land; needs the live app (container up, `THE_ONE_DEV_MODE=true` confirmed) + chrome-devtools.
- **No line drift:** Flight 02's ruff reformat touched only `.py`; the JS/CSS line refs in these legs are intact (A2 handle confirmed at `connector-editor.js:2511-2516`).
- Three legs touch overlapping files (`connector-editor.js` in all three; `studio.css` in L1+L3) → **design-review in parallel (read-only), implement sequentially** to avoid edit races. Flight `ready` → `in-flight`.

### 2026-06-04 — Leg design reviews (3× Developer agents, Sonnet, parallel) + revisions
All three approve-with-changes; revisions applied (no new scope → no second cycles):
- **Leg 1 (A2/A3) [high×2]:** there is NO shared reorder function — the drag path mutates the DOM via `insertBefore` + `checkDirty()` and `collectRoutingFromContainer` reads DOM order; the keydown handler must replicate that inline (use live `querySelectorAll` + `indexOf`, not the stale `data-row`). And `insertBefore` drops focus → **must `handle.focus()` after the swap** (added as named AC). Live region must be injected once into `renderRoutingRulesSection` (reuse `.visually-hidden` from `admin.css:505`); boundary = announce "already first/last" not `disabled`; drop the misleading `role="button"`; keep `<span>`+`tabindex` (not `<button>` — FF `draggable` issues). Test file corrected to `test_flow_studio_connector_editor.py` (model on `test_routing_rules_drag_reorder` ~527).
- **Leg 2 (A1/A4) [med]:** live nodes confirmed to persist across polls (created once, mutated in place) → just add attributes. `aria-live="polite"` on the **text span**, NOT the wrap div (which holds the LED whose aria-label churns each poll). `role="alert"` on the error wrap (more reliable than assertive for hidden→revealed). Presence ids `cf-discord-presence-type`/`-name` (no collision).
- **Leg 3 (A5/A6/A7) [high×2]:** A5 **scoped to connector-editor.js only** (flight scope) — but include the omitted "Danger Zone" title at ~655 (10 sites, not 9); app-wide `section-title` divs in 6 other files = out-of-scope A5-remainder. A7: the two `0.2s` `.tool-switch` literals match no token (fast=150/base=250) → **add `--motion-medium: 200ms`** (token route, behavior-preserving); `components.css` literals = out-of-scope residual. `.section-title` rule is in `components.css:333` and sets font explicitly → div→h2 visually identical, no reset. A6 outline `2px solid var(--accent)` (already ≥3:1 per the a11y token test).
- Proceeding: author the behavior-test spec, then implement L1→L2→L3 (sequential), `model: sonnet`.

### 2026-06-04 — Code review (Reviewer=Haiku + Accessibility Reviewer=Sonnet, parallel) → confirmed
- UI flight, so both reviewers ran. **Reviewer [HANDOFF:confirmed]**: all 3 legs meet acceptance criteria; scope clean (only the expected JS/CSS + tests + behavior spec; no other files' section-titles touched); ruff 0; token tests 48 passed. **Accessibility Reviewer [HANDOFF:confirmed]**: full WCAG pass — A1–A7 all PASS, no new regressions (no keyboard trap, focus retention verified, heading order `<h1>`→10×`<h2>` clean, reduced-motion incl. `--motion-medium` zeroed). Two cosmetic non-blocking notes accepted as-is: a duplicate `--focused` selector in studio.css (works), and a pre-existing one-poll stale-error-content quirk (not introduced here).
- Single review cycle, no fixes required.

### 2026-06-04 — Behavior test: connector-editor-keyboard-a11y → PASS
- Ran `/behavior-test connector-editor-keyboard-a11y` after the legs landed + container rebuilt. Run log: `tests/behavior/connector-editor-keyboard-a11y/runs/2026-06-04-19-52-56.md`. **8/8 judged steps pass, 0 fail** (step 2 setup; step 9 optional error-stub skipped). A2 (keyboard reorder + focus retention + position/boundary announcements) and A1 (live-status SR plumbing) verified Witnessed-style.
- Spec promoted draft→active; non-blocking nav-name correction applied ("Advanced // ROUTING" vs "Access-and-Routing").

---

## Decisions

### Behavior-test run adapted to a consolidated Executor pass (re-spawn mode)
**Context**: `SendMessage` live continuation unavailable this session; the keyboard-reorder flow is stateful and cold-reload-per-spawn would reset in-DOM order + wipe the unsaved fixture rules.
**Decision**: Run the whole interactive flow in one Executor turn, judged by one independent Validator, rather than strict per-row re-spawn.
**Impact**: Witnessed independence preserved; reliable for a stateful UI flow. Noted as the active mode in the run log.

### Behavior-test fixture left the live connector untouched
**Context**: Operator chose to run on the real "Discord Constellation" connector (which had 0 routing rules; spec needs ≥3).
**Decision**: Add the 3 fixture rules via the UI but **never save**; discard on exit.
**Impact**: Persisted config stayed at 0 rules (verified pre + post via DB) — no live-data mutation, restore guaranteed by construction (nothing was persisted).

---

## Deviations

_None affecting code. A5/A7 were bounded to the connector editor + studio.css per the flight scope; broader surfaces deferred — see Anomalies._

---

## Anomalies

### Out-of-scope a11y residuals (deferred follow-ups)
**Observed**: `section-title` `<div>`s exist in 6 other studio JS files (general-tab, provider-editor, mcp-server-editor, tools-editor, system-page, history-buckets) — A5 was scoped to `connector-editor.js`. `components.css` carries hardcoded transition literals not covered by the A7 token swap (studio.css only).
**Severity**: advisory (same WCAG findings, other surfaces)
**Resolution**: Deferred as **A5-remainder / A7-remainder** for a future pass — flagged for the flight debrief; not fixed in this maintenance flight.

---

## Session Notes
