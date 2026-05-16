"""Tests for F9 L2 vibing follow-up — runtime cache cleanup on source delete.

Covers:
  - extract_runtime_package decoder over the documented shape table.
  - _clean_uvx invokes ``uv cache prune`` (the env-scan was broken
    because uv stores environments-v2/<hash> as symlinks into archive-v0
    and Path.glob does not follow symlinks; prune is reachability-based
    and walks the symlink hop correctly).
  - _clean_npx removes a synthesized _npx slot whose package.json lists
    the package in dependencies (npx uses flat directories, not
    symlinks, so the directory walk works).
  - cleanup_runtime_cache swallows a hung subprocess via the outer
    asyncio.wait_for ceiling (no exception raised, returns).
  - cleanup_runtime_cache logs success at WARNING so outcomes surface
    under uvicorn's default root-logger threshold.
  - delete_mcp_source skips cleanup when another source still references
    the same (runtime, package) pair (refcount guard).
  - delete_mcp_source no-ops cleanup for unsupported runtimes
    (python/node/bash/Custom).
"""

from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository
from the_one.db.schema import ensure_schema
from the_one.encryption import Encryptor
from the_one.interfaces.web.api import router
from the_one.mcp import _pool, cache_cleanup
from the_one.mcp.cache_cleanup import (
    _clean_npx,
    cleanup_runtime_cache,
    extract_runtime_package,
)

# ── extract_runtime_package decoder table ────────────────────────────────


@pytest.mark.parametrize(
    "command,args,expected",
    [
        # uvx, single arg = package
        ("uvx", ["mcp-server-time"], ("uvx", "mcp-server-time")),
        # uvx --from indirection
        (
            "uvx",
            ["--from", "mcp-server-time", "mcp-server-time"],
            ("uvx", "mcp-server-time"),
        ),
        # uvx with PEP 440 version pin
        ("uvx", ["mcp-server-time==1.2.3"], ("uvx", "mcp-server-time")),
        # uvx --from with version pin
        (
            "uvx",
            ["--from", "mcp-server-time==1.2.3", "mcp-server-time"],
            ("uvx", "mcp-server-time"),
        ),
        # npx -y + scoped package
        ("npx", ["-y", "@scope/pkg"], ("npx", "@scope/pkg")),
        # npx without -y
        ("npx", ["@scope/pkg"], ("npx", "@scope/pkg")),
        # npx -y with scoped package + version pin (the @1.2.3 suffix)
        ("npx", ["-y", "@scope/pkg@1.2.3"], ("npx", "@scope/pkg")),
        # npx unscoped with version pin
        ("npx", ["pkg@1.0"], ("npx", "pkg")),
        # pipx run + package (post Part B's split)
        ("pipx", ["run", "mcp-server-time"], ("pipx", "mcp-server-time")),
        # pipx run with version pin
        ("pipx", ["run", "mcp-server-time==1.2.3"], ("pipx", "mcp-server-time")),
        # python -m foo: not a lazy-install runtime → None
        ("python", ["-m", "foo"], (None, None)),
        # node script: not a lazy-install runtime → None
        ("node", ["/app/server.js"], (None, None)),
        # bash wrapper: not a lazy-install runtime → None
        ("bash", ["/app/run.sh"], (None, None)),
        # Custom binary: not in the recognized set → None
        ("custom-cmd", ["--flag"], (None, None)),
        # uvx with empty args → can't extract
        ("uvx", [], (None, None)),
        # npx with empty args → can't extract
        ("npx", [], (None, None)),
        # pipx without `run` subcommand → not a lazy-install pattern
        ("pipx", ["install", "foo"], (None, None)),
        # pipx run with no package arg → can't extract
        ("pipx", ["run"], (None, None)),
        # uvx --from with too few args → falls through to first-arg path,
        # which would be `--from` itself (literal). This is operator
        # mis-config; we don't normalize it — it just won't match any
        # cache slot and that's fine.
        ("uvx", ["--from"], ("uvx", "--from")),
    ],
)
def test_extract_runtime_package_table(command: str, args: list[str], expected: tuple) -> None:
    assert extract_runtime_package(command, args) == expected


# ── _clean_uvx invokes `uv cache prune` ──────────────────────────────────


