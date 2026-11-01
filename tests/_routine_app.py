"""Shared end-to-end routine harness (M33 F1 leg 4; reused by leg 5).

``routine_app`` enters ``lifespan(app)`` on a schema-template data dir with the
dev gates open (the stub connector plugin registers), patches the provider
lookup with a scriptable LLM and talks to the app through an ASGI client. The
``Harness`` it yields is what leg 5 reuses.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from tests._routine_schedules import daily
from tests._schema_template import copy_template
from the_one.agent.config import AgentConfig  # noqa: F401
from the_one.config import settings
from the_one.connectors import registry as plugin_registry
from the_one.connectors.stub import StubPlugin
from the_one.db import connection as db_connection
from the_one.db.connection import get_connection
from the_one.db.repositories import ChatSessionRepository
from the_one.llm.base import LLMProvider, Message
from the_one.routines import runner


class ScriptLLM(LLMProvider):
    """Returns scripted assistant messages in order; the last one repeats."""

    name = "script"

    def __init__(self) -> None:
        self.script: list[Message] = [Message.assistant(content="routine reply")]
        self.delay = 0.0
        self.calls: list[list[Message]] = []

    async def complete(self, messages, tools=None, temperature=0.0, max_tokens=16384, **kw):
        self.calls.append(list(messages))
        if self.delay:
            await asyncio.sleep(self.delay)
        if len(self.script) > 1:
            return self.script.pop(0)
        return self.script[0]


class WS:
    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.frames.append(payload)


async def wait_for(cond, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = cond()
        if asyncio.iscoroutine(r):
            r = await r
        if r:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met in time")


@dataclass
class Harness:
    client: AsyncClient
    llm: ScriptLLM
    connector_id: str = ""
    agent: str = "bot"
    sids: list[str] = field(default_factory=list)

    async def api(self, method: str, path: str, **kw) -> Any:
        return await self.client.request(method, path, **kw)

    async def chat_rows(self) -> list:
        repo = ChatSessionRepository(await get_connection())
        async with (await get_connection()).execute("SELECT id FROM chat_sessions") as cur:
            ids = [r[0] for r in await cur.fetchall()]
        return [await repo.get(i) for i in ids]

    async def routine(self, name: str = "Brief", **over) -> dict:
        body = {
            "name": name,
            "prompt": "do the thing",
            "schedule": daily("09:00"),
            **over,
        }
        r = await self.api("POST", f"/api/agents/{self.agent}/routines", json=body)
        assert r.status_code == 201, r.text
        return r.json()

    async def run_now(self, rid: str) -> None:
        r = await self.api("POST", f"/api/agents/{self.agent}/routines/{rid}/run")
        assert r.status_code == 202, r.text
        await wait_for(lambda: not runner.registry.is_running(rid))

    async def runs(self, rid: str) -> list[dict]:
        r = await self.api("GET", f"/api/agents/{self.agent}/routines/{rid}/runs")
        return r.json()["runs"]

    async def last_run(self, rid: str) -> dict:
        runs = await self.runs(rid)
        assert runs, "no run recorded"
        return runs[0]


@pytest.fixture
async def routine_app(tmp_path, monkeypatch):
    from the_one.interfaces.web.app import app, lifespan

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.setenv("THE_ONE_STUB_TEST_ENDPOINT", "1")
    monkeypatch.setenv("THE_ONE_ROUTINE_RUN_TIMEOUT_SECONDS", "60")
    from the_one.db import _write_lock
    from the_one.interfaces.web import app as appmod
    from the_one.sessions._locks import clear_locks_for_test

    _write_lock.reset_for_test()
    clear_locks_for_test()
    appmod._sessions.clear()
    copy_template(settings.db_path)
    monkeypatch.setattr(db_connection, "_connection", None)
    StubPlugin.reset_for_test()
    plugin_registry.clear_for_test()
    runner.registry.reset_for_test()
    llm = ScriptLLM()
    monkeypatch.setattr("the_one.agent.factory.get_provider", lambda name, **kw: llm)

    # The lifespan owns anyio scopes, so it runs inside one task start to finish.
    ready, stop = asyncio.Event(), asyncio.Event()

    async def _serve() -> None:
        async with lifespan(app):
            ready.set()
            await stop.wait()

    server = asyncio.create_task(_serve())
    await asyncio.wait_for(ready.wait(), 30)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8499",
            headers=auth_headers(),
        ) as client:
            h = Harness(client=client, llm=llm)
            r = await client.post(
                "/api/providers", json={"name": "mock", "type": "mock", "base_url": ""}
            )
            assert r.status_code == 201, r.text
            r = await client.post(
                "/api/agents",
                json={
                    "name": "bot",
                    "provider_config_id": r.json()["id"],
                    "llm_model": "mock-default",
                    "system_prompt": "You are a test agent.",
                },
            )
            assert r.status_code == 201, r.text
            r = await client.post(
                "/api/connectors",
                json={
                    "name": "Stubby",
                    "type": "stub",
                    "config": {"default_agent": "bot", "allowlist": {"peers": ["p1"]}},
                    "secrets": {"token": "t"},
                },
            )
            assert r.status_code == 201, r.text
            h.connector_id = r.json()["id"]
            from the_one.connectors.manager import get_manager

            await wait_for(lambda: get_manager().client_for(h.connector_id) is not None)
            yield h
    finally:
        stop.set()
        await asyncio.wait_for(server, 60)
        _write_lock.reset_for_test()
        clear_locks_for_test()
        appmod._sessions.clear()
    StubPlugin.reset_for_test()
    plugin_registry.clear_for_test()
    runner.registry.reset_for_test()
