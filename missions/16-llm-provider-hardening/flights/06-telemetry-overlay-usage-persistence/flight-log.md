# Flight Log: Telemetry Overlay Usage Persistence

**Flight**: [Telemetry Overlay Usage Persistence](flight.md)

## Summary

Flight created (planning). Persists a per-session token-usage snapshot in
`session_metadata["last_usage"]` and restores it on chat reopen so the telemetry
overlay shows `used / max`, not `0 / max`. Originated from the Flight 5 HAT
finding (overlay used-token state doesn't survive reopen). No execution yet.

---

## Reconnaissance Report

Source: the Flight 5 HAT-surfaced Known Issue (mission `16`, "Discovered during
Flight 5 HAT"). Single item; walked against current code during F6 planning.

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| Overlay used-token state resets on chat reopen | `confirmed-live` | usage events are `_send_to_session`-only, never `session.add_event`'d (`app.py:1293`,`:1452` send; the `add_event` calls there are for the assistant message, not usage); `renderHistory` (`chat.js:253-320`) doesn't replay usage; `session_joined` re-seeds via `/context-window` with used-counts `0` (`chat.js:946-951`) | Persist `last_usage` in `session_metadata`; restore on join (this flight) |

**Durability path confirmed (apparatus / read-path, both axes):**
- *Write site*: `_process_and_broadcast` accumulates `total_input` / `total_output`
  / `last_input` (`app.py:1383-1385`) — available at turn settle.
- *Persistence*: `chat_sessions.session_metadata` JSON column (`db/models.py:724`),
  written by `ChatSessionRepository.append_to_session_metadata` (`repositories.py:1178`,
  the routing-audit precedent). A sibling **overwrite** primitive is the only new
  piece needed (the existing one appends-to-list).
- *Restore/read*: `_restore_session` loads `session_metadata` from the DB; the
  `session_joined` payload already includes the full `session_metadata`
  (`app.py:1068`, `:1097`); `chat.js` already consumes it (`session_metadata.routing`).
- *Observe*: overlay DOM fields `.t-in` / `.t-out` / `.t-ctx` / `.context-bar` /
  `.t-max` (`telemetry-overlay.js:74-90`).

No migration required (column exists; `last_usage` is a new JSON key within it).

**Carry-forward**: F5 landing baseline `3422 passed / 10 skipped / 594 deselected`,
0 failures. F5 HAT lesson — *verify integration against the real external surface,
not an assumed shape* — applies here to the persist→reload→restore round-trip and
the HAT.

---

## Flight Director Notes

- **2026-06-20** — Flight planned from the F5 HAT finding. Operator interview
  resolved: storage = `session_metadata["last_usage"]` via a new overwrite
  primitive (DD1); write cadence = final-usage-per-turn (DD2); restore scope = full
  overlay, bar + in/out totals (DD3); HAT included. Frontend reconcile (DD4) needed
  so the async `/context-window` max-seed doesn't re-zero the restored counts.
- **2026-06-20** — `/agentic-workflow` execution started. Loaded crew file
  `leg-execution.md` (well-formed: Crew / Interaction Protocol / Prompts all
  present). Branch-base decision: **`flight/06-telemetry-overlay-usage-persistence`
  branched from the `flight/05` tip (`55780e9`), not `main`.** Rationale: F5's PR
  #133 is still OPEN (F5 code not yet in `main`); F6 modifies F5-introduced code
  (the `chat.js` `/context-window` seed, DD4) and the F6 planning artifacts already
  sit on the `flight/05` branch. This is an intentional stacked-flight on top of F5.
  Flight status `ready` → `in-flight`.

---

## Decisions

### Design review (Architect, Opus) round 1 → needs rework, incorporated
The first-draft spec rested on three premises the design review refuted against
current code (the codebase is ahead of where recon was written):
- **The `set_session_metadata_key` primitive already exists** (`repositories.py:1222-1282`,
  M10 F07 L5, tested at `test_db_repositories.py:2988-3053`) — DD1/L01 rewritten to
  *consume* it, not add it; the "add primitive" leg scope dropped.
- **Auth-pause turns split across two functions** (`_process_and_broadcast` pre-pause
  + `_resume_paused_session` post-resume, the latter with no running total) — DD2
  reworked to write at **both** settle points (highest-risk premise; a single write
  would persist only the pre-pause partial).
- **Purge premise stale** — the daily sweep is `delete_older_than` (full row DELETE),
  not `purge_messages`; non-issue corrected to the right reason.
Also folded in: the overlay is **absolute-set / per-turn** (DD3 pins the last-turn
restore semantic + resolves the "first turn after restore" question); `repo.update`
deliberately doesn't round-trip `session_metadata` so no clobber (DD5); a **Playwright
browser harness** exists (`tests/browser/`) → used for the restore flow test instead
of a payload-only fallback.

### Design review round 2 → approve with changes, incorporated
All 6 round-1 findings confirmed against code. Two clarifications folded in:
`context_tokens` is a **derived** value (not a `TokenUsage` field), so the resume
settle must **add** an accumulator over `resume_after_auth()` (no existing total to
hoist) — sharpened in DD2 + L01; and the persisted snapshot for an auth-paused turn
is the **resume segment only** (matches the live per-segment overlay; no cross-pause
stashing — operator-acceptable). L03 sharpened to flow through `_restore_session`
(real restart path) + cover the degraded join-path. Spec is codebase-validated;
max 2 review cycles reached.

_(runtime decisions recorded here during execution)_

---

## Deviations

### DD-L03-1 — Mock provider test seam (`config["input_tokens"]`) added in L03
**Planned**: L03 (per the flight spec) drives a live turn through a seeded mock agent,
reopens, and asserts the restored overlay (`.t-in`/`.t-ctx`/`.context-bar`).
**Actual**: `MockProvider` hardcodes `TokenUsage(input_tokens=0, …)` (`mock.py:77`,
`:124`). Because the overlay's derived `context_tokens` is `last_input` (= the last
assistant step's `input_tokens`) and L01's zero-usage guard is `if last_input:`, a
default-mock turn yields `last_input == 0` → the `last_usage` write is **suppressed
entirely** → nothing to restore. So the flight's stated verification could not run on
the stock mock. L03 adds a **backward-compatible** seam: `MockProvider` reads an
optional `config["input_tokens"]` (default **0**, preserving all existing tests) and
emits it in `complete()` + `stream()`. Tests opt in with `config={"input_tokens": N}`.
**Reason**: the flight plan didn't anticipate the mock's zero `input_tokens`; the seam
is the minimal change that lets the flight's own acceptance test exercise the
persist→restart→restore path. The change is confined to test infrastructure (mock
defaults unchanged) and does not alter production behavior. *(F5-HAT-class lesson:
verify against the real apparatus — the mock's token accounting was the assumed-shape
gap.)*

### Known limitation surfaced (NOT fixed this flight): `if last_input:` guard drops real Ollama turns with `input_tokens=0`
Design review (L03) found the guard also suppresses persistence for any **real**
provider that reports `input_tokens=0` — notably Ollama, whose adapter uses
`u.get("prompt_tokens", 0)` and can settle a genuine turn with `last_input == 0` when
the build/endpoint omits `prompt_tokens` (or the usage block is absent). For such a
turn, reopening shows `0 / max` — the symptom this flight fixes, for that provider.
**Deliberately not addressed in F6**: (a) the fullness bar is unrestorable for such a
turn regardless of the guard, since `context_tokens` *is* the missing input count;
(b) a fix reopens landed L01 + its zero-usage-guard tests for an edge-of-edge case.
Carried forward as a mission Known Issue / candidate follow-up (e.g. guard on "saw any
usage event" or `last_input or total_output` so in/out still restore). **Flagged to
the operator.**

---

## Anomalies

_(none yet)_

---

## Leg Progress

### L01 — persist-usage-snapshot (landed 2026-06-20)

**Status**: landed

**Changes made:**
- `the_one/interfaces/web/app.py` — added `_persist_last_usage` shared helper after
  `_save_session_to_db`; added `last_usage` write inside `if not paused:` block in
  `_process_and_broadcast` (guarded by `if last_input:` for zero-usage guard);
  added resume-segment accumulator (`resume_input`, `resume_output`,
  `resume_last_input`) in `_resume_paused_session` inside the
  `resume_after_auth()` loop, with settle write outside the `try/except` next to
  `_save_session_to_db` (guarded by `if resume_last_input:`).
- `tests/test_last_usage_persistence.py` — new test file covering: `_persist_last_usage`
  helper (DB write + in-memory mirror + sibling-key preservation); non-paused settle
  (two-message turn asserting exact `context_tokens = last_input` not sum, zero-usage
  guard, in-memory/DB consistency); resume settle (two-message resume asserting exact
  `context_tokens = last resumed message's input_tokens`, zero-usage guard, single-
  message case, in-memory/DB consistency).

**Notes:**
- No new DB primitive, no migration. Uses existing `set_session_metadata_key`.
- 9/9 new tests passing; 207/207 existing `test_db_repositories + test_app_websocket_pause_resume` passing.
- Broader unit suite (`make test-unit`) launched in background — no failures observed at leg-end.
- `context_tokens` derived correctly as `last_input` (non-paused) and `resume_last_input` (resume),
  not the cumulative sum — the key discriminator the leg specification required.

### L02 — restore-overlay-on-join (landed 2026-06-20)

**Status**: landed

**Changes made:**
- `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js` — added raw-state
  retention (`chromeContent.__telemetry = {...}`) at the end of `updateTelemetry` (additive
  only — no existing DOM-write behavior changed); added `__telemetry` zeroing to
  `resetTelemetry`; added new `setTelemetryMax(chromeContent, maxContextTokens)` function
  inside the IIFE (module-private `fmtTokens` in scope; placed before the export block);
  exported `setTelemetryMax` on `window.App.chat`.
- `the_one/interfaces/web/static/js/areas/chat.js` — added synchronous `last_usage`
  restore block in `session_joined` handler after `resetTelemetry + renderHistory`
  (reads `data.session_metadata.last_usage` with the same defensive guard as the routing
  panel; calls `updateTelemetry` with `max_context_tokens: 0` when present); replaced
  the async `/context-window` seed's `updateTelemetry` call (which zeroed used-counts)
  with `App.chat.setTelemetryMax(content, payload.max_context_tokens)` — max-only update.
- `tests/test_session_joined_payload.py` — new test file (5 tests) covering: ok builder
  carries `last_usage` (present / absent-null / absent-key-missing); degraded builder
  carries `last_usage` (present / absent-null). Both use the same builder-import pattern
  as `test_ws_responsiveness.py`.

**Notes:**
- 5/5 new payload tests passing. All 22 tests in the new + sibling builder-test modules passing.
- Full unit suite: 3436 passed / 10 skipped / 594 deselected — above F5 baseline (3422 passed).
- The `_build_session_joined_degraded` test patches `_merge_pending_approvals_into_history`
  to avoid a real DB connection — consistent with the builder-level scope; round-trip is L03.
- No backend payload shape change — both builders already carried `session_metadata`; L02
  adds the frontend restore and the JS raw-state retention.

### L03 — verify-integration (landed 2026-06-20)

**Status**: landed

**Changes made:**
- `the_one/llm/mock.py` — added `_init_provider_state()` call in `MockProvider.__init__`
  (fixes pre-existing missing sentinel that caused `/api/agents/{name}/context-window` to
  500; required for the browser flow's `setTelemetryMax` path); updated docstring to
  document optional `"input_tokens": N` key (default 0); updated `complete()` and
  `stream()` to emit `self.config.get("input_tokens", 0)` instead of hardcoded `0`.
- `tests/test_mock_provider.py` — added `TestMockProviderInputTokensSeam` class (6 tests)
  asserting: `complete()` default yields `input_tokens == 0`; `config={"input_tokens": 42}`
  yields 42 in `complete()`; `stream()` with `stream_chunks` default/configured; `stream()`
  fallback-to-complete path default/configured.
- `tests/test_last_usage_round_trip.py` — new test file (1 test):
  `test_last_usage_round_trip_db_reload_branch` drives a StubAgent turn through
  `_process_and_broadcast`, verifies `last_usage` in DB, drops `_sessions` entry, calls
  `_restore_session` (DB-reload branch), asserts fresh Session identity, then asserts both
  `_build_session_joined_ok` and `_build_session_joined_degraded` (hand-constructed)
  payloads carry `context_tokens == 750` (exact value N, not merely non-zero).
- `tests/browser/test_flow_usage_restore.py` — new `@pytest.mark.browser` test:
  seeds provider with `config={"input_tokens": 850}`, drives a turn, waits for overlay
  non-zero via `wait_for_function`, reloads, asserts `.t-ctx`/`.t-in` restored (non-zero,
  match pre-reload values) and `.context-bar` inline width > 0%.

**Test results:**
- Mock seam: 11/11 passed (incl. 6 new)
- Integration round-trip: 1/1 passed
- Browser flow: 1/1 passed
- Full unit suite (post all L03 changes, two independent runs): **3443 passed** /
  10 skipped / 595 deselected — 21 above F5 baseline (3422). Confirmed green.
- Deviations DD-L03-1 and known limitation already recorded above in Deviations — not
  duplicated here.

**Notes:**
- `_init_provider_state()` fix was a pre-existing bug in `MockProvider` (not introduced
  by this leg). Required for the context-window endpoint to work during browser test. Base
  class docstring explicitly documents the contract; MockProvider was the sole violator.
- Stub-agent approach (not real MockProvider through factory) used for the in-process
  integration test — avoids requiring the full provider-table fixture setup; MockProvider
  seam is covered by unit tests + browser flow. Comment in test file documents this.
- Browser test asserts inline `bar.style.width` (set by `setTelemetryMax` after async
  `/context-window` fetch) rather than `getComputedStyle(...).width` — the latter reads
  the CSS box width, which doesn't reflect the percentage fill until the inline style is set.

---

## Session Notes

- **2026-06-20** — Created during `/flight` planning, immediately after Flight 5
  landed (PR #133). Distinct subsystem (session/DB persistence) kept out of F5 to
  avoid bundling unrelated work.
