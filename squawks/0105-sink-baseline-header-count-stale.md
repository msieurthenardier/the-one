# Squawk 0105: `DYNAMIC_SINK_BASELINE` header comment carries a stale site count

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-09-30
**Completed**: 2026-10-01

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

Reworded the header comment above `DYNAMIC_SINK_BASELINE` in `tests/test_ui_guards.py` (M25 F1 L1): it no longer restates a live site or file count; it says the dict is the authoritative current truth, that removals never fail the ratchet, and that static sites are exempt. Original suggestion kept for reference:

Reword the comment so it describes the history without a live count that can
go stale (for example, "counts at freeze time were …; the dict below is the
current truth"), or refresh it and add a note that the dict is authoritative.

## Verification

`grep -n "92 sites" tests/test_ui_guards.py` returns nothing; `tests/test_ui_guards.py` passes. Original check:

Read-back: `tests/test_ui_guards.py` still passes.

## Sign-Off

**Reviewer**: Flight 1 Reviewer agent (Sonnet) — flight-scoped review
**Verdict**: confirmed
**Commit**: `flight/1: control library foundation — App.ui factories, deep violet, WebKit apparatus` on branch `flight/01-control-library-foundation`
