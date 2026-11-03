# Squawk 0278: CLAUDE.md says `the-one serve` creates `api-credential` on first launch; it never does

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-28
**Completed**: 2026-11-03
**Related**: 0195: the same gap logged twice (`serve` never creates the credential file, CLAUDE.md says it does); complete together ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report
The behavior-test credential section of CLAUDE.md says that when `<data_dir>/api-credential` is missing you should "start the instance first (it creates the file on first launch)". That is wrong for `the-one serve`, which every behavior test uses. On a fresh scratch data dir no file appears, and every authenticated request gets a 401. Both Executors in the M31 F6 HAT-close spec runs hit this and recovered by running `rotate-api-credential` themselves (run logs `tests/behavior/agent-step-limit-notice/runs/2026-10-28-14-36-06.md` and `tests/behavior/mcp-sensitive-headers-round-trip/runs/2026-10-28-14-36-06.md`, Orchestrator Notes). Fix the instruction so the next run does not start with a 401.

## Evidence
- `CLAUDE.md:533` reads: "(it creates the file on first launch) or run".
- `the_one/api_credential.py:get_credential` (`:297`) is the only create-on-first-use path. It is called only from `the_one/interfaces/desktop/takeover.py` (`:69`, `:259`), which is the desktop app.
- `the_one/api_credential.py:lookup_credential` (`:330`) is read-only. Its docstring (`:345`) says it raises when nothing has ever called `get_credential()`.
- `the_one/main.py:16` uses the read-only lookup.

## Corrective Action
Docs only (no code change; creating the credential on `serve` is security-sensitive and out of scope). Root cause: `get_credential()` (create-on-first-use) is called only by the desktop takeover; `serve` uses the read-only `lookup_credential`. Changes:
- `CLAUDE.md` "Behavior-test credential convention" step 1: replaced the "start the instance first (it creates the file on first launch)" sentence with the truth (fresh `serve`/`make up` data dir has no `api-credential`, every authenticated request is 401 until `THE_ONE_DATA_DIR=<dir> the-one rotate-api-credential` is run; it may run before or after the instance starts).
- `SECURITY-MODEL.md` (~l.103): "Created on first use" now says first use by the desktop app, not `serve`.
- Grepped `tests/behavior/*.md`, `the_one/agents.md`, `docs/`, `.flightops/agent-crews/`, `Makefile`: no other file claims `serve` creates it (the specs that mention rotate-api-credential already say to run it; the only "first launch" hits are unrelated desktop-install text).

## Verification
Live, scratch instance (port 8491, data dir `$HOME/the-one-behavior-test-scratch/0278/data`, ownership confirmed via `/proc/<pid>/environ`, stopped by recorded PID): after `serve` start the data dir held no `api-credential`; `GET /api/live` 200, `GET /api/agents` without credential 401; after `THE_ONE_DATA_DIR=<dir> the-one rotate-api-credential` (server still running) the file existed and `curl -H "Authorization: Bearer $(cat api-credential)" /api/agents` returned 200.
`grep -rn "first launch" CLAUDE.md .flightops tests/behavior` finds no claim that `serve` creates the file (remaining hits are desktop-app first-launch text). No new tests.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

## Disposition
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** [0195](0195-dev-instance-credential-file-not-created.md) is merged into this one; complete them together.
