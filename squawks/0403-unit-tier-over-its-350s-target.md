# Squawk 0403: The unit tier runs over its 350 s target on a quiet host

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-23
**Completed**: 2026-11-24

## Report

The unit tier now takes about 385 s on a quiet host against its 350 s standing target, so by
`the_one/agents.md` the gate reads as regressed. The per-test cost is flat (about 0.034 s across
F3 and F4). The rise comes from test count (11898 passed), not from slower tests. The Mission 36
Flight 2 debrief already recommended raising the target to about 400 s or profiling with
`--durations`, and neither was done. Found by the Mission 36 Flight 4 debrief.

## Evidence
- **The F4 closing gate:** 11898 passed / 15 skipped in 387.43 s at `3178ae7d`, start load 0.74.
- **The F4 debrief's fresh run:** 384.03 s at `604e052c`.
- `the_one/agents.md` "Host policy" bullet: "the unit tier alone has a 350 s standing target … 387 s
  is 11% over it: re-check on the next quiet gate before raising".

## Corrective Action
Profiled on a quiet host (load 0.63, no other test process): `make test-unit`'s selection
(`-m 'not browser and not live and not pixel and not requires_bwrap'`) through `scripts/run-tests.sh`
with `THE_ONE_TEST_NETNS=1 --durations=0 --durations-min=0.5`: **12350 passed, 15 skipped in
456.76 s** (the F5 closing gate read 470 s). No code was changed; no clear, contained fix exists.

**Profile.** Per-phase sums: call 148 s, teardown 8.8 s, setup 4.6 s for the phases of 0.5 s or
more, 160 s in all. The other ~300 s is spread over about 37,000 phases under 0.5 s (about 0.008 s
each), so there is no single hotspot to remove. Top costs by file (seconds, tests of 0.5 s or more):
- `test_mcp_negotiation_fallback.py` 30.5 (five stdio tests at 2 to 4.4 s each: real
  negotiation-window waits against a stdio server; not an F5 file)
- `test_evals_gleepglorp_kinds.py` 15.7 (one test, "every variant of the ten F5 scenarios can pass
  offline", 11 s, plus one at 3.3 s; F5)
- `test_resolver_clip.py` 9.8 (one hypothesis property test, 7.1 s; not F5)
- `test_mcp_integration.py` 7.6, `test_fake_platforms.py` 7.4, `test_gleepglorp_kind_tool_config.py` 7.2
  (F5), `test_kb_manager.py` 6.0 (three 1.8 s fixture teardowns), `test_mcp_stdio_test_connect.py` 5.1
- no fixture stands out: teardown (kb_manager drain) and setup are small beside call time.

**Flight 5 files alone** (the 34 test files F5 added or changed, excluding `tests/browser/`),
run together at load about 2: 1450 passed in 97 s, about 0.067 s a test (the tier average is
0.037 s). Three files are 54 s of that: `test_gleepglorp_kind_tool_config.py` 25 s (a 20-field
normalize loop per tool in `test_each_tools_settable_set_is_exactly_the_table_plus_enabled`, about
0.7 s for each of about 30 tools, each normalize going through the DB; plus a `seed()` world per
test), `test_evals_gleepglorp_kinds.py` 17 s and `test_evals_gleepglorp_harness.py` 12 s (both run
every scenario variant offline through the eval harness). The rest of F5's files are small.

**Why not fixed.** Cutting these needs a change of test structure, not a mechanical one: sharing the
`seed()` world across the tool_config parametrized cases, or splitting or sampling the eval-variant
sweeps, changes what each test isolates and so is a design call. Replacing the real stdio waits in
`test_mcp_negotiation_fallback.py` with a fake clock touches the negotiation code's timing seam.
Together these would save at most about 60 to 70 s of 457 s, and the sweeps are the point of
those tests.

**Recommendation.** A further fix needs design work, and the cost is mostly test count and
per-test weight that F5 legitimately added (test count +4%, wall time +19% since the squawk was
logged; F5's 1450 tests are 12% of the tier and about 21% of its time). Raise the standing target
in `the_one/agents.md` to **500 s** (the F5 gate read 470 s and the profile run 457 s, so 500 s keeps
about 6% headroom). The operator decides; the target was not changed. If the operator prefers to
hold 350 s, the design work is: a shared module-scoped world for the tool_config kind tests, a
sampled or sharded eval-variant sweep, and a fake clock for the MCP negotiation window (about 60 to 70 s
saved, still 390 s or more).

**Decision and change (2026-11-24).** The operator chose to raise the standing target to 500 s. In
`the_one/agents.md` "Host policy" bullet of "Browser test lanes, budgets and run policy" the unit
target now reads 500 s (moved from 350 s at squawk 0403, with the profile cited), and the M36 F5
closing-gate sentence in the "Budget history" bullet records the same decision; earlier history is
kept and the 67-minute full-gate target is unchanged. The three speed-ups (a shared seeded world for
the tool_config kind tests, sampling the eval-variant sweeps, a fake clock for the MCP negotiation
window; about 60 to 70 s together) were not done, by operator decision.

## Verification
Profile recorded above; log at
`/tmp/claude-1000/-home-cprch-projects-the-one/1821e3c0-8ca0-4061-b85e-be991e1f3210/scratchpad/unit1.log`.
The tier is not back under 350 s; no change was made, so there is no after time. Resolution needs
the operator's decision on the target (or design work as described). The original check: a `--durations=30` profile of `make test-unit` on a quiet host is recorded. Then either the slowest
tests are fixed and the tier is back under 350 s, or the standing target in `the_one/agents.md` is
raised with the profile cited.

## Sign-Off
**Reviewer**: Reviewer agent (Haiku; no security-sensitive surface), batch review of squawks 0403, 0404, 0405, 0407, 0408, 0409 and 0410
**Verdict**: confirmed after one fix round (the stale "stays 350 s" sentence in the Host policy bullet was reworded as history). Unit tier on the final tree: 12350 passed, 15 skipped in 453 s, under the new 500 s target.
**Commit**: `squawk: turnaround 2026-11-24` on squawk/turnaround-2026-11-24
