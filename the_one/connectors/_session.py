"""Session-key normalization and continuation-window resolver.

M10 F03 L03: pure (envelope, account, plugin, repo) → ChatSession
resolver. Composes the plugin's :meth:`ConnectorPlugin.normalize_session_key`
(the existing F1 Protocol method) with a repository lookup and a
continuation-window check, creating a new chat_sessions row on first
contact or after the window elapses; reusing the most-recent matching
row when within the window.

The continuation window resolver mirrors
:func:`the_one.connectors._pool._resolve_ttl_seconds`'s shape: explicit
override → env var (read at call time) → default constant. The override
is the per-account ``ConnectorAccount.session_continuation_seconds``
(leg 1 added the column + Pydantic field); the env var is
``THE_ONE_SESSION_CONTINUATION_SECONDS``; the default is 86400 (24h).

Title derivation uses an OPTIONAL plugin hook ``display_channel``
accessed via ``getattr(plugin, "display_channel", None)``. This is NOT a
widening of the :class:`ConnectorPlugin` Protocol — see
``the_one/connectors/README.md`` "Optional hooks" section.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from the_one.connectors.base import ConnectorPlugin, InboundEnvelope
from the_one.db.models import ChatSession, ConnectorAccount, now_iso
from the_one.db.repositories import ChatSessionRepository

logger = logging.getLogger(__name__)


_DEFAULT_CONTINUATION_SECONDS = 86400  # 24 hours


def _resolve_continuation_seconds(override: int | None = None) -> int:
    """Resolve the per-account chat-session continuation window in seconds.

    Resolution order: explicit ``override`` (if not None) → env var
    ``THE_ONE_SESSION_CONTINUATION_SECONDS`` (if set + parseable) →
    ``_DEFAULT_CONTINUATION_SECONDS`` (86400). Env var is read at call
    time so test monkeypatching works; mirrors
    :func:`the_one.connectors._pool._resolve_ttl_seconds`.

    The override is the per-account
    ``ConnectorAccount.session_continuation_seconds`` value, passed
    through by :func:`resolve_session`. The resolver stays ignorant of
    which model field drives the override; the model owns the field
    name, the resolver owns the precedence. The ``override is not None``
    guard short-circuits BEFORE the env-var read by design — the
    operator's explicit per-account choice always wins.

    Non-int env-var values fall back to the default with a warning —
    matches the pool resolver's "fail open, don't crash" stance.
    """
    if override is not None:
        return override
    raw = os.environ.get("THE_ONE_SESSION_CONTINUATION_SECONDS")
    if raw is None:
        return _DEFAULT_CONTINUATION_SECONDS
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "THE_ONE_SESSION_CONTINUATION_SECONDS=%r is not an int; falling back to %d",
            raw,
            _DEFAULT_CONTINUATION_SECONDS,
        )
        return _DEFAULT_CONTINUATION_SECONDS


def _derive_title(envelope: InboundEnvelope, plugin: ConnectorPlugin) -> str:
    """Derive a human-readable session title for first-contact session creation.

    Calls the OPTIONAL ``plugin.display_channel(envelope)`` hook via
    :func:`getattr` with a sentinel-None default. Catches any exception
    from the hook AND any empty-string return; falls back to
    ``envelope.channel_id`` so the resolver is independent of plugin
    authorship discipline. Logs caught exceptions so plugin bugs surface
    without breaking inbound dispatch.

    NOT a widening of :class:`ConnectorPlugin`. See
    ``the_one/connectors/README.md`` "Optional hooks" section for the
    convention.
    """
    hook = getattr(plugin, "display_channel", None)
    if hook is None:
        return envelope.channel_id
    try:
        result = hook(envelope)
    except Exception:
        logger.warning(
            "plugin.display_channel raised; falling back to channel_id",
            exc_info=True,
        )
        return envelope.channel_id
    if not result:
        return envelope.channel_id
    return result


async def resolve_session(
    envelope: InboundEnvelope,
    account: ConnectorAccount,
    repo: ChatSessionRepository,
    *,
    agent_name: str,
    plugin: ConnectorPlugin,
) -> ChatSession:
    """Map an inbound envelope to its chat_sessions row.

    Steps:

    1. Ask the plugin for the canonical :class:`SessionKey` via
       :meth:`ConnectorPlugin.normalize_session_key`. The plugin
       decides which envelope fields participate in the key; the
       resolver respects that decision.
    2. Derive the 4-tuple lookup ``(platform, account_id, channel_id,
       thread_id)`` from the SessionKey. ``peer_id`` is NOT in the
       lookup tuple (per flight design — stored on the row at creation
       for audit, but doesn't participate in matching).
    3. Look up the most recent matching row via
       :meth:`ChatSessionRepository.find_most_recent_by_external_key`.
    4. If a row exists AND its ``last_inbound_at`` is within the
       per-account continuation window → return that row (reuse path).
       The dispatcher in F3 L4 calls
       :meth:`ChatSessionRepository.update_last_inbound` to bump the
       timestamp; F3 L3 does NOT touch the existing row.
    5. Else (no match OR outside the window) → create a new row with
       the external-key columns populated, ``agent_name`` set, title
       derived via the optional ``display_channel`` hook,
       ``last_inbound_at = now_iso()``. Returns the new row.

    Pure function — no pool acquire, no lock, no agent.step. F3 L4's
    dispatcher composes this with the pool and per-session lock.
    """
    key = plugin.normalize_session_key(envelope)
    continuation = _resolve_continuation_seconds(
        override=account.session_continuation_seconds
    )

    existing = await repo.find_most_recent_by_external_key(
        platform=key.platform,
        connector_account_id=key.account_id,
        channel_id=key.channel_id,
        thread_id=key.thread_id,
    )

    if existing is not None:
        metadata = existing.session_metadata or {}
        if "ended_at" in metadata:
            # M10 F07 L6: the ``/new`` (or ``/reset``) command wrote an
            # ``ended_at`` sentinel onto the session. Skip the reuse
            # path; fall through to new-row creation below so the next
            # inbound starts a fresh chat_sessions row.
            pass
        elif existing.last_inbound_at is not None:
            try:
                last = datetime.fromisoformat(existing.last_inbound_at)
            except ValueError:
                logger.warning(
                    "chat_sessions.last_inbound_at=%r is not ISO; treating as stale",
                    existing.last_inbound_at,
                )
                last = None
            if last is not None:
                # Normalise to UTC for the comparison — `now_iso` writes
                # UTC, but a hand-built test row may write naive; if naive,
                # treat as UTC to match the canonical write helper.
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                if (now - last).total_seconds() < continuation:
                    return existing

    # Create a new row on the (no-match OR outside-window OR ended) paths.
    title = _derive_title(envelope, plugin)
    current_iso = now_iso()
    new_session = ChatSession(
        id=uuid.uuid4().hex,
        agent_name=agent_name,
        title=title,
        messages="[]",
        created_at=current_iso,
        updated_at=current_iso,
        platform=key.platform,
        connector_account_id=key.account_id,
        channel_id=key.channel_id,
        thread_id=key.thread_id,
        peer_id=key.peer_id,
        session_metadata=None,
        last_inbound_at=current_iso,
    )
    await repo.create(new_session)
    return new_session
