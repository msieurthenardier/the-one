"""Envelope-free connector delivery primitives (Mission 33 F1 L2).

Delivery of a turn's final reply, the step-limit line and the channel's
agent-authorization rule, reachable WITHOUT an inbound envelope. The inbound
pipeline (``inbound.py``) and the send tool call these. This module must not
import ``inbound.py``, ``app.py`` or ``tools/``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from the_one.connectors.base import ConnectorClientError, SendTarget
from the_one.db.models import Connector
from the_one.llm.base import Message, Role

if TYPE_CHECKING:
    from the_one.connectors.manager import ConnectorManager

logger = logging.getLogger(__name__)

STEP_LIMIT_LINE = "(Stopped: reached its step limit for this message.)"

# See the layering note in ``inbound.py``: inlined, not imported from
# ``the_one/tools/connector_send.py``. Agreement is pinned by
# ``tests/test_connector_send_tool.py::test_shared_constants_pin_inbound_literals``.
_SEND_TO_PLATFORM_CHANNEL_TOOL_NAME = "send_to_platform_channel"
_PLATFORM_SEND_OK_PREFIX = "[platform-send-ok]"


def authorized_agent_for(connector: Connector, *, channel_id: str | None) -> str | None:
    """The agent a connector authorizes for a target.

    A channel target (``channel_id`` not ``None``, including ``""``) uses
    ``channel_map[channel_id]`` then ``default_agent``; ``None`` (a peer/DM
    target) uses ``default_agent`` alone.
    """
    default = connector.config.get("default_agent")
    if channel_id is None:
        return default
    channel_map = connector.config.get("channel_map") or {}
    return channel_map.get(channel_id) or default


async def send_step_limit_line(
    target: SendTarget, connector_id: str, manager: "ConnectorManager"
) -> None:
    """Tell the peer the agent stopped at its step limit. NEVER raises.

    A neutral plain line to the given target; with no client or on a send
    failure it is logged and dropped. Not stored.
    """
    try:
        client = manager.client_for(connector_id)
        if client is None:
            logger.warning(
                "dispatch_inbound: step-limit line skipped for connector %s (no live client)",
                connector_id,
            )
            return
        await client.send(target, STEP_LIMIT_LINE)
    except ConnectorClientError:
        logger.exception("dispatch_inbound: step-limit line failed for connector %s", connector_id)
    except Exception:
        logger.exception(
            "dispatch_inbound: unexpected error sending step-limit line for connector %s",
            connector_id,
        )


async def deliver_final_reply(
    messages: list[Message],
    pre_step_len: int,
    target: SendTarget,
    connector_id: str,
    manager: "ConnectorManager",
) -> None:
    """Mechanically deliver the turn's final assistant text to ``target`` (DD-10).

    Skip rule (no double-send): any message at or after ``pre_step_len`` that
    is a ``Role.TOOL`` result of ``send_to_platform_channel`` starting with
    the platform-send success prefix means the agent already spoke this turn,
    even to a different channel (DD-10's trade-off), and nothing is sent.

    Otherwise the FINAL ``Role.ASSISTANT`` message with non-empty str content
    is sent through ``manager.client_for(connector_id)``. Only a successful
    send mutates a message: its ``visibility`` flips to ``None`` (peer-visible)
    in place. Failures are logged (no live client, a send error); the reply
    stays operator-only. Never raises.
    """
    new_msgs = messages[pre_step_len:]

    tool_call_names: dict[str, str] = {}
    for msg in new_msgs:
        if msg.role == Role.ASSISTANT:
            for tc in msg.tool_calls:
                tool_call_names[tc.id] = tc.name

    for msg in new_msgs:
        if (
            msg.role == Role.TOOL
            and msg.tool_result is not None
            and tool_call_names.get(msg.tool_result.tool_call_id)
            == _SEND_TO_PLATFORM_CHANNEL_TOOL_NAME
            and isinstance(msg.content, str)
            and msg.content.startswith(_PLATFORM_SEND_OK_PREFIX)
        ):
            return

    assistant_msgs = [m for m in new_msgs if m.role == Role.ASSISTANT]
    if not assistant_msgs:
        return
    final = assistant_msgs[-1]
    if not isinstance(final.content, str) or not final.content:
        return

    client = manager.client_for(connector_id)
    if client is None:
        logger.warning(
            "dispatch_inbound: auto-reply delivery skipped for connector %s "
            "(no live client); reply stays operator-only",
            connector_id,
        )
        return

    try:
        await client.send(target, final.content)
    except ConnectorClientError:
        logger.exception(
            "dispatch_inbound: auto-reply delivery failed for connector %s; "
            "reply stays operator-only",
            connector_id,
        )
        return
    except Exception:
        logger.exception(
            "dispatch_inbound: unexpected error auto-delivering reply for connector %s; "
            "reply stays operator-only",
            connector_id,
        )
        return

    final.visibility = None