@pytest.mark.asyncio
async def test_cleanup_uvx_invokes_uv_cache_prune(monkeypatch) -> None:
    """``_clean_uvx`` must shell out to ``uv cache prune`` (NOT
    ``uv cache clean <pkg>`` and NOT a Path.glob env-scan).

    Reachability-based pruning is the only primitive that correctly
    handles uv's symlink layout (environments-v2/<hash> -> archive-v0/
    <content-hash>); the prior implementations silently no-op'd because
    Path.glob does not follow symlinks.
    """
    captured_args: list[tuple] = []

    async def _fake_exec(*args, **kwargs):
        captured_args.append(args)
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(b"Removed 3957 files (65.2 MiB)", b""))
        proc.kill = lambda: None
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    await cache_cleanup._clean_uvx("mcp-server-time")

    assert len(captured_args) == 1, "exactly one subprocess invocation expected"
    assert captured_args[0] == ("uv", "cache", "prune"), (
        f"expected `uv cache prune` (no per-package arg, prune is "
        f"reachability-based); got {captured_args[0]}"
    )


@pytest.mark.asyncio
async def test_cleanup_uvx_handles_missing_uv_binary(monkeypatch) -> None:
    """If the ``uv`` binary is not on PATH (e.g. dev container without
    uv installed), ``_clean_uvx`` must log + return, not raise."""

    async def _fake_exec(*args, **kwargs):
        raise FileNotFoundError("uv: command not found")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    # Must not raise.
    await cache_cleanup._clean_uvx("anything")


@pytest.mark.asyncio
async def test_cleanup_uvx_handles_prune_timeout(monkeypatch) -> None:
    """If ``uv cache prune`` hangs past the per-subprocess ceiling,
    ``_clean_uvx`` must kill the proc and return without raising."""

    async def _hang(*_a, **_kw):
        await asyncio.sleep(60)

    kill_called = {"count": 0}

    async def _fake_exec(*args, **kwargs):
        proc = AsyncMock()
        proc.communicate = AsyncMock(side_effect=_hang)

        def _kill():
            kill_called["count"] += 1

        proc.kill = _kill
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
    # Drop the per-subprocess timeout so the test runs fast.
    monkeypatch.setattr(cache_cleanup, "_UV_CACHE_PRUNE_TIMEOUT_S", 0.05)

    loop = asyncio.get_event_loop()
    start = loop.time()
    await cache_cleanup._clean_uvx("anything")
    elapsed = loop.time() - start

    assert elapsed < 2.0, f"timeout not honored ({elapsed:.2f}s)"
    assert kill_called["count"] >= 1, "hung process should have been killed"


# ── _clean_npx slot scan ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cleanup_npx_removes_slot(tmp_path, monkeypatch) -> None:
    """Synthesize a fake _npx/<hash>/package.json with the package in
    dependencies; assert the slot is removed."""
    fake_root = tmp_path / "_npx"
    fake_root.mkdir()

    # Slot 1: matches.
    slot_1 = fake_root / "hash1"
    slot_1.mkdir()
    (slot_1 / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {
                    "@modelcontextprotocol/server-everything": "^1.0.0",
                }
            }
        )
    )

    # Slot 2: different package, must NOT be removed.
    slot_2 = fake_root / "hash2"
    slot_2.mkdir()
    (slot_2 / "package.json").write_text(
        json.dumps({"dependencies": {"@scope/different-pkg": "^1.0.0"}})
    )

    # Slot 3: missing package.json, fallback path via node_modules.
    slot_3 = fake_root / "hash3"
    nm = slot_3 / "node_modules" / "@modelcontextprotocol/server-everything"
    nm.mkdir(parents=True)
    (nm / "package.json").write_text(
        json.dumps({"name": "@modelcontextprotocol/server-everything"})
    )

    monkeypatch.setattr(cache_cleanup, "NPX_CACHE_ROOT", fake_root)

    await cache_cleanup._clean_npx("@modelcontextprotocol/server-everything")

    assert not slot_1.exists(), "matching slot should be removed"
    assert slot_2.exists(), "non-matching slot must be preserved"
    assert not slot_3.exists(), "fallback-matched slot should be removed"


@pytest.mark.asyncio
async def test_cleanup_npx_handles_corrupt_package_json(tmp_path, monkeypatch) -> None:
    """A slot with corrupt package.json should not raise; if the fallback
    node_modules path matches, the slot is still cleaned."""
    fake_root = tmp_path / "_npx"
    fake_root.mkdir()

    slot = fake_root / "corrupt"
    nm = slot / "node_modules" / "@scope/pkg"
    nm.mkdir(parents=True)
    (nm / "package.json").write_text("{}")
    (slot / "package.json").write_text("not valid json {{{")

    monkeypatch.setattr(cache_cleanup, "NPX_CACHE_ROOT", fake_root)

    # Must not raise.
    await cache_cleanup._clean_npx("@scope/pkg")
    assert not slot.exists()


