"""Fail-open model-catalog lookup for context-window sizes.

Contract
--------
- ``context_window_for(provider, model)`` returns the context window (int) for
  the given provider and **bare** model id, or ``None`` on any miss or load
  failure.

Bare-id contract
    Callers pass the bare model id as returned by the SDK — e.g. ``gpt-4o``,
    ``claude-sonnet-4-6``.  The ``provider/model`` namespace form that some
    upstream datasets use (e.g. ``openai/gpt-4o``) is **never** passed by
    callers; stripping any such prefix is the generator script's responsibility,
    not the runtime lookup's.

Matching algorithm
    For a given provider section, the lookup first tries an exact match against
    the catalog keys.  If that misses, it falls back to longest-prefix-wins
    across all keys in that section (keys sorted descending by length), so a
    dated/variant id such as ``gpt-4o-2024-08-06`` resolves to the ``gpt-4o``
    entry rather than falling back to a shorter prefix match.  This mirrors the
    algorithm at ``openai_provider.py:94-104``.

Memoization and test seam
    The parsed catalog is memoized at module level (loaded once on first use).
    ``_reset_for_tests(catalog=None)`` replaces the memoized instance — pass a
    dict to inject a test fixture, or ``None`` to force a reload from the seed
    file on the next call.  This is a bare module-level function, not a class
    attribute, so tests can monkeypatch it without importing internals.

Runtime refresh
    ``refresh_catalog_cache()`` fetches models.dev asynchronously and atomically
    writes an on-disk cache at ``settings.data_dir / "model_catalog.json"``.
    ``_load_catalog()`` prefers that cache over the bundled seed when it is
    present and parses correctly; a corrupt cache logs a WARN and falls back
    to the seed.  ``invalidate()`` clears the memo so the next lookup re-reads
    from disk.

Shared projection helpers
    ``project_raw(raw)``, ``apply_floor``, ``_OPENAI_FLOOR``,
    ``_strip_provider_prefix``, and ``_extract_context_window`` live here so
    both this module and ``scripts/refresh_model_catalog.py`` share the same
    transform without duplication.

Fail-open guarantees
    - Whole-catalog parse/IO failure → logs ``WARNING`` once, treats catalog as
      empty (all lookups return ``None``).  Exceptions never escape.
    - Per-model miss → returns ``None`` silently (the miss-WARN is owned by the
      caller at the provider resolver layer, deferred to legs 3–4).
"""

from __future__ import annotations

import importlib.resources
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from the_one.config import settings

logger = logging.getLogger(__name__)

# Endpoint for the models.dev full dataset.
_MODELS_DEV_URL = "https://models.dev/api.json"

# Timeout for the async HTTP fetch (seconds).
_FETCH_TIMEOUT = 30.0

# Providers to include from models.dev.
_TARGET_PROVIDERS = {"openai", "anthropic"}

# Context-window floor values — mirrors the historical OPENAI_MODEL_CONTEXT
# table (now removed; this is the canonical floor).  Used to enforce the
# no-regression guarantee: if models.dev is absent or returns a smaller value
# for any of these ids, the floor value is used instead.
_OPENAI_FLOOR: dict[str, int] = {
    "gpt-4o": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4-32k": 32_768,
    "gpt-4-vision-preview": 128_000,
    "gpt-4-0125-preview": 128_000,
    "gpt-4-1106-preview": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo-instruct": 4_096,
    "gpt-3.5-turbo-16k": 16_385,
    "gpt-3.5-turbo": 16_385,
    "o1": 200_000,
    "o3-mini": 200_000,
}

# Module-level memoized catalog.  ``None`` means "not yet loaded"; a dict
# (possibly empty, if the seed failed to parse) is the loaded state.
_catalog: dict[str, Any] | None = None


# ── Shared projection helpers ─────────────────────────────────────────────


def _strip_provider_prefix(model_id: str, provider: str) -> str:
    """Strip a ``provider/`` namespace prefix from a model id if present.

    models.dev may represent model ids as ``openai/gpt-4o``; callers pass bare
    ids (``gpt-4o``) so we normalise here.
    """
    prefix = provider + "/"
    if model_id.startswith(prefix):
        return model_id[len(prefix) :]
    return model_id


