# Squawk 0278: CLAUDE.md says `the-one serve` creates `api-credential` on first launch; it never does

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-28
**Completed**: —
**Related**: 0195: the same gap logged twice (`serve` never creates the credential file, CLAUDE.md says it does); complete together ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report
The behavior-test credential section of CLAUDE.md says that when `<data_dir>/api-credential` is missing you should "start the instance first (it creates the file on first launch)". That is wrong for `the-one serve`, which every behavior test uses. On a fresh scratch data dir no file appears, and every authenticated request gets a 401. Both Executors in the M31 F6 HAT-close spec runs hit this and recovered by running `rotate-api-credential` themselves (run logs `tests/behavior/agent-step-limit-notice/runs/2026-10-28-14-36-06.md` and `tests/behavior/mcp-sensitive-headers-round-trip/runs/2026-10-28-14-36-06.md`, Orchestrator Notes). Fix the instruction so the next run does not start with a 401.

## Evidence
- `CLAUDE.md:533` reads: "(it creates the file on first launch) or run".
- `the_one/api_credential.py:get_credential` (`:297`) is the only create-on-first-use path. It is called only from `the_one/interfaces/desktop/takeover.py` (`:69`, `:259`), which is the desktop app.
- `the_one/api_credential.py:lookup_credential` (`:330`) is read-only. Its docstring (`:345`) says it raises when nothing has ever called `get_credential()`.
- `the_one/main.py:16` uses the read-only lookup.

## Corrective Action
*(written at completion)*
Likely fix: reword CLAUDE.md's step 1 to say that a fresh `serve` instance has no credential file, and to run `THE_ONE_DATA_DIR=<dir> the-one rotate-api-credential` before the first authenticated request (the desktop app creates one, `serve` does not). Also check `.flightops/agent-crews/behavior-tests-execution.md` and any spec Preconditions that repeat the claim.

## Verification
*(written at completion)*
`grep -rn "first launch" CLAUDE.md .flightops tests/behavior` finds no claim that `serve` creates the file. One manual check: a fresh scratch `serve` plus `rotate-api-credential` gives a working bearer token.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
