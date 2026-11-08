# Squawk 0341: `cache-probe`'s cache minimum is a Haiku 4.5 constant

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-08
**Completed**: —

## Report
`evals/cache_probe.py` fixes `CACHE_MINIMUM_TOKENS = 4096` and `PRECONDITION_FLOOR = CACHE_MINIMUM_TOKENS + 256`, which are Claude Haiku 4.5's minimum. If the `haiku` preset moves to a model with a different minimum (Claude Haiku 5.5's is 512), exit 3 ("inconclusive") stops meaning "the prompt is under the cache minimum". Key the minimum by the preset's model id, with an explicit table and a refusal for an unknown model, so the precondition follows the model that actually ran.

## Evidence
- `evals/cache_probe.py:27-28`, `CACHE_MINIMUM_TOKENS = 4096` and `PRECONDITION_FLOOR`.
- `evals/models.toml [haiku]` is `claude-haiku-4-5-20251001` today.
- Raised at the sortie 14 debrief (recommendation 5) by the Architect and the Developer.

## Corrective Action
*(written at completion)*

## Verification
- `tests/test_evals_cache_probe.py` covers a model-keyed minimum, including an unknown model.
- `.venv/bin/python -m pytest tests/test_evals_cache_probe.py tests/test_evals_freeze.py -q -x --timeout 60` passes.
- `make eval ARGS="cache-probe --help"` still works.
