"""Inbound dispatcher — composes pool + session resolver + per-session lock
+ agent.step into the end-to-end ingestion path for a connector-driven
message.

M10 F03 L04. This is the contract F8 (Discord) and F9 (the second
connector) will satisfy when they replace the F1-stub-driven inbound
with a real gateway-driven inbound. F3's stub-based tests prove the
contract holds against a synthetic envelope; F8 wires the real Discord
gateway to call this same ``dispatch_inbound``.

F4 (platform-send tool) owns outbound. This module is INBOUND ONLY —
EXCEPT for the L5-introduced **system-outbound path** for command
responses and the no-eligible peer-facing error, which mirrors the
platform-send tool's ``account_acquire → client.send`` shape but is
invoked dispatcher-internally (NOT through the tool registry).

The connector pool's :func:`account_acquire` is called per inbound
here — that is the **last_activity ratification** of the F1 Known
Issue (see ``the_one/agents.md``'s Connector subsystem section). The
dispatcher does NOT cache the :class:`ConnectorClient` reference
outside the pool; every inbound goes through ``account_acquire``.

Per-session serialization shares the SAME asyncio.Lock with
the WS handler. The lock registry lives at
``the_one.sessions.session_locks``; see F5 L2 for the
unification that closed the M10 mission Known Issue.

M10 F06 L2 — F6 gating contract.
================================

Resolver consult: after ``resolve_session`` materializes the session
row, the dispatcher consults ``getattr(plugin, "resolve",
_default_permit)(account, envelope)`` for EVERY inbound — Permit,
NeedsPairing, and Deny outcomes all enter the consult. The session
exists before the consult so audit-log writes have a target row. An
``StubPlugin`` (without ``resolve``) hits the ``_default_permit``
fallback and behaves byte-identically to pre-F6.

Audit-log shape: each gate decision appends an entry to
``session_metadata["audit"]`` via
:meth:`ChatSessionRepository.append_to_session_metadata`. The entry
shape is uniform — ``{"outcome", "peer_id", "ts", "reason"}`` — with
``reason: None`` on default-permit so the leg-4 Studio renderer reads
all four keys without per-entry shape checks.

``last_inbound_at`` on Deny / NeedsPairing-failure: the existing
dispatcher calls ``update_last_inbound`` INSIDE the per-session lock
(below). Deny and NeedsPairing-failure branches ``return`` BEFORE
entering the lock — so ``last_inbound_at`` is NOT bumped on denied
messages. This is deliberate: denied messages should not extend the
continuation window.

M10 F07 L5 — Routing + command-intercept integration.
=====================================================

The dispatcher's body composes 12 steps in a fixed canonical order
(AC bullets in the leg artifact reference the same numbering):

1. Function-local imports (load-cycle convention).
2. Account load.
3. Plugin resolve.
4. Enumerate eligible attached agents via
   :meth:`SQLiteAgentStore.list_by_connector_account` — REPLACES the
   L3 transitional helper. Empty list ⇒ silent return (preserves L3's
   no-attached-agents semantic).
5. ``resolve_session`` — uses ``eligible_attached_agents[0].name`` as
   the creation-time anchor for new rows; reuse path ignores
   ``agent_name``.
6. F6 resolver consult (``Permit`` / ``NeedsPairing`` / ``Deny``).
   Sets ``working_envelope``.
7. F7 routing engine consult — :func:`resolve_routing` walks
   override → rule-walk → default → first-eligible-alphabetical →
   no-eligible. The engine consults :func:`admits_inbound` internally
   for each candidate; this dispatcher does NOT re-check ACL on the
   engine's output.
8. Build the routing audit entry (``ts``, ``agent``, ``rule_index``,
   ``scope``, ``match``, ``reason``); ``disposition`` is filled in
   per branch below.
9. No-eligible branch — ``decision.agent is None``: ``disposition =
   "no-eligible"``; append audit entry; emit the peer-facing "No
   agents available for this conversation." via system-outbound using
   ``eligible_attached_agents[0].name`` as the pool key (the bot
   identity reflects the alphabetically-first attached agent's pool
   entry, which IS valid for outbound emission regardless of inbound-
   ACL state). Emit failures are logged + swallowed.
10. Pool acquire for the routed agent — ``account_acquire(account_id)``.
    Account-shared keying (M11 F2 L2, formerly M10 F8 L11 Fix #6):
    ``decision.agent`` drives routing audit but NOT the pool key, so
    all agents attached to one connector account share ONE gateway
    WebSocket. Failure
    ⇒ ``disposition = "no-eligible"`` (overload — the inbound is
    unanswerable so observable shape collapses onto no-eligible);
    append audit entry; return.
11. Command parse + intercept — :func:`_parse_command` on
    ``working_envelope.text``. If a command is parsed, dispatch to
    :func:`_dispatch_builtin_command` (L5 placeholder returns ``None``
    for every command_name; L6 fills the body). ``None`` return ⇒
    fall through to step 12. ``CommandResponse(text)`` ⇒ ``disposition
    = "command-intercepted"``; emit via system-outbound; return
    without the per-session lock or ``agent.step``.
12. Per-session lock + ``agent.step`` — existing F3+F4 logic with
    ``agent_name = decision.agent``. ``disposition = "stepped"``;
    append audit entry; run lock + step + visibility-tagging.

Routing-audit shape (under ``session_metadata["routing"]``,
list-append semantics via :meth:`append_to_session_metadata`):

    {
        "ts": iso_timestamp,
        "agent": slug | None,
        "rule_index": int | None,
        "scope": str | None,
        "match": str | None,
        "reason": str,
        "disposition": "stepped" | "command-intercepted" | "no-eligible",
    }

Mirrors F6's ``session_metadata["audit"]`` entry shape (``ts``,
``reason`` keys reuse F6's naming) so a single Studio renderer can
walk both logs uniformly.

System-outbound path: ``account_acquire(account_id) →
client.send(OutboundTarget(...), text)`` (M11 F2 L2; formerly
``acquire(agent_name, account_id)`` pre-M10 F8 L11). Mirrors
``the_one/tools/connector_send.py:SendToPlatformChannelTool.execute``
lines 183-200 in shape; NOT routed through the platform-send tool
registry. Commands work even when the tool is operator-disabled.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from the_one.agent._context import current_chat_session_id
from the_one.agent.config import AgentConfig
from the_one.agent.factory import AgentFactory
from the_one.connectors import registry
from the_one.connectors._acl import _default_no_mention
from the_one.connectors._inference import run_engagement_inference
from the_one.connectors._pairing import _PAIR_PREFIX, _validate_pairing_prefix
from the_one.connectors._pool import _get_account_cache_snapshot, account_acquire
from the_one.connectors._routing import RoutingDecision, resolve_routing
from the_one.connectors._session import resolve_session
from the_one.connectors.base import (
    ConnectorPlugin,
    Deny,
    InboundEnvelope,
    NeedsPairing,
    OutboundTarget,
    _default_permit,
)
from the_one.connectors.errors import ConnectorRegistrationError
from the_one.connectors.post_step_metadata import (
    bind_channel_context,
    bind_peer_name,
    resolve_channel_name,
    tag_post_step_visibility,
)
from the_one.db.codec import decode_messages, encode_messages, messages_to_ui_events
from the_one.db.models import Connector, now_iso
from the_one.llm.base import Message, Role
from the_one.sessions import broadcast_to_session, session_locks

logger = logging.getLogger(__name__)


async def _policy_gate_decision(
    *,
    envelope: InboundEnvelope,
    account: Connector,
    agent_config: AgentConfig,
    plugin: ConnectorPlugin,
    decision: RoutingDecision,
    session_messages: list[Message],
    conn: Any,
    encryptor: Any,
    settings: Any,
) -> tuple[bool, dict[str, Any]]:
    """Evaluate the F7 policy gate (Flight DD §1 five-path decision tree).

    Returns ``(should_engage, policy_audit)``:

    - ``should_engage`` — True → proceed to step 12; False → silent
      terminal-return.
    - ``policy_audit`` — dict describing the decision path, suitable for
      embedding in ``session_metadata["routing"]`` under the ``policy``
      key.

    Decision tree (first match wins):

    1. ``envelope.raw["is_dm"] is True`` → engage; outcome=``"dm"``.
       DMs ignore the policy gate (DD §1 step 1).
    2. ``decision.scope == "override"`` → engage; outcome=``"override"``.
       A peer's explicit ``/talk-to`` bypasses the gate.
    3. ``plugin.is_mention(envelope)`` returns True → engage;
       outcome=``"mention"``. The consult uses the
       ``optional-plugin-hook-via-getattr-sentinel`` convention with
       :func:`_default_no_mention` as the fallback (plugins without a
       mention concept stay silent-by-default).
    4. ``account.config["always_listen"]`` AND
       ``agent_config.connector_always_listen[account_id]`` both True →
       run inference; outcome=``"inference-yes"`` (engage) or
       ``"inference-no"`` (silent).
    5. Otherwise → silent; outcome=``"always-listen-off"`` (with sub-
       reason indicating which toggle was False).

    Per Flight DD §8 ("accept-and-document"), a per-agent True with an
    account-level False is structurally inert — the account check at
    step 4 short-circuits before the agent toggle is consulted.

    Per Flight DD §9 safe-default discipline, every exceptional outcome
    inside :func:`run_engagement_inference` collapses to False (silent).
    The gate does not need additional exception handling.
    """
    # 1. DM
    if envelope.raw.get("is_dm") is True:
        return True, {"outcome": "dm"}
    # 2. Override
    if decision.scope == "override":
        return True, {"outcome": "override"}
    # 3. Mention — getattr-sentinel consult (mirrors the F8 L6 ``is_dm``
    # consult pattern at ``_routing.py:168-171``).
    is_mention_fn = getattr(plugin, "is_mention", _default_no_mention)
    if is_mention_fn(envelope):
        return True, {"outcome": "mention"}
    # 4. Always-listen composition.
    account_listen = bool(account.config.get("always_listen", False))
    agent_listen_dict = agent_config.connector_always_listen
    agent_listen = (
        agent_listen_dict.get(account.id, False)
        if agent_listen_dict is not None
        else False
    )
    if not account_listen:
        return False, {
            "outcome": "always-listen-off",
            "account_always_listen": False,
            "agent_always_listen": agent_listen,
        }
    if not agent_listen:
        return False, {
            "outcome": "always-listen-off",
            "account_always_listen": True,
            "agent_always_listen": False,
        }
    # Both toggles True → run inference. Construct the provider repo
    # inline; the dispatcher's ``conn`` + ``encryptor`` are in scope from
    # step 1's ``get_connection()`` + ``get_encryptor()`` calls.
    from the_one.db.repositories import LLMProviderRepository

    provider_repo = LLMProviderRepository(conn, encryptor)
    engaged = await run_engagement_inference(
        account=account,
        envelope=envelope,
        session_messages=session_messages,
        settings=settings,
        provider_repo=provider_repo,
        fallback_provider_config_id=agent_config.provider_config_id,
        fallback_llm_model=agent_config.llm_model,
    )
    outcome = "inference-yes" if engaged else "inference-no"
    return engaged, {
        "outcome": outcome,
        "account_always_listen": True,
        "agent_always_listen": True,
        "inference_provider_id": (
            settings.inference_provider_config_id
            or agent_config.provider_config_id
        ),
        "inference_model": (
            settings.inference_model
            or agent_config.llm_model
        ),
    }


async def dispatch_inbound(
    account_id: str,
    envelope: InboundEnvelope,
    *,
    factory: AgentFactory,
) -> None:
    """Dispatch a single inbound envelope through the full F7 pipeline.

    See module docstring for the canonical 12-step composition order
    introduced by M10 F7 L5. The dispatcher's contract is "given an
    ``account_id`` and an ``envelope``, dispatch correctly." The caller
    (the plugin's inbound adapter; today only tests) does not need to
    know agent topology — the dispatcher enumerates eligible attached
    agents via :meth:`SQLiteAgentStore.list_by_connector_account` and
    picks the routed agent via :func:`resolve_routing`'s 5-step engine.

    Errors at the account-load / plugin-resolve / pool-acquire stages
    are logged and the function returns — a connector-layer failure
    DOES NOT take the agent runtime down. The no-attached-agents
    branch (step 4 returns an empty list) and the no-eligible branch
    (step 9, ``decision.agent is None``) share the silent / log-and-
    return shape; the difference is the no-eligible branch ALSO emits
    a peer-facing "No agents available for this conversation." via
    the system-outbound path. Errors raised inside the agent build
    (``factory.create``) or inside ``agent.step`` propagate up after
    the ContextVar is reset; F8's gateway-listener is responsible for
    catching them and surfacing a degraded state.
    """
    # 1. Function-local imports per the load-cycle convention. Mirrors
    # ``connectors/_pool._load_account``: ``db.connection`` /
    # ``db.repositories`` / ``encryption`` / ``config`` are imported at
    # call time so this module stays resilient regardless of import
    # order. The connectors→db layer boundary carries the same
    # circular-import risk that ``_pool.py`` and ``_session.py`` already
    # pay for.
    from the_one.config import settings
    from the_one.connectors._commands import (
        _dispatch_builtin_command,
        _parse_command,
    )
    from the_one.db.connection import get_connection
    from the_one.db.repositories import (
        ChatSessionRepository,
        ConnectorRepository,
        PendingApprovalRepository,
        SQLiteAgentStore,
    )
    from the_one.encryption import get_encryptor

    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    acc_repo = ConnectorRepository(conn, encryptor)
    chat_repo = ChatSessionRepository(conn)
    approval_repo = PendingApprovalRepository(conn)
    agent_store = SQLiteAgentStore(conn)

    # 2. Account load.
    try:
        account = await acc_repo.get(account_id)
    except KeyError:
        logger.warning(
            "dispatch_inbound: account %s not found (deleted mid-flight?)",
            account_id,
        )
        return

    # 3. Plugin resolve.
    try:
        plugin = registry.resolve(account.type)
    except ConnectorRegistrationError as exc:
        logger.error(
            "dispatch_inbound: unknown connector type %r for account %s: %s",
            account.type,
            account_id,
            exc,
        )
        return

    # 4. Enumerate eligible attached agents (alphabetically ordered by
    # ``AgentConfig.name`` per the ``ORDER BY`` in
    # :meth:`SQLiteAgentStore.list_by_connector_account`). Empty list ⇒
    # silent return (preserves the L3 no-attached-agents semantic). The
    # routing engine's first-eligible-alphabetical step depends on this
    # ordering; do NOT sort here or pass a reordered list to
    # :func:`resolve_routing`.
    eligible_attached_agents = await agent_store.list_by_connector_account(account_id)
    if not eligible_attached_agents:
        logger.info(
            "dispatch_inbound: no agents attached to account_id=%s; "
            "ignoring inbound",
            account_id,
        )
        return
    first_eligible_name = eligible_attached_agents[0].name

    # 5. Resolve session via the leg-3 resolver. ``agent_name`` is the
    # creation-time anchor for NEW rows (alphabetically-first attached
    # agent); the reuse path ignores ``agent_name`` and returns the
    # most-recent matching row's existing ``agent_name`` verbatim. Per-
    # session row identity is preserved across routing decisions.
    session_row = await resolve_session(
        envelope,
        account,
        chat_repo,
        agent_name=first_eligible_name,
        plugin=plugin,
    )

    # 6. F6 resolver consult + three-arm branch + audit write.
    # The resolver is consulted AFTER ``resolve_session`` so the audit
    # entries have a target row, and BEFORE routing / per-session lock
    # so Deny / NeedsPairing-failure return WITHOUT bumping
    # ``last_inbound_at``. ``getattr`` discovery + ``_default_permit``
    # fallback means a plugin without ``resolve`` (e.g. F1's
    # ``StubPlugin``) behaves byte-identically to pre-F6.
    resolver = getattr(plugin, "resolve", _default_permit)
    outcome = resolver(account, envelope)
    ts = now_iso()

    if isinstance(outcome, Deny):
        await chat_repo.append_to_session_metadata(
            session_row.id,
            "audit",
            {
                "outcome": "deny",
                "peer_id": envelope.peer_id,
                "ts": ts,
                "reason": outcome.reason,
            },
        )
        return

    working_envelope = envelope
    if isinstance(outcome, NeedsPairing):
        pairing = (account.config.get("pairing") or {}).get("code")
        success, cleaned = _validate_pairing_prefix(
            envelope.text, pairing or ""
        )
        if not success:
            if envelope.text.startswith(_PAIR_PREFIX):
                # Failed PAIR attempt (wrong code, malformed prefix, or
                # account-has-no-code). Existing audit-deny path.
                await chat_repo.append_to_session_metadata(
                    session_row.id,
                    "audit",
                    {
                        "outcome": "deny",
                        "peer_id": envelope.peer_id,
                        "ts": ts,
                        "reason": outcome.reason or "invalid_pairing",
                    },
                )
                return
            # No PAIR prefix — Discord-native approval candidate (F9 L2).
            # Order: upsert FIRST (storage must succeed; raises if broken);
            # broadcast SECOND (in-process, programmer-error-if-raises);
            # audit-log THIRD.
            approval = await approval_repo.upsert_pending(
                connector_id=account.id,
                peer_id=envelope.peer_id,
                peer_name=envelope.peer_name,
                preview=envelope.text[:200],
            )
            await broadcast_to_session(
                session_row.id,
                {
                    "type": "pending-approval",
                    "approval_id": approval.id,
                    "peer_name": approval.peer_name,
                    "peer_id": approval.peer_id,
                    "preview": approval.preview,
                    "received_at": approval.received_at,
                    "connector_id": approval.connector_id,
                    "status": approval.status,
                },
            )
            await chat_repo.append_to_session_metadata(
                session_row.id,
                "audit",
                {
                    "outcome": "deny",
                    "peer_id": envelope.peer_id,
                    "ts": ts,
                    "reason": "pending_approval",
                },
            )
            return
        # Success: persist the paired peer + clean the envelope.
        allowlist = account.config.get("allowlist") or {
            "peers": [],
            "channels": [],
        }
        peers = list(allowlist.get("peers", []))
        if envelope.peer_id not in peers:
            peers.append(envelope.peer_id)
        allowlist["peers"] = peers
        allowlist.setdefault("channels", [])
        account.config["allowlist"] = allowlist
        await acc_repo.update(account)
        working_envelope = replace(envelope, text=cleaned)
        await chat_repo.append_to_session_metadata(
            session_row.id,
            "audit",
            {
                "outcome": "permit",
                "peer_id": envelope.peer_id,
                "ts": ts,
                "reason": "paired",
            },
        )
    else:
        # Permit outcome. ``reason: None`` for shape uniformity (the
        # leg-4 Studio renderer reads all four keys without per-entry
        # shape checks).
        await chat_repo.append_to_session_metadata(
            session_row.id,
            "audit",
            {
                "outcome": "permit",
                "peer_id": envelope.peer_id,
                "ts": ts,
                "reason": None,
            },
        )

    # 7. F7 routing engine consult. Read ``session_metadata`` off the
    # row (decoded dict; ``None`` collapses to ``{}``). The engine
    # consults ``session_metadata["routing_override"]`` in step 1 of
    # its 5-step algorithm; the read side is wired here so L6's
    # ``/talk-to`` handler's ``set_session_metadata_key`` write is
    # observed on the NEXT inbound (within-session sequencing).
    db_session_for_routing = await chat_repo.get(session_row.id)
    if db_session_for_routing.session_metadata is None:
        session_metadata: dict[str, Any] = {}
    else:
        session_metadata = db_session_for_routing.session_metadata
    decision = resolve_routing(
        account,
        working_envelope,
        eligible_attached_agents,
        session_metadata,
        plugin=plugin,
    )

    # 8. Build the routing audit entry. ``disposition`` is filled per
    # branch (no-eligible / pool-failure-overload / command-intercepted
    # / stepped) before the entry is appended.
    audit_entry: dict[str, Any] = {
        "ts": now_iso(),
        "agent": decision.agent,
        "rule_index": decision.rule_index,
        "scope": decision.scope,
        "match": decision.match,
        "reason": decision.reason,
        # "disposition" set below per branch.
    }

    # 9. No-eligible branch — ``decision.agent is None``: append audit
    # entry, emit the peer-facing error via system-outbound using the
    # alphabetically-first attached agent's pool entry (the bot identity
    # reflects the eligible-list's first member, which IS valid for
    # outbound emission regardless of inbound-ACL state — outbound ACL
    # is a separate per-axis check the system-outbound path elides for
    # the platform-error message).
    if decision.agent is None:
        audit_entry["disposition"] = "no-eligible"
        await chat_repo.append_to_session_metadata(
            session_row.id,
            "routing",
            audit_entry,
        )
        try:
            # M10 F8 L11 HAT Fix #6: account-shared pool entry — one
            # gateway connection per account regardless of which
            # agent's identity surfaced in the no-eligible audit.
            client = await account_acquire(account_id)
            await client.send(
                OutboundTarget(
                    channel_id=working_envelope.channel_id,
                    thread_id=working_envelope.thread_id,
                ),
                "No agents available for this conversation.",
            )
        except Exception:
            # Emit failure → log + swallow. The peer's message goes
            # unanswered; the audit log preserves the "no-eligible"
            # disposition for the operator to debug.
            logger.exception(
                "dispatch_inbound: no-eligible peer-error emit failed "
                "for (agent=%s, account=%s)",
                first_eligible_name,
                account_id,
            )
        return

    # 10. Pool acquire for the routed agent. ``last_activity`` is
    # touched here (F1 ratification anchor — the L3 dispatcher had this
    # call BEFORE the agent enumeration; L5 moves it AFTER routing so
    # the touch is bound to the agent that actually handles the inbound).
    # Pool failure ⇒ ``disposition = "no-eligible"`` (overload — the
    # inbound is unanswerable; observable shape collapses onto
    # no-eligible). Alternative: a new ``"pool-failure"`` disposition;
    # L5 keeps the disposition vocabulary minimal — F10 hardening can
    # refine.
    try:
        # M10 F8 L11 HAT Fix #6: account-shared pool entry — all
        # agents attached to one connector account share a single
        # gateway WebSocket. Per-agent credentials are out of scope
        # for connectors (gateway protocols are physically one-token-
        # one-connection); the routed agent's identity continues to
        # flow through ``decision.agent`` for routing audit purposes,
        # not through the pool key.
        client = await account_acquire(account_id)
    except (KeyError, ConnectorRegistrationError) as exc:
        logger.warning(
            "dispatch_inbound: pool acquire failed for "
            "(agent=%s, account=%s): %s",
            decision.agent,
            account_id,
            exc,
        )
        audit_entry["disposition"] = "no-eligible"
        await chat_repo.append_to_session_metadata(
            session_row.id,
            "routing",
            audit_entry,
        )
        return
    except Exception:
        # Any other pool failure (connect raise, plugin connect timeout, etc.)
        logger.exception(
            "dispatch_inbound: unexpected pool acquire failure for "
            "(agent=%s, account=%s)",
            decision.agent,
            account_id,
        )
        audit_entry["disposition"] = "no-eligible"
        await chat_repo.append_to_session_metadata(
            session_row.id,
            "routing",
            audit_entry,
        )
        return

    # 11. Command parse + intercept (M10 F8 L1 — consult-then-fallthrough).
    # (i) Parse via :func:`_parse_command`; if the envelope text is not
    # a command, fall through to step 12 (``agent.step``). (ii) If a
    # command parses, consult an optional plugin handler via
    # ``getattr(plugin, "handle_command", None)`` per the
    # ``optional-plugin-hook-via-getattr-sentinel`` convention — a
    # plugin returning a non-None :class:`CommandResponse` short-
    # circuits the dispatcher with the same outbound + audit-log
    # treatment the built-in path uses (``disposition="command-
    # intercepted"``; ``intercept_source="plugin"`` for the
    # discriminator). Plugin exceptions are logged and treated as
    # ``None``. (iii) If the plugin returns ``None`` (or no plugin
    # consult was wired), dispatch to :func:`_dispatch_builtin_command`
    # — the six v1 handlers (``/agents``, ``/talk-to``, ``/whoami``,
    # ``/new``, ``/reset``, ``/help``); a non-None return emits with
    # ``intercept_source="builtin"``. (iv) If neither the plugin nor
    # the built-in handler produced a response (built-in returned
    # ``None`` for an unknown command name like ``/foo``), fall through
    # to step 12 (``agent.step``) — the agent sees the command text as
    # a regular user message.
    parsed = _parse_command(working_envelope.text)
    if parsed is not None:
        command_name, args = parsed
        context: dict[str, Any] = {
            "account": account,
            "envelope": working_envelope,
            "eligible_attached_agents": eligible_attached_agents,
            "routed_agent_name": decision.agent,
            "session_id": session_row.id,
            "chat_repo": chat_repo,
        }
        # F8 L1: optional plugin command-handler consult via the
        # ``optional-plugin-hook-via-getattr-sentinel`` convention. A
        # plugin opting into platform-native command handling
        # implements ``handle_command`` (per the ``CommandHandler``
        # Protocol in ``connectors/base.py``); the dispatcher consults
        # it BEFORE the built-in handler so a plugin response can
        # override the v1 built-in vocabulary. A plugin without
        # ``handle_command`` (the stub; pre-F8 plugins) short-circuits
        # past the consult via the ``getattr`` sentinel. Plugin-raised
        # exceptions are logged + swallowed (defensive fallback per the
        # F6 ``_acl`` precedent); we fall through to the built-in
        # handler on either ``None`` or exception.
        plugin_handle = getattr(plugin, "handle_command", None)
        if plugin_handle is not None:
            try:
                response = await plugin_handle(
                    working_envelope, command_name, args
                )
            except Exception:
                logger.exception(
                    "dispatch_inbound: plugin handle_command raised "
                    "for (command=%s, agent=%s, account=%s); "
                    "falling back to built-in handler",
                    command_name,
                    decision.agent,
                    account_id,
                )
                response = None
            if response is not None:
                audit_entry["disposition"] = "command-intercepted"
                audit_entry["intercept_source"] = "plugin"
                await chat_repo.append_to_session_metadata(
                    session_row.id,
                    "routing",
                    audit_entry,
                )
                try:
                    await client.send(
                        OutboundTarget(
                            channel_id=working_envelope.channel_id,
                            thread_id=working_envelope.thread_id,
                        ),
                        response.text,
                    )
                except Exception:
                    logger.exception(
                        "dispatch_inbound: plugin command-response emit failed "
                        "for (command=%s, agent=%s, account=%s)",
                        command_name,
                        decision.agent,
                        account_id,
                    )
                return
        # No plugin consult OR plugin returned None → fall through to
        # the built-in handler below.
        response = await _dispatch_builtin_command(command_name, args, context)
        if response is not None:
            audit_entry["disposition"] = "command-intercepted"
            audit_entry["intercept_source"] = "builtin"
            await chat_repo.append_to_session_metadata(
                session_row.id,
                "routing",
                audit_entry,
            )
            try:
                await client.send(
                    OutboundTarget(
                        channel_id=working_envelope.channel_id,
                        thread_id=working_envelope.thread_id,
                    ),
                    response.text,
                )
            except Exception:
                logger.exception(
                    "dispatch_inbound: command-response emit failed "
                    "for (command=%s, agent=%s, account=%s)",
                    command_name,
                    decision.agent,
                    account_id,
                )
            return
        # Built-in returned None (unknown command name) → fall through
        # to agent.step.

    # NOTE: step-10 and step-12 are independent pool acquisitions and do NOT share state — step-10 holds the dispatcher's outbound ``client`` for command/error emit; step-12's ``agent.step`` may acquire its own ``ConnectorClient`` references via the platform-send tool independently.

    # 11.5 (M11 F7 L8). Policy gate — decides engaged-vs-silent per Flight
    # DD §1 five-path decision tree before the per-session lock acquires.
    # Silent branches terminal-return with an audit-only side effect: no
    # lock, no ``update_last_inbound``, no agent build, no ``agent.step``,
    # no auto-relay, no WS broadcast — mirrors the F6 Deny /
    # NeedsPairing-failure precedent at step 6.
    #
    # The engaged branch flows through to step 12 unchanged; the policy
    # sub-block is NOT embedded in the engaged-path audit entry (F9's
    # audit-log inspector reads engaged entries' implicit non-silent
    # disposition).
    #
    # ``agent_config`` resolution: pick the routed agent's config from
    # the already-loaded ``eligible_attached_agents`` list (no extra DB
    # round-trip). The ``next(...)`` is guaranteed to succeed because
    # ``decision.agent`` was selected from this same list by
    # :func:`resolve_routing` at step 7.
    agent_config = next(
        a for a in eligible_attached_agents if a.name == decision.agent
    )
    session_messages = decode_messages(db_session_for_routing.messages)
    should_engage, policy_audit = await _policy_gate_decision(
        envelope=working_envelope,
        account=account,
        agent_config=agent_config,
        plugin=plugin,
        decision=decision,
        session_messages=session_messages,
        conn=conn,
        encryptor=encryptor,
        settings=settings,
    )
    if not should_engage:
        # Silent terminal-return per DD §13.
        audit_entry["disposition"] = "policy-silent"
        audit_entry["policy"] = policy_audit
        await chat_repo.append_to_session_metadata(
            session_row.id,
            "routing",
            audit_entry,
        )
        logger.info(
            "dispatch_inbound: policy gate silent on envelope "
            "(account=%s, channel=%s, peer=%s, outcome=%s); "
            "no engagement without mention/override/inference consent",
            account_id,
            working_envelope.channel_id,
            working_envelope.peer_id,
            policy_audit.get("outcome"),
        )
        return
    # Engaged → flow through to step 12 (lock + agent.step). ``audit_entry``
    # is NOT appended here; step 12 sets disposition="stepped" and appends.
    # The silent path above is the only L8 append site.

    # 12. Per-session lock + persist + agent.step + persist (existing
    # F3+F4 logic with ``agent_name = decision.agent``).
    audit_entry["disposition"] = "stepped"
    await chat_repo.append_to_session_metadata(
        session_row.id,
        "routing",
        audit_entry,
    )
    async with session_locks[session_row.id]:
        # Update last_inbound_at (and updated_at — the resolver's
        # most-recent-by-updated_at ordering consumes this).
        await chat_repo.update_last_inbound(session_row.id, now_iso())

        # Build a fresh agent for this turn. Errors here
        # (ProviderNotConfiguredError, ProviderNotFoundError) propagate
        # — F8's caller catches them and surfaces a degraded state.
        agent = await factory.create(decision.agent)

        # Re-fetch the session row inside the lock — history may have
        # been mutated by a previously serialized inbound. Decode the
        # stored messages; mirror the ``_restore_session`` shape: keep
        # the freshly-built agent's system message, append the
        # non-system stored messages.
        db_session = await chat_repo.get(session_row.id)
        stored = decode_messages(db_session.messages)
        if stored:
            non_system = [m for m in stored if m.role != Role.SYSTEM]
            agent.messages = agent.messages[:1] + non_system

        # Bind the ContextVar so any pool-spawned MCP OAuth provider
        # construction during agent.step routes ``auth_required``
        # broadcasts to the right session id (mirror of the WS handler
        # at ``interfaces/web/app.py:257``).
        # Snapshot ``pre_step_len`` BEFORE entering the try — pure read,
        # no exception risk; consumed by F4 L4's post-step visibility
        # tagging pass below.
        pre_step_len = len(agent.messages)
        token = current_chat_session_id.set(session_row.id)
        try:
            # Drive agent.step. The agent's core appends
            # ``Message.user(envelope.text)`` internally
            # (``agent/core.py:138``); iterates LLM round-trips;
            # appends assistant + tool messages. After completion,
            # ``agent.messages`` holds the full updated history.
            # No on_chunk / on_usage callbacks — F3 has no UI
            # subscribers (F5 owns broadcast).
            async for _ in agent.step(working_envelope.text):
                pass

            # F4 (M10) L4: post-step visibility tagging.
            # The dispatcher fires only for connector-attached inbound; every
            # new message in the turn is tagged either platform-visible (None)
            # or operator-only ("operator") for the F5 Chat UI's two-layer
            # rendering. The mission's enforcement-by-construction stance
            # (platform-send tool is the ONLY agent→platform path) makes
            # leakage impossible regardless of tagging; visibility is a
            # presentation metadata layer, not a security gate.
            #
            # F5 L3: the tagging rules live in ``connectors.visibility`` so
            # the F5 L4 WS-storage-edge shim can apply the SAME rules from
            # the operator-typed entry path. See ``visibility.py`` for the
            # full rule enumeration.
            tag_post_step_visibility(agent.messages, pre_step_len)

            # M11 F06 L03: post-step peer_name binding.
            # The Discord plugin's gateway translator populates
            # ``InboundEnvelope.peer_name`` (the_one/connectors/_discord_translate.py:125)
            # but ``Agent.step`` constructs ``Message.user(working_envelope.text)``
            # at agent/core.py:144 with no peer_name. The M11 mission constraint
            # forbids modifying ``agent/core.py`` and ``agent/factory.py``, so the
            # dispatcher binds peer_name here POST-step on the appended user
            # message, mirroring the ``tag_post_step_visibility`` pattern just
            # above (same idiom: fill in the metadata the agent loop doesn't
            # know about). The mutation is inside the per-session lock
            # (session_locks[session_row.id]) and inside the try block, so it
            # composes correctly with concurrent operator-typed turns and is
            # skipped on agent.step exceptions. Closes M10 debrief Bug C
            # (peer_name data-model gap, 6 surfaces) / M11 criterion #13.
            # M11 F7 L1: the inline mutation moved to
            # :func:`the_one.connectors.post_step_metadata.bind_peer_name`
            # alongside ``tag_post_step_visibility`` (n=3 lift trigger).
            # The WHY remains documented here at the call site; the WHAT
            # lives in the function's docstring.
            bind_peer_name(
                agent.messages, pre_step_len, working_envelope.peer_name
            )

            # M11 F07 L03: post-step channel-context binding.
            # The envelope always carries ``channel_id`` (every connector
            # plugin's translator sets it — see Discord's
            # ``_discord_translate.py:122``); ``channel_name`` is resolved
            # from the F3 L4 discoverable-entities cache (label lookup
            # matching ``envelope.channel_id`` against
            # ``cache.channels[i].id``). Cold pool / non-Discord plugin /
            # stale cache → ``channel_name`` stays ``None``; the L4 provider
            # projection handles partial-absence gracefully. The cache read
            # is awaited inside the per-session lock: the pool lock is
            # independent of ``session_locks[session_row.id]`` and the
            # snapshot capture holds no callable that could in turn
            # acquire any session lock, so no ordering violation is
            # possible. Composition: this is the third mutator in the
            # ``post_step_metadata`` set (visibility, peer_name,
            # channel_context — n=3 per agents.md
            # § post-step-dispatcher-message-metadata-binding).
            _channel_cache_snapshot = await _get_account_cache_snapshot(
                working_envelope.account_id
            )
            _resolved_channel_name = resolve_channel_name(
                _channel_cache_snapshot.cache
                if _channel_cache_snapshot is not None
                else None,
                working_envelope.channel_id,
            )
            bind_channel_context(
                agent.messages,
                pre_step_len,
                working_envelope.channel_id,
                _resolved_channel_name,
            )

            # Persist updated history. Mirror of ``_save_session_to_db``
            # at ``interfaces/web/app.py:469-487``. The leg-1 docstring
            # contract on ``ChatSessionRepository.update`` guarantees
            # the seven connector-identity columns are preserved across
            # this call — the SQL only writes ``title``, ``messages``,
            # ``updated_at``.
            encoded = encode_messages(agent.messages)
            updated = db_session.model_copy(
                update={
                    "title": session_row.title,
                    "messages": encoded,
                }
            )
            await chat_repo.update(updated)

            # F5 L6: per-message broadcast to live WS observers. Zero
            # subscribers is a clean no-op. The codec emits visibility
            # on each event from Message.visibility (already tagged by
            # tag_post_step_visibility above), so live observers see
            # operator-only markers correctly. The broadcast loop is
            # intentionally inside the per-session lock — operator-typed
            # turns on the same session_id queue behind the broadcast
            # rather than interleaving (Edge Cases documents the
            # serialization trade-off). index_offset=pre_step_len keeps
            # parent_message_ids unique across consecutive inbound turns
            # on the same session (regression coverage in
            # test_dispatch_inbound_multi_turn_parent_message_ids_do_not_collide).
            # No exclude — the inbound came from the connector gateway,
            # not from any WS subscriber.
            new_msgs = agent.messages[pre_step_len:]
            if new_msgs:
                events = messages_to_ui_events(
                    new_msgs, index_offset=pre_step_len
                )
                for event in events:
                    await broadcast_to_session(session_row.id, event)

            # M11 F7 L5 — auto-relay platform replies (invariant on
            # engaged turns).
            # ===================================================
            # Auto-relay is the invariant outbound path on engaged
            # turns: when the dispatcher reaches this block, the agent
            # has produced a plaintext reply and that reply MUST go to
            # the platform. The engagement decision is now the policy
            # gate's responsibility (L8), so by the time we get here
            # the contract is "this reply belongs to peers."
            #
            # F4 invariant is preserved: outbound STILL goes through
            # ``client.send`` (the pool-mediated platform conduit). The
            # dispatcher is just an additional caller of ``client.send``;
            # the send_to_platform_channel tool remains the
            # agent-deliberate path, this branch is the system-default
            # path.
            #
            # Skip conditions (any one ⇒ skip):
            #   * Agent already called ``send_to_platform_channel``
            #     during this step (avoid double-send).
            #   * Agent produced no plaintext (e.g. only tool calls).
            #
            # Failure of ``client.send`` is logged + swallowed — the
            # inbound is considered handled; the auto-relay failure is
            # non-fatal (mirrors the F7 L5 no-eligible peer-error and
            # plugin/builtin command-response emit-swallow precedents).
            # Detect agent-deliberate platform-send during this step
            # — if the agent already called the tool, the auto-relay
            # path must NOT fire (avoid double-send to peers).
            already_sent_via_tool = False
            for msg in new_msgs:
                if msg.role == Role.ASSISTANT:
                    for tc in msg.tool_calls:
                        if tc.name == "send_to_platform_channel":
                            already_sent_via_tool = True
                            break
                if already_sent_via_tool:
                    break

            # Find the LAST plaintext assistant reply produced this
            # step. The agent.step loop emits one or more assistant
            # messages; the final one (with no tool_calls and
            # non-empty content) is the user-facing reply.
            reply_text: str | None = None
            for msg in reversed(new_msgs):
                if (
                    msg.role == Role.ASSISTANT
                    and not msg.tool_calls
                    and msg.content
                ):
                    reply_text = msg.content
                    break

            if (
                not already_sent_via_tool
                and reply_text is not None
            ):
                try:
                    # M10 F8 L11 HAT Fix #6: account-shared pool —
                    # auto-relay uses the same gateway connection
                    # the dispatcher already warmed at step 10.
                    relay_client = await account_acquire(account_id)
                    send_result = await relay_client.send(
                        OutboundTarget(
                            channel_id=working_envelope.channel_id,
                            thread_id=working_envelope.thread_id,
                        ),
                        reply_text,
                    )
                    # Flip the agent's plaintext assistant reply
                    # from OPERATOR_VISIBILITY (tagged by
                    # ``tag_post_step_visibility`` above) to
                    # platform-visible (``visibility=None``) — the
                    # message DID make it to peers via this relay.
                    # The Chat UI then renders it correctly as a
                    # platform-bound reply rather than an
                    # operator-only deliberation.
                    for msg in reversed(new_msgs):
                        if (
                            msg.role == Role.ASSISTANT
                            and not msg.tool_calls
                            and msg.content == reply_text
                        ):
                            msg.visibility = None
                            break
                    # Re-persist to capture the visibility flip on
                    # the assistant message.
                    encoded = encode_messages(agent.messages)
                    db_session_after_relay = await chat_repo.get(
                        session_row.id
                    )
                    await chat_repo.update(
                        db_session_after_relay.model_copy(
                            update={"messages": encoded}
                        )
                    )
                    logger.info(
                        "Auto-relayed agent %s reply to platform "
                        "via account %s channel %s (message_id=%s)",
                        decision.agent,
                        account_id,
                        working_envelope.channel_id,
                        send_result.platform_message_id,
                    )
                except Exception:
                    # Log + swallow. The agent already produced the
                    # reply; the operator-console view still shows
                    # it (visibility stays OPERATOR_VISIBILITY since
                    # the flip block above did not run). The
                    # operator can manually invoke
                    # ``send_to_platform_channel`` or retry.
                    logger.exception(
                        "dispatch_inbound: auto-relay client.send "
                        "failed for (agent=%s, account=%s, channel=%s); "
                        "agent reply preserved as operator-only",
                        decision.agent,
                        account_id,
                        working_envelope.channel_id,
                    )
        finally:
            # Always reset the ContextVar — even if agent.step raises
            # mid-stream.
            current_chat_session_id.reset(token)


async def _clear_for_test() -> None:
    """Test seam: clear the shared per-session lock registry.

    Delegates to ``the_one.sessions.clear_locks_for_test``.
    Kept ``async def`` for back-compat with autouse fixtures that
    ``await`` this symbol.
    """
    from the_one.sessions import clear_locks_for_test
    clear_locks_for_test()
