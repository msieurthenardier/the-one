"""Tests for the runtime model-catalog refresh loop (M16 F05 L02).

Covers:
- Cache preferred over seed when cache exists and is valid.
- Corrupt cache falls back to seed and logs a WARN.
- Atomic write produces a valid cache with ``fetched_at``.
- ``_refresh_due`` returns correct values for fresh / stale / absent cache.
- Offline refresh (httpx raises) returns False and leaves the cache intact.
- Seed-coverage write guard: a payload missing a seed pair → no write, False.
- Post-refresh invalidation reflects new values from the cache.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import the_one.llm.model_catalog as mod
from the_one.llm.model_catalog import (
    _refresh_due,
    _reset_for_tests,
    context_window_for,
    invalidate,
    refresh_catalog_cache,
)

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

# A minimal valid models.dev-style payload (list shape) that covers all pairs
# in the bundled seed (openai + anthropic models).
_SEED_PROVIDERS: dict[str, dict[str, int]] = {}


def _get_seed_providers() -> dict[str, dict[str, int]]:
    """Load the bundled seed's providers section (cached after first call)."""
    global _SEED_PROVIDERS
    if not _SEED_PROVIDERS:
        import importlib.resources

        package = importlib.resources.files("the_one.llm")
        seed_file = package.joinpath("data").joinpath("model_catalog.json")
        data = json.loads(seed_file.read_text(encoding="utf-8"))
        _SEED_PROVIDERS = data.get("providers", {})
    return _SEED_PROVIDERS


def _make_full_payload() -> list[dict]:
    """Build a models.dev list-shape payload that covers all seed pairs."""
    entries = []
    for provider, models in _get_seed_providers().items():
        for model_id, ctx in models.items():
            entries.append({"id": model_id, "provider": provider, "context": ctx})
    return entries


def _make_mock_response(payload) -> MagicMock:
    """Return a mock httpx response that yields ``payload`` from ``.json()``."""
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture(autouse=True)
def reset_catalog_state():
    """Force a fresh catalog load for each test and restore afterward."""
    _reset_for_tests(None)
    yield
    _reset_for_tests(None)


# ---------------------------------------------------------------------------
# Cache-preferred-over-seed
# ---------------------------------------------------------------------------


class TestCachePreferredOverSeed:
    def test_cache_preferred_over_seed(self, tmp_path, monkeypatch):
        """When a valid cache exists it is loaded instead of the bundled seed."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        # Write a cache with a higher context window for a known model.
        cache = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "models.dev",
            "providers": {
                "openai": {"gpt-4o": 999_999},
                "anthropic": {"claude-sonnet-4-6": 2_000_000},
            },
        }
        (tmp_path / "model_catalog.json").write_text(
            json.dumps(cache), encoding="utf-8"
        )
        _reset_for_tests(None)  # ensure fresh load from the new cache

        assert context_window_for("openai", "gpt-4o") == 999_999
        assert context_window_for("anthropic", "claude-sonnet-4-6") == 2_000_000

    def test_seed_used_when_no_cache(self, tmp_path, monkeypatch):
        """When the cache is absent the bundled seed drives lookups."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        # tmp_path is empty — no cache.
        _reset_for_tests(None)

        result = context_window_for("openai", "gpt-4o")
        assert result == 128_000  # seed value


# ---------------------------------------------------------------------------
# Corrupt cache falls back to seed + WARN
# ---------------------------------------------------------------------------


class TestCorruptCacheFallback:
    def test_corrupt_cache_falls_back_to_seed(self, tmp_path, monkeypatch, caplog):
        """A corrupt cache logs a WARN and falls back to the bundled seed."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        (tmp_path / "model_catalog.json").write_text(
            "not valid json {{{{", encoding="utf-8"
        )
        _reset_for_tests(None)

        with caplog.at_level(logging.WARNING, logger="the_one.llm.model_catalog"):
            result = context_window_for("openai", "gpt-4o")

        # Lookup still works (seed fallback)
        assert result == 128_000
        # A WARN was logged
        warn_messages = [
            r.message
            for r in caplog.records
            if r.levelno >= logging.WARNING and "corrupt" in r.message.lower()
        ]
        assert warn_messages, (
            f"Expected a corrupt-cache WARN; got records: {[r.message for r in caplog.records]}"
        )

    def test_corrupt_cache_root_not_dict_falls_back(self, tmp_path, monkeypatch, caplog):
        """A cache whose root is a JSON array (not a dict) falls back to the seed."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        (tmp_path / "model_catalog.json").write_text(
            json.dumps([1, 2, 3]), encoding="utf-8"
        )
        _reset_for_tests(None)

        with caplog.at_level(logging.WARNING, logger="the_one.llm.model_catalog"):
            result = context_window_for("openai", "gpt-4o")

        assert result == 128_000
        assert any(
            r.levelno >= logging.WARNING for r in caplog.records
        ), "Expected WARN log for non-dict cache root"


