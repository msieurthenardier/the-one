# Squawk 0218: `FakeLLM` accepts a history that real providers reject

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-15
**Completed**: 2026-11-14

## Report
`FakeLLM` (the scripted provider most agent-loop tests use) accepts any message history. Real providers reject a history where one `tool_use` id has more than one `tool_result`, or a result with no preceding call. Sortie 04's HAT hit exactly that: `resume_after_auth` left the "auth required" placeholder beside the real result, and the Claude API returned 400 `invalid_request_error`. Every unit test passed because `FakeLLM` did not check. Make `FakeLLM` validate tool-call/result pairing on each call by default (raise a clear assertion naming the id), with an explicit opt-out for tests that build malformed histories on purpose.

## Evidence
- `tests/conftest.py::FakeLLM` (~l.143) — records calls and returns scripted messages; no history validation.
- `sorties/04-honest-mcp-sign-in/flight-log.md` (H2 third re-run: "each tool_use … multiple tool_result blocks"); the fix in `the_one/agent/core.py::resume_after_auth`.

## Corrective Action
`tests/conftest.py`: `check_tool_pairing(messages)` raises an `AssertionError` naming the id for a duplicate `tool_result` and for a result with no earlier call; `FakeLLM.__init__` takes `strict_history: bool = True` and `complete` runs the check (after recording the call). Subclasses that override `complete` without calling `super()` are not checked. Valid = every result id has an earlier call and is answered once; "call with no result" is not checked (the squawk names only the two rejected shapes).

The check tripped four tests across 967 in the 32 files that use `FakeLLM` or its helper modules:
- `tests/test_routine_tools_taint.py::test_clearing_or_deleting_the_routine_does_not_unflag_the_chat`: a real script bug (two `save()` calls reusing the id `n1` across turns); fixed with `cid="n2"`.
- `tests/test_notes_tools.py`: `test_ids_repeating_across_turns_are_flagged`, `test_ollama_bare_name_ids_identical_every_turn_are_flagged` and `test_orphaned_tool_result_is_flagged_unknown_tool` build such histories on purpose; each opts out through a new `strict_history` kwarg on the file's `_agent` helper, with a comment.
New file `tests/test_fake_llm_history.py` (6 tests): paired passes, duplicate and orphan raise naming the id, a result before its call is an orphan, the opt-out accepts both, a rejected call is still recorded. Falsified by edit (conftest, restored by edit): duplicate check disabled -> the duplicate test FAILS; orphan check disabled -> 3 tests FAIL; opt-out ignored (`if True`) -> the opt-out test FAILS.

## Verification
Done: the 32 test files that reference `FakeLLM`, `_secret_env`, `_routine_tools_env` or `_embedding_stub` (968 tests incl. the new ones) pass with the check on; `ruff check` and `ruff format --check` clean on the four changed files. NOT done: `make test-unit` (batch rule: no whole-suite run). A test that uses `FakeLLM` indirectly through a file outside that grep is the one place a trip could hide, and the Flight Director's full unit run will show it. One earlier combined run showed `tests/test_db_api.py::test_session_summary_keys_are_a_subset_of_the_ws_list_payload` failing twice, while another Developer was editing `interfaces/web/app.py`; it passed alone, passed with the check disabled, and passed in two later identical combined runs, so it is not caused by this change. Original criteria:
A unit test that `FakeLLM` raises on a duplicate `tool_result` id and on an orphan result, and passes with the opt-out; `make test-unit` green (any test that trips the check is either a real bug or opts out explicitly, named in the corrective action).

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`. The full unit run is the check the Developer left open, so no test outside the 32 files trips the new pairing check.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`