def _extract_context_window(model_entry: dict) -> int | None:
    """Extract the context window int from a models.dev model entry.

    models.dev may nest the value under various shapes (``context``,
    ``contextWindow``, ``limit.context``, ``maxInputTokens``).  Try the known
    shapes in priority order; return ``None`` if none yield a positive int.
    """
    for key in ("context", "contextWindow", "context_window", "maxInputTokens"):
        val = model_entry.get(key)
        if isinstance(val, int) and val > 0:
            return val

    # Nested limit object (e.g. ``{"limit": {"context": 128000}}``)
    limit = model_entry.get("limit")
    if isinstance(limit, dict):
        for key in ("context", "contextWindow", "input"):
            val = limit.get(key)
            if isinstance(val, int) and val > 0:
                return val

    return None


def project_raw(raw: Any) -> dict[str, dict[str, int]]:
    """Project a raw models.dev API payload to the flat catalog shape.

    Returns a dict keyed by provider name, each containing a dict of
    ``{bare_model_id: context_window}`` for models where a context window is
    available.

    This is the pure projection — no HTTP call.  Both the async runtime refresh
    loop and the sync ``scripts/refresh_model_catalog.py`` call this after their
    respective fetches.
    """
    providers: dict[str, dict[str, int]] = {}

    # models.dev top-level shape: either a list of model entries (each with a
    # ``provider`` field), or a dict keyed by provider name.  Handle both.
    if isinstance(raw, list):
        # List shape: [{id, provider, context, ...}, ...]
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            provider = entry.get("provider", "")
            if not isinstance(provider, str):
                continue
            provider = provider.lower()
            if provider not in _TARGET_PROVIDERS:
                continue
            model_id = entry.get("id", "")
            if not isinstance(model_id, str) or not model_id:
                continue
            bare_id = _strip_provider_prefix(model_id, provider)
            ctx = _extract_context_window(entry)
            if ctx is not None:
                providers.setdefault(provider, {})[bare_id] = ctx

    elif isinstance(raw, dict):
        # Real models.dev shape (as of 2026):
        #   {
        #     "<provider>": {                        # top-level: provider metadata
        #       "id": "...", "name": "...", ...,
        #       "models": {                          # nested models dict
        #         "<model_id>": {"limit": {"context": N}, ...},
        #         ...
        #       }
        #     },
        #     ...
        #   }
        #
        # Traverse raw[provider]["models"] to reach the per-model entries.
        # Defensive fallbacks below handle older flat shapes (provider → models dict
        # without a "models" nesting key) in case the API shape ever reverts.
        for provider, provider_data in raw.items():
            if not isinstance(provider, str):
                continue
            provider = provider.lower()
            if provider not in _TARGET_PROVIDERS:
                continue
            if not isinstance(provider_data, dict):
                continue

            # Primary path: real nested shape {provider: {models: {id: entry}}}
            nested_models = provider_data.get("models")
            if isinstance(nested_models, dict):
                for model_id, entry in nested_models.items():
                    if not isinstance(entry, dict):
                        continue
                    bare_id = _strip_provider_prefix(model_id, provider)
                    ctx = _extract_context_window(entry)
                    if ctx is not None:
                        providers.setdefault(provider, {})[bare_id] = ctx
            # Defensive fallback: flat {provider: {model_id: entry}} shape —
            # skip provider-level metadata keys (non-dict values) silently.
            else:
                for model_id, entry in provider_data.items():
                    if not isinstance(entry, dict):
                        continue  # skip metadata keys (id, env, npm, name, doc)
                    bare_id = _strip_provider_prefix(model_id, provider)
                    ctx = _extract_context_window(entry)
                    if ctx is not None:
                        providers.setdefault(provider, {})[bare_id] = ctx

    return providers


def apply_floor(
    providers: dict[str, dict[str, int]],
    floor: dict[str, int],
    provider: str,
) -> dict[str, dict[str, int]]:
    """Ensure all floor entries are present at their minimum window values.

    For each entry in ``floor``:
    - If the model is absent in ``providers[provider]``, add it with the floor
      value.
    - If the model is present but models.dev returned a smaller window, keep
      the floor value (no-regression guarantee).
    """
    section = providers.setdefault(provider, {})
    for model_id, floor_window in floor.items():
        existing = section.get(model_id)
        if existing is None or existing < floor_window:
            section[model_id] = floor_window
    return providers


# ── Loader ───────────────────────────────────────────────────────────────


