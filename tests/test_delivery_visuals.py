"""``delivery.send_reply`` and its callers (M35 F3 L3, AC3, AC6-AC9)."""

from __future__ import annotations

import asyncio
import json
import logging

import pytest

from the_one.connectors import delivery
from the_one.connectors.base import (
    ChannelTarget,
    ConnectorClientError,
    SendResult,
    VisualUploadError,
)
from the_one.llm.base import Message, Role
from the_one.visuals import chart_image
from the_one.visuals.chart_image import ChartImageError, RenderedChart
from the_one.visuals.outbound import WIDGET_NOTE

TARGET = ChannelTarget(connector_id="conn-1", channel_id="ch-1")


def _chart(title: str = "", n: int = 3) -> str:
    spec = {
        "type": "bar",
        "x": {"values": [f"Q{i}" for i in range(n)]},
        "series": [{"values": list(range(n))}],
    }
    if title:
        spec["title"] = title
    return "```chart\n" + json.dumps(spec) + "\n```\n"


class _Plain:
    """A client without ``send_visual``."""

    def __init__(self, exc: Exception | None = None):
        self.calls: list[tuple] = []
        self.exc = exc

    async def send(self, target, content):
        self.calls.append(("send", target, content))
        if self.exc:
            raise self.exc
        return None


class _Visual(_Plain):
    def __init__(self, visual_exc=None, details=None, fallback_exc=None, with_fallback=False):
        super().__init__(fallback_exc)
        self.visual_exc = visual_exc
        self.details = details
        if with_fallback:
            self.send_visual_fallback = self._fallback

    async def send_visual(self, target, content, images):
        self.calls.append(("send_visual", target, content, list(images)))
        if self.visual_exc:
            raise self.visual_exc
        return SendResult("m", {} if self.details is None else self.details)

    async def _fallback(self, target, content):
        self.calls.append(("send_visual_fallback", target, content))
        if self.exc:
            raise self.exc
        return SendResult("fb", {})


@pytest.fixture
def fake_render(monkeypatch):
    def render(spec):
        return RenderedChart(data=b"PNG" + spec.title.encode(), width=640, height=300)

    monkeypatch.setattr(chart_image, "render_png", render)


# AC3 / AC6(a)


@pytest.mark.parametrize(
    "content",
    [
        "plain text",
        "```python\nprint(1)\n```\n",
        "```chart\n{broken}\n```\n",
        "```chart\n" + json.dumps({"type": "bar"}),
    ],
)
async def test_no_plan_sends_the_identical_content_and_nothing_else(content) -> None:
    client = _Visual()
    result, n = await delivery.send_reply(client, TARGET, content, connector_id="c")
    assert n == 0 and result is None
    assert len(client.calls) == 1
    kind, target, sent = client.calls[0]
    assert kind == "send" and target is TARGET and sent is content


# (b)


async def test_widget_only_sends_the_fallback_text() -> None:
    client = _Visual()
    text = "hi\n```widget\n<p/>\n```\nbye"
    await delivery.send_reply(client, TARGET, text)
    assert client.calls == [("send", TARGET, f"hi\n{WIDGET_NOTE}\nbye")]


# (c)


async def test_none_drawn_sends_fallback_and_warns_per_chart(monkeypatch, caplog) -> None:
    def boom(spec):
        raise ChartImageError("secret-data-123")

    monkeypatch.setattr(chart_image, "render_png", boom)
    client = _Visual()
    text = _chart("A") + _chart("B")
    with caplog.at_level(logging.WARNING):
        _, n = await delivery.send_reply(client, TARGET, text, connector_id="conn-9")
    assert n == 0
    assert client.calls == [("send", TARGET, text)]
    warns = [r.getMessage() for r in caplog.records if "could not be drawn" in r.getMessage()]
    assert len(warns) == 2
    assert "chart 0" in warns[0] and "chart 1" in warns[1]
    assert all("conn-9" in w and "secret-data" not in w for w in warns)


# (d)


async def test_drawn_charts_go_through_send_visual_in_order(fake_render) -> None:
    client = _Visual()
    text = "x\n```chart\n{bad}\n```\n" + _chart("One") + _chart("") + "end"
    result, n = await delivery.send_reply(client, TARGET, text)
    assert n == 2 and result.platform_message_id == "m"
    ((kind, target, content, images),) = client.calls
    assert kind == "send_visual" and target is TARGET
    assert content.startswith("x\n```chart\n{bad}\n```\n")
    assert [i.filename for i in images] == ["chart-2.png", "chart-3.png"]
    assert [i.title for i in images] == ["One", "Chart 3"]
    assert images[0].data == b"PNGOne" and (images[0].width, images[0].height) == (640, 300)
    assert images[0].fallback == _chart("One")
    assert "\U0001f4ca Chart: One (below)" in content and "Chart 3 (below)" in content


async def test_a_chart_that_fails_alone_stays_as_its_source(monkeypatch) -> None:
    def render(spec):
        if spec.title == "Bad":
            raise ChartImageError("x")
        return RenderedChart(data=b"P", width=1, height=1)

    monkeypatch.setattr(chart_image, "render_png", render)
    client = _Visual()
    await delivery.send_reply(client, TARGET, _chart("Good") + _chart("Bad"))
    ((_, _, content, images),) = client.calls
    assert [i.title for i in images] == ["Good"]
    assert content == "\U0001f4ca Chart: Good (below)\n" + _chart("Bad")


