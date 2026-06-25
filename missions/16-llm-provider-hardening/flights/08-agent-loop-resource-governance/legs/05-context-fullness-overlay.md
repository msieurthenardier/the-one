# Leg: context-fullness-overlay

**Status**: completed
**Flight**: [Agent-loop Resource Governance & Context-budget Management](../flight.md)

## Objective
Make the chat telemetry overlay's context-fullness warning **configurable** (env-tunable
warn/critical thresholds, plumbed to the frontend) and **non-color-only accessible** (a
screen-reader-perceivable state at warn/critical) — the overlay already colors the bar
orange→red as the conversation fills; this leg completes DD2's guardrail without rebuilding
the coloring.

## Context
- **DD2 + architect MEDIUM-2/LOW-1 (binding)**: the orange/red threshold coloring is
  **ALREADY SHIPPED** — `telemetry-overlay.js` computes `stateClass = pct >= 90 ? 'crit'
  : pct >= 70 ? 'warn' : ''` at **:83 and :136**, applied to `.t-ctx-pct` and `.context-bar`
  (`chat.css`). Leg 5's real (and only) work: (a) make the thresholds **config-driven**
  (env override, plumbed to the frontend), and (b) fix the **a11y gap** — the warn/crit
  signal is **color-only**: the overlay container's `aria-label` is the static "Token
  usage" (`:21`), the detail rows are `aria-hidden="true"` (`:57`), and the pct span carries
  no live/text state. Verify-and-keep the coloring; do NOT re-implement it.
- **Codebase facts (verified):**
  - Two update paths set the state class: the initial-data update (`telemetry-overlay.js`
    ~:78-96) and the max-context update (~:126-145). Both must read the configurable
    thresholds.
  - **Frontend config path**: `/api/config` (`api.py:171`) returns `{"dev_mode":…,
    "version":…}`; the app **boot-blocks** on it to populate `window.App.config` before any
    `area.init()` (`app.js:224-239`, fallback `{dev_mode:false, version:'unknown'}`). →
    add the thresholds to `/api/config` and read them off `window.App.config` in the overlay
    (fallback to 70/90 if absent — robust to an old/failed config fetch).
  - **Settings**: env-driven config lives in `the_one/config.py` `settings` (the governor
    leg added env-tunables in its own module; the overlay thresholds belong in `settings` so
    `/api/config` can expose them). Follow the existing `settings` env-var pattern.
  - The container already has `aria-label` (`:21`) — making it DYNAMIC (pct + state phrase)
    is the least-invasive non-color signal; an optional debounced `aria-live="polite"`
    status node is the architect's alternative.

## Inputs
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js` (coloring at :83/:136;
  aria-label at :21; update paths :78-96 / :126-145).
- `the_one/interfaces/web/api.py:171` `/api/config`; `the_one/config.py` `settings`;
  `the_one/interfaces/web/static/js/app.js:224-239` (`window.App.config` boot).

## Outputs
- `settings` gains `context_warn_pct` (default 70) + `context_crit_pct` (default 90),
  env-overridable; validated (0 < warn < crit ≤ 100).
- `/api/config` returns the two thresholds.
- `telemetry-overlay.js` reads the thresholds from `window.App.config` (fallback 70/90) in
  BOTH update paths; coloring otherwise unchanged.
- The overlay exposes a **non-color** warn/critical signal to assistive tech: a dynamic
  `aria-label` (pct + "approaching limit"/"context nearly full") and/or a debounced
  `aria-live="polite"` status — perceivable without color.
- Tests: `/api/config` exposes thresholds + env override; browser test for color + a11y
  state at the (configurable) thresholds.

## Acceptance Criteria
- [x] `settings.context_warn_pct` (70) + `settings.context_crit_pct` (90) exist on the
      `Settings` `BaseSettings` (env prefix `THE_ONE_` → `THE_ONE_CONTEXT_WARN_PCT`/
      `_CRIT_PCT`), and a `@model_validator(mode="after")` CLAMPS invalid values back to
      70/90 when `not (0 < warn < crit <= 100)` and logs a warning (must NOT raise — raising
      crashes boot). Single source of truth; `/api/config` then always emits sane values.
- [x] `/api/config` returns both thresholds; `window.App.config` carries them after boot.
- [x] `telemetry-overlay.js` derives `stateClass` from the config thresholds (fallback
      70/90 when absent) in BOTH update paths (:83 and :136); the existing `.warn`/`.crit`
      coloring on `.t-ctx-pct` + `.context-bar` is preserved (verify-and-keep, not rebuild).
- [x] **Non-color a11y signal**: the overlay container already has `role="status"` (:20);
      make its `aria-label` DYNAMIC — `"Token usage: {pct}% of context"` + `, approaching
      limit` (warn) / `, context nearly full` (crit) — KEEPING "Token usage" as the prefix
      (structure-based locators depend on it). This is the primary non-color signal. An
      `aria-live="polite"` node is optional and, if added, MUST reuse the existing
      `.visually-hidden` class (`chat.css:382`) and update only on warn↔crit TRANSITIONS
      (debounced). Detail rows stay `aria-hidden` (single SR source of truth).
      (Chose the dynamic `aria-label` only; the optional `aria-live` node was not added.)
- [x] Custom env thresholds move the transition point (e.g. warn=50 colors+announces at
      50%); confirmed by a test.
- [x] WCAG 2.1 AA: the warn/crit state is perceivable without color; focus/landmark/labels
      unaffected. (Accessibility reviewer signs off at flight-end review.)
- [x] Browser test (`tests/browser/`, DOM/role — NOT pixel) drives the overlay to ≥warn and
      ≥crit and asserts the state class AND the a11y signal; a unit test covers `/api/config`
      + env override + validation.
- [x] FULL unit suite green at/above the leg-4 baseline (3565 → 3574); `make test-browser` green.

## Verification Steps
- **FIRST**: run `make test-browser` to capture a true green baseline (prior legs only ran
  single browser files — establish full-target green before this leg's work so a latent red
  isn't misattributed here).
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_api_config.py -x --timeout 30`
  (/api/config thresholds + env override + validation — new test file; the endpoint has zero
  coverage today).
