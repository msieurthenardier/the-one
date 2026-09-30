# Squawk 0105: `DYNAMIC_SINK_BASELINE` header comment carries a stale site count

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-30
**Completed**: —

## Report

The header comment above `DYNAMIC_SINK_BASELINE` says the baseline was
"Re-baselined in M17 F4 L1 to the live 92 sites across 27 files" (65 static).
After squawk 0104 the live classifier reports 68 dynamic sites across 21 files
(63 static). The drift started before 0104 and has built up as later flights
removed sites. Nothing asserts the number, so it is prose that will keep going
stale. Found by the squawk 0103/0104 Reviewer.

## Evidence

- `tests/test_ui_guards.py` — the comment block preceding `DYNAMIC_SINK_BASELINE` ("…to the live 92 sites across 27 files…").
- `classify_sinks()` currently returns 68 dynamic sites across 21 files.

## Corrective Action

*(written at completion)*

Reword the comment so it describes the history without a live count that can
go stale (for example, "counts at freeze time were …; the dict below is the
current truth"), or refresh it and add a note that the dict is authoritative.

## Verification

*(written at completion)*

Read-back: `tests/test_ui_guards.py` still passes.

## Sign-Off

*(written at completion)*
