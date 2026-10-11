"""The zone module (M28 F1 L1): names, detection, setting, resolve, formatters."""

from __future__ import annotations

import ast
import locale
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from tests._schema_template import connect_template_db
from the_one import time_zones as tz
from the_one.time_zones import EffectiveZone, TimeZoneSetting

NOW = datetime(2026, 10, 10, 22, 45, 12, tzinfo=timezone.utc)
LA = EffectiveZone("America/Los_Angeles", ZoneInfo("America/Los_Angeles"))
KOLKATA = EffectiveZone("Asia/Kolkata", ZoneInfo("Asia/Kolkata"))


@pytest.fixture
async def conn(tmp_path):
    c = await connect_template_db(tmp_path / "t.db")
    yield c
    await c.close()


class TestNames:
    def test_canonical(self) -> None:
        z = tz.canonical_zones()
        assert len(z) > 300
        assert {"Asia/Kolkata", "America/Los_Angeles", "Etc/UTC"} <= set(z)
        assert "US/Pacific" not in z
        assert z == sorted(z)

    def test_names_include_links(self) -> None:
        assert "US/Pacific" in tz.zone_names()
        assert set(tz.canonical_zones()) <= tz.zone_names()

    @pytest.mark.parametrize("key", ["America/Los_Angeles", "US/Pacific", "UTC"])
    def test_known(self, key: str) -> None:
        assert tz.is_known_zone(key) is True

    @pytest.mark.parametrize(
        "key",
        [
            "localtime",
            "posixrules",
            "Mars/Olympus_Mons",
            "",
            None,
            5,
            ["UTC"],
            "../etc/passwd",
            "America/../../x",
        ],
    )
    def test_unknown(self, key) -> None:
        assert tz.is_known_zone(key) is False


class _FakeTzlocal:
    def __init__(self, value=None, boom=False):
        self.value, self.boom, self.reloads = value, boom, 0

    def reload_localzone(self):
        self.reloads += 1

    def get_localzone_name(self):
        if self.boom:
            raise RuntimeError("no zone")
        return self.value


class TestDetect:
    @pytest.fixture(autouse=True)
    def _reset(self, monkeypatch):
        monkeypatch.setattr(tz, "_last_reload", None)

    def test_returns_known_name(self, monkeypatch) -> None:
        monkeypatch.setattr(tz, "tzlocal", _FakeTzlocal("Asia/Tokyo"))
        assert tz.detect_system_zone() == "Asia/Tokyo"

    @pytest.mark.parametrize("value", [None, "", "localtime", "Not/AZone", 7])
    def test_unusable_is_none(self, monkeypatch, value) -> None:
        monkeypatch.setattr(tz, "tzlocal", _FakeTzlocal(value))
        assert tz.detect_system_zone() is None

    def test_exception_is_none(self, monkeypatch) -> None:
        monkeypatch.setattr(tz, "tzlocal", _FakeTzlocal(boom=True))
        assert tz.detect_system_zone() is None

    def test_utc_is_accepted(self, monkeypatch) -> None:
        monkeypatch.setattr(tz, "tzlocal", _FakeTzlocal("UTC"))
        assert tz.detect_system_zone() == "UTC"

    def test_reload_at_most_once_a_minute(self, monkeypatch) -> None:
        fake = _FakeTzlocal("Asia/Tokyo")
        monkeypatch.setattr(tz, "tzlocal", fake)
        clock = [1000.0]
        monkeypatch.setattr(tz.time, "monotonic", lambda: clock[0])
        tz.detect_system_zone()
        tz.detect_system_zone()
        assert fake.reloads == 1
        clock[0] += 61
        tz.detect_system_zone()
        assert fake.reloads == 2


class TestSetting:
    def test_defaults(self) -> None:
        s = TimeZoneSetting()
        assert (s.mode, s.zone) == ("system", None)

    def test_zone_mode_needs_zone(self) -> None:
        with pytest.raises(ValidationError):
            TimeZoneSetting(mode="zone")

    @pytest.mark.parametrize("mode", ["system", "zone"])
    def test_unknown_zone_rejected_in_either_mode(self, mode) -> None:
        with pytest.raises(ValidationError):
            TimeZoneSetting(mode=mode, zone="Mars/Olympus_Mons")

    def test_extra_forbidden_and_bad_mode(self) -> None:
        with pytest.raises(ValidationError):
            TimeZoneSetting.model_validate({"mode": "system", "x": 1})
        with pytest.raises(ValidationError):
            TimeZoneSetting.model_validate({"mode": "auto"})

    async def test_absent_is_default(self, conn) -> None:
        assert await tz.load_setting(conn) == TimeZoneSetting()

    async def test_round_trip(self, conn) -> None:
        s = TimeZoneSetting(mode="zone", zone="Asia/Tokyo")
        await tz.save_setting(conn, s)
        assert await tz.load_setting(conn) == s

    @pytest.mark.parametrize(
        "raw",
        ["not json{{", '{"mode": "zone", "zone": "Mars/X"}', '{"mode": "zone"}', "[]"],
    )
    async def test_invalid_stored_is_default_with_warning(self, conn, raw, caplog) -> None:
        from the_one.db.repositories import AppMetadataRepository

        await AppMetadataRepository(conn).set(tz.SETTING_KEY, raw)
        with caplog.at_level("WARNING"):
            assert await tz.load_setting(conn) == TimeZoneSetting()
        assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 1


