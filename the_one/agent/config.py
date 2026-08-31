"""Agent configuration model and base system prompt."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

BASE_PROMPT = """\
You are an AI agent with access to a set of tools. Use them to accomplish what the \
operator asks.

Tool discovery:
- At the start of each conversation, you have only `search_tools` and `continue` \
available.
- To use any other capability, call `search_tools` with a query describing what you \
need. The catalog covers BOTH built-in tools (shell, file operations, web fetch, \
etc.) AND tools from any MCP servers attached to this agent — they all surface \
through this one tool. Empty query lists everything; a specific query narrows \
results.
- Results are grouped by source: `built-in: …` for built-in tools, `mcp:<server>: …` \
for MCP server tools. Don't second-guess which catalog has what — just search by \
intent ("issue tracker", "read a file", "http request") and the right tools will \
surface regardless of where they come from.
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


def compose_system_prompt(base: str, persona: str) -> str:
    """Compose the agent's system prompt: ``base``, optionally appended
    with a per-agent ``persona`` via a "---" separator.

    Mission 23 Flight 1 (backend-removal leg): the connector-aware
    extension point (``connector_attached``/``send_tool_enabled`` kwargs
    and the auto-relay directive they selected) was removed with the
    connector subsystem — every caller now gets the plain
    ``{base}\\n\\n---\\n\\n{persona}`` shape unconditionally.
    """
    parts = [base]
    if persona:
        parts.append("---")
        parts.append(persona)
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

    def is_tool_enabled(self, tool_name: str) -> bool:
        """Check if a specific tool should be available to this agent.

        The ``enabled_tools`` whitelist governs **built-in tools only**.
        MCP tools — canonically prefixed ``mcp__`` at registration
        (``mcp/_tool.py:101``; cf. ``_MCP_PREFIX`` in
        ``tools/_search_tools.py``) — are governed by ``mcp_overrides``,
        applied upstream at agent build via
        ``MCPToolProvider.get_tools_for_agent`` /
        ``filter_mcp_tools_by_override``. Applying the built-ins-only
        whitelist to MCP names too would double-gate them: the agent
        editor populates ``enabled_tools`` from built-in checkboxes only,
        so any non-null whitelist it emits excludes every ``mcp__`` name
        and would silently strip all MCP tools (F09-08). Decoupling here
        stops that; ``disabled_tools`` stays a UNIVERSAL explicit
        blacklist (an ``mcp__…`` name listed there is still disabled).

        ``enabled_tools == []`` (empty whitelist) blocks all **built-in**
        tools but does NOT block MCP tools, consistent with the decouple
        (MCP enablement is governed solely by ``mcp_overrides``).
        """
        is_mcp = tool_name.startswith("mcp__")
        if not is_mcp and self.enabled_tools is not None and tool_name not in self.enabled_tools:
            return False
        if tool_name in self.disabled_tools:
            return False
        return True

    def get_system_prompt(self) -> str:
        """Return the resolved system prompt: BASE_PROMPT, optionally
        appended with a per-agent persona via a "---" separator.
        """
        return compose_system_prompt(BASE_PROMPT, self.system_prompt)
