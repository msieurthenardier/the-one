# Squawk 0389: Mission 36 Flight 1 documents and the full-gate target

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-19
**Completed**: 2026-11-19

## Report
After Mission 36 Flight 1, three documents lag the code:
1. **The "Full-gate target" paragraph in CLAUDE.md** is from Mission 34 Flight 1: 43 minutes, from a 229 s unit tier plus a 2027 s browser run.
   - Flight 1's final gate was 308.75 s plus 2270 s, about 43.0 minutes, but on a loaded host.
   - Run the full gate on a quiet host (load below about 1.0).
   - Restate the target from that reading, with the 350 s unit target.
   - Re-budget any lane that moved more than 15%, per the quiet-host rule.
2. **`the_one/agents.md` should state the final HAT designs as the reference:**
   - the GleepGlorp setup state (a quiet next step, option A);
   - the shared notes list (option A, no edit);
   - the provider delete box shown on open.
   The flight log holds superseded versions of all three.
3. **CLAUDE.md's "Control library" paragraph** should name `App.ui.button`'s `tone: 'danger'` and `App.ui.confirm.disarm`. Both are in the catalogue.

## Evidence
- `CLAUDE.md` "Full-gate target (M34 F1 L02)".
- The flight log's "Flight-end review fixes and gate" (the loaded reading, start load 1.91) and its "Superseded HAT entries" paragraph.
- `docs/ui-control-inventory.md`, the `button` and `confirm` rows.

## Corrective Action
- `the_one/agents.md`: provider delete box now states the `aria-describedby` tie, `App.ui.confirm.disarm` on untick and the focus return after a failed forced delete; the notes Delete states `tone: 'danger'`; the notes list states board option A (no `size`/`showNumber`, title-line usage and Clear all); the setup line states the `aria-hidden` line plus status region. Other text already matched the shipped code.
- `CLAUDE.md` "Control library": names `App.ui.button` `tone: 'danger'` and `App.ui.confirm.disarm(el)`.
- Host was not quiet (start load 1.39), so no totals restated and no lane re-budgeted; the "Full-gate target" paragraph already stated the 350 s unit target and now records that the quiet re-measure is still owed.

## Verification
`make gate` (THE_ONE_TEST_NETNS=1, THE_ONE_REQUIRE_WEBKIT=1), start load 1.39, no other test processes: unit 10696 passed, 15 skipped in 307.14 s; browser `PARALLEL_RESULT rc=0 total=2211s lanes=20 failed=-`. No lane failed; no lane over budget (closest: mcp 316/330, agent-routines 281/300). `ruff check` and `ruff format --check` clean; `tests/test_run_tests_lanes.py` 19 passed.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), batch review of squawks 0386-0390
**Verdict**: confirmed (docs match the shipped code). The quiet-host re-measure of the full-gate total and lane budgets did not happen: the host was loaded (1.39). CLAUDE.md records it as owed, for the next quiet full gate.
**Commit**: `squawk: turnaround 2026-11-19` on flight/01-gleepglorp-exists-and-answers (PR #380)
