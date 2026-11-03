# Leg: credentials-take-effect

**Status**: completed
**Flight**: [Per-agent MCP credentials](../flight.md)

## Objective
Make a per-agent MCP credential a validated, never-blank value that reaches the server on the agent's next connection after a save: validate `mcp_overrides` credentials on agent writes (DD2), stop sending blank values and classify their 401 honestly (DD3), resolve the effective source when a pool connection opens and evict on every credential change (DD7), ignore a per-agent Authorization on an OAuth server (DD8), overlay header names case-insensitively (DD1), add the `cache_write`/`record_era` switches the next leg needs (DD6), and add the key-checking test server (DD11), with tests and docs.

## Context
- The flight's DD1-DD11 are the design. Read `../flight.md` first; this leg does not restate the rationale. Its "Architect review 1/2" notes in `../flight-log.md` explain why several rules are shaped as they are.
- Charter criteria this leg starts: 1 (blank values, write-only values kept), 2 (next turn uses new values; two agents, two keys), 4 (OAuth Authorization refused). Criterion 3 (per-agent tool list) is leg 2; the UI is leg 3.
- **Security-sensitive:** credential handling, the pool's connect lifecycle and the MCP sign-in classification (sortie 04). Never log a value; never add a value to an error string.
- **No schema change in this leg.** The per-agent cache table (DD5) and its row deletes arrive in leg 2; this leg's eviction hooks evict pool entries only.
- The Library Test path changes (DD3 missing-values path, the helper switches), so this leg's gate includes the `mcp` and `mcp-connection` browser lanes.
- Debrief lessons that apply: raw-body validation before the merge (sortie 08); the sortie 07 422 shape; sortie 04's evidence rule; falsify each layer (sortie 08 debrief); test HTTP servers must shut down fast (M34 F1: `serve_forever(poll_interval=0.02)` for stdlib servers, a short graceful-shutdown for uvicorn); tests patch `_pool._WORKER_TEARDOWN_TIMEOUT_SECONDS` rather than waiting it out.

## Inputs
- Branch `sortie/09-per-agent-mcp-credentials` at `2958510f` (main), with the sortie artifacts and `tests/behavior/per-agent-mcp-credentials.md` uncommitted in the tree.
- No prior leg.

## Outputs
- Server: new `the_one/mcp/override_validation.py`; `the_one/mcp/_overrides.py`, `_tool_provider.py`, `_tool.py`, `_pool.py`, `client.py`, `transports/streamable_http.py`, `transports/stdio.py`; `the_one/interfaces/web/api.py`.
- Fixture: new `tests/fixtures/mcp/key_server.py`.
- Tests: new unit test files (suggested `tests/test_mcp_agent_credentials.py` for validation/overlay/blank/classification and `tests/test_mcp_pool_resolve.py` for resolve-at-connect and eviction), plus updates to existing tests whose pins change.
- Docs: `the_one/agents.md`, `SECURITY-MODEL.md`.

## Acceptance Criteria

**Validation (DD2)**
- [ ] AC1. `create_agent` and `update_agent` run a new `validate_mcp_overrides(...)` (in `the_one/mcp/override_validation.py`) on the **raw** body's `mcp_overrides`, after `_normalize_surface_fields` and before `_merge_preserved_mcp_credentials`. Every refusal is a detail `{"type": "mcp_override", "loc": ["mcp_overrides", <source name>, "headers"|"env"|"bearer_token", <name>?], "msg": <one plain sentence with no value in it>}`; all refusals in one body are returned together as one 422. Values that are mask-shaped (`_looks_masked`) are not checked. `mcp_repo.list()` is called only when the body carries at least one credential key.
- [ ] AC2. The rules hold, each pinned by a unit test.
  - **Source-independent rules**, applied to every entry, including one whose name matches no source (an orphan entry, which would otherwise break builds once a source takes that name):
    - a header name that is not an RFC 9110 token;
    - a header name in the transport-managed set (`Host`, `Content-Length`, `Transfer-Encoding`, `Connection`, `Content-Type`, `Accept`, `Mcp-Session-Id`, `Mcp-Protocol-Version`, case-insensitive);
    - two header names in one entry that differ only by case;
    - a header value or `bearer_token` that, trimmed, is empty or holds anything but visible ASCII, space and tab;
    - an env name not matching `[A-Za-z_][A-Za-z0-9_]*`;
    - an env value that, trimmed, is empty or contains NUL;
    - a non-string **inner** value, `null` included.
  - **Source-dependent rules**, skipped for an orphan entry:
    - `headers` on a stdio source;
    - `env` on a streamable-http source;
    - `Authorization` (any case) or `bearer_token` on a source with OAuth state (`secrets` holds any `OAUTH_MANAGED_SECRET_KEYS`). The refusal uses exactly the flight's sentence: "This server signs in with OAuth, so its Authorization header can't be set per agent."
    - The OAuth check does **not** use `_cache.auth_posture`: a source with `auth_posture: "oauth"` and no OAuth-managed secret accepts a per-agent `Authorization` (test).
  - **Valid:** a top-level `headers: null`, `env: null` or `bearer_token: null` is a valid clear and is not refused (the merge relies on it, `api.py:~436`). A valid body still saves. Every existing test that PUTs overrides (for example `tests/test_db_api.py:395-449` with its orphan "github" entry) passes unchanged.
