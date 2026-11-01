"""Sortie 07 leg 4 - ``GET /api/config`` reports ``execution_sandbox`` (DD10).

The selection is monkeypatched in every test (it depends on the host), and the
value is cached on ``app.state`` by a lifespan task, never in a module variable.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from tests._schema_template import copy_template
from the_one.interfaces.web.api import router
from the_one.platform.sandbox import factory


def _select(name: str):
    def describe():
        return name, ("" if name == "bubblewrap" else "test")

    return describe


@pytest.fixture
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from the_one.config import settings
    from the_one.db import connection as db_connection

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    copy_template(settings.db_path)
    monkeypatch.setattr(db_connection, "_connection", None)
    yield tmp_path
    monkeypatch.setattr(db_connection, "_connection", None)


async def _get_config(app) -> dict:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://127.0.0.1", headers=auth_headers()
    ) as client:
        resp = await client.get("/api/config")
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.parametrize("name", ["bubblewrap", "passthrough"])
async def test_config_reports_the_selection(monkeypatch, name) -> None:
    monkeypatch.setattr(factory, "describe_selection", _select(name))
    app = FastAPI()
    app.include_router(router)
    assert (await _get_config(app))["execution_sandbox"] == name


async def test_a_request_before_the_warm_up_reads_off_the_loop(monkeypatch) -> None:
    loop_thread = threading.get_ident()
    seen: list[int] = []

    def describe():
        seen.append(threading.get_ident())
        return "passthrough", "test"

    monkeypatch.setattr(factory, "describe_selection", describe)
    app = FastAPI()
    app.include_router(router)
    await _get_config(app)
    assert seen and all(t != loop_thread for t in seen)


@pytest.mark.usefixtures("reset_lifespan_singletons")
async def test_two_app_runs_each_report_their_own_selection(
    _isolated_data_dir, monkeypatch
) -> None:
    from asgi_lifespan import LifespanManager

    from the_one.interfaces.web.app import app

    for name in ("bubblewrap", "passthrough", "bubblewrap"):
        monkeypatch.setattr(factory, "describe_selection", _select(name))
        async with LifespanManager(app):
            task = app.state.execution_sandbox_task
            await task
            assert app.state.execution_sandbox == name
            assert (await _get_config(app))["execution_sandbox"] == name


@pytest.mark.usefixtures("reset_lifespan_singletons")
async def test_the_lifespan_warm_up_runs_through_to_thread(_isolated_data_dir, monkeypatch) -> None:
    from asgi_lifespan import LifespanManager

    from the_one.interfaces.web.app import app

    monkeypatch.setattr(factory, "describe_selection", _select("passthrough"))
    real = asyncio.to_thread
    called: list[object] = []

    async def spy(fn, *a, **k):
        called.append(fn)
        return await real(fn, *a, **k)

    monkeypatch.setattr(asyncio, "to_thread", spy)
    async with LifespanManager(app):
        await app.state.execution_sandbox_task
    assert factory.describe_selection in called
