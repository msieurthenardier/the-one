"""Ollama native REST API client for model lifecycle management.

Standalone async functions wrapping Ollama's native API endpoints (not the
OpenAI-compatible /v1 endpoints).  Each function accepts a ``base_url``
parameter so callers can target different Ollama instances.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Model-capabilities cache: (base_url, model) → (capabilities_set, fetched_at).
# Avoids a /api/show round-trip on every chat turn. TTL is short enough that a
# `make rebuild` or new model pull is reflected within minutes.
_CAPABILITIES_TTL = 300  # seconds
_capabilities_cache: dict[tuple[str, str], tuple[frozenset[str], float]] = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def strip_v1(base_url: str) -> str:
    """Strip trailing slash and ``/v1`` suffix so we hit the native API."""
    url = base_url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3]
    return url


def ensure_v1(base_url: str) -> str:
    """Strip trailing slash and ensure ``/v1`` suffix for OpenAI-compatible endpoints."""
    url = base_url.rstrip("/")
    return url if url.endswith("/v1") else f"{url}/v1"


def _parse_parameter_size(raw: str | None) -> int | None:
    """Parse Ollama's ``parameter_size`` string (e.g. ``'7B'``) to an int."""
    if not raw:
        return None
    raw = raw.strip().upper()
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}
    for suffix, mult in multipliers.items():
        if raw.endswith(suffix):
            try:
                return int(float(raw[: -len(suffix)]) * mult)
            except ValueError:
                return None
    # Bare number
    try:
        return int(float(raw))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def list_models(base_url: str) -> list[dict[str, Any]]:
    """Return a list of locally available models from ``/api/tags``.

    Each dict contains at minimum ``name``, ``size`` (bytes), and
    ``modified_at``.
    """
    url = strip_v1(base_url)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError as exc:
        raise ConnectionError(f"Cannot connect to Ollama at {url}: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise ConnectionError(f"Timeout connecting to Ollama at {url}: {exc}") from exc

    return data.get("models", [])


async def list_running(base_url: str) -> list[dict[str, Any]]:
    """Return currently loaded/running models from ``/api/ps``.

    Each dict includes model name, size, VRAM usage, and expiry info.
    """
    url = strip_v1(base_url)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{url}/api/ps")
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError as exc:
        raise ConnectionError(f"Cannot connect to Ollama at {url}: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise ConnectionError(f"Timeout connecting to Ollama at {url}: {exc}") from exc

    return data.get("models", [])


async def show_model(
    base_url: str,
    model: str,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return model details from ``/api/show``.

    The returned dict always includes the keys ``parameter_size`` (int or
    None), ``quantization_level`` (str or None), and ``size`` (file size in
    bytes), plus any other fields from the raw response.
    """
    url = strip_v1(base_url)
    try:
        async with httpx.AsyncClient(timeout=30, headers=headers or {}) as client:
            resp = await client.post(f"{url}/api/show", json={"model": model})
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError as exc:
        raise ConnectionError(f"Cannot connect to Ollama at {url}: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise ConnectionError(f"Timeout connecting to Ollama at {url}: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ValueError(f"Model '{model}' not found on Ollama at {url}") from exc
        raise

    details = data.get("details", {})
    raw_param_size = details.get("parameter_size")
    result: dict[str, Any] = {
        **data,
        "parameter_size": _parse_parameter_size(raw_param_size),
        "quantization_level": details.get("quantization_level"),
        "size": data.get("size", 0),
    }
    return result


def extract_ollama_context_length(show_response: dict[str, Any]) -> int | None:
    """Find the ``.context_length`` field in Ollama's /api/show ``model_info``.

    Ollama nests ``context_length`` under a model-family-namespaced key
    (e.g., ``qwen2.context_length``, ``llama.context_length``). This walks
    ``model_info`` for any key ending in ``.context_length`` and returns
    the first int value found.

    Returns None if ``model_info`` is missing/not a dict, if no matching
    key exists, or if the value isn't an int.
    """
    model_info = show_response.get("model_info", {})
    if not isinstance(model_info, dict):
        return None
    for key, value in model_info.items():
        if isinstance(key, str) and key.endswith(".context_length") and isinstance(value, int):
            return value
    return None


async def get_model_context_length(base_url: str, model: str) -> int | None:
    """Return the model's advertised context length from Ollama ``/api/show``.

    F6.5 L04 — async wrapper around :func:`show_model` +
    :func:`extract_ollama_context_length`. Used by the Studio agent
    editor's per-model context-window chip. Fail-open: returns ``None``
    on any error (mirrors :func:`get_model_capabilities` semantics).
    """
    try:
        data = await show_model(base_url, model)
    except (ConnectionError, ValueError, httpx.HTTPError):
        return None
    return extract_ollama_context_length(data)


async def get_model_capabilities(base_url: str, model: str) -> frozenset[str] | None:
    """Return the set of capabilities reported by ``/api/show`` for ``model``.

    Returns ``None`` if the capabilities can't be determined (model missing,
    network error, etc.) — callers should treat ``None`` as "unknown" and
    fall through to the actual request rather than fail-closed.

    Result is cached per (base_url, model) for ``_CAPABILITIES_TTL`` seconds.
    """
    url = strip_v1(base_url)
    key = (url, model)
    cached = _capabilities_cache.get(key)
    now = time.time()
    if cached and now - cached[1] < _CAPABILITIES_TTL:
        return cached[0]

    try:
        data = await show_model(url, model)
    except (ConnectionError, ValueError, httpx.HTTPError):
        return None

    raw = data.get("capabilities")
    if not isinstance(raw, list):
        return None
    caps = frozenset(c for c in raw if isinstance(c, str))
    _capabilities_cache[key] = (caps, now)
    return caps


async def chat_stream(
    provider_url: str,
    body: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream ``/v1/chat/completions`` SSE chunks from an OpenAI-compatible Ollama endpoint.

    Yields parsed JSON dicts for each ``data: {...}`` line. Stops on
    ``data: [DONE]``. Wire format is **true SSE** (``data: ...`` prefix
    + ``[DONE]`` terminator), distinct from ``pull_model``'s JSONL.
    """
    url = ensure_v1(provider_url)
    try:
        async with httpx.AsyncClient(timeout=600, headers=headers or {}) as client:
            async with client.stream(
                "POST", f"{url}/chat/completions", json={**body, "stream": True}
            ) as resp:
                if resp.status_code >= 400:
                    # Read the (still-unconsumed) body so the raised error
                    # surfaces Ollama's explanation (e.g. "model X does not
                    # support tools") instead of a bare HTTP-status link.
                    body_bytes = await resp.aread()
                    detail = body_bytes.decode("utf-8", errors="replace").strip()
                    raise httpx.HTTPStatusError(
                        f"Ollama returned {resp.status_code} from "
                        f"{resp.request.url}: {detail or '(empty body)'}",
                        request=resp.request,
                        response=resp,
                    )
                async for raw_line in resp.aiter_lines():
                    if not raw_line:
                        continue
                    if not raw_line.startswith("data:"):
                        continue
                    payload = raw_line[len("data:") :].strip()
                    if payload == "[DONE]":
                        return
                    try:
                        yield json.loads(payload)
                    except ValueError:
                        continue
    except httpx.ConnectError as exc:
        raise ConnectionError(f"Cannot connect to Ollama at {url}: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise ConnectionError(f"Timeout streaming from Ollama at {url}: {exc}") from exc


async def pull_model(base_url: str, model: str) -> AsyncIterator[dict[str, Any]]:
    """Stream-pull a model via ``/api/pull``.

    Yields progress dicts with keys like ``status``, ``completed``, and
    ``total``.
    """
    url = strip_v1(base_url)
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream("POST", f"{url}/api/pull", json={"model": model}) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue
    except httpx.ConnectError as exc:
        raise ConnectionError(f"Cannot connect to Ollama at {url}: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise ConnectionError(f"Timeout pulling model from Ollama at {url}: {exc}") from exc


async def delete_model(base_url: str, model: str) -> None:
    """Delete a model via ``DELETE /api/delete``."""
    url = strip_v1(base_url)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request("DELETE", f"{url}/api/delete", json={"model": model})
            resp.raise_for_status()
    except httpx.ConnectError as exc:
        raise ConnectionError(f"Cannot connect to Ollama at {url}: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise ConnectionError(f"Timeout connecting to Ollama at {url}: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ValueError(f"Model '{model}' not found on Ollama at {url}") from exc
        raise


async def load_model(base_url: str, model: str, keep_alive: str = "24h") -> None:
    """Load a model into VRAM via ``/api/generate`` with ``keep_alive``.

    Ollama loads the model when it receives a generate request.
    """
    url = strip_v1(base_url)
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{url}/api/generate",
                json={"model": model, "keep_alive": keep_alive},
            )
            resp.raise_for_status()
    except httpx.ConnectError as exc:
        raise ConnectionError(f"Cannot connect to Ollama at {url}: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise ConnectionError(f"Timeout loading model '{model}' on Ollama at {url}: {exc}") from exc


async def unload_model(base_url: str, model: str) -> None:
    """Unload a model from VRAM via ``/api/generate`` with ``keep_alive: 0``.

    Waits until the model no longer appears in ``/api/ps`` before returning.
    """
    import asyncio

    url = strip_v1(base_url)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{url}/api/generate",
                json={"model": model, "keep_alive": 0},
            )
            resp.raise_for_status()

            # Wait for Ollama to actually release the model
            for _ in range(20):  # up to ~5 seconds
                await asyncio.sleep(0.25)
                ps = await client.get(f"{url}/api/ps")
                running = ps.json().get("models", [])
                if not any(m.get("name", "") == model for m in running):
                    return
            logger.warning("Model '%s' still running after polling exhausted on %s", model, url)
    except httpx.ConnectError as exc:
        raise ConnectionError(f"Cannot connect to Ollama at {url}: {exc}") from exc
    except httpx.TimeoutException as exc:
        raise ConnectionError(
            f"Timeout unloading model '{model}' on Ollama at {url}: {exc}"
        ) from exc
