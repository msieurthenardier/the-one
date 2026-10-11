# Squawk 0182: The date line can name `current_time` to a tool-less model, and the preview clock has no parity pin

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: 2026-10-11

## Report
(a) `time_tool_available` treats a `supports_tools()` timeout or error as "yes". If the build-time probe times out and the turn-time probe in `core.py` later returns False, a chat-only model's degraded prompt keeps the suffix, so the date line names `current_time`, a tool it cannot call. That breaks Mission 28's "a model running without tools never sees the tool named". Prompt wording must be true under every fallback, so a probe failure should mean "no tool" **for the wording only**, while the tool stays registered. (b) The Date and time page's preview clock is formatted by Python `time_zones._clock` and claims to match the app's `App.time.formatClock`. No test pins the two together.

## Evidence
`the_one/agent/prompt_layers.py::time_tool_available`; `the_one/agent/core.py:~271, ~459-460`; `static/js/areas/admin/date-time-page.js` (~221, preview clock). The fix: (a) a separate wording predicate that fails closed, plus a unit test; (b) draw the preview clock client-side with `App.time.formatClock`, or add a parity test.

Logged from the Mission 28 mission debrief (mission Architect).

## Corrective Action
(a) `time_tool_available` (used only for the date line's `tool_available=` wording, in `factory.py` and `pending.py`) now fails CLOSED: a `supports_tools()` timeout or error returns False, so the prompt takes the tool-free wording. Tool registration, seeding and dispatch and `core.py` are untouched. Docstring, `agents.md` and the matrix test updated. (b) The Date and time page's preview clock is now drawn client-side: `patchPreview` calls `App.time.applySettings(settings)` then `App.time.formatClock(new Date())`, so it matches the app's formatter by construction. `preview.clock` stays in the API (additive; pinned by existing API tests).

## Verification
Unit and browser runs below (see report): `tests/test_prompt_layers.py` matrix now asserts timeout, exception and no-llm give False; browser `test_flow_settings_date_time.py` clock shape assertion unchanged and passing.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of the 2026-10-11 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-11` commit on `squawk/turnaround-2026-10-11`. The final gate passed: unit 5946 passed and 14 skipped; `PARALLEL_RESULT rc=0 total=977s lanes=8 failed=-`, every lane within budget.
