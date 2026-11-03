# Squawk 0142: Document the single-flight fill, the cross-version-check rule and the Pull list's first-letter limit

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-11-03

## Report

Sortie 01 produced three things the docs don't yet carry.

1. **The detached single-flight fill pattern**, a named project pattern in `the_one/agents.md`'s Project Conventions. It is a reusable shape for a slow upstream catalog: a module-level task, awaited through `asyncio.shield` with a bounded wait and a `loading` answer plus a client re-request. List its obligations:
   - a lifespan `shutdown_drain()` at the top of the shutdown block;
   - the client, semaphore and other loop-bound primitives created per fill, never module-level;
   - a `_reset_for_tests` hook with autouse fixtures;
   - per-key writes into one shared map, where `unknown` never overwrites a known entry within its TTL.
2. **The cross-version-check rule**, in CLAUDE.md's Testing section. A check under another Python version must not touch the project environment: use `uv run --no-project …` or a scratch `UV_PROJECT_ENVIRONMENT`. A rebuilt venv is synced with `uv sync --all-extras --frozen` before its results count. In sortie 01, `uv run --python 3.11 --with-editable .` rebuilt the repo `.venv` as 3.11, and an unlocked reinstall then produced 11 false failures.
3. **The Pull list's accepted limit**, in the "Ollama pull catalog" section. On Windows (WebView2), the native `<select>` of about 448 entries jumps by first letter only; multi-letter type-to-find does not work. The operator accepted this at the HAT and rejected a filter box, so a future "can't find deepseek-r1:671b" report is a known limit. If the list is revisited, the starting point is `App.ui.searchList`.

Found in the sortie 01 debrief.

## Evidence

- `the_one/agents.md:1467` "### Ollama pull catalog (sortie 01)"; `:101` "## Project Conventions".
- `sorties/01-ollama-pull-download-size/flight-log.md`: the `.venv` anomaly and DD12's revert. `flight-debrief.md`: Methodology Observations 1 and 3.

## Corrective Action
Docs only. `the_one/agents.md`: new Project Conventions entry `detached-single-flight-fill` (shield with bounded wait and `loading` re-request, lifespan `shutdown_drain()`, per-fill loop-bound primitives, `_reset_for_tests` with autouse fixtures, per-key writes where `unknown` never overwrites a known entry), checked against `ollama_library.py` (`shutdown_drain`, `_reset_for_tests`, `_record`) and `app.py`'s lifespan; the "Ollama pull catalog" section gained the accepted first-letter-only limit of the native `<select>` (DD12 reverted, start from `App.ui.searchList`). `CLAUDE.md` Testing: the cross-version-check rule (`uv run --no-project` or a scratch `UV_PROJECT_ENVIRONMENT`; `uv sync --all-extras --frozen` after a rebuild).

## Verification
Done: passages checked against `ollama_library.py` and the sortie flight log; `THE_ONE_TEST_NETNS=1 make test-unit`: 8724 passed, 15 skipped. No new tests (docs).
- The three passages exist and are accurate against `the_one/llm/ollama_library.py` and the sortie's flight log.
- Any doc guard tests still pass (`make test-unit`).

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