# ── cleanup_runtime_cache: timeout + swallow semantics ───────────────────


@pytest.mark.asyncio
async def test_cleanup_swallows_subprocess_timeout(monkeypatch) -> None:
    """If the per-runtime helper hangs, the outer wait_for must enforce
    the timeout, log, and return — never raise."""

    async def _hung_helper(pkg: str) -> None:
        await asyncio.sleep(60)  # would block forever vs. our timeout

    monkeypatch.setattr(cache_cleanup, "_clean_uvx", _hung_helper)

    # Wrapping returns within timeout_s + small buffer (use a tight 0.1s
    # ceiling for the test). Must complete within 1s wall-clock total.
    loop = asyncio.get_event_loop()
    start = loop.time()
    await cleanup_runtime_cache("uvx", "some-pkg", timeout_s=0.1)
    elapsed = loop.time() - start
    assert elapsed < 1.0, f"cleanup did not honor timeout ceiling ({elapsed:.2f}s)"


@pytest.mark.asyncio
async def test_cleanup_swallows_helper_exception(monkeypatch) -> None:
    """If the helper raises, cleanup_runtime_cache logs + returns; the
    operator-facing delete already committed."""

    async def _raising_helper(pkg: str) -> None:
        raise RuntimeError("simulated cache-clean explosion")

    monkeypatch.setattr(cache_cleanup, "_clean_uvx", _raising_helper)

    # Must not raise.
    await cleanup_runtime_cache("uvx", "some-pkg", timeout_s=5.0)


@pytest.mark.asyncio
async def test_cleanup_unsupported_runtime_no_op() -> None:
    """A runtime string that doesn't match uvx/npx/pipx is a logged
    no-op, not an error."""
    # Must not raise.
    await cleanup_runtime_cache("docker", "some-pkg", timeout_s=1.0)


@pytest.mark.asyncio
async def test_cleanup_logs_completion_at_warning(monkeypatch, caplog) -> None:
    """Cleanup outcomes must surface at WARNING (not INFO) so they're
    visible under uvicorn's default root-logger threshold without
    operators having to lower the bar globally."""

    async def _noop_helper(pkg: str) -> None:
        return None

    monkeypatch.setattr(cache_cleanup, "_clean_uvx", _noop_helper)

    with caplog.at_level(logging.WARNING, logger="the_one.mcp.cache_cleanup"):
        await cleanup_runtime_cache("uvx", "some-pkg", timeout_s=5.0)

    completion_records = [
        r
        for r in caplog.records
        if r.name == "the_one.mcp.cache_cleanup"
        and r.levelno == logging.WARNING
        and "completed" in r.getMessage()
    ]
    assert completion_records, (
        "cleanup completion should be logged at WARNING so operators see "
        "it under uvicorn's default threshold"
    )


@pytest.mark.asyncio
async def test_clean_uvx_logs_prune_output_at_warning(monkeypatch, caplog) -> None:
    """``_clean_uvx`` must surface ``uv cache prune`` stdout at WARNING
    so the bytes-reclaimed line lands in the operator-visible log."""

    async def _fake_exec(*args, **kwargs):
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(b"Removed 3957 files (65.2 MiB)", b""))
        proc.kill = lambda: None
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    with caplog.at_level(logging.WARNING, logger="the_one.mcp.cache_cleanup"):
        await cache_cleanup._clean_uvx("mcp-server-time")

    prune_records = [
        r
        for r in caplog.records
        if r.name == "the_one.mcp.cache_cleanup"
        and r.levelno == logging.WARNING
        and "uv cache prune completed" in r.getMessage()
    ]
    assert prune_records, "prune completion line missing at WARNING"
    assert "65.2 MiB" in prune_records[0].getMessage(), (
        "prune stdout should be embedded so operators see what was reclaimed"
    )


@pytest.mark.asyncio
async def test_cleanup_pipx_delegates_to_uvx(monkeypatch) -> None:
    """pipx 1.12 in this container shells out to ``uv tool run``, so the
    cleanup path is the same as uvx."""
    captured: list[str] = []

    async def _fake_clean_uvx(pkg: str) -> None:
        captured.append(pkg)

    monkeypatch.setattr(cache_cleanup, "_clean_uvx", _fake_clean_uvx)
    await cleanup_runtime_cache("pipx", "some-pkg", timeout_s=5.0)
    assert captured == ["some-pkg"]


