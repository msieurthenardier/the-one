# Squawk 0142: Document the single-flight fill, the cross-version-check rule and the Pull list's first-letter limit

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: —

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
*(written at completion)*

## Verification
- The three passages exist and are accurate against `the_one/llm/ollama_library.py` and the sortie's flight log.
- Any doc guard tests still pass (`make test-unit`).

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
