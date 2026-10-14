# Squawk 0211: Evals section attribution falls back silently when no capability combination matches

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: —

## Report
`evals/tokens.py::platform_prompt_sections` tries a hard-coded set of capability combinations (tools × knowledge × exec_tools, plus tool-free) to attribute the platform text to section ids. If a future section conditions on another capability (notes, rules, time_tool), no combination matches. Attribution then degrades to a single `platform` part, with only a log warning, and per-section size reports go quietly wrong.

## Evidence
- `evals/tokens.py::platform_prompt_sections`: the fallback returns one `platform` part and logs a warning.

## Corrective Action
*(written at completion)* Make the fallback fail `python -m evals selftest` and `measure-prompt`, or pass the capabilities `measure-prompt` built into the splitter instead of searching for them.

## Verification

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
