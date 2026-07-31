from __future__ import annotations

from typing import Any

from the_one.db._provider_types import PROVIDER_TYPES
from the_one.llm.base import LLMProvider

_providers: dict[str, type[LLMProvider]] = {}

# Map stored provider-config ``type`` to LLM registry name. Keys MUST equal
# ``PROVIDER_TYPES`` exactly (module-load assert below, pinned by
# ``tests/test_provider_types_consistency.py``); the ``openai-compatible`` →
# ``ollama`` re-route is the one historical alias and lives here only.
# M19 F01 L02: lifted here from ``agent/factory.py`` (the code's own
# forward-note) now that a third caller exists — ``agent/factory.py``,
# ``connectors/_inference.py``, and the provider ``/test``+``/models`` API
# branches all dispatch through this single source of truth.
PROVIDER_TYPE_MAP = {
    "ollama": "ollama",
    "openai-compatible": "ollama",
    "openai": "openai",
    "anthropic": "anthropic",
    "mock": "mock",
    "openrouter": "openrouter",
    "anthropic-plan": "anthropic-plan",
}

assert set(PROVIDER_TYPE_MAP.keys()) == set(PROVIDER_TYPES), (
    "PROVIDER_TYPE_MAP keys drifted from PROVIDER_TYPES — "
    "every type declared in db/_provider_types.py must dispatch to a registry name."
)


def register_provider(name: str, cls: type[LLMProvider]) -> None:
    _providers[name] = cls


def get_provider(name: str, **kwargs: Any) -> LLMProvider:
    if name not in _providers:
        # Lazy-load built-in providers
        _try_load_builtin(name)
    if name not in _providers:
        available = ", ".join(_providers) or "(none)"
        raise ValueError(f"Unknown LLM provider '{name}'. Available: {available}")
    return _providers[name](**kwargs)


def _try_load_builtin(name: str) -> None:
    loaders = {
        "openai": lambda: __import__("the_one.llm.openai_provider", fromlist=["_"]),
        "anthropic": lambda: __import__("the_one.llm.anthropic_provider", fromlist=["_"]),
        "ollama": lambda: __import__("the_one.llm.ollama_provider", fromlist=["_"]),
        "mock": lambda: __import__("the_one.llm.mock", fromlist=["_"]),
        "openrouter": lambda: __import__("the_one.llm.openrouter_provider", fromlist=["_"]),
        "anthropic-plan": lambda: __import__("the_one.llm.anthropic_plan_provider", fromlist=["_"]),
    }
    if name in loaders:
        try:
            loaders[name]()
        except ImportError as e:
            # OpenRouter rides the openai package — no separate [openrouter] extra.
            # anthropic-plan rides the anthropic package the same way — no
            # separate [anthropic-plan] extra exists.
            extra_aliases = {"openrouter": "openai", "anthropic-plan": "anthropic"}
            extra = extra_aliases.get(name, name)
            raise ImportError(
                f"Provider '{name}' requires extra dependencies. "
                f"Install with: pip install 'the-one[{extra}]'"
            ) from e
