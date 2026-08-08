"""Asset wiring for the F6 L4 connection-test buttons."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from httpx import ASGITransport, AsyncClient

import the_one.interfaces.web.app as web_app
from tests._credential_helpers import auth_headers
from the_one.db.schema import ensure_schema
from the_one.interfaces.web.api import router

# Resolve the prod static dir from the package source — independent of CWD.
_STATIC_DIR = Path(web_app.__file__).parent / "static"


@pytest.fixture
async def client(tmp_path):
    db_path = tmp_path / "test.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
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


class TestToolsTestButtonAssets:
    async def test_tools_editor_js_exposes_test_button_wiring(self, client: AsyncClient) -> None:
        resp = await client.get("/static/js/areas/admin/tools-editor.js")
        assert resp.status_code == 200
        body = resp.text
        assert "_TESTABLE_TOOLS" in body
        assert "test-tool-btn" in body
        assert "/api/tools/configs/" in body
        # Anchor on the trailing /test' (or '/test) so a comment mentioning
        # /test elsewhere cannot satisfy this assertion.
        assert "/test'" in body or "'/test" in body
        assert "tool-test-output" in body
