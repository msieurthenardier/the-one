# Squawk 0209: `tests/_old_prompts.py` holds the current prompt text under "old" names

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: —

## Report
`tests/_old_prompts.py` was created in Mission 30 F2 leg 1b to pin the old `BASE_PROMPT`/`CHAT_ONLY_PROMPT` literals. Since tuning it holds the **current** renders, still under `OLD_…` names, and 11 test files import it. A reader will assume it holds legacy text.

## Evidence
- `tests/_old_prompts.py`: its docstring says the literals are now the new renders.
- 11 importers (`grep -rln "_old_prompts" tests/`).

## Corrective Action
*(written at completion)* Rename it (for example `tests/_platform_prompt_pins.py`, with neutral names), or keep one pin in `test_platform_prompt.py` and render through `render_platform(Capabilities.all_on())` elsewhere.

## Verification

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
