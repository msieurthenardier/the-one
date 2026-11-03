# Squawk 0280: Add a unit guard that every session turn takes its lock through `track_turn`

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-28
**Completed**: 2026-11-03

## Report
Since M31 F6 leg 10b, the Chats row activity (`busy`, `turn_seq`, the `sessions_changed` start and end pushes) depends on every turn acquiring the per-session lock through `the_one.sessions.track_turn`. Web turns and connector turns do so today. Nothing enforces it. A future turn path that writes `async with session_locks[...]` directly would run with no row activity and no new-reply dot, and every test would stay green. Add a cheap static guard now, while there is exactly one acquisition site.

## Evidence
- `the_one/sessions/_locks.py:89`: `async with session_locks[session_id]:` inside `track_turn` (`:76`). It is the only `session_locks[` acquisition under `the_one/`. `app.py:2220`, `:2223` and `:2523` mention it only in comments.
- `the_one/agents.md` "Chats row activity" (Server seam) documents `track_turn` as "the per-session lock acquisition". The resume-after-auth path is untracked by design, and the guard should allow that one exception by name, if it ever takes the lock.

## Corrective Action
Added `tests/test_track_turn_guard.py`: an AST scan (via `tests/_source_scan.py`) of every `the_one/**/*.py` that fails on any `session_locks[...]` / `x.session_locks[...]` subscript outside `the_one/sessions/_locks.py`; the failure message points at `track_turn`. It also asserts the one allowed site still exists, and a planted-violation test pins the detector (flags a direct `async with`, ignores comments, strings, `.pop`, `.get`).

## Verification
`tests/test_track_turn_guard.py` passes on the current tree (2 tests). Falsified: changing the matched name in the detector made both tests fail; restored. `ruff check` and `ruff format --check` clean. `THE_ONE_TEST_NETNS=1 make test-unit`: 8727 passed, 15 skipped.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
