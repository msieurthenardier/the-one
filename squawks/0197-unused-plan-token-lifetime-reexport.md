# Squawk 0197: unused re-export of `PLAN_TOKEN_LIFETIME_DAYS`

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: 2026-10-13

## Report
Sortie 03 defined `PLAN_TOKEN_LIFETIME_DAYS` in `the_one/llm/anthropic_oauth.py` (so `api.py` can read it without the SDK) and re-exported it from `anthropic_plan_provider.py`, but nothing imports the re-export. Remove it (and its mention in `the_one/agents.md`), or make it the one import site.

## Evidence
- `the_one/llm/anthropic_plan_provider.py:47` — `PLAN_TOKEN_LIFETIME_DAYS = anthropic_oauth.PLAN_TOKEN_LIFETIME_DAYS`.
- Only consumer: `the_one/interfaces/web/api.py` (~l.4990) reads `anthropic_oauth.PLAN_TOKEN_LIFETIME_DAYS`.
- `the_one/agents.md` ~l.1714 ("re-exported beside `OAUTH_BETA_HEADER`").

## Deferral
Deferred at the sortie 03 debrief. Revisit trigger: the next squawk batch.

## Corrective Action
Removed the unused `PLAN_TOKEN_LIFETIME_DAYS` re-export (and its comment) from `the_one/llm/anthropic_plan_provider.py`, plus the `anthropic_oauth` import that only served it (ruff F401). Reworded the `the_one/agents.md` mention to say `anthropic_oauth.py` is the one import site. Removal chosen over keeping the re-export: a repo-wide grep (the_one, tests, scripts, packaging, docs) found no importer and no `__all__`; the sole consumer, `api.py`, already reads `anthropic_oauth.PLAN_TOKEN_LIFETIME_DAYS`.

## Verification
- `grep -rn PLAN_TOKEN_LIFETIME_DAYS the_one tests scripts packaging docs`: only the definition, the api.py use, and prose references remain.
- `ruff check` / `ruff format --check the_one/llm/anthropic_plan_provider.py`: clean.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_anthropic_provider.py tests/test_plan_credentials.py tests/test_provider_api.py -x --timeout 30`: 341 passed.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget.
