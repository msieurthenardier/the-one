# Squawk 0282: Re-author the `mcp-sensitive-headers-round-trip` spec's follow-ups from its 2026-10-28 run

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-28
**Completed**: 2026-11-03
**Related**: 0256, 0281: behavior-spec follow-ups; complete together in one spec-edit pass ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report
The HAT-close run of `tests/behavior/mcp-sensitive-headers-round-trip.md` passed 8/8. The run listed four spec-quality follow-ups, deliberately not edited at the run. Apply them.

## Evidence
`tests/behavior/mcp-sensitive-headers-round-trip/runs/2026-10-28-14-36-06.md`, Orchestrator Notes ("Spec follow-ups"):
- Step 6: split the re-store precondition from the judged key change, or require evidence of the stored state first.
- Steps 5 and 7: add a note on the different storage of an empty value (in `config` when not sensitive, in `secrets` when sensitive).
- Step 8: name the before/after API diff as the evidence.
- Out of Scope: mention the automatic connection-status line.

## Corrective Action
Edited `tests/behavior/mcp-sensitive-headers-round-trip.md`: step 6 is split into 6a (setup, no judgment: re-store with `S1` and record the API evidence that `secrets.Authorization` is `***...1111`, stop if not) and 6b (the judged key change); steps 5 and 7 carry a note that an empty value lives in `config.headers` when not sensitive and in `secrets` when sensitive; step 8 names the before/after `GET /api/mcp-sources/{SRC}` diff around Cancel as the evidence; Out of Scope mentions the automatic connection-status line. Per 0213 the spec already used `$HOME`; it gained example `$HOME/the-one-behavior-test-scratch/mcp-headers/{data,cwd}` paths, stop-by-PID and the `rotate-api-credential` step. The step numbering now has 6a/6b, so the Variants "steps 1-8" wording still holds.

## Verification
No behavior test was run (not requested). Re-read the edited spec: format intact. `THE_ONE_TEST_NETNS=1 make test-unit`: 8724 passed, 15 skipped (no test reads `tests/behavior/` specs; the only grep hit, `tests/test_unused_selectors_script.py`, uses a temp tree). No new tests, so no falsification.
Each of the four items is reflected in the spec, and the spec still validates against ARTIFACTS.md's format.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