- [ ] AC3. (Folded into AC2.)

**Overlay and OAuth skip (DD1, DD8)**
- [ ] AC4. `_apply_override` for streamable-http removes from **both** `config.headers` and `secrets` any Library header whose name equals an agent header name ignoring case (and, when `bearer_token` is applied, any Library `Authorization` in any case), then overlays the agent's names; env names stay case-sensitive. For a source with OAuth state it skips a per-agent `Authorization` (any case) and `bearer_token` (a value stored before the source gained a sign-in is not sent). Unit tests cover both layers, the skip, and that a source without overrides is returned unchanged.

**Blank values and classification (DD3)**
- [ ] AC5. `build_request_headers` and `build_stdio_environ` drop a name whose final value is empty once trimmed. For stdio, a dropped blank lets the allowlist's value for that name through (stated in the docstring). A new helper `missing_values(library_source, effective_source) -> list[str]` (in `mcp/_overrides.py`) returns, case-insensitively for headers, the names the Library configures (`config.headers`/`config.env` and `secrets` minus OAuth-managed keys) whose effective value is blank, in a stable order.
- [ ] AC6. `MCPClient._signin_signal` treats a streamable-http source that **configures** any header name (blank or not, excluding OAuth-managed keys) as credentials evidence: a bare 401 (no `resource_metadata`) with no auth provider is `MCPCredentialsRejected`; a 401 with `resource_metadata` stays `MCPAuthRequired`. The client's source is already the effective one, so it calls `missing_values(self.source, self.source)`. `MCPCredentialsRejected` (`mcp/errors.py:~63-71`) gains an optional `missing: Sequence[str] = ()`:
  - empty: the message is byte-identical to today's (pinned by `tests/test_mcp_tool_provider.py:299`, `tests/test_mcp_signin_detection.py:670`, `tests/test_agent.py:207`, `tests/browser/test_flow_studio_mcp_editor_signin_lifecycle.py:204`);
  - non-empty: the message keeps "rejected the configured credentials" (so the `mcp-error.js:23` headline stays right) and adds one sentence naming the missing names, for example "It needs a value for X-Api-Key, which agents set in their Tools tab." Names only.
  
  Sortie 04's existing tests pass unchanged.
- [ ] AC7. The Library Test (`_test_mcp_connection_inner`) of a **streamable-http** source with missing values:
  - **Where:** the branch sits after the body-override block (~4101-4127) and after `has_live_tokens` is computed (~4160), and **before** the `cached_posture == "no_auth"` early return (~4174), so a cached `no_auth` source with a blank value takes it too. The Library Test has no agent overlay, so it calls `missing_values(src, src)`.
  - **With live sign-in tokens:** Phase A runs as today.
  - **Without tokens:**
    - the Phase 0 probe is skipped, and the no-auth helper runs with `cache_write="shared_no_posture"` and `classify=True` (AC8);
    - on `_SIGNIN_REQUIRED` (an `MCPAuthRequired`) the test enters Phase B through the same steps as the existing fall-through arm (~4207-4218), except that it does **not** call `_persist_oauth_posture` and sets `rejection_evidence=False`. So an OAuth server with a "Set per agent" header can still be signed in to (test);
    - a bare 401 (`MCPCredentialsRejected`) returns the error naming the missing values and runs no client registration (test).
  - `auth_posture` is never written on this path. A Test with no body still records `last_check`.
  - `_is_credentials_rejection` (~4375) uses the configured-names helper instead of `build_request_headers`, which now drops blanks.
  - A **stdio** source with a blank env value takes no special path: the blank is dropped (DD3) and the test runs as today.
  - Every existing Library Test test passes unchanged.
