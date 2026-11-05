# Squawk 0331: Three missing secret-runtime tests

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-05
**Completed**: —

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
*(written at completion)* Planned: add (1) and (2) to `tests/test_secret_runtime.py` or `tests/test_secret_loop.py`. Add a granted case beside each of the two hook tests: a session whose agent has the grant runs a stub tool and receives the value, and the stored arguments keep the placeholder. Falsify (1) by removing `re.escape`. If (3) fails, stop: that is a defect and is escalated, not folded in.

## Verification
The new tests pass under `THE_ONE_TEST_NETNS=1 make test-unit` (expected 15 skipped), and (1)'s falsification fails as expected.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
