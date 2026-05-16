"""Per-runtime cache cleanup for deleted MCP sources.

F9 L2 vibing follow-up: when an operator deletes a stdio MCP source whose
``config.command`` resolves to a lazy-install runtime (``uvx``, ``npx``,
``pipx run``), the package cache that was downloaded on first spawn lives
on in the container filesystem indefinitely. This module provides
extraction + best-effort cleanup so that "delete the source" also reclaims
the cache slot.

Design notes (architect-approved):

- **Decoder is pure.** :func:`extract_runtime_package` returns
  ``(runtime, package)`` for known shapes and ``(None, None)`` otherwise.
  It does NOT decide whether to clean — the caller (the delete handler)
  refcounts against other sources first.
- **Cleanup never raises.** :func:`cleanup_runtime_cache` swallows every
  exception, logs the outcome, and returns. The DB delete has already
  committed by the time cleanup runs; a hung ``uv cache prune`` or a
  missing slot directory must not regress the user-facing "delete worked"
  signal. The wrapper imposes an outer ``asyncio.wait_for`` ceiling so
  even a wedged subprocess cannot pin the request thread.
- **uvx uses prune, not env-scan.** Earlier iterations walked
  ``environments-v2/`` looking for site-packages matches. That broke
  silently because uv stores each env hash as a symlink into
  ``archive-v0/``, and ``Path.glob`` does NOT follow symlinks. The
  fix shells out to ``uv cache prune``: a reachability-based GC that
  follows the symlink hop, marks live archive entries from existing
  envs, and reaps everything else (including orphan archive entries
  from prior failed installs). After the caller's refcount guard +
  ``repo.delete``, the env hash for the deleted source is provably
  unreachable, so prune sweeps it cleanly.
- **pipx delegates to uv.** pipx 1.12 in this container shells out to
  ``uv tool run``; the cache that ``pipx run <pkg>`` writes lives under
  ``/root/.cache/uv/environments-v2``, the same place ``uvx`` populates.
  :func:`_clean_pipx` therefore forwards to :func:`_clean_uvx`.
- **Operator visibility.** Cleanup outcomes log at WARNING (not INFO)
  so they surface in ``docker compose logs the-one`` under uvicorn's
  default root-logger threshold, without forcing operators to lower
  the threshold globally.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# Inner subprocess timeout for `uv cache prune`. The outer
# `cleanup_runtime_cache` wait_for ceiling is the request-blocking budget;
# this is just the per-subprocess bound so the helper noticeably moves on
# rather than waiting for the outer kill.
_UV_CACHE_PRUNE_TIMEOUT_S: float = 8.0

# Filesystem roots — module-level so tests can monkeypatch.
# ``UV_ENVIRONMENTS_ROOT`` is retained for backward compatibility and for
# the npx cache scan's mirror layout, but ``_clean_uvx`` no longer walks
# this path: uv stores environments-v2/<hash> as symlinks into archive-v0,
# and ``Path.glob`` does NOT follow symlinks (so the previous env-scan
# silently failed to match). ``uv cache prune`` walks reachability across
# the symlink hop and is the correct primitive for reclaiming env slots.
UV_ENVIRONMENTS_ROOT = Path("/root/.cache/uv/environments-v2")
NPX_CACHE_ROOT = Path("/root/.npm/_npx")


def _strip_version_pin(spec: str) -> str:
    """Strip a PEP 440 ``==`` or ``@`` version pin suffix from a package spec.

    Examples
    --------
    ``mcp-server-time==1.2.3`` -> ``mcp-server-time``
    ``@scope/pkg@1.2.3`` -> ``@scope/pkg``  (npm scope prefix preserved)
    ``pkg`` -> ``pkg``
    """
    if not spec:
        return spec
    # Handle `pkg==X` first (PyPI).
    if "==" in spec:
        return spec.split("==", 1)[0]
    # Handle `@scope/pkg@version` (npm) and `pkg@version`. The first `@`
    # at index 0 is part of an npm scope and must be preserved; only `@`
    # after position 0 marks the version pin.
    at_idx = spec.find("@", 1)
    if at_idx > 0:
        return spec[:at_idx]
    return spec


def extract_runtime_package(
    command: str, args: list[str]
) -> tuple[Literal["uvx", "npx", "pipx"] | None, str | None]:
    """Decode a saved (command, args) pair into (runtime, package) if known.

    Pure function — no I/O, no side effects.

    Returns ``(None, None)`` for any shape that does NOT match a known
    lazy-install runtime (python/node/bash/Custom or unrecognized
    commands). The caller treats that as "no cleanup applicable".

    Decoding rules
    --------------
    - ``command == "uvx"``:
      - If ``args[0] == "--from"`` and ``len(args) >= 3``: package is
        ``args[1]`` with version-pin stripped.
      - Otherwise: package is ``args[0]`` with version-pin stripped.
    - ``command == "npx"``:
      - If ``args[0] == "-y"`` and ``len(args) >= 2``: package is
        ``args[1]`` with version-pin stripped (npm scope ``@`` preserved).
      - Otherwise: package is ``args[0]`` with version-pin stripped.
    - ``command == "pipx"`` AND ``args[0] == "run"``: package is
      ``args[1]`` with version-pin stripped.
    - Anything else: ``(None, None)``.
    """
    args_list = list(args) if args else []

    if command == "uvx":
        if not args_list:
            return (None, None)
        if args_list[0] == "--from" and len(args_list) >= 3:
            return ("uvx", _strip_version_pin(args_list[1]))
        return ("uvx", _strip_version_pin(args_list[0]))

    if command == "npx":
        if not args_list:
            return (None, None)
        if args_list[0] == "-y" and len(args_list) >= 2:
            return ("npx", _strip_version_pin(args_list[1]))
        return ("npx", _strip_version_pin(args_list[0]))

    if command == "pipx":
        if len(args_list) >= 2 and args_list[0] == "run":
            return ("pipx", _strip_version_pin(args_list[1]))
        return (None, None)

    return (None, None)


async def _clean_uvx(pkg: str) -> None:
    """Best-effort cleanup of uvx cache after the source for ``pkg`` is gone.

    Fires ``uv cache prune`` — uv's reachability-based GC pass. Walks
    every ``environments-v2/<hash>`` env, follows the symlink into
    ``archive-v0/<content-hash>``, marks reachable, and removes orphan
    archive entries. Bounded by ``_UV_CACHE_PRUNE_TIMEOUT_S`` so a hung
    subprocess can't pin us.

    Why prune (and not ``uv cache clean <pkg>`` + env-scan)?

    - ``uv cache clean <pkg>`` targets the wheel/simple metadata cache,
      not env slots — the empirical probe showed it cleared 0 bytes for
      the env hash we were trying to reclaim.
    - ``Path.glob`` does NOT follow symlinks, and uv stores each
      ``environments-v2/<hash>`` as a symlink into ``archive-v0/``. The
      previous env-scan silently matched zero entries and left the cache
      pinned indefinitely.
    - Prune is reachability-based: now that the source row is deleted
      (caller orders prune AFTER ``repo.delete``) and the refcount guard
      confirmed no other source references this package, the env hash
      dir is provably unreachable. Prune sweeps it, the archive entry
      it pointed to, AND any orphan archive entries from prior failed
      install attempts (e.g. an earlier ``mcp_server_time`` underscore
      typo). Other operators' active envs stay reachable and untouched.

    The ``pkg`` argument is retained for log context; ``uv cache prune``
    is package-agnostic by design.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "uv",
            "cache",
            "prune",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.warning("uv binary not on PATH; skipping `uv cache prune` for %s", pkg)
        return
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("`uv cache prune` failed to start for %s: %s", pkg, e)
        return

    try:
        stdout, _stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_UV_CACHE_PRUNE_TIMEOUT_S
        )
        logger.warning(
            "uv cache prune completed for delete of %s: %s",
            pkg,
            (stdout or b"").decode("utf-8", "replace").strip() or "<no output>",
        )
    except asyncio.TimeoutError:
        logger.warning(
            "uv cache prune timed out after %.1fs for %s; killing",
            _UV_CACHE_PRUNE_TIMEOUT_S,
            pkg,
        )
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        # Best-effort drain so the child doesn't linger as a zombie.
        with contextlib.suppress(BaseException):
            await asyncio.wait_for(proc.communicate(), timeout=1.0)
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("`uv cache prune` failed for %s: %s", pkg, e)


