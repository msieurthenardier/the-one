# Squawk 0384: Documents and tidy-ups left by sortie 19's negotiation change

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-18
**Completed**: 2026-11-21

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
1. `the_one/agents.md` (negotiation paragraph, after "Era count"; MCP editor "protocol-fallback note" paragraph): documents what "second time in a row" counts (successive successful connects of any client, Test included; concurrent clients each count; a failed connect resets via `forget_era`; a cancelled one does not). Checked against `client.py::connect` and `::_connect_once`. One correction to the squawk's wording: the agent Test route (`mcp_agent_test.py`) always passes `record_era=False`, so it never touches the count at all; and only the per-agent-credential case writes no shared cache (`cache_write="none"`). An agent Test with no credential override uses `shared_no_posture`, which writes the shared cache and deletes `protocol_fallback`. The docs say exactly this.
2. `the_one/mcp/_era.py` module docstring: added the count's meaning; also fixed its stale statement that `remember_era` is called from the connect path (it is `record_result`).
3. `the_one/mcp/_negotiate.py` module docstring: added the paragraph on why the first (and a no-time-left) probe is not bounded by the window, noting DD2's full-reserve claim does not hold for that one probe. Removed the redundant `state.no_answer = False` after the successful send in `_probe` (the flag is reset at the top of every loop iteration and the only path setting it true raises, so it is already false there).
4. `_era.py::remember_era`: chose the docstring note ("No production caller ... used by tests to seed the memory"); removal would touch ~10 test call sites across five files.
5. Not touched, as instructed.

## Verification
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_mcp_negotiate.py tests/test_mcp_era.py -x --timeout 60`: 103 passed.
- `tests/test_mcp_negotiation_fallback.py tests/test_mcp_test_connection_negotiation.py` same runner: 43 passed.
- `.venv/bin/ruff check` and `ruff format --check` on `_era.py`, `_negotiate.py`: clean.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the security tier, since the batch changed the shell-write hook and CLAUDE.md's safety rules), batch review of squawks 0368, 0379, 0384, 0385, 0391-0397
**Verdict**: confirmed
**Commit**: `squawk: turnaround 2026-11-21` on squawk/turnaround-2026-11-21
