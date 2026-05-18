"""Inbound dispatcher — composes pool + session resolver + per-session lock
+ agent.step into the end-to-end ingestion path for a connector-driven
message.

M10 F03 L04. This is the contract F8 (Discord) and F9 (the second
connector) will satisfy when they replace the F1-stub-driven inbound
with a real gateway-driven inbound. F3's stub-based tests prove the
contract holds against a synthetic envelope; F8 wires the real Discord
gateway to call this same ``dispatch_inbound``.

F4 (platform-send tool) owns outbound. This module is INBOUND ONLY.

The per-(agent, account) pool's :func:`acquire` is called per inbound
here — that is the **last_activity ratification** of the F1 Known
Issue (see ``the_one/agents.md``'s Connector subsystem section). The
dispatcher does NOT cache the :class:`ConnectorClient` reference
outside the pool; every inbound goes through ``acquire``.

Per-session serialization shares the SAME asyncio.Lock with
the WS handler. The lock registry lives at
``the_one.sessions.session_locks``; see F5 L2 for the
unification that closed the M10 mission Known Issue.
"""

from __future__ import annotations

import logging

from the_one.agent._context import current_chat_session_id
from the_one.agent.factory import AgentFactory
from the_one.connectors import registry
from the_one.connectors._pool import acquire as pool_acquire
from the_one.connectors._session import resolve_session
from the_one.connectors.base import InboundEnvelope
from the_one.connectors.errors import ConnectorRegistrationError
from the_one.connectors.visibility import tag_post_step_visibility
from the_one.db.codec import decode_messages, encode_messages, messages_to_ui_events
from the_one.db.models import now_iso
from the_one.llm.base import Role
from the_one.sessions import broadcast_to_session, session_locks

logger = logging.getLogger(__name__)


