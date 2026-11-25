"""The MCP write service and its repository hooks (Mission 36 F4 L4a, DD9).

``update_in_txn`` (re-read inside the write transaction), ``create`` / ``replace`` / ``change``
in ``the_one/mcp/service.py``, the secret-looking key rule, and the import boundary.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db import _write_lock
from the_one.db._write_lock import write_transaction
from the_one.db.models import MCPSource
from the_one.db.repositories import MCPSourceRepository, SecretRepository, SQLiteAgentStore
from the_one.encryption import get_encryptor
from the_one.mcp import service as svc
from the_one.mcp.oauth.storage import MCPSourceTokenStorage

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
async def world(tmp_path):
    _write_lock.reset_for_test()
    conn = await connect_template_db(tmp_path / "svc.db")
    enc = get_encryptor(tmp_path)
    repo = MCPSourceRepository(conn, enc)
    store = SQLiteAgentStore(conn, enc)
    secrets = SecretRepository(conn, enc)

    async def agent_store():
        return store

    async def secret_repo():
        return secrets

    ns = SimpleNamespace(
        conn=conn,
        enc=enc,
        repo=repo,
        store=store,
        deps=svc.McpWriteDeps(repo=repo, agent_store=agent_store, secret_repo=secret_repo),
    )
    yield ns
    await conn.close()


async def make_http(world, **kw) -> MCPSource:
    body = {
        "id": "h1",
        "name": "Docs",
        "type": "streamable-http",
        "config": {"url": "https://mcp.example.com/a", "headers": {"Accept": "text/plain"}},
        "secrets": {"Authorization": "Bearer-secret-value-1234"},
    }
    body.update(kw)
    source = MCPSource.model_validate(body)
    await world.repo.create(source)
    return source


async def make_stdio(world, **kw) -> MCPSource:
    body = {
        "id": "s1",
        "name": "Local",
        "type": "stdio",
        "config": {
            "command": "npx",
            "args": ["-y", "pkg"],
            "env": {"LOG_LEVEL": "info"},
            "cwd": "/home/x/work",
            "sandbox": {"network_allowed": False},
        },
        "secrets": {"MY_SETTING": "sensitive-value-1234"},
    }
    body.update(kw)
    source = MCPSource.model_validate(body)
    await world.repo.create(source)
    return source


@pytest.fixture
def effects(monkeypatch):
    """Spy on every post-commit side effect, in order."""
    log: list[tuple] = []

    async def evict(source_id):
        log.append(("evict", source_id))

    async def carry(source_id, old, new, *, agent_store, mcp_repo):
        log.append(("carry", source_id, old, new))
        return []

    async def carry_secrets(old, new, *, secret_repo, mcp_repo):
        log.append(("carry_secrets", old, new))

    async def drop(repo, source_id):
        log.append(("drop", source_id))

    monkeypatch.setattr("the_one.mcp._pool._evict_all_for_source", evict)
    monkeypatch.setattr("the_one.mcp.rename_references.carry_mcp_rename", carry)
    monkeypatch.setattr(
        "the_one.mcp.rename_references.carry_mcp_rename_into_secrets", carry_secrets
    )
    monkeypatch.setattr(svc, "drop_source_agent_tool_cache", drop)
    monkeypatch.setattr(svc, "forget_era", lambda sid: log.append(("era", sid)))
    return log


# --- AC2: the import boundary -----------------------------------------------------------


def test_the_service_imports_no_interface_layer() -> None:
    tree = ast.parse((ROOT / "the_one" / "mcp" / "service.py").read_text())
    banned = ("fastapi", "starlette", "the_one.interfaces", "the_one.gleepglorp")
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        assert not any(n == b or n.startswith(b + ".") for n in names for b in banned), names


# --- the secret-looking key rule (one algorithm, pinned by a table) ----------------------


@pytest.mark.parametrize(
    "name",
    [
        "Authorization",
        "X-Api-Key",
        "apiKey",
        "accessKey",
        "GITHUB_TOKEN",
        "DB_PASSWORD",
        "PRIVATE_KEY",
        "--api-key",
        # accepted false positives (one handoff each)
        "X-Request-Key-Id",
        "MAX_TOKENS",
    ],
)
def test_secret_looking_names(name) -> None:
    assert svc.looks_secret_key(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "Accept",
        "KEYBOARD_LAYOUT",
        "MONKEY",
        "TOKENIZERS_PARALLELISM",
        "PRIVATE_NETWORK",
        "LOG_LEVEL",
    ],
)
def test_not_secret_looking_names(name) -> None:
    assert svc.looks_secret_key(name) is False


@pytest.mark.parametrize(
    ("args", "flag"),
    [
        (["--token=abc123"], "token"),
        (["-token=abc123"], "token"),
        (["--api-key", "abc123"], "api-key"),
        (["-y", "pkg", "--password=x"], "password"),
        (["--token="], None),  # an empty value is the handoff, not a secret
        (["--token"], None),
        (["--token", "--other"], None),  # the next item is a flag, not a value
        (["-y", "pkg", "--verbose"], None),
        (["--keyboard=us"], None),
    ],
)
def test_secret_args_flags(args, flag) -> None:
    assert svc.secret_args_flag(args) == flag


# --- AC3: update_in_txn -------------------------------------------------------------------


async def test_update_in_txn_rereads_so_the_cache_and_oauth_tokens_survive(world) -> None:
    await make_http(world)
    stale = await world.repo.get("h1")  # a snapshot taken before the concurrent writes
    await world.repo.merge_cache("h1", {"last_check": {"status": "ok"}, "tools": [{"name": "t"}]})
    from mcp.shared.auth import OAuthToken

    await MCPSourceTokenStorage(world.repo, "h1").set_tokens(
        OAuthToken(access_token="fresh-access", token_type="Bearer", refresh_token="fresh-refresh")
    )
    assert "access_token" not in stale.secrets
    after = await svc.change_mcp_source(world.deps, "h1", {"url": "https://mcp.example.com/b"})
    stored = await world.repo.get("h1")
    assert stored.config["url"] == "https://mcp.example.com/b"
    assert stored.secrets["access_token"] == "fresh-access"
    assert stored.secrets["refresh_token"] == "fresh-refresh"
    assert stored.config["_cache"]["tools"] == [{"name": "t"}]
    # the URL changed, so the old server's last check is dropped; the tools cache stays
    assert "last_check" not in stored.config["_cache"]
    assert after.config == stored.config


async def test_a_write_landing_while_the_change_waits_for_the_lock_is_kept(world) -> None:
    """The real gap: another write commits after this change started but before it holds the
    write lock. The row is read under the lock, so that write is not overwritten."""
    import asyncio
    import json

    await make_http(world)
    gate = asyncio.Event()

    async def concurrent_write() -> None:
        async with write_transaction(world.conn):
            gate.set()
            await asyncio.sleep(0.1)  # the change below is now waiting on the lock
            cfg = {"url": "https://mcp.example.com/a", "_cache": {"tools": [{"name": "fresh"}]}}
            secrets = {"Authorization": "Bearer-secret-value-1234", "access_token": "rotated"}
            await world.conn.execute(
                "UPDATE mcp_sources SET config=?, secrets=? WHERE id='h1'",
                (json.dumps(cfg), world.repo._secrets_to_ciphertext(secrets)),
            )

    task = asyncio.create_task(concurrent_write())
    await gate.wait()
    await svc.change_mcp_source(world.deps, "h1", {"headers": {"X-New": "1"}})
    await task
    stored = await world.repo.get("h1")
    assert stored.secrets["access_token"] == "rotated"
    assert stored.config["_cache"] == {"tools": [{"name": "fresh"}]}
    assert stored.config["headers"] == {"X-New": "1"}  # the concurrent write set no headers


async def test_update_in_txn_returns_before_and_after_and_moves_updated_at(world) -> None:
    src = await make_http(world)
    before, after = await world.repo.update_in_txn(
        "h1", lambda cur: cur.model_copy(update={"name": "Docs 2"})
    )
    assert before.name == "Docs" and after.name == "Docs 2"
    assert after.updated_at != src.updated_at and after.updated_at >= src.updated_at
    assert (await world.repo.get("h1")).updated_at == after.updated_at


async def test_a_mutator_exception_writes_nothing(world) -> None:
    await make_http(world)

    def boom(cur):
        raise ValueError("no")

    with pytest.raises(ValueError):
        await world.repo.update_in_txn("h1", boom)
    assert (await world.repo.get("h1")).name == "Docs"


async def test_on_commit_runs_inside_the_transaction_and_rolls_back_with_it(world) -> None:
    await make_http(world)
    seen: list[str] = []

    async def hook(conn):
        async with conn.execute("SELECT name FROM mcp_sources WHERE id = 'h1'") as cur:
            seen.append((await cur.fetchone())[0])  # the new name is visible: same transaction

    await world.repo.update_in_txn(
        "h1", lambda cur: cur.model_copy(update={"name": "Docs 2"}), on_commit=hook
    )
    assert seen == ["Docs 2"]

    async def failing(conn):
        raise RuntimeError("late")

    with pytest.raises(RuntimeError):
        await world.repo.update_in_txn(
            "h1", lambda cur: cur.model_copy(update={"name": "Docs 3"}), on_commit=failing
        )
    assert (await world.repo.get("h1")).name == "Docs 2"


async def test_a_hook_that_opens_a_write_transaction_fails_loudly(world) -> None:
    await make_http(world)

    async def nested(conn):
        async with write_transaction(conn):
            pass

    with pytest.raises(RuntimeError, match="re-entered"):
        await world.repo.update_in_txn("h1", lambda cur: cur, on_commit=nested)


async def test_update_in_txn_of_an_unknown_id_is_a_key_error(world) -> None:
    with pytest.raises(KeyError):
        await world.repo.update_in_txn("nope", lambda cur: cur)


async def test_create_on_commit_rides_in_the_insert_transaction(world) -> None:
    async def failing(conn):
        raise RuntimeError("late")

    body = {"id": "n1", "name": "New", "type": "stdio", "config": {"command": "echo"}}
    with pytest.raises(RuntimeError):
        await svc.create_mcp_source(world.deps, body, on_commit=failing)
    with pytest.raises(KeyError):
        await world.repo.get("n1")


# --- create and replace: today's route behaviour ------------------------------------------


async def test_create_checks_the_name_the_reserved_name_and_the_config(world) -> None:
    ok = {"name": "New", "type": "stdio", "config": {"command": "echo"}}
    made = await svc.create_mcp_source(world.deps, ok)
    assert len(made.id) == 12
    with pytest.raises(svc.McpWriteError) as e:
        await svc.create_mcp_source(world.deps, {**ok, "name": "  "})
    assert e.value.status == 422 and e.value.detail[0]["loc"] == ["name"]
    with pytest.raises(svc.McpWriteError) as e:
        await svc.create_mcp_source(world.deps, {**ok, "name": "self-configuration"})
    assert e.value.status == 409
    with pytest.raises(svc.McpWriteError) as e:
        await svc.create_mcp_source(world.deps, {"name": "X", "type": "stdio", "config": {}})
    assert e.value.status == 422 and "requires config.command" in e.value.detail
    with pytest.raises(svc.McpWriteError) as e:
        await svc.create_mcp_source(world.deps, {"name": "X", "type": "bogus"})
    assert e.value.status == 422 and isinstance(e.value.detail, list)
    assert e.value.items[0]["loc"]  # the shape the approve path reads


async def test_replace_is_the_put_semantics(world, effects) -> None:
    await make_http(world, config={"url": "https://a.test/x", "_cache": {"tools": [1]}})
    out = await svc.replace_mcp_source(
        world.deps,
        "h1",
        {
            "config": {"url": "https://b.test/x", "_cache": {"tools": ["poisoned"]}},
            "secrets": {"Authorization": "__MASKED__", "access_token": "forged"},
        },
    )
    assert out.config["_cache"] == {"tools": [1]}  # the cache is server-managed
    assert out.secrets == {
        "Authorization": "Bearer-secret-value-1234"
    }  # masked kept, forged dropped
    assert ("evict", "h1") in effects and ("drop", "h1") in effects and ("era", "h1") in effects
    with pytest.raises(svc.McpSourceNotFound):
        await svc.replace_mcp_source(world.deps, "nope", {})
    with pytest.raises(svc.McpWriteError) as e:
        await svc.replace_mcp_source(world.deps, "h1", {"secrets": ["x"]})
    assert (e.value.status, e.value.detail) == (422, "secrets must be a dict.")


# --- AC4: change_mcp_source ---------------------------------------------------------------


async def test_only_the_named_fields_change_and_rows_merge_per_row(world) -> None:
    await make_stdio(world)
    await world.repo.merge_cache("s1", {"last_check": {"status": "ok"}})
    out = await svc.change_mcp_source(
        world.deps, "s1", {"env": {"EXTRA": "1", "LOG_LEVEL": "debug"}}
    )  # squawk 0382: an args change would now (rightly) prune the check; this one is env only
    cfg = out.config
    assert cfg["command"] == "npx" and cfg["args"] == ["-y", "pkg"]
    assert cfg["env"] == {"LOG_LEVEL": "debug", "EXTRA": "1"}  # merged per row, none removed
    assert cfg["cwd"] == "/home/x/work" and cfg["sandbox"] == {"network_allowed": False}
    assert cfg["_cache"]["last_check"] == {"status": "ok"}  # the type did not change
    assert out.secrets == {"MY_SETTING": "sensitive-value-1234"}
    assert out.name == "Local" and out.type == "stdio"


async def test_a_header_row_replaces_the_existing_one_case_insensitively(world) -> None:
    await make_http(world)
    out = await svc.change_mcp_source(world.deps, "h1", {"headers": {"accept": "application/json"}})
    assert out.config["headers"] == {"accept": "application/json"}


async def test_a_url_change_prunes_the_old_servers_cache_keys(world) -> None:
    await make_http(world)
    await world.repo.merge_cache(
        "h1",
        {
            "last_check": {"s": 1},
            "auth_posture": "oauth",
            "protocol_fallback": "x",
            "tools": [{"name": "t"}],
        },
    )
    out = await svc.change_mcp_source(world.deps, "h1", {"url": "https://other.test/mcp"})
    assert out.config["_cache"] == {"tools": [{"name": "t"}]}
    await world.repo.merge_cache("h1", {"last_check": {"s": 2}})
    same = await svc.change_mcp_source(world.deps, "h1", {"name": "Docs renamed"})
    assert same.config["_cache"]["last_check"] == {"s": 2}  # no server change, no pruning


_CHECKED = {
    "last_check": {"s": 1},
    "auth_posture": "oauth",
    "protocol_fallback": "no_answer",
    "tools": [{"name": "t"}],
}


async def _seed_stdio_cache(world) -> None:
    await make_stdio(world)
    await world.repo.merge_cache("s1", dict(_CHECKED))


def _stdio_body(**cfg) -> dict:
    base = {"command": "npx", "args": ["-y", "pkg"], "env": {"LOG_LEVEL": "info"}}
    return {"name": "Local", "type": "stdio", "config": {**base, **cfg}, "secrets": {}}


@pytest.mark.parametrize("via", ["put", "change"])
@pytest.mark.parametrize("field", ["command", "args"])
async def test_a_stdio_command_or_args_change_prunes_the_old_servers_cache(
    world, via, field
) -> None:
    """Squawk 0382: a local-command server's identity is its command and arguments."""
    await _seed_stdio_cache(world)
    new = {"command": "uvx"} if field == "command" else {"args": ["-y", "other"]}
    if via == "put":
        out = await svc.replace_mcp_source(world.deps, "s1", _stdio_body(**new))
    else:
        out = await svc.change_mcp_source(world.deps, "s1", new)
    assert out.config["_cache"] == {"tools": [{"name": "t"}]}
    assert (await world.repo.get("s1")).config["_cache"] == {"tools": [{"name": "t"}]}


