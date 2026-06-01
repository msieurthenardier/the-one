"""Platform-side command text-prefix parser + built-in dispatcher.

M10 F07 L1: parses leading-slash commands of the form ``/<name> [args...]``
from an inbound envelope's text. v1 vocabulary: ``/agents``, ``/talk-to``,
``/whoami``, ``/new``, ``/reset``, ``/help``.

M10 F07 L5: ships :func:`_dispatch_builtin_command` as a placeholder that
returns ``None`` for every command_name. The L5 inbound dispatcher wires
the parser + placeholder so the integration code path
(parse → dispatch → fall-through to ``agent.step``) is exercised end-to-end
without depending on the L6 handler implementations.

M10 F07 L6: replaces the placeholder body with the six v1 command
handlers. Each handler is a private async function that consumes the
dispatcher context dict and returns a :class:`CommandResponse`. Unknown
command names (those not in v1 vocabulary) continue to return ``None`` —
the dispatcher falls through to ``agent.step``, treating them as regular
user messages.

The parser is a pure function — no I/O. Mirrors
:mod:`the_one.connectors._pairing`'s shape: byte-equality comparisons,
no regex, returns a discriminated value the dispatcher can branch on.
Case-sensitive (lowercase command names only) — same convention as
:func:`_validate_pairing_prefix`'s ``PAIR`` keyword.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from the_one.connectors._acl import AdmissionContext, admits_inbound
from the_one.connectors.base import CommandResponse, InboundEnvelope
from the_one.db.models import Connector, now_iso

_COMMAND_PREFIX = "/"

# Lowercase letters / digits / hyphen for the command word's tail.
# The leading character must be a lowercase letter — matches the slug
# shape used elsewhere in the project (agent names, connector type
# identifiers, etc.). Frozen literal sets (NOT ``string.ascii_lowercase``)
# match the project's existing character-class convention — see
# ``_INTERACTIVE_SHELL_BASENAMES``, ``GATED_METHODS``, ``OAUTH_MANAGED_SECRET_KEYS``;
# zero existing ``import string`` usages in ``the_one/``.
_NAME_HEAD_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz")
_NAME_TAIL_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")


def _parse_command(text: str) -> tuple[str, list[str]] | None:
    """Parse ``text`` as ``/<name> [args...]``.

    Returns ``(command_name, args)`` if ``text`` starts with a single
    forward slash, the next character is a lowercase letter, the
    following characters are all in ``[a-z0-9-]``, and the command name
    is terminated either by end-of-string or by whitespace.

    Returns ``None`` if any of those conditions fail (including: empty
    text, leading whitespace, a non-slash prefix, a double slash, an
    uppercase or underscore in the name, etc.).

    ``args`` is ``text``'s post-name remainder split on whitespace via
    :meth:`str.split` (no argument) — runs of whitespace collapse;
    trailing whitespace alone produces no args.
    """
    if not text.startswith(_COMMAND_PREFIX):
        return None
    rest = text[len(_COMMAND_PREFIX) :]
    if not rest:
        return None
    head = rest[0]
    if head not in _NAME_HEAD_CHARS:
        return None
    # Walk the name characters until we hit whitespace or end-of-string.
    name_end = 1
    while name_end < len(rest):
        c = rest[name_end]
        if c.isspace():
            break
        if c not in _NAME_TAIL_CHARS:
            return None
        name_end += 1
    command_name = rest[:name_end]
    args_text = rest[name_end:]
    args = args_text.split()
    return command_name, args


def _permitted_agents(context: dict[str, Any]) -> list[str]:
    """Return alphabetically-ordered agent names that the envelope's
    peer is permitted to invoke on the account (filtered by per-agent
    ACL via :func:`admits_inbound`).

    Consumes ``context["account"]``, ``context["envelope"]``,
    ``context["eligible_attached_agents"]``, and ``context["plugin"]``
    (the resolved :class:`ConnectorPlugin`; the dispatcher always
    supplies it — see :func:`dispatch_inbound`'s command-context
    builder). The dispatcher hands us the alphabetically-ordered
    ``list[AgentConfig]`` of attached agents; this helper applies the
    per-agent ACL filter on top.

    F14 L1 (Bug D): this secondary admission now threads the full
    envelope context (``is_dm`` via the shared
    :func:`the_one.connectors._acl.envelope_is_dm` helper, plus
    ``guild_id`` / ``member_roles`` read from ``envelope.raw``) into
    :func:`admits_inbound` — byte-for-byte aligned with the routing
    path's primary admission at :func:`_routing._agent_admits`. Without
    these kwargs the post-F12 structured-tuple channel allowlist wrongly
    denies every slash command under a real Discord guild.

    Pure-with-context — no I/O. Mirrors :func:`admits_inbound`'s
    short-circuit shape.
    """
    account: Connector = context["account"]
    envelope: InboundEnvelope = context["envelope"]
    eligible = context["eligible_attached_agents"]
    plugin = context["plugin"]
    # M11 F14 L8 — the admission context is agent-independent (it derives
    # only from the envelope + plugin), so build it ONCE outside the
    # eligible-agents loop and reuse it for every agent's per-agent ACL
    # check. from_envelope owns the is_dm / guild_id / member_roles
    # derivation formerly inlined here.
    ctx = AdmissionContext.from_envelope(envelope, plugin)
    permitted: list[str] = []
    for agent_config in eligible:
        agent_acl: dict[str, list[str] | None] | None = None
        if agent_config.connector_acls is not None:
            agent_acl = agent_config.connector_acls.get(account.id)
        admits, _reason = admits_inbound(account, agent_acl, ctx)
        if admits:
            permitted.append(agent_config.name)
    return permitted


async def _handle_agents(context: dict[str, Any]) -> CommandResponse:
    """Handler for ``/agents`` — list ACL-permitted attached agents.

    Returns the alphabetically-ordered names of agents the inbound's
    peer is permitted to invoke on this account. If the permitted list
    is empty, returns the no-eligible string used by the L5 dispatcher's
    no-eligible peer-facing path — unified byte-for-byte for consistency.
    """
    names = _permitted_agents(context)
    if not names:
        return CommandResponse(
            text="No agents available for this conversation.", ephemeral=True
        )
    lines = ["Agents available to you on this account:"]
    lines.extend(f"- {name}" for name in names)
    return CommandResponse(text="\n".join(lines), ephemeral=True)


async def _handle_talk_to(context: dict[str, Any]) -> CommandResponse:
    """Handler for ``/talk-to <agent-slug>`` — set the session's
    ``routing_override`` to the requested agent.

    Reads ``context["args"]``. Empty args ⇒ "Usage:" message. Unknown
    or ACL-denied slug ⇒ peer-facing error. Valid slug ⇒
    :meth:`ChatSessionRepository.set_session_metadata_key` writes
    ``"routing_override" = <slug>`` (last-writer-wins concurrency
    posture); returns a confirmation text. The L4 routing engine reads
    the override on the NEXT inbound (step 1 of its 5-step algorithm).

    The agent slug is the FULL remainder of the command line (all
    tokens joined with spaces).  When the slash body is re-parsed after
    Discord's underscore→hyphen normalisation, a multi-word agent name
    (e.g. "Sonos Agent") arrives as separate tokens in ``args``; joining
    them reconstructs the original name.
    """
    args: list[str] = context["args"]
    if not args:
        return CommandResponse(text="Usage: /talk-to <agent-slug>")
    target = " ".join(args)
    permitted = _permitted_agents(context)
    if target not in permitted:
        return CommandResponse(
            text=f"No such agent or you don't have permission: {target}"
        )
    chat_repo = context["chat_repo"]
    session_id: str = context["session_id"]
    await chat_repo.set_session_metadata_key(session_id, "routing_override", target)
    return CommandResponse(text=f"Now routing your messages to {target}.")


async def _handle_whoami(context: dict[str, Any]) -> CommandResponse:
    """Handler for ``/whoami`` — return the routed agent for THIS turn.

    Reads ``context["routed_agent_name"]`` (set by the L5 dispatcher
    from the routing engine's decision). No DB read — the dispatcher
    has already routed the current inbound to this agent.

    Note: a preceding ``/talk-to`` in the SAME inbound turn would not
    have effect here — the override applies to the next inbound. The
    handler reports the agent that is currently handling THIS message.
    """
    routed = context["routed_agent_name"]
    return CommandResponse(text=f"Currently responding: {routed}.", ephemeral=True)


async def _handle_new(context: dict[str, Any]) -> CommandResponse:
    """Handler for ``/new`` — mark the current session as ended.

    Writes ``session_metadata["ended_at"] = now_iso()`` via
    :meth:`ChatSessionRepository.set_session_metadata_key`. The next
    inbound creates a fresh session via :func:`resolve_session`'s
    ``ended_at`` sentinel check in the reuse path.
    """
    chat_repo = context["chat_repo"]
    session_id: str = context["session_id"]
    await chat_repo.set_session_metadata_key(session_id, "ended_at", now_iso())
    return CommandResponse(
        text=(
            "Started a new conversation. Your next message will begin a "
            "fresh session."
        )
    )


async def _handle_reset(context: dict[str, Any]) -> CommandResponse:
    """Handler for ``/reset`` — alias for ``/new``.

    M10 F7 L6 ships alias-only semantics; ``/reset`` and ``/new``
    produce the same response text and the same ``ended_at``
    side-effect. A future HAT / mission may differentiate the two
    semantics (e.g. ``/reset`` clearing routing override too); the
    aliasing here is the minimal v1 surface.
    """
    return await _handle_new(context)


async def _handle_help(context: dict[str, Any]) -> CommandResponse:
    """Handler for ``/help`` — list available commands.

    Permission-filtered per the flight Design Decision: ``/whoami``,
    ``/new``, ``/reset``, ``/help`` are ALWAYS listed; ``/agents`` and
    ``/talk-to`` are listed only when :func:`_permitted_agents` is
    non-empty for the inbound's peer.
    """
    lines = ["Available commands:"]
    if _permitted_agents(context):
        lines.append("- /agents — list agents you can talk to here")
        lines.append("- /talk-to <agent> — switch to a different agent")
    lines.append("- /whoami — show which agent is currently responding")
    lines.append("- /new — start a fresh conversation")
    lines.append("- /reset — alias for /new")
    lines.append("- /help — show this list")
    return CommandResponse(text="\n".join(lines), ephemeral=True)


_HANDLERS: dict[str, Callable[[dict[str, Any]], Awaitable[CommandResponse]]] = {
    "agents": _handle_agents,
    "talk-to": _handle_talk_to,
    "whoami": _handle_whoami,
    "new": _handle_new,
    "reset": _handle_reset,
    "help": _handle_help,
}


async def _dispatch_builtin_command(
    command_name: str,
    args: list[str],
    context: dict[str, Any],
) -> CommandResponse | None:
    """Dispatch a parsed v1 command to its handler.

    M10 F7 L6: replaces the L5 placeholder that returned ``None`` for
    every command. Unknown command names (those not in v1 vocabulary)
    continue to return ``None`` — the dispatcher falls through to
    ``agent.step``, treating them as regular user messages.

    The ``context`` dict is the L5 dispatcher's per-invocation state:

    - ``account`` — the :class:`Connector` for the inbound.
    - ``envelope`` — the (possibly cleaned) :class:`InboundEnvelope`.
    - ``eligible_attached_agents`` — the alphabetically-ordered list
      of :class:`AgentConfig` attached to this account.
    - ``routed_agent_name`` — the agent ``RoutingDecision.agent`` from
      the L4 engine (always a string when this dispatcher fires; the
      ``decision.agent is None`` path is handled before this call).
    - ``session_id`` — the resolved ``chat_sessions.id``.
    - ``chat_repo`` — the :class:`ChatSessionRepository` instance for
      ``set_session_metadata_key`` writes.

    L6 packs ``args`` (the parsed argument list) into the context
    under the ``args`` key before invoking the handler — keeps handler
    signatures uniform at ``async def _handle_X(context) -> ...``.

    Distinct from returning ``CommandResponse(text="")``: ``None``
    means "fall through to ``agent.step``"; an empty-text response
    means "command handled with intentionally empty reply" and the
    dispatcher MUST emit it via the system-outbound path without
    falling through. See :class:`CommandResponse` in
    ``connectors/base.py``.
    """
    # Discord slash-command names use underscores (hyphens are rejected by
    # the API), while the F7 v1 vocabulary uses hyphens.  Try the exact
    # name first (covers every non-hyphenated command); if that misses,
    # normalise underscores → hyphens as a belt-and-suspenders backstop.
    # PRIMARY FIX: ``_build_slash_envelope`` in _discord.py now hyphenates
    # the command name before synthesizing the envelope text, so
    # ``_parse_command`` always yields ``"talk-to"`` (not ``"talk_to"``) —
    # the underscore form never reaches this dispatcher via the real path.
    # This normalisation remains as a defensive depth layer against any
    # future caller that skips the envelope layer and invokes dispatch
    # directly with an underscore-form name.
    # Unknown commands still return None (fall through to agent.step).
    handler = _HANDLERS.get(command_name) or _HANDLERS.get(
        command_name.replace("_", "-")
    )
    if handler is None:
        return None
    context["args"] = args
    return await handler(context)
