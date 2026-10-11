# Squawk 0182: The date line can name `current_time` to a tool-less model, and the preview clock has no parity pin

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-11
**Completed**: —

## Report
(a) `time_tool_available` treats a `supports_tools()` timeout or error as "yes". If the build-time probe times out and the turn-time probe in `core.py` later returns False, a chat-only model's degraded prompt keeps the suffix, so the date line names `current_time`, a tool it cannot call. That breaks Mission 28's "a model running without tools never sees the tool named". Prompt wording must be true under every fallback, so a probe failure should mean "no tool" **for the wording only**, while the tool stays registered. (b) The Date and time page's preview clock is formatted by Python `time_zones._clock` and claims to match the app's `App.time.formatClock`. No test pins the two together.

## Evidence
`the_one/agent/prompt_layers.py::time_tool_available`; `the_one/agent/core.py:~271, ~459-460`; `static/js/areas/admin/date-time-page.js` (~221, preview clock). The fix: (a) a separate wording predicate that fails closed, plus a unit test; (b) draw the preview clock client-side with `App.time.formatClock`, or add a parity test.

Logged from the Mission 28 mission debrief (mission Architect).

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
