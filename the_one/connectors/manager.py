"""Listener-task lifecycle + in-memory pairing-code store (DD-1, DD-3).

One :class:`ConnectorManager` instance is installed at lifespan startup
via :func:`set_manager` (mirrors ``agent.factory.set_factory`` /
``get_factory`` — the send/history tools resolve the running manager the
same way the agent loop resolves the running factory, with no
construction-time wiring). Tests construct their own instances freely.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import secrets as _secrets
import time
from dataclasses import dataclass

from the_one.connectors import registry
from the_one.connectors.base import (
    ConnectorClient,
    ConnectorPlugin,
    InboundEnvelope,
    PermanentConnectorFailure,
)
from the_one.db.models import Connector
from the_one.db.repositories import ConnectorRepository
from the_one.encryption import Encryptor

logger = logging.getLogger(__name__)

PAIRING_TTL_SECONDS = 600  # DD-3: 10 minutes. Public — the pairing-code
# route (interfaces/web/api.py) renders the wall-clock expiry from this
# constant since generate_pairing_code below only tracks a monotonic
# deadline internally.


@dataclass
class _PairingEntry:
    code: str
    expires_at: float


@dataclass
class _ListenerEntry:
    task: asyncio.Task
    client: ConnectorClient | None = None


class ConnectorManager:
    """Owns one supervised listener task per enabled connector.

    ``poll_interval`` / ``backoff_base`` / ``backoff_max`` are
    constructor-overridable (production uses the defaults; tests pass
    small values so reconnect/backoff scenarios run fast).
    """

    def __init__(
        self,
        *,
        poll_interval: float = 5.0,
        backoff_base: float = 1.0,
        backoff_max: float = 30.0,
    ) -> None:
        self._listeners: dict[str, _ListenerEntry] = {}
        self._pairing: dict[str, _PairingEntry] = {}
        self._poll_interval = poll_interval
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max

    # ── pairing codes (DD-3) — no await between check and consume, so
    # concurrent submissions of the same code resolve atomically under
    # asyncio's cooperative scheduling: first caller wins, the rest see
    # the code already gone. ─────────────────────────────────────────
    def generate_pairing_code(self, connector_id: str) -> str:
        code = _secrets.token_hex(4)
        self._pairing[connector_id] = _PairingEntry(
            code=code, expires_at=time.monotonic() + PAIRING_TTL_SECONDS
        )
        return code

    def consume_pairing_code(self, connector_id: str, candidate: str) -> bool:
        """Return True and consume the code iff it matches and hasn't expired."""
        entry = self._pairing.get(connector_id)
        if entry is None:
            return False
        if time.monotonic() > entry.expires_at:
            del self._pairing[connector_id]
            return False
        if entry.code != candidate:
            return False
        del self._pairing[connector_id]
        return True

    # ── listener lifecycle ──────────────────────────────────────────
    def client_for(self, connector_id: str) -> ConnectorClient | None:
        entry = self._listeners.get(connector_id)
        return entry.client if entry is not None else None

    async def start_all(self, repo: ConnectorRepository, encryptor: Encryptor) -> None:
        for account in await repo.list():
            # DD-6 (Mission 23 Flight 3 Leg 2): absent key = enabled, no
            # migration. ``start()`` itself stays dumb — this is the only
            # skip point at boot; unit tests constructing accounts directly
            # and calling ``start()`` keep the original unconditional
            # behavior.
            if account.config.get("enabled", True) is False:
                continue
            self.start(account, encryptor, repo=repo)

    def start(
        self,
        account: Connector,
        encryptor: Encryptor,
        *,
        repo: ConnectorRepository | None = None,
    ) -> None:
        """Start a listener task for ``account``.

        ``repo`` is OPTIONAL (Mission 23 Flight 2 Leg 2, DD-Q3 rotation
        fix): when supplied, ``_run``'s supervisor loop re-fetches a fresh
        connector row from it before every RECONNECT attempt (not the
        initial connect — see ``_run``'s docstring) so a listener that
        outlives a PUT-driven config change or an encryption-key rotation
        never reconnects on stale in-memory state. Callers that omit it
        (unit tests constructing an in-memory-only ``Connector`` with no
        backing DB row) keep the original closure-captured-``account``
        behavior unchanged.
        """
        if account.id in self._listeners:
            return
        task = asyncio.create_task(self._run(account, encryptor, repo))
        self._listeners[account.id] = _ListenerEntry(task=task)

    def listener_ids(self) -> list[str]:
        """Ids of every connector this manager currently tracks a listener
        task for (connecting, connected, or backing off). Read by the
        rotation-restart hook (``interfaces/web/api.py``) to know which
        connectors need a stop+start cycle after a key rotation."""
        return list(self._listeners)

    async def stop(self, connector_id: str) -> None:
        """Stop the listener for ``connector_id``. Idempotent on an unknown id."""
        entry = self._listeners.pop(connector_id, None)
        if entry is None:
            return
        entry.task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await entry.task

    async def drain(self) -> None:
        for connector_id in list(self._listeners):
            await self.stop(connector_id)

    async def _run(
        self,
        account: Connector,
        encryptor: Encryptor,
        repo: ConnectorRepository | None = None,
    ) -> None:
        """Supervisor loop: connect, hold while alive, reconnect with backoff.

        Rotation fix (Q3 design review): the FIRST connect attempt uses the
        ``account`` snapshot the caller passed to :meth:`start` (unchanged
        behavior — a test constructing an in-memory-only account with no
        ``repo`` still connects on it). Every attempt AFTER that — i.e.
        every reconnect, whether from a dead client or a failed connect —
        re-fetches a fresh row via ``repo`` (when supplied) before calling
        ``plugin.connect`` again. Without this, a listener that survives a
        long time on the original closure-captured ``account`` would
        reconnect using secrets decrypted before an encryption-key
        rotation, silently stranding it in the backoff loop forever. A
        missing row (deleted mid-backoff) stops the loop cleanly.
        """
        plugin = registry.get_plugin(account.type)
        if plugin is None:
            logger.warning(
                "connector %s: no plugin registered for type %r", account.id, account.type
            )
            return
        account_id = account.id
        current = account
        attempt = 0
        while True:
            if attempt > 0 and repo is not None:
                try:
                    current = await repo.get(account_id)
                except KeyError:
                    logger.info("connector %s: row no longer exists; stopping listener", account_id)
                    return
            try:
                client = await self._connect_once(plugin, current, encryptor)
            except PermanentConnectorFailure as exc:
                # AC-4: stop-and-log, no backoff. The `_ListenerEntry` for
                # `account_id` is deliberately left in `self._listeners` —
                # correct today because every recovery path
                # (`update_connector` PUT, rotation restart) calls `stop()`
                # before `start()`, so this read as intentional, not a
                # leak (design review 2026-09-01).
                logger.error(
                    "connector %s: permanent failure (%s); listener stopping, no reconnect",
                    account_id,
                    exc,
                )
                return
            if client is not None:
                entry = self._listeners.get(account_id)
                if entry is None:
                    # stop() raced us — disconnect the just-connected client and exit.
                    await _safe_disconnect(plugin, client)
                    return
                entry.client = client
                attempt = 0
                try:
                    while client.is_alive():
                        await asyncio.sleep(self._poll_interval)
                finally:
                    await _safe_disconnect(plugin, client)
                    live_entry = self._listeners.get(account_id)
                    if live_entry is not None:
                        live_entry.client = None
            attempt += 1
            delay = min(self._backoff_base * (2 ** (attempt - 1)), self._backoff_max)
            delay += random.uniform(0, delay * 0.25)
            await asyncio.sleep(delay)

    async def _connect_once(
        self, plugin: ConnectorPlugin, account: Connector, encryptor: Encryptor
    ) -> ConnectorClient | None:
        from the_one.connectors.inbound import dispatch_inbound

        async def _on_inbound(envelope: InboundEnvelope) -> None:
            try:
                await dispatch_inbound(account.id, envelope, manager=self)
            except Exception:
                logger.exception("connector %s: inbound dispatch failed", account.id)

        try:
            return await plugin.connect(account, encryptor, _on_inbound)
        except asyncio.CancelledError:
            raise
        except PermanentConnectorFailure:
            # AC-5: re-raise ahead of the catch-all below so `_run` alone
            # converts this to stop+log — `_connect_once` itself just
            # forwards it (no logging here would double-log at two layers).
            raise
        except Exception:
            logger.exception("connector %s: connect failed", account.id)
            return None


async def _safe_disconnect(plugin: ConnectorPlugin, client: ConnectorClient) -> None:
    try:
        await plugin.disconnect(client)
    except Exception:
        logger.exception("connector: disconnect failed")


_manager: ConnectorManager | None = None


def set_manager(manager: ConnectorManager | None) -> None:
    """Install the application :class:`ConnectorManager`. Lifespan-only."""
    global _manager
    _manager = manager


def get_manager() -> ConnectorManager | None:
    """Return the running :class:`ConnectorManager`, or ``None`` pre-startup."""
    return _manager
