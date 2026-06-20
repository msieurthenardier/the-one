# Flight Debrief: Telemetry Overlay Usage Persistence

**Date**: 2026-06-20
**Flight**: [Telemetry Overlay Usage Persistence](flight.md)
**Status**: landed
**Duration**: 2026-06-20 (single-day; planned, executed, HAT'd, and landed same day)
**Legs Completed**: 4 of 4 (3 autonomous + 1 optional HAT)

## Outcome Assessment

### Objectives Achieved

The flight achieved its objective in full. The web telemetry overlay now persists the
last completed turn's `{input_tokens, output_tokens, context_tokens}` into
`session_metadata["last_usage"]` at both turn-settle points (non-paused
`_process_and_broadcast` and auth-resume `_resume_paused_session`) via the existing
`set_session_metadata_key` primitive — no new primitive, no migration. On
`session_joined`, `chat.js` restores the snapshot synchronously and the async
`/context-window` seed was made max-only (`setTelemetryMax`) so it no longer re-zeros
the restore. Reopening a chat — including after a genuine server restart — shows the
last turn's `used / max`, not `0 / max`.

### Mission Criteria Advanced

- **Resolved the F5-HAT Known Issue** ("Telemetry overlay used-token state doesn't
  persist on chat reopen") — now checked off in mission 16. This completes the
  operator-facing half of the mission's UI-reporting outcome ("accurate context-window
  reporting that survives going back to an old chat"): F5 made the *max* survive
  restart; F6 makes the *used* state survive too.
- The flight's single contributing criterion (overlay restores `used / max` on reopen,
  incl. after restart) is met and HAT-confirmed.

### Checkpoints

All four In-Flight checkpoints met: `last_usage` written at both settle points with
correct totals (L01); in-memory + DB consistency and purge non-interference (L01);
reopen restores the overlay without the `/context-window` re-zero (L02); round-trip
integration + browser flow, full suite ≥ baseline (L03).

## What Went Well

- **Design review caught real issues before any code was written.** Per-leg design
  reviews (Sonnet Developer) returned "approve with changes" on all three autonomous
  legs; every revision happened pre-implementation. No DD was revised *during*
  implementation and no autonomous leg required post-implementation rework. The
  flight-wide review (Haiku Reviewer over all uncommitted changes) confirmed on the
  **first cycle** with zero issues.
- **All six design decisions (DD1–DD6) held up in practice.** Notably DD2 (write at
  both settle points, with a *new* accumulator over the resume loop) — the highest-risk
  premise — was implemented exactly as specified; the shared `_persist_last_usage`
  helper kept the two structurally-dissimilar settle sites from diverging.
- **Exact-value test assertions, not "non-zero".** The round-2 review's sharpening
  (assert `context_tokens == N`, the derived last-input, not the cumulative sum) is
  reflected in every test and directly guards the sum-vs-last-input bug class. The
  round-trip test even asserts object identity (`restored is not pre_pop_session`) to
  prove the DB-reload branch ran rather than the warm-cache branch.
- **Both restore branches covered at the right level**: warm-cache via the browser
  flow's `page.reload()` (subprocess stays up; `existing.session_metadata` refreshes
  from DB at `app.py:966`), and the genuine DB-reload via the in-process test's
  `_sessions.pop()`. The browser test docstring documents the distinction.
- **The HAT (genuine process restart) proved high-value**, consistent with the F5
  pattern — it exercised the real DB-reload path the automated browser test cannot, and
  the operator confirmed the restore visually.
- **Strong convention adherence**: mission-tagged comments (`# M16 F06 L01:`), repo
  acquisition via `_chat_repo()` matching `_save_session_to_db`, the
  `set_session_metadata_key` write pattern matching `routing_override`, and a docstring
  update enumerating known `session_metadata` keys.

## What Could Be Improved

