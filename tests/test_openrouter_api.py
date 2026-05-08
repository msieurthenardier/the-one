"""Tests for openrouter_api helper module."""

from __future__ import annotations

import time

import httpx
import pytest

from the_one.llm import openrouter_api
from the_one.llm.openrouter_api import OpenRouterModelEntry


@pytest.fixture(autouse=True)
def _clear_cache():
    """Each test gets a clean module-level cache."""
    openrouter_api._models_cache.clear()
    yield
    openrouter_api._models_cache.clear()


def _mock_async_client(monkeypatch, handler):
    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)


@pytest.mark.asyncio
class TestListModels:
    async def test_returns_data_array(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [{"id": "m1"}, {"id": "m2"}]})

        _mock_async_client(monkeypatch, handler)

        result = await openrouter_api.list_models("https://openrouter.ai/api/v1", "k1")
        # list_models now returns OpenRouterModelEntry objects (typed shape).
        assert all(isinstance(entry, OpenRouterModelEntry) for entry in result)
        assert [entry.id for entry in result] == ["m1", "m2"]

    async def test_entry_attribute_access(self, monkeypatch):
        """The returned entries expose attribute access — ``entry.id``,
        ``entry.name``, ``entry.supported_parameters`` — matching the
        Studio capability-chip / list-models renderer's expectations."""

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "m1",
                            "name": "Model One",
                            "supported_parameters": ["tools"],
                            "context_length": 128_000,
                            "description": "A model.",
                        }
                    ]
                },
            )

        _mock_async_client(monkeypatch, handler)

        result = await openrouter_api.list_models("https://openrouter.ai/api/v1", "k")
        entry = result[0]
        assert entry.id == "m1"
        assert entry.name == "Model One"
        assert entry.supported_parameters == ["tools"]
        assert entry.context_length == 128_000
        assert entry.description == "A model."

    async def test_entry_forward_compat_extra_fields(self, monkeypatch):
        """``OpenRouterModelEntry`` is ``extra='allow'``; an unknown field
        from a future OpenRouter response shape must NOT raise."""

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"data": [{"id": "m1", "future_field": "value"}]},
            )

        _mock_async_client(monkeypatch, handler)

        result = await openrouter_api.list_models("https://openrouter.ai/api/v1", "k")
        assert result[0].id == "m1"
        # Extra-allowed fields are accessible via model_extra in pydantic v2.
        assert result[0].model_extra["future_field"] == "value"

    async def test_entry_optional_fields_default_to_none(self, monkeypatch):
        """A minimal payload (``id`` only) must validate with ``name`` /
        ``supported_parameters`` / ``context_length`` defaulted, and
        ``description`` empty-string."""

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [{"id": "m1"}]})

        _mock_async_client(monkeypatch, handler)

        result = await openrouter_api.list_models("https://openrouter.ai/api/v1", "k")
        entry = result[0]
        assert entry.id == "m1"
        assert entry.name is None
        assert entry.supported_parameters is None
        assert entry.context_length is None
        assert entry.description == ""

    async def test_sends_authorization_when_key_set(self, monkeypatch):
        captured: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(200, json={"data": []})

        _mock_async_client(monkeypatch, handler)

        await openrouter_api.list_models("https://openrouter.ai/api/v1", "sk-123")
        assert captured[0].headers.get("authorization") == "Bearer sk-123"

    async def test_no_authorization_when_key_empty(self, monkeypatch):
        captured: list[httpx.Request] = []

        def handler(req: httpx.Request) -> httpx.Response:
            captured.append(req)
            return httpx.Response(200, json={"data": []})

        _mock_async_client(monkeypatch, handler)

        await openrouter_api.list_models("https://openrouter.ai/api/v1", "")
        assert "authorization" not in {k.lower() for k in captured[0].headers.keys()}

    async def test_raises_on_500(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        _mock_async_client(monkeypatch, handler)

        with pytest.raises(httpx.HTTPStatusError):
            await openrouter_api.list_models("https://openrouter.ai/api/v1", "k1")

    async def test_raises_on_network_error(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("nope")

        _mock_async_client(monkeypatch, handler)

        with pytest.raises(httpx.RequestError):
            await openrouter_api.list_models("https://openrouter.ai/api/v1", "k1")

    async def test_cache_keyed_on_base_url_and_api_key_hash(self, monkeypatch):
        call_count = {"n": 0}

        def handler(req: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(200, json={"data": [{"id": "m"}]})

        _mock_async_client(monkeypatch, handler)

        # Two calls with the same (base_url, api_key) — only ONE upstream fetch
        await openrouter_api.list_models("https://openrouter.ai/api/v1", "key-A")
        await openrouter_api.list_models("https://openrouter.ai/api/v1", "key-A")
        assert call_count["n"] == 1

        # Different api_key on same base_url — separate cache entry
        await openrouter_api.list_models("https://openrouter.ai/api/v1", "key-B")
        assert call_count["n"] == 2

    async def test_cache_ttl_expiry(self, monkeypatch):
        call_count = {"n": 0}

        def handler(req: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            return httpx.Response(200, json={"data": []})

        _mock_async_client(monkeypatch, handler)

        await openrouter_api.list_models("https://openrouter.ai/api/v1", "k")
        for k in list(openrouter_api._models_cache.keys()):
            payload, _ = openrouter_api._models_cache[k]
            openrouter_api._models_cache[k] = (payload, time.time() - 999)

        await openrouter_api.list_models("https://openrouter.ai/api/v1", "k")
        assert call_count["n"] == 2


@pytest.mark.asyncio
class TestVerifyKey:
    async def test_returns_dict_on_success(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {"label": "test"}})

        _mock_async_client(monkeypatch, handler)

        result = await openrouter_api.verify_key("https://openrouter.ai/api/v1", "good")
        assert result == {"data": {"label": "test"}}

    async def test_raises_on_401(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "Invalid"}})

        _mock_async_client(monkeypatch, handler)

        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            await openrouter_api.verify_key("https://openrouter.ai/api/v1", "bad")
        assert excinfo.value.response.status_code == 401


@pytest.mark.asyncio
class TestGetModelCapabilities:
    async def test_returns_supported_parameters_as_frozenset(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "m1", "supported_parameters": ["tools", "reasoning"]},
                    ]
                },
            )

        _mock_async_client(monkeypatch, handler)

        caps = await openrouter_api.get_model_capabilities(
            "https://openrouter.ai/api/v1", "k", "m1"
        )
        assert caps == frozenset({"tools", "reasoning"})

    async def test_fail_open_on_fetch_error(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        _mock_async_client(monkeypatch, handler)

        caps = await openrouter_api.get_model_capabilities(
            "https://openrouter.ai/api/v1", "k", "m1"
        )
        assert caps is None

    async def test_fail_open_on_missing_model(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [{"id": "other"}]})

        _mock_async_client(monkeypatch, handler)

        caps = await openrouter_api.get_model_capabilities(
            "https://openrouter.ai/api/v1", "k", "missing"
        )
        assert caps is None

    async def test_fail_open_on_missing_supported_parameters(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [{"id": "m1"}]})

        _mock_async_client(monkeypatch, handler)

        caps = await openrouter_api.get_model_capabilities(
            "https://openrouter.ai/api/v1", "k", "m1"
        )
        assert caps is None

    async def test_fail_open_on_empty_supported_parameters(self, monkeypatch):
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"data": [{"id": "m1", "supported_parameters": []}]},
            )

        _mock_async_client(monkeypatch, handler)

        caps = await openrouter_api.get_model_capabilities(
            "https://openrouter.ai/api/v1", "k", "m1"
        )
        assert caps is None


