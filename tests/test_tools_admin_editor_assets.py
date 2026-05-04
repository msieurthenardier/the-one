"""Asset wiring for the F6 L3 per-tool editor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import aiosqlite
import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from httpx import ASGITransport, AsyncClient

import the_one.interfaces.web.app as web_app
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
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    await conn.close()


class TestToolsEditorAssets:
    async def test_tools_editor_js_served(self, client: AsyncClient) -> None:
        resp = await client.get("/static/js/areas/admin/tools-editor.js")
        assert resp.status_code == 200
        assert "App.admin.renderToolsEditor" in resp.text
        # F6 HAT inline fix #3: model-level 422 errors and unmatched-field
        # 422 errors route to a prominent banner (above .editor-section)
        # rather than the small `.editor-error` span. The banner DOM is
        # emitted in the renderer; assert the served bundle still carries
        # the marker class.
        assert "editor-error-banner" in resp.text

    async def test_index_html_includes_tools_editor_script(self, client: AsyncClient) -> None:
        # The SPA shell lives at /static/index.html; the prod / route serves it
        # via FileResponse, but the static mount serves the same bytes here.
        resp = await client.get("/static/index.html")
        assert resp.status_code == 200
        assert "tools-editor.js" in resp.text
