from __future__ import annotations

from typing import Protocol, runtime_checkable

from the_one.tools.base import Tool


@runtime_checkable
class ToolProvider(Protocol):
    """Protocol for sources of tools.

    Single-method (besides ``name``) per Decision 10. ``get_tools`` accepts
    optional ``tool_configs`` and ``agent_overrides`` so the provider can
    invoke the policy resolver internally (provider-drives-resolution).
    Both default to ``None`` for introspection callers (e.g., ``/api/tools``);
    when both are ``None`` the provider returns tools instantiated with
    their default empty Config.

    ``runtime_checkable`` Protocol checks method NAMES only, so widening
    this signature is non-breaking for any existing
    ``isinstance(provider, ToolProvider)`` checks.
    """

    @property
    def name(self) -> str:
        """Unique identifier for this provider (e.g., 'builtin', 'mcp:slack')."""
        ...

    def get_tools(
        self,
        tool_configs: dict[str, dict] | None = None,
        agent_overrides: dict[str, dict] | None = None,
    ) -> list[Tool]:
        """Return all tools this provider can supply."""
        ...
