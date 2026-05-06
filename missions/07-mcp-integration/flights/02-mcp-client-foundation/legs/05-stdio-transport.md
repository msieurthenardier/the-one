# Leg: 05-stdio-transport

**Status**: completed
**Flight**: [MCP Client Foundation](../flight.md)

## Objective

Wire the stdio transport into `MCPClient` end-to-end. Implement `build_stdio_environ(source, allowlist_env)` (2-layer flat-merge of host allowlist + operator-configured kv table — `config.env ∪ secrets`, secrets win) and `connect_stdio(source)` (an `@asynccontextmanager` yielding a fully-entered `ClientSession`); update `_transport_connect` in `client.py` so its `stdio` branch delegates to the new helper. Reuses the canonical `_ENV_ALLOWLIST` and `_build_subprocess_env()` from `the_one/platform/env.py` (DOES NOT re-declare per the architect's L4-design-review fix).

## Context

- **Flight design** §11 (env-var assembly shape): 2-layer flat merge of host allowlist (8 keys: `PATH`, `HOME`, `USER`, `LOGNAME`, `LANG`, `LC_ALL`, `TERM`, `TZ`) + operator kv table (`config.env` plaintext-at-rest ∪ `secrets` encrypted-at-rest, secrets win on collision); §2 (MCPClient API surface — `connect()` dispatches via `_transport_connect`); §6 (SDK pin); §10 (fail-hard version handshake — already enforced by L2)
- **L4 set the pattern**: transport module exposes `build_*` helper + `connect_*` `@asynccontextmanager` yielding a fully-entered `ClientSession`; dispatcher in `client.py::_transport_connect` does a local-import + `async with ... as session: yield session`. L5 mirrors this shape for stdio
- **L2's `_transport_connect`** (post-L4): the stdio branch raises `NotImplementedError("transport 'stdio' not implemented; L5 lands it")`. L5 replaces this with `async with connect_stdio(source) as session: yield session`
- **L3 fixture `mcp_fixture_stdio_params`** yields a `dict[str, Any]` shaped like `StdioServerParameters(command=sys.executable, args=["-m", "tests.fixtures.mcp.hello_server", "--stdio"], env={"PATH": ..., "PYTHONPATH": ...}, cwd=None)`. L5 integration tests construct an `MCPSource` shaped like this fixture's `command/args/env/cwd` plus an `id`/`name`/`type="stdio"` wrapper
- **The SDK's `stdio_client`** signature: `stdio_client(server: StdioServerParameters, errlog: TextIO = sys.stderr)`. Returns `(read_stream, write_stream)` 2-tuple (NOT 3-tuple like streamable-http). The `errlog=sys.stderr` default is fine for L3's smoke test; L5 doesn't change it
- **The SDK's env-merge behavior** (per L3 edge-case): SDK applies its own `get_default_environment()` UNDER the env we supply. Our `build_stdio_environ` produces the OPERATOR-side environ; the SDK adds the floor. Means: in production our explicit allowlist is a CEILING-ONLY view (operator-controlled keys), and the SDK supplies an extra base layer of HOME/LANG/etc. that's beneficial (FastMCP startup wouldn't choke on missing HOME). NOT a regression — defense-in-depth
- **Reviewer's L4 finding**: `the_one/platform/env._ENV_ALLOWLIST` is the canonical 8-key allowlist, NOT to be re-declared. `_build_subprocess_env()` is the canonical "filter os.environ by allowlist" helper. L5 imports both and uses them
- **Subprocess startup variance**: per L3 measurement, ~0.5-0.8s for Python cold-start + FastMCP init. L5's 3 integration tests should complete in <3s combined. If CI variance pushes >3s, the leg's edge cases note the deferred mitigation
- **Test-seam pattern from L4**: the streamable-http transport has a `_test_http_client_override` for in-process ASGI testing. L5 needs NO equivalent seam — stdio is inherently subprocess-based (the `mcp_fixture_stdio_params` fixture IS the production shape, just pointing at the in-repo fixture script). Tests just construct an `MCPSource` whose `config.command/args/env/cwd` come from the fixture's dict

## Inputs

What exists before this leg runs:
- L1+L2+L3+L4 outputs: `MCPClient` lifecycle, error hierarchy, dataclasses, `_transport_connect` dispatch with streamable-http branch wired (stdio still raises `NotImplementedError`); L3 stdio subprocess fixture; L4 streamable-http transport landed
- `the_one/mcp/transports/stdio.py` with placeholder docstring (L1 stub)
- `the_one/platform/env.py::_ENV_ALLOWLIST` (8-tuple) and `_build_subprocess_env() -> dict[str, str]` (filters `os.environ`)
- `mcp.client.stdio.stdio_client(StdioServerParameters)` SDK function returning a 2-tuple `(read, write)` async context manager
- `mcp.client.stdio.StdioServerParameters` Pydantic model with fields: `command: str` (required), `args: list[str]` (default-factory `[]`, NOT required — `StdioServerParameters(command='echo')` works without `args`), `env: dict[str, str] | None = None`, `cwd: str | Path | None = None`, plus `encoding`/`encoding_error_handler` defaults

## Outputs

What exists after this leg completes:
- `the_one/mcp/transports/stdio.py` — full implementation:
  - `build_stdio_environ(source: MCPSource, allowlist_env: dict[str, str]) -> dict[str, str]` — 2-layer flat-merge per flight §11. Pure function. Production callers pass `_build_subprocess_env()` from `the_one/platform/env.py` for `allowlist_env`
  - `connect_stdio(source: MCPSource) -> AsyncIterator[ClientSession]` — `@asynccontextmanager`-decorated; builds `StdioServerParameters` from `MCPSource.config` (`command`, `args`, `cwd`) + the materialized environ from `build_stdio_environ(source, _build_subprocess_env())`; nests `stdio_client(params)` then `ClientSession(read, write)`; yields the entered session
  - Module-level `__all__ = ["build_stdio_environ", "connect_stdio"]` for symmetry with L4's streamable-http module
- `the_one/mcp/client.py::_transport_connect` — stdio branch replaced with `async with connect_stdio(source) as session: yield session`. Streamable-http branch unchanged (L4); else-branch unchanged (defensive exhaustiveness)
- `tests/test_mcp_client.py` extended with:
  - `TestBuildStdioEnviron` — 6 unit tests covering: allowlist-only / config.env-only / secrets-only / mixed-no-collision / mixed-secrets-win / empty-config-no-env-key (per acceptance criteria below)
- `tests/test_mcp_integration.py` extended with:
  - `TestL5Stdio` — 3 integration tests using `mcp_fixture_stdio_params`:
    1. `test_connect_via_mcpclient_against_stdio_fixture` — full MCPClient connect → assertions on `is_alive`/`negotiated_protocol_version`/`server_capabilities` → disconnect; mirrors L4's test #1 shape
    2. `test_connect_with_extra_env_passes_through` — MCPSource adds extra `config.env` and `secrets` keys (e.g. `MY_VAR=hello`); `connect()` succeeds (FastMCP doesn't read MY_VAR but the round-trip proves the env is materialized without breaking spawn)
    3. `test_connect_already_connected_via_stdio_transport` — same as L2's mocked test but against the real stdio transport (matches L4's `test_connect_already_connected_via_real_transport` naming pattern)
- Test count after L5: **1127 baseline (post-L4) + 6 unit + 3 integration = exactly 1136 passing** + 1 skipped (unchanged)
- `make lint` clean (no NEW ruff errors)

## Acceptance Criteria

- [ ] `the_one/mcp/transports/stdio.py::build_stdio_environ(source: MCPSource, allowlist_env: dict[str, str]) -> dict[str, str]`:
  - Returns `{**allowlist_env, **source.config.get("env", {}), **source.secrets}` — 2-layer flat-merge in this exact precedence (allowlist underneath, then config.env, then secrets — secrets win on collision)
  - Pure function; no I/O, no side effects
  - Does NOT call `_build_subprocess_env()` itself — accepts `allowlist_env` as a parameter for testability (tests inject a known dict; production callers pass `_build_subprocess_env()`)
  - Returns a dict, never None — empty inputs produce `{}`
  - Trusts F1's API validator (which gates `config.env: dict[str, str]` per L1's API patch); does NOT re-validate types
- [ ] `the_one/mcp/transports/stdio.py::connect_stdio(source: MCPSource) -> AsyncIterator[ClientSession]`:
  - Decorated with `@asynccontextmanager`
  - Reads required fields from `source.config`: `command: str`, `args: list[str]` (default `[]`), `cwd: str | None` (default `None`). F1's API validator gates the shape; the helper trusts the model
  - Builds `params = StdioServerParameters(command=..., args=..., env=build_stdio_environ(source, _build_subprocess_env()), cwd=...)` — the call to `_build_subprocess_env()` is INSIDE the helper (production needs the host's actual env; tests can monkeypatch `the_one.mcp.transports.stdio._build_subprocess_env` if they want a known-shape fixture)
  - Opens `async with stdio_client(params) as (read, write):` then nests `async with ClientSession(read, write) as session: yield session`. LIFO cleanup on context exit
  - Does NOT pass `errlog` to `stdio_client` — accepts the SDK's `errlog=sys.stderr` default (FastMCP fixture's startup INFO logs surface in `pytest -v` output; acceptable per L3 edge case)
- [ ] Module-level declarations:
  - `__all__ = ["build_stdio_environ", "connect_stdio"]` at module top (mirrors L4's pattern)
  - SDK imports (`from mcp import ClientSession`, `from mcp.client.stdio import stdio_client, StdioServerParameters`) at module top — NOT lazy (L4's streamable-http does the same; symmetry)
  - Helper imports (`from the_one.platform.env import _build_subprocess_env`, `from the_one.db.models import MCPSource`) at module top
- [ ] `the_one/mcp/client.py::_transport_connect`'s stdio branch is replaced with:
  ```python
  elif source.type == "stdio":
      from the_one.mcp.transports.stdio import connect_stdio
      async with connect_stdio(source) as session:
          yield session
  ```
  - The local import keeps SDK out of `client.py`'s module-load path (consistent with L4's pattern)
  - Streamable-http branch unchanged (L4-shipped); else-branch unchanged (defensive `MCPClientError`)
- [ ] **`TestBuildStdioEnviron` (6 unit tests in `tests/test_mcp_client.py`)**:
  1. `test_allowlist_only` — source with no `config.env` and no `secrets`; `allowlist_env={"PATH": "/usr/bin", "HOME": "/home/x"}` → `build_stdio_environ(source, allowlist) == {"PATH": "/usr/bin", "HOME": "/home/x"}`
  2. `test_config_env_only` — source with `config={"command": "x", "env": {"FOO": "bar"}}` and empty secrets; allowlist `{}` → `{"FOO": "bar"}`
  3. `test_secrets_only` — source with `config={"command": "x"}` (no env key) and `secrets={"TOKEN": "abc"}`; allowlist `{}` → `{"TOKEN": "abc"}`
  4. `test_mixed_no_collision` — allowlist `{"PATH": "/usr/bin"}`, `config.env = {"FOO": "bar"}`, `secrets = {"TOKEN": "abc"}` → `{"PATH": "/usr/bin", "FOO": "bar", "TOKEN": "abc"}`
  5. `test_secrets_win_over_config_env` — `config.env = {"OVERRIDE": "config-value"}`, `secrets = {"OVERRIDE": "secret-value"}`; allowlist `{}` → `{"OVERRIDE": "secret-value"}` (secrets win)
  6. `test_secrets_win_over_allowlist` — `allowlist = {"PATH": "/usr/bin"}`, `secrets = {"PATH": "/operator-override"}`; config no env → `{"PATH": "/operator-override"}` (secrets win even over allowlist; documented behavior per flight §11 — the operator can override anything)
- [ ] **`TestL5Stdio` (3 integration tests in `tests/test_mcp_integration.py`)**:
  1. `test_connect_via_mcpclient_against_stdio_fixture(mcp_fixture_stdio_params)`:
     - `params_dict = mcp_fixture_stdio_params` — the L3 dict
     - Build `MCPSource(id="src-stdio-1", name="hello-stdio", type="stdio", config={"command": params_dict["command"], "args": params_dict["args"], "env": params_dict["env"], "cwd": params_dict["cwd"]}, secrets={})`
     - `client = MCPClient(source)`; `await client.connect()` succeeds; `assert client.is_alive`; `assert client.negotiated_protocol_version == "2025-11-25"`; `caps = client.server_capabilities; assert isinstance(caps["tools"], dict) and "listChanged" in caps["tools"]`
     - `await client.disconnect()`; `assert not client.is_alive`
  2. `test_connect_with_extra_env_passes_through(mcp_fixture_stdio_params)`:
     - Same setup as #1, but extend `config["env"]` with an extra plaintext key (`MY_PLAIN: hello`) AND add `secrets={"MY_SECRET": "shh"}`
     - `connect()` succeeds; `assert client.is_alive` (FastMCP fixture doesn't read these env vars but the round-trip proves the env materialized without breaking spawn)
  3. `test_connect_already_connected_via_stdio_transport(mcp_fixture_stdio_params)`:
     - Same setup as #1; `connect()` once succeeds; second `connect()` raises `MCPConnectionError("MCPClient is already connected.")`
- [ ] **NO unit-test mocking of `stdio_client` / `ClientSession` for header-injection-style spy** is required — the env-injection contract is fully covered by `TestBuildStdioEnviron` (the helper is pure-Python; no SDK round-trip needed to verify env precedence). The 3 integration tests provide end-to-end smoke; combined coverage matches L4's pattern
- [ ] `make lint` exits 0 (in-container) — no NEW ruff errors. The leg's pattern matches L4's, so no new lint risks expected
- [ ] `make test` (in-container) — exactly **1136 passing + 1 skipped** (1127 post-L4 baseline + 6 unit + 3 integration). The 1 skipped count carries forward unchanged

## Verification Steps

```bash
# In container
cd /home/cprch/projects/the-one

# Module imports cleanly, helper signatures correct
docker compose exec the-one python -c "
from the_one.mcp.transports.stdio import build_stdio_environ, connect_stdio
from the_one.mcp.transports.stdio import __all__ as a
print('__all__:', a)
print('build_stdio_environ:', build_stdio_environ)
print('connect_stdio:', connect_stdio)
"

# build_stdio_environ smoke
docker compose exec the-one python -c "
from the_one.db.models import MCPSource
from the_one.mcp.transports.stdio import build_stdio_environ
src = MCPSource(id='t', name='t', type='stdio',
                config={'command':'echo', 'args':[], 'env':{'FOO':'bar'}},
                secrets={'TOKEN':'abc'})
result = build_stdio_environ(src, {'PATH':'/usr/bin'})
assert result == {'PATH':'/usr/bin', 'FOO':'bar', 'TOKEN':'abc'}, result
print('smoke OK:', result)
"

# Unit tests in isolation
docker compose exec the-one make test ARGS='-k TestBuildStdioEnviron -v'

# Integration tests in isolation
docker compose exec the-one make test ARGS='-k TestL5Stdio -v'

# Full suite
docker compose exec the-one make test
docker compose exec the-one make lint
```

## Implementation Guidance

1. **Implement `the_one/mcp/transports/stdio.py`** — replace the placeholder with:

   ```python
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
        win on collision.

   Allowlist sits at the floor (overridable by both operator layers).
   The SDK applies its own `get_default_environment()` UNDER our env as
   well — so the effective subprocess environ has 3 layers: SDK floor,
   our allowlist, our operator kv. We never see the SDK floor because
   we don't call `get_default_environment()` ourselves; the SDK applies
   it inside `stdio_client`.

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
            collision (so an operator-marked-sensitive value beats any
            plaintext default of the same name).

       Layer 2 is one logical concept (the operator's kv table from the L6
       editor); the at-rest config/secrets split is purely the F1
       encryption-at-rest implementation detail.

       Returns a fresh dict; does not mutate inputs.

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

       The subprocess environ is materialized via build_stdio_environ
       passing the result of _build_subprocess_env() (the canonical
       host allowlist filter). The SDK applies its own
       get_default_environment() UNDER our env, providing additional
       defense-in-depth defaults for HOME/LANG/etc.
       """
       command: str = source.config["command"]
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
   ```

2. **Update `the_one/mcp/client.py::_transport_connect`** — replace the stdio NotImplementedError branch:

   ```python
   if source.type == "streamable-http":
       from the_one.mcp.transports.streamable_http import connect_streamable_http
       async with connect_streamable_http(source) as session:
           yield session
   elif source.type == "stdio":
       from the_one.mcp.transports.stdio import connect_stdio
       async with connect_stdio(source) as session:
           yield session
   else:
       raise MCPClientError(f"unknown MCP transport type: {source.type!r}")
   ```

   The dead `yield  # type: ignore[unreachable]` after the else-branch (currently in client.py) STAYS — it's needed for the `@asynccontextmanager` decorator's contract. Don't remove it.

3. **Add `TestBuildStdioEnviron` to `tests/test_mcp_client.py`** — 6 pure-Python tests:

   ```python
   from the_one.mcp.transports.stdio import build_stdio_environ


   def _stdio_source_for_env_test(
       *,
       env: dict[str, str] | None = None,
       secrets: dict[str, str] | None = None,
   ) -> MCPSource:
       config: dict[str, object] = {"command": "echo", "args": []}
       if env is not None:
           config["env"] = env
       return MCPSource(
           id="src-env-test",
           name="t",
           type="stdio",
           config=config,
           secrets=secrets or {},
       )


   class TestBuildStdioEnviron:
       def test_allowlist_only(self) -> None:
           src = _stdio_source_for_env_test()
           allowlist = {"PATH": "/usr/bin", "HOME": "/home/x"}
           assert build_stdio_environ(src, allowlist) == allowlist

       def test_config_env_only(self) -> None:
           src = _stdio_source_for_env_test(env={"FOO": "bar"})
           assert build_stdio_environ(src, {}) == {"FOO": "bar"}

       def test_secrets_only(self) -> None:
           src = _stdio_source_for_env_test(secrets={"TOKEN": "abc"})
           assert build_stdio_environ(src, {}) == {"TOKEN": "abc"}

       def test_mixed_no_collision(self) -> None:
           src = _stdio_source_for_env_test(
               env={"FOO": "bar"},
               secrets={"TOKEN": "abc"},
           )
           result = build_stdio_environ(src, {"PATH": "/usr/bin"})
           assert result == {"PATH": "/usr/bin", "FOO": "bar", "TOKEN": "abc"}

       def test_secrets_win_over_config_env(self) -> None:
           src = _stdio_source_for_env_test(
               env={"OVERRIDE": "config-value"},
               secrets={"OVERRIDE": "secret-value"},
           )
           assert build_stdio_environ(src, {}) == {"OVERRIDE": "secret-value"}

       def test_secrets_win_over_allowlist(self) -> None:
           src = _stdio_source_for_env_test(secrets={"PATH": "/operator-override"})
           assert build_stdio_environ(src, {"PATH": "/usr/bin"}) == {
               "PATH": "/operator-override"
           }
   ```

   `MCPSource` import is already at the top of `tests/test_mcp_client.py` (added by L2/L4); the test helpers may need to be added inline or as a module-level helper near the existing `_http_source` from L4 (mirrors L4's helper pattern).

4. **Add `TestL5Stdio` to `tests/test_mcp_integration.py`** — each test wrapped in `@pytest.mark.timeout(15)` so a hung subprocess (broken pipe, missing PYTHONPATH typo, FastMCP deadlock) fails fast at 15s instead of stalling the suite. `pytest-timeout 2.4.0` is already installed in the dev container; no config changes needed:

   ```python
   class TestL5Stdio:
       @pytest.mark.timeout(15)
       async def test_connect_via_mcpclient_against_stdio_fixture(
           self, mcp_fixture_stdio_params
       ) -> None:
           params_dict = mcp_fixture_stdio_params
           source = MCPSource(
               id="src-stdio-1",
               name="hello-stdio",
               type="stdio",
               config={
                   "command": params_dict["command"],
                   "args": params_dict["args"],
                   "env": params_dict["env"],
                   "cwd": params_dict["cwd"],
               },
               secrets={},
           )
           client = MCPClient(source)
           await client.connect()
           try:
               assert client.is_alive
               assert client.negotiated_protocol_version == "2025-11-25"
               caps = client.server_capabilities
               assert isinstance(caps["tools"], dict)
               assert "listChanged" in caps["tools"]
           finally:
               await client.disconnect()
           assert not client.is_alive

       @pytest.mark.timeout(15)
       async def test_connect_with_extra_env_passes_through(
           self, mcp_fixture_stdio_params
       ) -> None:
           params_dict = mcp_fixture_stdio_params
           extended_env = {**params_dict["env"], "MY_PLAIN": "hello"}
           source = MCPSource(
               id="src-stdio-2",
               name="hello-stdio-with-env",
               type="stdio",
               config={
                   "command": params_dict["command"],
                   "args": params_dict["args"],
                   "env": extended_env,
                   "cwd": params_dict["cwd"],
               },
               secrets={"MY_SECRET": "shh"},
           )
           client = MCPClient(source)
           await client.connect()
           try:
               assert client.is_alive
           finally:
               await client.disconnect()

       @pytest.mark.timeout(15)
       async def test_connect_already_connected_via_stdio_transport(
           self, mcp_fixture_stdio_params
       ) -> None:
           params_dict = mcp_fixture_stdio_params
           source = MCPSource(
               id="src-stdio-3",
               name="hello-stdio-double",
               type="stdio",
               config={
                   "command": params_dict["command"],
                   "args": params_dict["args"],
                   "env": params_dict["env"],
                   "cwd": params_dict["cwd"],
               },
               secrets={},
           )
           client = MCPClient(source)
           await client.connect()
           try:
               with pytest.raises(MCPConnectionError, match="already connected"):
                   await client.connect()
           finally:
               await client.disconnect()
   ```

   `pytest`, `MCPSource`, `MCPClient`, `MCPConnectionError` are already imported at the top of `tests/test_mcp_integration.py` (added by L4) — no new top-level imports needed.

5. **Run the in-container test cycle** — verify each new test in isolation, then full suite:

   ```bash
   docker compose exec the-one make test ARGS='-k TestBuildStdioEnviron -v'  # 6 pass
   docker compose exec the-one make test ARGS='-k TestL5Stdio -v'  # 3 pass
   docker compose exec the-one make test  # 1136 passed + 1 skipped
   docker compose exec the-one make lint  # clean
   ```

6. **Update flight log L5 entry** in `## Leg Progress / ### L5: Stdio transport` covering: status (landed); changes (transport module body, dispatch wiring, helper imports from `the_one/platform/env.py`); notes (env-merge SDK behavior — the SDK adds its own floor under our env; secrets-wins-over-allowlist is documented behavior; subprocess startup runtimes for the 3 integration tests); test count before/after (1127 → 1136); lint status.

## Edge Cases

- **`source.config.get("env", {}) or {}`**: defensive against `env: None` (Pydantic doesn't auto-coerce; F1 validator should reject — but defense-in-depth handles a future schema drift).

- **`source.config.get("args", [])`**: F1's API validator gates `args: list[str]` shape, but if `args` is missing entirely (operator only set `command`), default to `[]`. The SDK's `StdioServerParameters` requires `args` (Pydantic `args: list[str]` with no default).

- **`source.config.get("cwd")`**: returns `None` if absent. The SDK's `StdioServerParameters.cwd` accepts `str | Path | None = None`. Pass `None` through unchanged.

- **Subprocess startup variance in CI**: per L3 measurements, FastMCP cold-start is ~0.5-0.8s. Three L5 integration tests serially = ~2-3s. If CI variance pushes this >5s combined, the leg is acceptable — adaptation is a future routine-maintenance concern (session-scoped subprocess fixture).

- **Per-test timeout protection**: `pytest-timeout 2.4.0` is installed in the dev container but NOT globally configured (no `addopts = "--timeout=N"` in pyproject). Without per-test deadlines, a hung FastMCP subprocess (broken pipe, missing PYTHONPATH typo, deadlock) would stall the suite indefinitely. **L5 adds `@pytest.mark.timeout(15)` to each `TestL5Stdio` integration test** — well above the ~0.8s real cold-start; tight enough to fail fast on a wedge. Unit tests in `TestBuildStdioEnviron` are pure-Python and don't need timeouts.

- **`stdio_client`'s `errlog=sys.stderr` default**: FastMCP's startup INFO logs surface in `pytest -v` output. Acceptable per L3 edge case — not silenced. If this becomes noisy enough to obscure real test failures, the leg's adaptation criterion is to monkeypatch `errlog=open(os.devnull, "w")` in the fixture; defer to L5 implementer's discretion.

- **`_build_subprocess_env()` reading `os.environ`**: in production, the spawned process inherits PATH/HOME/etc. from the parent process's env. In tests, the test process has its own env (set by pytest/the test runner). `build_stdio_environ` accepts `allowlist_env` as a parameter so unit tests don't depend on the test process's actual env (test #1 passes a known dict). Integration tests rely on the test process having PATH set (always true in CI/dev).

- **SDK's env-merge floor**: per L3 edge case, the SDK applies `get_default_environment()` UNDER our env. This means the actual spawned environ has 3 layers: SDK floor → our allowlist → operator kv. If the operator wants to PREVENT the SDK from leaking some inherited env var into the child, they currently CAN'T — the SDK floor wins on keys they don't override. This is an intentional limitation of F2 (the OS-level sandbox is F3). Documented in the module docstring.

- **`MCPSource.merged_config()` non-use**: per flight §11, F2 explicitly does NOT consume `merged_config()` for stdio environ assembly. Documented in the module docstring AND in `agents.md` (per L1's contract enumeration). Future maintainers should NOT "fix" this by switching to `merged_config()`.

- **`async with stdio_client(params) as (read, write):`**: SDK returns a 2-tuple (NOT 3-tuple like streamable-http's `(read, write, get_session_id)`). Confirmed at design time via in-container probe.

- **`StdioServerParameters` field `args: list[str]`**: the SDK provides a `default_factory=[]`, so `args` is technically NOT required at the Pydantic layer. We still pass `source.config.get("args", [])` defensively in case F1 validator drift ever lets `args` go absent — this guarantees an explicit empty list reaches the SDK regardless.

- **`encoding` and `encoding_error_handler` SDK defaults**: `encoding="utf-8"`, `encoding_error_handler="strict"`. F2 doesn't override these. The FastMCP fixture writes UTF-8 JSON-RPC; `strict` is appropriate.

- **F4-pool compatibility**: `connect_stdio` is stateless (only reads its arguments + module-globals from the platform layer). Each MCPClient instance owns its own `_transport_cm` per L2's design. F4 will hold MCPClient instances across multiple tool calls; the warm-pool acquires `_transport_connect` once and re-uses the session. Stdio's subprocess lifetime tracks the `_transport_cm` (kept alive across `list_tools`/`call_tool` calls within a single connect/disconnect bracket). F4-pool-safe.

## Files Affected

- `the_one/mcp/transports/stdio.py` — replace L1 placeholder with the full implementation
- `the_one/mcp/client.py` — update `_transport_connect`'s stdio branch (~5 lines changed)
- `tests/test_mcp_client.py` — extend with `TestBuildStdioEnviron` (6 unit tests + helper)
- `tests/test_mcp_integration.py` — extend with `TestL5Stdio` (3 integration tests; reuses L4's top-level imports)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests passing — exactly 1136 passing + 1 skipped (1127 baseline post-L4 + 6 unit + 3 integration)
- [x] `make lint` clean (no NEW ruff errors) — run inside the container
- [x] Update flight-log.md with leg progress entry under `## Leg Progress / ### L5: Stdio transport`
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Check off this leg in flight.md (under `### Legs`)
- [x] **Do NOT commit** — agentic-workflow batches commits at flight end

## Citation Audit

5 SDK + repo citations verified at leg-design time:

1. `the_one/mcp/client.py::_transport_connect` (post-L4): verified the stdio branch at lines 67-69 raises `NotImplementedError("transport 'stdio' not implemented; L5 lands it")`. L5 replaces this branch with `connect_stdio` dispatch
2. `the_one/mcp/transports/stdio.py` — verified L1 placeholder shape (docstring only, no code); L5 replaces the entire body
3. `the_one/platform/env.py` — verified `_ENV_ALLOWLIST: tuple[str, ...] = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TERM", "TZ")` and `_build_subprocess_env() -> dict[str, str]` (filters os.environ by allowlist); both already module-level
4. `mcp.client.stdio.stdio_client(server: StdioServerParameters, errlog: TextIO = sys.stderr)` — verified signature in container at design time. Returns 2-tuple `(read, write)`. NOT 3-tuple (different from streamable-http's 3-tuple `(read, write, get_session_id)`)
5. `mcp.client.stdio.StdioServerParameters` — verified Pydantic model fields: `command: str` (required), `args: list[str]` (required, no default), `env: dict[str, str] | None = None`, `cwd: str | Path | None = None`, `encoding: str = "utf-8"`, `encoding_error_handler: Literal["strict", "ignore", "replace"] = "strict"`

All citations clean — no drift.
