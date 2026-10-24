"""The real 422 body shapes `App.api.fieldErrors` is built for (M31 F4 L03a, DD3).

`tests/browser/test_ui_api_errors.py` feeds copies of these bodies to the JS
reader; this file proves the copies still match what the API sends (provenance).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one.interfaces.web.api import router


@pytest.fixture
async def client(tmp_path):
    conn = await connect_template_db(tmp_path / "test.db")
    with patch("the_one.interfaces.web.api.get_connection", return_value=conn):
        app = FastAPI()
        app.include_router(router)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers()
        ) as c:
            yield c
    await conn.close()


async def test_tools_config_field_error_loc_is_config_field(client: AsyncClient) -> None:
    resp = await client.put(
        "/api/tools/configs/http_request", json={"config": {"timeout_seconds_max": -1}}
    )
    assert resp.status_code == 422
    item = resp.json()["detail"][0]
    assert item["loc"] == ["timeout_seconds_max"]
    assert item["msg"].startswith("Input should be greater than or equal to")


async def test_knowledge_settings_field_error_loc_is_bare_field(client: AsyncClient) -> None:
    resp = await client.put("/api/knowledge-settings", json={"chunking": {"size_chars": 1}})
    assert resp.status_code == 422
    items = resp.json()["detail"]
    assert isinstance(items, list)
    assert items[0]["loc"] == ["size_chars"]


async def test_knowledge_overlap_model_validator_loc_is_empty(client: AsyncClient) -> None:
    resp = await client.put(
        "/api/knowledge-settings", json={"chunking": {"size_chars": 1000, "overlap_chars": 900}}
    )
    assert resp.status_code == 422
    item = resp.json()["detail"][0]
    assert item["loc"] == []
    assert item["msg"].startswith("Value error, ")
