# Squawk 0208: Platform prompt has a stale section title and docstring

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: —

## Report
Settings › Prompts shows the `tool_use_tail` section titled "Failure, tool descriptions and turn semantics", but after Mission 30's tuning that section holds only the `continue` rule. The module docstring still says "No condition is switched on yet", and a comment still reads "(candidate 1)".

## Evidence
- `the_one/agent/platform_prompt.py`: the `Section("tool_use_tail", "Failure, tool descriptions and turn semantics", …)` declaration, the module docstring ("No condition is switched on yet"), and the comment "# Tool discovery (candidate 1)".
- The title reaches the UI through `platform_sections_for_ui()` → `/api/info` → Settings › Prompts.

## Corrective Action
*(written at completion)* Retitle the section to match its content and refresh the docstring and comment. Prompt text itself is unchanged, so no eval run is needed; the UI title is not platform prompt text.

## Verification

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