@pytest.mark.parametrize("via", ["put", "change"])
async def test_a_stdio_env_or_sandbox_change_keeps_the_cache(world, via) -> None:
    await _seed_stdio_cache(world)
    if via == "put":
        out = await svc.replace_mcp_source(
            world.deps,
            "s1",
            _stdio_body(env={"LOG_LEVEL": "debug"}, sandbox={"network_allowed": True}),
        )
    else:
        out = await svc.change_mcp_source(world.deps, "s1", {"env": {"LOG_LEVEL": "debug"}})
    assert out.config["_cache"] == _CHECKED


async def test_a_stdio_args_absent_to_empty_is_not_a_change(world) -> None:
    await make_stdio(world, config={"command": "npx"})
    await world.repo.merge_cache("s1", dict(_CHECKED))
    out = await svc.replace_mcp_source(world.deps, "s1", _stdio_body(command="npx", args=[]))
    assert out.config["_cache"] == _CHECKED


async def _wait_for_waiter(task) -> None:
    """Yield until ``task`` is blocked on the write lock the test holds."""
    import asyncio

    for _ in range(400):
        if task.done():
            raise AssertionError("the write finished without waiting for the lock")
        if getattr(_write_lock._lock, "_waiters", None):
            return
        await asyncio.sleep(0.005)
    raise AssertionError("the write never reached the lock")


