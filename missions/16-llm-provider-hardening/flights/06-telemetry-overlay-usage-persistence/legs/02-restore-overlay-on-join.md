# Leg: restore-overlay-on-join

**Status**: completed
**Flight**: [Telemetry Overlay Usage Persistence](../flight.md)

## Objective

In the `chat.js` `session_joined` handler, restore the persisted
`session_metadata.last_usage` snapshot into the telemetry overlay (the
`used / max` numbers + the fullness bar) and change the async `/context-window`
seed to be **max-only** so it no longer re-zeros the restored used-counts.

## Context

- **DD4** — the `session_joined` handler runs `resetTelemetry(content)`
  (`chat.js:910`), then fires an **async** `/context-window` fetch whose `.then`
  calls `updateTelemetry` with `input/output/context_tokens: 0` + the real `max`
  (`chat.js:946-951`). That async callback resolves *after* the handler returns and,
  as written, **re-zeros** any restored snapshot. The fix: (a) restore `last_usage`
  **synchronously** in the handler (before the async seed can resolve), and (b) make
  the async seed update **only** `max_context_tokens` so it can't clobber the restore.
- **DD3** — the overlay is **absolute-set / per-turn**. `updateTelemetry`
  (`telemetry-overlay.js:74-92`) overwrites all four displayed values and recomputes
  the bar from `context_tokens / max_context_tokens`. There is **no retained raw
  state** — the only persisted values live in DOM text, which is lossy
  (`fmtTokens` renders `1234 → "1.2k"`). A max-only seed that must recompute the bar
  therefore needs the raw `context_tokens`, so this leg adds lightweight raw-state
  retention on the overlay element.
- The backend already surfaces the snapshot: `_build_session_joined_ok` carries
  `session.session_metadata` (`app.py:1068`) and `_build_session_joined_degraded`
  carries `db.session_metadata` (`app.py:1097`). After L01, both the in-memory
  `session.session_metadata` and the DB column contain `last_usage`, so **no backend
  payload change is needed** — this leg asserts the carry at the payload level and
  does the frontend restore.
- Depends on **L01** (writes `last_usage`). L03 verifies the full restart round-trip
  + the restored DOM via Playwright.

## Inputs

What exists before this leg runs:
- L01 landed: `last_usage` is written to `session_metadata` (DB + in-memory).
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js` —
  `updateTelemetry` (`:74`), `resetTelemetry` (`:96`), exports at `:109-112`.
- `the_one/interfaces/web/static/js/areas/chat.js` — the `session_joined` handler
  (`:895`), `resetTelemetry` call (`:910`), routing-panel restore precedent reading
  `data.session_metadata.routing` (`:915`), the async `/context-window` seed
  (`:942-954`).
- Join-payload builders `_build_session_joined_ok` (`app.py:1048`) /
  `_build_session_joined_degraded` (`app.py:1072`), both carrying `session_metadata`.

## Outputs

What exists after this leg completes:
- `telemetry-overlay.js` gains a `setTelemetryMax(chromeContent, maxContextTokens)`
  function (max-only update that recomputes the bar from retained `context_tokens`),
  exported on `window.App.chat`. `updateTelemetry` retains its raw input values on the
  element; `resetTelemetry` clears the retained state.
- `chat.js` `session_joined` restores `last_usage` synchronously into the overlay and
  the async `/context-window` callback calls `setTelemetryMax` (no zeroed used-counts).
- A unit test asserting the join payload carries `session_metadata.last_usage`.

## Acceptance Criteria
- [x] On `session_joined`, when `data.session_metadata.last_usage` is present, the
      overlay's `.t-in` / `.t-out` / `.t-ctx` show the restored values (not `0`) and
      the `.context-bar` / `.t-ctx-pct` reflect `context_tokens / max` once the max
      seed resolves.
- [x] The async `/context-window` callback **no longer passes zeroed used-counts** —
      it updates only `max_context_tokens` (and recomputes the bar from the retained
      `context_tokens`), so there is **no async re-zero race**.
- [x] When `data.session_metadata.last_usage` is **absent** (fresh session), behavior
      is unchanged: overlay shows `0` used and the seeded `max`.
- [x] `updateTelemetry` remains absolute-set for the live `usage` event path (its
      existing callers are unaffected); the raw-state retention is additive.
- [x] A unit test asserts **both** `_build_session_joined_ok` **and**
      `_build_session_joined_degraded` surface `session_metadata.last_usage` when the
      source carries it (both are cheap builder-level assertions; the full restart
      round-trip through `_restore_session` remains L03's scope).
- [x] No backend payload shape change (the builders already carry `session_metadata`).

## Verification Steps
- Payload assertion: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_session_joined_payload.py -x --timeout 30` (new file — see step 4) — a
  `Session` with `session_metadata={"last_usage": {...}}` produces a
  `_build_session_joined_ok` payload whose `session_metadata.last_usage` equals the
  snapshot, and the degraded builder carries it too.