class TestResolve:
    def test_zone_mode(self) -> None:
        eff = tz.resolve(TimeZoneSetting(mode="zone", zone="Asia/Tokyo"))
        assert eff.key == "Asia/Tokyo" and eff.tzinfo == ZoneInfo("Asia/Tokyo")

    def test_system_mode_named(self, monkeypatch) -> None:
        monkeypatch.setattr(tz, "detect_system_zone", lambda: "Europe/Paris")
        eff = tz.resolve(TimeZoneSetting())
        assert eff.key == "Europe/Paris"

    def test_system_mode_unnamed_keeps_host_abbreviation(self, monkeypatch) -> None:
        monkeypatch.setattr(tz, "detect_system_zone", lambda: None)
        eff = tz.resolve(TimeZoneSetting())
        host = datetime.now().astimezone()
        assert eff.key is None
        assert eff.tzinfo.utcoffset(None) == host.utcoffset()
        assert eff.tzinfo.tzname(None) == host.tzname()

    def test_zone_that_fails_to_load_falls_back(self, monkeypatch, caplog) -> None:
        monkeypatch.setattr(tz, "detect_system_zone", lambda: "Europe/Paris")

        def boom(key):
            if key == "Asia/Tokyo":
                raise OSError("gone")
            return ZoneInfo(key)

        monkeypatch.setattr(tz, "ZoneInfo", boom)
        with caplog.at_level("WARNING"):
            eff = tz.resolve(TimeZoneSetting(mode="zone", zone="Asia/Tokyo"))
        assert eff.key == "Europe/Paris"
        assert any("could not be loaded" in r.message for r in caplog.records)

    async def test_load_effective_zone_honours_frozen_clock_seam(self, conn, frozen_clock) -> None:
        eff = await tz.load_effective_zone(conn)
        assert eff.key == "America/Los_Angeles"
        assert tz.utcnow() == frozen_clock

    async def test_load_effective_zone_never_raises(self, monkeypatch, frozen_clock) -> None:
        async def boom(conn):
            raise RuntimeError("db gone")

        monkeypatch.setattr(tz, "load_setting", boom)
        eff = await tz.load_effective_zone(object())
        assert eff.key == "America/Los_Angeles"


