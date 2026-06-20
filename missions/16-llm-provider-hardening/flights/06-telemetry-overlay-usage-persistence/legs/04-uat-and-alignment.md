# Leg: uat-and-alignment

**Status**: completed
**Flight**: [Telemetry Overlay Usage Persistence](../flight.md)

## Objective

Operator-witnessed HAT: confirm that after a **real server restart** (in-memory
`_sessions` dropped → DB-reload path), reopening a chat restores the telemetry
overlay's last-turn `used / max` fullness — not `0 / max`.

## Context

- Interactive leg — not autonomously implemented. The Flight Director drives the
  apparatus and presents evidence; the operator makes the pass/fail call.
- This is the increment over the automated browser flow (`test_flow_usage_restore.py`,
  which uses `page.reload()` → warm-cache branch): the HAT performs a **genuine
  process restart** so the join flows through `_restore_session`'s fresh-`Session`
  DB-reload branch (`app.py:970-986`).
- Run on **port 8485** (operator-specified; avoids the default `:8484`).
- Dev-mode isolated instance + mock agent with `config["input_tokens"] > 0` (the
  L03 seam) so a turn produces a meaningful, persistable snapshot without real API
  cost.

## Acceptance Criteria (verification steps)
- [x] A dev instance on `:8485` serves the F6 branch code.
- [x] After sending a message, the overlay shows non-zero `in` / `out` / `ctx` and a
      filled `context-bar`, with a real `max`. *(in=1.2k, out=20, ctx=1.2k, max=128.0k,
      bar=1%)*
- [x] After a **real server restart** (process down→up) and reopening the same chat
      from history, the overlay restores the last-turn `used / max` — bar filled,
      counts non-zero — **not** `0 / max`. *(restored identical: 1.2k/20/1.2k/128.0k/1%)*
- [x] Operator confirms the restored overlay matches the pre-restart state. *(PASS,
      2026-06-20)*

## Apparatus (DD6)
- *Act*: send messages (turn totals accumulate); restart the server process (drops
  in-memory `_sessions`); reopen the chat from history.
- *Observe*: overlay DOM `.t-in` / `.t-out` / `.t-ctx` / `.context-bar` / `.t-max`,
  via the chrome-devtools browser + screenshots.

## Notes
- Evidence (screenshots) is ephemeral HAT evidence, not committed.
- Findings / fixes recorded in the flight log; if a fix is needed it lands in a new
  commit (no amend) and the affected step is re-verified.

---

## Post-Completion Checklist
- [x] All verification steps pass (operator-confirmed)
- [x] Flight log updated with HAT outcome
- [x] Leg status → `completed`
- [x] Flight finalized by the Flight Director (Phase 3)
