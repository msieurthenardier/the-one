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


class TestToolFilterFieldsSchema:
    """L1 — per-source tool allow/deny fields on both override classes."""

    def test_stdio_override_accepts_enabled_disabled_tools_alongside_env(self) -> None:
        """L1.1: enabled_tools + disabled_tools validate alongside env."""
        o = StdioMCPOverride(
            env={"K": "V"},
            enabled_tools=["a", "b"],
            disabled_tools=["c"],
        )
        assert o.env == {"K": "V"}
        assert o.enabled_tools == ["a", "b"]
        assert o.disabled_tools == ["c"]

    def test_stdio_override_tool_fields_default_to_none(self) -> None:
        """L1.1: both new fields default to None (no-op by default)."""
        o = StdioMCPOverride()
        assert o.enabled_tools is None
        assert o.disabled_tools is None

    def test_streamable_http_override_accepts_enabled_disabled_tools_alongside_creds(
        self,
    ) -> None:
        """L1.1: enabled_tools + disabled_tools validate alongside bearer/headers."""
        o = StreamableHttpMCPOverride(
            bearer_token="tok",
            headers={"X": "Y"},
            enabled_tools=["a"],
            disabled_tools=[],
        )
        assert o.bearer_token == "tok"
        assert o.enabled_tools == ["a"]
        assert o.disabled_tools == []

    def test_streamable_http_override_tool_fields_default_to_none(self) -> None:
        """L1.1: both new fields default to None on StreamableHttpMCPOverride."""
        o = StreamableHttpMCPOverride()
        assert o.enabled_tools is None
        assert o.disabled_tools is None

    def test_stdio_override_extra_fields_ignored(self) -> None:
        """L1.4: Pydantic extra='ignore' (project default) silently drops unknown keys.

        Documents that a typo'd field name (e.g. ``enabled_tool`` vs ``enabled_tools``)
        will NOT raise — operator gets the no-op behavior, same as ``bear_token`` vs
        ``bearer_token`` at _overrides.py:101-103.
        """
        # Should NOT raise.
        o = StdioMCPOverride.model_validate({"enabled_tool": ["typo"]})  # singular
        assert o.enabled_tools is None  # the typo'd value was dropped

    def test_enabled_tools_not_substitute_annotated(self) -> None:
        """L1.1 negative: the new fields are NOT Annotated[..., Substitute].
        The resolver must NOT pick them up (no marker on field metadata).
        """
        stdio_meta = StdioMCPOverride.model_fields["enabled_tools"].metadata
        assert not any(m is Substitute for m in stdio_meta), (
            "enabled_tools must NOT carry a Substitute marker — "
            "it is read directly via model_validate, not via resolve()"
        )
        http_meta = StreamableHttpMCPOverride.model_fields["enabled_tools"].metadata
        assert not any(m is Substitute for m in http_meta), (
            "enabled_tools must NOT carry a Substitute marker on StreamableHttpMCPOverride"
        )

    def test_disabled_tools_not_substitute_annotated(self) -> None:
        """L1.1 negative: disabled_tools also carries no resolver marker."""
        stdio_meta = StdioMCPOverride.model_fields["disabled_tools"].metadata
        assert not any(m is Substitute for m in stdio_meta)
        http_meta = StreamableHttpMCPOverride.model_fields["disabled_tools"].metadata
        assert not any(m is Substitute for m in http_meta)


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