async def test_a_refresh_written_while_a_replace_waits_for_the_lock_survives(world) -> None:
    """Squawk 0400: the PUT reads the row under the write lock, so a rotated refresh token and
    a new ``_cache`` key written while it waits are pinned, not overwritten."""
    import asyncio
    import json

    await make_http(
        world, secrets={"Authorization": "Bearer-secret-value-1234", "refresh_token": "old"}
    )
    await world.repo.merge_cache("h1", {"tools": [{"name": "t"}]})
    body = {
        "name": "Renamed",
        "type": "streamable-http",
        "config": {"url": "https://mcp.example.com/a"},
        "secrets": {"Authorization": "Bearer-secret-value-1234"},
    }
    async with write_transaction(world.conn):
        task = asyncio.create_task(svc.replace_mcp_source(world.deps, "h1", body))
        await _wait_for_waiter(task)
        cfg = {
            "url": "https://mcp.example.com/a",
            "headers": {"Accept": "text/plain"},
            "_cache": {"tools": [{"name": "t"}], "last_check": {"s": 9}},
        }
        secrets = {"Authorization": "Bearer-secret-value-1234", "refresh_token": "rotated"}
        await world.conn.execute(
            "UPDATE mcp_sources SET config=?, secrets=? WHERE id='h1'",
            (json.dumps(cfg), world.repo._secrets_to_ciphertext(secrets)),
        )
    after = await task
    stored = await world.repo.get("h1")
    assert stored.name == "Renamed"
    assert stored.secrets["refresh_token"] == "rotated"
    assert stored.config["_cache"]["last_check"] == {"s": 9}
    assert after.secrets["refresh_token"] == "rotated"
    assert after.updated_at == stored.updated_at
    assert "_cache" not in body["config"]  # the caller's dict is not mutated