# ---------------------------------------------------------------------------
# Atomic write + fetched_at
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    @pytest.mark.asyncio
    async def test_atomic_write_produces_valid_cache(self, tmp_path, monkeypatch):
        """refresh_catalog_cache writes a valid cache with fetched_at."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        payload = _make_full_payload()
        mock_resp = _make_mock_response(payload)
        mock_get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient.get", mock_get):
            result = await refresh_catalog_cache()

        assert result is True
        cache_path = tmp_path / "model_catalog.json"
        assert cache_path.exists()
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert "fetched_at" in data
        assert "source" in data
        assert data["source"] == "models.dev"
        assert "providers" in data
        assert isinstance(data["providers"], dict)
        # No leftover .tmp file
        assert not (tmp_path / "model_catalog.tmp").exists()

    @pytest.mark.asyncio
    async def test_atomic_write_no_tmp_file_after_success(self, tmp_path, monkeypatch):
        """The .tmp file is cleaned up (renamed) after a successful write."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        payload = _make_full_payload()
        mock_resp = _make_mock_response(payload)
        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            await refresh_catalog_cache()

        assert not (tmp_path / "model_catalog.tmp").exists()
        assert (tmp_path / "model_catalog.json").exists()

    @pytest.mark.asyncio
    async def test_fetched_at_is_utc_parseable(self, tmp_path, monkeypatch):
        """The fetched_at stamp is a parseable ISO-8601 UTC datetime."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        payload = _make_full_payload()
        mock_resp = _make_mock_response(payload)
        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            await refresh_catalog_cache()

        data = json.loads((tmp_path / "model_catalog.json").read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(data["fetched_at"])
        # Should be recent (within the last 60 seconds)
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
        assert 0 <= age < 60


# ---------------------------------------------------------------------------
# _refresh_due logic
# ---------------------------------------------------------------------------


class TestRefreshDue:
    def test_due_when_cache_absent(self, tmp_path, monkeypatch):
        """No cache → always due."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        assert _refresh_due() is True

    def test_due_when_cache_no_fetched_at(self, tmp_path, monkeypatch):
        """Cache without fetched_at (e.g. seed copy) → due."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        (tmp_path / "model_catalog.json").write_text(
            json.dumps({"generated_at": "2026-01-01", "providers": {}}),
            encoding="utf-8",
        )
        assert _refresh_due() is True

    def test_due_when_cache_stale(self, tmp_path, monkeypatch):
        """Cache older than 24h → due."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        stale_time = datetime.now(timezone.utc) - timedelta(hours=25)
        (tmp_path / "model_catalog.json").write_text(
            json.dumps({"fetched_at": stale_time.isoformat(), "providers": {}}),
            encoding="utf-8",
        )
        assert _refresh_due() is True

    def test_not_due_when_cache_fresh(self, tmp_path, monkeypatch):
        """Cache from 1 hour ago → not due."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        fresh_time = datetime.now(timezone.utc) - timedelta(hours=1)
        (tmp_path / "model_catalog.json").write_text(
            json.dumps({"fetched_at": fresh_time.isoformat(), "providers": {}}),
            encoding="utf-8",
        )
        assert _refresh_due() is False

    def test_due_when_cache_corrupt(self, tmp_path, monkeypatch):
        """Corrupt cache JSON → due (treat as absent)."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        (tmp_path / "model_catalog.json").write_text(
            "{{bad json}}", encoding="utf-8"
        )
        assert _refresh_due() is True


# ---------------------------------------------------------------------------
# Offline refresh (httpx raises)
# ---------------------------------------------------------------------------


