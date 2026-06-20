# Flight: Telemetry Overlay Usage Persistence

**Status**: landed
**Mission**: [LLM Provider Layer Hardening & Capability Completeness](../../mission.md)

## Contributing to Criteria

> Serves the mission's broader UI-reporting outcome ("accurate context-window
> reporting in the UI that survives going back to an old chat"). Completes the
> operator-facing half of Flight 5: F5 made the context-window **value** (max)
> correct + restart-survivable; F6 makes the **used-token state** survive too, so
> the overlay restores `used / max` (not `0 / max`) on reopen. Tracked against the
> F5-HAT Known Issue in the mission.

- [x] Reopening an old chat (including after a server restart) restores the
      telemetry overlay's last-turn `used / max` fullness — not `0 / max`. *(HAT
      PASS + automated round-trip/browser coverage)*

---

## Pre-Flight

### Objective

Persist a per-session token-usage snapshot durably and restore it when a chat is
reopened, so the telemetry overlay shows the conversation's real fullness (the
`context_tokens / max` bar + the last turn's input/output totals) instead of
resetting to zero. Today usage events are projection-only (live WebSocket push,
never persisted) and `renderHistory` doesn't replay them; Flight 5 made the *max*
restart-survivable via the catalog, but the *used-token* state still resets. This
flight closes that gap by reusing the existing `session_metadata` durability path.

### Open Questions
- [x] **Storage location** → DD1. Resolved: `session_metadata["last_usage"]`, via
      the **already-existing** `set_session_metadata_key` repository primitive.
- [x] **Write cadence** → DD2. Resolved (operator + design review): write once per
      *completed* turn — but a turn can settle in **two** places (normal vs.
      auth-pause/resume), so the write goes at **both** settle points.
- [x] **Restore scope / semantic** → DD3. Resolved: restore the **last completed
      turn's** `{input_tokens, output_tokens, context_tokens}` (the overlay is
      per-turn / absolute-set, not session-cumulative — see DD3). The fullness bar
      (`context_tokens`) is the headline value.
- [x] **Purge/retention interaction** → corrected by design review: the daily sweep
      is `retention.run_purge_sweep → delete_older_than` (`repositories.py:1096-1133`),
      a **full row DELETE** — `session_metadata.last_usage` is removed atomically
      with the row. Non-issue (no orphaning; no surviving row). *(Not `purge_messages`,
      which the first draft wrongly cited.)*
- [x] **Live overlay on the first turn after restore** → DD3. The restore pre-fills
      the overlay; the next turn's `usage` event updates it per-turn as normal (the
      `context_tokens` bar tracks the growing conversation size, so it does not
      "drop"). No server-side accumulator seeding required.

### Design Decisions

**DD1 — Store in `session_metadata["last_usage"]` via the EXISTING overwrite
primitive**: persist `{input_tokens, output_tokens, context_tokens}` into the
`chat_sessions.session_metadata` JSON column (`db/models.py:724`) using the
**already-implemented** `ChatSessionRepository.set_session_metadata_key(session_id,
key, value)` (`repositories.py:1222-1282`, landed M10 F07 L5 for `routing_override`;
unit-tested at `tests/test_db_repositories.py:2988-3053`). It read-modify-writes the
column, overwrites a single key, preserves siblings, and raises `KeyError` on an
unknown session — exactly the semantics needed.
- Rationale: the column is persisted + reloaded across server restarts, the
  `session_joined` payload already surfaces the full `session_metadata`
  (`app.py:1068` ok-path, `:1097` degraded-path), and `chat.js` already reads it
  (`session_metadata.routing`). The whole read/write path exists — **no new
  primitive, no migration**. (Design review corrected the first draft, which
  proposed adding a primitive that already exists.)
- Trade-off: none.

