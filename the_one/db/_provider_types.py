"""Single source of truth for the LLM provider type enum.

Three layers must agree on the valid values:

- The Pydantic ``Literal`` annotation on ``LLMProviderConfig.type`` (compile-time
  type checking, JSON-schema generation, request validation at the API edge).
- The SQLite CHECK constraint string baked into the ``llm_providers`` table
  (runtime DB-level rejection of bogus rows).
- The provider-type → registry-name map in ``the_one.agent.factory`` (runtime
  dispatch from a stored provider config to an LLM client).

Historically these drifted (the openrouter rollout had to touch all three
independently). The tuple below is the canonical list; the three sites
re-derive their representation from it. The consistency tests in
``tests/test_provider_types_consistency.py`` pin all three to this tuple.
"""

from __future__ import annotations

PROVIDER_TYPES: tuple[str, ...] = (
    "ollama",
    "openai-compatible",
    "openai",
    "anthropic",
    "mock",
    "openrouter",
    "anthropic-plan",
    "anthropic-plan-token",
)

# Human-readable label per type (the UI's provider-type picker and the wording of
# provider connection errors). Keys must equal ``PROVIDER_TYPES``.
PROVIDER_TYPE_LABELS: dict[str, str] = {
    "ollama": "Ollama",
    "openai-compatible": "OpenAI-compatible",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "mock": "Mock (dev)",
    "openrouter": "OpenRouter",
    "anthropic-plan": "Claude Plan (OAuth)",
    "anthropic-plan-token": "Claude Plan (Token)",
}

assert set(PROVIDER_TYPE_LABELS) == set(PROVIDER_TYPES), (
    "PROVIDER_TYPE_LABELS keys drifted from PROVIDER_TYPES."
)
