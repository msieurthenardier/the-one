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


# ── Connector system-prompt directive (M11 F7 L9) ─────────────────────
#
# A single directive is appended whenever the agent is attached to a
# connector account. F7 made auto-relay an invariant of engaged turns
# (mentions, DMs, ``/talk_to`` redirects, or inference-yes turns reach
# the agent; everything else is silenced upstream by the L8 policy
# gate). The pre-F7 OFF directive (and the ``auto_relay`` kwarg that
# selected it) was deleted in this leg — there is no longer an OFF
# state to describe.
#
# The directive forward-references L10's history tools
# (``fetch_channel_history`` / ``fetch_thread_history`` /
# ``fetch_dm_history`` / ``list_visible_channels``) with "if available"
# hedging so the prompt stays truthful both pre-L10 (tools not yet
# registered → "tool not available" on call) and post-L10 (tools
# registered → calls succeed). This matches the pre-F7 OFF directive's
# hedging pattern around ``send_to_platform_channel``.
#
# KEEP IN SYNC WITH JS twin in
# ``the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js``
# only if a Session-section codeblock surface re-emerges; L5 removed
# all four JS sites that mirrored the pre-F7 directives. Python is the
# sole source of truth post-L9.

_CONNECTOR_AUTO_RELAY_DIRECTIVE = (
    "This conversation is attached to a connector account on an external "
    "platform (Discord, Slack, etc.). You only see messages the system "
    "has decided to engage you on — direct messages, mentions of you, "
    "explicit ``/talk_to`` redirects from peers, or messages a "
    "lightweight inference pre-step decided are worth your response "
    "(the operator can configure this per-account). Messages the "
    "inference step silenced never reach you and are intentionally "
    "invisible.\n\n"
    "Auto-relay is on: your plaintext replies in this session ARE "
    "automatically delivered to platform peers — treat the conversation "
    "as the platform conversation itself. Do NOT ask the operator for "
    "permission to respond on the platform; do NOT narrate that you're "
    "'using send_to_platform_channel'; just reply naturally as you "
    "would in any chat. Messages tagged ``visibility=\"platform\"`` in "
    "the history came from platform peers; messages tagged "
    "``visibility=\"operator\"`` came from the operator's private "
    "local Chat console (operator-only — these are NOT relayed).\n\n"
    "If you need recent channel context beyond what's in this session "
    "(e.g. catching up after a silent stretch), use the "
    "``fetch_channel_history`` / ``fetch_thread_history`` / "
    "``fetch_dm_history`` tools if available. Use "
    "``list_visible_channels`` to discover which channels and peers "
    "you can read. If you need to send a message to a different "
    "channel or thread on the platform (not the current one), use the "
    "``send_to_platform_channel`` tool explicitly with a target "
    "specifying the destination."
)