# ── End-to-end via DELETE handler: refcount + dispatch ───────────────────


@pytest.fixture(autouse=True)
async def _clear_pool():
    """Reset the F4 pool between tests so eviction-counts don't bleed."""
    await _pool._clear_for_test()
    yield
    await _pool._clear_for_test()


@pytest.fixture
async def client_and_repo(tmp_path):
    """FastAPI client + back-channel repo. Mirrors test_mcp_connection_reset."""
    db_path = tmp_path / "delete.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "test.key")
    repo = MCPSourceRepository(conn, encryptor)

    with (
        patch("the_one.interfaces.web.api.get_connection", return_value=conn),
        patch("the_one.interfaces.web.api.get_encryptor", return_value=encryptor),
    ):
        test_app = FastAPI()
        test_app.include_router(router)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, repo

    await conn.close()


async def _seed_stdio(
    repo: MCPSourceRepository, sid: str, *, command: str, args: list[str]
) -> None:
    await repo.create(
        MCPSource(
            id=sid,
            name=f"Source-{sid}",
            type="stdio",
            config={"command": command, "args": args},
            secrets={},
        )
    )


@pytest.mark.asyncio
async def test_refcount_guard_skips_cleanup(client_and_repo) -> None:
    """Two sources share (uvx, mcp-server-time); deleting one must NOT
    invoke cleanup_runtime_cache — the survivor still needs the cache.
    """
    client, repo = client_and_repo
    await _seed_stdio(repo, "alpha", command="uvx", args=["mcp-server-time"])
    await _seed_stdio(repo, "bravo", command="uvx", args=["mcp-server-time"])

    with patch(
        "the_one.mcp.cache_cleanup.cleanup_runtime_cache",
        new_callable=AsyncMock,
    ) as mock_cleanup:
        resp = await client.delete("/api/mcp-sources/alpha")
        assert resp.status_code == 200
        mock_cleanup.assert_not_called()

    # The survivor row is still present.
    survivor = await repo.get("bravo")
    assert survivor.config["command"] == "uvx"


@pytest.mark.asyncio
async def test_unsupported_runtime_no_cleanup_invoked(client_and_repo) -> None:
    """A source with command=python args=[-m, foo] is not a lazy-install
    runtime — extract_runtime_package returns (None, None) and the
    handler must NOT call cleanup_runtime_cache."""
    client, repo = client_and_repo
    await _seed_stdio(repo, "p1", command="python", args=["-m", "foo"])

    with patch(
        "the_one.mcp.cache_cleanup.cleanup_runtime_cache",
        new_callable=AsyncMock,
    ) as mock_cleanup:
        resp = await client.delete("/api/mcp-sources/p1")
        assert resp.status_code == 200
        mock_cleanup.assert_not_called()


@pytest.mark.asyncio
async def test_supported_runtime_invokes_cleanup(client_and_repo) -> None:
    """Sole source with (uvx, mcp-server-time): delete must invoke
    cleanup_runtime_cache exactly once with the decoded pair."""
    client, repo = client_and_repo
    await _seed_stdio(repo, "solo", command="uvx", args=["mcp-server-time"])

    with patch(
        "the_one.mcp.cache_cleanup.cleanup_runtime_cache",
        new_callable=AsyncMock,
    ) as mock_cleanup:
        resp = await client.delete("/api/mcp-sources/solo")
        assert resp.status_code == 200
        mock_cleanup.assert_awaited_once_with("uvx", "mcp-server-time")


@pytest.mark.asyncio
async def test_pipx_run_split_shape_invokes_cleanup(client_and_repo) -> None:
    """A source saved with the post-Part-B split (command='pipx',
    args=['run', 'pkg']) must decode to ('pipx', 'pkg') and trigger
    cleanup. This is the contract that ties Part A's decoder to Part B's
    save shape."""
    client, repo = client_and_repo
    await _seed_stdio(repo, "px1", command="pipx", args=["run", "mcp-server-time"])

    with patch(
        "the_one.mcp.cache_cleanup.cleanup_runtime_cache",
        new_callable=AsyncMock,
    ) as mock_cleanup:
        resp = await client.delete("/api/mcp-sources/px1")
        assert resp.status_code == 200
        mock_cleanup.assert_awaited_once_with("pipx", "mcp-server-time")


