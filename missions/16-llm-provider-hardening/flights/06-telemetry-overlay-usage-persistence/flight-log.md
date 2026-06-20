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

_(none yet)_

---

## Anomalies

_(none yet)_

---

## Session Notes

- **2026-06-20** — Created during `/flight` planning, immediately after Flight 5
  landed (PR #133). Distinct subsystem (session/DB persistence) kept out of F5 to
  avoid bundling unrelated work.
