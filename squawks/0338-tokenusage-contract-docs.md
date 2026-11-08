# Squawk 0338: state the `TokenUsage` contract on the type, and that interim frames carry no cache counts

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-08
**Completed**: —

## Report
Since sortie 14, `TokenUsage.input_tokens` is "the whole prompt" (Anthropic sums uncached, cache write and cache read). `cache_read_tokens` and `cache_write_tokens` are a breakdown that no consumer sums again. That contract is written only in `the_one/agents.md` and `evals/README.md`, not on the type. A future provider mapping (OpenAI `cached_tokens`, Ollama in sortie 13) could miss it.

Two related facts are documented nowhere:
- the interim mid-stream usage frames are byte estimates that carry no cache counts;
- a cost or quota display that sums `input_tokens` would over-count cached tokens.

## Evidence
- `the_one/llm/base.py:137` (`class TokenUsage`) has no docstring stating the contract.
- `the_one/llm/_streaming.py` builds the interim usage from bytes; only `anthropic_provider.py::_usage_from_sdk` fills the cache fields, on the final message.
- Raised at the sortie 14 debrief (`sorties/14-anthropic-prompt-caching/flight-debrief.md`, recommendation 2), by both the Developer and the Architect.

## Corrective Action
*(written at completion)*

## Verification
- `TokenUsage` has a docstring stating that `input_tokens` is the whole prompt and the cache fields are a breakdown.
- `the_one/agents.md` "Anthropic prompt caching (sortie 14)" mentions the interim frames and the over-count hazard.
- `.venv/bin/python -m pytest tests/test_db_codec.py tests/test_anthropic_prompt_caching.py -q -x --timeout 60` passes.
