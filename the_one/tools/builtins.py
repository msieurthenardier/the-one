from __future__ import annotations

from the_one.tools._search_backends import SearchBackend, build_search_backend
from the_one.tools._web_config import WebConfig
from the_one.tools._web_search_config import WebSearchConfig
from the_one.tools.base import Tool
from the_one.tools.filesystem import (
    DeleteFileTool,
    EditFileTool,
    FilesystemConfig,
    GlobTool,
    GrepTool,
    ListDirTool,
    MkdirTool,
    MoveFileTool,
    ReadFileTool,
    WriteFileTool,
)
from the_one.tools.python_exec import PythonExecTool
from the_one.tools.resolver import _EmptyConfig, resolve
from the_one.tools.sessions import (
    ShellSessionCloseTool,
    ShellSessionListTool,
    ShellSessionSendTool,
    ShellSessionStartTool,
)
from the_one.tools.shell import ShellTool
from the_one.tools.web import (
    DownloadFileTool,
    FetchUrlTool,
    HttpRequestTool,
    WebSearchTool,
)

# Module-level eager-init mapping. One dict per Python process; tests that
# need to monkeypatch tool classes can patch
# ``the_one.tools.builtins._TOOL_CLASSES`` directly. The per-agent isolation
# guarantee is about the tool INSTANCES returned by `get_tools`, not this
# dict.
_TOOL_CLASSES: dict[str, type[Tool]] = {
    "shell": ShellTool,
    "read_file": ReadFileTool,
    "write_file": WriteFileTool,
    "edit_file": EditFileTool,
    "delete_file": DeleteFileTool,
    "move_file": MoveFileTool,
    "mkdir": MkdirTool,
    "glob": GlobTool,
    "grep": GrepTool,
    "list_dir": ListDirTool,
    "python_exec": PythonExecTool,
    "shell_session_start": ShellSessionStartTool,
    "shell_session_send": ShellSessionSendTool,
    "shell_session_close": ShellSessionCloseTool,
    "shell_session_list": ShellSessionListTool,
    "http_request": HttpRequestTool,
    "fetch_url": FetchUrlTool,
    "download_file": DownloadFileTool,
    "web_search": WebSearchTool,
}