@pytest.mark.asyncio
async def test_npx_y_split_shape_invokes_cleanup(client_and_repo) -> None:
    """Sanity: npx -y split (command='npx', args=['-y', '@scope/pkg'])
    decodes to ('npx', '@scope/pkg') and triggers cleanup."""
    client, repo = client_and_repo
    await _seed_stdio(repo, "n1", command="npx", args=["-y", "@scope/pkg"])

    with patch(
        "the_one.mcp.cache_cleanup.cleanup_runtime_cache",
        new_callable=AsyncMock,
    ) as mock_cleanup:
        resp = await client.delete("/api/mcp-sources/n1")
        assert resp.status_code == 200
        mock_cleanup.assert_awaited_once_with("npx", "@scope/pkg")


@pytest.mark.asyncio
async def test_delete_404_short_circuits(client_and_repo) -> None:
    """Deleting an unknown source must 404 cleanly without invoking
    cleanup."""
    client, _repo = client_and_repo

    with patch(
        "the_one.mcp.cache_cleanup.cleanup_runtime_cache",
        new_callable=AsyncMock,
    ) as mock_cleanup:
        resp = await client.delete("/api/mcp-sources/nonexistent")
        assert resp.status_code == 404
        mock_cleanup.assert_not_called()


@pytest.mark.asyncio
async def test_find_by_runtime_package_returns_matches(tmp_path) -> None:
    """Direct repo-level test of find_by_runtime_package decoding."""
    db_path = tmp_path / "find.db"
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys=ON")
    await ensure_schema(conn)
    encryptor = Encryptor(Fernet.generate_key(), key_path=tmp_path / "k.key")
    repo = MCPSourceRepository(conn, encryptor)

    try:
        await _seed_stdio(repo, "a", command="uvx", args=["pkg-x"])
        await _seed_stdio(repo, "b", command="uvx", args=["pkg-x"])
        await _seed_stdio(repo, "c", command="uvx", args=["pkg-y"])
        await _seed_stdio(repo, "d", command="python", args=["-m", "pkg-x"])

        # Looking for siblings of `a`: only `b` shares (uvx, pkg-x).
        matches = await repo.find_by_runtime_package("uvx", "pkg-x", "a")
        assert {m.id for m in matches} == {"b"}

        # No siblings for the lone (uvx, pkg-y) source.
        matches_y = await repo.find_by_runtime_package("uvx", "pkg-y", "c")
        assert matches_y == []
    finally:
        await conn.close()


# ── _clean_npx package-name allowlist (Leg 03 security sweep) ────────────


@pytest.mark.parametrize(
    "pkg",
    [
        "lodash",
        "@types/node",
        "@scope/pkg",
        "pkg-with-dashes",
        "pkg_with_underscores",
        "a",
        "abc123",
        "@a/b",
    ],
)
@pytest.mark.asyncio
async def test_clean_npx_accepts_valid_npm_package_names(pkg, monkeypatch) -> None:
    """The npm-spec allowlist must accept syntactically-valid package names.

    The function still no-ops (NPX_CACHE_ROOT.exists() is False in the test
    environment), but the important thing is the validation does NOT raise.
    """
    # Force NPX_CACHE_ROOT.exists() False so we only exercise the validator.
    monkeypatch.setattr(
        cache_cleanup,
        "NPX_CACHE_ROOT",
        cache_cleanup.Path("/nonexistent-npx-root"),
    )
    await _clean_npx(pkg)  # must not raise


@pytest.mark.parametrize(
    "pkg",
    [
        "../etc/passwd",  # path traversal — the vector the original allowlist missed
        "a/b/c",  # deep path (only scoped `@x/y` allowed)
        ".hidden",  # leading dot
        "-leading-dash",  # leading dash
        "Foo",  # uppercase (npm spec is lowercase-only)
        "pkg;name",  # shell metacharacter
        "pkg name",  # whitespace
        "pkg\nname",  # newline
        "",  # empty
        "@/x",  # malformed scope
        "@scope/",  # missing name after scope
    ],
)
@pytest.mark.asyncio
async def test_clean_npx_rejects_unsafe_inputs(pkg) -> None:
    """The npm-spec allowlist must raise ValueError for unsafe inputs.

    Specifically: ``../etc/passwd`` and ``a/b/c`` were allowed by the
    previous draft's ``[A-Za-z0-9._@/-]`` character-class allowlist —
    every individual character in those strings is in that set. The
    tightened regex pins ``/`` to the post-scope position and rejects
    leading dots / uppercase / shell metachars, closing the traversal
    vector at the function entry.
    """
    with pytest.raises(ValueError, match="unsafe npx package name"):
        await _clean_npx(pkg)