async def _clean_npx(pkg: str) -> None:
    """Best-effort cleanup of npx cache slots for ``pkg``.

    Each ``/root/.npm/_npx/<hash>/`` slot is a flat directory (NOT
    symlink-based, unlike uv's archive-v0 layout) with a ``package.json``
    listing the package(s) installed there in ``dependencies``. Walking
    these with ``Path.iterdir`` works correctly. Defensive fallback: if
    the root ``package.json`` is missing/corrupt, check
    ``node_modules/<pkg>/package.json``.
    """
    try:
        if not NPX_CACHE_ROOT.exists():
            return
        for slot_dir in NPX_CACHE_ROOT.iterdir():
            if not slot_dir.is_dir():
                continue
            matched = False
            slot_pkg_json = slot_dir / "package.json"
            if slot_pkg_json.exists():
                try:
                    data = json.loads(slot_pkg_json.read_text(encoding="utf-8"))
                    deps = data.get("dependencies") or {}
                    if pkg in deps:
                        matched = True
                except (json.JSONDecodeError, OSError) as e:
                    logger.debug(
                        "npx slot %s has unreadable package.json (%s); falling back",
                        slot_dir,
                        e,
                    )

            if not matched:
                # Defensive fallback: check node_modules/<pkg>/package.json
                node_modules_pkg = slot_dir / "node_modules" / pkg / "package.json"
                if node_modules_pkg.exists():
                    matched = True

            if matched:
                logger.warning("Removing npx slot %s (matches package %s)", slot_dir, pkg)
                shutil.rmtree(slot_dir, ignore_errors=True)
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("npx cache scan failed for %s: %s", pkg, e)


