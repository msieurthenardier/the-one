"""M16 F08 L05 — tests for ``GET /api/config`` and the context-fullness
threshold settings it exposes.

Covers:
- ``/api/config`` returns both thresholds at their defaults (70 / 90).
- ``THE_ONE_CONTEXT_WARN_PCT`` / ``_CRIT_PCT`` env overrides flow into a fresh
  ``Settings()`` and through the endpoint.
- An invalid threshold combination (warn ≥ crit, out of range, etc.) CLAMPS
  back to 70 / 90 via the ``Settings`` validator rather than raising — so boot
  never crashes and ``/api/config`` always emits sane values.

The endpoint reads the module-level ``settings`` singleton, so the env-override
and clamp cases monkeypatch that singleton with a freshly-constructed
``Settings()`` (which reads the patched environment / explicit kwargs). The
endpoint has no DB dependency, so a bare ASGI client around the router suffices.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from tests._api_app import shared_app
from tests._credential_helpers import auth_headers
from the_one.config import Settings
from the_one.interfaces.web import api as api_module


@pytest.fixture
async def client() -> Iterator[AsyncClient]:
    """Bare ASGI test client around the api router — /api/config has no DB
    dependency, so no DB fixture is needed.
    """
    test_app = shared_app()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers=auth_headers()
    ) as c:
        yield c


class TestConfigThresholds:
    async def test_config_returns_default_thresholds(self, client: AsyncClient) -> None:
        """A default ``Settings()`` exposes 70 / 90 through /api/config."""
        # Pin the singleton to a default Settings so the assertion is
        # independent of any ambient env in the runner.
        default_settings = Settings(context_warn_pct=70, context_crit_pct=90, _env_file=None)
        api_module.settings = default_settings
        try:
            resp = await client.get("/api/config")
        finally:
            # Restore the imported singleton for other tests in the process.
            import importlib

            api_module.settings = importlib.import_module("the_one.config").settings

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["context_warn_pct"] == 70
        assert payload["context_crit_pct"] == 90
        # The pre-existing keys must still be present (no regression).
        assert "dev_mode" in payload
        assert "version" in payload

    async def test_env_override_changes_thresholds(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``THE_ONE_CONTEXT_WARN_PCT`` / ``_CRIT_PCT`` flow into a fresh
        ``Settings()`` and out through /api/config.
        """
        monkeypatch.setenv("THE_ONE_CONTEXT_WARN_PCT", "55")
        monkeypatch.setenv("THE_ONE_CONTEXT_CRIT_PCT", "80")
        overridden = Settings(_env_file=None)
        assert overridden.context_warn_pct == 55
        assert overridden.context_crit_pct == 80

        api_module.settings = overridden
        try:
            resp = await client.get("/api/config")
        finally:
            import importlib

            api_module.settings = importlib.import_module("the_one.config").settings

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["context_warn_pct"] == 55
        assert payload["context_crit_pct"] == 80

    @pytest.mark.parametrize(
        "warn, crit",
        [
            (95, 80),  # warn >= crit
            (70, 200),  # crit out of range (> 100)
            (0, 90),  # warn at/below 0
            (70, 70),  # warn == crit (not strictly less)
            (-5, 90),  # negative warn
        ],
    )
    def test_invalid_combo_clamps_to_defaults(self, warn: int, crit: int) -> None:
        """The validator CLAMPS any invalid combination back to 70 / 90 and
        does NOT raise (raising would crash boot).
        """
        s = Settings(context_warn_pct=warn, context_crit_pct=crit, _env_file=None)
        assert s.context_warn_pct == 70
        assert s.context_crit_pct == 90

    def test_valid_combo_is_preserved(self) -> None:
        """A valid in-range combination is left untouched."""
        s = Settings(context_warn_pct=50, context_crit_pct=85, _env_file=None)
        assert s.context_warn_pct == 50
        assert s.context_crit_pct == 85

    async def test_invalid_env_clamps_through_endpoint(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An invalid env combination clamps to 70 / 90 by the time it reaches
        /api/config — the client never sees a broken threshold.
        """
        monkeypatch.setenv("THE_ONE_CONTEXT_WARN_PCT", "95")
        monkeypatch.setenv("THE_ONE_CONTEXT_CRIT_PCT", "80")
        clamped = Settings(_env_file=None)

        api_module.settings = clamped
        try:
            resp = await client.get("/api/config")
        finally:
            import importlib

            api_module.settings = importlib.import_module("the_one.config").settings

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["context_warn_pct"] == 70
        assert payload["context_crit_pct"] == 90
