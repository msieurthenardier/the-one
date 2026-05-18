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


_CONNECTOR_TOOL_ENABLED_DIRECTIVE = (
    "This conversation is attached to a connector account on an external "
    "platform. Your plain-text replies in this session reach the operator "
    "only — to reply to peers on the external platform, call the "
    "`send_to_platform_channel` tool with the target (account_id, "
    "channel_id, and optional thread_id) and the content to send."
)

_CONNECTOR_TOOL_DISABLED_DIRECTIVE = (
    "This conversation is attached to a connector account on an external "
    "platform, but the platform-send capability is currently DISABLED by "
    "the operator. Your replies in this session reach the operator only "
    "— they do not reach the external platform. The "
    "`send_to_platform_channel` tool is not available right now. Do not "
    "claim to have sent anything to the platform."
)


def compose_system_prompt(
    base: str,
    persona: str,
    *,
    connector_attached: bool = False,
    send_tool_enabled: bool = False,
) -> str:
    """Compose the agent's system prompt.

    Mission 10 Flight 4 Leg 3. Adds a connector-aware extension point so
    agents attached to a connector account receive an explicit directive
    about how their outbound flows.

    Non-connector callers (``AgentConfig.get_system_prompt()`` for
    persistence/edit-form use; the WS handler's prompt-equivalence
    checks) pass ``connector_attached=False`` and receive byte-identical
    output to the pre-F4 ``{base}\\n\\n---\\n\\n{persona}`` shape.

    The connector-aware path inserts a directive between ``base`` and
    the persona separator:
    - ``connector_attached AND send_tool_enabled`` →
      :data:`_CONNECTOR_TOOL_ENABLED_DIRECTIVE` (instructs the agent to
      call the platform-send tool to reach peers).
    - ``connector_attached AND NOT send_tool_enabled`` →
      :data:`_CONNECTOR_TOOL_DISABLED_DIRECTIVE` (informs the agent that
      platform-send is operator-disabled and its replies stay local).
    """
    parts = [base]
    if connector_attached:
        if send_tool_enabled:
            parts.append(_CONNECTOR_TOOL_ENABLED_DIRECTIVE)
        else:
            parts.append(_CONNECTOR_TOOL_DISABLED_DIRECTIVE)
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
    # M10 F4: connector accounts attached to this agent. Mirror of mcp_source_ids.
    connector_account_ids: list[str] = Field(default_factory=list)

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

    def is_tool_enabled(self, tool_name: str) -> bool:
        """Check if a specific tool should be available to this agent."""
        if self.enabled_tools is not None and tool_name not in self.enabled_tools:
            return False
        if tool_name in self.disabled_tools:
            return False
        return True

    def get_system_prompt(self) -> str:
        """Return the resolved system prompt: BASE_PROMPT, optionally
        appended with a per-agent persona via a "---" separator.

        Non-connector callers (persistence edit form, WS handler's
        prompt-equivalence checks) use this method. The factory uses
        :func:`compose_system_prompt` directly with the actual connector
        flags so its output reflects the connector state.
        """
        return compose_system_prompt(
            BASE_PROMPT,
            self.system_prompt,
            connector_attached=False,
            send_tool_enabled=False,
        )
