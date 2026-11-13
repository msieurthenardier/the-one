"""The fake-platforms seam: the pure URL check and the lifespan wiring (M35 F3 L6)."""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from pathlib import Path

import pytest

from the_one.config import Settings
from the_one.connectors.fake_platforms_seam import FakeUrls, Refused, fake_platform_urls

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    ("raw", "host"),
    [
        ("http://127.0.0.1:8490", "127.0.0.1:8490"),
        ("http://127.0.0.1:8490/", "127.0.0.1:8490"),
        ("  http://127.0.0.1:8490  ", "127.0.0.1:8490"),
        ("http://[::1]:8490", "[::1]:8490"),
    ],
)
def test_accepts_loopback_literals(raw, host):
    got = fake_platform_urls(raw, dev_mode=True)
    assert got == FakeUrls(
        discord_rest=f"http://{host}/discord/api/v10",
        discord_gateway=f"ws://{host}/discord/gateway",
        telegram_base=f"http://{host}/telegram",
    )


@pytest.mark.parametrize(
    "raw",
    [
        "http://localhost:8490",
        "http://10.0.0.1:8490",
        "http://example.com:8490",
        "https://127.0.0.1:8490",
        "http://127.0.0.1",
        "http://user@127.0.0.1:8490",
        "http://user:secret@127.0.0.1:8490",
        "http://127.0.0.1:8490/x",
        "http://127.0.0.1:8490?q=1",
        "http://127.0.0.1:8490/#f",
        "ftp://127.0.0.1:8490",
        "http://[::1",
        "http://[::ffff:127.0.0.1]:8490",
        "http://127.0.0.1:notaport",
        "x" * 10000,
        "garbage",
        123,
        b"http://127.0.0.1:8490",
        ["http://127.0.0.1:8490"],
    ],
)
def test_refuses(raw):
    got = fake_platform_urls(raw, dev_mode=True)
    assert isinstance(got, Refused)
    assert got.reason


@pytest.mark.parametrize("raw", [None, "", "   ", "\n"])
def test_unset_is_none(raw):
    assert fake_platform_urls(raw, dev_mode=True) is None


@pytest.mark.parametrize("raw", ["http://127.0.0.1:8490", "http://localhost:1", "junk", 5])
def test_dev_mode_off_is_none(raw):
    assert fake_platform_urls(raw, dev_mode=False) is None


def test_refused_carries_scheme_and_host_only():
    got = fake_platform_urls("http://user:secret@example.com:8490/p?q=1", dev_mode=True)
    assert isinstance(got, Refused)
    assert got.host == "example.com" and got.scheme == "http"
    assert "secret" not in repr(got)


# ---- lifespan -------------------------------------------------------------


async def _run_lifespan(tmp_path, monkeypatch, *, dev_mode, value, caplog):
    from tests._schema_template import copy_template
    from the_one.config import settings
    from the_one.connectors import registry as plugin_registry
    from the_one.db import _write_lock
    from the_one.db import connection as db_connection
    from the_one.interfaces.web.app import app, lifespan
    from the_one.sessions._locks import clear_locks_for_test

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "dev_mode", dev_mode)
    if value is None:
        monkeypatch.delenv("THE_ONE_FAKE_PLATFORMS_URL", raising=False)
    else:
        monkeypatch.setenv("THE_ONE_FAKE_PLATFORMS_URL", value)
    _write_lock.reset_for_test()
    clear_locks_for_test()
    copy_template(settings.db_path)
    monkeypatch.setattr(db_connection, "_connection", None)
    plugin_registry.clear_for_test()

    seen: dict = {}
    ready, stop = asyncio.Event(), asyncio.Event()

    async def _serve() -> None:
        async with lifespan(app):
            seen["discord"] = plugin_registry.get_plugin("discord")
            seen["telegram"] = plugin_registry.get_plugin("telegram")
            ready.set()
            await stop.wait()

    with caplog.at_level(logging.INFO, logger="the_one"):
        task = asyncio.create_task(_serve())
        await asyncio.wait_for(ready.wait(), 30)
        stop.set()
        await asyncio.wait_for(task, 30)
    return seen