async def _clean_pipx(pkg: str) -> None:
    """pipx 1.12 delegates to ``uv tool run``; reuse the uvx cleanup path."""
    await _clean_uvx(pkg)


async def cleanup_runtime_cache(runtime: str, package: str, *, timeout_s: float = 10.0) -> None:
    """Dispatch to the per-runtime cleanup helper, swallowing all errors.

    Logs at WARNING on success/no-op/failure so cleanup outcomes surface
    in ``docker compose logs`` without operators having to lower the
    root logger threshold below uvicorn's default WARNING. WARNING isn't
    semantically perfect for "operation succeeded normally" — we use it
    purely for visibility (the alternative would be a structured
    response field, which is out of scope per the silent-UX decision).
    Bounded by ``timeout_s`` so a wedged subprocess cannot pin the
    calling request.

    Architect: "cleanup failures log + swallow" — never raises, even on
    BaseException-derived (e.g. ``asyncio.CancelledError``,
    ``KeyboardInterrupt``). The DB delete is already committed by the
    time we run; the operator-facing "delete worked" signal must not
    regress on a stale cache GC.
    """
    try:
        if runtime == "uvx":
            inner = _clean_uvx(package)
        elif runtime == "npx":
            inner = _clean_npx(package)
        elif runtime == "pipx":
            inner = _clean_pipx(package)
        else:
            logger.warning("cleanup_runtime_cache: unsupported runtime %r; no-op", runtime)
            return

        try:
            await asyncio.wait_for(inner, timeout=timeout_s)
        except asyncio.TimeoutError:
            logger.warning(
                "cleanup_runtime_cache(%s, %s) exceeded %.1fs; abandoned",
                runtime,
                package,
                timeout_s,
            )
            return

        logger.warning("cleanup_runtime_cache(%s, %s) completed", runtime, package)
    except BaseException as e:  # noqa: BLE001 — architect: swallow everything
        logger.warning(
            "cleanup_runtime_cache(%s, %s) swallowed %s: %s",
            runtime,
            package,
            type(e).__name__,
            e,
        )
