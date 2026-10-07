"""Ollama pull catalog: every pullable ``name:tag`` with its exact download size.

Sources (fixed URLs, see SECURITY-MODEL.md "Ollama library and registry fetches"):

* ``https://ollama.com/library`` (HTML): the model names, each model's parameter-size
  tags and its cloud badge. Parsed by :func:`parse_library_page`.
* ``https://ollama.com/api/tags`` (JSON): extra names and a cloud signal.
* ``https://registry.ollama.ai/v2/library/{name}/manifests/{tag}``: the exact download
  size, ``sum(layers[].size) + config.size``.

The registry manifests are a fixed host fetched with ``follow_redirects=False``. The
library page and ``/api/tags`` are fixed ollama.com URLs fetched with redirects followed;
their responses are only parsed, and every name and tag is validated (:func:`split_model`,
``re.fullmatch``) before any manifest URL is built.

Each entry carries one status: ``ok`` (manifest 200, size known), ``cloud`` (404 with a
cloud signal), ``missing`` (404 without one) or ``unknown`` (anything else).

Sizes are cached in one shared in-memory map and on disk at
``{data_dir}/ollama-sizes.json``. A detached module task fills the map (single-flight);
requests wait for it at most :data:`_WAIT_S` seconds and otherwise answer ``loading``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

LIBRARY_URL = "https://ollama.com/library"
TAGS_URL = "https://ollama.com/api/tags"
REGISTRY = "https://registry.ollama.ai"
ACCEPT = "application/vnd.docker.distribution.manifest.v2+json"

# Anchored allowlists, applied with ``re.fullmatch`` (``re.match`` + ``$`` would accept a
# trailing newline) before any value is interpolated into a URL.
_NAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_TAG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

_TTL_OK = 7 * 86400.0
_TTL_CLOUD = 7 * 86400.0
_TTL_MISSING = 86400.0
_UNKNOWN_TTL = 300.0  # in memory only
_LISTING_TTL = 300.0
_TTLS = {"ok": _TTL_OK, "cloud": _TTL_CLOUD, "missing": _TTL_MISSING, "unknown": _UNKNOWN_TTL}
_PERSISTED_STATUSES = ("ok", "cloud", "missing")

_CONCURRENCY = 16
_MANIFEST_TIMEOUT = 10.0
_SIZE_TIMEOUT = 5.0
_BUDGET_S = 45.0
_WAIT_S = 8.0
_COOLDOWN_S = 300.0

_SEAM_ENV = "THE_ONE_OLLAMA_LIBRARY_TEST_JSON"

# ── Shared state ──────────────────────────────────────────────────────────

_sizes: dict[str, dict[str, Any]] = {}  # "name:tag" -> {size, status, fetched_at}
_library: dict[str, Any] | None = None  # {"entries": [{"name", "cloud"}], "fetched_at"}
_fill: asyncio.Task[None] | None = None
_fill_path: Path | None = None
_cache_path_override: Path | None = None
_loaded_from_disk = False
_last_attempt = 0.0  # last listing fetch attempt (memory only)
_cooldown_until = 0.0  # set after an early stop (memory only)


def _new_client(**kwargs: Any) -> httpx.AsyncClient:
    """The one place an HTTP client is built (a seam for tests)."""
    return httpx.AsyncClient(**kwargs)


# ── Names ─────────────────────────────────────────────────────────────────


def split_model(model: str) -> tuple[str, str | None]:
    """Validate ``name`` or ``name:tag``; return ``(name, tag-or-None)``.

    Raises ``ValueError`` (with a user-presentable message) when either part fails the
    allowlist.
    """
    value = (model or "").strip()
    if not value:
        raise ValueError("model is required")
    name, sep, tag = value.partition(":")
    if not _NAME_RE.fullmatch(name):
        raise ValueError(f"invalid model name: {value!r}")
    if sep and not _TAG_RE.fullmatch(tag):
        raise ValueError(f"invalid model tag: {value!r}")
    return name, (tag if sep else None)


def _key(model: str) -> str:
    """Cache key: bare names normalise to ``name:latest``."""
    name, tag = split_model(model)
    return f"{name}:{tag or 'latest'}"


def _model_part(name: str) -> str:
    return name.partition(":")[0].lower()


# ── Library page parser ───────────────────────────────────────────────────

# Split on each entry's <li>; the class list is whitespace-tolerant (a literal-class split
# once found zero blocks).
_LI_SPLIT_RE = re.compile(r"<li\s[^>]*items-baseline", re.IGNORECASE)
_ANCHOR_RE = re.compile(
    r"""<a\b[^>]*?\bhref\s*=\s*["'](?P<href>[^"']*)["'][^>]*>(?P<body>.*?)</a>""",
    re.IGNORECASE | re.DOTALL,
)
_SIZE_TAG_RE = re.compile(
    r"""<span\b[^>]*text-blue-600[^>]*>\s*(?P<tag>[^<]*?)\s*</span>""", re.IGNORECASE
)
_CLOUD_BADGE_RE = re.compile(r"""<span\b[^>]*text-cyan-500""", re.IGNORECASE)


def _library_link_name(href: str) -> str | None:
    """The single-segment model name of a ``/library/{name}`` link, else ``None``."""
    rest = re.sub(r"^https?://ollama\.com", "", href.strip(), flags=re.IGNORECASE)
    if not rest.startswith("/library/"):
        return None
    rest = re.split(r"[?#]", rest[len("/library/") :], maxsplit=1)[0].rstrip("/")
    if not rest or "/" in rest:
        return None
    return rest


def parse_library_page(html: str) -> list[dict[str, Any]]:
    """Parse the library page into ``[{"name": "model:tag" | "model", "cloud": bool}]``.

    Pure (no network). One entry per size tag, in page order, or the bare name when the
    model has none. Each ``<li>`` block is scoped to its own anchor so spans never bleed
    into the next entry. An empty list means nothing recognisable was found.
    """
    entries: dict[str, dict[str, Any]] = {}
    for block in _LI_SPLIT_RE.split(html)[1:]:
        model = None
        body = ""
        for m in _ANCHOR_RE.finditer(block):
            model = _library_link_name(m.group("href"))
            if model is not None:
                body = m.group("body")
                break
        if model is None:
            continue
        if not _NAME_RE.fullmatch(model):
            logger.warning("Ollama library: dropping invalid model name %r", model)
            continue
        cloud = bool(_CLOUD_BADGE_RE.search(body))
        tags = [t.group("tag") for t in _SIZE_TAG_RE.finditer(body)]
        names: list[str] = []
        if tags:
            for tag in tags:
                if _TAG_RE.fullmatch(tag):
                    names.append(f"{model}:{tag}")
                else:
                    logger.warning("Ollama library: dropping invalid tag %r of %r", tag, model)
        else:
            names.append(model)
        for name in names:
            entries.setdefault(_key(name), {"name": name, "cloud": cloud})
    return list(entries.values())


def _merge_tag_names(entries: list[dict[str, Any]], names: list[str]) -> list[dict[str, Any]]:
    """Add ``/api/tags`` names: cloud-flag an existing entry, else append after the page's."""
    merged = [dict(e) for e in entries]
    index = {_key(e["name"]): e for e in merged}
    for raw in names:
        try:
            key = _key(raw)
        except ValueError:
            logger.warning("Ollama tags: dropping invalid name %r", raw)
            continue
        if key in index:
            index[key]["cloud"] = True
        else:
            entry = {"name": raw.strip(), "cloud": True}
            merged.append(entry)
            index[key] = entry
    return merged


