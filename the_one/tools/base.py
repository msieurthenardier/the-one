from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Base class for all tools the agent can use."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema

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

    def load_defaults(self) -> None:
        """Load all built-in tools."""
        from the_one.tools.shell import ShellTool
        from the_one.tools.filesystem import ReadFileTool, WriteFileTool, ListDirTool
        from the_one.tools.web import HttpRequestTool, WebSearchTool
        from the_one.tools.python_exec import PythonExecTool
        from the_one.tools.git import GitTool
        from the_one.tools.test_runner import TestRunnerTool
        from the_one.tools.self_deploy import SelfDeployTool
        from the_one.tools.rollback import RollbackTool
        from the_one.tools.restart import RestartTool

        for tool_cls in [
            ShellTool,
            ReadFileTool,
            WriteFileTool,
            ListDirTool,
            HttpRequestTool,
            WebSearchTool,
            PythonExecTool,
            GitTool,
            TestRunnerTool,
            SelfDeployTool,
            RollbackTool,
            RestartTool,
        ]:
            self.register(tool_cls())
