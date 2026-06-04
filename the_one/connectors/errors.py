"""Connector client error hierarchy.

Single base class with narrow subclasses. Each subclass formats a clean
single-sentence ``__str__`` for small-model consumption — mirrors the
``the_one/mcp/errors.py`` shape. No nested causes, no rich tracebacks
visible in tool-result strings.

The connector hierarchy starts smaller than MCP's (6 producer-side types
vs MCP's 10). Subsequent flights MAY add types when a real platform
reveals a distinct error mode that doesn't fit any existing type —
deliberate growth, not speculative.
"""


class ConnectorClientError(Exception):
    """Base for all connector-client-raised errors."""


class ConnectorConfigError(ConnectorClientError):
    """An account's config or secrets dict is invalid — missing required
    field, malformed value, or otherwise rejected by the plugin's
    validation."""

    def __init__(self, account_id: str, validation_message: str) -> None:
        self.account_id = account_id
        self.validation_message = validation_message
        super().__init__(f"Connector account {account_id!r} config rejected: {validation_message}")


class ConnectorConnectionError(ConnectorClientError):
    """Transport / network / handshake failure connecting to the platform."""


class ConnectorRegistrationError(ConnectorClientError):
    """Raised when a connector type cannot register cleanly.

    Two failure modes covered: (a) unknown type passed to the registry;
    (b) collision in the registry (two plugins registered under the same
    type name).
    """

    def __init__(self, type_name: str, reason: str) -> None:
        self.type_name = type_name
        self.reason = reason
        super().__init__(f"Connector type {type_name!r} registration failed: {reason}")


class ConnectorRateLimitError(ConnectorClientError):
    """Raised when the platform returns a rate-limit response.

    Carries ``retry_after_seconds`` when the platform advertises one
    (Discord ``X-RateLimit-Reset-After``, Slack ``Retry-After``); ``None``
    when no hint is given.
    """

    def __init__(
        self,
        account_id: str,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.account_id = account_id
        self.retry_after_seconds = retry_after_seconds
        if retry_after_seconds is not None:
            msg = (
                f"Connector account {account_id!r} rate-limited; "
                f"retry after {retry_after_seconds:.1f}s"
            )
        else:
            msg = f"Connector account {account_id!r} rate-limited (no retry hint)"
        super().__init__(msg)
