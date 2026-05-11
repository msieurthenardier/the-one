# Leg: 02-list-tools-401-translation

**Status**: landed
**Flight**: [OAuth simplification + Test connection button](../flight.md)

## Objective

Extend `MCPClient.list_tools` with `MCPAuthRequired` translation that mirrors `call_tool`'s F5 L4 except*-group pattern, and extend `MCPToolProvider.get_tools_for_agent`'s graceful-degrade-skip except list to include `MCPAuthRequired` — closing the auth-on-`tools/list` common-posture gap that F6 shipped open (Cloudflare API MCP and most production OAuth MCPs surface 401 on `list_tools`, not `call_tool`).

## Context

F5 L4 added `try/except* (OAuthFlowError, OAuthTokenError) / except* httpx.HTTPStatusError` to `MCPClient.call_tool` to translate SDK auth-flow failures and no-provider 401 responses into `MCPAuthRequired`. Probe-confirmed at F5 L4 (A8/A9 stake-test) that the SDK's anyio TaskGroup wraps these in a `BaseExceptionGroup` in production paths — `except*` matches both bare and grouped surfaces.

`list_tools` was NOT extended at F5 — it still translates `(httpx.HTTPError, anyio.ClosedResourceError)` to `MCPConnectionError` blindly. That means: when a server (Cloudflare API MCP, most production OAuth MCPs) requires auth on `tools/list` and the client connects without a provider, the 401 surfaces as `MCPConnectionError("MCP transport error during list_tools: HTTPStatusError: 401 ...")` instead of `MCPAuthRequired`. F6's `MCPToolProvider.get_tools_for_agent` graceful-degrade-skips on `MCPConnectionError`, so the agent silently builds with zero tools from that source — operator gets no path forward.

L2 closes the gap. After L2:
1. `MCPClient.list_tools` raises `MCPAuthRequired` (with `resource_metadata_url` parsed from `WWW-Authenticate` header where present) on 401 — same shape as `call_tool` post-F5-L4.
2. `MCPToolProvider.get_tools_for_agent`'s except list at `_tool_provider.py:225-229` extends from `(MCPSandboxError, MCPConnectionError, MCPVersionMismatch)` to `(MCPSandboxError, MCPConnectionError, MCPVersionMismatch, MCPAuthRequired)`. The graceful-degrade-skip log line gains an `auth_required` discriminator (per flight Design Decision §1 + the technical-approach note about ops visibility) so the F7 inspector can later render the right operator message.
3. F6.5's L3 (Test button) becomes the operator-facing path — once L2 lands, an OAuth-protected source attached to an agent with no tokens skips cleanly at agent build, and the operator runs the Test button on the source-edit page to drive the OAuth flow at source-creation time.

L2 introduces no behavior change for non-401 / non-OAuth `list_tools` failures: timeouts, version mismatches, transport errors, McpError responses all translate exactly as before.

Key learnings from prior legs (flight log + F5 L4):

- **`except*` matches both bare and grouped exception shapes**: F5 L4 verified this against production SDK paths. The pattern is identical to `call_tool`'s; transcribe verbatim with field substitutions.
- **`extract_field_from_www_auth` is the canonical 401→PRM-URL extractor**: imported from `mcp.client.auth.utils` already in `client.py:26`; no new import needed.
- **`MCPAuthRequired.consent_url` is None at this layer**: only the OAuth modal flow (F5) populates `consent_url`. Pre-flow `MCPAuthRequired` carries `(source_id, resource_metadata_url)` only — the lazy-OAuth flow is responsible for filling `consent_url` later. This matches `call_tool`'s pattern at `client.py:594-598`.
- **The `try/except*` block must sit INSIDE `asyncio.timeout(...)` AND BEFORE the existing translations**: `call_tool`'s outer `try` starts at line 555 and the full pattern runs to line 617; `list_tools` mirrors. The outer `except asyncio.TimeoutError`, `except UrlElicitationRequiredError`, `except McpError`, `except (httpx.HTTPError, anyio.ClosedResourceError)` clauses run AFTER the inner except* clauses, so the inner OAuth-aware translations have priority.
- **`MCPAuthRequired` does NOT extend `McpError`**: per `the_one/mcp/errors.py`, the class extends `MCPClientError` → `Exception` (NOT `McpError`, the SDK class). So the explicit `except MCPAuthRequired: raise` before `except McpError` is defensive — strictly not required for class-resolution reasons, but kept for parity with `call_tool`'s pattern + clarity.
- **`MCPAuthRequired` constructor: keyword-only fields**: `errors.py` defines `__init__(self, source_id: str, *, resource_metadata_url: str | None = None, consent_url: str | None = None)`. The `*` makes the latter two keyword-only. Use the keyword form `MCPAuthRequired(source_id=..., resource_metadata_url=..., consent_url=...)` everywhere — positional form raises `TypeError`. This is consistent with `call_tool`'s usage at `client.py:568-572, 594-598, 327-330`.
- **Module-level imports already in place**: `OAuthFlowError`, `OAuthTokenError`, `extract_field_from_www_auth`, `MCPAuthRequired`, `httpx`, `anyio` are all imported at `client.py:21-39`. No new imports needed.

