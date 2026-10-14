# Squawk 0208: Platform prompt has a stale section title and docstring

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: 2026-10-14

## Report
Settings › Prompts shows the `tool_use_tail` section titled "Failure, tool descriptions and turn semantics", but after Mission 30's tuning that section holds only the `continue` rule. The module docstring still says "No condition is switched on yet", and a comment still reads "(candidate 1)".

## Evidence
- `the_one/agent/platform_prompt.py`: the `Section("tool_use_tail", "Failure, tool descriptions and turn semantics", …)` declaration, the module docstring ("No condition is switched on yet"), and the comment "# Tool discovery (candidate 1)".
- The title reaches the UI through `platform_sections_for_ui()` → `/api/info` → Settings › Prompts.

## Corrective Action
Retitled the section to match its content and refresh the docstring and comment. Prompt text itself is unchanged, so no eval run is needed; the UI title is not platform prompt text. Section id `tool_use_tail` unchanged; title is now "Turn semantics"; docstring rewritten to describe the sectioned, capability-conditioned state; "(candidate 1)" comment dropped.

## Verification
- Rendered `render_platform(Capabilities.all_on())` sha256 identical before and after (035729ab...).
- `pytest tests/test_platform_prompt.py tests/test_prompt_layers.py`: 59 passed. ruff check and format --check clean. No test asserts the old title.

## Sign-Off
*(written at completion)*
**Reviewer**: Reviewer agent (Sonnet tier), batch review of squawks 0208–0212
**Verdict**: confirmed
**Commit**: 5e4203f
