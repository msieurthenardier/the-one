# Leg: persist-usage-snapshot

**Status**: completed
**Flight**: [Telemetry Overlay Usage Persistence](../flight.md)

## Objective

Persist the last completed turn's token-usage snapshot to
`session_metadata["last_usage"]` at **both** turn-settle points (non-paused
completion and auth-pause resume), updating the in-memory `session.session_metadata`
at the same time, so the value is durable across server restarts and visible to a
same-process reopen.

## Context

- **DD1** — store `{input_tokens, output_tokens, context_tokens}` under the
  `last_usage` key of `chat_sessions.session_metadata` via the **already-existing**
  `ChatSessionRepository.set_session_metadata_key(session_id, key, value)`
  (`the_one/db/repositories.py:set_session_metadata_key`,
  `repositories.py:1222-1282`). Overwrite semantic, preserves siblings, raises
  `KeyError` on unknown session. **No new primitive, no migration.**
- **DD2** — a turn settles in **two** places. The non-paused turn settles at the
  end of the `agent.step()` loop in `_process_and_broadcast` (the loop accumulates
  `total_input` / `total_output` / `last_input`, `app.py:1442-1444`). A turn that
  pauses for OAuth `break`s out (`paused = True; break`, `app.py:1511-1512`) holding
  only a pre-pause partial, and **completes separately** in `_resume_paused_session`
  (`app.py:1567`), which forwards each message to `_broadcast_one` and keeps **no
  running total**. So the resume settle needs a **new** accumulator.
