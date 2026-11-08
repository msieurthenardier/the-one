# Squawk 0339: falsify the Anthropic strip loop's repeat-refusal tests

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-08
**Completed**: —

## Report
The provider's bounded strip-and-retry loop (`the_one/llm/anthropic_provider.py`, `complete` and `stream`) terminates because each strip fires only while its key is still in kwargs. The tests that pin "a repeat refusal re-raises instead of looping" were never shown to fail with that guard removed. If the guard were broken, a test might hang or pass instead of failing. Falsify each one: remove the presence check by editing, see the test fail within its timeout, then put the check back by editing.

## Evidence
- `tests/test_anthropic_prompt_caching.py`: `test_complete_repeat_temperature_400_reraises_not_loops` (~260), `test_complete_repeat_cache_400_reraises_not_loops` (~271), `test_stream_repeat_400_reraises_with_tool_name` (~341).
- The leg 1 report falsified only the DD2 sum, the TypeError-then-temperature composition and `_cache_disabled` persistence (`sorties/14-anthropic-prompt-caching/flight-log.md`).
- Raised at the sortie 14 debrief, recommendation 3.

## Corrective Action
*(written at completion)*

## Verification
Each named test fails, rather than hanging, with the presence guard removed; `--timeout` keeps a would-be loop bounded. Each passes with the guard restored. `.venv/bin/python -m pytest tests/test_anthropic_prompt_caching.py -q -x --timeout 30` is green.