def _load_seed() -> dict[str, Any]:
    """Load the bundled seed JSON and return its parsed content.

    Raises any IO or parse exception — the caller owns the fail-open error
    boundary and WARNING log.
    """
    package = importlib.resources.files("the_one.llm")
    seed_file = package.joinpath("data").joinpath("model_catalog.json")
    raw = seed_file.read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"catalog root must be a JSON object, got {type(data).__name__}")
    return data


def _load_catalog() -> dict[str, Any]:
    """Load the catalog, preferring the on-disk cache over the bundled seed.

    Resolution order:
    1. ``settings.data_dir / "model_catalog.json"`` (runtime cache) — if it
       exists and parses as a dict, return it.
    2. Cache exists but fails to parse → log WARNING and fall through to seed.
    3. Bundled seed (``the_one/llm/data/model_catalog.json``) — Leg-1 behavior.

    Raises any IO or parse exception from the seed load — the caller
    (``_get_catalog``) owns the fail-open error boundary and WARNING log, so
    that monkeypatching this function in tests exercises the same boundary.
    """
    cache_path = settings.data_dir / "model_catalog.json"
    if cache_path.exists():
        try:
            raw = cache_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
            raise ValueError(
                f"cache root must be a JSON object, got {type(data).__name__}"
            )
        except Exception as exc:
            logger.warning(
                "model_catalog: cache at %s is corrupt (%s) — falling back to bundled seed",
                cache_path,
                exc,
            )

    return _load_seed()


def _get_catalog() -> dict[str, Any]:
    """Return the memoized catalog, loading it on first call.

    This is the fail-open error boundary: any exception from ``_load_catalog``
    is caught here, a WARNING is logged once, and an empty dict is stored so
    subsequent lookups return ``None`` without retrying a broken load.

    The call to ``_load_catalog`` is made via the module's own attribute so
    that tests can monkeypatch ``the_one.llm.model_catalog._load_catalog``
    to inject failure scenarios and still exercise this boundary.
    """
    global _catalog
    if _catalog is None:
        import the_one.llm.model_catalog as _self

        try:
            _catalog = _self._load_catalog()
        except Exception as exc:
            logger.warning(
                "model_catalog: failed to load bundled seed — all context-window lookups "
                "will return None (fail-open): %s",
                exc,
            )
            _catalog = {}
    return _catalog


def _reset_for_tests(catalog: dict[str, Any] | None = None) -> None:
    """Replace the memoized catalog instance.

    Pass a ``dict`` to inject a test fixture, or ``None`` to force a fresh
    load from the seed file on the next ``context_window_for`` call.
    """
    global _catalog
    _catalog = catalog


def invalidate() -> None:
    """Clear the memoized catalog so the next lookup re-reads from disk.

    Called by ``refresh_catalog_cache()`` after a successful write so the
    next ``context_window_for()`` call picks up the fresh cache.  Also
    available to runtime code that needs to force a reload (e.g. tests,
    admin tooling).

    Equivalent to ``_reset_for_tests(None)`` but with a runtime-meaningful
    name that signals intent rather than exposing a test seam.
    """
    global _catalog
    _catalog = None


# ── Refresh-due check ─────────────────────────────────────────────────────

_REFRESH_INTERVAL_SECONDS = 24 * 3600  # 24 hours


def _refresh_due() -> bool:
    """Return True when the on-disk cache is absent, corrupt, or older than 24h.

    Reads the cache file's ``fetched_at`` field (ISO-8601 UTC timestamp written
    by ``refresh_catalog_cache``).  Absent cache, missing ``fetched_at``,
    unparseable timestamp, or a timestamp older than 24h → True.

    The seed uses ``generated_at`` (a date string, not a timestamp) — if the
    operator has manually copied the seed to the cache path it will have no
    ``fetched_at`` and the check returns True (startup catch-up fires).
    """
    cache_path = settings.data_dir / "model_catalog.json"
    if not cache_path.exists():
        return True
    try:
        raw = cache_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        fetched_at_str = data.get("fetched_at")
        if not fetched_at_str:
            return True
        fetched_at = datetime.fromisoformat(fetched_at_str)
        # Normalise to UTC-aware for comparison.
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - fetched_at).total_seconds()
        return age >= _REFRESH_INTERVAL_SECONDS
    except Exception:
        return True


# ── Runtime cache refresh ─────────────────────────────────────────────────


