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
platform-send tool's ``pool_acquire → client.send`` shape but is
invoked dispatcher-internally (NOT through the tool registry).

The per-(agent, account) pool's :func:`acquire` is called per inbound
here — that is the **last_activity ratification** of the F1 Known
Issue (see ``the_one/agents.md``'s Connector subsystem section). The
dispatcher does NOT cache the :class:`ConnectorClient` reference
outside the pool; every inbound goes through ``acquire``.

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
10. Pool acquire for the routed agent — ``pool_acquire(decision.agent,
    account_id)``. Failure ⇒ ``disposition = "no-eligible"`` (overload
    — the inbound is unanswerable so observable shape collapses onto
    no-eligible); append audit entry; return.
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

System-outbound path: ``pool_acquire(agent_name, account_id) →
client.send(OutboundTarget(...), text)`` — invoked dispatcher-internally
with function-local imports for cycle-break. Mirrors
``the_one/tools/connector_send.py:SendToPlatformChannelTool.execute``
lines 183-200 in shape; NOT routed through the platform-send tool
registry. Commands work even when the tool is operator-disabled.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from the_one.agent._context import current_chat_session_id
from the_one.agent.factory import AgentFactory
from the_one.connectors import registry
from the_one.connectors._pairing import _validate_pairing_prefix
from the_one.connectors._pool import acquire as pool_acquire
from the_one.connectors._routing import resolve_routing
from the_one.connectors._session import resolve_session
from the_one.connectors.base import (
    Deny,
    InboundEnvelope,
    NeedsPairing,
    OutboundTarget,
    _default_permit,
)
from the_one.connectors.errors import ConnectorRegistrationError
from the_one.connectors.visibility import tag_post_step_visibility
from the_one.db.codec import decode_messages, encode_messages, messages_to_ui_events
from the_one.db.models import now_iso
from the_one.llm.base import Role
from the_one.sessions import broadcast_to_session, session_locks

logger = logging.getLogger(__name__)


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
        ConnectorAccountRepository,
        SQLiteAgentStore,
    )
    from the_one.encryption import get_encryptor

    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    acc_repo = ConnectorAccountRepository(conn, encryptor)
    chat_repo = ChatSessionRepository(conn)
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
            client = await pool_acquire(first_eligible_name, account_id)
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
        client = await pool_acquire(decision.agent, account_id)
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
