# Squawk 0384: Documents and tidy-ups left by sortie 19's negotiation change

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-18
**Completed**: —

## Report
The sortie 19 debrief found wording that does not yet say what the code does, and one dead line. No behaviour changes.

1. `the_one/agents.md` (the negotiation paragraph and the MCP editor notes) does not say: that "remembered only the second time in a row" counts successive successful connects of any client for the source, a Test included, so two unchanged Tests that both fall back make later chat connects skip the check; that two clients connecting at the same moment each count; that a failed connect resets the count and a cancelled one does not; and that an agent Test with per-agent credentials never changes the shared fallback note.
2. `the_one/mcp/_era.py`'s module docstring says the unlocked maps are safe because there is one event loop. Add what the count means (point 1).
3. `the_one/mcp/_negotiate.py`: the reason the first probe of an attempt is not bounded by the window is in an inline comment in `_probe`; the module docstring's "Patient probe" passage should say it. In `_probe`, the flag is set to false again after a successful send, where it is already false: remove that line.
4. `the_one/mcp/_era.py::remember_era` has no caller left outside tests (the client calls `record_result`). Say so in its docstring, or remove it and move the tests that seed the memory to `record_result`.
5. `sorties/19-local-mcp-servers-newest-protocol/flight.md` is a record and is not edited; the debrief already notes that DD2's "the handshake keeps the full reserve" does not hold for the one probe the recovery sends.

## Evidence
- `the_one/mcp/_era.py::record_result`, `::forget_era` — the count's rules.
- `the_one/mcp/client.py::_connect_once` — `_era.record_result(...)` runs for every successful connect when `record_era` is true; `connect` calls `forget_era` on a failure and re-raises a cancellation before it.
- `the_one/mcp/_negotiate.py::_probe` — the `first or left <= 0` branch and its comment; the repeated `state.no_answer = False`.
- `sorties/19-local-mcp-servers-newest-protocol/flight-debrief.md`, "What Could Be Improved".

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