- **DD3** — the overlay is **absolute-set / per-turn**: `context_tokens` is a
  *derived* value, not a `TokenUsage` field. On the non-paused path it is
  `last_input` (the last assistant step's `input_tokens`, `app.py:1444`/`:1449`); on
  the resume path it is the last broadcast message's `input_tokens`
  (`_broadcast_one` sets `"context_tokens": msg.usage.input_tokens`,
  `app.py:1290`). The snapshot stores this derived last-input value.
- **DD2 (paused-turn value)** — the persisted value for an auth-paused turn is the
  **resume segment only** (operator decision): the pre-pause partial is discarded at
  the `break`; the resume segment overwrites at the second settle. This matches the
  live per-segment overlay (resume `usage` events are absolute-set per message), so
  reopening shows exactly what the operator last saw. Do **not** stash/sum the
  pre-pause partial across the pause.
- **DD5** — `_save_session_to_db` → `repo.update` writes only
  `title, messages, updated_at` and does **not** round-trip `session_metadata`
  (`repositories.py:1038-1067`), so the post-turn save cannot clobber the
  `last_usage` write regardless of ordering.
- This is the first of three legs. L02 restores the snapshot into the overlay; L03
  verifies the round-trip end-to-end.

## Inputs

What exists before this leg runs:
- `the_one/interfaces/web/app.py` with `_process_and_broadcast` (`:1336`),
  `_resume_paused_session` (`:1567`), `_broadcast_one` (`:1248`),
  `_save_session_to_db` (`:1001`).
- `ChatSessionRepository.set_session_metadata_key` (`repositories.py:1222`),
  unit-tested at `tests/test_db_repositories.py:2988-3053`.
- `Session.session_metadata: dict[str, Any] | None` (`app.py:366`).
- The `chat_sessions.session_metadata` JSON column (`db/models.py:724`).

## Outputs

What exists after this leg completes:
- `_process_and_broadcast` writes `last_usage` to the DB **and** in-memory
  `session.session_metadata` after the step loop settles (non-paused completion).
- `_resume_paused_session` accumulates usage over its `resume_after_auth()` loop and
  writes `last_usage` (resume segment) to the DB **and** in-memory at its settle.
- Both writes use `set_session_metadata_key`; no new primitive, no migration.
- Unit tests covering **both** settle paths, asserting the derived `context_tokens`
  value (not merely non-zero).

## Acceptance Criteria
- [x] After a non-paused turn, `session_metadata["last_usage"]` in the DB equals
      `{input_tokens: total_input, output_tokens: total_output, context_tokens:
      last_input}` for that turn, written via `set_session_metadata_key`.
- [x] The in-memory `session.session_metadata["last_usage"]` matches the DB value
      after the non-paused settle (no DB round-trip needed for a same-process reopen).
- [x] After an auth-pause **resume**, `session_metadata["last_usage"]` equals the
      **resume segment's** totals: `input_tokens` / `output_tokens` summed over the
      resumed messages, `context_tokens` = the last resumed assistant message's
      `input_tokens`.
- [x] The resume-path accumulator does not double-count and does not depend on the
      pre-pause partial (the pre-pause partial is discarded by design).
- [x] No new repository primitive is added and no DB migration is introduced.
- [x] A turn with no usage (e.g. agent error before any usage event) does not write a
      malformed/zeroed snapshot that would mislead the restore — see Edge Cases.
- [x] Unit tests exist for both the non-paused settle and the resume settle, each
      asserting the exact derived `context_tokens` value; existing
      `set_session_metadata_key` tests still pass.

## Verification Steps
- Non-paused write: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/<new-or-updated-test-file> -x --timeout 30` — asserts the persisted
  `last_usage` after a simulated turn equals `{total_input, total_output,
  last_input}`.
- Resume write: same runner — asserts the resume-segment accumulator persists the
  summed in/out and the last message's `input_tokens` as `context_tokens`.
- In-memory consistency: assert `session.session_metadata["last_usage"]` equals what
  was written to the DB at each settle.
- Purge non-interference: confirm the daily sweep `delete_older_than`
  (`repositories.py:1096-1133`) is a full-row DELETE so `last_usage` is removed
  atomically with the row (no orphaning) — a read/inspection check, not new behavior.
- Regression: `tests/test_db_repositories.py` (the existing
  `set_session_metadata_key` suite) still green.

## Implementation Guidance

1. **Add a `last_usage` write at the non-paused settle in `_process_and_broadcast`.**
   - **Placement (explicit, per design review):** put the write **inside the
     `if not paused:` block** at `app.py:1559-1563` — i.e. after the unconditional
     `_save_session_to_db` call at `:1553-1557`, in the same block that broadcasts the
     `done` event. This is the unambiguous, pause-correct site: a paused turn skips
     this block (its snapshot is written later at the resume settle), and the
     non-paused turn writes exactly once here.
   - Build the snapshot from the settled accumulators: `{"input_tokens": total_input,
     "output_tokens": total_output, "context_tokens": last_input}`.
   - Persist it via the shared helper (step 3) which does
     `set_session_metadata_key(session.id, "last_usage", snapshot)` and updates
     in-memory: `session.session_metadata = {**(session.session_metadata or {}),
     "last_usage": snapshot}` (mirror the repo's read-modify-write so siblings like
     `routing` survive in-memory too).
   - **Repo acquisition (corrected, per design review):** acquire the repo with
     `await _chat_repo()` from within `app.py` (`app.py:_chat_repo`, `:764`) —
     exactly as `_save_session_to_db` does at `app.py:1004`. Do **not** model the call
     on `api.py:3709` (that is a different file's access path; it is only a *semantic*
     parallel for the metadata-key write, not the acquisition pattern to copy).

2. **Add a usage accumulator + `last_usage` write at the resume settle in
   `_resume_paused_session`.**
   - There is no running total on this path — `_broadcast_one` emits per-message
     usage (`app.py:1284-1293`) but keeps nothing. Add locals before the
     `async for msg in session.agent.resume_after_auth()` loop (`app.py:1603`):
     `resume_input = 0`, `resume_output = 0`, `resume_last_input = 0`, and a flag
     for "saw any usage".
   - Inside the loop, when `msg.role == Role.ASSISTANT and msg.usage`, accumulate:
     `resume_input += msg.usage.input_tokens`, `resume_output +=
     msg.usage.output_tokens`, `resume_last_input = msg.usage.input_tokens`.
   - **Placement (explicit, per design review):** write the snapshot **outside the
     `try/except`**, next to the existing `_save_session_to_db` call at
     `app.py:1631-1634` (i.e. after the `finally` that resets `csid_token` at
     `:1621-1622`). This matches the `_save_session_to_db` placement so a
     partial-resume exception still persists whatever usage accumulated before the
     exception — consistent with the save's own positioning.
   - If any usage was seen, persist `{"input_tokens": resume_input, "output_tokens":
     resume_output, "context_tokens": resume_last_input}` via the shared helper
     (step 3). Do **not** touch the pre-pause partial — it is intentionally discarded
     (DD2). The resume segment is the persisted value.

3. **Factor the snapshot-write into a shared helper (strongly recommended).** The two
   settle sites have *different* surrounding structure (one inside `if not paused:`,
   one after a `finally`), so a single helper is the cleanest guard against the two
   sites diverging: `async def _persist_last_usage(session, input_tokens,
   output_tokens, context_tokens)` that (a) builds the snapshot dict, (b) calls
   `set_session_metadata_key`, and (c) updates in-memory `session.session_metadata`.
   Call it from both settle points.

4. **Unit tests — both settle paths.**
   - Non-paused: drive a turn (or call the settle helper) and assert the persisted
     `last_usage` matches `{total_input, total_output, last_input}` AND the in-memory
     value matches. Reuse the `set_session_metadata_key` test patterns at
     `tests/test_db_repositories.py:2988-3053` for the DB assertion shape.
   - Resume: simulate the resume loop accumulation (messages with `usage`) and assert
     the resume-segment snapshot is persisted with the correct derived
     `context_tokens` (the **last** message's `input_tokens`, not the sum).
   - Assert the **exact** derived `context_tokens`, not just "non-zero" (the round-2
     design review's sharpening — a sum-vs-last-input bug must be caught here).

## Edge Cases
- **Turn with zero usage events** (agent errored before any `usage` arrived): the
  accumulators stay 0. Prefer **not** writing a `last_usage` of all-zeros that would
  make a restored overlay read `0 / max` indistinguishably from "never ran" — guard
  the write on "saw at least one usage event". On the non-paused path the existing
  accumulators already signal this (`last_input == 0` ⇒ no usage event fired, since
  they start at 0 at `app.py:1368-1370`), so an explicit `if last_input:` guard
  suffices; on the resume path use the "saw any usage" boolean (or `resume_last_input`
  as the same shorthand). A turn that produced no usage leaves the prior snapshot
  intact.
- **Resume itself re-pauses** (`re_paused = True; break` at `app.py:1605-1607`): the
  accumulator may hold a partial resume segment. The write site is outside the
  `try/except`, so it still runs; if any usage was seen, the partial resume-segment is
  persisted (same trade-off class as the mid-turn-crash case below — the next
  completed turn overwrites). If no usage was seen before the re-pause, the zero-usage
  guard suppresses the write and the prior snapshot survives. This is acceptable per
  DD2 (persisted value = the resume segment, even when that segment is itself partial).
- **Mid-turn crash before either settle**: the write never happens; the prior turn's
  snapshot persists; the next completed turn overwrites. Acceptable (DD2 trade-off).
- **`session_metadata` is `None`** on a fresh session: the repo primitive initialises
  it to `{}`; mirror that in the in-memory update (`session.session_metadata or {}`).
- **Concurrent writes**: `set_session_metadata_key` is last-writer-wins by design
  (`repositories.py:1236-1245`); acceptable for per-turn snapshots.

## Files Affected
- `the_one/interfaces/web/app.py` — `_process_and_broadcast` (non-paused settle
  write), `_resume_paused_session` (resume accumulator + settle write), optional
  shared `_persist_last_usage` helper.
- `tests/` — new/updated unit tests for both settle paths (e.g.
  `tests/test_last_usage_persistence.py` or extend an existing app-path test module —
  the Developer chooses the module following the repo's test layout).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [ ] If final leg of flight: (not final — L02, L03 follow)
- [x] Commit all changes together (code + artifacts)

> **Note (agentic-workflow):** This flight defers commit until after the last
> autonomous leg. The Developer for this leg stops at `[HANDOFF:review-needed]` with
> leg status `landed` and the flight log updated — it does **not** commit. The Flight
> Director runs a single review + commit after L03.

## Citation Audit

9 citations verified against current code at leg design time (design-review pass
confirmed all line numbers accurate; repo-acquisition reference corrected from
`api.py:3709` to `app.py:_chat_repo`):
- `app.py:_chat_repo` / `:764` (repo acquisition inside `app.py`; used by
  `_save_session_to_db` at `:1004`) — **OK** (the acquisition pattern both settle
  writes must follow).
- `repositories.py:set_session_metadata_key` / `:1222-1282` — **OK** (overwrite
  primitive, exists, KeyError-on-missing).
- `repositories.py:1038-1067` (`repo.update` writes only `title, messages,
  updated_at`, no `session_metadata`) — **OK** (DD5 coexistence holds).
- `app.py:1442-1444` (non-paused accumulators `total_input`/`total_output`/
  `last_input`) — **OK**.
- `app.py:1511-1512` (`paused = True; break`) — **OK**.
- `app.py:1559` (`if not paused:` guard before `done`) — **OK** (reuse as settle
  guard).
- `app.py:1567` / `:1603-1608` (`_resume_paused_session`, `resume_after_auth()`
  loop, no running total) — **OK**.
- `app.py:1290` (`_broadcast_one` resume `context_tokens = msg.usage.input_tokens`)
  — **OK** (resume-path derived context source).
- `tests/test_db_repositories.py:2988-3053` (existing `set_session_metadata_key`
  tests) — **OK** (assertion-shape precedent for the new tests).