class TestOfflineRefresh:
    @pytest.mark.asyncio
    async def test_offline_refresh_returns_false(self, tmp_path, monkeypatch):
        """When httpx raises, refresh_catalog_cache returns False (no crash)."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)

        import httpx

        with patch(
            "httpx.AsyncClient.get",
            AsyncMock(side_effect=httpx.ConnectError("unreachable")),
        ):
            result = await refresh_catalog_cache()

        assert result is False

    @pytest.mark.asyncio
    async def test_offline_refresh_leaves_existing_cache_intact(
        self, tmp_path, monkeypatch
    ):
        """When the network is down the existing cache file is not modified."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        # Write a pre-existing cache.
        original_cache = {
            "fetched_at": (
                datetime.now(timezone.utc) - timedelta(hours=1)
            ).isoformat(),
            "source": "models.dev",
            "providers": {"openai": {"gpt-4o": 128_000}},
        }
        cache_path = tmp_path / "model_catalog.json"
        cache_path.write_text(json.dumps(original_cache), encoding="utf-8")
        mtime_before = cache_path.stat().st_mtime

        import httpx

        with patch(
            "httpx.AsyncClient.get",
            AsyncMock(side_effect=httpx.ConnectError("unreachable")),
        ):
            await refresh_catalog_cache()

        assert cache_path.stat().st_mtime == mtime_before, (
            "Cache was modified despite network failure"
        )

    @pytest.mark.asyncio
    async def test_offline_refresh_logs_warning(self, tmp_path, monkeypatch, caplog):
        """Offline failure is logged at WARNING level, not silently swallowed."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)

        import httpx

        with caplog.at_level(logging.WARNING, logger="the_one.llm.model_catalog"):
            with patch(
                "httpx.AsyncClient.get",
                AsyncMock(side_effect=httpx.ConnectError("unreachable")),
            ):
                await refresh_catalog_cache()

        assert any(
            r.levelno >= logging.WARNING for r in caplog.records
        ), "Expected a WARNING on fetch failure"


# ---------------------------------------------------------------------------
# Seed-coverage write guard
# ---------------------------------------------------------------------------


class TestSeedCoverageGuard:
    @pytest.mark.asyncio
    async def test_guard_blocks_write_when_payload_missing_seed_pair(
        self, tmp_path, monkeypatch
    ):
        """A payload missing a seed (provider, model) pair must not be written."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)

        # Build a payload that only has ONE anthropic model — definitely missing
        # some seed anthropic entries.
        partial_payload = [
            {"id": "gpt-4o", "provider": "openai", "context": 128_000},
            # Only one anthropic model, seed has 8 anthropic entries.
            {"id": "claude-sonnet-4-6", "provider": "anthropic", "context": 1_000_000},
        ]
        mock_resp = _make_mock_response(partial_payload)

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            result = await refresh_catalog_cache()

        assert result is False
        assert not (tmp_path / "model_catalog.json").exists()

    @pytest.mark.asyncio
    async def test_guard_allows_write_when_full_coverage(
        self, tmp_path, monkeypatch
    ):
        """A payload that covers all seed pairs is written successfully."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        payload = _make_full_payload()
        mock_resp = _make_mock_response(payload)

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            result = await refresh_catalog_cache()

        assert result is True
        assert (tmp_path / "model_catalog.json").exists()

    @pytest.mark.asyncio
    async def test_guard_blocks_empty_payload(self, tmp_path, monkeypatch):
        """An empty payload (no models) must not be written."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        mock_resp = _make_mock_response([])  # empty list

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            result = await refresh_catalog_cache()

        assert result is False
        assert not (tmp_path / "model_catalog.json").exists()

    @pytest.mark.asyncio
    async def test_guard_blocks_garbage_response(self, tmp_path, monkeypatch):
        """A garbage payload (wrong shape) must not overwrite the cache."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        mock_resp = _make_mock_response({"something": "totally wrong"})

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            result = await refresh_catalog_cache()

        assert result is False
        assert not (tmp_path / "model_catalog.json").exists()

    @pytest.mark.asyncio
    async def test_existing_cache_intact_after_guard_blocks(
        self, tmp_path, monkeypatch
    ):
        """When the guard rejects a new fetch the existing cache is not modified."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        # Pre-existing cache with a special window value.
        original_cache = {
            "fetched_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            "source": "models.dev",
            "providers": {"openai": {"gpt-4o": 222_222}},
        }
        cache_path = tmp_path / "model_catalog.json"
        cache_path.write_text(json.dumps(original_cache), encoding="utf-8")
        mtime_before = cache_path.stat().st_mtime

        # Payload that fails the coverage guard.
        partial_payload = [{"id": "gpt-4o", "provider": "openai", "context": 128_000}]
        mock_resp = _make_mock_response(partial_payload)

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            result = await refresh_catalog_cache()

        assert result is False
        assert cache_path.stat().st_mtime == mtime_before


# ---------------------------------------------------------------------------
# Post-refresh invalidation
# ---------------------------------------------------------------------------


class TestPostRefreshInvalidation:
    @pytest.mark.asyncio
    async def test_invalidation_reflects_cache_after_refresh(
        self, tmp_path, monkeypatch
    ):
        """After refresh the memo is cleared and context_window_for reads the cache."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)

        # Seed value for gpt-4o is 128_000.  Write a cache with 999_999.
        # Start by loading from seed so the memo has the seed value.
        _reset_for_tests(None)
        before = context_window_for("openai", "gpt-4o")
        assert before == 128_000

        # Now refresh with a payload that includes 999_999 for gpt-4o (+ all seed pairs).
        entries = _make_full_payload()
        # Override gpt-4o in the payload with a higher window.
        entries = [
            e if not (e.get("id") == "gpt-4o" and e.get("provider") == "openai")
            else {**e, "context": 999_999}
            for e in entries
        ]
        mock_resp = _make_mock_response(entries)
        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            result = await refresh_catalog_cache()
        assert result is True

        # After refresh, the memo should be invalidated; next call re-reads cache.
        after = context_window_for("openai", "gpt-4o")
        assert after == 999_999, f"Expected 999_999 from cache; got {after}"

    def test_invalidate_clears_memo(self, tmp_path, monkeypatch):
        """invalidate() sets _catalog to None so the next lookup re-loads."""
        monkeypatch.setattr(mod.settings, "data_dir", tmp_path)
        # Prime the memo with the seed.
        _ = context_window_for("openai", "gpt-4o")
        assert mod._catalog is not None

        invalidate()
        assert mod._catalog is None
