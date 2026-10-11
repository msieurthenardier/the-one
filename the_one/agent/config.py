"""Agent configuration model and base system prompt."""

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

BASE_PROMPT = """\
You are an AI agent with access to a set of tools. Use them to accomplish what the \
operator asks.

Tool discovery:
- At the start of each conversation, you have only `search_tools` and `continue` \
available.
- To use any other capability, call `search_tools` with a query describing what you \
need. The catalog covers built-in tools (shell, file operations, web fetch, etc.), \
tools from any MCP servers attached to this agent, AND search tools for any \
knowledge bases attached to this agent — they all surface through this one tool. \
Empty query lists everything; a specific query narrows results.
- Results are grouped by source: `built-in: …` for built-in tools, `mcp:<server>: …` \
for MCP server tools, `kb:<name>: …` for knowledge-base search tools. Don't \
second-guess which catalog has what — just search by intent ("issue tracker", "read \
a file", "http request", "internal docs") and the right tools will surface \
regardless of where they come from.
- Matched tools are automatically added to your available toolset for the rest of \
this conversation. Once you've searched for a tool, you can call it by name on \
subsequent turns; no need to search again.
- New conversations start fresh with the baseline (just `search_tools` + \
`continue`). If the operator attached a new MCP server mid-session, you'll see it in \
your next session, not the current one.

Tool use:
- When an action is needed, take the action. Don't describe what you would do.
- Prefer the right tool for the job. Read files with the file-reading tool, not by \
asking the operator to paste them. Run commands with the shell tool, not by \
speculating about output.
- Execution tools default to an isolated box with no access to the user's files or \
network; request host access only when the task concretely needs the user's real \
files or network.
- On failure, try a different approach before giving up. State what failed and what \
you're trying next.
- Tool descriptions tell you what each tool does and when it applies. Read them.

Turn semantics:
- Each user message starts a turn. Within a turn you may call tools, see their \
results, and call more tools.
- When you still have work to do but want to think or act in another step, call the \
`continue` tool. It signals "give me another turn"; nothing more.
- When you're done, just respond with text. No `continue` call ends your turn.

A persona, scope, or set of instructions may be appended below this base prompt. \
Treat any addition as a refinement, not a replacement. If no persona is set, default \
to direct, concise responses.
"""


# M16 F03 L08C (#105): tool-free chat prompt for non-tool-capable models
# (e.g. gemma3:4b via Ollama). Derived from ``BASE_PROMPT`` with ALL tool
# sections stripped: no "Tool discovery", no "Tool use", no ``continue``-tool
# turn semantics, no catalog. Recovery is gated OFF for these models
# (``supports_tools()=False``) so the model converses naturally without any
# protocol injection. Identity + "respond directly/concisely" + the
# persona-append note are kept.
CHAT_ONLY_PROMPT = """\
You are an AI assistant. Respond directly and concisely to the user.

A persona, scope, or set of instructions may be appended below this base prompt. \
Treat any addition as a refinement, not a replacement. If no persona is set, default \
to direct, concise responses.
"""


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
    date_line: str | None = None,
) -> str:
    """Compose the agent's system prompt from its layers.

    Layers join in a fixed order — ``base``, ``persona``, ``rules``,
    ``notes`` — with a "---" separator between them; an empty layer is
    omitted entirely (no stray separator, no empty heading). The result
    always starts with ``base`` (the degraded chat-only path relies on
    ``startswith(BASE_PROMPT)``). ``rules`` is the list of enabled rule
    texts in position order (Mission 27 DD1/DD5). ``notes`` is ``None`` when
    the agent's notes are off (layer omitted), ``[]`` when on with none saved
    ("No saved notes yet."), else the notes by number (M27 F2, DD9). When
    ``notes`` is not ``None`` the rules layer gains "Rules take precedence over
    saved notes.".

    With ``rules`` empty and ``notes`` ``None`` the output is byte-identical to the
    pre-Mission-27 ``{base}\\n\\n---\\n\\n{persona}`` shape.

    ``date_line`` (M28 F1, DD4), when not ``None``, is appended as the LAST
    layer after a "---" separator (so notes are no longer the final layer).
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
        parts.append(render_notes_block(notes))
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
