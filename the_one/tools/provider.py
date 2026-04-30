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
        agent_name: str | None = None,
    ) -> list[Tool]:
        """Return all tools this provider can supply.

        ``agent_name`` is the per-agent state-isolation key (F4 Decision 4):
        used to scope per-agent runtime state like PTY session ownership
        keyed on ``(agent_name, session_id)``. NOT an adversarial separator —
        agents trust the operator's tool-level policy boundary. Defaults to
        ``None`` for introspection callers (e.g. ``/api/tools``).

        The provider's per-call ``cross_configs`` view (passed into each
        tool's ``__init__``) carries two categories of entries (F5 L6):
        Pydantic-keyed Config entries (frozen models — F4 L1b shape) and
        Protocol-keyed service entries (e.g. ``SearchBackend`` mapped to a
        per-call ``DDGSearchBackend()`` instance). The widening is
        non-breaking for ``isinstance(provider, ToolProvider)`` checks
        because ``runtime_checkable`` Protocols only validate method names.
        """
        ...
