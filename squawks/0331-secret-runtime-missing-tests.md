# Squawk 0331: Three missing secret-runtime tests

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-05
**Completed**: 2026-11-05

## Report
The sortie 10 debrief Developer found three untested cases in the secret runtime. The code is believed correct in each case, but nothing pins it:
1. A stored value with regex metacharacters, e.g. `a.b*(c)[d]|e`, is masked literally and matches nothing else. `build_masker` uses `re.escape`.
2. A `{{secret:key}}` inside a dict **key** of tool arguments is neither filled nor refused, because `_collect`/`_fill` walk string leaves only. The behaviour is safe but unspecified.
3. A positive grant used successfully on the routine-run and connector-turn paths. Today those paths only prove that the hook is present, through a refusal.

## Evidence
- `the_one/secret_store/runtime.py` — `build_masker`, `_collect`, `_fill`, `SecretResolver.prepare`.
- `tests/test_routines_runner.py:392` — `test_a_routine_run_reaches_the_secrets_hook`; `tests/test_inbound_session_updated.py:282` — `test_connector_turn_reaches_the_secrets_hook`: both assert the "not granted" refusal only.
- `sorties/10-secrets/flight-debrief.md` "Technical".

## Corrective Action
Tests only; nothing under `the_one/` changed. Added:
1. `tests/test_secret_runtime.py::TestMasker::test_regex_metacharacters_are_matched_literally`: `a.b*(c)[d]|e` is masked where it appears literally, and look-alikes (`aXbbb(c)d|e`, `e`, ...) are untouched.
2. `tests/test_secret_loop.py::TestSubstitution::test_a_placeholder_in_a_dict_key_is_neither_filled_nor_refused`: a `{{secret:k}}` dict key reaches the tool unchanged, not filled and not refused (comment says this is deliberate and safe).
3. `tests/test_routines_runner.py::test_a_routine_run_fills_a_granted_secret_and_masks_the_result` and `tests/test_inbound_session_updated.py::test_connector_turn_fills_a_granted_secret_and_masks_the_result`: with the grant and `current_time` allowed, the real value reaches the tool (observed through its bad-zone error), the stored result carries `[secret:home_city]`, and the stored tool call keeps the placeholder. Both paths applied the grant correctly.

## Verification
Touched files pass (79 passed). Falsification of (1): with `re.escape` removed in `build_masker`, the new test fails (`KeyError: 'e'`, the unescaped alternation matches a bare `e`); the line was restored exactly and `git diff -- the_one/` is empty. `ruff check` and `ruff format --check` are clean. `THE_ONE_TEST_NETNS=1 make test-unit` result recorded in the Developer report.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; secret-runtime tests), batch review of the 2026-11-05 squawk turnaround, scoped to the diff. `[HANDOFF:confirmed]`, no blocking issues; it confirmed tests only (nothing under `the_one/`), and that the positive-grant tests prove the value reached the tool through the masked `current_time` echo while the stored arguments keep the placeholder. The Developer's `THE_ONE_TEST_NETNS=1 make test-unit`: 9141 passed, 15 skipped. `ruff` clean.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-05` commit on `squawk/turnaround-2026-11-05`.
