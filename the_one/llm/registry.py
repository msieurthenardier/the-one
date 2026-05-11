from __future__ import annotations

from typing import Any

from the_one.llm.base import LLMProvider

_providers: dict[str, type[LLMProvider]] = {}


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
    }
    if name in loaders:
        try:
            loaders[name]()
        except ImportError as e:
            # OpenRouter rides the openai package — no separate [openrouter] extra.
            extra = "openai" if name == "openrouter" else name
            raise ImportError(
                f"Provider '{name}' requires extra dependencies. "
                f"Install with: pip install 'the-one[{extra}]'"
            ) from e
