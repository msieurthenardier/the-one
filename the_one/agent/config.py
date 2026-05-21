"""Agent configuration model and base system prompt."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

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
    "platform (Discord, Slack, etc.). Messages tagged ``visibility=\"platform\"`` "
    "in the history came from platform peers; messages tagged "
    "``visibility=\"operator\"`` came from the operator's private local Chat "
    "console. When a platform-peer message in this session needs a response, "
    "you MUST call the ``send_to_platform_channel`` tool to deliver your reply "
    "to peers — your plain-text replies in this session reach only the "
    "operator's local console, NOT peers. The operator console is for the "
    "operator to direct or observe you; only deliberate ``send_to_platform_channel`` "
    "calls reach the platform. The tool takes a target (account_id, channel_id, "
    "and optional thread_id) plus content. Use the account_id and channel_id "
    "from the platform-inbound message you're replying to."
)

_CONNECTOR_AUTO_RELAY_DIRECTIVE = (
    "This conversation is attached to a connector account on an external "
    "platform (Discord, Slack, etc.). Auto-relay is ON: your plaintext "
    "replies in this session ARE automatically delivered to platform peers "
    "— treat the conversation as the platform conversation itself. Do NOT "
    "ask the operator for permission to respond on the platform; do NOT "
    "narrate that you're 'using send_to_platform_channel'; just reply "
    "naturally as you would in any chat. Messages tagged "
    "``visibility=\"platform\"`` in the history came from platform peers; "
    "messages tagged ``visibility=\"operator\"`` came from the operator's "
    "private local Chat console (operator-only — these are NOT relayed). "
    "If you need to send a message to a different channel or thread on "
    "the platform (not the current channel), use the "
    "``send_to_platform_channel`` tool explicitly with a target "
    "specifying that destination."
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
    auto_relay: bool = True,
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
    - ``connector_attached AND send_tool_enabled AND auto_relay`` →
      :data:`_CONNECTOR_AUTO_RELAY_DIRECTIVE` (informs the agent that
      its plaintext replies ARE the platform reply by default; do not
      ask permission to respond on the platform).
    - ``connector_attached AND send_tool_enabled AND NOT auto_relay`` →
      :data:`_CONNECTOR_TOOL_ENABLED_DIRECTIVE` (instructs the agent to
      call the platform-send tool to reach peers; opt-out path from
      L11 HAT Fix #4).
    - ``connector_attached AND NOT send_tool_enabled`` →
      :data:`_CONNECTOR_TOOL_DISABLED_DIRECTIVE` (informs the agent that
      platform-send is operator-disabled and its replies stay local).
      The ``auto_relay`` value is moot when send is disabled.

    M10 F8 L11 HAT Fix #5: the auto-relay branch fixes the broken UX
    where Fix #4's mechanical auto-relay combined with the Fix #1
    directive ("plaintext reaches only the operator") produced agents
    that ask for permission to reply on the platform — and then the
    auto-relay posts THAT question to the platform.
    """
    parts = [base]
    if connector_attached:
        if send_tool_enabled:
            if auto_relay:
                parts.append(_CONNECTOR_AUTO_RELAY_DIRECTIVE)
            else:
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

    # M10 F6 L1c: per-agent ACL overrides keyed by account_id.
    # Shape: {account_id: {"peers": list[str] | None,
    #                       "channels": list[str] | None}}.
    #
    # M10 F6 L7 HAT — semantic redesign (see flight-log "Deviations"):
    # each per-axis value is tri-state:
    #   - ``None`` → INHERIT account-scope (no per-agent narrowing on
    #     this axis)
    #   - ``[]`` (explicit empty list) → "no access" sentinel for this
    #     axis. For peers, no peer is permitted; for channels, "DMs only"
    #     — but DM classification ships in F8 (Discord), so until then
    #     the runtime fails closed on outbound non-DM channels.
    #   - ``[items]`` → subset (intersected with account-scope on this
    #     axis).
    #
    # The two axes are INDEPENDENTLY overridable. Both keys
    # (``"peers"``, ``"channels"``) MUST be present in each per-account
    # entry; partial entries are rejected by the validator below — the
    # operator's per-axis intent is captured by ``None`` vs ``[]`` vs
    # ``[items]``, not by key omission.
    #
    # ``None`` (the field default) and ``{}`` (empty outer dict) are
    # both valid and mean "no per-agent narrowing for any account."
    # An entry being ABSENT from a non-empty outer dict ALSO means
    # "inherit account-scope" for that specific account.
    #
    # Inner type ``dict[str, list[str] | None]`` (NOT bare ``dict``) so
    # Pydantic v2 validates each inner value — mirrors the same
    # rationale as ``tool_overrides`` and ``mcp_overrides`` above.
    connector_acls: dict[str, dict[str, list[str] | None]] | None = None

    # Behavior
    max_iterations: int = 20

    @field_validator("connector_acls", mode="after")
    @classmethod
    def _validate_connector_acls(
        cls, value: dict[str, dict[str, list[str] | None]] | None
    ) -> dict[str, dict[str, list[str] | None]] | None:
        """Enforce exact-keys shape on per-account ACL inner dicts.

        Pydantic v2's ``dict[str, dict[str, list[str] | None]]``
        annotation already enforces:
          - non-string outer keys → rejected (``string_type`` error)
          - non-dict outer values → rejected (``dict_type`` error)
          - inner values that aren't ``list[str] | None`` → rejected
        This validator's job is the ONE invariant Pydantic cannot
        express from the annotation alone: each inner dict MUST have
        the required keys ``{"peers", "channels"}`` and MAY optionally
        carry the M10 F8 L8 axes ``{"guilds", "roles"}`` — no other
        keys, no missing required keys.

        M10 F6 L7 HAT semantic — each axis is tri-state:
          - ``None`` → inherit account-scope
          - ``[]`` → explicit empty (peers: no peer; channels: DMs-only
            sentinel; runtime resolution for DMs-only ships in F8 — until
            then outbound fails closed)
          - ``[items]`` → subset (intersected with account-scope)

        M10 F8 L8 — ``guilds`` and ``roles`` axes (Discord-flavored)
        join the inner-dict surface as OPTIONAL keys. Existing 2-key
        ACL rows still validate (back-compat). Same tri-state semantic
        applies; the per-agent narrowing convention is uniform across
        all 4 axes.

        ``None`` and ``{}`` outer values are both valid (semantically:
        no per-agent narrowing).

        Pydantic v2 ``@field_validator(mode="after")`` runs on both
        ``model_validate`` and direct ``BaseModel(**kwargs)`` so the
        repository read path at ``_row_to_config`` is validated without
        a separate ``model_validate`` wrapper.
        """
        if value is None:
            return value
        for account_id, acl in value.items():
            # Pydantic already enforced ``acl`` is a dict with str keys
            # and inner values are ``list[str] | None``.
            # The only invariant left is the exact-keys check.
            # M10 F8 L8 — accept ``guilds`` + ``roles`` as OPTIONAL
            # axes alongside the required ``peers`` + ``channels``.
            keys = set(acl.keys())
            extra = keys - {"peers", "channels", "guilds", "roles"}
            if extra:
                raise ValueError(
                    f"connector_acls[{account_id!r}] has unexpected keys: "
                    f"{sorted(extra)}"
                )
            missing = {"peers", "channels"} - keys
            if missing:
                raise ValueError(
                    f"connector_acls[{account_id!r}] is missing required "
                    f"keys: {sorted(missing)}"
                )
        return value

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
            auto_relay=True,
        )
