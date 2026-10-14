# Squawk 0211: Evals section attribution falls back silently when no capability combination matches

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-14
**Completed**: 2026-10-14

## Report
`evals/tokens.py::platform_prompt_sections` tries a hard-coded set of capability combinations (tools × knowledge × exec_tools, plus tool-free) to attribute the platform text to section ids. If a future section conditions on another capability (notes, rules, time_tool), no combination matches. Attribution then degrades to a single `platform` part, with only a log warning, and per-section size reports go quietly wrong.

## Evidence
- `evals/tokens.py::platform_prompt_sections`: the fallback returns one `platform` part and logs a warning.

## Corrective Action
Chose option (b): option (a) would need the factory's computed Capabilities, i.e. a product change. `platform_prompt_sections` gained `strict=True` and a new `PlatformAttributionError`; `strict_platform_prompt_sections` is the strict splitter, and `measure_configs` (hence `measure-prompt`) now uses it by default, so an unattributable platform text raises instead of degrading to one `platform` part. The lenient default (warning plus one part) stays for other callers. `selftest` runs the new unit test. Original note: make the fallback fail `python -m evals selftest` and `measure-prompt`, or pass the capabilities `measure-prompt` built into the splitter instead of searching for them.

## Verification
`tests/test_evals_*.py` 294 passed (new test: unattributable text raises, in both the splitter and `measure_configs`); ruff check and format clean; `measure-prompt --json` before/after byte-identical (same fingerprint e8d2089b...).

## Sign-Off
*(written at completion)*
**Reviewer**: Reviewer agent (Sonnet tier), batch review of squawks 0208–0212
**Verdict**: confirmed
**Commit**: 66798d3