**DD2 — Write once per completed turn, at BOTH settle points**: a non-paused turn
settles in `_process_and_broadcast` (which accumulates the turn totals
`total_input`/`total_output`/`last_input`, `app.py:1442-1444`) and reaches
`_save_session_to_db` (`:1555`). A turn that pauses for OAuth, however, **breaks**
out (`paused = True; break`, `:1511-1512`) holding only the *pre-pause partial*, and
**completes in a separate function** `_resume_paused_session` (`:1567`, driven by a
separate task from the OAuth callback `api.py:2251`) — which emits per-message usage
via `_broadcast_one` and carries **no running total** from the pre-pause portion.
`_process_and_broadcast` does **not** re-run on resume (so no double-write), but a
single-settle-point write would persist only the pre-pause partial and miss the
resume portion. **Resolution**: write `last_usage` at **both** settle points — after
the `_process_and_broadcast` turn loop settles (non-paused completion) and at the
`_resume_paused_session` settle (resume completion, accumulating that segment's
usage there). The exact mechanism (write in both vs. hoist a cumulative onto the
`Session`) is a Leg-1 design call; either must capture the resume portion. **The
resume settle has no existing accumulator to hoist** — `_resume_paused_session`
just forwards each message to `_broadcast_one` — so L01 must **add** a small usage
accumulator over the `resume_after_auth()` loop (sum `input_tokens`/`output_tokens`;
keep the last message's `input_tokens` as the derived `context_tokens`).
- **Persisted value for a paused turn = the resume segment only** (operator
  decision): the pre-pause partial is discarded at the `break` and the resume
  segment overwrites at the second settle. This **matches the live overlay** (whose
  resume `usage` events are per-segment / absolute-set), so reopening shows exactly
  what the operator last saw. We deliberately do NOT stash the pre-pause partial
  across the pause to sum it.
- Rationale: operator wants final-per-turn; the auth-pause split means "per turn"
  has two endings. Design review flagged this as the highest-risk premise.
- Trade-off: two write sites instead of one; a mid-turn crash before either settle
  loses that in-progress turn's snapshot (the prior turn's persists; the next
  completed turn overwrites). Acceptable.

