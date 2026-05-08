"""OpenRouter REST API client.

Helpers for the model-list (``/models``), key-verification (``/auth/key``),
and capability lookup endpoints. Mirrors ``the_one/llm/ollama_api.py`` shape.

Design contract:
- ``list_models`` / ``verify_key`` raise on failure (caller translates to HTTP).
- ``get_model_capabilities`` is a separate fail-open wrapper for the Studio
  capability chip — returns ``None`` on any error or absent capability data.

Cache:
- ``_models_cache`` keyed on ``(base_url, sha256(api_key)[:16])``, TTL 300s.
- Hashing the api_key avoids cross-account list bleed if two configs share a
  base_url with different keys.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class OpenRouterModelEntry(BaseModel):
    """Typed shape for a single entry returned by ``GET /models``.

    Only the fields read by the Studio model-list / capability chip are
    declared explicitly; everything else flows through via
    ``extra='allow'`` so future OpenRouter response additions don't
    require a release here. ``description`` defaults to ``""`` (matching
    the previous ``m.get("description", "")`` callsite); the rest default
    to ``None`` so a minimal ``{"id": "..."}`` payload validates.
    """

    id: str
    name: str | None = None
    supported_parameters: list[str] | None = None
    context_length: int | None = None
    description: str = ""

    model_config = ConfigDict(extra="allow")


_CACHE_TTL = 300  # seconds
_models_cache: dict[tuple[str, str], tuple[list[OpenRouterModelEntry], float]] = {}


def _cache_key(base_url: str, api_key: str | None) -> tuple[str, str]:
    raw = (api_key or "").encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return (base_url.rstrip("/"), digest)


def _auth_headers(api_key: str | None) -> dict[str, str]:
    key = (api_key or "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


async def list_models(base_url: str, api_key: str | None) -> list[OpenRouterModelEntry]:
    """Fetch and cache ``GET {base_url}/models``.

    Returns a list of ``OpenRouterModelEntry`` (typed, extra-fields allowed).

    Raises:
        httpx.HTTPStatusError: on 4xx / 5xx response.
        httpx.RequestError: on network failure.
        ValueError: on JSON parse / shape failure.

    Test seam: when ``settings.dev_mode`` is True AND the environment
    variable ``THE_ONE_OPENROUTER_TEST_MODELS_JSON`` is set, its JSON
    value is parsed into ``OpenRouterModelEntry`` instances directly
    without any network call. Intended only for browser-test subprocesses
    that cannot share in-process cache state with the test runner.

    The dev_mode gate ensures an accidentally-exported env var in a
    production environment cannot silently substitute fake models for
    real ones.
    """
    test_json = os.environ.get("THE_ONE_OPENROUTER_TEST_MODELS_JSON")
    if test_json:
        from the_one.config import settings

        if settings.dev_mode:
            logger.info(
                "Using THE_ONE_OPENROUTER_TEST_MODELS_JSON test seam (dev_mode=true)"
            )
            raw = json.loads(test_json)
            if not isinstance(raw, list):
                raise ValueError("THE_ONE_OPENROUTER_TEST_MODELS_JSON must be a JSON array")
            return [OpenRouterModelEntry.model_validate(item) for item in raw]
        # In production (dev_mode=False) the env var is silently
        # ignored. A warning surfaces operator awareness without
        # disrupting the actual /models fetch below.
        logger.warning(
            "THE_ONE_OPENROUTER_TEST_MODELS_JSON is set but dev_mode is False — "
            "the test seam is ignored. Unset the env var to silence this warning."
        )

    cache_key = _cache_key(base_url, api_key)
    cached = _models_cache.get(cache_key)
    if cached is not None and (time.time() - cached[1]) < _CACHE_TTL:
        return cached[0]

    url = base_url.rstrip("/") + "/models"
    async with httpx.AsyncClient(timeout=30, headers=_auth_headers(api_key)) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, dict) or "data" not in data:
        raise ValueError(f"Unexpected payload shape from {url}: missing 'data' key")
    raw = data["data"]
    if not isinstance(raw, list):
        raise ValueError(f"Unexpected 'data' type from {url}: {type(raw).__name__}")
    models = [OpenRouterModelEntry.model_validate(item) for item in raw]
    _models_cache[cache_key] = (models, time.time())
    return models


async def verify_key(base_url: str, api_key: str) -> dict[str, Any]:
    """Probe ``GET {base_url}/auth/key`` for actual key validity.

    Raises:
        httpx.HTTPStatusError: on 401 (invalid key) / 4xx / 5xx.
        httpx.RequestError: on network failure.
    """
    url = base_url.rstrip("/") + "/auth/key"
    async with httpx.AsyncClient(timeout=15, headers=_auth_headers(api_key)) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def get_model_capabilities(
    base_url: str,
    api_key: str | None,
    model: str,
) -> frozenset[str] | None:
    """Return ``supported_parameters`` for ``model`` as a frozenset.

    Returns ``None`` on:
    - any fetch failure (mirrors ollama_api.get_model_capabilities semantics)
    - model not found in the listing
    - missing ``supported_parameters`` field
    - empty ``supported_parameters`` list

    The caller (Studio capability chip) treats ``None`` as "unknown" and
    renders no chip, ensuring fail-open behavior.
    """
    try:
        models = await list_models(base_url, api_key)
    except (httpx.HTTPError, ValueError) as e:
        # Fail-open user-side (no chip rendered), but log server-side
        # so a contract violation (ValueError) or persistent auth
        # failure (401) is observable in production logs. Swallowing
        # silently was the previous behavior — the chip absence was
        # the only signal, which is opaque for debugging.
        logger.warning(
            "get_model_capabilities failed for model=%s base=%s: %s",
            model,
            base_url,
            e,
            exc_info=True,
        )
        return None

    for entry in models:
        if entry.id == model:
            params = entry.supported_parameters
            if not isinstance(params, list) or len(params) == 0:
                return None
            return frozenset(p for p in params if isinstance(p, str))
    return None
