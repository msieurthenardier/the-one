"""Asset wiring for the F6 L5 shared tools-form-helpers module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from httpx import ASGITransport, AsyncClient

import the_one.interfaces.web.app as web_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.interfaces.web.api import router

# Resolve the prod static dir from the package source — independent of CWD.
_STATIC_DIR = Path(web_app.__file__).parent / "static"


@pytest.fixture
async def client(tmp_path):
    db_path = tmp_path / "test.db"
    conn = await connect_template_db(db_path)
    with patch("the_one.interfaces.web.api.get_connection", return_value=conn):
        test_app = FastAPI()
        test_app.include_router(router)
        test_app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=auth_headers()
        ) as c:
            yield c
    await conn.close()


class TestToolsFormHelpersAssets:
    async def test_tools_form_helpers_js_served(self, client: AsyncClient) -> None:
        resp = await client.get("/static/js/areas/admin/tools-form-helpers.js")
        assert resp.status_code == 200
        assert "App.adminFormHelpers" in resp.text