class TestFormatters:
    def test_tool_lines_la(self) -> None:
        assert tz.tool_lines(NOW, LA) == [
            "2026-10-10T15:45:12-07:00 (America/Los_Angeles)",
            "Saturday, October 10, 2026, 3:45 PM PDT (UTC-07:00)",
        ]

    def test_tool_lines_kolkata(self) -> None:
        assert tz.tool_lines(NOW, KOLKATA) == [
            "2026-10-11T04:15:12+05:30 (Asia/Kolkata)",
            "Sunday, October 11, 2026, 4:15 AM IST (UTC+05:30)",
        ]

    def test_tool_lines_numeric_abbreviation_omitted(self) -> None:
        kiri = EffectiveZone("Pacific/Kiritimati", ZoneInfo("Pacific/Kiritimati"))
        kath = EffectiveZone("Asia/Kathmandu", ZoneInfo("Asia/Kathmandu"))
        assert tz.tool_lines(NOW, kiri)[1] == "Sunday, October 11, 2026, 12:45 PM (UTC+14:00)"
        assert tz.tool_lines(NOW, kath)[1] == "Sunday, October 11, 2026, 4:30 AM (UTC+05:45)"

    def test_tool_lines_unnamed_utc(self) -> None:
        eff = EffectiveZone(None, timezone.utc)
        assert tz.tool_lines(NOW, eff) == [
            "2026-10-10T22:45:12+00:00 (system time zone, UTC+00:00)",
            "Saturday, October 10, 2026, 10:45 PM UTC (UTC+00:00)",
        ]

    def test_unnamed_offsets_with_and_without_a_name(self) -> None:
        named = EffectiveZone(None, timezone(timedelta(hours=-5), "CDT"))
        bare = EffectiveZone(None, timezone(timedelta(hours=-5)))
        assert tz.tool_lines(NOW, named)[1] == "Saturday, October 10, 2026, 5:45 PM CDT (UTC-05:00)"
        assert tz.tool_lines(NOW, bare)[1] == "Saturday, October 10, 2026, 5:45 PM (UTC-05:00)"

    def test_date_line(self) -> None:
        assert tz.date_line(NOW, LA, tool_available=True) == (
            "Today is Saturday, October 10, 2026 (America/Los_Angeles). This date is as of "
            "when this conversation was last loaded. For the current date and time, "
            "call current_time."
        )
        assert tz.date_line(NOW, LA, tool_available=False) == (
            "Today is Saturday, October 10, 2026 (America/Los_Angeles), as of when this "
            "conversation was last loaded."
        )

    def test_render_date_line_placeholders(self) -> None:
        assert tz.render_date_line("{today's date}", "{time zone}", tool_available=True) == (
            "Today is {today's date} ({time zone}). This date is as of when this conversation "
            "was last loaded. For the current date and time, call current_time."
        )
        assert tz.render_date_line("{today's date}", "{time zone}", tool_available=False) == (
            "Today is {today's date} ({time zone}), as of when this conversation was last loaded."
        )

    def test_clock_text(self) -> None:
        assert tz.clock_text(NOW, LA) == "3:45 PM"
        utc = EffectiveZone("Etc/UTC", ZoneInfo("Etc/UTC"))
        assert tz.clock_text(datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc), utc) == "12:00 AM"
        assert tz.clock_text(datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc), utc) == "12:00 PM"

    def test_half_hour_zone_minutes(self) -> None:
        kt = EffectiveZone("Asia/Kathmandu", ZoneInfo("Asia/Kathmandu"))
        assert tz.clock_text(NOW, kt) == "4:30 AM"

    def test_locale_neutral(self) -> None:
        old = locale.setlocale(locale.LC_TIME)
        for name in ("fr_FR.UTF-8", "de_DE.UTF-8"):
            try:
                locale.setlocale(locale.LC_TIME, name)
                break
            except locale.Error:
                continue
        else:
            pytest.skip("no fr_FR or de_DE locale installed")
        try:
            assert tz.tool_lines(NOW, LA)[1] == (
                "Saturday, October 10, 2026, 3:45 PM PDT (UTC-07:00)"
            )
        finally:
            locale.setlocale(locale.LC_TIME, old)


class TestZoneLinks:
    def test_named_links(self) -> None:
        links = tz.zone_links()
        assert links["Asia/Calcutta"] == "Asia/Kolkata"
        assert links["UTC"] == "Etc/UTC"
        assert links["US/Pacific"] == "America/Los_Angeles"
        assert links["Europe/Oslo"] in tz.canonical_zones()

    def test_every_target_is_canonical(self) -> None:
        canon = set(tz.canonical_zones())
        assert all(v in canon for v in tz.zone_links().values())

    def test_canonical_name(self) -> None:
        assert tz.canonical_name("Asia/Kolkata") == "Asia/Kolkata"
        assert tz.canonical_name("Asia/Calcutta") == "Asia/Kolkata"
        assert tz.canonical_name("Mars/Olympus_Mons") is None
        assert tz.canonical_name(None) is None
        assert tz.canonical_name(5) is None


class TestZoneRows:
    def test_kolkata_row(self) -> None:
        rows = {r["zone"]: r for r in tz.zone_rows(NOW)}
        assert rows["Asia/Kolkata"] == {
            "zone": "Asia/Kolkata",
            "region": "Asia",
            "city": "Kolkata",
            "offset": "UTC+05:30",
            "abbreviation": "IST",
        }

    def test_exclusions_and_utc(self) -> None:
        rows = {r["zone"]: r for r in tz.zone_rows(NOW)}
        for name in ("Factory", "CST6CDT", "EST5EDT", "MST7MDT", "PST8PDT"):
            assert name not in rows
            assert name in tz.zone_names()
        assert not [z for z in rows if z.startswith("Etc/") and z != "Etc/UTC"]
        assert (rows["Etc/UTC"]["region"], rows["Etc/UTC"]["city"]) == ("UTC", "UTC")
        assert rows["Etc/UTC"]["abbreviation"] == "UTC"

    def test_nested_city_and_sort(self) -> None:
        rows = tz.zone_rows(NOW)
        ba = next(r for r in rows if r["zone"] == "America/Argentina/Buenos_Aires")
        assert (ba["region"], ba["city"]) == ("America", "Buenos Aires")
        keys = [(r["region"], r["city"]) for r in rows]
        assert keys == sorted(keys)


def test_module_is_a_leaf() -> None:
    src = Path(tz.__file__).read_text()
    for node in ast.parse(src).body:
        mods = []
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [node.module or ""]
        for m in mods:
            assert not m.startswith(("the_one.agent", "the_one.tools", "the_one.interfaces")), m