def compose_system_prompt(
    base: str,
    persona: str,
    *,
    connector_attached: bool = False,
    send_tool_enabled: bool = False,
) -> str:
    """Compose the agent's system prompt.

    Mission 10 Flight 4 Leg 3 introduced the connector-aware extension
    point so agents attached to a connector account receive an explicit
    directive about how their outbound flows.

    Non-connector callers (``AgentConfig.get_system_prompt()`` for
    persistence/edit-form use; the WS handler's prompt-equivalence
    checks) pass ``connector_attached=False`` and receive byte-identical
    output to the pre-F4 ``{base}\\n\\n---\\n\\n{persona}`` shape.

    M11 F7 L9: the directive surface collapsed to a single directive.
    F7 made auto-relay an invariant of engaged turns — the L8 policy
    gate (mentions, DMs, ``/talk_to``, or inference-yes) silences
    everything else upstream, so the LLM never sees a turn it shouldn't
    relay on. The pre-F7 OFF directive and the ``auto_relay`` kwarg
    that selected it were both deleted here; the surviving directive
    is unconditionally appended whenever ``connector_attached=True``.
    It forward-references L10's history tools
    (``fetch_channel_history`` etc.) with "if available" hedging so it
    stays truthful pre-L10 and post-L10.

    ``send_tool_enabled`` is RETAINED IN THE SIGNATURE BUT NOT
    CONSULTED in directive selection — the directive is now
    unconditional when ``connector_attached=True``. The factory still
    computes ``send_tool_enabled`` for unrelated purposes (the F10
    carve-out that pre-loads the send tool's schema into the agent's
    visible-schema set); keeping the kwarg avoids churning the
    factory call site for a no-op semantic change. The new directive's
    wording covers both tool-enabled and tool-disabled cases via the
    explicit ``send_to_platform_channel`` mention — when the tool is
    disabled, the LLM cannot call it regardless of the prompt.
    """
    parts = [base]
    if connector_attached:
        parts.append(_CONNECTOR_AUTO_RELAY_DIRECTIVE)
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
    connector_ids: list[str] = Field(default_factory=list)

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
    connector_acls: dict[str, dict[str, list[str] | bool | None]] | None = None

    # M11 F7 L6: per-agent ``always_listen`` toggle keyed by account_id.
    # Shape: ``{account_id: bool}``. ``True`` means the agent listens to
    # all messages on that account (bypassing the F7 default mentions-only
    # gate); ``False`` (or absent) means the agent stays mentions-only on
    # that account.
    #
    # Precondition (set by M11 F7 L5): the account-level
    # ``Connector.config["always_listen"]`` is the master gate. A
    # per-agent ``True`` here is structurally inert when the account-level
    # switch is False — the L8 policy-gate consult site checks account
    # first and short-circuits. The validator does NOT enforce this
    # composition; per Flight DD §8, "accept-and-document is the lighter
    # discipline."
    #
    # ``None`` (field default) and ``{}`` are both valid (no per-agent
    # override). ``None`` decodes from NULL DB rows (pre-v20 agents AND
    # new agents without per-agent overrides); ``{}`` decodes from
    # ``"{}"`` JSON (an agent that was edited then had all toggles
    # removed). Both have the same runtime semantic; the codec preserves
    # the distinction for round-trip fidelity (mirrors ``connector_acls``).
    #
    # L8 consult pattern (per the leg DD): absent account_id → False
    # (the per-agent default). Read site mirrors the L5 account-level
    # read: ``config.connector_always_listen.get(account_id, False) if
    # config.connector_always_listen else False``.
    connector_always_listen: dict[str, bool] | None = None

    # Behavior
    max_iterations: int = 20

    @field_validator("connector_acls", mode="after")
    @classmethod
    def _validate_connector_acls(
        cls, value: dict[str, dict[str, list[str] | bool | None]] | None
    ) -> dict[str, dict[str, list[str] | bool | None]] | None:
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
            # and inner values are ``list[str] | bool | None``.
            # The only invariant left is the exact-keys check.
            # M10 F8 L8 — accept ``guilds`` + ``roles`` as OPTIONAL
            # axes alongside the required ``peers`` + ``channels``.
            # M11 F10 L1 — accept ``admit_dms`` as OPTIONAL per-agent
            # DM-admission opt-out (``bool | None``; ``None`` and absent
            # both mean inherit account-scope ``dm_admission``).
            keys = set(acl.keys())
            extra = keys - {"peers", "channels", "guilds", "roles", "admit_dms"}
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

            # M11 F10 L1: per-key value-type validation. The widened
            # annotation ``dict[str, list[str] | bool | None]`` accepts
            # either type for any key; this branch enforces the intended
            # type per key — ``admit_dms`` is ``bool | None``;
            # ``peers``/``channels``/``guilds``/``roles`` are
            # ``list[str] | None`` (per-item string check restored).
            for key, value_at_key in acl.items():
                if key == "admit_dms":
                    if value_at_key is not None and not isinstance(
                        value_at_key, bool
                    ):
                        raise ValueError(
                            f"connector_acls[{account_id!r}]['admit_dms'] "
                            f"must be bool or None; got "
                            f"{type(value_at_key).__name__}"
                        )
                else:
                    # peers, channels, guilds, roles — list[str] | None
                    if value_at_key is not None and not isinstance(
                        value_at_key, list
                    ):
                        raise ValueError(
                            f"connector_acls[{account_id!r}][{key!r}] must "
                            f"be list[str] or None; got "
                            f"{type(value_at_key).__name__}"
                        )
                    if isinstance(value_at_key, list):
                        for i, item in enumerate(value_at_key):
                            if not isinstance(item, str):
                                raise ValueError(
                                    f"connector_acls[{account_id!r}]"
                                    f"[{key!r}][{i}] must be a string"
                                )
        return value

    @field_validator("connector_always_listen", mode="after")
    @classmethod
    def _validate_connector_always_listen(
        cls, value: dict[str, bool] | None
    ) -> dict[str, bool] | None:
        """Enforce inner-value bool invariants on the per-agent toggle dict.

        Shape contract: outer keys are account_id strings (enforced by the
        ``dict[str, bool]`` annotation; Pydantic v2 coerces or rejects
        non-str keys before the validator runs). Inner values must be bools
        — defensively enforced here against truthy-but-non-bool smuggling
        through the kv-table or raw-JSON edit paths.

        Runtime semantic (NOT validator-enforced — composition happens at
        the L8 policy-gate consult site):
        - The account-level ``always_listen`` switch (L5) is the master
          gate; per-agent True is structurally inert when account-level
          is False (the account check short-circuits).
        - Absent account_id in the dict → False (the per-agent default).
        - Explicit False is equivalent to absent and round-trips as-is so
          the codec preserves the operator's intent.

        Per Flight DD §8: "accept-and-document is the lighter discipline"
        — the validator does NOT reject inconsistent (per-agent True +
        account-level False) configurations; the dispatcher's gate
        composition handles them correctly at runtime.
        """
        if value is None:
            return value
        for account_id, toggle in value.items():
            if not isinstance(toggle, bool):
                raise ValueError(
                    f"connector_always_listen[{account_id!r}] must be a bool "
                    f"(True or False); got {type(toggle).__name__}: {toggle!r}"
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
        )
