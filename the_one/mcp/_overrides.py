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
    # F8 L1: per-source tool allow/deny. Plain fields (NOT Annotated
    # with Substitute/Narrow) — read directly from the validated
    # model in _tool_provider.py, not routed through the resolver.
    # Un-prefixed server-side tool names. None on enabled_tools means
    # "no allowlist applied"; an empty list means "no tools enabled".
    enabled_tools: list[str] | None = None
    disabled_tools: list[str] | None = None


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
    # F8 L1: see StdioMCPOverride for rationale.
    enabled_tools: list[str] | None = None
    disabled_tools: list[str] | None = None


# M21 F01 L01: marker-derived set of `mcp_overrides` inner-dict keys that
# carry credential material. Computed by scanning both override schemas'
# `model_fields[name].metadata` for the `Substitute` marker object (the
# same `m is Substitute` identity check `the_one/tools/resolver.py` and
# `interfaces/web/api.py:_enrich_schema_with_markers` both use) — NOT
# hand-listed. `enabled_tools` / `disabled_tools` carry no marker and are
# correctly excluded: they are not secrets, and Studio's Tools tab
# round-trips them in the clear.
#
# `interfaces/web/api.py:_agent_response` masks exactly these keys inside
# each `mcp_overrides[<source>]` entry; `tool_overrides` values are never
# masked (no `Substitute`-marked field exists on any built-in tool Config
# today — see the leg's Context section for the `WebConfig.default_user_agent`
# citation). A future `Substitute` credential added to either override
# schema is masked automatically, with no `api.py` edit required — that is
# the point of deriving this set rather than typing it out.
MCP_OVERRIDE_CREDENTIAL_KEYS: frozenset[str] = frozenset(
    name
    for schema_cls in (StdioMCPOverride, StreamableHttpMCPOverride)
    for name, field_info in schema_cls.model_fields.items()
    if any(m is Substitute for m in field_info.metadata)
)
