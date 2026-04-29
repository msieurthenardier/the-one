from __future__ import annotations

from the_one.tools.base import Tool


class BuiltinToolProvider:
    """Provides all built-in tools via lazy imports."""

    @property
    def name(self) -> str:
        return "builtin"

    def get_tools(self) -> list[Tool]:
        """Lazy-import and instantiate all 7 built-in tools."""
        from the_one.tools.filesystem import ListDirTool, ReadFileTool, WriteFileTool
        from the_one.tools.python_exec import PythonExecTool
        from the_one.tools.shell import ShellTool
        from the_one.tools.web import HttpRequestTool, WebSearchTool

        return [
            ShellTool(),
            ReadFileTool(),
            WriteFileTool(),
            ListDirTool(),
            HttpRequestTool(),
            WebSearchTool(),
            PythonExecTool(),
        ]