# M14 F4 L7 — ordering-is-policy assertion. The cross-config resolution loop in
# ``BuiltinToolProvider.get_tools`` walks ``_TOOL_CLASSES`` in declared order and
# maps each DISTINCT ``cls.Config`` to the FIRST tool name that carries it.
# ``FilesystemConfig`` is shared by all 9 filesystem tools; the first one wins —
# currently ``read_file`` (``shell`` is first overall but its Config is
# ``ExecutionConfig``, not ``FilesystemConfig``). Tool-config tests must therefore
# key filesystem-policy fields under ``"read_file"``, not ``"shell"`` or any other
# filesystem tool. Reordering ``_TOOL_CLASSES`` silently changes which tool name
# resolves ``FilesystemConfig`` — policy consequence, not just cosmetics.
assert next(n for n, c in _TOOL_CLASSES.items() if c.Config is FilesystemConfig) == "read_file", (
    "_TOOL_CLASSES ordering changed: the first FilesystemConfig tool is no longer "
    "'read_file'. The cross-config resolution loop keys FilesystemConfig under the "
    "first matching tool — tool-config tests and operators keying FS policy under "
    "'read_file' will silently break. Update this assert AND audit all test fixtures."
)


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

    The factory-path ``cross_configs`` view contains TWO categories of
    entries (F5 L6):

    * **Pydantic-keyed Config entries** — ``FilesystemConfig``,
      ``ExecutionConfig``, ``PythonExecConfig``, ``WebConfig`` — frozen
      models resolved from operator/agent policy. These are the F4 L1b
      shape.
    * **Protocol-keyed service entries** — ``SearchBackend`` is the first
      such entry, mapped to a fresh ``DDGSearchBackend()`` per
      ``get_tools(...)`` call. F5 ships only DDG; F6 admin will let
      operators pick the active backend. The backend instance owns its
      own httpx client; per-call lifecycle matches the session-bound
      freshness contract — agents with different ``extra_allowed_hosts``
      get separate backend instances via separate ``get_tools()`` calls.
    """

    @property
    def name(self) -> str:
        return "builtin"

    def get_tools(
        self,
        tool_configs: dict[str, dict] | None = None,
        agent_overrides: dict[str, dict] | None = None,
        agent_name: str | None = None,
    ) -> list[Tool]:
        # Both None → introspection path (no resolver invocation).
        # `Tool.__init__` defaults `cross_configs={}` and `agent_name=None`,
        # so zero-arg construction preserves the F2/F3 introspection contract.
        if tool_configs is None and agent_overrides is None:
            return [cls() for cls in _TOOL_CLASSES.values()]
        # Factory path → resolver invocation per tool.
        tool_configs = tool_configs or {}
        agent_overrides = agent_overrides or {}

        # Build the per-call shared cross-Config view (F4 Decision 7). Walk
        # `_TOOL_CLASSES.items()` once in declared order; for each distinct
        # `cls.Config` (skipping `_EmptyConfig`), resolve from the FIRST tool
        # name carrying that Config. Multiple tools sharing one Config (e.g.
        # all 9 filesystem tools share `FilesystemConfig`) collapse to one
        # entry. Agent overrides are NOT applied at the cross-Config layer —
        # the cross-Config view is the operator-default baseline so a tool
        # consulting another category's policy sees what the operator
        # declared, not what the agent narrowed for its own bag.
        cross_configs: dict[type, object] = {}
        for name, cls in _TOOL_CLASSES.items():
            if cls.Config is _EmptyConfig:
                continue
            if cls.Config in cross_configs:
                continue
            cross_configs[cls.Config] = resolve(cls.Config, tool_configs.get(name), None)

        # M16 F08 L02 (DD3 refinement): inject the SearchBackend service built
        # from the resolved `WebSearchConfig` (engine selector + per-engine
        # fields). The SSRF policy (`extra_allowed_hosts`) is read off the
        # resolved shared `WebConfig` so even DDG's request respects it; each
        # backend opens/closes its OWN per-call SSRF-guarded client. A
        # selected-but-unconfigured keyed engine still constructs and raises
        # `SearchUnavailableError` at call time (NO silent DDG fallback). The
        # backend is constructed fresh per `get_tools(...)` call and GC'd when
        # the tool list goes out of scope.
        #
        # `WebSearchTool.Config` is now `WebSearchConfig`, so the cross-Config
        # loop above already resolved it into `cross_configs[WebSearchConfig]`;
        # `WebConfig` is likewise resolved (the other web tools carry it).
        web_search_cfg = cross_configs.get(WebSearchConfig)
        if web_search_cfg is None:
            web_search_cfg = resolve(WebSearchConfig, tool_configs.get("web_search"), None)
        web_cfg = cross_configs.get(WebConfig)
        if web_cfg is None:
            web_cfg = WebConfig()
        cross_configs[SearchBackend] = build_search_backend(
            web_search_cfg,
            extra_allowed_hosts=web_cfg.extra_allowed_hosts,
        )

        result: list[Tool] = []
        for name, cls in _TOOL_CLASSES.items():
            cfg = resolve(
                cls.Config,
                tool_configs.get(name),
                agent_overrides.get(name),
            )
            # `cross_configs` is shared by reference across all tools in this
            # call; frozen Configs (FilesystemConfig + future ExecutionConfig)
            # prevent any tool from mutating a peer's view.
            #
            # Mission 23 Flight 1 (backend-removal leg): the five connector
            # tools that used to receive extra ``connector_ids``/
            # ``connector_acls`` construction kwargs here (send + four
            # channel-context fetch tools) were deleted with the connector
            # package — every remaining tool takes the plain construction
            # below.
            result.append(cls(cfg, cross_configs=cross_configs, agent_name=agent_name))
        return result