- [ ] AC8. `_build_and_test_no_auth_mcp` (~3748) and `_build_and_test_stdio_mcp` (~3860) gain `cache_write: Literal["none", "shared", "shared_no_posture"] = "shared"`, which replaces their single `merge_cache` call. Their existing `record_era` keyword is kept.
  - `"shared"` reproduces today's writes exactly, `"shared_no_posture"` writes the same fields minus `auth_posture`, and `"none"` writes nothing.
  - Existing call sites do **not** pass `cache_write`, so stubs with the old signature keep working (for example `tests/test_mcp_test_connection_negotiation.py:361`, `_fake(source, source_id, repo_, *, record_era=True)`).
  - The no-auth helper also gains `classify: bool = False`. With `classify=True` (and `from_fallthrough=True`) it returns `_SIGNIN_REQUIRED` only for `MCPAuthRequired`, and the normal error dict for `MCPCredentialsRejected`. Today both fold into `_SIGNIN_REQUIRED` (~3838-3842). With `classify=False`, behaviour is unchanged.
  - Unit tests pin the three modes and both `classify` values.

**Resolve at connect and eviction (DD7)**
- [ ] AC9. `acquire(agent_name, source_id, *, source_override=None, resolve_source=None)`: `resolve_source` (an async callable returning an `MCPSource`) is passed to `_entry_worker` and awaited on the worker task inside its `try`, before the OAuth provider is built and before `MCPClient` is constructed; the OAuth-provider block currently before the `try` (`_pool.py` ~207-224) moves inside it, so any failure there sets `entry.failure` and `client_ready` (test: a resolver that raises does not hang its waiters, and the waiter gets the error). A warm entry never calls the resolver (test).
- [ ] AC10. A resolver in `_tool_provider.py` (lazy imports) loads the stored agent and the stored source and returns `_apply_override(source, override_for(agent.mcp_overrides, source))`; when the agent is not in the store (a `KeyError` from the agent load) it returns the build-time `source_override`; any other failure (for example a deleted source) is raised as `MCPConnectionError` with a fixed message that carries no exception text (test: the tool returns its plain `[error] ...` envelope, not a raw exception). `resolve_source` is passed into `_entry_worker` at the `create_task` call (`_pool.py:~541`), so both of `acquire`'s attempts (including the rebuild after `_evict_stale`) use it. The OAuth imports in the worker stay function-local and keep their exact text (`tests/test_agent_context.py:220` pins `from the_one.agent._context import current_chat_session_id, current_tool_call_id`; `tests/test_mcp_pool.py:1250` patches `the_one.mcp.oauth.build_oauth_provider_for_source`). `MCPClientTool.execute` passes it; build Path A keeps passing its fresh effective source.
- [ ] AC11. Eviction, synchronous, after the write commits: `update_agent`/`create_agent` evict `(name, source_id)` for each source whose final `headers`/`env`/`bearer_token` differ from the stored ones (no eviction when nothing credential-related changed, test); `rename_agent` and `delete_agent` evict every `(name, *)` key through a new `_pool._evict_all_for_agent(name)`; `update_mcp_source` evicts every key for the source (`_evict_all_for_source`) when `type`, `config` (minus `_cache`) or `secrets` change, and not otherwise (test).
- [ ] AC12. End to end in-process, with `key_server.py`. Harness:
  - reach the in-process app through the **factory** form of `_test_http_client_override` (`streamable_http.py:~431-433`): a callable taking `headers` and returning `httpx2.AsyncClient(transport=ASGITransport(app=key_app), headers=headers)`, as in `tests/test_mcp_signin_detection.py:515` and `tests/test_mcp_oauth_integration.py:174`. Never the pre-built-client form, which mutates one shared client's headers (`:428`) and would leak old keys across reconnects;
  - wrap the app in `asgi_lifespan.LifespanManager`, as `tests/conftest.py:277-305` does;
  - drive the saves through `httpx2.AsyncClient(ASGITransport(shared_app()))` on the test's own event loop, never the sync `TestClient`, because `_evict` awaits a worker task on the test loop;
  - patch `_pool._resolve_ttl_seconds` for the long idle TTL.

  The test: agent A saved with key 1 calls a tool (the server sees key 1); A is saved with key 2; A's **same** `MCPClientTool` instance (an open chat's tool, not rebuilt) calls again and the server sees key 2, with the idle TTL far longer than the test. Falsified: with the eviction removed, the second call carries key 1; with the resolver removed (eviction kept), the second call carries key 1. Two agents with different keys on one source each reach it with their own key.

