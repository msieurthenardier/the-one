# Squawk 0209: `tests/_old_prompts.py` holds the current prompt text under "old" names

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: 2026-10-14

## Report
`tests/_old_prompts.py` was created in Mission 30 F2 leg 1b to pin the old `BASE_PROMPT`/`CHAT_ONLY_PROMPT` literals. Since tuning it holds the **current** renders, still under `OLD_…` names, and 11 test files import it. A reader will assume it holds legacy text.

## Evidence
- `tests/_old_prompts.py`: its docstring says the literals are now the new renders.
- 11 importers (`grep -rln "_old_prompts" tests/`).

## Corrective Action
Renamed with `git mv` to `tests/_platform_prompt_pins.py`; constants are now `PLATFORM_TOOLS_ALL_ON_PIN` and `PLATFORM_TOOL_FREE_PIN`; docstring rewritten (byte-for-byte pins of the current renders; wording changes need an eval run). All 11 importers updated; test semantics unchanged.

## Verification
grep for `_old_prompts|OLD_PLATFORM|OLD_BASE|OLD_CHAT` across the_one/tests/evals/scripts/docs/*.md is empty; the 11 importer test files pass (279 passed); ruff check and format --check clean.

## Sign-Off
*(written at completion)*
**Reviewer**: Reviewer agent (Sonnet tier), batch review of squawks 0208–0212
**Verdict**: confirmed
**Commit**: 66798d3
