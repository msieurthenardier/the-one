from __future__ import annotations

from the_one.tools.base import Tool


class BuiltinToolProvider:
    """Provides all built-in tools via lazy imports."""

    @property
    def name(self) -> str:
        return "builtin"

    def get_tools(self) -> list[Tool]:
        """Lazy-import and instantiate all 14 built-in tools."""
        from the_one.tools.filesystem import ListDirTool, ReadFileTool, WriteFileTool
        from the_one.tools.git import GitTool
        from the_one.tools.memory import MemoryTool
        from the_one.tools.mission_control import MissionControlTool
        from the_one.tools.python_exec import PythonExecTool
        from the_one.tools.restart import RestartTool
        from the_one.tools.rollback import RollbackTool
        from the_one.tools.self_deploy import SelfDeployTool
        from the_one.tools.shell import ShellTool
        from the_one.tools.test_runner import TestRunnerTool
        from the_one.tools.web import HttpRequestTool, WebSearchTool

        return [
            ShellTool(),
            ReadFileTool(),
            WriteFileTool(),
            ListDirTool(),
            HttpRequestTool(),
            WebSearchTool(),
            PythonExecTool(),
            GitTool(),
            TestRunnerTool(),
            SelfDeployTool(),
            RollbackTool(),
            RestartTool(),
            MissionControlTool(),
            MemoryTool(),
        ]
