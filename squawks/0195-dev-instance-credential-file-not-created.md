# Squawk 0195: a fresh `make up` data dir has no `api-credential`, contrary to CLAUDE.md

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: 2026-11-03
**Related**: 0278: the same gap logged twice (`serve` never creates the credential file, CLAUDE.md says it does); complete together ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report
CLAUDE.md's "Behavior-test credential convention" says a fresh instance "creates the file on first launch". A host-native `make up` on a scratch data dir does not: `get_credential()` is create-on-first-use and the server never calls it at startup, so `make up`'s `verify-serving` stops with "no local API credential found" and a behavior-test Executor has no credential to read. Sortie 03 leg 2 had to run `rotate-api-credential` and restart. Fix one or the other: the doc, or create the credential at server startup. Read the code first to see which is intended.

## Evidence
- `the_one/api_credential.py::get_credential` — "Return the current credential, creating it on first use."
- CLAUDE.md, "Behavior-test credential convention" §1 ("start the instance first (it creates the file on first launch)").
- Sortie 03 flight log, `live-verification` (2026-10-12); debrief Recommendation 1.

## Deferral
Deferred at the sortie 03 debrief. Revisit trigger: the next squawk batch (with 0193, 0194), or before the next live behavior test on a scratch data dir.

## Corrective Action
Merged into [0278](0278-claude-md-serve-credential-creation.md); the doc was the side fixed (CLAUDE.md step 1, plus SECURITY-MODEL.md's "Created on first use"). `serve` still does not create the credential; the instruction is to run `the-one rotate-api-credential`.

## Verification
See 0278: live scratch `serve` had no `api-credential`; after `rotate-api-credential` a bearer `curl` to `/api/agents` returned 200 (401 before).

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs. Completed together with 0278 (merged at triage).
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

## Disposition
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** the trigger has fired. **Merged into [0278](0278-claude-md-serve-credential-creation.md):** one CLAUDE.md fix closes both, using `the-one rotate-api-credential` rather than claiming `serve` creates the file. The code-side alternative (create it on serve) is security-sensitive and out of squawk scope. Complete together in the next turnaround.
