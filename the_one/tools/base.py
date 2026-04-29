from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from the_one.tools.resolver import _EmptyConfig


class Tool(ABC):
    """Base class for all tools the agent can use.

    Subclasses may declare a ``Config`` class attribute pointing to a
    Pydantic ``BaseModel`` subclass (with ``Narrow`` / ``Substitute``
    field-metadata markers) to participate in the tool policy resolver.
    F2's seven tools inherit the empty default; F3-F5 introduce real
    Configs.

    The ``__init__`` takes an already-resolved ``BaseModel`` instance
    (built by ``the_one.tools.resolver.resolve(...)`` and handed in by
    ``BuiltinToolProvider.get_tools(...)``). When ``config`` is omitted
    the tool falls back to ``self.Config()`` so existing zero-arg
    ``Tool()`` constructions (introspection callers, tests) keep working.
    """

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema

    # Default Config is `_EmptyConfig`, NOT bare `BaseModel` —
    # Pydantic v2's `BaseModel()` raises `PydanticUserError`. Subclasses
    # override `Config` with their own `BaseModel` schema as F3+ adds
    # constraint fields.
    Config: type[BaseModel] = _EmptyConfig

    def __init__(self, config: BaseModel | None = None) -> None:
        # `or self.Config()` evaluates `self.Config()` only when `config` is
        # None, so subclasses with required-field Configs only fail when they
        # actually need a config but didn't get one.
        self._config = config or self.Config()

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Run the tool and return a string result."""
        ...

    def to_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    def all_schemas(self) -> list[dict[str, Any]]:
        return [t.to_schema() for t in self._tools.values()]

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools)