async def dispatch_inbound(
    agent_name: str,
    account_id: str,
    envelope: InboundEnvelope,
    *,
    factory: AgentFactory,
) -> None:
    """Dispatch a single inbound envelope through the full pipeline.

    Pool-acquires for the (agent, account) pair (touches
    ``last_activity``; this is the F1 ratification anchor). Loads the
    account, resolves the plugin, resolves the chat_sessions row via
    :func:`the_one.connectors._session.resolve_session`, acquires the
    per-session lock, updates ``last_inbound_at``, builds a fresh
    :class:`Agent` via the injected ``factory``, loads the session's
    message history into the agent, drives :meth:`Agent.step`, and
    persists the updated history back to the row.

    The agent loop is unchanged — this dispatcher drives ``agent.step``
    the same way the WS handler does; the only difference is the
    trigger source (an :class:`InboundEnvelope` vs. a WS message).

    Errors at the pool-acquire / account-load / plugin-resolve stages
    are logged and the function returns — a connector-layer failure
    DOES NOT take the agent runtime down. Errors raised inside the
    agent build (``factory.create``) or inside ``agent.step`` propagate
    up after the ContextVar is reset; F8's gateway-listener is
    responsible for catching them and surfacing a degraded state.
    """
    # 1. Pool acquire — touches last_activity (F1 ratification).
    # The returned client is NOT consumed here (F4 owns outbound); the
    # call is for the touch side effect AND to surface pool failures
    # (account not found, plugin not registered, connect failed) BEFORE
    # the dispatcher does any DB work.
    try:
        await pool_acquire(agent_name, account_id)
    except (KeyError, ConnectorRegistrationError) as exc:
        logger.warning(
            "dispatch_inbound: pool acquire failed for (agent=%s, account=%s): %s",
            agent_name,
            account_id,
            exc,
        )
        return
    except Exception:
        # Any other pool failure (connect raise, plugin connect timeout, etc.)
        logger.exception(
            "dispatch_inbound: unexpected pool acquire failure for (agent=%s, account=%s)",
            agent_name,
            account_id,
        )
        return

    # 2. Function-local imports per the load-cycle convention. Mirrors
    # ``connectors/_pool._load_account``: ``db.connection`` /
    # ``db.repositories`` / ``encryption`` / ``config`` are imported at
    # call time so this module stays resilient regardless of import
    # order. The connectors→db layer boundary carries the same circular-
    # import risk that ``_pool.py`` and ``_session.py`` already pay for.
    from the_one.config import settings
    from the_one.db.connection import get_connection
    from the_one.db.repositories import (
        ChatSessionRepository,
        ConnectorAccountRepository,
    )
    from the_one.encryption import get_encryptor

    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    acc_repo = ConnectorAccountRepository(conn, encryptor)
    chat_repo = ChatSessionRepository(conn)

    try:
        account = await acc_repo.get(account_id)
    except KeyError:
        logger.warning(
            "dispatch_inbound: account %s not found (deleted mid-flight?)",
            account_id,
        )
        return

    # 3. Resolve plugin. Deliberately redundant with the pool-acquire's
    # internal plugin resolution (``_pool._resolve_plugin`` at
    # ``_pool.py:440`` already raises ``ConnectorRegistrationError``
    # for unknown types) — pool acquire would have already raised on
    # this path. The second catch is dead in the happy path; kept as
    # defensive coding so a future reader who refactors the pool's
    # error surface doesn't strand the dispatcher with an unhandled
    # unknown-type path. Do NOT "simplify" by removing.
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

    # 4. Resolve session via the leg-3 resolver.
    session_row = await resolve_session(
        envelope,
        account,
        chat_repo,
        agent_name=agent_name,
        plugin=plugin,
    )

    # 5-12. Per-session lock + persist + agent.step + persist.
    async with session_locks[session_row.id]:
        # 6. Update last_inbound_at (and updated_at — the resolver's
        # most-recent-by-updated_at ordering consumes this).
        await chat_repo.update_last_inbound(session_row.id, now_iso())

        # 7. Build a fresh agent for this turn. Errors here
        # (ProviderNotConfiguredError, ProviderNotFoundError) propagate
        # — F8's caller catches them and surfaces a degraded state.
        agent = await factory.create(agent_name)

        # 8. Re-fetch the session row inside the lock — history may
        # have been mutated by a previously serialized inbound. Decode
        # the stored messages; mirror the ``_restore_session`` shape:
        # keep the freshly-built agent's system message, append the
        # non-system stored messages.
        db_session = await chat_repo.get(session_row.id)
        stored = decode_messages(db_session.messages)
        if stored:
            non_system = [m for m in stored if m.role != Role.SYSTEM]
            agent.messages = agent.messages[:1] + non_system

        # 9. Bind the ContextVar so any pool-spawned MCP OAuth provider
        # construction during agent.step routes ``auth_required``
        # broadcasts to the right session id (mirror of the WS handler
        # at ``interfaces/web/app.py:257``).
        # Snapshot ``pre_step_len`` BEFORE entering the try — pure read,
        # no exception risk; consumed by F4 L4's post-step visibility
        # tagging pass below.
        pre_step_len = len(agent.messages)
        token = current_chat_session_id.set(session_row.id)
        try:
            # 10. Drive agent.step. The agent's core appends
            # ``Message.user(envelope.text)`` internally
            # (``agent/core.py:138``); iterates LLM round-trips;
            # appends assistant + tool messages. After completion,
            # ``agent.messages`` holds the full updated history.
            # No on_chunk / on_usage callbacks — F3 has no UI
            # subscribers (F5 owns broadcast).
            async for _ in agent.step(envelope.text):
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

            # 11. Persist updated history. Mirror of
            # ``_save_session_to_db`` at
            # ``interfaces/web/app.py:469-487``. The leg-1 docstring
            # contract on ``ChatSessionRepository.update`` guarantees
            # the seven connector-identity columns are preserved
            # across this call — the SQL only writes ``title``,
            # ``messages``, ``updated_at``.
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
            # 12. Always reset the ContextVar — even if agent.step
            # raises mid-stream.
            current_chat_session_id.reset(token)


async def _clear_for_test() -> None:
    """Test seam: clear the shared per-session lock registry.

    Delegates to ``the_one.sessions.clear_locks_for_test``.
    Kept ``async def`` for back-compat with autouse fixtures that
    ``await`` this symbol.
    """
    from the_one.sessions import clear_locks_for_test
    clear_locks_for_test()
