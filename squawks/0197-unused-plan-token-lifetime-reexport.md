# Squawk 0197: unused re-export of `PLAN_TOKEN_LIFETIME_DAYS`

**Status**: deferred
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: —

## Report
Sortie 03 defined `PLAN_TOKEN_LIFETIME_DAYS` in `the_one/llm/anthropic_oauth.py` (so `api.py` can read it without the SDK) and re-exported it from `anthropic_plan_provider.py`, but nothing imports the re-export. Remove it (and its mention in `the_one/agents.md`), or make it the one import site.

## Evidence
- `the_one/llm/anthropic_plan_provider.py:47` — `PLAN_TOKEN_LIFETIME_DAYS = anthropic_oauth.PLAN_TOKEN_LIFETIME_DAYS`.
- Only consumer: `the_one/interfaces/web/api.py` (~l.4990) reads `anthropic_oauth.PLAN_TOKEN_LIFETIME_DAYS`.
- `the_one/agents.md` ~l.1714 ("re-exported beside `OAUTH_BETA_HEADER`").

## Deferral
Deferred at the sortie 03 debrief. Revisit trigger: the next squawk batch.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*
