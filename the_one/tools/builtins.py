from __future__ import annotations

from the_one.tools.base import Tool
from the_one.tools.filesystem import ListDirTool, ReadFileTool, WriteFileTool
from the_one.tools.python_exec import PythonExecTool
from the_one.tools.resolver import resolve
from the_one.tools.shell import ShellTool
from the_one.tools.web import HttpRequestTool, WebSearchTool

# Module-level eager-init mapping. One dict per Python process; tests that
# need to monkeypatch tool classes can patch
# ``the_one.tools.builtins._TOOL_CLASSES`` directly. The per-agent isolation
# guarantee is about the tool INSTANCES returned by `get_tools`, not this
# dict.
_TOOL_CLASSES: dict[str, type[Tool]] = {
    "shell": ShellTool,
    "read_file": ReadFileTool,
    "write_file": WriteFileTool,
    "list_dir": ListDirTool,
    "python_exec": PythonExecTool,
    "http_request": HttpRequestTool,
    "web_search": WebSearchTool,
}


class BuiltinToolProvider:
    """Provides all built-in tools.

    Per Decision 3 / Decision 9, ``get_tools(...)`` instantiates a fresh
    set of tools per call (no shared singletons). The two paths:

    * Both args ``None`` (introspection path) — each tool is instantiated
      with ``cls()`` (which falls back to ``cls.Config()`` for an empty
      default Config). Used by ``/api/tools`` and zero-arg tests.
    * At least one arg supplied (factory path) — each tool's Config is
      resolved via ``resolve(cls.Config, tool_configs.get(name),
      agent_overrides.get(name))`` and the resolved Config is handed to
      ``cls(resolved_config)``. Unknown tool names in ``agent_overrides``
      are silently ignored (mirrors `enabled_tools` strip behavior).
    """

    @property
    def name(self) -> str:
        return "builtin"

    def get_tools(
        self,
        tool_configs: dict[str, dict] | None = None,
        agent_overrides: dict[str, dict] | None = None,
    ) -> list[Tool]:
        # Both None → introspection path (no resolver invocation).
        if tool_configs is None and agent_overrides is None:
            return [cls() for cls in _TOOL_CLASSES.values()]
        # Factory path → resolver invocation per tool.
        tool_configs = tool_configs or {}
        agent_overrides = agent_overrides or {}
        result: list[Tool] = []
        for name, cls in _TOOL_CLASSES.items():
            cfg = resolve(
                cls.Config,
                tool_configs.get(name),
                agent_overrides.get(name),
            )
            result.append(cls(cfg))
        return result
