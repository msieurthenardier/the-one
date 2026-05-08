"""Per-agent MCP source override schemas.

These Pydantic models declare the inner-shape contract for the
``mcp_overrides`` field on ``AgentConfig`` (the outer dict's keys are
``MCPSource.name`` strings; this module's schemas validate the inner
override dicts). The resolver in ``the_one.tools.resolver.resolve``
dispatches on ``Annotated[T, marker]`` field metadata at agent-build
time to merge tool-level config with per-agent overrides.

Why all-``Substitute``: credentials don't have a narrowing semantic.
An operator-set bearer token is REPLACED by the agent's bearer token,
not narrowed to a substring; an env-var dict overlays onto the
source's ``secrets["env"]`` rather than restricting any subset
relation. Future fields with a narrowing semantic (e.g., a per-source
``read_only`` boolean or an allowlist of method paths) can use
``Narrow`` without changing the schema shape.

Why ``Annotated[T | None, Substitute] = None`` (NOT
``Annotated[T, Substitute] | None = None``): per Architect cycle-1
H1, Pydantic v2 hoists metadata that sits INSIDE a ``Union`` during
model construction. The broken placement
``Annotated[T, Substitute] | None = None`` yields
``model_fields[name].metadata == []`` at runtime, so the resolver's
``m is Substitute for m in markers`` check never finds the marker
and ``the_one.tools.resolver.resolve`` raises
``ValueError: ... no Narrow/Substitute marker``. The correct,
working form is ``Annotated[T | None, Substitute] = None`` — the
``| None`` lives INSIDE the ``Annotated`` so the marker survives.
The L1 introspection regression test
``tests/test_mcp_overrides.py::TestMarkerPlacementRegression``
locks this placement so a future schema addition that copies the
broken form fails LOUD at test time, not silently at agent-build
time.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict

from the_one.tools.resolver import Substitute


class StdioMCPOverride(BaseModel):
    """Per-agent override schema for stdio-transport MCP sources.

    Substitution-only overlay: the agent's ``env`` dict REPLACES the
    source's ``secrets["env"]`` at spawn time (via ``Substitute``
    semantics in ``the_one.tools.resolver.resolve``).

    Field placement note: ``env`` is declared as
    ``Annotated[dict[str, str] | None, Substitute] = None`` (NOT
    ``Annotated[dict[str, str], Substitute] | None = None``) — see
    the module docstring for the H1 rationale.
    """

    model_config = ConfigDict(frozen=True)

    env: Annotated[dict[str, str] | None, Substitute] = None


class StreamableHttpMCPOverride(BaseModel):
    """Per-agent override schema for streamable-http MCP sources.

    Two substitution-only fields:

    * ``headers`` — dict overlay applied to the source's HTTP request
      headers at ``auth=...`` injection time.
    * ``bearer_token`` — replaces the source-stored bearer token at
      injection time. ``Substitute`` semantic, not ``Narrow``: a
      bearer token has no canonical narrowing relation.

    Field placement note: both fields follow the
    ``Annotated[T | None, Substitute] = None`` placement convention
    (see module docstring) so the marker survives Pydantic v2's
    ``Union``-hoisting.
    """

    model_config = ConfigDict(frozen=True)

    headers: Annotated[dict[str, str] | None, Substitute] = None
    bearer_token: Annotated[str | None, Substitute] = None
