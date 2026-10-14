# Squawk 0193: `make up` verify-serving still checks provider files sortie 02 moved

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: 2026-10-13

## Report
`make up` / `make restart` end with `verify-serving`, which curls a fixed list of admin static files. Since sortie 02 moved the provider editor into Library, three entries no longer exist under `areas/admin/`, so every `make up` prints `✗ admin/providers-list.js returned 404` and exits non-zero although the server is serving. Found while starting the sortie 03 live-verification dev instance.

## Evidence
- `Makefile` `verify-serving` loop (~l.154): lists `admin/providers-list.js` (deleted in sortie 02), `admin/provider-editor.js` and `admin/provider-models.js` (moved to `areas/studio/`).
- Sortie 03 flight log, `live-verification` (2026-10-12).

## Deferral
Deferred mid-flight (sortie 03). Revisit trigger: the next squawk batch after the sortie 03 debrief, or the next time `Makefile` is touched. Workaround: the instance is up when `/api/live` answers.

## Corrective Action
Replaced the literal admin asset list in the Makefile's `verify-serving` loop with a list derived from disk: `admin.js` plus `find admin -name '*.js'` under a new `ADMIN_JS_ROOT` variable (`the_one/interfaces/web/static/js/areas`). Derivation was chosen over trimming the literal list so the check cannot go stale again when files move. Credential handling is untouched (squawk 0195 is separate). New unit test `tests/test_makefile_verify_serving.py` asserts the literal list is gone and that every derived file exists. Squawk 0198 is a duplicate of this one and is closed by the same change.

## Verification
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_makefile_verify_serving.py -x --timeout 30`: 2 passed.
- `ruff check` / `ruff format --check` on the new test: clean.
- Live: `THE_ONE_PORT=8496 THE_ONE_DATA_DIR=/tmp/claude-1000/sq0193 make up` (credential minted first): every admin asset served 200 (including previously unlisted ones), port ownership check passed, exit 0; then `make down` on the same port/dir.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget. Closes duplicate 0198 with the same change.
