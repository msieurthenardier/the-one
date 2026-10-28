# Squawk 0280: Add a unit guard that every session turn takes its lock through `track_turn`

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-28
**Completed**: —

## Report
Since M31 F6 leg 10b, the Chats row activity (`busy`, `turn_seq`, the `sessions_changed` start and end pushes) depends on every turn acquiring the per-session lock through `the_one.sessions.track_turn`. Web turns and connector turns do so today. Nothing enforces it. A future turn path that writes `async with session_locks[...]` directly would run with no row activity and no new-reply dot, and every test would stay green. Add a cheap static guard now, while there is exactly one acquisition site.

## Evidence
- `the_one/sessions/_locks.py:89`: `async with session_locks[session_id]:` inside `track_turn` (`:76`). It is the only `session_locks[` acquisition under `the_one/`. `app.py:2220`, `:2223` and `:2523` mention it only in comments.
- `the_one/agents.md` "Chats row activity" (Server seam) documents `track_turn` as "the per-session lock acquisition". The resume-after-auth path is untracked by design, and the guard should allow that one exception by name, if it ever takes the lock.

## Corrective Action
*(written at completion)*
Likely fix: a unit test (an AST or regex scan of `the_one/**/*.py`, comments stripped) that fails on any `session_locks[` subscript outside `the_one/sessions/_locks.py::track_turn`. Its failure message points at `track_turn`.

## Verification
*(written at completion)*
The new test passes on the current tree. A falsification check (add a direct `async with session_locks[x]:` in a scratch copy) makes it fail, and is then reverted.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