- Frontend behavior (max-only seed, restore, no-snapshot fallback) is exercised by
  **L03's Playwright browser flow** + the HAT — this repo has **no JS unit harness**
  (frontend is tested via `tests/browser/`, Python-driven Playwright). Do not add a
  JS-only test framework for this leg.
- Manual smoke (optional, during dev): reopen a chat with a prior turn → overlay shows
  the last turn's in/out/ctx and the bar fills; reopen a fresh chat → overlay shows 0.
- Regression: full unit suite still green at/above the F5 baseline.

## Implementation Guidance

1. **Add raw-state retention + a max-only updater to `telemetry-overlay.js`.**
   - In `updateTelemetry`, after it mutates the DOM, stash the raw inputs on the
     element so a later max-only update can recompute the bar without re-parsing
     formatted DOM text: e.g. `chromeContent.__telemetry = { input_tokens:
     data.input_tokens, output_tokens: data.output_tokens, context_tokens:
     data.context_tokens, max_context_tokens: data.max_context_tokens || 0 };`. This
     is purely additive — the existing DOM writes and the absolute-set contract are
     unchanged.
   - In `resetTelemetry`, clear the retained state to zeros (mirror the DOM reset):
     `chromeContent.__telemetry = { input_tokens: 0, output_tokens: 0, context_tokens:
     0, max_context_tokens: 0 };`.
   - Add `function setTelemetryMax(chromeContent, maxContextTokens)` **inside the
     IIFE** (so the module-private `fmtTokens` is in scope — place it next to
     `resetTelemetry`, before the `window.App.chat.*` export block at
     `telemetry-overlay.js:109-112`; defining it after the closing `})();` at `:113`
     would break the `fmtTokens` reference). It: reads the retained `context_tokens`
     (`var t = chromeContent.__telemetry || {}; var ctx = t.context_tokens || 0;` —
     the `|| {}` fallback covers the unreachable-in-practice case where neither
     `updateTelemetry` nor `resetTelemetry` has run yet, since `resetTelemetry` always
     runs first in the join handler), sets `.t-max` text via `fmtTokens(maxContextTokens
     || 0)`, recomputes `pct = maxContextTokens > 0 ? Math.min(100, Math.round(ctx /
     maxContextTokens * 100)) : 0`, applies the same `stateClass` (`pct >= 90 'crit' :
     pct >= 70 'warn' : ''`) to `.t-ctx-pct` and `.context-bar`, sets the bar width,
     and updates the retained `max_context_tokens`. It must **not** touch `.t-in` /
     `.t-out` / `.t-ctx`. Reuse the exact pct/stateClass logic from `updateTelemetry`
     (`telemetry-overlay.js:80-89`) so the bar is identical.
   - Export it alongside the others: `window.App.chat.setTelemetryMax =
     setTelemetryMax;`.

2. **Restore `last_usage` synchronously in the `session_joined` handler (`chat.js`).**
   - After `App.chat.resetTelemetry(content)` (`chat.js:910`) and the
     `renderHistory` call, read the snapshot the same defensive way the routing panel
     reads its key (`chat.js:915`): `var lastUsage = (data.session_metadata &&
     data.session_metadata.last_usage) || null;`.
   - If present, restore synchronously:
     `App.chat.updateTelemetry(content, { input_tokens: lastUsage.input_tokens || 0,
     output_tokens: lastUsage.output_tokens || 0, context_tokens:
     lastUsage.context_tokens || 0, max_context_tokens: 0 });` — the `max` is still
     unknown here (the seed resolves it shortly); the bar shows 0% for the brief
     interval until the max-only seed runs, then fills.

3. **Make the async `/context-window` seed max-only (`chat.js:942-954`).**
   - Replace the `updateTelemetry(content, { input_tokens: 0, output_tokens: 0,
     context_tokens: 0, max_context_tokens: payload.max_context_tokens })` call inside
     the `.then` with `App.chat.setTelemetryMax(content, payload.max_context_tokens);`.
   - This eliminates the re-zero entirely: the seed now only sets `max` and recomputes
     the bar from the retained `context_tokens` (restored or live), so it is race-free
     w.r.t. both the synchronous restore **and** any live `usage` event that may have
     arrived first.

