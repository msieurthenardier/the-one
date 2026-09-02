"""``TelegramPlugin`` — ``ConnectorPlugin``/``ConnectorClient`` Protocol
implementation, envelope translation, per-account long-poll state (DD-1/
DD-2, Mission 23 Flight 4)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from the_one.connectors import base
from the_one.connectors.telegram._api import DEFAULT_BASE_URL, TelegramApiClient
from the_one.db.models import Connector
from the_one.encryption import Encryptor

logger = logging.getLogger(__name__)

_POLL_TIMEOUT = 50  # DD-2: getUpdates(timeout=50, allowed_updates=["message"])
_LIVENESS_GRACE_SECONDS = 10.0  # is_alive() window: 2*POLL_TIMEOUT+GRACE


@dataclass
class _AccountState:
    # offset: redelivery cursor (DD-2, AC-2) -- fresh state means offset=None.
    bot_id: str | None = None
    bot_username: str | None = None
    offset: int | None = None
    last_poll_at: float | None = None
    failure: str | None = None
    client: "TelegramClient | None" = None
    allowlist_peers: frozenset[str] = field(default_factory=frozenset)


def _mentions_bot(msg: dict[str, Any], state: _AccountState) -> bool:
    # DD-2: "mention" entity -> @botusername (ci); "text_mention" -> bot
    # user.id. Offsets are UTF-16 CODE UNITS, sliced via UTF-16LE re-encode.
    entities = msg.get("entities") or []
    if not entities:
        return False
    bot_username = (state.bot_username or "").lstrip("@").lower()
    text16 = (msg.get("text") or "").encode("utf-16-le")
    for ent in entities:
        etype = ent.get("type")
        if etype == "text_mention":
            uid = (ent.get("user") or {}).get("id", "")
            if state.bot_id is not None and str(uid) == state.bot_id:
                return True
        elif etype == "mention" and bot_username:
            start = ent.get("offset", 0) * 2
            end = start + ent.get("length", 0) * 2
            mention = text16[start:end].decode("utf-16-le", errors="ignore")
            if mention.lstrip("@").lower() == bot_username:
                return True
    return False


async def _upsert_channel_directory(
    connector_id: str, chat_id: str, thread_id: str | None, title: str
) -> None:
    # DD-4 (cycle-2, quoted): "Channel entries are DELIBERATELY NOT admission-
    # gated ... naming visible channels grants zero new reach."
    from the_one.db.connection import get_connection
    from the_one.db.repositories import ConnectorDirectoryRepository

    try:
        conn = await get_connection()
        await ConnectorDirectoryRepository(conn).upsert(
            connector_id=connector_id,
            kind="channel",
            platform_id=chat_id,
            thread_id=thread_id,
            display_name=title,
            username=None,
        )
    except Exception:
        logger.exception(
            "telegram plugin: channel-directory upsert failed for %s/%s", connector_id, chat_id
        )


async def _translate_message(
    state: _AccountState, msg: dict[str, Any], connector_id: str
) -> base.InboundEnvelope | None:
    """One Bot API ``message`` -> ``InboundEnvelope``, or ``None`` to drop."""
    text = msg.get("text")
    if not text:
        return None  # text-less (joins/stickers/media) -- no media handling
    frm = msg.get("from") or {}
    frm_id = str(frm.get("id", "")) if frm.get("id") is not None else ""
    if frm.get("is_bot") and frm_id not in state.allowlist_peers:
        return None  # bot-authored, not allowlisted -> drop (Flight 3 DD-4 parity)

    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    is_dm = chat.get("type") == "private"
    raw_thread = msg.get("message_thread_id")
    thread_id = str(raw_thread) if raw_thread is not None else None
    if not is_dm and chat.get("title"):
        await _upsert_channel_directory(connector_id, chat_id, thread_id, chat["title"])

    first, last = frm.get("first_name") or "", frm.get("last_name") or ""
    peer_name = f"{first} {last}".strip() or frm.get("username") or frm_id or "unknown"
    return base.InboundEnvelope(
        platform="telegram",
        connector_id=connector_id,
        channel_id=chat_id,
        thread_id=thread_id,
        peer_id=frm_id,
        peer_name=peer_name,
        text=text,
        is_dm=is_dm,
        mentions_bot=_mentions_bot(msg, state),
        peer_username=frm.get("username"),
    )


@dataclass
class TelegramClient:
    """Structurally satisfies ``ConnectorClient``. NO ``history`` method
    (the Bot API has no history endpoint) -- covered free by ``fetch_
    channel_history``'s existing ``getattr(client, "history", None)``."""

    _task: asyncio.Task
    _api: TelegramApiClient
    account_id: str
    _state: _AccountState

    def is_alive(self) -> bool:  # DD-2: task alive AND last poll within window
        if self._task.done():
            return False
        last = self._state.last_poll_at
        window = 2 * _POLL_TIMEOUT + _LIVENESS_GRACE_SECONDS
        return last is None or time.monotonic() - last <= window

    async def send(self, target: base.SendTarget, content: str) -> base.SendResult:
        # DD-2: PeerTarget -> chat_id=peer_id (Telegram DM chat id IS the
        # user id, no Create-DM step); ChannelTarget -> chat_id+thread.
        if isinstance(target, base.PeerTarget):
            chat_id, thread_id = target.peer_id, None
        else:
            chat_id, thread_id = target.channel_id, target.thread_id
        result = await self._api.send_message(
            chat_id=chat_id, text=content, message_thread_id=thread_id
        )
        return base.SendResult(platform_message_id=str(result.get("message_id", "")))


