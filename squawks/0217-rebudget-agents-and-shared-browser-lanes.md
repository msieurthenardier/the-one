# Squawk 0217: Re-budget the `agents` and `shared` browser lanes

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-15
**Completed**: 2026-10-22

## Report
Two browser lanes now run at or over their wall-clock budgets in a `--parallel 3` gate. `agents` read 504, 501, **523**, 503 and 500 s against 510 across sortie 04's gates (506 at sortie 03, whose debrief already asked for a re-budget). `shared` read 283, 292, **302**, 300 and 301 s against 300, growing with every shared-lane browser test. Over budget is only a warning, so the next flight that adds browser tests will make the warning permanent noise. Re-budget from the current measurements (proposed: `agents` about 560, `shared` about 330), keeping the same "+~10% headroom, rounded to 30 s" style.

## Evidence
- `scripts/run-tests.sh` budget table (`[agents]=510`, `[shared]=300`, ~l.57-68) and the `--help` text that prints it (~l.85).
- CLAUDE.md "Lane time budgets" table (`agents` 510 / 459, `shared` 300 / 235, ~l.368-373), last re-measured at sortie 02.
- `sorties/04-honest-mcp-sign-in/flight-debrief.md` "Test Metrics"; `sorties/03-claude-plan-token/flight-debrief.md`.

## Corrective Action
Re-measured in the Mission 31 Flight 2 close (leg 11) full `make gate` (`--parallel 3`): `agents` 672 s against 510 (1.32x, past the 1.3x rule), `shared` 268 s, `contracts` 374 s, `chats` 346 s, `mcp` 341 s. `agents` was split into `agents` (427 s measured, budget 540) and `agent-tabs` (the self-configuration, Rules and notes and Tools-override files; 233 s, budget 300) in `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py` and CLAUDE.md's lane table and descriptions. `contracts` (480), `chats` (450) and `mcp` (450) were re-set to measured plus 25% rounded to 30 s; `shared` stays 300 (268-270 s). CLAUDE.md's table now matches the script.

## Verification
`tests/test_run_tests_lanes.py` (pins the budget table: every canonical lane once) green (14 passed); the `--parallel 3` run after the split shows no OVER BUDGET lane (routing 503/600, agents 427/540, providers 306/420, contracts 367/480, chats 346/450, mcp 341/450, agent-tabs 233/300, library 246/300, settings 234/300, shared 270/300); CLAUDE.md's table matches the script.

## Sign-Off
**Reviewer**: Mission 31 Flight 2 flight review (independent Sonnet Reviewer, 2026-10-22; cycles 1-2)
**Verdict**: [HANDOFF:confirmed]
**Commit**: the Flight 2 commit for legs 08b-11 on `flight/02-agents-on-the-library` (see the Flight 2 draft PR)
