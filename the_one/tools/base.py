from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from the_one.tools.resolver import _EmptyConfig


class ConstraintError(Exception):
    """Policy-driven refusal raised by tools and category-helper checks.
    Tool wrappers catch this type and format
    `[error] [constraint] {msg}`; environmental exceptions still format
    `[error] {e}` so agents can distinguish policy refusals from runtime
    failures (Flight 3 Decision 1.5)."""


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

    # F4 Decision 7: tools may declare other Configs they consult at execute
    # time (e.g. ShellTool consults `FilesystemConfig` for cwd validation so
    # `cd /etc && cat passwd` is denied for an agent denied
    # `read_file('/etc/passwd')`). The provider resolves each declared Config
    # once per `get_tools(...)` call and hands the full mapping to every tool
    # via `cross_configs`. `Requires` is purely declarative in L1b — the
    # provider passes the full dict to all tools regardless. Future flights
    # may use `Requires` for static analysis or selective dispatch. Tuple
    # (immutable) so subclasses can't accidentally mutate the class default.
    #
    # F5 L6 widens this from `tuple[type[BaseModel], ...]` to `tuple[type, ...]`
    # so tools can declare service-style dependencies (e.g.
    # `WebSearchTool.Requires = (SearchBackend,)` where `SearchBackend` is a
    # `runtime_checkable` Protocol, NOT a `BaseModel`).
    Requires: tuple[type, ...] = ()

    def __init__(
        self,
        config: BaseModel | None = None,
        cross_configs: dict[type, object] | None = None,
        agent_name: str | None = None,
    ) -> None:
        # `or self.Config()` evaluates `self.Config()` only when `config` is
        # None, so subclasses with required-field Configs only fail when they
        # actually need a config but didn't get one.
        self._config = config or self.Config()
        # `cross_configs` is the per-call shared mapping of tool-level
        # Configs (Pydantic-keyed) AND per-call service instances
        # (Protocol-keyed) the provider built across `_TOOL_CLASSES`. Tools
        # that need cross-Config policy lookups (F4 Decision 7) read from
        # this dict by Config-type key (e.g.
        # `self._cross_configs[FilesystemConfig]`); tools that need
        # service-style dependencies (F5 L6) read by Protocol-type key
        # (e.g. `self._cross_configs[SearchBackend]`).
        #
        # **Type widening (F5 L6)**: F4 L1b's signature was
        # `dict[type[BaseModel], BaseModel]` because every entry was a
        # frozen Pydantic model. F5 L6 widens to `dict[type, object]` so
        # the same dispatch dict can also carry Protocol-keyed service
        # instances (e.g. `SearchBackend`). The "frozen Pydantic"
        # invariant from F4 still holds for Pydantic-keyed Config entries
        # (`FilesystemConfig`, `ExecutionConfig`, `PythonExecConfig`,
        # `WebConfig`) — those are still frozen models so a peer tool
        # cannot mutate one to corrupt another's view. Protocol-keyed
        # service entries are stateful (e.g. `DDGSearchBackend` owns an
        # httpx client) but per-`get_tools()`-call-scoped, matching the
        # session-bound freshness contract — every agent invocation gets
        # a fresh provider call, so two concurrent agents never share a
        # backend instance.
        self._cross_configs: dict[type, object] = cross_configs or {}
        # `agent_name` is per-agent state-isolation key (F4 Decision 4 — PTY
        # session ownership keys on `(agent_name, session_id)`). NOT an
        # adversarial separator; agents trust the operator's tool-level
        # policy. `None` for introspection callers and zero-arg test paths.
        self._agent_name: str | None = agent_name

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