## Inputs

What exists before this leg runs:

- Branch `flight/6_5-oauth-simplification` with L0 + L1 landed (uncommitted)
- `the_one/mcp/client.py:440-470` — current `list_tools` implementation:
  ```python
  async def list_tools(self) -> list[MCPTool]:
      """..."""
      if not self._is_alive or self._session is None:
          raise MCPConnectionError(
              "MCPClient is not connected; cannot list tools."
          )
      self._touch_activity()
      # L6b: SDK error translation. UrlElicitationRequiredError IS a subclass
      # of McpError (verified at L6b design review) — re-raise BEFORE the
      # McpError clause or it gets silently swallowed into MCPConnectionError,
      # breaking F3+'s ability to surface URL elicitation prompts.
      try:
          async with asyncio.timeout(self.timeout_seconds):
              result = await self._session.list_tools()
      except asyncio.TimeoutError:
          raise MCPConnectionError(
              f"MCP list_tools exceeded {self.timeout_seconds} seconds"
          ) from None
      except UrlElicitationRequiredError:
          raise
      except McpError as e:
          raise MCPConnectionError(f"MCP list_tools failed: {e}") from None
      except (httpx.HTTPError, anyio.ClosedResourceError) as e:
          raise MCPConnectionError(
              f"MCP transport error during list_tools: {type(e).__name__}: {e}"
          ) from None
      # ... [tool wrapping continues at line 472-end] ...
  ```
