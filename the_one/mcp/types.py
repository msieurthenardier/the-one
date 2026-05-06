"""MCP value-objects: MCPTool and MCPToolResult dataclasses.

Frozen for safety (immutable after construction). MCPTool is constructed by
MCPClient.list_tools() from the SDK's tool-list response; MCPToolResult is
constructed by MCPClient.call_tool() from the SDK's call-tool response with
text-flattening of content blocks.

See flight design decisions §4 (MCPToolResult) and §5b (MCPTool) for the
full shape rationale.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MCPTool:
    """A tool available on an MCP server.

    Constructed from the server's tools/list response. F6 will translate
    these into the project's existing Tool abstraction.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    annotations: dict[str, Any] | None


@dataclass(frozen=True)
class MCPToolResult:
    """The result of a tool call.

    text: flattened textual representation for agent consumption (mission
        constraint #56 — agent loop dispatches by tool name; tool results
        render to string format)
    raw: original content blocks from the server (for F7's inspector)
    structured: MCP `structuredContent` typed-object form, if present
    is_error: mirrors the server's isError flag — when true, MCPClient.call_tool
        raises MCPCallError; this field is preserved on the dataclass for
        inspector trace-pane visibility (F7)
    """

    text: str
    raw: list[dict[str, Any]]
    structured: dict[str, Any] | None
    is_error: bool
