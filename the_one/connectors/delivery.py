"""Envelope-free connector delivery primitives (Mission 33 F1 L2).

Delivery of a turn's final reply, the step-limit line and the channel's
agent-authorization rule, reachable WITHOUT an inbound envelope. The inbound
pipeline (``inbound.py``) and the send tool call these. This module must not
import ``inbound.py``, ``app.py`` or ``tools/``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from the_one.connectors.base import (
    ConnectorClientError,
    OutboundImage,
    SendResult,
    SendTarget,
    VisualUploadError,
)
from the_one.db.models import Connector
from the_one.llm.base import Message, Role
from the_one.visuals.outbound import plan_outbound

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


def _draw_all(candidates: tuple, connector_id: str) -> dict[int, Any]:
    """Draw every candidate (runs in a worker thread); a failure leaves a chart undrawn."""
    from the_one.visuals import chart_image

    drawn: dict[int, Any] = {}
    for cand in candidates:
        try:
            drawn[cand.index] = chart_image.render_png(cand.spec)
        except Exception as exc:  # ChartImageError or anything unexpected: never the data
            logger.warning(
                "chart %d could not be drawn for connector %s (%s); falling back to text",
                cand.index,
                connector_id,
                type(exc).__name__,
            )
    return drawn


async def send_reply(
    client: Any, target: SendTarget, content: str, *, connector_id: str = ""
) -> tuple[SendResult | None, int]:
    """Send ``content`` to ``target``, turning chart and widget blocks into platform output.

    The one conversion step shared by the automatic reply and ``send_to_platform_channel``
    (M35 F3 DD1). Returns ``(client's result, images_sent)``. With nothing to convert the
    call is exactly ``client.send(target, content)``. Raises what the client raises, except
    a ``VisualUploadError`` (nothing was posted), which is resent once as plain text.
    """
    plan = plan_outbound(content)
    if plan is None:
        return await client.send(target, content), 0
    if not plan.candidates:
        return await client.send(target, plan.fallback_text), 0

    rendered = await asyncio.to_thread(_draw_all, plan.candidates, connector_id)
    send_visual = getattr(client, "send_visual", None)
    if not rendered or send_visual is None:
        return await client.send(target, plan.fallback_text), 0

    drawn = set(rendered)
    images = [
        OutboundImage(
            filename=f"chart-{cand.number}.png",
            data=rendered[cand.index].data,
            title=cand.alt,
            width=rendered[cand.index].width,
            height=rendered[cand.index].height,
            fallback=cand.source,
        )
        for cand in plan.candidates
        if cand.index in drawn
    ]
    refused: VisualUploadError | None = None
    try:
        result = await send_visual(target, plan.render(drawn), images)
    except VisualUploadError as exc:
        refused = exc
    if refused is not None:
        exc = refused
        # The one warning for this fallback: indices, connector, client class and status only.
        # Never the exception text or response body (platform-controlled) or any chart data.
        logger.warning(
            "chart upload refused for charts %s on connector %s (%s), status %s; "
            "falling back to text",
            sorted(drawn),
            connector_id,
            type(client).__name__,
            getattr(exc, "status", None),
        )
        resend = getattr(client, "send_visual_fallback", None) or client.send
        return await resend(target, plan.fallback_text), 0
    sent = len(images)
    details = getattr(result, "details", None)
    if isinstance(details, dict):
        value = details.get("images_sent", sent)
        if isinstance(value, int) and not isinstance(value, bool):
            sent = max(0, min(value, len(images)))
    return result, sent


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
        await send_reply(client, target, final.content, connector_id=connector_id)
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