**DD3 — Restore the last completed turn's values; overlay is per-turn**:
`updateTelemetry` (`telemetry-overlay.js:74-92`) is **absolute-set** (each `usage`
event overwrites the displayed values), and the server-side turn totals reset to 0
at the top of each `_process_and_broadcast`. So the overlay always shows the **last
turn's** in/out and the last turn's `context_tokens` (≈ the conversation's context
size). `last_usage` therefore snapshots the last completed turn's
`{input_tokens, output_tokens, context_tokens}`; restoring it pre-fills the overlay
to exactly its on-leave state. The first message after reopen produces a new turn
that updates the overlay normally — not a regression (the `context_tokens` bar tracks
the growing conversation, so it does not visibly drop). No seeding of server-side
accumulators is needed.
- Rationale: matches existing live per-turn semantics; restore only fills the
  reopen gap. (Design review surfaced the absolute-set behavior; this DD pins the
  intended semantic so it isn't discovered in the HAT.)
- Trade-off: the overlay reflects the *last turn*, not a session-lifetime sum — but
  that is already how the live overlay behaves, so restore is consistent with it.
- **`context_tokens` is derived, not a struct field**: `TokenUsage`
  (`llm/base.py:58-61`) carries only `input_tokens`/`output_tokens`. The overlay's
  `context_tokens` is synthesized — `last_input` (the last assistant step's input
  tokens) on the non-paused path (`app.py:1444/1449`), and the last broadcast
  message's `input_tokens` on the resume path (`:1290`). The snapshot stores this
  derived last-input value; tests assert the derivation, not a struct field.

**DD4 — Frontend reconcile: the `/context-window` seed must be max-only**: the
`session_joined` handler runs `resetTelemetry` (`chat.js:910`), then an async
`/context-window` fetch resolves *later* and calls `updateTelemetry` with
`input/output/context_tokens: 0` + the real `max` (`chat.js:~942-955`) — which would
re-zero a restored snapshot. Resolution: the restore applies `last_usage`
synchronously in the handler, and the async max-seed is changed to update **only**
`max_context_tokens` (since `updateTelemetry` is absolute-set, the seed needs to
touch only `.t-max` and must not pass zeroed used-counts that clobber the restore).
- Rationale: removes the async re-zero race. Design review confirmed the race is
  real and this fix is sound.
- Trade-off: a small, contained change to the existing seed callback. *(Spec line
  numbers for this handler are approximate — refresh against current `chat.js` in
  Leg 2.)*

**DD5 — Coexistence with the post-turn save (no clobber)**: `_save_session_to_db`
→ `repo.update` (`repositories.py:1038-1067`) deliberately writes only
`title, messages, updated_at` and **does NOT** round-trip `session_metadata`
(`:1065`, documented coexistence contract the routing-audit writer already relies
on). So a `set_session_metadata_key("last_usage", …)` write cannot be clobbered by
the turn's save regardless of ordering.

**DD6 — Apparatus (verify/HAT), both axes confirmed**:
- *Act*: send messages (turn totals accumulate in `_process_and_broadcast`);
  restart the server (drops in-memory `_sessions`, forcing a DB restore on reopen).
- *Observe*: automated — the `session_joined` payload's `session_metadata.last_usage`
  (read path confirmed: `_restore_session` always loads `session_metadata` from the
  DB and feeds both `_build_session_joined_ok` `:1068` and `_build_session_joined_degraded`
  `:1097`; the warm-cache vs DB-restore paths converge through `_restore_session`, so
  restart-survival holds); live/UI — the overlay DOM (`.t-in`/`.t-out`/`.t-ctx`/
  `.context-bar`/`.t-max`) via the existing **Playwright browser harness**
  (`tests/browser/`, `seeders.py` `seed_mock_agent`/`seed_mock_provider`). No
  test-only seam needed.

### Prerequisites
- [ ] No new network service / port / table and **no DB migration** — the
      `session_metadata` column and the `set_session_metadata_key` primitive both
      already exist; `last_usage` is a new JSON key within the column.
- [ ] For the HAT/browser legs: a running instance + an agent with a configured
      provider. Run the F6 dev instance on a **free port** (the stale 0.2.2 instance
      on :8484 conflict from F5 still applies).

### Pre-Flight Checklist
- [x] Open questions resolved (all 5 resolved above; the auth-pause write mechanism
      is a Leg-1 design detail with two acceptable shapes)
- [x] Design decisions documented (DD1–DD6)
- [x] Prerequisites verified (no new service/port/table/migration; HAT env = free port)
- [x] Validation approach defined (unit + integration round-trip + Playwright + HAT)
- [x] Legs defined (3 + optional HAT); architect-validated over 2 review cycles

---

## In-Flight

### Technical Approach

Call the existing `set_session_metadata_key` to write `last_usage =
{input_tokens, output_tokens, context_tokens}` at both turn-settle points in
`app.py`: the non-paused settle in `_process_and_broadcast` (after the `agent.step()`
loop, using the settled turn totals) and the resume settle in
`_resume_paused_session` (capturing the resumed segment's usage). Update the
in-memory `session.session_metadata` at the same time so a same-process reopen sees
it without a DB round-trip. The `session_joined` payload already carries
`session_metadata`, so no backend payload change is needed and `repo.update` won't
clobber it (DD5). In `chat.js`, the `session_joined` handler restores `last_usage`
into the overlay and the `/context-window` seed becomes max-only (DD4).

### Checkpoints
- [x] `last_usage` is written via `set_session_metadata_key` at the non-paused
      settle AND the resume settle; correct totals in each case (L01)
- [x] In-memory + DB stay consistent; purge (`delete_older_than`) confirmed
      non-interfering (L01)
- [x] Reopening a chat restores the overlay (bar + last-turn in/out); the
      `/context-window` seed no longer re-zeros it (L02)
- [x] Round-trip integration (write → DB reload as a simulated restart →
      `session_joined` carries `last_usage` → restore applies it) + a browser flow
      test asserting the restored overlay DOM; full suite ≥ F5 baseline (L03)

### Adaptation Criteria
**Divert if**:
- Writing `last_usage` per turn measurably regresses turn latency (it shouldn't —
  one small JSON-column read-modify-write; the routing writer does the same) →
  reconsider batching.

**Acceptable variations**:
- The auth-pause write mechanism (write at both sites vs. hoist a cumulative onto
  the `Session`), provided the resume portion is captured.
- Snapshot key names; whether the frontend reconcile is by reorder or max-only seed
  (DD4), provided no async re-zero race remains.

### Legs

> **Note:** Tentative; planned one at a time as the flight progresses.

- [x] `persist-usage-snapshot` - Write `last_usage` via the existing
      `set_session_metadata_key` at **both** turn-settle points, updating in-memory
      `session.session_metadata` too. Non-paused: use the settled
      `total_input`/`total_output`/`last_input` in `_process_and_broadcast`. Resume:
      **add** a usage accumulator over the `resume_after_auth()` loop in
      `_resume_paused_session` (none exists today — it forwards to `_broadcast_one`),
      summing `input_tokens`/`output_tokens` and keeping the last message's
      `input_tokens` as the derived `context_tokens`. Confirm `delete_older_than`
      purge is non-interfering. Unit tests for **both** settle paths, asserting the
      derived `context_tokens` (not just non-zero). *(No new primitive — it exists.)*
- [x] `restore-overlay-on-join` - In `chat.js` `session_joined`, restore
      `last_usage` from `data.session_metadata` into the overlay (bar + last-turn
      in/out); make the `/context-window` seed max-only so it doesn't re-zero the
      restore (DD4). Backend payload already carries it — assert that at the payload
      level.
- [x] `verify-integration` - Integration round-trip: send a turn → `last_usage`
      persisted → **drop the in-memory `_sessions` entry** so the join flows through
      `_restore_session` (`app.py:856`) from the DB (the real restart path, not a
      warm-cache shortcut) → `session_joined` carries `last_usage` → restore applies
      it (assert the restored `context_tokens` equals the written value, not merely
      "non-zero"). Cover **both** the ok-path (`_build_session_joined_ok:1068`) and
      the degraded-path (`_build_session_joined_degraded:1097`) carry `last_usage`
      (nearly free — both read `db_session.session_metadata`). Add a **Playwright
      browser flow test** (`tests/browser/`):
      seed a mock agent, drive a turn, reopen the session, assert `.t-in`/`.t-ctx`/
      `.context-bar` DOM reflects the restored values (DOM-shape assertions, **no
      committed visual snapshots** per the snapshot-gitignore rule). Full suite green
      at/above the F5 baseline.
- [x] `uat-and-alignment` *(optional)* - Guided HAT: send a few messages, note the
      overlay's used/max; **restart the server**; reopen the chat from history and
      confirm the overlay restores the last-turn used + max (not 0/max). **PASS**
      (operator-confirmed, 2026-06-20): genuine process restart on `:8485`, overlay
      restored 1.2k/20/1.2k/128.0k/1% identical to pre-restart. See flight-log L04.

---

## Post-Flight

### Completion Checklist
- [x] All legs completed (L01–L03 + the optional HAT L04)
- [ ] Code merged *(draft PR #134 → ready for review; merges after F5 #133)*
- [x] Tests passing (full suite `3443 / 10 / 595`, 21 above the F5 baseline, no new
      flakes; new Playwright browser flow green)
- [x] Documentation: the `session_metadata.last_usage` snapshot noted in
      `set_session_metadata_key`'s docstring; mock `config` options (incl.
      `input_tokens`) documented in CLAUDE.md

### Verification
- **Unit** (hermetic): the per-turn write at the non-paused settle and the resume
  settle each persist the correct `last_usage` via `set_session_metadata_key`
  (reusing that method's existing test patterns); purge non-interference.
- **Integration**: persist → DB reload (no in-memory session — the restart case) →
  `_restore_session` / `session_joined` payload carries `last_usage` → restore
  yields the written overlay state (assert the value the snapshot drove).
- **Browser** (Playwright, `tests/browser/`): drive a turn → reopen the session →
  assert the overlay DOM restored. DOM-shape assertions only; any visual snapshot
  stays gitignored (global rule).
- **HAT** (operator's choice; real-environment): live server restart + reopen,
  eyeballing the overlay restore — the paradigm that proved high-value in F5.
- **Not behavior-test-backed for now**: the browser flow test + HAT cover the live
  cross-restart UI check; a re-runnable `/behavior-test` is a candidate future
  regression net, not authored speculatively here.