@pytest.mark.parametrize(
    ("field", "rows", "fragment"),
    [
        ("headers", {"Authorization": "x1"}, "stored as a Sensitive value"),
        ("headers", {"X-Tenant": "x1"}, "stored as a Sensitive value"),
        ("headers", {"x-tenant": "x1"}, "stored as a Sensitive value"),  # case-insensitive
        ("headers", {"X-TENANT": "x1"}, "stored as a Sensitive value"),
        ("headers", {"access_token": "x1"}, "managed by sign-in"),
        ("headers", {"Access_Token": "x1"}, "managed by sign-in"),
        ("headers", {"X-Api-Key": "x1"}, "looks like a secret"),
    ],
)
async def test_header_rows_that_could_hold_a_secret_are_refused(
    world, field, rows, fragment
) -> None:
    await make_http(
        world,
        secrets={"Authorization": "Bearer-secret-value-1234", "X-Tenant": "tenant-secret-1234"},
    )
    with pytest.raises(svc.McpWriteError) as e:
        await svc.change_mcp_source(world.deps, "h1", {field: rows})
    assert e.value.status == 422 and fragment in e.value.items[0]["msg"]
    assert (await world.repo.get("h1")).config["headers"] == {"Accept": "text/plain"}


async def test_env_rows_compare_exactly_and_refuse_secret_looking_names(world) -> None:
    await make_stdio(world)
    with pytest.raises(svc.McpWriteError, match="stored as a Sensitive value"):  # exactly
        await svc.change_mcp_source(world.deps, "s1", {"env": {"MY_SETTING": "plain"}})
    out = await svc.change_mcp_source(world.deps, "s1", {"env": {"my_setting": "plain"}})
    assert out.config["env"]["my_setting"] == "plain"  # exact compare: a different key
    with pytest.raises(svc.McpWriteError) as e:
        await svc.change_mcp_source(world.deps, "s1", {"env": {"GITHUB_TOKEN": "abc"}})
    assert "looks like a secret" in e.value.items[0]["msg"]
    with pytest.raises(svc.McpWriteError):
        await svc.change_mcp_source(world.deps, "s1", {"args": ["--token=abc123"]})


