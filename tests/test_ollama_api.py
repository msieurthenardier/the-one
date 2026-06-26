"""Tests for the_one.llm.ollama_api — Ollama native REST API client."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from the_one.llm import ollama_api

BASE = "http://localhost:11434"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_client(response: MagicMock | None = None) -> tuple[MagicMock, AsyncMock]:
    """Return (patcher_target, mock_instance) for httpx.AsyncClient."""
    instance = AsyncMock()
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=False)
    if response is not None:
        instance.get = AsyncMock(return_value=response)
        instance.post = AsyncMock(return_value=response)
        instance.delete = AsyncMock(return_value=response)
        instance.request = AsyncMock(return_value=response)
    return instance


def _json_response(data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response with .json() and .raise_for_status()."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    if status_code >= 400:
        http_error = httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
        resp.raise_for_status.side_effect = http_error
    else:
        resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# strip_v1
# ---------------------------------------------------------------------------


class TestStripV1OllamaApi:
    def test_strips_trailing_slash(self) -> None:
        assert ollama_api.strip_v1("http://host:1234/") == "http://host:1234"

    def test_strips_v1_suffix(self) -> None:
        assert ollama_api.strip_v1("http://host:1234/v1") == "http://host:1234"

    def test_strips_v1_with_trailing_slash(self) -> None:
        assert ollama_api.strip_v1("http://host:1234/v1/") == "http://host:1234"

    def test_no_change_needed(self) -> None:
        assert ollama_api.strip_v1("http://host:1234") == "http://host:1234"


# ---------------------------------------------------------------------------
# _parse_parameter_size
# ---------------------------------------------------------------------------


class TestParseParameterSize:
    def test_billions(self) -> None:
        assert ollama_api._parse_parameter_size("7B") == 7_000_000_000

    def test_millions(self) -> None:
        assert ollama_api._parse_parameter_size("500M") == 500_000_000

    def test_float_value(self) -> None:
        assert ollama_api._parse_parameter_size("1.5B") == 1_500_000_000

    def test_none_input(self) -> None:
        assert ollama_api._parse_parameter_size(None) is None

    def test_empty_string(self) -> None:
        assert ollama_api._parse_parameter_size("") is None

    def test_bare_number(self) -> None:
        assert ollama_api._parse_parameter_size("7000000000") == 7_000_000_000


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------


class TestListModels:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        models = [
            {"name": "llama3:8b", "size": 4_000_000_000, "modified_at": "2025-01-01"},
            {"name": "qwen2.5:7b", "size": 3_500_000_000, "modified_at": "2025-01-02"},
        ]
        resp = _json_response({"models": models})
        instance = _mock_client(resp)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            result = await ollama_api.list_models(BASE)
        assert len(result) == 2
        assert result[0]["name"] == "llama3:8b"

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        resp = _json_response({"models": []})
        instance = _mock_client(resp)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            result = await ollama_api.list_models(BASE)
        assert result == []

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        instance = _mock_client()
        instance.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            with pytest.raises(ConnectionError, match="Cannot connect"):
                await ollama_api.list_models(BASE)

    @pytest.mark.asyncio
    async def test_timeout_error(self) -> None:
        instance = _mock_client()
        instance.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            with pytest.raises(ConnectionError, match="Timeout"):
                await ollama_api.list_models(BASE)

    @pytest.mark.asyncio
    async def test_strips_v1_from_url(self) -> None:
        resp = _json_response({"models": []})
        instance = _mock_client(resp)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            await ollama_api.list_models(f"{BASE}/v1")
        instance.get.assert_called_once_with(f"{BASE}/api/tags")


# ---------------------------------------------------------------------------
# list_running
# ---------------------------------------------------------------------------


class TestListRunning:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        models = [
            {
                "name": "llama3:8b",
                "size": 4_000_000_000,
                "size_vram": 4_000_000_000,
                "expires_at": "2025-01-01T12:00:00Z",
            }
        ]
        resp = _json_response({"models": models})
        instance = _mock_client(resp)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            result = await ollama_api.list_running(BASE)
        assert len(result) == 1
        assert result[0]["size_vram"] == 4_000_000_000

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        instance = _mock_client()
        instance.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            with pytest.raises(ConnectionError, match="Cannot connect"):
                await ollama_api.list_running(BASE)


# ---------------------------------------------------------------------------
# show_model
# ---------------------------------------------------------------------------


class TestShowModel:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        raw = {
            "modelfile": "...",
            "details": {
                "parameter_size": "7B",
                "quantization_level": "Q4_K_M",
            },
            "size": 4_000_000_000,
        }
        resp = _json_response(raw)
        instance = _mock_client(resp)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            result = await ollama_api.show_model(BASE, "llama3:8b")
        assert result["parameter_size"] == 7_000_000_000
        assert result["quantization_level"] == "Q4_K_M"
        assert result["size"] == 4_000_000_000

    @pytest.mark.asyncio
    async def test_missing_details(self) -> None:
        raw = {"size": 2_000_000_000}
        resp = _json_response(raw)
        instance = _mock_client(resp)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            result = await ollama_api.show_model(BASE, "tiny")
        assert result["parameter_size"] is None
        assert result["quantization_level"] is None

    @pytest.mark.asyncio
    async def test_404_raises_value_error(self) -> None:
        resp = _json_response({"error": "not found"}, status_code=404)
        instance = _mock_client(resp)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            with pytest.raises(ValueError, match="not found"):
                await ollama_api.show_model(BASE, "nonexistent")

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        instance = _mock_client()
        instance.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            with pytest.raises(ConnectionError, match="Cannot connect"):
                await ollama_api.show_model(BASE, "llama3:8b")


# ---------------------------------------------------------------------------
# pull_model
# ---------------------------------------------------------------------------


class TestPullModel:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        lines = [
            json.dumps({"status": "pulling manifest"}),
            json.dumps({"status": "downloading", "completed": 500, "total": 1000}),
            json.dumps({"status": "success"}),
        ]

        # Mock the streaming response
        stream_resp = AsyncMock()
        stream_resp.raise_for_status = MagicMock()
        stream_resp.aiter_lines = lambda: _async_iter(lines)

        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)

        # stream() returns an async context manager
        stream_cm = AsyncMock()
        stream_cm.__aenter__ = AsyncMock(return_value=stream_resp)
        stream_cm.__aexit__ = AsyncMock(return_value=False)
        instance.stream = MagicMock(return_value=stream_cm)

        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            results = []
            async for chunk in ollama_api.pull_model(BASE, "llama3:8b"):
                results.append(chunk)

        assert len(results) == 3
        assert results[0]["status"] == "pulling manifest"
        assert results[1]["completed"] == 500
        assert results[2]["status"] == "success"

    @pytest.mark.asyncio
    async def test_empty_lines_skipped(self) -> None:
        lines = ["", json.dumps({"status": "success"}), ""]

        stream_resp = AsyncMock()
        stream_resp.raise_for_status = MagicMock()
        stream_resp.aiter_lines = lambda: _async_iter(lines)

        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        stream_cm = AsyncMock()
        stream_cm.__aenter__ = AsyncMock(return_value=stream_resp)
        stream_cm.__aexit__ = AsyncMock(return_value=False)
        instance.stream = MagicMock(return_value=stream_cm)

        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            results = []
            async for chunk in ollama_api.pull_model(BASE, "test"):
                results.append(chunk)

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.stream = MagicMock(side_effect=httpx.ConnectError("refused"))

        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            with pytest.raises(ConnectionError, match="Cannot connect"):
                async for _ in ollama_api.pull_model(BASE, "model"):
                    pass

    @staticmethod
    def _stream_client_raising(status: int) -> AsyncMock:
        """Build a mocked AsyncClient whose streamed response fails
        ``raise_for_status()`` with the given HTTP status."""
        resp = MagicMock()
        resp.status_code = status
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
        stream_cm = AsyncMock()
        stream_cm.__aenter__ = AsyncMock(return_value=resp)
        stream_cm.__aexit__ = AsyncMock(return_value=False)
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.stream = MagicMock(return_value=stream_cm)
        return instance

    @pytest.mark.asyncio
    async def test_404_raises_value_error(self) -> None:
        """A 404 (unknown model) surfaces a clean ValueError, not a raw
        HTTPStatusError (issue #94 secondary)."""
        instance = self._stream_client_raising(404)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            with pytest.raises(ValueError, match="not found"):
                async for _ in ollama_api.pull_model(BASE, "nonexistent"):
                    pass

    @pytest.mark.asyncio
    async def test_http_error_raises_value_error(self) -> None:
        """A non-404 HTTP error surfaces a clean ValueError naming the status."""
        instance = self._stream_client_raising(500)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            with pytest.raises(ValueError, match="HTTP 500"):
                async for _ in ollama_api.pull_model(BASE, "boom"):
                    pass


# ---------------------------------------------------------------------------
# delete_model
# ---------------------------------------------------------------------------


class TestDeleteModel:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        resp = _json_response({})
        instance = _mock_client(resp)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            await ollama_api.delete_model(BASE, "old-model")
        instance.request.assert_called_once_with(
            "DELETE", f"{BASE}/api/delete", json={"model": "old-model"}
        )

    @pytest.mark.asyncio
    async def test_404_raises_value_error(self) -> None:
        resp = _json_response({"error": "not found"}, status_code=404)
        instance = _mock_client(resp)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            with pytest.raises(ValueError, match="not found"):
                await ollama_api.delete_model(BASE, "nonexistent")

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        instance = _mock_client()
        instance.request = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            with pytest.raises(ConnectionError):
                await ollama_api.delete_model(BASE, "model")


# ---------------------------------------------------------------------------
# load_model
# ---------------------------------------------------------------------------


class TestLoadModel:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        resp = _json_response({})
        instance = _mock_client(resp)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            await ollama_api.load_model(BASE, "llama3:8b")
        instance.post.assert_called_once_with(
            f"{BASE}/api/generate",
            json={"model": "llama3:8b", "keep_alive": "24h"},
        )

    @pytest.mark.asyncio
    async def test_custom_keep_alive(self) -> None:
        resp = _json_response({})
        instance = _mock_client(resp)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            await ollama_api.load_model(BASE, "llama3:8b", keep_alive="1h")
        instance.post.assert_called_once_with(
            f"{BASE}/api/generate",
            json={"model": "llama3:8b", "keep_alive": "1h"},
        )

    @pytest.mark.asyncio
    async def test_num_ctx_sets_options(self) -> None:
        # num_ctx is the runtime context window; it must go via the native
        # /api/generate ``options`` map (the /v1 endpoint ignores it).
        resp = _json_response({})
        instance = _mock_client(resp)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            await ollama_api.load_model(BASE, "llama3:8b", num_ctx=32_768)
        instance.post.assert_called_once_with(
            f"{BASE}/api/generate",
            json={"model": "llama3:8b", "keep_alive": "24h", "options": {"num_ctx": 32_768}},
        )

    @pytest.mark.asyncio
    async def test_num_ctx_none_omits_options(self) -> None:
        # The default (None) must leave the body exactly as before — no options.
        resp = _json_response({})
        instance = _mock_client(resp)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            await ollama_api.load_model(BASE, "llama3:8b", num_ctx=None)
        instance.post.assert_called_once_with(
            f"{BASE}/api/generate",
            json={"model": "llama3:8b", "keep_alive": "24h"},
        )

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        instance = _mock_client()
        instance.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            with pytest.raises(ConnectionError):
                await ollama_api.load_model(BASE, "model")

    @pytest.mark.asyncio
    async def test_timeout_error(self) -> None:
        instance = _mock_client()
        instance.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            with pytest.raises(ConnectionError, match="Timeout loading"):
                await ollama_api.load_model(BASE, "model")

    @pytest.mark.asyncio
    async def test_http_error_surfaces_ollama_message(self) -> None:
        # A 500 from /api/generate previously leaked the raw httpx
        # "Server error '500 ...'" string. Surface Ollama's own error body
        # (e.g. an out-of-memory message) so the operator knows why.
        resp = _json_response(
            {"error": "model requires more system memory than is available"},
            status_code=500,
        )
        instance = _mock_client(resp)
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            with pytest.raises(ValueError, match="more system memory"):
                await ollama_api.load_model(BASE, "huge-model")


# ---------------------------------------------------------------------------
# unload_model
# ---------------------------------------------------------------------------


class TestUnloadModel:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        resp = _json_response({})
        ps_resp = _json_response({"models": []})
        instance = _mock_client(resp)
        instance.get = AsyncMock(return_value=ps_resp)
        with (
            patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_cls.return_value = instance
            await ollama_api.unload_model(BASE, "llama3:8b")
        instance.post.assert_called_once_with(
            f"{BASE}/api/generate",
            json={"model": "llama3:8b", "keep_alive": 0},
        )

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        instance = _mock_client()
        instance.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            with pytest.raises(ConnectionError):
                await ollama_api.unload_model(BASE, "model")

    @pytest.mark.asyncio
    async def test_timeout_error(self) -> None:
        instance = _mock_client()
        instance.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        with patch("the_one.llm.ollama_api.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = instance
            with pytest.raises(ConnectionError, match="Timeout unloading"):
                await ollama_api.unload_model(BASE, "model")


# ---------------------------------------------------------------------------
# Async iterator helper
# ---------------------------------------------------------------------------


async def _async_iter(items: list[str]) -> None:
    """Helper to create an async iterator from a list."""
    for item in items:
        yield item