async def refresh_catalog_cache(url: str = _MODELS_DEV_URL) -> bool:
    """Fetch models.dev and atomically write the on-disk cache.

    Steps:
    1. Async GET ``url`` with timeout + follow_redirects.
    2. Project the payload via ``project_raw`` + ``apply_floor``.
    3. **Seed-coverage write guard**: load the bundled seed and check that
       every ``(provider, model)`` pair the seed covers is also present in the
       newly-projected catalog.  If any pair is missing, skip the write and
       return ``False`` (keeps the existing cache/seed intact).
    4. Atomic write: ``<cache>.tmp`` in the same dir, then ``os.replace``.
       Payload: ``{fetched_at, source, providers}``.
    5. ``invalidate()`` so the next ``context_window_for()`` re-reads from disk.

    Returns ``True`` only on a successful write.  All exceptions are caught,
    logged, and ``False`` is returned so the loop is offline-safe and never
    raises into the lifespan.

    The seed-coverage guard is the critical defence against empty/garbage
    fetches: ``apply_floor`` unconditionally injects all 12 OpenAI floor keys,
    so an empty fetch would still look "covered" for OpenAI while silently
    losing Anthropic entries and newer models.  Checking against the seed
    (which carries both providers) is the correct guard.
    """
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=_FETCH_TIMEOUT, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            raw_payload = resp.json()

        projected = apply_floor(project_raw(raw_payload), _OPENAI_FLOOR, "openai")

        # ── Seed-coverage write guard ─────────────────────────────────────
        # Load the bundled seed (always present) and verify the projected
        # catalog covers every (provider, model) pair the seed covers.
        try:
            seed_data = _load_seed()
            seed_providers: dict[str, Any] = seed_data.get("providers", {})
        except Exception as exc:
            logger.warning(
                "model_catalog: could not load seed for coverage check — skipping cache write: %s",
                exc,
            )
            return False

        projected_providers = projected  # {provider: {model: ctx}}
        for provider, seed_models in seed_providers.items():
            if not isinstance(seed_models, dict):
                continue
            proj_section = projected_providers.get(provider, {})
            for model in seed_models:
                if model not in proj_section:
                    logger.warning(
                        "model_catalog: fetch missing seed pair (%s, %s) — "
                        "skipping cache write to protect existing catalog",
                        provider,
                        model,
                    )
                    return False

        # ── Atomic write ──────────────────────────────────────────────────
        cache_path = settings.data_dir / "model_catalog.json"
        tmp_path = cache_path.with_suffix(".tmp")
        catalog_payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "models.dev",
            "providers": {
                p: dict(sorted(models.items()))
                for p, models in sorted(projected_providers.items())
            },
        }
        tmp_path.write_text(
            json.dumps(catalog_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, cache_path)
        invalidate()
        logger.info(
            "model_catalog: cache refreshed at %s (%d providers)",
            cache_path,
            len(projected_providers),
        )
        return True

    except Exception as exc:
        logger.warning(
            "model_catalog: refresh failed — keeping existing cache/seed intact: %s",
            exc,
        )
        return False


# ── Catalog lookup ────────────────────────────────────────────────────────


def context_window_for(provider: str, model: str) -> int | None:
    """Return the context-window size for the given provider and bare model id.

    Parameters
    ----------
    provider:
        Provider name as stored in the catalog (e.g. ``"openai"``,
        ``"anthropic"``).
    model:
        Bare model id as returned by the provider SDK — no ``provider/``
        namespace prefix (e.g. ``"gpt-4o"``, ``"claude-sonnet-4-6"``).

    Returns
    -------
    int | None
        The context window in tokens, or ``None`` if the provider section is
        absent, the model is not found, or the catalog failed to load.
    """
    catalog = _get_catalog()
    providers: dict[str, Any] = catalog.get("providers", {})
    provider_section: dict[str, int] | None = providers.get(provider)
    if not isinstance(provider_section, dict):
        return None

    # Exact match first.
    if model in provider_section:
        return provider_section[model]

    # Longest-prefix-wins fallback: sort keys descending by length so a longer
    # prefix (e.g. ``gpt-4-turbo``) beats a shorter one (e.g. ``gpt-4``) when
    # both are prefixes of the query string.
    for key in sorted(provider_section, key=len, reverse=True):
        if model.startswith(key):
            return provider_section[key]

    return None
