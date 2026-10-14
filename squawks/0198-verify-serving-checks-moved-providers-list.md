# Squawk 0198: `make verify-serving` checks a moved file and always fails

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: 2026-10-13

## Report
`make up` (and `make verify-serving`) fails against a healthy instance:
`✗ admin/providers-list.js returned 404 — not serving`. Sortie 2 (Model providers in Library) moved the provider list out of `static/js/areas/admin/`, but the Makefile's asset list still names `admin/providers-list.js`, so the check cannot pass. Found during Mission 29 Flight 1's HAT, on a dev instance on port 8492.

## Evidence
- `Makefile` `verify-serving` asset loop (~154): `for f in admin.js admin/system-page.js admin/providers-list.js admin/provider-editor.js admin/provider-models.js …`
- `ls the_one/interfaces/web/static/js/areas/admin/` has no `providers-list.js`, `provider-editor.js` or `provider-models.js` (moved by `f88b5a0`, "sortie/2: model providers move to Library").
- Every other listed asset returned 200 on the same instance.

## Corrective Action
Replaced the literal admin asset list in the Makefile's `verify-serving` loop with a list derived from disk: `admin.js` plus `find admin -name '*.js'` under a new `ADMIN_JS_ROOT` variable (`the_one/interfaces/web/static/js/areas`). Derivation was chosen over trimming the literal list so the check cannot go stale again when files move. Credential handling is untouched (squawk 0195 is separate). New unit test `tests/test_makefile_verify_serving.py` asserts the literal list is gone and that every derived file exists. Duplicate of squawk 0193; both are closed by this same change.

## Verification
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_makefile_verify_serving.py -x --timeout 30`: 2 passed.
- `ruff check` / `ruff format --check` on the new test: clean.
- Live: `THE_ONE_PORT=8496 THE_ONE_DATA_DIR=/tmp/claude-1000/sq0193 make up` (credential minted first): every admin asset served 200 (including previously unlisted ones), port ownership check passed, exit 0; then `make down` on the same port/dir.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget. Duplicate of 0193, closed by the same change.

## Disposition
**Deferred**: out of scope for Mission 29 Flight 1 (MCP SDK port), logged mid-flight per the agentic workflow. Revisit at the next squawk turnaround, or the next time the Makefile is touched.
