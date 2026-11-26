# Squawk 0432: A fresh environment skips 25 tests for an uncached tiktoken encoding

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-26
**Completed**: —

## Report
In a freshly synced environment (a git worktree with its own `.venv`), the unit tier skips 25 more tests than expected (40 instead of 15). The reason given is "o200k_base is not cached". Under the loopback-only namespace (`THE_ONE_TEST_NETNS=1`) tiktoken cannot download the encoding, so these tests silently skip and the expected skip count in `CLAUDE.md` no longer holds. Seen in sortie 20's worktree; see `sorties/20-deleting-an-agent-deletes-its-chats/flight-debrief.md`, "Test metrics".

## Evidence
- `tests/test_evals_gleepglorp_fixes.py:413-415`: `tiktoken.get_encoding("o200k_base")` inside a try, then `pytest.skip("o200k_base is not cached")`.
- The same skip appears in `tests/test_gleepglorp_prompt.py`, `test_evals_gleepglorp_prompt_file.py`, `test_gleepglorp_proposals_tool.py` and `test_gleepglorp_fill_tool.py`.

## Corrective Action
*(written at completion)*

Suggested direction: either document a one-time warm-up for a new environment (for example `make warm-tiktoken`, or a line in `CLAUDE.md` "Testing" that fetches the encoding outside the namespace), or point `TIKTOKEN_CACHE_DIR` at a shared, provisioned cache. Then restate the expected skip count.

## Verification
A fresh worktree, after the documented step, runs `make test-unit` with the expected skip count and no "o200k_base is not cached" skips.

## Sign-Off
*(written at completion)*
**Reviewer**: —
**Verdict**: —
**Commit**: —