- `make test-browser` (overlay color + aria state at default and custom thresholds).
- `make test-unit` once — green.
- Manual: open chat, drive context up; bar goes orange ~70% / red ~90%; a screen reader
  (or the aria-label inspected in devtools) announces "approaching limit"/"nearly full".

## Implementation Guidance
1. **Settings** (`the_one/config.py`, `class Settings(BaseSettings)`). Add
   `context_warn_pct: int = 70`, `context_crit_pct: int = 90` (env binds via the existing
   `THE_ONE_` prefix). Add a `@model_validator(mode="after")` that, when
   `not (0 < warn < crit <= 100)`, resets BOTH to 70/90 and `logger.warning(...)` — clamp,
   never raise (raising would crash boot). This is the only validation site.
2. **`/api/config`** (`api.py:171`). Add the two keys to the returned dict.
3. **Overlay thresholds** (`telemetry-overlay.js`). Read
   `(window.App.config && window.App.config.context_warn_pct) || 70` (and crit || 90) once
   (or per-update); replace the literal `70`/`90` at :83 and :136. Keep the class names and
   coloring identical.
4. **Non-color a11y**. In the update paths, set the container `aria-label` to e.g.
   `Token usage: {pct}% of context` + `, approaching limit` (warn) / `, context nearly full`
   (crit). If using `aria-live`, add a visually-hidden `aria-live="polite"` node updated only
   on state TRANSITIONS (debounce — don't announce every token), to avoid SR spam. Keep the
   detail rows `aria-hidden`.
5. **Tests**. Unit: `/api/config` returns thresholds; env override changes them; invalid
   env falls back. Browser: drive `setTelemetryMax`/telemetry updates to cross warn and crit
   (default and a custom env threshold) and assert `.context-bar.warn`/`.crit` + the
   `aria-label`/live text. Follow existing chat browser-test patterns.

## Edge Cases
- **`max_context_tokens == 0`** (pre-resolution): pct path already guards (`:80-82`); no
  state class, neutral aria-label. Keep.
- **Invalid env (warn≥crit, >100, non-int)**: validate in settings → fallback 70/90 +
  warning; never ship a broken threshold to the client.
- **aria-live chattiness**: announce only on warn/crit state transitions, debounced — not on
  every percentage tick.
- **Old/failed `/api/config`**: `window.App.config` fallback lacks the keys → overlay uses
  the 70/90 default (no crash).
- **Coloring regression**: do NOT alter `.warn`/`.crit` CSS or the class application shape;
  a test asserts the existing coloring still triggers.

## Files Affected
- `the_one/config.py` — `context_warn_pct` / `context_crit_pct` + validation.
- `the_one/interfaces/web/api.py` (`:171`) — expose thresholds in `/api/config`.
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js` — config-driven
  thresholds + non-color aria signal (both update paths).
- `tests/test_api_config.py` (NEW) — `/api/config` thresholds + env override + validation
  (endpoint has zero coverage today).
- `tests/browser/` — overlay color + a11y state at default + custom thresholds.
- `.env.example` (near the governor block, ~:67-79) — `# THE_ONE_CONTEXT_WARN_PCT=70` /
  `# THE_ONE_CONTEXT_CRIT_PCT=90`.
- Docs: the two env vars (warn/crit pct) alongside the governor env vars.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (full unit suite + `make test-browser`)
- [x] Update flight-log.md (thresholds plumbed via /api/config, the non-color a11y signal
      chosen, that coloring was kept-not-rebuilt)
- [x] Set this leg's status to `landed` (commit deferred to flight end)
- [x] Check off this leg in flight.md
- [x] (Not the final leg — do not land the flight here)
