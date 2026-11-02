"""Routes GET/PUT /api/time-settings, GET /api/time-zones and /api/info (M28 F1 L1)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from tests._schema_template import connect_template_db
from the_one import time_zones
from the_one.encryption import Encryptor


@pytest.fixture
async def client(tmp_path, frozen_clock):
    conn = await connect_template_db(tmp_path / "test.db")
    enc = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=enc),
    ):
        app = shared_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=auth_headers()
        ) as c:
            c.conn = conn  # type: ignore[attr-defined]
            c.enc = enc  # type: ignore[attr-defined]
            yield c
    await conn.close()


LA_TOOL = (
    "2026-10-10T15:45:12-07:00 (America/Los_Angeles)\n"
    "Saturday, October 10, 2026, 3:45 PM PDT (UTC-07:00)"
)


class TestGet:
    async def test_default_shape(self, client: AsyncClient) -> None:
        body = (await client.get("/api/time-settings")).json()
        assert set(body) == {"mode", "zone", "system", "effective", "tool_enabled", "preview"}
        assert body["mode"] == "system" and body["zone"] is None
        assert body["system"] == {"zone": "America/Los_Angeles", "offset": "UTC-07:00"}
        assert body["effective"] == {
            "zone": "America/Los_Angeles",
            "canonical": "America/Los_Angeles",
            "label": "America/Los_Angeles",
            "offset": "UTC-07:00",
            "offset_minutes": -420,
            "abbreviation": "PDT",
        }
        assert body["tool_enabled"] is True
        assert body["preview"] == {
            "tool": LA_TOOL,
            "prompt": (
                "Today is Saturday, October 10, 2026 (America/Los_Angeles). This date is as of "
                "when this conversation was last loaded. For the current date and time, "
                "call current_time."
            ),
            "prompt_without_tool": (
                "Today is Saturday, October 10, 2026 (America/Los_Angeles), as of when this "
                "conversation was last loaded."
            ),
            "clock": "3:45 PM",
        }

    async def test_tool_enabled_follows_tool_config_row(self, client: AsyncClient) -> None:
        from the_one.db.repositories import ToolConfigRepository

        repo = ToolConfigRepository(client.conn, client.enc)  # type: ignore[attr-defined]
        assert (await client.get("/api/time-settings")).json()["tool_enabled"] is True
        await repo.upsert("current_time", {}, enabled=True)
        assert (await client.get("/api/time-settings")).json()["tool_enabled"] is True
        await repo.upsert("current_time", {}, enabled=False)
        assert (await client.get("/api/time-settings")).json()["tool_enabled"] is False

    @pytest.mark.parametrize("raw", ["garbage{{", '{"mode": "zone", "zone": "Mars/Olympus_Mons"}'])
    async def test_bad_stored_value_gives_default(self, client: AsyncClient, raw: str) -> None:
        from the_one.db.repositories import AppMetadataRepository

        await AppMetadataRepository(client.conn).set("time_zone", raw)  # type: ignore[attr-defined]
        body = (await client.get("/api/time-settings")).json()
        assert body["mode"] == "system" and body["zone"] is None


class TestPut:
    async def test_zone_mode_saves(self, client: AsyncClient) -> None:
        r = await client.put("/api/time-settings", json={"mode": "zone", "zone": "Asia/Tokyo"})
        assert r.status_code == 200
        body = r.json()
        assert body["effective"]["zone"] == "Asia/Tokyo"
        assert body["effective"]["offset"] == "UTC+09:00"
        assert body["preview"]["clock"] == "7:45 AM"
        assert (await client.get("/api/time-settings")).json()["mode"] == "zone"

    async def test_alias_accepted(self, client: AsyncClient) -> None:
        r = await client.put("/api/time-settings", json={"mode": "zone", "zone": "US/Pacific"})
        assert r.status_code == 200 and r.json()["effective"]["zone"] == "US/Pacific"

    async def test_system_mode_keeps_zone_and_follows_system(self, client: AsyncClient) -> None:
        r = await client.put("/api/time-settings", json={"mode": "system", "zone": "Asia/Tokyo"})
        body = r.json()
        assert body["zone"] == "Asia/Tokyo"
        assert body["effective"]["zone"] == "America/Los_Angeles"

    async def test_clear(self, client: AsyncClient) -> None:
        await client.put("/api/time-settings", json={"mode": "zone", "zone": "Asia/Tokyo"})
        r = await client.put("/api/time-settings", json={"mode": "system", "zone": None})
        assert r.json()["zone"] is None and r.json()["mode"] == "system"

    @pytest.mark.parametrize(
        ("body", "sentence"),
        [
            (
                {"mode": "zone", "zone": "Mars/Olympus_Mons"},
                "Unknown time zone 'Mars/Olympus_Mons'",
            ),
            ({"mode": "zone", "zone": "localtime"}, "Unknown time zone 'localtime'"),
            ({"mode": "zone", "zone": 5}, "Unknown time zone."),
            ({"mode": "zone"}, "Choose a time zone when mode is 'zone'."),
            ({"mode": "zone", "zone": None}, "Choose a time zone when mode is 'zone'."),
            ({"mode": "auto"}, "mode must be 'system' or 'zone'."),
            ({"mode": "system", "extra": 1}, "Body may contain only 'mode' and 'zone'."),
            (["mode"], "Body must be a JSON object."),
            ("zone", "Body must be a JSON object."),
        ],
    )
    async def test_422_is_one_sentence_and_changes_nothing(
        self, client: AsyncClient, body: Any, sentence: str
    ) -> None:
        await client.put("/api/time-settings", json={"mode": "zone", "zone": "Asia/Tokyo"})
        r = await client.put("/api/time-settings", json=body)
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert isinstance(detail, str) and sentence in detail
        after = (await client.get("/api/time-settings")).json()
        assert (after["mode"], after["zone"]) == ("zone", "Asia/Tokyo")

    async def test_malformed_json_is_422(self, client: AsyncClient) -> None:
        r = await client.put(
            "/api/time-settings", content=b"{not json", headers={"content-type": "application/json"}
        )
        assert r.status_code == 422 and isinstance(r.json()["detail"], str)

    async def test_long_zone_echo_truncated(self, client: AsyncClient) -> None:
        r = await client.put("/api/time-settings", json={"mode": "zone", "zone": "x" * 500})
        assert r.status_code == 422 and len(r.json()["detail"]) < 200


class TestZones:
    async def test_zone_rows(self, client: AsyncClient) -> None:
        body = (await client.get("/api/time-zones")).json()
        assert set(body) == {"zones", "links"}
        assert body["links"] == time_zones.zone_links()
        rows = {r["zone"]: r for r in body["zones"]}
        assert rows["Asia/Kolkata"]["offset"] == "UTC+05:30"
        assert rows["America/Los_Angeles"]["abbreviation"] == "PDT"
        assert rows["Pacific/Kiritimati"]["abbreviation"] == ""
        assert rows["Asia/Kathmandu"]["abbreviation"] == ""

    async def test_effective_numeric_abbreviation_is_empty(self, client: AsyncClient) -> None:
        r = await client.put(
            "/api/time-settings", json={"mode": "zone", "zone": "Pacific/Kiritimati"}
        )
        assert r.status_code == 200
        assert r.json()["effective"]["abbreviation"] == ""


class TestCanonical:
    async def test_stored_alias(self, client: AsyncClient) -> None:
        await client.put("/api/time-settings", json={"mode": "zone", "zone": "Asia/Calcutta"})
        eff = (await client.get("/api/time-settings")).json()["effective"]
        assert eff["zone"] == "Asia/Calcutta" and eff["canonical"] == "Asia/Kolkata"

    async def test_canonical_zone(self, client: AsyncClient) -> None:
        await client.put("/api/time-settings", json={"mode": "zone", "zone": "Asia/Kolkata"})
        eff = (await client.get("/api/time-settings")).json()["effective"]
        assert eff["zone"] == eff["canonical"] == "Asia/Kolkata"

    async def test_unnamed_system_zone(self, client: AsyncClient, monkeypatch) -> None:
        monkeypatch.setattr(time_zones, "detect_system_zone", lambda: None)
        eff = (await client.get("/api/time-settings")).json()["effective"]
        assert eff["zone"] is None and eff["canonical"] is None

    async def test_offset_minutes_positive_half_hour(self, client: AsyncClient) -> None:
        await client.put("/api/time-settings", json={"mode": "zone", "zone": "Asia/Kolkata"})
        eff = (await client.get("/api/time-settings")).json()["effective"]
        assert eff["offset_minutes"] == 330 and eff["offset"] == "UTC+05:30"

    async def test_offset_minutes_negative(self, client: AsyncClient) -> None:
        await client.put("/api/time-settings", json={"mode": "zone", "zone": "America/Denver"})
        eff = (await client.get("/api/time-settings")).json()["effective"]
        assert eff["offset_minutes"] == -360 and eff["offset"] == "UTC-06:00"

    async def test_offset_minutes_unnamed_system_zone(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        monkeypatch.setattr(time_zones, "detect_system_zone", lambda: None)
        eff = (await client.get("/api/time-settings")).json()["effective"]
        assert eff["zone"] is None
        assert isinstance(eff["offset_minutes"], int)
        sign = -1 if eff["offset"].startswith("UTC-") else 1
        hh, mm = eff["offset"][4:].split(":")
        assert eff["offset_minutes"] == sign * (int(hh) * 60 + int(mm))

    async def test_system_zone_detected_as_alias(self, client: AsyncClient, monkeypatch) -> None:
        monkeypatch.setattr(time_zones, "detect_system_zone", lambda: "Asia/Calcutta")
        eff = (await client.get("/api/time-settings")).json()["effective"]
        assert eff["zone"] == "Asia/Calcutta" and eff["canonical"] == "Asia/Kolkata"


@pytest.fixture
def full_client() -> Any:
    from the_one.interfaces.web.app import app

    with TestClient(app, headers=auth_headers()) as c:
        yield c


@pytest.mark.usefixtures("reset_lifespan_singletons")
class TestAuthAndInfo:
    @pytest.mark.parametrize(
        ("method", "path"),
        [("GET", "/api/time-settings"), ("PUT", "/api/time-settings"), ("GET", "/api/time-zones")],
    )
    def test_requires_credential(self, method: str, path: str) -> None:
        from the_one.interfaces.web.app import app

        with TestClient(app) as c:
            assert c.request(method, path, json={}).status_code == 401

    def test_info_date_examples(self, full_client: Any) -> None:
        body = full_client.get("/api/info").json()
        assert body["date_prompt_example"] == (
            "Today is {today's date} ({time zone}). This date is as of when this conversation "
            "was last loaded. For the current date and time, call current_time."
        )
        assert body["date_prompt_example_without_tool"] == (
            "Today is {today's date} ({time zone}), as of when this conversation was last loaded."
        )