**Fixture (DD11)**
- [ ] AC13. `tests/fixtures/mcp/key_server.py`: a streamable-http MCP server usable in-process (an ASGI app factory taking the header name and a `{key: [tool names]}` map) and as a subprocess (`--port 0` prints `PORT n`; `--header`, `--keys key:tool,tool;key:tool` or an equivalent documented flag), serving `echo` (argument documented, e.g. `message`) and `add` (e.g. `a`, `b`). A request without a matching key gets a bare 401 (no `WWW-Authenticate` resource metadata); `tools/list` returns only that key's tools; a control route (e.g. `GET /_log`) returns entries `{seq, method, key_tail}` with only the last 4 characters of the key. Keys must be at least 8 characters, and the factory refuses shorter ones, so the tail never reveals a whole key. Per-key `tools/list` filtering may be one low-level handler, or one MCP app per key behind a header-routing wrapper with each app's lifespan run; take whichever is simpler. It shuts down within about a second. Its flags, tool arguments and control route are written in its module docstring and copied into `tests/behavior/per-agent-mcp-credentials.md` (replacing the spec's "fixed in leg 1" placeholders).

**Secrets and docs (DD9)**
- [ ] AC14. No new code path logs or returns a credential value: a test runs a refused save, a missing-values Test, a rejected connection and a resolver failure with a distinctive value and asserts it appears in no response body and no captured log record.
- [ ] AC15. `the_one/agents.md` gains a "Per-agent MCP credentials (sortie 09)" block (validation rules and the 422 shape, blank values and `missing_values`, the evidence rule change, resolve-at-connect and the eviction hooks, the OAuth skip, the known effects from DD7) and updates "Agent override secrets storage" and the pool's "pinned to the first acquire" description. `SECURITY-MODEL.md` gains the "Per-agent MCP credentials" paragraph's first part (values stay in the encrypted column, masked with the existing 4-character tail rule, never logged, the value grammar keeps transport errors from echoing a value, OAuth Authorization stays the sign-in's). The flight log has the leg's entry.

**Gate**
- [ ] AC16. The **full** `THE_ONE_TEST_NETNS=1 make test-unit` passes (expected skip count per CLAUDE.md; the new 422 can reach any test that PUTs overrides, for example `test_self_configuration_*`, `test_override_cleanup`, `test_rename_carries`, `test_factory`), and the `mcp` and `mcp-connection` browser lanes pass through `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1` (or one failure that passes isolated and is logged). `ruff check` and `ruff format --check` are clean on the touched paths.

## Verification Steps
- AC1-AC3: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_mcp_agent_credentials.py -x --timeout 30` (or the chosen file names), plus `tests/test_db_api.py` and `tests/test_agent_tool_overrides_round_trip.py` unchanged-green.
- AC4-AC8: the new tests plus `tests/test_mcp_signin_detection.py`, `tests/test_oauth_test_connection_endpoint.py`, `tests/test_mcp_stdio_test_connect.py`, `tests/test_mcp_client.py` and every `tests/test_mcp_*` file unchanged-green.
- AC9-AC12: the new pool tests plus `tests/test_mcp_pool.py`, `tests/test_mcp_tool_provider.py`, `tests/test_factory.py`.
- AC13: the fixture's own smoke test (in-process and subprocess start/stop).
- AC14: the leak test.
- AC15: read the docs diff.
- AC16: `THE_ONE_TEST_NETNS=1 make test-unit`; `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane mcp`; same with `--lane mcp-connection`; `ruff check the_one/ tests/`; `ruff format --check the_one/ tests/`.

## Implementation Guidance

1. **Fixture first** (`tests/fixtures/mcp/key_server.py`). Model it on `tests/fixtures/mcp/rich_http_server.py` (subprocess, `PORT n`) and `tests/fixtures/mcp/asgi_401.py` (`Auth401Wrapper`, a bare 401 for chosen methods) and `hello_server.py` (`make_http_app()`). Wrap an MCP app with a header check that returns 401 with no resource metadata. Filter `tools/list` per key (a low-level handler, or one server object per key behind a dispatcher). Record `{seq, method, key_tail}` per JSON-RPC request in memory; serve it on a non-MCP control route.
2. **Overlay, OAuth skip, blank drop, `missing_values`** (`_overrides.py`, `_tool_provider.py::_apply_override`, `streamable_http.py::build_request_headers`, `stdio.py::build_stdio_environ`). A small shared predicate for "source has OAuth state" (`any(k in source.secrets for k in OAUTH_MANAGED_SECRET_KEYS)`) used by `_apply_override` and the validator. Keep `_apply_override` returning the source unchanged when there is nothing to apply.
3. **Validation** (`mcp/override_validation.py`). Mirror `tools/override_validation.py`'s `_detail`. Inputs: the raw `mcp_overrides` dict and `{name: MCPSource}`. Call it from `create_agent` (~1235) and `update_agent` (~1288) at the point named in AC1, raising `HTTPException(422, detail=details)` like `_validate_tool_overrides` (~290-301).
4. **Classification** (`client.py::_signin_signal`). Replace the `if build_request_headers(self.source):` evidence with "the source configures any non-OAuth header name" (a helper beside `missing_values`). Build the message from `missing_values` when non-empty. Check `MCPCredentialsRejected`'s constructor (`mcp/errors.py`) for how to carry the names; extend it compatibly.
5. **Helper switches and the Library missing-values path** (`api.py::_build_and_test_no_auth_mcp` ~3748, `_build_and_test_stdio_mcp` ~3860, `_test_mcp_connection_inner` ~4023). Add `cache_write` (default `"shared"`) and `classify` (default `False`); existing call sites pass neither (AC8), and only the new missing-values branch passes them. In `_test_mcp_connection_inner`, compute `missing_values(stored_or_overridden_source, same)` after the body override is applied; branch as AC7 says, reusing the existing `from_fallthrough` / `_SIGNIN_REQUIRED` path into Phase B. Do not restructure the phases beyond this (the Phase A extraction is leg 2).
6. **Resolve at connect** (`_pool.py::acquire` ~466, `_entry_worker` ~160-250; `_tool.py::execute` ~174; `_tool_provider.py`). Thread `resolve_source` into the worker. In the worker: `try:` resolver (if any, else the given source) → posture check → OAuth provider → `MCPClient(...)` → `connect()`; the `except BaseException` that sets `entry.failure` and `client_ready` covers all of it. Keep connect and disconnect on the worker task. Note that `acquire` today loads `_load_source` before the lock only when no `source_override` is given; keep that path for callers that pass neither.
7. **Eviction hooks** (`api.py`): compute per-source credential diffs in `update_agent` from the stored agent (`existing`, decrypted by `store.load`) and the final `cfg`, both available right after `store.save` (~1368); map source names to ids with `mcp_repo.list()` only when either side has a credential key, skipping surface rows; evict after `store.save`. In `update_mcp_source`, compare right after `await repo.update(updated)` (~3499), where secrets are already mask-resolved; a rename-only PUT evicts nothing (the pool key is the source id). `create_agent` has no stored state: evict `(name, sid)` for each source carrying a credential (harmless; covers a re-created name with a stale pool entry). Add `_evict_all_for_agent(name)` to `_pool.py` next to `_evict_all_for_source` (~311), same shape. Hook `rename_agent` (~1393) and `delete_agent` (~1378) after their writes. In `update_mcp_source` (~3387), compare the stored and new `type`, `config` minus `_cache`, and `secrets` (after mask resolution) and evict when any differs.
8. **Tests**, per AC, with falsification where AC12 asks for it (remove the fix by editing, run, restore by editing; never a backup copy).
9. **Docs** (AC15), then the gate (AC16). Run the long gates in the background and wait for their notification.

## Edge Cases
- **An override for a source the agent does not attach**: validated like any other (the source exists by name); the build ignores it as today.
- **`bearer_token` and an `Authorization` header in one entry**: both validated; `bearer_token` still wins at overlay (applied after `headers`).
- **The self-configuration row**: `_normalize_surface_fields` already 422s a non-empty `mcp_overrides["self-configuration"]` before validation; the resolver goes through `override_for`, which returns `None` for a surface row.
- **A Library source with a blank value and no agent overrides at all**: its builds and tool calls send no value for that name; a bare 401 is `MCPCredentialsRejected` naming it.
- **A stdio source whose blank value is an allowlisted host variable**: the host value goes through (intended, DD3).
- **An agent not in the store** (CLI `the-one chat`, tests with injected configs): the resolver returns the build-time source, so behaviour is unchanged for them.
- **Eviction while a call is in flight**: the call may fail with a connection error (known effect); do not add retries.
- **`update_mcp_source` with only `_cache` differences or an unchanged masked secret**: no eviction.

## Files Affected
- `the_one/mcp/override_validation.py` - new: `validate_mcp_overrides`
- `the_one/mcp/_overrides.py` - `missing_values`, the OAuth-state predicate, the configured-names helper
- `the_one/mcp/_tool_provider.py` - `_apply_override` overlay and OAuth skip; the resolver
- `the_one/mcp/_tool.py` - `execute` passes the resolver
- `the_one/mcp/_pool.py` - `acquire(resolve_source=...)`, worker `try` widening, `_evict_all_for_agent`
- `the_one/mcp/client.py` - `_signin_signal` evidence rule and message
- `the_one/mcp/errors.py` - `MCPCredentialsRejected` carries missing names (if needed)
- `the_one/mcp/transports/streamable_http.py`, `the_one/mcp/transports/stdio.py` - blank drop
- `the_one/interfaces/web/api.py` - validation calls, eviction hooks, helper switches, the Library missing-values path
- `tests/fixtures/mcp/key_server.py` - new
- `tests/test_*.py` - new and updated unit tests
- `tests/behavior/per-agent-mcp-credentials.md` - fixture flags and tool arguments filled in
- `the_one/agents.md`, `SECURITY-MODEL.md` - docs

## Citation Audit
Checked against the working tree at `2958510f` during flight design and leg design (2026-11-03):
- `the_one/mcp/_pool.py::_entry_worker` - OAuth provider built before the `try` (~207-224); the `try` covers only `MCPClient(...)` and `connect()`; disconnect in the same task - verified
- `the_one/mcp/_pool.py::acquire` (466) - `source = source_override if ... else await _load_source(source_id)` before the lock; key `(agent_name, source_id)` - verified
- `the_one/mcp/_tool.py::MCPClientTool.execute` (~172-185) - passes `source_override=self._effective_source`; catches `SandboxError`, `MCPConnectionError`, `MCPVersionMismatch` and returns `[error] MCP source ... unavailable: ...` - verified
- `the_one/mcp/client.py::_signin_signal` (381-405) - evidence is `build_request_headers(self.source)` non-empty - verified
- `the_one/mcp/transports/stdio.py::build_stdio_environ` (368-394) - `{**allowlist_env, **config_env, **source.secrets}` - verified
- `the_one/mcp/transports/streamable_http.py::build_request_headers` (157-190) - `{**config_headers, **operator_secrets}`, values stripped, blanks kept - verified
- `the_one/interfaces/web/api.py` - `create_agent` 1235, `update_agent` 1288, `delete_agent` 1378, `rename_agent` 1393, `update_mcp_source` 3387, `reset_mcp_connection` 3670, `_build_and_test_no_auth_mcp` 3748, `_build_and_test_stdio_mcp` 3860, `_test_mcp_connection_inner` 4023, `_normalize_surface_fields` 312, `_merge_preserved_mcp_credentials` 366 - verified (line numbers)
- `the_one/tools/override_validation.py::_detail` (115-117) - the 422 detail shape - verified (flight design)
- `tests/fixtures/mcp/asgi_401.py::Auth401Wrapper`, `rich_http_server.py`, `hello_server.py::make_http_app` - exist - verified (flight design)