@pytest.mark.parametrize(
    ("details", "expected"),
    [
        ({"images_sent": 1}, 1),
        ({}, 2),
        ({"images_sent": "2"}, 2),
        ({"images_sent": 9}, 2),
        ({"images_sent": -3}, 0),
        ({"images_sent": 0}, 0),
    ],
)
async def test_images_sent_comes_from_details_and_is_clamped(
    fake_render, details, expected
) -> None:
    client = _Visual(details=details)
    _, n = await delivery.send_reply(client, TARGET, _chart("A") + _chart("B"))
    assert n == expected


# (e)


async def test_no_send_visual_sends_the_fallback(fake_render) -> None:
    client = _Plain()
    text = _chart("A")
    _, n = await delivery.send_reply(client, TARGET, text)
    assert n == 0 and client.calls == [("send", TARGET, text)]


# (f)


@pytest.mark.parametrize("with_fallback", [True, False])
async def test_upload_error_resends_once_as_text(fake_render, caplog, with_fallback) -> None:
    exc = VisualUploadError("platform-controlled body text")
    exc.status = 413
    client = _Visual(visual_exc=exc, with_fallback=with_fallback)
    text = "hello\n" + _chart("A") + _chart("B")
    with caplog.at_level(logging.WARNING):
        result, n = await delivery.send_reply(client, TARGET, text, connector_id="conn-7")
    assert n == 0
    assert [c[0] for c in client.calls] == [
        "send_visual",
        "send_visual_fallback" if with_fallback else "send",
    ]
    assert client.calls[1][2] == text
    assert result is None if not with_fallback else result.platform_message_id == "fb"
    (warn,) = [r.getMessage() for r in caplog.records if "refused" in r.getMessage()]
    assert "[0, 1]" in warn and "conn-7" in warn and "_Visual" in warn and "413" in warn
    assert "falling back to text" in warn
    assert "hello" not in warn and "platform-controlled" not in warn


# (g)


async def test_a_plain_connector_error_propagates_without_a_resend(fake_render) -> None:
    client = _Visual(visual_exc=ConnectorClientError("HTTP 502"))
    with pytest.raises(ConnectorClientError) as info:
        await delivery.send_reply(client, TARGET, _chart("A"))
    assert not isinstance(info.value, VisualUploadError)
    assert [c[0] for c in client.calls] == ["send_visual"]


# (h)


async def test_a_failing_resend_propagates(fake_render) -> None:
    client = _Visual(
        visual_exc=VisualUploadError("HTTP 400"),
        fallback_exc=ConnectorClientError("down"),
    )
    with pytest.raises(ConnectorClientError, match="down"):
        await delivery.send_reply(client, TARGET, _chart("A"))
    assert [c[0] for c in client.calls] == ["send_visual", "send"]


# AC7


async def test_drawing_does_not_block_the_event_loop(monkeypatch) -> None:
    import threading
    import time

    threads: list[str] = []

    def slow(spec):
        threads.append(threading.current_thread().name)
        time.sleep(0.2)
        return RenderedChart(data=b"P", width=1, height=1)

    monkeypatch.setattr(chart_image, "render_png", slow)
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    calls = []
    real = asyncio.to_thread

    async def counting(fn, *a, **kw):
        calls.append(fn)
        return await real(fn, *a, **kw)

    monkeypatch.setattr(delivery.asyncio, "to_thread", counting)
    await delivery.send_reply(_Visual(), TARGET, _chart("A") + _chart("B"))
    task.cancel()
    assert ticks >= 10  # the loop kept running during 2 x 0.2 s of drawing
    assert len(calls) == 1  # one to_thread draws every candidate
    assert set(threads) and "MainThread" not in threads


# AC8


class _Manager:
    def __init__(self, client):
        self.client = client

    def client_for(self, connector_id):
        return self.client


def _final(text: str) -> list[Message]:
    return [Message(role=Role.USER, content="hi"), Message(role=Role.ASSISTANT, content=text)]


async def test_deliver_final_reply_converts_and_flips_visibility(fake_render) -> None:
    client = _Visual()
    msgs = _final("see\n" + _chart("T"))
    msgs[-1].visibility = "operator"
    await delivery.deliver_final_reply(msgs, 1, TARGET, "conn-1", _Manager(client))
    assert client.calls[0][0] == "send_visual"
    assert msgs[-1].visibility is None


async def test_deliver_final_reply_plain_text_is_unchanged() -> None:
    client = _Visual()
    msgs = _final("just words")
    await delivery.deliver_final_reply(msgs, 1, TARGET, "conn-1", _Manager(client))
    assert client.calls == [("send", TARGET, "just words")]
    assert msgs[-1].visibility is None


async def test_deliver_final_reply_keeps_operator_only_when_both_sends_fail(fake_render) -> None:
    client = _Visual(
        visual_exc=VisualUploadError("HTTP 400"), fallback_exc=ConnectorClientError("x")
    )
    msgs = _final(_chart("T"))
    msgs[-1].visibility = "operator"
    await delivery.deliver_final_reply(msgs, 1, TARGET, "conn-1", _Manager(client))
    assert msgs[-1].visibility == "operator"


def test_delivery_imports_nothing_from_inbound_app_or_tools() -> None:
    import ast
    from pathlib import Path

    tree = ast.parse(Path(delivery.__file__).read_text("utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        elif isinstance(node, ast.Import):
            names += [a.name for a in node.names]
    for bad in ("inbound", "app", "tools"):
        assert not any(bad in n.split(".") for n in names), names
