"""MCP client error hierarchy.

Single base class with narrow subclasses. Each subclass formats a clean
single-sentence __str__ for small-model consumption (mission constraint #61).
No nested causes, no rich tracebacks visible in tool-result strings.
"""


class MCPClientError(Exception):
    """Base for all MCPClient-raised errors."""


class MCPVersionMismatch(MCPClientError):  # noqa: N818  (mandated by F2 contract; subclass of MCPClientError)
    """Server announced a protocol version different from what the-one targets."""

    def __init__(self, pinned: str, observed: str) -> None:
        self.pinned = pinned
        self.observed = observed
        super().__init__(
            f"MCP server announced protocol version {observed}, the-one supports "
            f"{pinned}. Server upgrade or the-one downgrade required."
        )


class MCPCapabilityMissing(MCPClientError):  # noqa: N818  (mandated by F2 contract; subclass of MCPClientError)
    """Server didn't announce a capability the-one needs."""

    def __init__(self, capability: str) -> None:
        self.capability = capability
        super().__init__(
            f"MCP server did not announce required capability: {capability!r}."
        )


class MCPConnectionError(MCPClientError):
    """Spawn failed, stream closed, network unreachable, transport-level error."""


class MCPSandboxError(MCPClientError):
    """Local MCP sandbox setup failed before bwrap successfully wraps-and-execs
    the target command: bwrap binary missing, ``writable_paths`` entry
    nonexistent, ``EPERM`` on ``unshare``, container lacks the §10 privilege
    grants, or other pre-spawn failure (F3 §6).
    """


class MCPToolNotFoundError(MCPClientError):
    """call_tool was invoked with a tool name not present in the server's tool list."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"MCP tool not found on server: {tool_name!r}.")


class MCPArgumentError(MCPClientError):
    """call_tool arguments don't conform to the tool's input JSON Schema."""

    def __init__(self, tool_name: str, validation_message: str) -> None:
        self.tool_name = tool_name
        self.validation_message = validation_message
        super().__init__(
            f"MCP tool {tool_name!r} rejected arguments: {validation_message}"
        )


class MCPCallError(MCPClientError):
    """Server returned a tool-call error result (isError=true)."""

    def __init__(self, tool_name: str, server_message: str) -> None:
        self.tool_name = tool_name
        self.server_message = server_message
        super().__init__(f"MCP tool {tool_name!r} returned an error: {server_message}")