async def test_a_change_never_names_a_field_of_the_other_transport(world) -> None:
    await make_http(world)
    with pytest.raises(svc.McpWriteError):
        await svc.change_mcp_source(world.deps, "h1", {"command": "echo"})
    with pytest.raises(svc.McpWriteError):
        await svc.change_mcp_source(world.deps, "h1", {"cwd": "/tmp"})  # operator-only: unknown
    with pytest.raises(svc.McpWriteError):
        await svc.change_mcp_source(world.deps, "h1", {"secrets": {"a": "b"}})
    with pytest.raises(svc.McpWriteError):
        await svc.change_mcp_source(world.deps, "h1", {"type": "stdio"})


async def test_stale_base_raises_unless_override_and_writes_nothing(world) -> None:
    await make_http(world)
    changes = {"url": "https://new.test/mcp", "headers": {"Accept": "a/b", "X-New": "1"}}
    base = {"url": "https://mcp.example.com/a", "headers": {"Accept": "text/plain"}}
    # X-New is absent at proposal time. A concurrent save adds it.
    await svc.change_mcp_source(world.deps, "h1", {"headers": {"X-New": "theirs"}})
    with pytest.raises(svc.McpStaleError) as e:
        await svc.change_mcp_source(world.deps, "h1", changes, base=base)
    assert e.value.fields == [
        {"field": "headers", "current": {"X-New": "theirs"}, "proposed": {"X-New": "1"}}
    ]
    assert (await world.repo.get("h1")).config["url"] == "https://mcp.example.com/a"
    # the url moved too
    await svc.change_mcp_source(world.deps, "h1", {"url": "https://moved.test/mcp"})
    with pytest.raises(svc.McpStaleError) as e:
        await svc.change_mcp_source(world.deps, "h1", {"url": "https://x.test/"}, base=base)
    assert e.value.fields[0]["field"] == "url"
    assert e.value.fields[0]["current"] == "https://moved.test/mcp"
    out = await svc.change_mcp_source(
        world.deps, "h1", {"url": "https://x.test/"}, base=base, override=True
    )
    assert out.config["url"] == "https://x.test/"


