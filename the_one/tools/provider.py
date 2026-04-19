from __future__ import annotations

from typing import Protocol, runtime_checkable

from the_one.tools.base import Tool


@runtime_checkable
class ToolProvider(Protocol):
    """Protocol for sources of tools."""

    @property
    def name(self) -> str:
        """Unique identifier for this provider (e.g., 'builtin', 'mcp:slack')."""
        ...

    def get_tools(self) -> list[Tool]:
        """Return all tools this provider can supply."""
        ...