@pytest.mark.asyncio
class TestGetCapabilitiesLogging:
    """Fail-open is correct for the UI (no chip rendered) but the
    swallowed exception MUST be logged server-side so contract
    violations and persistent auth failures are observable."""

    async def test_logs_warning_on_fetch_failure(self, monkeypatch, caplog):
        import logging

        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("network down")

        _mock_async_client(monkeypatch, handler)
        caplog.set_level(logging.WARNING, logger="the_one.llm.openrouter_api")

        caps = await openrouter_api.get_model_capabilities(
            "https://openrouter.ai/api/v1", "k", "m1"
        )
        assert caps is None
        assert any(
            "get_model_capabilities failed" in rec.message
            for rec in caplog.records
        )

    async def test_logs_warning_on_value_error(self, monkeypatch, caplog):
        import logging

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"oops": "bad shape"})

        _mock_async_client(monkeypatch, handler)
        caplog.set_level(logging.WARNING, logger="the_one.llm.openrouter_api")

        caps = await openrouter_api.get_model_capabilities(
            "https://openrouter.ai/api/v1", "k", "m1"
        )
        assert caps is None
        assert any(
            "get_model_capabilities failed" in rec.message
            for rec in caplog.records
        )


@pytest.mark.asyncio
class TestTestSeamDevModeGate:
    """THE_ONE_OPENROUTER_TEST_MODELS_JSON is gated on settings.dev_mode.
    A stray export in production must NOT silently substitute scripted
    models for real ones."""

    async def test_seam_honored_when_dev_mode_true(self, monkeypatch):
        from the_one.config import settings

        monkeypatch.setattr(settings, "dev_mode", True)
        monkeypatch.setenv(
            "THE_ONE_OPENROUTER_TEST_MODELS_JSON",
            '[{"id": "fake/model", "supported_parameters": ["tools"]}]',
        )
        models = await openrouter_api.list_models(
            "https://openrouter.ai/api/v1", "k"
        )
        assert len(models) == 1 and models[0].id == "fake/model"

    async def test_seam_ignored_when_dev_mode_false(self, monkeypatch, caplog):
        import logging

        from the_one.config import settings

        monkeypatch.setattr(settings, "dev_mode", False)
        monkeypatch.setenv(
            "THE_ONE_OPENROUTER_TEST_MODELS_JSON",
            '[{"id": "fake/model"}]',
        )

        # Stub the real network so the post-seam fetch is deterministic.
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [{"id": "real/model"}]})

        _mock_async_client(monkeypatch, handler)
        caplog.set_level(logging.WARNING, logger="the_one.llm.openrouter_api")

        models = await openrouter_api.list_models(
            "https://openrouter.ai/api/v1", "k"
        )
        # Real fetch wins — fake/model from env was ignored.
        assert len(models) == 1 and models[0].id == "real/model"
        # Operator gets a warning about the stray env var.
        assert any(
            "test seam is ignored" in rec.message for rec in caplog.records
        )