### Process
- **Apparatus reality wasn't verified at flight-design time (DD-L03-1).** The flight
  assumed a mock-driven turn would yield a restorable snapshot, but `MockProvider`
  hardcodes `input_tokens=0` and L01's `if last_input:` guard suppressed the write
  entirely — making the L03 verification a no-op on the stock mock. This is the *same*
  class as the F5-HAT lesson ("verify against the real apparatus, not an assumed
  shape"), here applied to *internal test infrastructure* rather than an external API.
  It was caught and resolved within L03 (a small, backward-compatible `config["input_tokens"]`
  seam) without diverting, but it added unplanned scope to L03.
- **Stacked-leg citation drift.** L01 added ~87 lines to `app.py`, shifting the
  join-payload builders (`1048→1088`); L02's spec citations were stale by the time it
  ran. The per-leg design-review citation pass caught and repaired this — the system
  working as intended — but it is an inherent hazard of stacked legs touching the same
  file.
- **L03 scope was slightly underestimated** (it absorbed the mock seam + 6 mock tests +
  a pre-existing-bug fix). The single-review-and-commit batching absorbed this
  gracefully; no new leg or divert was needed.

### Technical
- **`__telemetry` DOM-property state retention** (`telemetry-overlay.js`) couples
  overlay raw state to the DOM element's lifecycle. It works because the element is
  stable within a session, but if the chrome is ever re-rendered wholesale the state is
  lost and `setTelemetryMax` falls back to a zero bar. A module-level `Map` keyed on the
  chrome element (mirroring `inFlightSessions` in `chat.js`) would remove the coupling.
- **`setTelemetryMax` duplicates `updateTelemetry`'s bar-pct/stateClass logic.** Fine at
  two call sites; factor a `_applyBarPct(chromeContent, ctx, max)` helper if a third
  appears.
- **Test-suite timing**: full unit suite **3443 passed / 10 skipped / 595 deselected,
  0 failures, ~316s** (single run). Versus the F5 baseline (**3422 passed / 10 / 594,
  ~296s**): **+21 tests** (9 persistence + 5 payload + 1 round-trip + 6 mock-seam,
  matching the commit), **+1 deselected** (the new `@pytest.mark.browser` flow), **+~20s
  (~7%)** wall-clock attributable to the 21 new async-DB-fixture tests. No new failures
  or flakes. The pre-existing `RuntimeError: Event loop is closed` aiosqlite teardown
  warnings persist (not F6-introduced).
- **Untested**: the Ollama `input_tokens=0` guard-suppression behavior is documented but
  has no test; the real auth-pause→resume lifecycle (vs. the `StubAgent`-level
  accumulator unit tests) is not integration-tested — a gap that predates F6
  (`test_app_websocket_pause_resume.py` has the same shape).

### Documentation
- The `set_session_metadata_key` docstring now lists 2 known keys; the broader
  `session_metadata` key set is becoming a de-facto durable-session-state bus (see Key
  Learnings) and warrants a single canonical reference as it grows.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Added `config["input_tokens"]` seam to `MockProvider` (default 0) | Stock mock emits `input_tokens=0`; the zero-usage guard suppressed the write, so the flight's own verification couldn't run | No (test infra). But standardize the *design-time check* that surfaces such gaps — see Action Items |
| Fixed `MockProvider.__init__` missing `_init_provider_state()` | Pre-existing bug (base-class contract violation) caused `/context-window` to 500 for mock agents; blocked the browser flow's `setTelemetryMax` | Fix is sound; standardize *enforcement* of the contract (ABC `__init_subclass__`) so it can't recur |
| Persist resume *segment only* for auth-paused turns (discard pre-pause partial) | Matches the live overlay's per-segment absolute-set behavior; operator decision | Yes — keep, unless the overlay model becomes cumulative |
| `StubAgent` in the round-trip test (not a real `MockProvider` through the factory) | Avoids full provider-table fixture weight; the browser test covers the real stack | Acceptable as-is |

## Key Learnings

1. **Verify the test apparatus's default behavior at design time, not at implementation
   time.** The F5-HAT lesson generalizes: it applies to mocks and internal harnesses,
   not just external APIs. When a flight verifies usage/value-dependent logic via a
   mock, confirm the mock emits the needed values by default (or identify the seam)
   before designing the test.
2. **`session_metadata` has become a durable-session-state bus.** It now carries five
   named slots across two subsystems — `routing_override`, `routing`, `ended_at`
   (connectors) and `last_usage` (web turn-settle, F6) — all written via
   `set_session_metadata_key`, all surviving restart, all loaded by `_restore_session`
   and surfaced in `session_joined`. Both the Developer and Architect flagged this
   independently. The pattern is sound and worth promoting from emergent convention to a
   documented architectural decision (keys, owners, consumers, concurrency posture,
   when-to-use-vs-a-new-column).
3. **The `if last_input:` guard conflates "saw a usage event" with "input_tokens > 0".**
   Correct for providers that always report a non-zero prompt count; wrong for Ollama
   builds that omit `prompt_tokens` (the turn completes but reopens at `0/max`). The
   targeted fix is a separate `saw_usage` boolean (or `if last_input or total_output:`)
   so in/out still restore when context is unknown.
4. **Per-leg design review + single flight-wide review/commit is an efficient pattern
   for a small, cohesive flight.** It caught design issues pre-code, kept rework to
   zero, and absorbed L03's scope creep without a divert.

## Recommendations

1. **Create a follow-up issue for the `if last_input:` guard** vs. Ollama
   `input_tokens=0` — fix is `if last_input or total_output:` (or a `saw_usage` flag).
   Medium priority; elevate if the operator uses Ollama as a primary chat provider.
2. **Document the `session_metadata` durable-session-state bus** in one canonical place
   (consolidate the connector-side `connectors/README.md §12` notes and the
   `set_session_metadata_key` docstring into a single key registry in `agents.md` or a
   new `session-state-bus.md`).
3. **Enforce the `_init_provider_state()` base-class contract** (e.g. via
   `LLMProvider.__init_subclass__` or an ABC test) so a provider that skips it fails
   loudly rather than 500-ing at the `/context-window` endpoint.
4. **Add a flight-design checklist item for mock-backed verification**: "Confirm the
   mock emits the values the feature's guards require, or identify the seam needed,"
   before leg design.
5. **(Optional, low priority) Reduce the `__telemetry` element-lifecycle coupling** by
   moving overlay raw state to a module-level `Map`, and factor `_applyBarPct` to
   dedupe the bar computation between `updateTelemetry` and `setTelemetryMax`.

## Action Items

- [ ] File the `if last_input:` guard / Ollama `input_tokens=0` follow-up (carried in
      mission 16 Known Issues; route to `/mission-debrief` or a maintenance leg)
- [ ] Author the `session_metadata` key-registry / session-state-bus documentation
- [ ] Enforce `_init_provider_state()` in the `LLMProvider` ABC (+ a guard test)
- [ ] Add the "verify mock apparatus defaults" item to the flight-design checklist
- [ ] Once F5 (#133) merges, rebase #134 onto `main` (stacked PR)
- [ ] *(Optional)* Refactor `__telemetry` to module-level state; extract `_applyBarPct`

## Skill Effectiveness

- **Mission skill**: adequate context; the F5-HAT Known Issue gave F6 a precise,
  pre-scoped target.
- **Flight skill**: DD1–DD6 structure supported execution well. **Gap**: the DD6
  apparatus section confirmed the harness *exists* and that `seed_mock_provider` takes a
  `config=`, but not what the mock *emits by default* — the DD-L03-1 miss. A future
  improvement to the flight/DD6 template: when the apparatus is a mock, verify its
  default output satisfies the feature's guards.
- **Leg skill**: the Citation Audit (Phase 3b) earned its keep — it caught the L01→L02
  line drift in a stacked-leg situation. Acceptance criteria were verifiable throughout
  (exact integer values). No changes recommended.