async def test_a_fresh_base_applies(world) -> None:
    await make_http(world)
    out = await svc.change_mcp_source(
        world.deps,
        "h1",
        {"headers": {"accept": "a/b"}},
        base={"headers": {"accept": "text/plain"}},  # matched case-insensitively
    )
    assert out.config["headers"] == {"accept": "a/b"}


async def test_the_name_rule_reserved_name_surface_row_and_validation_apply(world) -> None:
    await make_http(world)
    with pytest.raises(svc.McpWriteError) as e:
        await svc.change_mcp_source(world.deps, "h1", {"name": " "})
    assert e.value.status == 422 and e.value.detail[0]["loc"] == ["name"]
    with pytest.raises(svc.McpWriteError) as e:
        await svc.change_mcp_source(world.deps, "h1", {"name": "self-configuration"})
    assert e.value.status == 409
    with pytest.raises(svc.McpWriteError) as e:
        await svc.change_mcp_source(world.deps, "h1", {"url": ""})
    assert e.value.status == 422
    surface = MCPSource(
        id="sf",
        name="self-configuration",
        type="streamable-http",
        config={"url": "http://127.0.0.1:1/x", "self_configuration": {"agent": "a"}},
    )
    await world.repo.create(surface)
    with pytest.raises(svc.McpWriteError) as e:
        await svc.change_mcp_source(world.deps, "sf", {"url": "http://127.0.0.1:2/x"})
    assert e.value.status == 409
    with pytest.raises(svc.McpSourceNotFound):
        await svc.change_mcp_source(world.deps, "nope", {"url": "https://a.test/"})