- `the_one/mcp/client.py:555-617` — reference `call_tool` translation pattern (the source-of-truth for L2's mirror)
- `the_one/mcp/_tool_provider.py:225-236` — the except list + graceful-degrade-skip log:
  ```python
  except (
      MCPSandboxError,
      MCPConnectionError,
      MCPVersionMismatch,
  ) as e:
      logger.warning(
          "MCP source %r failed to connect: %s: %s; skipping",
          source.name,
          type(e).__name__,
          e,
      )
      continue
  ```
- `the_one/mcp/errors.py` — defines `MCPAuthRequired` with fields `(source_id, resource_metadata_url, consent_url)`; F6 L0 canonical
- `tests/test_mcp_client_list_tools.py` (or whatever the existing list_tools test file is — implementer should grep `from the_one.mcp.client import MCPClient` in `tests/` to find the canonical test file). If no dedicated `list_tools` test file exists, the new tests join the existing `test_mcp_client.py` or `test_mcp_integration.py` pattern.
- `tests/test_mcp_tool_provider.py` (the existing tool-provider test file — implementer should grep for `MCPToolProvider` in `tests/` to find canonical location). The MCPAuthRequired graceful-skip test joins the existing tests there.

## Outputs

What exists after this leg completes:

- `the_one/mcp/client.py::MCPClient.list_tools` translates 401 (and `OAuthFlowError`/`OAuthTokenError`) to `MCPAuthRequired` via the `try/except*` pattern mirroring `call_tool`. Non-401 / non-OAuth failures translate as before.
- `the_one/mcp/_tool_provider.py::MCPToolProvider.get_tools_for_agent` extends its except tuple to include `MCPAuthRequired`; graceful-degrade-skips with a discriminator distinguishing AUTH-skipped from CONNECT-skipped (per flight technical approach).
- 4 new unit tests covering:
  1. `list_tools` 401 wrapped in `BaseExceptionGroup` translates to `MCPAuthRequired`
  2. `list_tools` `OAuthFlowError` (bare or grouped) translates to `MCPAuthRequired`
  3. `list_tools` `OAuthTokenError` (bare or grouped) translates to `MCPAuthRequired`
  4. `MCPToolProvider.get_tools_for_agent` graceful-degrade-skips on `MCPAuthRequired`; agent builds with remaining sources' tools; log line carries the AUTH discriminator
- All retained pytest suites pass under `docker exec the-one pytest -m 'not browser and not live and not pixel' --ignore=tests/test_mcp_pool.py`.
- Grep sweep: `grep -rn "MCPAuthRequired" the_one/mcp/client.py the_one/mcp/_tool_provider.py` shows the new references on top of the existing F5 L4 ones.

## Acceptance Criteria

- [ ] `MCPClient.list_tools` body has a `try / except* (OAuthFlowError, OAuthTokenError) / except* httpx.HTTPStatusError` block wrapping `await self._session.list_tools()` — structurally identical to `call_tool`'s F5 L4 pattern (just with `source.id` field reads, not `tool_name`)
- [ ] The outer `try` keeps the existing `except asyncio.TimeoutError`, `except UrlElicitationRequiredError`, `except McpError`, `except (httpx.HTTPError, anyio.ClosedResourceError)` translations — none deleted, none re-ordered
- [ ] A new `except MCPAuthRequired: raise` line sits between `except asyncio.TimeoutError` and `except UrlElicitationRequiredError` (mirrors `call_tool:608-609`); without this line, the inner `MCPAuthRequired` would be caught by the outer `except McpError` clause and silently rewrapped as `MCPConnectionError`
- [ ] No new imports needed — all required SDK + project imports are already present at `client.py:21-39`. (Implementer: confirm before adding any.)
- [ ] `MCPToolProvider.get_tools_for_agent`'s except tuple at `_tool_provider.py:225-229` extends to `(MCPSandboxError, MCPConnectionError, MCPVersionMismatch, MCPAuthRequired)` — alphabetic order is up to implementer; the post-F6 convention is the order they were introduced in
- [ ] The graceful-degrade-skip log line at `_tool_provider.py:230-235` includes a discriminator distinguishing AUTH-skipped from CONNECT-skipped — implementation choice: separate log statements branched on `isinstance(e, MCPAuthRequired)`, OR a `kind` field in the log call's f-string. Either is acceptable; the contract is that an ops-engineer reading the log line can tell which class of failure was skipped without reading source. Recommended:
  ```python
  except MCPAuthRequired as e:
      logger.warning(
          "MCP source %r requires authorization; skipping (auth_required, source_id=%s)",
          source.name,
          e.source_id,
      )
      continue
  except (MCPSandboxError, MCPConnectionError, MCPVersionMismatch) as e:
      logger.warning(
          "MCP source %r failed to connect: %s: %s; skipping",
          source.name,
          type(e).__name__,
          e,
      )
      continue
  ```
- [ ] `tests/test_mcp_client*.py` (or wherever `list_tools` tests live) contains 3 new tests:
  1. `test_list_tools_401_in_exception_group_raises_mcp_auth_required` — mocks `self._session.list_tools` to raise `BaseExceptionGroup("test", [httpx.HTTPStatusError(...)])` with a 401 response; asserts `MCPAuthRequired` raised with the expected `source_id` and `resource_metadata_url` extracted from the WWW-Authenticate header
  2. `test_list_tools_oauth_flow_error_raises_mcp_auth_required` — mocks `list_tools` to raise `OAuthFlowError(...)`; asserts `MCPAuthRequired` raised with `consent_url=None, resource_metadata_url=None`
  3. `test_list_tools_oauth_token_error_raises_mcp_auth_required` — mocks `list_tools` to raise `OAuthTokenError(...)`; asserts `MCPAuthRequired` raised
- [ ] `tests/test_mcp_tool_provider.py` (or wherever the tool-provider tests live) contains 1 new test:
  4. `test_get_tools_for_agent_graceful_skips_on_mcp_auth_required` — sets up two MCP sources, mocks one's `acquire`/`list_tools` to raise `MCPAuthRequired`, asserts the agent builds with the second source's tools only and the log carries the AUTH discriminator (use `caplog`)
- [ ] Existing `list_tools` tests untouched (the pre-F6.5 transport-error and timeout behaviors are unchanged)
- [ ] Existing `MCPToolProvider` tests untouched
- [ ] Test suite green:
  ```
  docker exec the-one pytest -m 'not browser and not live and not pixel' --ignore=tests/test_mcp_pool.py --tb=short -q
  ```
  exits 0 (modulo the 3 pre-existing `test_mcp_sandbox_integration.py` bwrap failures L0/L1 documented)
- [ ] Browser tests (`test_oauth_modal_flow.py` + `test_flow_studio_mcp_editor.py`): still pass — L2 doesn't touch any frontend code, but verifying no regression in case of indirect effect

## Verification Steps

How to confirm each criterion is met:

- **`list_tools` translation pattern check**:
  ```bash
  grep -A 30 "async def list_tools" the_one/mcp/client.py | head -50
  ```
  Should show the `try/except*` block matching the call_tool pattern.

- **Cross-check against `call_tool`**: open `client.py` to lines 540-617 and 440-510 side by side. The two should structurally mirror each other (different field references — `tool_name` vs `source.id`, `call_timeout_seconds` vs `timeout_seconds`).

- **Imports unchanged**: `git diff the_one/mcp/client.py` should show ZERO additions to the import block (lines 1-40). If implementer accidentally added a new import, that's a smell — every required symbol is already there.

- **Tool provider except list**:
  ```bash
  grep -A 15 "except.*MCPSandboxError" the_one/mcp/_tool_provider.py
  ```
  Should show `MCPAuthRequired` either in the same tuple or as a separate preceding `except` block (per the recommended pattern in AC).

- **Test runs**:
  ```bash
  docker exec the-one pytest tests/test_mcp_client.py tests/test_mcp_tool_provider.py -v --tb=short
  ```
  All new tests pass; no existing tests broken. Implementer: substitute the actual test file names found via grep.

- **Full unit suite**:
  ```bash
  docker exec the-one pytest -m 'not browser and not live and not pixel' --ignore=tests/test_mcp_pool.py --tb=short -q
  ```
  Exits 0 (modulo 3 pre-existing sandbox failures).

- **No frontend regression**:
  ```bash
  docker exec the-one pytest -m browser tests/browser/test_oauth_modal_flow.py tests/browser/test_flow_studio_mcp_editor.py -v
  ```
  Exits 0 (23 tests).

## Implementation Guidance

The leg is small and surgical. Three edits total — two in production code, one set of test additions. Order matters:

### Step 1: `client.py::list_tools` — add the `try/except*` translation block

Open `the_one/mcp/client.py`, find `async def list_tools(self)` (around line 432). Find the existing try/except block at lines 456-470. Replace it with the mirrored pattern from `call_tool`:

```python
self._touch_activity()
try:
    async with asyncio.timeout(self.timeout_seconds):
        # The except*-group below catches OAuth/auth exceptions whether
        # they bubble bare (test stubs) or wrapped in a BaseExceptionGroup
        # from the SDK's anyio TaskGroup (production SDK path).
        # `except*` matches both shapes. F6.5 L2 mirrors call_tool's
        # F5 L4 (A8/A9) pattern — see client.py:555-603 for the original.
        try:
            result = await self._session.list_tools()
        except* (OAuthFlowError, OAuthTokenError):
            # SDK auth-flow failed. Provider attached but couldn't
            # complete (refresh failed / discovery failed / DCR failed).
            raise MCPAuthRequired(
                source_id=self.source.id,
                resource_metadata_url=None,
                consent_url=None,
            ) from None
        except* httpx.HTTPStatusError as eg:
            # No-provider 401 path. The SDK's transport surfaces 401 as
            # an ExceptionGroup wrapping HTTPStatusError. Walk the group;
            # translate 401 to MCPAuthRequired (parsing the
            # WWW-Authenticate `resource_metadata` field per RFC 9728);
            # re-raise other statuses for the outer except to translate.
            auth_error: httpx.HTTPStatusError | None = None
            for sub in eg.exceptions:
                if (
                    isinstance(sub, httpx.HTTPStatusError)
                    and sub.response.status_code == 401
                ):
                    auth_error = sub
                    break
            if auth_error is not None:
                rmd = extract_field_from_www_auth(
                    auth_error.response, "resource_metadata"
                )
                raise MCPAuthRequired(
                    source_id=self.source.id,
                    resource_metadata_url=rmd,
                    consent_url=None,
                ) from None
            raise eg.exceptions[0] from None
except asyncio.TimeoutError:
    raise MCPConnectionError(
        f"MCP list_tools exceeded {self.timeout_seconds} seconds"
    ) from None
except MCPAuthRequired:
    raise
except UrlElicitationRequiredError:
    raise
except McpError as e:
    raise MCPConnectionError(f"MCP list_tools failed: {e}") from None
except (httpx.HTTPError, anyio.ClosedResourceError) as e:
    raise MCPConnectionError(
        f"MCP transport error during list_tools: {type(e).__name__}: {e}"
    ) from None
```

The pre-existing comment at line 452-455 (about `UrlElicitationRequiredError` ordering) can be retained — its content still applies. Optionally extend the comment to note the F6.5 L2 `MCPAuthRequired` re-raise rationale, mirroring the comment at `call_tool:542-554`.

After the `try/except` block, the rest of the function body (lines 472+ — tool wrapping, tools_cache assignment, return) is unchanged.

### Step 2: `_tool_provider.py::get_tools_for_agent` — extend except list with MCPAuthRequired

Open `the_one/mcp/_tool_provider.py`. Find the import block (line 49-52) and add `MCPAuthRequired`:

```python
from the_one.mcp.errors import (
    MCPAuthRequired,  # NEW
    MCPConnectionError,
    MCPRegistrationError,
    MCPSandboxError,
    MCPVersionMismatch,
)
```

(Implementer: confirm `MCPRegistrationError` is in the existing import — it's referenced at line 252 — and preserve alphabetic ordering or whatever convention the file uses.)

Find the except block at lines 225-236. Split into two except clauses (preserving the existing connect-failure path and adding the new auth-required path) per the AC's recommended pattern:

```python
except MCPAuthRequired as e:
    logger.warning(
        "MCP source %r requires authorization; skipping (auth_required, source_id=%s)",
        source.name,
        e.source_id,
    )
    continue
except (
    MCPSandboxError,
    MCPConnectionError,
    MCPVersionMismatch,
) as e:
    logger.warning(
        "MCP source %r failed to connect: %s: %s; skipping",
        source.name,
        type(e).__name__,
        e,
    )
    continue
```

**Why split the except into two clauses (not one tuple)?** Not for class-resolution reasons — `MCPAuthRequired` does NOT extend any of `MCPSandboxError`, `MCPConnectionError`, or `MCPVersionMismatch` (they share only `MCPClientError` as ancestor), so a single tuple `(MCPSandboxError, MCPConnectionError, MCPVersionMismatch, MCPAuthRequired)` would also work correctly. The split is for **observability**: auth-pending and connect-failed are distinct ops scenarios warranting distinct log lines. The auth-required clause is placed first only by convention; either ordering compiles and runs identically.

**Module docstring at lines 14-18 is STALE post-L2 and contains text that directly contradicts the new behavior.** The current docstring at line 17-18 contains language saying `list_tools` translates 401 to `MCPConnectionError`, NOT `MCPAuthRequired`. That whole caveat is the pre-L2 state; L2 inverts it. The implementer must DELETE lines 17-18 (the contradicting caveat) and rewrite the surrounding paragraph to reflect L2 reality:

Replace lines 14-18 with something like:

```
:meth:`MCPClient.list_tools` raises :class:`MCPSandboxError` /
:class:`MCPConnectionError` / :class:`MCPVersionMismatch` /
:class:`MCPAuthRequired` → log + skip the source, continue with others.
The agent builds with whatever sources connected successfully and were
authorized; auth-required sources are skipped with a discriminator log
line so ops engineers can distinguish auth-pending from connect-failed.
```

The exact wording is implementer choice — the binding contract is: zero remaining sentences saying "NOT `MCPAuthRequired`" or equivalent. Read the surrounding 30 lines of docstring before editing — there may be other dependent sentences that need re-flowing.

### Step 3: Tests

Test files (verified at design review cycle 1):
- **`MCPClient.list_tools` tests**: `tests/test_mcp_client.py`, class `TestListToolsAndCallTool` starting around line 858. New `list_tools` tests join this class.
- **`MCPToolProvider` tests**: `tests/test_mcp_tool_provider.py`, class `TestMCPToolProvider` starting around line 443. The new graceful-skip test joins this class.
- **Existing helpers in `test_mcp_tool_provider.py`** (use these, don't reinvent):
  - `_stub_mcp_client(...)` at line 432 — builds stub MCPClient instances; pass it the exception you want `list_tools` to raise (e.g. `_stub_mcp_client(MCPAuthRequired(source_id="x"))`)
  - The existing `monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)` pattern at line 561 — use the module-object form (`provider_mod`, not the dotted-string form) per file convention.
- **Existing helpers in `test_mcp_client.py`** (find by reading the file): there should be a connected-client fixture or factory function around the `TestListToolsAndCallTool` class. Adapt to what's there; don't introduce new fixtures unless none exists.

**Required imports for the test file** (add at top if missing):

```python
import httpx
from unittest.mock import AsyncMock, MagicMock
from mcp.client.auth.exceptions import OAuthFlowError, OAuthTokenError
from the_one.mcp.errors import MCPAuthRequired
```

(`OAuthFlowError` and `OAuthTokenError` are SDK classes from `mcp.client.auth.exceptions`, NOT from `the_one.mcp.oauth.errors`. The flight log Phase 1b recon item "cosmetic drift" notes this; use the SDK import path.)

**Test 1: `test_list_tools_401_in_exception_group_raises_mcp_auth_required`**

```python
import httpx
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_list_tools_401_in_exception_group_raises_mcp_auth_required(...):
    client = await _connected_client()  # use existing fixture for a connected MCPClient
    
    # Build a 401 HTTPStatusError with WWW-Authenticate header carrying
    # resource_metadata URL.
    response_401 = httpx.Response(
        status_code=401,
        headers={
            "WWW-Authenticate": (
                'Bearer resource_metadata="https://example.com/.well-known/oauth-protected-resource"'
            )
        },
        request=httpx.Request("POST", "https://example.com/mcp"),
    )
    inner = httpx.HTTPStatusError(
        "401 Unauthorized", request=response_401.request, response=response_401
    )
    eg = BaseExceptionGroup("test group", [inner])
    
    client._session = MagicMock()
    client._session.list_tools = AsyncMock(side_effect=eg)
    
    with pytest.raises(MCPAuthRequired) as exc_info:
        await client.list_tools()
    
    assert exc_info.value.source_id == client.source.id
    assert exc_info.value.resource_metadata_url == (
        "https://example.com/.well-known/oauth-protected-resource"
    )
    assert exc_info.value.consent_url is None
```

**Test 2: `test_list_tools_oauth_flow_error_raises_mcp_auth_required`**

```python
from mcp.client.auth.exceptions import OAuthFlowError

@pytest.mark.asyncio
async def test_list_tools_oauth_flow_error_raises_mcp_auth_required(...):
    client = await _connected_client()
    client._session = MagicMock()
    client._session.list_tools = AsyncMock(side_effect=OAuthFlowError("discovery failed"))
    
    with pytest.raises(MCPAuthRequired) as exc_info:
        await client.list_tools()
    
    assert exc_info.value.source_id == client.source.id
    assert exc_info.value.resource_metadata_url is None
    assert exc_info.value.consent_url is None
```

**Test 3: `test_list_tools_oauth_token_error_raises_mcp_auth_required`**

```python
from mcp.client.auth.exceptions import OAuthTokenError

@pytest.mark.asyncio
async def test_list_tools_oauth_token_error_raises_mcp_auth_required(...):
    client = await _connected_client()
    client._session = MagicMock()
    client._session.list_tools = AsyncMock(side_effect=OAuthTokenError("refresh failed"))
    
    with pytest.raises(MCPAuthRequired) as exc_info:
        await client.list_tools()
    
    assert exc_info.value.source_id == client.source.id
    assert exc_info.value.resource_metadata_url is None
    assert exc_info.value.consent_url is None
```

**Test 4: `test_get_tools_for_agent_graceful_skips_on_mcp_auth_required`**

Joins `tests/test_mcp_tool_provider.py::TestMCPToolProvider`. **Use the existing `_stub_mcp_client(...)` helper at line 432** to build the auth-required client — pass it `MCPAuthRequired(source_id="github_mcp")` as the exception. **Use the existing `monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)` pattern at line 561** — module-object form, not dotted-string. Adapt to whatever fixture convention the existing tests use for source/config setup.

Sketch (illustrative — adapt to file's existing patterns):

```python
@pytest.mark.asyncio
async def test_get_tools_for_agent_graceful_skips_on_mcp_auth_required(
    monkeypatch, caplog
):
    auth_required_source = _make_source("github_mcp", ...)
    healthy_source = _make_source("filesystem_mcp", ...)
    config = AgentConfig(
        ...,
        mcp_source_ids=["github_mcp", "filesystem_mcp"],
    )
    
    # Use existing _stub_mcp_client + _stub_acquire helpers per file convention.
    def _stub_acquire(agent_name, source_id, source_override=None):
        if source_id == "github_mcp":
            return _stub_mcp_client(MCPAuthRequired(source_id=source_id))
        return _stub_mcp_client(tools=[_mock_tool("read_file")])
    
    monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)
    # ... mock repo.get for both sources per file convention ...
    
    with caplog.at_level(logging.WARNING, logger="the_one.mcp._tool_provider"):
        provider = MCPToolProvider()
        tools = await provider.get_tools_for_agent("test_agent", config)
    
    # Healthy source's tool present; auth-required source's tools absent.
    assert len(tools) == 1
    assert tools[0].name.endswith("read_file")  # post-prefix
    
    # Log line carries the AUTH discriminator.
    auth_log = [r for r in caplog.records if "auth_required" in r.message]
    assert len(auth_log) == 1
    assert "github_mcp" in auth_log[0].message
```

The `_stub_mcp_client` and `_stub_acquire` helpers may take different argument shapes than illustrated — the contract is "use what exists." Read 50 lines of context around `_stub_acquire` (line 561) and `_stub_mcp_client` (line 432) before writing the test, and follow the call convention.

### Step 4: Run tests

```bash
# Targeted file run first:
docker exec the-one pytest tests/test_mcp_client.py tests/test_mcp_tool_provider.py -v --tb=short

# Then full unit suite:
docker exec the-one pytest -m 'not browser and not live and not pixel' --ignore=tests/test_mcp_pool.py --tb=short -q

# Then browser tests (sanity):
docker exec the-one pytest -m browser tests/browser/test_oauth_modal_flow.py tests/browser/test_flow_studio_mcp_editor.py
```

If any new test fails, debug in place — common modes:
- `BaseExceptionGroup` is Python 3.11+ syntax; if the test file imports something incompatible, use the `exceptiongroup` backport's `ExceptionGroup` (the project is 3.11+ per `pyproject.toml`, so `BaseExceptionGroup` is built-in).
- `extract_field_from_www_auth` returns `None` if the field isn't present in the header — the test must build a response with the exact `WWW-Authenticate` header shape per RFC 9728 §5.1: `Bearer resource_metadata="<url>"`. Quoting matters.
- `MCPAuthRequired` field names — verify by reading `the_one/mcp/errors.py`. The fields are `source_id`, `resource_metadata_url`, `consent_url` (per F6 L0).

## Edge Cases

- **`except* httpx.HTTPStatusError` matching non-401 inside the group**: if the SDK happens to raise a 503 or 500 wrapped in an ExceptionGroup, the `except*` clause matches, and the inner walk-and-translate falls through to `raise eg.exceptions[0]`. The outer `except (httpx.HTTPError, anyio.ClosedResourceError)` catches it and translates to `MCPConnectionError` — same behavior as pre-L2. Test scope: not required, but the mirror to `call_tool`'s pattern preserves this correctness.
- **401 with no `WWW-Authenticate` header**: `extract_field_from_www_auth` returns `None`; `MCPAuthRequired.resource_metadata_url=None`. Behavior is correct (lazy-OAuth flow proceeds without PRM URL hint; SDK falls back to default discovery). Test 1 covers the WITH-header case; the WITHOUT-header case is implicitly covered by Tests 2 + 3 (which raise OAuth exceptions, not 401-via-HTTPStatusError, but exercise the same `resource_metadata_url=None` outcome).
- **Mixed group with 401 + non-401**: the inner walk picks the FIRST 401 it finds (`break` on match). If the group has both a 401 and a 500, `MCPAuthRequired` is raised. This matches `call_tool`'s behavior at `client.py:582-590` and is desirable — auth-required is more actionable than a server error.
- **`MCPAuthRequired` re-raise from inner**: when the inner `except* (OAuthFlowError, OAuthTokenError)` raises `MCPAuthRequired`, the exception propagates out of the `async with asyncio.timeout(...)` and hits the outer `except MCPAuthRequired: raise`. Without that explicit `raise`, the exception WOULD be caught by `except McpError` (because `MCPAuthRequired` extends `McpError`? — check `errors.py`). If `MCPAuthRequired` does NOT extend `McpError`, the explicit re-raise is still good defense; if it DOES extend `McpError`, the re-raise is REQUIRED. Verify by reading `the_one/mcp/errors.py::MCPAuthRequired` definition.
- **`_tool_provider.py` log discriminator format**: ops engineers grep logs by string. The current log line is `"MCP source %r failed to connect: %s: %s; skipping"`. The new auth-required line should NOT use the substring `"failed to connect"` — that would conflate two distinct ops scenarios. Use `"requires authorization"` or `"awaiting OAuth consent"` or similar. The leg's recommended `"requires authorization; skipping (auth_required, source_id=%s)"` is fine; whatever phrasing the implementer picks should be clearly auth-related.
- **`_tool_provider.py` except ordering inside the for-loop**: the `for source in sources:` loop with the `try/except/continue` pattern means each source's failure is independent. Adding `MCPAuthRequired` to its own preceding `except` (per AC recommendation) preserves this — one auth-required source doesn't block others from connecting.
- **Test fixtures for connected client**: if no `_connected_client()` fixture exists, the test file likely has a pattern like `MCPClient(source=..., _is_alive=True, _session=MagicMock())` or uses `monkeypatch.setattr` to bypass `connect()`. Adapt to file convention. The leg's test code is illustrative; the implementer adapts to actual fixture shape.

## Files Affected

- `the_one/mcp/client.py` — extend `list_tools` body with `try/except*` translation block (lines ~456-470 replaced; ~50 lines added net)
- `the_one/mcp/_tool_provider.py` — add `MCPAuthRequired` import; split the existing `except (...)` into a preceding `except MCPAuthRequired` clause + the original tuple; update module docstring to reflect new graceful-skip class
- `tests/test_mcp_client.py` (or canonical list_tools test file) — add 3 new tests
- `tests/test_mcp_tool_provider.py` (or canonical tool-provider test file) — add 1 new test

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing inside the dev container
- [ ] Update flight-log.md with leg progress entry under `## Leg Progress` → `### L2`
- [ ] Set this leg's status to `landed` in this file's header
- [ ] Check off this leg in flight.md
- [ ] **DO NOT commit** — flight 6.5 uses per-flight commit cadence; the Reviewer + commit run after L3

## Citation Audit

10 citation regions verified against current code on branch `flight/6_5-oauth-simplification` post-L0+L1 at leg design time (2026-05-08):

- `client.py:1-46` (imports — confirms `OAuthFlowError`, `OAuthTokenError`, `extract_field_from_www_auth`, `MCPAuthRequired`, `httpx`, `anyio` all imported) — OK
- `client.py:432-470` (existing `list_tools` body — translation block to replace) — OK
- `client.py:555-617` (reference `call_tool` translation pattern — outer try at 555, full block to 617) — OK; note the leg pre-review draft cited `:540-617` which is a wider range that includes the jsonschema-validate prelude; the inner translation pattern starts at 555
- `_tool_provider.py:14-18` (module docstring re: graceful-skip classes) — OK
- `_tool_provider.py:49-52` (import block) — OK
- `_tool_provider.py:225-236` (existing except + warning log) — OK
- `errors.py::MCPAuthRequired` (field names: `source_id`, `resource_metadata_url`, `consent_url`) — verified live during L0; field names canonical
- **Test file locations VERIFIED at design review cycle 1**:
  - `tests/test_mcp_client.py::TestListToolsAndCallTool` at line ~858 — host for Tests 1, 2, 3
  - `tests/test_mcp_tool_provider.py::TestMCPToolProvider` at line ~443 — host for Test 4
  - Helpers: `_stub_mcp_client(...)` at `test_mcp_tool_provider.py:432`; `_stub_acquire` monkeypatch pattern at line 561 using module-object form `monkeypatch.setattr(provider_mod, "acquire", _stub_acquire)`
- `BaseExceptionGroup` Python 3.11+ availability — OK (project pinned 3.11+ per pyproject.toml)
- `extract_field_from_www_auth` SDK-helper behavior (returns None on missing field, parses `Bearer realm="...", resource_metadata="..."` shape per RFC 9728 §5.1) — OK; same helper used by `call_tool`'s F5 L4 pattern

L2 is structurally a transcribe-from-`call_tool` exercise. The risk is lower than L0/L1 because the source-of-truth pattern is in the same file 100 lines below the target, and the project's existing test patterns cover the OAuth surfaces. The expected diff is ~60 production lines + ~80 test lines.

**Design review cycle 1 (2026-05-08)**: Reviewer flagged 1 high + 1 medium issue (+ verified test file locations and helper conventions, plus a citation correction). All incorporated:
- HIGH (resolved) — `_tool_provider.py` module docstring at lines 14-18 contains a STALE caveat saying `list_tools` translates 401 to `MCPConnectionError`, NOT `MCPAuthRequired`. L2 inverts this; the implementer must DELETE the contradicting caveat (not just append). Step 2 instructions updated to make this explicit.
- MEDIUM (resolved) — the AC's rationale for splitting the except into two clauses cited "Python's exception ordering" as the reason. The actual reason is observability — `MCPAuthRequired` doesn't extend any of the other classes, so a single tuple would also work correctly; the split is for log-line clarity. Rationale corrected.
- (informational) — `MCPAuthRequired.__init__` is `(source_id: str, *, resource_metadata_url: str | None = None, consent_url: str | None = None)` — keyword-only after `source_id`. Added to Context section as an explicit reminder.
- (test file finding) — Tests 1-3 join `tests/test_mcp_client.py::TestListToolsAndCallTool` (~line 858); Test 4 joins `tests/test_mcp_tool_provider.py::TestMCPToolProvider` (~line 443) and uses existing `_stub_mcp_client` (line 432) + `_stub_acquire` monkeypatch (line 561, module-object form `provider_mod`).
- (suggestion adopted) — Test 3 now asserts `resource_metadata_url is None` and `consent_url is None` for symmetry with Tests 1-2.
- (citation correction) — `client.py` reference range corrected to `:555-617` (the inner try-block) instead of `:540-617` (which includes jsonschema-validate prelude).
