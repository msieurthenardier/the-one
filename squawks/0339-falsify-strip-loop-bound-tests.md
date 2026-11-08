# Squawk 0339: falsify the Anthropic strip loop's repeat-refusal tests

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-08
**Completed**: 2026-11-08

## Report
The provider's bounded strip-and-retry loop (`the_one/llm/anthropic_provider.py`, `complete` and `stream`) terminates because each strip fires only while its key is still in kwargs. The tests that pin "a repeat refusal re-raises instead of looping" were never shown to fail with that guard removed. If the guard were broken, a test might hang or pass instead of failing. Falsify each one: remove the presence check by editing, see the test fail within its timeout, then put the check back by editing.

## Evidence
- `tests/test_anthropic_prompt_caching.py`: `test_complete_repeat_temperature_400_reraises_not_loops` (~260), `test_complete_repeat_cache_400_reraises_not_loops` (~271), `test_stream_repeat_400_reraises_with_tool_name` (~341).
- The leg 1 report falsified only the DD2 sum, the TypeError-then-temperature composition and `_cache_disabled` persistence (`sorties/14-anthropic-prompt-caching/flight-log.md`).
- Raised at the sortie 14 debrief, recommendation 3.

## Corrective Action
Each guard was removed by editing `the_one/llm/anthropic_provider.py`, the test run, and the guard restored by editing (provider ends with no diff against HEAD). No test change was needed; no provider behaviour changed.

- `test_complete_repeat_temperature_400_reraises_not_loops`: removed `and "temperature" in kwargs` in `_strip_for_bad_request`. The test FAILED (0.69 s, no hang): the second 400 stripped again and the loop made a third call, which the recorder could not serve, so `pytest.raises(BadRequestError)` was not satisfied.
- `test_stream_repeat_400_reraises_with_tool_name`: same guard (shared by `stream`). FAILED (0.72 s, `IndexError` from the exhausted stream recorder on the third attempt).
- `test_complete_repeat_cache_400_reraises_not_loops`: removed the `if "cache_control" not in kwargs: return False` guard in `_strip_cache_markers`. FAILED (0.71 s); the log shows the cache strip firing twice.

There is no independent attempt cap: the guards are the only bound. The tests fail by the recorder running out of scripted responses rather than by a pinned call count, which is sufficient and bounded.

## Verification
Each named test fails, rather than hanging, with the presence guard removed; `--timeout` keeps a would-be loop bounded. Each passes with the guard restored. `.venv/bin/python -m pytest tests/test_anthropic_prompt_caching.py -q -x --timeout 30` is green.

Results: all three named tests failed with their guard removed (see Corrective Action) and passed with it restored. `.venv/bin/python -m pytest tests/test_anthropic_prompt_caching.py -q -x --timeout 30`: 30 passed. `.venv/bin/ruff check the_one/ tests/`: all checks passed. `.venv/bin/ruff format --check the_one/ tests/`: 830 files already formatted. `git diff HEAD -- the_one/llm/anthropic_provider.py`: empty.

## Sign-Off
**Reviewer**: Reviewer agent (Haiku; no security-sensitive surface), batch review of the 2026-11-08 squawk turnaround, scoped to the diff: `[HANDOFF:confirmed]`, no blocking issues. It re-ran `test_db_codec`, `test_anthropic_prompt_caching`, `test_evals_cache_probe`, `test_evals_freeze` and `test_evals_cli` (217 passed) and ruff check and format (clean). It confirmed no diff in the provider or the test file, and that the two `while True` loops are bounded only by the presence guards the record names. It accepted the falsification timings on the record, since a reviewer does not edit files.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-08` commit on `squawk/turnaround-2026-11-08`.
