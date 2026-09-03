"""Regression test for Squawk 0037 -- the Telegram Bot API embeds the bot
token in the request URL path (``/bot<token>/<method>``, see
``the_one/connectors/telegram/_api.py``), and httpx/httpcore log the full
request URL at INFO on every request. Left unquieted, that leaks the
token into the host log on every poll cycle. Fixed in
``the_one.logging_config.configure_logging`` by pinning the ``httpx`` and
``httpcore`` loggers to WARNING. No live network -- all requests go
through ``tests._telegram_api_fixture.FakeTelegramApi``'s
``httpx.MockTransport``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from tests._telegram_api_fixture import FakeTelegramApi
from the_one.connectors import base
from the_one.connectors.telegram.plugin import TelegramPlugin
from the_one.db.models import Connector
from the_one.encryption import get_encryptor
from the_one.logging_config import _QUIETED_THIRD_PARTY_LOGGERS, configure_logging

# Distinctive enough that it can't accidentally collide with any other
# substring the test infra or fixture might log (chat ids, message ids).
_SECRET_TOKEN = "887654321:AAF9k_SQUAWK0037_SECRET_TOKEN_STRING"


def _account(token: str) -> Connector:
    return Connector(
        id="acc-1", name="Test Telegram", type="telegram", secrets={"token": token}, config={}
    )


@pytest.fixture(autouse=True)
def _hermetic_third_party_loggers():
    """Restore httpx/httpcore levels after the test so a hostile
    precondition simulated here (or the fix's own WARNING pin) never
    leaks into other tests running in the same process."""
    originals = {name: logging.getLogger(name).level for name in _QUIETED_THIRD_PARTY_LOGGERS}
    yield
    for name, level in originals.items():
        logging.getLogger(name).setLevel(level)


async def test_telegram_poll_and_send_cycle_logs_no_token_at_info(tmp_path: Path, caplog) -> None:
    """A full connect (getMe + getUpdates poll loop) + send cycle against
    the fixture must not put the token into any INFO-level log line.

    The setup deliberately puts ``httpx``'s logger into the exact hostile
    state that caused the original leak (an explicit INFO level, as
    ``anthropic``/``openai`` set it themselves at import time when
    ``ANTHROPIC_LOG=info``/``OPENAI_LOG=info`` is set) *before* calling
    ``configure_logging()`` -- proving the app's own startup call wins
    and re-quiets it, rather than the test passing vacuously because
    httpx was never loud to begin with.
    """
    logging.getLogger("httpx").setLevel(logging.INFO)
    logging.getLogger("httpcore").setLevel(logging.INFO)

    configure_logging()
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() == logging.WARNING

    fake = FakeTelegramApi(
        me={"id": 111, "is_bot": True, "username": "TestBot"},
        updates=[
            {
                "update_id": 5,
                "message": {
                    "message_id": 1,
                    "chat": {"id": 999, "type": "private"},
                    "from": {"id": 42, "first_name": "Alice"},
                    "text": "hi",
                },
            }
        ],
    )
    plugin = TelegramPlugin(api_transport=fake.transport)
    encryptor = get_encryptor(tmp_path)
    account = _account(_SECRET_TOKEN)
    inbound = []

    async def on_inbound(envelope):
        inbound.append(envelope)

    with caplog.at_level(logging.DEBUG):
        client = await plugin.connect(account, encryptor, on_inbound)
        try:
            await asyncio.sleep(0.05)  # let the poll loop dispatch the scheduled update
            assert len(inbound) == 1  # the poll cycle actually ran
            await client.send(base.PeerTarget(connector_id=account.id, peer_id="999"), "hello back")
        finally:
            await plugin.disconnect(client)

    # The fixture itself proves requests actually happened (getMe,
    # getUpdates, sendMessage all hit the token-bearing path).
    methods_called = {m for m, _ in fake.calls}
    assert {"getMe", "getUpdates", "sendMessage"} <= methods_called

    # The actual regression assertion: the token never appears in any
    # captured log line, at any level.
    assert _SECRET_TOKEN not in caplog.text

    # Stronger, mechanism-level assertion: no httpx/httpcore INFO record
    # was emitted at all -- pins the quieting itself, not just an
    # incidental absence of the token substring.
    noisy_info_records = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO
        and any(r.name == name or r.name.startswith(f"{name}.") for name in ("httpx", "httpcore"))
    ]
    noisy_messages = [r.getMessage() for r in noisy_info_records]
    assert noisy_info_records == [], (
        f"expected no httpx/httpcore INFO records, got: {noisy_messages}"
    )
