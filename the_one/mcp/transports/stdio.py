"""Stdio transport for MCPClient.

Implements the wire-shape glue between F1's MCPSource model and the
official mcp SDK's stdio_client. The transport itself is a single
async-context-manager (`connect_stdio`) that yields a fully-entered
`ClientSession`; MCPClient only sees the session, never the
(read, write) stream tuple.

Subprocess environ is assembled at spawn time from two layers:
  1. Host allowlist (the canonical 8-key set from
     `the_one.platform.env._ENV_ALLOWLIST`, materialized via
     `_build_subprocess_env()`).
  2. Operator-configured kv table — `config.env` (plaintext at rest)
     flat-merged with `secrets` (Fernet-encrypted at rest); secrets
     win on collision (over BOTH allowlist and config.env).

Allowlist sits at the floor (overridable by both operator layers).
The SDK applies its own `get_default_environment()` UNDER our env as
well — so the effective subprocess environ has 3 layers: SDK floor,
our allowlist, our operator kv. We never see the SDK floor because
we don't call `get_default_environment()` ourselves; the SDK applies
it inside `stdio_client`.

`_build_subprocess_env` is private by underscore convention but is the
canonical helper for filtering the host environ by the allowlist —
promoted-by-use-not-by-rename. F2 imports it directly.

NOTE: this helper does NOT consume `MCPSource.merged_config()` —
`merged_config()` flat-merges secrets at the config TOP level, which
would inject command/args/cwd-shaped keys into the env if we used it.
The kv table for stdio sources lives at `config["env"]`, never at
`config` top-level. See flight 02 design decision §11.

See flight 02 design decision §11 for the env-var-assembly contract,
and L4's `transports/streamable_http.py` for the structurally
parallel headers-assembly pattern.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from the_one.db.models import MCPSource
from the_one.platform.env import _build_subprocess_env

__all__ = ["build_stdio_environ", "connect_stdio"]


def build_stdio_environ(
    source: MCPSource, allowlist_env: dict[str, str]
) -> dict[str, str]:
    """Materialize the spawned-child environ for a stdio MCP source.

    Two-layer flat merge in precedence order:
      1. allowlist_env — the canonical host-environment-filtered allowlist
         (caller passes `_build_subprocess_env()` in production; tests
         inject a known-shape dict for determinism).
      2. operator-configured kv table — config["env"] (plaintext at rest)
         ∪ source.secrets (encrypted at rest), with secrets winning on
         collision (over BOTH allowlist and config.env — so an
         operator-marked-sensitive value beats any plaintext default of
         the same name AND any host-inherited allowlist value).

    Layer 2 is one logical concept (the operator's kv table from the L6
    editor); the at-rest config/secrets split is purely the F1
    encryption-at-rest implementation detail.

    Returns a fresh dict; does not mutate inputs. Pure function — no I/O.

    NOTE: do NOT call source.merged_config() — that produces
    {**config, **secrets} which would inject command/args/cwd as
    env-var-shaped keys. The kv table for stdio sources lives at
    config["env"], not at config top-level.
    """
    config_env: dict[str, str] = source.config.get("env", {}) or {}
    return {**allowlist_env, **config_env, **source.secrets}


@asynccontextmanager
async def connect_stdio(source: MCPSource) -> AsyncIterator[ClientSession]:
    """Open an entered ClientSession over stdio transport.

    Yields a fully-entered ClientSession (initialize() NOT called — the
    caller — typically MCPClient.connect — runs the handshake). The
    session and transport contexts close in correct LIFO order on exit.

    The subprocess environ is materialized via `build_stdio_environ`
    passing the result of `_build_subprocess_env()` (the canonical host
    allowlist filter). The SDK applies its own
    `get_default_environment()` UNDER our env, providing additional
    defense-in-depth defaults for HOME/LANG/etc.
    """
    command: str = source.config["command"]
    # SDK's StdioServerParameters has args: list[str] with default_factory=list,
    # so args is technically NOT required at the Pydantic layer. We still pass
    # `.get("args", [])` defensively in case F1 validator drift ever lets args
    # go absent — guarantees an explicit empty list reaches the SDK regardless.
    args: list[str] = source.config.get("args", [])
    # F1 validator restricts cwd to str|None; SDK also accepts pathlib.Path
    # but we don't surface that — keeps the contract tight at the API edge.
    cwd: str | None = source.config.get("cwd")
    env = build_stdio_environ(source, _build_subprocess_env())

    params = StdioServerParameters(
        command=command,
        args=args,
        env=env,
        cwd=cwd,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            yield session
