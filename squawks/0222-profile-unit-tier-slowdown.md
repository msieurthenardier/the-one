# Squawk 0222: Profile the unit tier's unexplained slowdown

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-15
**Completed**: —

## Report
`make test-unit` has slowed from about 195 s (sortie 03) to 281-289 s (sortie 04; Mission 31 Flight 1), roughly +45%, while the test count grew only about 11% (6019 → 6705). No debrief has explained it. The sortie 04 debrief asked for a `--durations` profile first; nobody has run one.

Run the unit tier with `--durations=40` on a quiet host and compare against the sortie 03 era if you can. Name the slowest tests, and fix any obvious regression or record the cause. Typical causes: a fixture that lost its template-DB fast path, a sleep-based wait, or an eval-runner test doing real work.

## Evidence
- `sorties/03-claude-plan-token/flight-debrief.md` (unit 194.8 s);
- `sorties/04-honest-mcp-sign-in/flight-debrief.md` (288.6 s, "profile with `--durations` first");
- `missions/31-control-library-everywhere/flights/01-library-completion-and-pilot/flight-debrief.md` (281 s).

## Corrective Action
*(written at completion)*

## Verification
The `--durations` output is recorded in the corrective action. Either the unit tier returns near its expected time for the current test count, or the cause is documented with a follow-up.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
