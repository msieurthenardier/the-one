# Squawk 0341: `cache-probe`'s cache minimum is a Haiku 4.5 constant

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-08
**Completed**: 2026-11-08

## Report
`evals/cache_probe.py` fixes `CACHE_MINIMUM_TOKENS = 4096` and `PRECONDITION_FLOOR = CACHE_MINIMUM_TOKENS + 256`, which are Claude Haiku 4.5's minimum. If the `haiku` preset moves to a model with a different minimum (Claude Haiku 5.5's is 512), exit 3 ("inconclusive") stops meaning "the prompt is under the cache minimum". Key the minimum by the preset's model id, with an explicit table and a refusal for an unknown model, so the precondition follows the model that actually ran.

## Evidence
- `evals/cache_probe.py:27-28`, `CACHE_MINIMUM_TOKENS = 4096` and `PRECONDITION_FLOOR`.
- `evals/models.toml [haiku]` is `claude-haiku-4-5-20251001` today.
- Raised at the sortie 14 debrief (recommendation 5) by the Architect and the Developer.

## Corrective Action
`evals/cache_probe.py` replaces the fixed `CACHE_MINIMUM_TOKENS` / `PRECONDITION_FLOOR` with an explicit `CACHE_MINIMUMS` table keyed by the preset's resolved model id (`claude-haiku-4-5-20251001` = 4096, `claude-haiku-5-5` = 512) and `FLOOR_HEADROOM = 256`. `cache_minimum(model)` refuses an unknown model with a one-line `EvalRefusalError` naming the model (exit 2); `run_probe` calls it right after resolving the preset, before any startup or model call. `decide` takes the `minimum` as a required keyword and derives the floor from it; exit codes 0-4 and `MARGIN = 32` are unchanged. `evals/README.md`'s `cache-probe` row states the per-model floor.

## Verification
- `tests/test_evals_cache_probe.py` covers a model-keyed minimum (`test_the_minimum_and_floor_follow_the_model`) and an unknown model refused with exit 2 and no run directory (`test_an_unknown_model_is_refused_before_any_call`); both falsified by editing the lookup out.
- `.venv/bin/python -m pytest tests/test_evals_cache_probe.py tests/test_evals_freeze.py -q -x --timeout 60` passes.
- `make eval ARGS="cache-probe --help"` still works.

## Sign-Off
**Reviewer**: Reviewer agent (Haiku; no security-sensitive surface), batch review of the 2026-11-08 squawk turnaround, scoped to the diff: `[HANDOFF:confirmed]`, no blocking issues. It re-ran `test_db_codec`, `test_anthropic_prompt_caching`, `test_evals_cache_probe`, `test_evals_freeze` and `test_evals_cli` (217 passed) and ruff check and format (clean). It confirmed `cache_minimum(preset.model)` runs after the preset is resolved and before `startup()` or any model call, that exit codes 0-4 and `MARGIN` are unchanged, and that `evals/outcomes.py` and the scoring digests are untouched. Its note that the Haiku 5.5 value (512) could not be verified from the repo: the Flight Director checked it against the Claude API reference's prompt-caching minimums table (Haiku 5.5: 512; Haiku 4.5: 4096). The 5.5 entry has not run live, because `evals/models.toml [haiku]` is still Haiku 4.5.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-08` commit on `squawk/turnaround-2026-11-08`.