# ── Disk cache ────────────────────────────────────────────────────────────


def _cache_path() -> Path:
    if _cache_path_override is not None:
        return _cache_path_override
    from the_one.config import settings

    return Path(settings.data_dir) / "ollama-sizes.json"


def _timestamp(value: Any) -> float | None:
    """A cached ``fetched_at`` as a finite, non-negative float, else ``None``."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        out = float(value)  # a huge int raises OverflowError
    except (OverflowError, ValueError):
        return None
    return out if math.isfinite(out) and out >= 0 else None


def _parse_disk(
    raw: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None, int]:
    """Validate a parsed cache file into ``(sizes, library, dropped_name_count)``.

    Pure: touches no module state, so a failure part-way leaves nothing half-loaded.
    """
    dropped = 0  # invalid names/keys (hand-edited file): dropped with one warning
    sizes_out: dict[str, dict[str, Any]] = {}
    sizes = raw.get("sizes")
    if isinstance(sizes, dict):
        for key, val in sizes.items():
            if not isinstance(val, dict) or val.get("status") not in _PERSISTED_STATUSES:
                continue
            fetched = _timestamp(val.get("fetched_at"))
            size = val.get("size")
            if fetched is None:
                continue
            if size is not None and (not isinstance(size, int) or isinstance(size, bool)):
                continue
            try:
                norm = _key(str(key))
            except ValueError:
                dropped += 1
                continue
            sizes_out.setdefault(
                norm, {"size": size, "status": val["status"], "fetched_at": fetched}
            )
    library_out: dict[str, Any] | None = None
    lib = raw.get("library")
    if isinstance(lib, dict) and isinstance(lib.get("entries"), list):
        entries = []
        for e in lib["entries"]:
            if not isinstance(e, dict) or not isinstance(e.get("name"), str):
                continue
            try:
                _key(e["name"])
            except ValueError:
                dropped += 1
                continue
            entries.append({"name": e["name"], "cloud": bool(e.get("cloud"))})
        if entries:
            library_out = {
                "entries": entries,
                "fetched_at": _timestamp(lib.get("fetched_at")) or 0.0,
            }
    return sizes_out, library_out, dropped


def _load_disk() -> None:
    """Load the disk cache into memory, once. Never raises (``CancelledError`` aside).

    A missing file is the normal cold start. Any other failure of the file (unreadable,
    not JSON, nesting too deep, wrong shape, ...) logs one warning and leaves no disk
    cache; individual bad entries in an otherwise good file are dropped on their own.
    """
    global _loaded_from_disk, _library
    if _loaded_from_disk:
        return
    _loaded_from_disk = True
    path = _cache_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("not an object")
        sizes, library, dropped = _parse_disk(raw)
    except FileNotFoundError:
        return
    except Exception as e:  # a corrupt cache must degrade, never 500 (DD4)
        logger.warning("Ollama size cache %s unreadable (%r); starting empty", path, e)
        return
    for key, entry in sizes.items():
        _sizes.setdefault(key, entry)
    if _library is None and library is not None:
        _library = library
    if dropped:
        logger.warning("Ollama size cache %s: dropped %d invalid entries", path, dropped)


def _persist(path: Path | None = None) -> None:
    """Write the cache atomically (tmp then ``os.replace``, no await between). Never raises."""
    target = path or _cache_path()
    payload = {
        "version": 1,
        "library": _library,
        "sizes": {k: v for k, v in _sizes.items() if v["status"] in _PERSISTED_STATUSES},
    }
    tmp = target.with_suffix(".json.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp, target)
    except (OSError, TypeError, ValueError) as e:
        logger.warning("Could not persist Ollama size cache to %s: %s", target, e)
        with contextlib.suppress(OSError):
            tmp.unlink()


# ── The shared map ────────────────────────────────────────────────────────


def _expired(entry: dict[str, Any], now: float) -> bool:
    return now - entry["fetched_at"] > _TTLS[entry["status"]]


def _needs_fetch(key: str, now: float) -> bool:
    entry = _sizes.get(key)
    return entry is None or _expired(entry, now)


def _record(key: str, status: str, size: int | None) -> dict[str, Any]:
    """Write one key. An ``unknown`` never overwrites a known entry within its TTL."""
    now = time.time()
    existing = _sizes.get(key)
    if (
        status == "unknown"
        and existing is not None
        and existing["status"] != "unknown"
        and not _expired(existing, now)
    ):
        return existing
    entry = {"size": size if status == "ok" else None, "status": status, "fetched_at": now}
    _sizes[key] = entry
    return entry


# ── Registry manifest ─────────────────────────────────────────────────────


async def _fetch_manifest(
    client: httpx.AsyncClient, name: str, tag: str, cloud: bool
) -> tuple[str, int | None, bool]:
    """Fetch one manifest. Returns ``(status, size, hard_failure)``.

    ``hard_failure`` marks transport errors, 403 and 429 (what the early stop counts).
    """
    url = f"{REGISTRY}/v2/library/{name}/manifests/{tag}"
    try:
        resp = await client.get(url, headers={"Accept": ACCEPT})
    except (httpx.HTTPError, OSError):
        return "unknown", None, True
    code = resp.status_code
    if code == 200:
        try:
            data = resp.json()
            layers = sum(int(layer["size"]) for layer in data["layers"])
            total = int(data["config"]["size"]) + layers
            if total < 0:
                raise ValueError("negative size")
        except (ValueError, KeyError, TypeError):
            return "unknown", None, False
        return "ok", total, False
    if code == 404:
        return ("cloud" if cloud else "missing"), None, False
    return "unknown", None, code in (403, 429)


# ── The fill ──────────────────────────────────────────────────────────────


def _fill_running() -> bool:
    if _fill is None or _fill.done():
        return False
    try:
        return _fill.get_loop() is asyncio.get_running_loop()
    except RuntimeError:
        return False


def _needs_fill(now: float) -> bool:
    if now < _cooldown_until:
        return False
    fetched = _library["fetched_at"] if _library else 0.0
    if now - max(fetched, _last_attempt) > _LISTING_TTL:
        return True
    if _library is None:
        return False
    return any(_needs_fetch(_key(e["name"]), now) for e in _library["entries"])


async def _fetch_listing() -> bool:
    """Fetch the page and ``/api/tags``, update the listing. True when the page parsed."""
    global _library, _last_attempt
    now = time.time()
    _last_attempt = now
    page: list[dict[str, Any]] = []
    tag_names: list[str] = []
    async with _new_client(timeout=_MANIFEST_TIMEOUT, follow_redirects=True) as client:
        try:
            resp = await client.get(LIBRARY_URL)
            resp.raise_for_status()
            page = parse_library_page(resp.text)
        except (httpx.HTTPError, OSError):
            logger.warning("Ollama library page fetch failed", exc_info=True)
        try:
            resp = await client.get(TAGS_URL)
            resp.raise_for_status()
            for m in resp.json().get("models", []):
                n = m.get("name") or m.get("model")
                if isinstance(n, str) and n:
                    tag_names.append(n)
        except (httpx.HTTPError, OSError, ValueError, AttributeError):
            logger.warning("Ollama tags fetch failed", exc_info=True)
    base = page or (_library["entries"] if _library else [])
    merged = _merge_tag_names(base, tag_names)
    if merged:
        fetched_at = now if page else (_library["fetched_at"] if _library else 0.0)
        _library = {"entries": merged, "fetched_at": fetched_at}
    if page:
        # Prune only after a successful page parse (never after a failed fetch).
        live = {_key(e["name"]) for e in merged}
        for key in [k for k in _sizes if k not in live]:
            del _sizes[key]
    return bool(page)


async def _fetch_one(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, entry: dict[str, Any]
) -> bool:
    name, tag = split_model(entry["name"])
    async with sem:
        status, size, hard = await _fetch_manifest(
            client, name, tag or "latest", bool(entry["cloud"])
        )
    _record(_key(entry["name"]), status, size)
    return hard


async def _settle(tasks: list[asyncio.Task[bool]], timeout: float) -> list[asyncio.Task[bool]]:
    """Wait up to ``timeout``; cancel the rest. Returns the finished tasks."""
    if not tasks:
        return []
    done: set[asyncio.Task[bool]] = set()
    try:
        done, _pending = await asyncio.wait(tasks, timeout=max(timeout, 0.0))
    finally:
        # Also runs when the fill itself is cancelled (shutdown_drain): no child task may
        # outlive this call, or the client closes underneath it.
        leftover = [t for t in tasks if not t.done()]
        for t in leftover:
            t.cancel()
        if leftover:
            await asyncio.gather(*leftover, return_exceptions=True)
    return [t for t in tasks if t in done]


async def _fill_body(path: Path) -> None:
    global _cooldown_until
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _BUDGET_S
    await _fetch_listing()
    _persist(path)  # the listing survives a later outage
    if _library is None:
        return
    now = time.time()
    todo = [e for e in _library["entries"] if _needs_fetch(_key(e["name"]), now)]
    if not todo:
        return
    sem = asyncio.Semaphore(_CONCURRENCY)
    async with _new_client(
        timeout=_MANIFEST_TIMEOUT,
        follow_redirects=False,
        limits=httpx.Limits(max_connections=_CONCURRENCY),
    ) as client:
        wave, rest = todo[:_CONCURRENCY], todo[_CONCURRENCY:]
        wave_tasks = [loop.create_task(_fetch_one(client, sem, e)) for e in wave]
        finished = await _settle(wave_tasks, deadline - loop.time())
        if (
            len(wave) == _CONCURRENCY
            and len(finished) == len(wave)
            and all(t.result() for t in finished)
        ):
            logger.warning("Ollama size fill stopped early: first %d requests failed", len(wave))
            _cooldown_until = time.time() + _COOLDOWN_S
            return
        rest_tasks = [loop.create_task(_fetch_one(client, sem, e)) for e in rest]
        await _settle(rest_tasks, deadline - loop.time())


async def _fill_main(path: Path) -> None:
    try:
        await _fill_body(path)
    except Exception:
        logger.exception("Ollama size fill failed")
    _persist(path)


def _ensure_fill() -> asyncio.Task[None]:
    global _fill, _fill_path
    if _fill_running():
        assert _fill is not None
        return _fill
    _fill_path = _cache_path()
    _fill = asyncio.get_running_loop().create_task(_fill_main(_fill_path))
    return _fill


# ── Seam ──────────────────────────────────────────────────────────────────


def _seam_catalog() -> list[dict[str, Any]] | None:
    """The ``THE_ONE_OLLAMA_LIBRARY_TEST_JSON`` catalog, only with dev mode on."""
    raw = os.environ.get(_SEAM_ENV)
    if not raw:
        return None
    from the_one.config import settings

    if not settings.dev_mode:
        logger.warning(
            "%s is set but dev_mode is False — the test seam is ignored. "
            "Unset the env var to silence this warning.",
            _SEAM_ENV,
        )
        return None
    try:
        models = json.loads(raw)["models"]
        return [
            {
                "name": str(m["name"]),
                "size": m.get("size") if m.get("status") == "ok" else None,
                "status": str(m["status"]),
            }
            for m in models
        ]
    except (ValueError, KeyError, TypeError, AttributeError):
        logger.warning("%s is not a valid catalog; serving an empty one", _SEAM_ENV)
        return []


def _filtered_sorted(models: list[dict[str, Any]], q: str) -> list[dict[str, Any]]:
    needle = (q or "").strip().lower()
    picked = [m for m in models if not needle or needle in m["name"].lower()]
    # Stable: groups by model name, keeps each model's tag order.
    return sorted(picked, key=lambda m: _model_part(m["name"]))


# ── Public API ────────────────────────────────────────────────────────────


def _snapshot(q: str) -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    if _library is not None:
        for e in _library["entries"]:
            known = _sizes.get(_key(e["name"]))
            if known is None:
                models.append({"name": e["name"], "size": None, "status": "unknown"})
            else:
                models.append(
                    {
                        "name": e["name"],
                        "size": known["size"] if known["status"] == "ok" else None,
                        "status": known["status"],
                    }
                )
    return _filtered_sorted(models, q)


async def search(q: str = "") -> dict[str, Any]:
    """The Pull list: ``{"loading": bool, "models": [{name, size, status}]}``. Never raises."""
    seam = _seam_catalog()
    if seam is not None:
        return {"loading": False, "models": _filtered_sorted(seam, q)}
    try:
        _load_disk()
        if _needs_fill(time.time()):
            task = _ensure_fill()
            # Shield: a cancelled waiter must not cancel the fill shared by everyone.
            await asyncio.wait({asyncio.shield(task)}, timeout=_WAIT_S)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Ollama library search failed")
    return {"loading": _fill_running(), "models": _snapshot(q)}


async def size(model: str) -> dict[str, Any]:
    """Re-check one entry's size. ``ValueError`` on an invalid model (the route's 422).

    Never joins, starts or cancels a fill, and never prunes.
    """
    requested = (model or "").strip()
    name, tag = split_model(requested)
    key = f"{name}:{tag or 'latest'}"
    seam = _seam_catalog()
    if seam is not None:
        for m in seam:
            try:
                if _key(m["name"]) == key:
                    return {"name": requested, "size": m["size"], "status": m["status"]}
            except ValueError:
                continue
        return {"name": requested, "size": None, "status": "missing"}
    _load_disk()
    cloud = bool(_sizes.get(key, {}).get("status") == "cloud")
    if _library is not None:
        cloud = cloud or any(e["cloud"] for e in _library["entries"] if _key(e["name"]) == key)
    async with _new_client(timeout=_SIZE_TIMEOUT, follow_redirects=False) as client:
        status, got, _hard = await _fetch_manifest(client, name, tag or "latest", cloud)
    entry = _record(key, status, got)
    _persist()
    return {
        "name": requested,
        "size": entry["size"] if entry["status"] == "ok" else None,
        "status": entry["status"],
    }


async def shutdown_drain() -> None:
    """Cancel a running fill and persist what settled. No-op otherwise."""
    task = _fill
    if task is None or task.done() or not _fill_running():
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task
    _persist(_fill_path)


def _reset_for_tests(cache_path: Path | None = None) -> None:
    """Cancel a pending fill, clear every cache and point the disk cache at ``cache_path``."""
    global _fill, _fill_path, _library, _loaded_from_disk, _cache_path_override
    global _last_attempt, _cooldown_until
    task = _fill
    if task is not None and not task.done():
        with contextlib.suppress(RuntimeError):
            if not task.get_loop().is_closed():
                task.cancel()
    _fill = None
    _fill_path = None
    _library = None
    _sizes.clear()
    _loaded_from_disk = False
    _last_attempt = 0.0
    _cooldown_until = 0.0
    _cache_path_override = cache_path
