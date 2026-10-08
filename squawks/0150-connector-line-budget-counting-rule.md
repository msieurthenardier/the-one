# Squawk 0150: The connector line budget has no recorded counting rule

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-08
**Completed**: 2026-10-08

## Report
Mission 23 set a 3,000-line Python budget for connectors and closed at "2,970 / 3,000". Nothing records how that is counted: `the_one/connectors/*.py` alone is 2,553 lines, and the total only reconciles once the connector tools (417) are added. The next platform will face a live budget decision with no reproducible measurement. Found by routine maintenance 2026-10-08 (finding #26).

## Evidence
- `missions/23-connector-reset/mission-debrief.md` — "package 2,553 + tools 417"
- `the_one/connectors/README.md` — no budget or counting command

## Corrective Action
Added a "Size budget" section to `the_one/connectors/README.md`: 3,000 Python lines over the `the_one/connectors/` package plus `the_one/tools/connector_{send,lookup,history}.py`, counted with plain `wc -l` (blank lines, comments and docstrings all count), with the exact command and a note that a new platform needs an explicit trim-or-raise decision.

## Verification
`find the_one/connectors -name '*.py' | xargs cat the_one/tools/connector_*.py | wc -l` prints `2970` on HEAD (package 2553 + tools 417: send 204, lookup 108, history 105). The same file set reproduces 2970 at commit 327c015 (the Mission 23 close; 66aad47, Flight 4, gave 2950).

## Sign-Off

**Reviewer**: independent batch Reviewer (Sonnet tier: the batch touches the credential-gated test seams and secret echo in 422 bodies), plus a Haiku re-review of the one fix-loop change (`tests/test_store_static.py`, a static guard that pinned the pre-0145 fetch literal); unit suite 5647 passed, 1 failed before the guard fix (the guard, re-run green after), 16 skipped (10 Windows-only, 2 root-only under `THE_ONE_TEST_NETNS=1`, 4 `requires_bwrap` sandbox skips included by the run's marker set); agents lane 154 passed, 2 skipped; shared lane 465 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-08` on branch `squawk/turnaround-2026-10-08`
