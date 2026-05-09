"""L1 — MCP source override schema + resolver dispatch tests.

Locks the inverted-Annotated[T | None, Substitute] = None placement
per Architect cycle-1 H1 — Pydantic v2 hoists metadata inside Union
types, so the broken form Annotated[T, Substitute] | None yields
model_fields[name].metadata == [] and the resolver fails to dispatch.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from the_one.mcp._overrides import StdioMCPOverride, StreamableHttpMCPOverride
from the_one.tools.resolver import Substitute, resolve


class TestMarkerPlacementRegression:
    """Lock Annotated[T | None, Substitute] = None placement (cycle-1 H1).

    A future schema addition that uses the broken
    Annotated[T, Substitute] | None placement would silently regress
    to marker_count == 0 and break the resolver. These tests pin the
    working form by reading `field_info.metadata` directly so the
    regression fails LOUD at test time rather than silently at
    agent-build time.
    """

    def test_stdio_override_env_marker_is_substitute(self) -> None:
        markers = StdioMCPOverride.model_fields["env"].metadata
        assert any(m is Substitute for m in markers), markers

    def test_streamable_http_override_headers_marker_is_substitute(self) -> None:
        markers = StreamableHttpMCPOverride.model_fields["headers"].metadata
        assert any(m is Substitute for m in markers), markers

    def test_streamable_http_override_bearer_token_marker_is_substitute(self) -> None:
        markers = StreamableHttpMCPOverride.model_fields["bearer_token"].metadata
        assert any(m is Substitute for m in markers), markers


class TestResolverDispatch:
    """Resolver dispatch tests for the substitution-only schemas."""

    def test_resolve_stdio_substitute_replaces_env(self) -> None:
        merged = resolve(StdioMCPOverride, None, {"env": {"FOO": "bar"}})
        assert isinstance(merged, StdioMCPOverride)
        assert merged.env == {"FOO": "bar"}

    def test_resolve_stdio_locked_down_null_returns_none_env(self) -> None:
        """`agent_override is None` is the locked-down NULL semantic
        (resolver lines 224-226). Every Substitute-marked field stays
        at its default (None)."""
        merged = resolve(StdioMCPOverride, None, None)
        assert isinstance(merged, StdioMCPOverride)
        assert merged.env is None

    def test_resolve_streamable_http_full_override(self) -> None:
        merged = resolve(
            StreamableHttpMCPOverride,
            None,
            {"headers": {"X-Foo": "y"}, "bearer_token": "tok"},
        )
        assert isinstance(merged, StreamableHttpMCPOverride)
        assert merged.headers == {"X-Foo": "y"}
        assert merged.bearer_token == "tok"

    def test_resolve_streamable_http_partial_override(self) -> None:
        """Only `headers` is provided in the agent override; the
        unset `bearer_token` retains its schema default of None."""
        merged = resolve(
            StreamableHttpMCPOverride,
            None,
            {"headers": {"X-Foo": "y"}},
        )
        assert isinstance(merged, StreamableHttpMCPOverride)
        assert merged.headers == {"X-Foo": "y"}
        assert merged.bearer_token is None

    def test_resolve_streamable_http_locked_down_null(self) -> None:
        merged = resolve(StreamableHttpMCPOverride, None, None)
        assert isinstance(merged, StreamableHttpMCPOverride)
        assert merged.headers is None
        assert merged.bearer_token is None

    def test_resolve_unknown_key_dropped_silently(self) -> None:
        """Pydantic's default `extra="ignore"` (resolver line 260) drops
        unknown override keys silently. An operator who types
        `bear_token` instead of `bearer_token` gets `bearer_token=None`
        with NO error — silent-drop is the documented behavior."""
        merged = resolve(
            StreamableHttpMCPOverride,
            None,
            {"bear_token": "typo"},
        )
        assert isinstance(merged, StreamableHttpMCPOverride)
        assert merged.bearer_token is None
        # The typo'd attribute does not appear on the model.
        assert not hasattr(merged, "bear_token")


class TestModelsAreFrozen:
    """Both schemas declare `model_config = ConfigDict(frozen=True)` —
    attempts to mutate after construction must raise."""

    def test_stdio_override_is_frozen(self) -> None:
        m = StdioMCPOverride(env={"FOO": "bar"})
        with pytest.raises(ValidationError):
            m.env = {"BAZ": "qux"}  # type: ignore[misc]

    def test_streamable_http_override_is_frozen(self) -> None:
        m = StreamableHttpMCPOverride(headers={"X-Foo": "y"}, bearer_token="tok")
        with pytest.raises(ValidationError):
            m.bearer_token = "changed"  # type: ignore[misc]