def _seam_records(caplog):
    return [
        r
        for r in caplog.records
        if "fake platforms" in r.getMessage() or "FAKE_PLATFORMS" in r.getMessage()
    ]


REAL_DISCORD = "https://discord.com/api/v10"
REAL_TELEGRAM = "https://api.telegram.org"


async def test_lifespan_set_points_plugins_at_the_fake(tmp_path, monkeypatch, caplog):
    seen = await _run_lifespan(
        tmp_path, monkeypatch, dev_mode=True, value="http://127.0.0.1:8493", caplog=caplog
    )
    assert seen["discord"]._rest_base_url == "http://127.0.0.1:8493/discord/api/v10"
    assert seen["discord"]._gateway_url_override == "ws://127.0.0.1:8493/discord/gateway"
    assert seen["telegram"]._base_url == "http://127.0.0.1:8493/telegram"
    recs = _seam_records(caplog)
    assert len(recs) == 1
    assert recs[0].levelno == logging.WARNING
    assert "connectors use the fake platforms at http://127.0.0.1:8493" in recs[0].getMessage()


async def test_lifespan_refused_uses_defaults_and_logs_no_secret(tmp_path, monkeypatch, caplog):
    raw = "http://user:secret@127.0.0.1:8493"
    seen = await _run_lifespan(tmp_path, monkeypatch, dev_mode=True, value=raw, caplog=caplog)
    assert seen["discord"]._rest_base_url == REAL_DISCORD
    assert seen["discord"]._gateway_url_override is None
    assert seen["telegram"]._base_url == REAL_TELEGRAM
    recs = _seam_records(caplog)
    assert len(recs) == 1 and recs[0].levelno == logging.ERROR
    blob = " ".join(r.getMessage() + str(r.args) + (r.exc_text or "") for r in caplog.records)
    for needle in ("user", "secret", raw):
        assert needle not in " ".join(r.getMessage() for r in recs), needle
    assert "secret" not in blob


async def test_lifespan_localhost_is_refused(tmp_path, monkeypatch, caplog):
    seen = await _run_lifespan(
        tmp_path, monkeypatch, dev_mode=True, value="http://localhost:8493", caplog=caplog
    )
    assert seen["telegram"]._base_url == REAL_TELEGRAM
    assert seen["discord"]._rest_base_url == REAL_DISCORD


async def test_lifespan_dev_mode_off_ignores_the_variable(tmp_path, monkeypatch, caplog):
    seen = await _run_lifespan(
        tmp_path, monkeypatch, dev_mode=False, value="http://127.0.0.1:8493", caplog=caplog
    )
    assert seen["discord"]._rest_base_url == REAL_DISCORD
    assert seen["discord"]._gateway_url_override is None
    assert seen["telegram"]._base_url == REAL_TELEGRAM
    assert _seam_records(caplog) == []


async def test_lifespan_unset_uses_defaults(tmp_path, monkeypatch, caplog):
    seen = await _run_lifespan(tmp_path, monkeypatch, dev_mode=True, value=None, caplog=caplog)
    assert seen["discord"]._rest_base_url == REAL_DISCORD
    assert seen["telegram"]._base_url == REAL_TELEGRAM
    assert _seam_records(caplog) == []


async def test_lifespan_empty_is_silent(tmp_path, monkeypatch, caplog):
    seen = await _run_lifespan(tmp_path, monkeypatch, dev_mode=True, value="", caplog=caplog)
    assert seen["telegram"]._base_url == REAL_TELEGRAM
    assert _seam_records(caplog) == []


# ---- isolation ------------------------------------------------------------


def test_not_a_settings_field_and_read_from_os_environ():
    assert "fake_platforms_url" not in Settings.model_fields
    from the_one.interfaces.web import app as appmod

    src = inspect.getsource(appmod.lifespan)
    assert 'os.environ.get("THE_ONE_FAKE_PLATFORMS_URL")' in src


def test_connector_packages_never_read_the_environment():
    for pkg in ("discord", "telegram"):
        for path in (ROOT / "the_one" / "connectors" / pkg).glob("*.py"):
            text = path.read_text()
            assert not re.search(r"os\.environ|getenv|environ\[", text), path
