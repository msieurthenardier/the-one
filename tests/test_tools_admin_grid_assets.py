"""Asset wiring for the F6 L2 tools admin grid."""

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


class TestToolsGridAssets:
    async def test_tools_grid_js_served(self, client: AsyncClient) -> None:
        resp = await client.get("/static/js/areas/admin/tools-grid.js")
        assert resp.status_code == 200
        assert "App.admin.toolsGrid" in resp.text

    async def test_index_html_includes_tools_grid_script(self, client: AsyncClient) -> None:
        # The SPA shell lives at /static/index.html; the prod / route serves it
        # via FileResponse, but the static mount serves the same bytes here.
        resp = await client.get("/static/index.html")
        assert resp.status_code == 200
        assert "tools-grid.js" in resp.text
