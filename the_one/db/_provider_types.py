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