4. **Add the payload-level unit test(s).**
   - Create `tests/test_session_joined_payload.py` (no existing module asserts the
     `session_metadata` carry — `test_ws_responsiveness.py`,
     `test_session_registry_lock_unification.py`, and `test_app_pending_approval_merge.py`
     import `_build_session_joined_*` but only assert other fields; follow their import
     pattern for the builders).
   - Construct a `Session` with `session_metadata = {"last_usage": {"input_tokens": …,
     "output_tokens": …, "context_tokens": …}}`, call `_build_session_joined_ok(session)`,
     and assert the returned payload's `session_metadata["last_usage"]` equals the
     snapshot.
   - Add the symmetric one-liner for `_build_session_joined_degraded` (it passes
     `db.session_metadata` directly — construct/restore a `RestoredSession` whose
     `db.session_metadata` carries `last_usage` and assert the payload carries it).
     These are cheap builder-level assertions; the **real restart round-trip** through
     `_restore_session` (drop in-memory session → DB reload) stays L03's scope.

## Edge Cases
- **No `last_usage` key** (fresh session, or pre-L01 sessions): `lastUsage` is `null`;
  skip the synchronous restore; the max-only seed sets `max` with the retained
  context_tokens at 0 → overlay shows `0 / max`. Unchanged behavior.
- **`session_metadata` is `null`** in the payload: the `(data.session_metadata &&
  …)` guard yields `null` → no restore. Safe.
- **`/context-window` fetch fails** (404/400/network): the `.catch` leaves `max` at 0
  (current behavior); the restored used-counts still display, the bar stays at 0%
  until the first live `usage` event. No regression vs. today — but note the optics
  shift: previously the overlay showed `0 / 0`; now it shows the restored `used / 0`
  (non-zero used against a zero max) for a failed-fetch session. This is acceptable
  (the used-counts are real; only the max is unknown) and self-heals on the first live
  `usage` event, which carries `max_context_tokens`. No code change warranted.
- **Partial/malformed `last_usage`** (missing a field): the `|| 0` fallbacks render 0
  for the missing field rather than `NaN`/`undefined`.
- **Live `usage` event arrives before the seed resolves** (user sends immediately on
  reopen): `setTelemetryMax` recomputes the bar from whatever `context_tokens` is
  currently retained (the live value), never re-zeroing — strictly better than the
  pre-leg behavior.

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js` — raw-state
  retention in `updateTelemetry`/`resetTelemetry`; new exported `setTelemetryMax`.
- `the_one/interfaces/web/static/js/areas/chat.js` — synchronous `last_usage` restore
  in `session_joined`; max-only `/context-window` seed.
- `tests/` — one unit test asserting the join payload carries
  `session_metadata.last_usage` (backend module per repo layout).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [ ] If final leg of flight: (not final — L03 follows)
- [x] Commit all changes together (code + artifacts)

> **Note (agentic-workflow):** Deferred-commit flight. The Developer stops at
> `[HANDOFF:review-needed]` with leg status `landed` and the flight log updated — it
> does **not** commit. The Flight Director runs a single review + commit after L03.

## Citation Audit

Citations verified against current code at leg design time (design-review pass
caught L01-induced line drift in the join-payload builders; repaired below):
- `telemetry-overlay.js:74-92` (`updateTelemetry`, absolute-set, pct/stateClass at
  `:80-89`) — **OK**.
- `telemetry-overlay.js:96-107` (`resetTelemetry`) — **OK**.
- `telemetry-overlay.js:109-112` (exports) — **OK**.
- `chat.js:895` (`session_joined` handler), `:910` (`resetTelemetry(content)`),
  `:915` (routing-key defensive read precedent) — **OK**.
- `chat.js:942-954` (async `/context-window` seed calling `updateTelemetry` with
  zeroed used-counts at `:946-951`) — **OK** (the re-zero this leg removes).
- `app.py:1088` (`_build_session_joined_ok`) / `:1108` (`"session_metadata":
  session.session_metadata`) — **drifted→repaired**: L01 added ~87 lines to `app.py`
  (was `:1048`/`:1068` at flight-design time); re-verified against the post-L01
  working tree.
- `app.py:1112` (`_build_session_joined_degraded`) / `:1137` (`"session_metadata":
  db.session_metadata`) — **drifted→repaired** (was `:1072`/`:1097`); re-verified
  post-L01. L02 now asserts this builder's carry too (AC5).
- Test modules importing `_build_session_joined_*` (`test_ws_responsiveness.py`,
  `test_session_registry_lock_unification.py`, `test_app_pending_approval_merge.py`)
  — **OK**: confirmed none assert the `session_metadata` carry, so the new
  `test_session_joined_payload.py` is non-duplicative.