class TelegramPlugin:
    """Type-keyed singleton -- production ``ConnectorPlugin`` for Telegram."""

    def __init__(self, *, base_url: str = DEFAULT_BASE_URL, api_transport: Any = None) -> None:
        self._base_url = base_url
        self._api_transport = api_transport  # test seam: a real instance never sets this
        self._state: dict[str, _AccountState] = {}

    def _state_for(self, account_id: str) -> _AccountState:
        return self._state.setdefault(account_id, _AccountState())

    def _new_api_client(self, token: str) -> TelegramApiClient:
        kwargs = {"transport": self._api_transport} if self._api_transport is not None else {}
        return TelegramApiClient(token, base_url=self._base_url, **kwargs)

    async def connect(
        self, account: Connector, encryptor: Encryptor, on_inbound: base.InboundCallback
    ) -> TelegramClient:
        # getMe + first getUpdates in a background task, awaited via
        # ready_future: 401/404/409 raises PermanentConnectorFailure.
        state = self._state_for(account.id)
        state.failure = None  # lifecycle rule: cleared unconditionally at the top.
        state.offset = None
        allowlist = account.config.get("allowlist") or {}
        state.allowlist_peers = frozenset(allowlist.get("peers") or [])
        api = self._new_api_client(account.secrets["token"])
        connector_id = account.id
        ready_future: asyncio.Future[None] = asyncio.get_running_loop().create_future()

        async def _run() -> None:  # closure: avoids a 5-param helper signature
            try:
                me = await api.get_me()
                state.bot_id = str(me.get("id", ""))
                state.bot_username = me.get("username")
                while True:
                    updates = await api.get_updates(offset=state.offset, timeout=_POLL_TIMEOUT)
                    state.last_poll_at = time.monotonic()
                    if not ready_future.done():
                        ready_future.set_result(None)
                    last_update_id: int | None = None
                    for update in updates:
                        last_update_id = update["update_id"]
                        msg = update.get("message")
                        if msg is None:
                            continue  # allowed_updates=["message"] excludes the rest
                        envelope = await _translate_message(state, msg, connector_id)
                        if envelope is not None:
                            await on_inbound(envelope)
                    if last_update_id is not None:
                        state.offset = last_update_id + 1  # after dispatch only (AC-2)
            except asyncio.CancelledError:
                raise
            except BaseException as exc:  # must resolve ready_future on every exit
                if not ready_future.done():
                    ready_future.set_exception(exc)
                if isinstance(exc, base.PermanentConnectorFailure):
                    raise

        task = asyncio.create_task(_run())
        try:
            await ready_future
        except Exception as exc:
            if isinstance(exc, base.PermanentConnectorFailure):
                state.failure = str(exc)
            with contextlib.suppress(Exception):
                await task
            await api.aclose()
            raise

        client = TelegramClient(task, api, account.id, state)
        state.client = client
        return client

    async def disconnect(self, client: "TelegramClient") -> None:
        """Idempotent -- safe on an already-disconnected client."""
        if not client._task.done():
            client._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await client._task
        with contextlib.suppress(Exception):
            await client._api.aclose()
        state = self._state.get(client.account_id)
        if state is not None and state.client is client:
            state.client = None

    async def doctor(self, account: Connector, encryptor: Encryptor) -> base.DoctorReport:
        state = self._state_for(account.id)
        if state.failure is not None:
            msg = f"permanently failed: {state.failure}"
            return base.DoctorReport(status="failed", message=msg)
        token = account.secrets.get("token")
        if not token:
            return base.DoctorReport(status="failed", message="no bot token configured")
        api = self._new_api_client(token)
        try:
            me = await api.get_me()
        except base.ConnectorClientError as exc:
            return base.DoctorReport(status="failed", message=f"API check failed: {exc}")
        finally:
            await api.aclose()
        poll_alive = state.client is not None and state.client.is_alive()
        return base.DoctorReport(
            status="ok" if poll_alive else "degraded",
            message="poll loop connected" if poll_alive else "API reachable; poll not connected",
            details={"bot_username": me.get("username"), "poll_connected": poll_alive},
        )
