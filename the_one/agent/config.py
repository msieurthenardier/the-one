"""Agent configuration model and system-prompt composition.

The platform prompt text lives in :mod:`the_one.agent.platform_prompt`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from the_one.time_zones import CURRENT_TIME_TOOL_NAME

# Flight 5 Leg 1, DD-6: prefixes exempt from the `enabled_tools` built-in
# whitelist (`str.startswith` accepts a tuple). Generalized from a single
# hardcoded `"mcp__"` carve-out so a knowledge-base tool (`kb__…`, Flight 5
# Leg 2) is not silently stripped by an agent whose built-in whitelist was
# narrowed in Studio — `disabled_tools` still applies to both prefixes
# UNIVERSALLY, checked after this gate in `is_tool_enabled` below.
UNGATED_TOOL_PREFIXES = ("mcp__", "kb__")

# Mission 28 F1 L2 (DD6): built-in names also exempt from the `enabled_tools`
# whitelist. `current_time` must reach every agent, so an empty or trimmed
# whitelist no longer blocks *every* built-in. `disabled_tools` still applies.
WHITELIST_EXEMPT_TOOLS: frozenset[str] = frozenset({CURRENT_TIME_TOOL_NAME})


@dataclass(frozen=True)
class RenderedNote:
    """One saved note as the prompt layer sees it (M27 F2, DD9)."""

    number: int
    text: str
    untrusted: bool = False


def compose_system_prompt(
    base: str,
    persona: str,
    *,
    rules: Sequence[str] = (),
    notes: Sequence[RenderedNote] | None = None,
    secrets: str = "",
    date_line: str | None = None,
    tools: bool = True,
) -> str:
    """Compose the agent's system prompt from its layers.

    Layers join in a fixed order — ``base``, ``persona``, ``rules``,
    ``notes`` — with a "---" separator between them; an empty layer is
    omitted entirely (no stray separator, no empty heading). The result
    always starts with ``base`` (the platform prompt text). ``rules`` is the list of enabled rule
    texts in position order (Mission 27 DD1/DD5). ``notes`` is ``None`` when
    the agent's notes are off (layer omitted), ``[]`` when on with none saved
    ("No saved notes yet."), else the notes by number (M27 F2, DD9). When
    ``notes`` is not ``None`` the rules layer gains "Rules take precedence over
    saved notes.".

    With ``rules`` empty and ``notes`` ``None`` the output is byte-identical to the
    pre-Mission-27 ``{base}\\n\\n---\\n\\n{persona}`` shape.

    ``secrets`` (sortie 10, DD8) is the rendered secrets block, placed after notes and
    before the date line; empty adds nothing.

    ``date_line`` (M28 F1, DD4), when not ``None``, is appended as the LAST
    layer after a "---" separator (so notes are no longer the final layer).

    ``tools=False`` (the tool-free variant) gives the notes layer its tool-free
    heading, which never asks the model to save or update a note.
    """
    parts = [base]
    if persona:
        parts.append("---")
        parts.append(persona)
    if rules:
        # Deferred: importing the db package at module load would be a cycle.
        from the_one.db._rules import render_rules_block

        parts.append("---")
        parts.append(render_rules_block(rules, notes_present=notes is not None))
    if notes is not None:
        from the_one.db._notes import render_notes_block

        parts.append("---")
        parts.append(render_notes_block(notes, tools=tools))
    if secrets:
        # Sortie 10 DD8: the rendered secrets block (placeholders only), after notes.
        parts.append("---")
        parts.append(secrets)
    if date_line is not None:
        parts.append("---")
        parts.append(date_line)
    return "\n\n".join(parts)


class AgentConfig(BaseModel):
    """Definition of an agent's identity and capabilities."""

    model_config = {"extra": "ignore"}

    # Identity
    name: str
    description: str = ""

    # LLM
    provider_config_id: str | None = None
    llm_model: str = ""

    # Prompt
    system_prompt: str = ""

    # Tools
    enabled_tools: list[str] | None = None
    disabled_tools: list[str] = Field(default_factory=list)

    # Associations (reference IDs only — no functional behavior yet)
    kb_ids: list[str] = Field(default_factory=list)
    # Sortie 10: ids of the Library secrets this agent may pass to its tools.
    secret_ids: list[str] = Field(default_factory=list)
    mcp_source_ids: list[str] = Field(default_factory=list)

    # Tool-level constraint overrides (per-agent narrowing or substitution).
    # None means "no overrides set" (uses tool-level defaults — locked-down
    # NULL semantic, mirrors `enabled_tools=None`). The inner value type is
    # `dict[str, Any]` (NOT bare `dict`) so Pydantic v2 actually validates
    # that each tool's override is itself a dict — bare `dict` is parametric
    # and Pydantic skips inner-value validation.
    tool_overrides: dict[str, dict[str, Any]] | None = None

    # Per-agent MCP source override dict — shape parallels `tool_overrides`
    # but keys by source NAME (NOT tool name). The outer dict's key is the
    # MCPSource.name; the inner dict's keys are validated against the
    # transport-specific schema in `the_one/mcp/_overrides.py`
    # (StdioMCPOverride or StreamableHttpMCPOverride). None = no overrides
    # set (locked-down NULL semantic, mirrors `tool_overrides` and
    # `enabled_tools`). Inner type is `dict[str, Any]` (NOT bare `dict`)
    # for the same Pydantic v2 inner-validation reason as `tool_overrides`.
    mcp_overrides: dict[str, dict[str, Any]] | None = None

    # Behavior
    max_iterations: int = 20
    chat_history_retention_days: int = Field(default=30, ge=1, le=365)

    # M21 F02 L02 — per-agent approval mode. When True, a self-revision the
    # agent proposes through the self-configuration surface is held in the
    # `agent_revisions` queue as `pending` (awaiting operator approve/dismiss)
    # rather than applied immediately. Operator-owned: set by an immediate-post
    # Studio control and NOT reachable by the agent — no write tool addresses
    # it and the `get_my_configuration` projection omits it. Persisted in the
    # v35 `agents.self_revision_requires_approval INTEGER NOT NULL DEFAULT 0`
    # column (plain load, no absent/NULL case).
    self_revision_requires_approval: bool = False

    # M27 F2 DD2 — per-agent notes switch. Operator-owned (no agent tool writes
    # it; `get_my_configuration` omits it). Persisted in the v43
    # `agents.notes_enabled INTEGER NOT NULL DEFAULT 0` column. The per-agent
    # number counter `agents.notes_next_number` is deliberately NOT a field.
    notes_enabled: bool = False
    # Operator-owned Routines switches (M33 F2 DD4). Stored in
    # `agents.routines_self_config_enabled` (default 0) and
    # `agents.routines_require_approval` (DDL default 1, but `save`'s INSERT
    # writes this model's default, off, for a new agent: M33 F4 L5). `save`
    # never changes an existing row's value, and agent create/update ignore
    # incoming values, so only the Routines item routes (the targeted setter)
    # can change them.
    routines_self_config_enabled: bool = False
    routines_require_approval: bool = False

    def is_tool_enabled(self, tool_name: str) -> bool:
        """Check if a specific tool should be available to this agent.

        The ``enabled_tools`` whitelist governs **built-in tools only**.
        Names prefixed by :data:`UNGATED_TOOL_PREFIXES` are exempt from it:
        MCP tools — canonically prefixed ``mcp__`` at registration
        (``mcp/_tool.py:101``; cf. ``_MCP_PREFIX`` in
        ``tools/_search_tools.py``) — are governed by ``mcp_overrides``,
        applied upstream at agent build via
        ``MCPToolProvider.get_tools_for_agent`` /
        ``filter_mcp_tools_by_override``; knowledge-base tools — prefixed
        ``kb__`` (Flight 5 Leg 2) — have no per-tool override surface at
        all and are governed solely by whether their knowledge base is
        attached (``AgentConfig.kb_ids``). Applying the built-ins-only
        whitelist to either would double-gate them: the agent editor
        populates ``enabled_tools`` from built-in checkboxes only, so any
        non-null whitelist it emits excludes every ungated-prefix name and
        would silently strip all of them (F09-08, generalized at Flight 5
        Leg 1 DD-6 from a single hardcoded ``mcp__`` carve-out). Decoupling
        here stops that; ``disabled_tools`` stays a UNIVERSAL explicit
        blacklist (an ungated-prefix name listed there is still disabled).

        Names in :data:`WHITELIST_EXEMPT_TOOLS` (``current_time``, M28) are
        exempt from the whitelist too; ``disabled_tools`` still disables them.

        ``enabled_tools == []`` (empty whitelist) blocks all built-in tools
        **except** those in ``WHITELIST_EXEMPT_TOOLS``, and does NOT block MCP or
        knowledge-base tools, consistent
        with the decouple (their enablement is governed by
        ``mcp_overrides`` / attachment, not this whitelist).
        """
        is_ungated = (
            tool_name.startswith(UNGATED_TOOL_PREFIXES) or tool_name in WHITELIST_EXEMPT_TOOLS
        )
        if (
            not is_ungated
            and self.enabled_tools is not None
            and tool_name not in self.enabled_tools
        ):
            return False
        if tool_name in self.disabled_tools:
            return False
        return True