async def test_side_effects_run_after_commit_under_the_routes_conditions(world, effects) -> None:
    await make_http(world)
    # a name-only change: no connection eviction (config and secrets are the same), a carry
    await svc.change_mcp_source(world.deps, "h1", {"name": "Docs 2"})
    assert effects == [
        ("era", "h1"),
        ("carry", "h1", "Docs", "Docs 2"),
        ("carry_secrets", "Docs", "Docs 2"),
    ]
    effects.clear()
    # a config change: eviction, then the tool-cache drop, no carry
    await svc.change_mcp_source(world.deps, "h1", {"url": "https://n.test/mcp"})
    assert effects == [("era", "h1"), ("evict", "h1"), ("drop", "h1")]


async def test_no_side_effect_runs_when_the_write_fails(world, effects) -> None:
    await make_http(world)

    async def failing(conn):
        raise RuntimeError("late")

    with pytest.raises(RuntimeError):
        await svc.change_mcp_source(
            world.deps, "h1", {"name": "Docs 2", "url": "https://n.test/mcp"}, on_commit=failing
        )
    with pytest.raises(svc.McpStaleError):
        await svc.change_mcp_source(
            world.deps, "h1", {"url": "https://n.test/mcp"}, base={"url": "https://old.test/"}
        )
    assert effects == []
    assert (await world.repo.get("h1")).name == "Docs"


async def test_a_failing_agent_store_getter_does_not_skip_the_secrets_carry(world, effects) -> None:
    await make_http(world)

    async def broken():
        raise RuntimeError("store down")

    deps = svc.McpWriteDeps(repo=world.repo, agent_store=broken, secret_repo=world.deps.secret_repo)
    await svc.change_mcp_source(deps, "h1", {"name": "Docs 2"})
    assert ("carry_secrets", "Docs", "Docs 2") in effects
    assert not any(e[0] == "carry" for e in effects)


async def test_a_rename_carries_into_an_attached_agents_override_key(world) -> None:
    await make_http(world)
    await world.store.save(
        AgentConfig(
            name="wide",
            mcp_source_ids=["h1"],
            mcp_overrides={"Docs": {"headers": {"X-Tenant": "acme"}}},
        )
    )
    await svc.change_mcp_source(world.deps, "h1", {"name": "Docs renamed"})
    cfg = await world.store.load("wide")
    assert "Docs renamed" in (cfg.mcp_overrides or {}) and "Docs" not in (cfg.mcp_overrides or {})
