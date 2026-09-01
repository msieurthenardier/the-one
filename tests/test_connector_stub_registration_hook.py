"""Tests for the dual-gated stub-registration lifespan startup hook
(design review Q1, resolved) in ``interfaces/web/app.py``. Mission 23
Flight 2 Leg 2.

Drives the real ``lifespan(app)`` context manager directly (mirrors
``tests/test_lifespan.py``'s pattern) rather than a full
``TestClient(app)`` HTTP round-trip — the hook's effect (a registry
mutation) is observable without ever making a request.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.usefixtures("reset_lifespan_singletons")


@pytest.fixture
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Mirrors ``tests/test_lifespan.py``'s fixture of the same name."""
    from the_one.config import settings
    from the_one.db import connection as db_connection

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(db_connection, "_connection", None)
    yield tmp_path
    monkeypatch.setattr(db_connection, "_connection", None)


async def test_registers_stub_when_both_gates_open(
    _isolated_data_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    from the_one.config import settings
    from the_one.connectors import registry
    from the_one.interfaces.web.app import app, lifespan

    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.setenv("THE_ONE_STUB_TEST_ENDPOINT", "1")
    registry.clear_for_test()

    async with lifespan(app):
        assert registry.get_plugin("stub") is not None

    # Symmetric teardown: unregistered again after shutdown.
    assert registry.get_plugin("stub") is None


async def test_unregistered_when_dev_mode_off(
    _isolated_data_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    from the_one.config import settings
    from the_one.connectors import registry
    from the_one.interfaces.web.app import app, lifespan

    monkeypatch.setattr(settings, "dev_mode", False)
    monkeypatch.setenv("THE_ONE_STUB_TEST_ENDPOINT", "1")
    registry.clear_for_test()

    async with lifespan(app):
        assert registry.get_plugin("stub") is None


async def test_unregistered_when_env_flag_absent(
    _isolated_data_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    from the_one.config import settings
    from the_one.connectors import registry
    from the_one.interfaces.web.app import app, lifespan

    monkeypatch.setattr(settings, "dev_mode", True)
    monkeypatch.delenv("THE_ONE_STUB_TEST_ENDPOINT", raising=False)
    registry.clear_for_test()

    async with lifespan(app):
        assert registry.get_plugin("stub") is None


async def test_does_not_clobber_a_test_registered_plugin(
    _isolated_data_dir, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plugin a TEST registered directly (bypassing the hook) is left
    alone by the symmetric-teardown flag — the flag is per-process-cycle,
    scoped to whether THIS hook run registered it."""
    from the_one.connectors import registry
    from the_one.connectors.stub import StubPlugin
    from the_one.interfaces.web.app import app, lifespan

    registry.clear_for_test()
    sentinel = StubPlugin()
    registry.register_for_test("stub", sentinel)

    monkeypatch.setattr("the_one.config.settings.dev_mode", False)
    monkeypatch.delenv("THE_ONE_STUB_TEST_ENDPOINT", raising=False)

    async with lifespan(app):
        # The hook's gate is closed, so it neither registers nor touches
        # the existing registration.
        assert registry.get_plugin("stub") is sentinel

    # Shutdown teardown only fires when `_stub_connector_registered_by_hook`
    # is True (it isn't here), so the test's own registration survives.
    assert registry.get_plugin("stub") is sentinel
    registry.clear_for_test()
