# Leg: uat-and-alignment (HAT)

**Status**: completed
**Flight**: [Chat-loop Robustness & Control](../flight.md)

## Objective
Operator acceptance of the chat-loop fixes against a live instance.

## Verification performed (2026-06-21, live on :8485 with the new code)
- **No-hang (the original defect)** — called `http_request` AND `fetch_url` directly
  against the exact URL that hung in the repro
  (`https://stream.radioparadise.com/aac-320`): both returned in **0.3s** with
  `[error] looks like a media stream (type=audio/aac), not fetchable as text` (media
  short-circuit fires on response headers before the body is pulled). Was: infinite hang.
- **Interrupt/cancel** — over the WS: started a long turn, sent `{action:"cancel"}`
  mid-flight → received `{"type":"cancelled"}`; a follow-up message on the same
  session then responded normally ("RECOVERED.") → the session lock is released.
- **Full regression** — `3489 passed / 10 skipped / 0 failures`, ruff clean,
  flight-wide review `[HANDOFF:confirmed]`.

## Operator-deferred (UI eyeball)
The two purely-visual UI checks — the stop control appearing during a turn and the
queued-message pending indicator — are left to the operator against the running
:8485 instance (and confirmed in the real installed app after the next installer
rebuild). The behavior-test spec `tests/behavior/chat-loop-hang-and-cancel.md`
remains available to run via `/behavior-test chat-loop-hang-and-cancel`.

## Outcome
Operator accepted the live verification (2026-06-21). Flight landed.

---

## Post-Completion Checklist
- [x] Core behaviors verified live (no-hang, cancel, lock-release)
- [x] Operator acceptance recorded
- [x] Update flight-log.md
- [x] Set this leg's status to `completed`
