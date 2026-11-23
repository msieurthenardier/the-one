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

# What the provider editor shows and defaults per type (the server-side copy of
# ``TYPE_DEFAULTS`` in ``static/js/areas/studio/providers-section.js``; a test pins the two
# together). ``base_url_shown`` is false for a hidden-URL type (the editor submits the default).
# ``shows_api_key`` is the "key-taking" definition: the type stores an API key or token.
PROVIDER_TYPE_DEFAULTS: dict[str, dict[str, object]] = {
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "base_url_shown": True,
        "shows_api_key": False,
        "shows_num_ctx": True,
        "shows_thinking": False,
        "shows_reasoning_effort": True,
        "plan_sign_in": False,
    },
    "openai-compatible": {
        "base_url": "",
        "base_url_shown": True,
        "shows_api_key": True,
        "shows_num_ctx": False,
        "shows_thinking": False,
        "shows_reasoning_effort": True,
        "plan_sign_in": False,
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "base_url_shown": False,
        "shows_api_key": True,
        "shows_num_ctx": False,
        "shows_thinking": False,
        "shows_reasoning_effort": True,
        "plan_sign_in": False,
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "base_url_shown": False,
        "shows_api_key": True,
        "shows_num_ctx": False,
        "shows_thinking": True,
        "shows_reasoning_effort": True,
        "plan_sign_in": False,
    },
    "anthropic-plan": {
        "base_url": "https://api.anthropic.com",
        "base_url_shown": False,
        "shows_api_key": False,
        "shows_num_ctx": False,
        "shows_thinking": True,
        "shows_reasoning_effort": True,
        "plan_sign_in": True,
    },
    "anthropic-plan-token": {
        "base_url": "https://api.anthropic.com",
        "base_url_shown": False,
        "shows_api_key": True,
        "shows_num_ctx": False,
        "shows_thinking": True,
        "shows_reasoning_effort": True,
        "plan_sign_in": False,
    },
    "mock": {
        "base_url": "",
        "base_url_shown": False,
        "shows_api_key": False,
        "shows_num_ctx": False,
        "shows_thinking": False,
        "shows_reasoning_effort": False,
        "plan_sign_in": False,
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "base_url_shown": True,
        "shows_api_key": True,
        "shows_num_ctx": False,
        "shows_thinking": False,
        "shows_reasoning_effort": True,
        "plan_sign_in": False,
    },
}

assert set(PROVIDER_TYPE_DEFAULTS) == set(PROVIDER_TYPES), (
    "PROVIDER_TYPE_DEFAULTS keys drifted from PROVIDER_TYPES."
)

# The types that run the Claude request path (extended thinking applies): derived, one source.
CLAUDE_PROVIDER_TYPES: tuple[str, ...] = tuple(
    t for t in PROVIDER_TYPES if PROVIDER_TYPE_DEFAULTS[t]["shows_thinking"]
)
