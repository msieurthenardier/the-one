# Leg: 00-cleanup-batch

**Status**: completed
**Flight**: [Cleanup + connect-time 401 translation](../flight.md)

## Objective

Land the F6.5 debrief carry-forward maintenance items as a single batch: 3 unit tests covering F6.5 L4 inline fixes, the `App.areas` re-export that fixes Anomaly A2, the synthetic-csid pattern docstring, and an operator-facing entry for the Test connection button.

## Context

- Origin: F6.5 debrief recommendations 1–4 + flight `In-Flight::Technical Approach::L0` (six itemized deliverables).
- Each item is independent and ≤30 LOC; bundling reduces orchestration cost (per flight Design Decision §1).
- F6.5 L4 introduced three production fixes that landed without unit tests; HAT verified them empirically against live Cloudflare, but the test suite has no reproducible coverage. L0 closes that gap.
- F6.5 L1 reverted an `App.areas` export as scope-creep without realizing JS test helpers consumed it (Anomaly A2). Re-adding the export is the surgical fix per flight Open Question resolution.
- The synthetic-csid pattern (`test:*`, `agent_build:*`, real csid) is now used in three production sites (`api.py` Test endpoint, `_pool.py::_entry_worker`, redirect_handler closure). Documenting it once at `handlers.py`'s module docstring centralizes the contract.

## Inputs

What exists before this leg runs:

- `the_one/mcp/oauth/provider_factory.py:57 (in build_oauth_provider_for_source) — "allow_dcr_bootstrap: bool = False,"` — F6.5 L3's bootstrap factory path is in production but has no dedicated test (existing tests in `test_oauth_provider_factory.py` cover the `dcr_credentials`-present and `chat_session_id is None` paths only).
- `the_one/mcp/transports/streamable_http.py:60 (in build_request_headers) — "config_headers: dict[str, str] = source.config.get("headers", {})"` — the helper exists; the `OAUTH_MANAGED_SECRET_KEYS`-filter on line 81 was expanded in F6.5 L4 to include `token_type` and `scope` but has no parametrized test pinning all six keys.
- `the_one/mcp/oauth/storage.py:51 — "OAUTH_MANAGED_SECRET_KEYS: frozenset[str] = frozenset({"` — six keys: `access_token`, `refresh_token`, `token_expires_at`, `token_type`, `scope`, `dcr_credentials`.
- `the_one/mcp/_pool.py:148 (in _entry_worker) — "async def _entry_worker(source: MCPSource, entry: _RegistryEntry) -> None:"` — the synthetic-csid bootstrap path lives at lines 197–200 (`csid = current_chat_session_id.get(None)` → `if csid is None and source.secrets.get("access_token"): csid = f"agent_build:{source.id}"`). Test file `tests/test_mcp_pool.py` exists but has no test for this branch.
- `the_one/interfaces/web/static/js/app.js:2 — "var areas = {};"` (closure-private, dict keyed by descriptor.id). `the_one/interfaces/web/static/js/app.js:3 — "var order = [];"` (closure-private, array of descriptors sorted by `order` field).
- `the_one/interfaces/web/static/js/app.js:267 (in IIFE) — "Object.assign(window.App, {"` — currently exposes `registerArea`, `router`, `escapeHtml`, `escapeAttr`, `formatBytes`, `showFlash`. NO `areas` export.
- `tests/browser/test_oauth_modal_flow.py:31-51 (in _emit_ws_event) — "window.App.areas.find(a => a.id === 'chat')"` — this consumer expects `Array.prototype.find` semantics on `window.App.areas` (i.e., `App.areas` must iterate as an array of descriptors, not a dict).
- `tests/browser/test_flow_studio_mcp_navigation.py:16 — "Note: App.areas is closure-private in app.js, so tests use BEHAVIORAL DOM"` — confirms the export is currently absent.
- `the_one/mcp/oauth/handlers.py:1-26` — module docstring exists, no synthetic-csid coverage yet.
- `CLAUDE.md` — project docs file (no `README.md` at repo root). Lines 298–334 cover MCP storage / sandbox contracts but have no operator-facing Test-connection-button section.
- Branch `flight/6_6-cleanup-and-connect-401` already exists, working tree clean (per Flight Director state-load 2026-05-09).

## Outputs

What exists after this leg completes:

- `tests/test_oauth_provider_factory.py` — new test `test_factory_with_allow_dcr_bootstrap_constructs_provider_for_unregistered_source` covering the F6.5 L3 bootstrap path (returns non-None `OAuthClientProvider` when `dcr_credentials` absent AND `allow_dcr_bootstrap=True` AND `chat_session_id` is set to a synthetic value).
- `tests/test_streamable_http_transport.py` — **NEW** test file (verified absent at design-review time via `ls tests/ | grep streamable_http` returning no matches and `grep -rln "build_request_headers" tests/` returning zero hits). Parametrized over the 6 `OAUTH_MANAGED_SECRET_KEYS` values; asserts `build_request_headers(source)` does not contain any of them in its output. Each parametrization uses the correct value type per F6.5 L4's typing fix (string for tokens, float for `token_expires_at`, dict for `dcr_credentials`).
- `tests/test_mcp_pool.py` — new test `test_entry_worker_uses_synthetic_csid_when_tokens_present` covering the F6.5 L4 fix at `_pool.py:197-200`. Mocks `current_chat_session_id.get(None)` → None; seeds `source.secrets["access_token"]`; asserts `build_oauth_provider_for_source` is invoked with csid `f"agent_build:{source.id}"` and the resulting provider is non-None.
- `the_one/interfaces/web/static/js/app.js` — `Object.assign(window.App, {…})` block at line 267 grows by one entry exporting the area registry under `App.areas` so `window.App.areas.find(a => a.id === 'chat')` works (see Edge Cases for the dict-vs-array discrepancy).
- `the_one/mcp/oauth/handlers.py` — module docstring extended with one paragraph naming the three known csid shapes, the prefix-uniqueness invariant, and the no-op-on-synthetic-csid contract.
- `CLAUDE.md` (or another operator-facing doc the implementer locates first) — one paragraph describing the Test connection button at the source-creation surface.
- All four currently-failing `test_oauth_modal_flow.py` browser tests transition from FAIL → PASS as a side effect of the export.
- Flight log updated; flight checklist `Checkpoints::L0 landing` checked off.

## Acceptance Criteria

- [x] `tests/test_oauth_provider_factory.py::test_factory_with_allow_dcr_bootstrap_constructs_provider_for_unregistered_source` exists and passes. Asserts: (a) `result is not None`; (b) `isinstance(result, OAuthClientProvider)`; (c) the path is reached only when `allow_dcr_bootstrap=True` AND `chat_session_id` is non-None AND `dcr_credentials` is absent.
- [x] A parametrized test in `tests/test_streamable_http_transport.py` (or equivalent) iterates over all 6 keys in `OAUTH_MANAGED_SECRET_KEYS` (`access_token`, `refresh_token`, `token_expires_at`, `token_type`, `scope`, `dcr_credentials`) — for each key, seed `source.secrets[key]` with an appropriately-typed value, call `build_request_headers(source)`, assert `key not in result`. The test must mechanically read `OAUTH_MANAGED_SECRET_KEYS` (not hardcode the list) so future expansions are caught.
- [x] `tests/test_mcp_pool.py::test_entry_worker_uses_synthetic_csid_when_tokens_present` exists and passes. Verifies the F6.5 L4 fix at `_pool.py:197-200`: csid bootstrapped to `f"agent_build:{source.id}"` when `current_chat_session_id.get(None)` is None AND `source.secrets["access_token"]` is set; the build_oauth_provider_for_source call receives this synthetic csid and returns a non-None provider.
- [x] `the_one/interfaces/web/static/js/app.js` exports the area registry under `App.areas` such that `window.App.areas.find(a => a.id === 'chat')` (Array.prototype.find semantics) returns the chat area descriptor when called from a browser context. See Edge Cases for the dict-vs-array implementation choice.
- [x] All 4 currently-failing browser tests in `tests/browser/test_oauth_modal_flow.py` (`test_login_button_renders_on_auth_required_event`, `test_modal_opens_on_button_click`, `test_modal_closes_on_auth_resolved_event` (line 100), `test_button_clears_on_auth_resolved_event` (line 114)) transition from FAIL → PASS. Verify the count of passing tests in this file before vs after.
- [x] `the_one/mcp/oauth/handlers.py`'s module docstring contains one paragraph (≤8 lines) that names: (a) the three known csid shapes — `test:{source_id}` (allocated by the F6.5 Test connection endpoint at `the_one/interfaces/web/api.py:~867,~912`), `agent_build:{source.id}` (allocated by `_pool._entry_worker` at `the_one/mcp/_pool.py:200`), and real 12-char uuid4-hex csids (allocated per chat WebSocket connection in `the_one/interfaces/web/app.py`); (b) the **collision-free invariant** — real csids are 12-char lowercase hex (charset `[0-9a-f]`), synthetic csids contain a literal `:` separator that the hex charset cannot produce, so the two namespaces are disjoint by character-set construction (NOT by length); (c) the no-op-broadcast-on-synthetic-csid contract — `_sessions.get(synthetic_csid)` returns None for both synthetic prefixes, so the `_send_to_session` broadcast is a guarded no-op.
- [x] An operator-facing doc (the implementer first runs `grep -rn -i "MCP Sources\|Test connection" CLAUDE.md docs/` and inserts into the closest fit; if no fit exists, append a new short subsection to `CLAUDE.md` under a heading describing operator workflows) contains a paragraph (≤6 lines) describing the Test connection button: where it is (Studio → MCP Sources → source-edit page), what it does (verifies the connection lifecycle and lists the server's tools; for OAuth-protected servers, drives the OAuth consent flow at source-creation time), and the side effect (subsequent agent builds register real tools using the persisted tokens).
- [x] Existing tests in `tests/test_oauth_provider_factory.py`, `tests/test_mcp_pool.py`, and any pre-existing `tests/test_streamable_http_transport.py` pass UNMODIFIED — no signature changes, no inversions of existing assertions.
- [x] After the export lands, `App.areas` is referenced at exactly two known sites: the new export inside `app.js`'s `Object.assign(window.App, {…})` block at line ~267, AND the pre-existing consumer in `tests/browser/test_oauth_modal_flow.py:42`. Other consumers may be present (or land in future work); the AC pins the two known sites only.

## Verification Steps

How to confirm each criterion:

- **Test 1** (`test_factory_with_allow_dcr_bootstrap_constructs_provider_for_unregistered_source`): `docker compose exec the-one pytest tests/test_oauth_provider_factory.py::test_factory_with_allow_dcr_bootstrap_constructs_provider_for_unregistered_source -v`
- **Test 2** (parametrized `OAUTH_MANAGED_SECRET_KEYS` filter): `docker compose exec the-one pytest tests/test_streamable_http_transport.py::test_build_request_headers_filters_oauth_managed_keys -v` (or whatever the implementer named it). Pytest output should show one PASSED line per of the 6 keys.
- **Test 3** (`test_entry_worker_uses_synthetic_csid_when_tokens_present`): `docker compose exec the-one pytest tests/test_mcp_pool.py::test_entry_worker_uses_synthetic_csid_when_tokens_present -v --timeout 30`. The `--timeout` is required because flight Open Questions waiver excludes `tests/test_mcp_pool.py` from the full-suite run; run this single test directly without `--ignore` to verify.
- **App.areas export**: `grep -n "App.areas\|window.App.areas" the_one/interfaces/web/static/js/` should show the new export site PLUS the existing consumer reference in `test_oauth_modal_flow.py`. Then `docker compose exec the-one pytest tests/browser/test_oauth_modal_flow.py -v` should show 4 newly-passing tests (the implementer should record the pre-state count first, then verify the post-state count).
- **handlers.py docstring**: `head -50 the_one/mcp/oauth/handlers.py` should show the new paragraph. Manual read confirms all three required elements are present (3 csid shapes + uniqueness invariant + no-op contract).
- **Operator-facing docs**: `grep -n -i "Test connection" CLAUDE.md docs/` should return at least one match in the doc the implementer chose; manual read confirms the paragraph names location, behaviour, and side effect.
- **Pre-existing test stability**: `docker compose exec the-one pytest --ignore=tests/test_mcp_pool.py -q` — full suite passes (modulo the 3 pre-existing `test_mcp_sandbox_integration.py` bwrap failures noted in flight's Checkpoints).

## Implementation Guidance

1. **Order**: Items 1, 2, 3 (the 3 unit tests) are independent; items 4 (export), 5 (docstring), 6 (operator-facing docs) are also independent. Do them in any order; recommend the test items first to surface any spec-vs-code-state drift early.

2. **Test 1 — `test_factory_with_allow_dcr_bootstrap_constructs_provider_for_unregistered_source`** — add to `tests/test_oauth_provider_factory.py`. Use the existing `repo_with_source` fixture. The source has `secrets={}` already (no `dcr_credentials`). Call `build_oauth_provider_for_source(source, repo, "test:src-factory-1", allow_dcr_bootstrap=True)`. Assert non-None and `isinstance(result, OAuthClientProvider)`. Also assert the negative control: same call without `allow_dcr_bootstrap=True` returns None (this duplicates one assertion from `test_factory_returns_none_when_dcr_credentials_absent` but documents the boundary in one test).

3. **Test 2 — parametrized header filter** — create `tests/test_streamable_http_transport.py` as a NEW pytest module (verified absent at design-review time). Minimal module that imports `build_request_headers` from `the_one.mcp.transports.streamable_http`, `OAUTH_MANAGED_SECRET_KEYS` from `the_one.mcp.oauth.storage`, and `MCPSource` from `the_one.db.models`.
   - Test shape:
     ```python
     @pytest.mark.parametrize("key, value", [
         ("access_token", "ya29.test-access"),
         ("refresh_token", "1//0g.test-refresh"),
         ("token_expires_at", 1234567890.0),
         ("token_type", "Bearer"),
         ("scope", "openid profile"),
         ("dcr_credentials", {"client_id": "test", "issuer": "https://example.com"}),
     ])
     def test_build_request_headers_filters_oauth_managed_keys(key, value):
         source = MCPSource(id="src-1", name="t", type="streamable-http",
                            config={"url": "https://example.com/mcp"},
                            secrets={key: value})
         headers = build_request_headers(source)
         assert key not in headers
     ```
   - The mechanical-iteration variant (preferred): `for key in OAUTH_MANAGED_SECRET_KEYS: …` inside one test. Either shape is fine; the parametrized variant gives clearer pytest output per-key. Pick one.
   - **Important**: the test must construct an `MCPSource` with the secrets in plaintext form — the encryption boundary is the repository, not the model. `build_request_headers` reads `source.secrets` directly.

4. **Test 3 — `test_entry_worker_uses_synthetic_csid_when_tokens_present`** — add to `tests/test_mcp_pool.py`. The challenge: `_entry_worker` is an async function that runs `MCPClient.connect()` against a real source. The simplest unit-test shape is a single mock that captures the factory's call args and then raises to stop the worker before the real `MCPClient.connect()` ever runs:
   - **Mock target**: `monkeypatch.setattr("the_one.mcp.oauth.build_oauth_provider_for_source", mock_provider_factory)`. Rationale: the import at `_pool.py:196` (`from the_one.mcp.oauth import build_oauth_provider_for_source`) inside the async function body re-resolves the name from the source module on each call, so patching `the_one.mcp.oauth.build_oauth_provider_for_source` is the right target. Patching `the_one.mcp._pool.build_oauth_provider_for_source` would FAIL with `AttributeError` because no module-level binding exists at that path.
   - **One-mock-stops-worker pattern**: configure the mock with `mock_provider_factory.side_effect = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("captured-and-stopped"))` — but record args first via `side_effect = capture_then_raise` where `capture_then_raise` saves `args, kwargs` to a closure-local list and then raises. Or simpler: use `unittest.mock.MagicMock(side_effect=RuntimeError("stop"))` and read `mock.call_args` AFTER `_entry_worker` returns (the mock records args even when side_effect raises). The `RuntimeError` from the factory propagates up to `_entry_worker`'s `except BaseException as exc:` branch (line 210), which sets `entry.failure = exc` and returns — no second mock needed for `MCPClient.connect`.
   - **MCPSource construction**: `MCPSource(id="src-pool-test", name="t", type="streamable-http", config={"url": "https://example.com/mcp"}, secrets={"access_token": "tok-1", "dcr_credentials": {"client_id": "c1"}})`.
   - **`_RegistryEntry` construction**: `_RegistryEntry(ttl_seconds=300, client_ready=asyncio.Event(), evict_event=asyncio.Event())` — `ttl_seconds` is the only required positional field per `_pool.py:92`; `worker` defaults to None and is not consulted by the early-return path the test exercises. `client_ready` and `evict_event` MUST be real `asyncio.Event()` instances because `_entry_worker` asserts both are non-None at lines 169–170.
   - **No explicit ContextVar manipulation needed**: `current_chat_session_id.get(None)` returns the fallback when unset, which is the test's desired state (no inherited csid). If a sibling test contaminates the ContextVar, isolate via `pytest.fixture(autouse=True)` that resets it.
   - **Assertion**: `mock_provider_factory.assert_called_once()` and `mock_provider_factory.call_args.args[2] == f"agent_build:{source.id}"` — third positional arg is `chat_session_id` per `provider_factory.py:60`. Then assert `entry.failure is not None` (the mock's `RuntimeError` propagated to `entry.failure`) and `entry.client_ready.is_set()` (worker reached its early-return path).

5. **Item 4 — `App.areas` export** — see Edge Cases below for the dict-vs-array decision. The change is one line inside the `Object.assign(window.App, {…})` block at `app.js:267`. Implementation:
   - **Try first** (per flight Open Question resolution): add `areas: areas,` to the block.
   - Run `docker compose exec the-one pytest tests/browser/test_oauth_modal_flow.py -v`.
   - **If 4 tests pass**: done.
   - **If tests fail with "areas.find is not a function" or similar** (the dict-vs-array discrepancy materializes): switch to `areas: order,` — exporting the array `order` under the name `areas`. Re-run; tests should pass. Document the deviation in the flight log under `## Deviations` with the explicit choice and rationale.

6. **Item 5 — synthetic-csid docstring** — extend `the_one/mcp/oauth/handlers.py`'s existing module docstring at lines 1–26 (do NOT create a new docstring; append a new paragraph inside the existing triple-quoted block). Suggested wording (implementer may rephrase to fit the project's tone):
   > **Synthetic chat-session-id pattern.** Three csid shapes pass through this module's `redirect_handler` closure: real csids (12-char uuid4 hex, allocated per chat WebSocket connection by `the_one.interfaces.web.app`), `f"test:{source_id}"` (allocated by the F6.5 Test connection endpoint at `the_one/interfaces/web/api.py:~867,~912` when no chat WS subscription exists), and `f"agent_build:{source.id}"` (allocated by `_pool._entry_worker` at `the_one/mcp/_pool.py:200` when an OAuth-token-bearing source is connected outside a chat path — REST/CLI/agent-build). The two namespaces are disjoint by **character-set construction**: real csids are 12-char lowercase hex (charset `[0-9a-f]`); synthetic csids contain a literal `:` separator that the hex charset cannot produce. Collision is impossible regardless of the synthetic-prefix length. The redirect_handler's `_sessions.get(synthetic_csid)` lookup returns None for both synthetic shapes, so the `auth_required` broadcast becomes a guarded no-op — appropriate, since neither path has a chat UI to surface a modal.

7. **Item 6 — operator-facing Test connection button doc** — first locate the doc:
   - Run `grep -rn -i "MCP Sources\|Test connection\|mcp.sources" CLAUDE.md docs/`.
   - If a section already names "MCP Sources" (operator-facing), insert the paragraph there.
   - If no fit exists, append a new short subsection to `CLAUDE.md` at the bottom of the operator-workflows area (find the closest existing operator-flow section with `grep -n "## " CLAUDE.md` to choose insertion point).
   - Suggested wording:
     > **Test connection button.** Each MCP source's Studio source-edit page exposes a Test connection button. Clicking it invokes `POST /api/mcp-sources/{id}/test/connect` against the live source: `MCPClient.connect()` runs the lifecycle handshake and `list_tools()` returns the server's tool catalogue. For OAuth-protected sources, the first click drives the spec-compliant DCR + auth-code flow in a popup — operator completes consent at the IDP, tokens persist encrypted, and the second click renders the tool list. Side effect: subsequent agent builds attached to the source see fresh tokens in `secrets["dcr_credentials"]` and register real tools, closing the auth-on-`tools/list` blocking gap.

8. **Run the full unit suite** once all six items land: `docker compose exec the-one pytest --ignore=tests/test_mcp_pool.py -q`. Confirm green (modulo 3 pre-existing `test_mcp_sandbox_integration.py` bwrap failures). Then run `tests/test_mcp_pool.py` directly: `docker compose exec the-one pytest tests/test_mcp_pool.py -v --timeout 30`.

9. **Update flight log** — append a `### L0 — cleanup-batch` entry under `## Leg Progress` with: completion timestamp, the six deliverable summaries, the pre/post test counts for `test_oauth_modal_flow.py`, and any deviation notes (especially if Item 4 deviated to `areas: order`). Do NOT commit; that is deferred to the post-review batch commit per skill protocol.

10. **Post-completion checklist**: update this leg's status to `landed` (NOT `completed` — that transition happens at the post-review commit step). Do NOT check off this leg in `flight.md` yet (also deferred to the commit step). Do NOT signal `[COMPLETE:leg]`. DO signal `[HANDOFF:review-needed]`.

## Edge Cases

- **`App.areas` dict-vs-array discrepancy** (Item 4): the local `areas` variable in `app.js` is a dict (`var areas = {};` at line 2); the local array of descriptors is `var order = [];` at line 3. The test helper at `test_oauth_modal_flow.py:42` calls `window.App.areas.find(a => a.id === 'chat')` — `.find()` is `Array.prototype`, NOT a method on plain objects. Two shapes:
  - **`areas: areas`** (dict export): `window.App.areas.find` is `undefined`; the test helper throws `TypeError: window.App.areas.find is not a function`; the 4 `test_oauth_modal_flow.py` tests stay red. **Mechanically predictable to fail.**
  - **`areas: order`** (array export under the name `areas`): `.find()` works; the 4 tests turn green. The local variable name is hidden inside the IIFE — only `App.areas` is visible to consumers.
  - Flight design (`flight.md::Design Review Cycle 1::LOW`) directed `areas: areas` after architect cycle 1; cycle-1 architect did not check the test helper's `.find()` method. The leg's primary path is therefore: TRY `areas: areas` to honor design intent, observe the predictable browser-test failure, then deviate to `areas: order` and document in `flight-log.md::Deviations` with the test output as evidence. The first attempt is a confirmation step (~30s of test runtime), not a discovery — the predicted failure justifies the deviation against design review's directive on observed test evidence rather than reviewer judgement at design time. If the implementer prefers, they MAY skip the failing first attempt and go directly to `areas: order` with a deviation note explaining the mechanical-predictability rationale; both paths land the same code.

- **`tests/test_mcp_pool.py` is excluded from the default pytest run** per flight `Post-Flight::Completion Checklist::Tests passing inside docker compose exec the-one pytest --ignore=tests/test_mcp_pool.py`. The new test in this file MUST be runnable directly via the `pytest tests/test_mcp_pool.py::test_entry_worker_uses_synthetic_csid_when_tokens_present` invocation in CI/local. If the test interacts badly with the file's pre-existing test-collection issues (whatever caused the `--ignore`), isolate the test using a marker (`@pytest.mark.parametrize` or a module-level skip-conditional) so it remains runnable.

- **No `README.md` exists** at the repo root; `CLAUDE.md` is the project's primary doc file, plus `docs/kb-architecture.md`. The spec said "README.md (or wherever the project's user-facing docs live)" — the implementer's grep MUST run before insertion to avoid creating a redundant or contradictory section. If grep finds NO existing "MCP Sources" / "Test connection" section, prefer appending to `CLAUDE.md` at the bottom of the operator-flows area; the alternative (creating a new top-level `README.md`) introduces a new doc file the project may not want to maintain.

- **Test-3's `_entry_worker` mocking — `from … import …` re-resolution**: the `_entry_worker` function imports `build_oauth_provider_for_source` lazily inside its body (`_pool.py:196 — "from the_one.mcp.oauth import build_oauth_provider_for_source"`). Function-local `from … import …` statements re-execute on every function call, re-resolving the name from the source module each time. So `monkeypatch.setattr("the_one.mcp.oauth.build_oauth_provider_for_source", mock)` correctly intercepts the lookup at every `_entry_worker` invocation. The wrong target (`the_one.mcp._pool.build_oauth_provider_for_source`) does NOT exist as a module-level binding and would fail with `AttributeError`.

- **`_RegistryEntry` construction — `ttl_seconds` is required**: per `the_one/mcp/_pool.py:92`, `_RegistryEntry` has one required positional field (`ttl_seconds: int`) and five optional fields with defaults (`worker: asyncio.Task[None] | None = None`, `evict_event: asyncio.Event | None = None`, `client_ready: asyncio.Event | None = None`, `client: MCPClient | None = None`, `failure: BaseException | None = None`). The test MUST construct `_RegistryEntry(ttl_seconds=300, client_ready=asyncio.Event(), evict_event=asyncio.Event())` (any int for `ttl_seconds`; the early-return path doesn't read it) — `client_ready` and `evict_event` MUST be real `asyncio.Event()` instances per the asserts at `_pool.py:169-170`. `worker` defaults to None and is fine.

- **Operator-facing doc placement is non-load-bearing**: any reasonable insertion point inside `CLAUDE.md` (or any other doc) that contains the required information is acceptable per flight Adaptation Criteria's "L0's README entry placement: implementer's discretion."

## Files Affected

- `tests/test_oauth_provider_factory.py` — append one test (~25 LOC).
- `tests/test_streamable_http_transport.py` — new file OR append to existing (~20 LOC).
- `tests/test_mcp_pool.py` — append one test (~40 LOC, mocking-heavy).
- `the_one/interfaces/web/static/js/app.js` — one line added inside `Object.assign(window.App, {…})` at line 267 (PRIMARY attempt: `areas: areas,`; FALLBACK if browser tests reject: `areas: order,` — fallback documented as a deviation).
- `the_one/mcp/oauth/handlers.py` — module docstring extension (~6–8 lines added).
- `CLAUDE.md` (or located alternative) — one paragraph addition (~5–6 lines).
- `missions/07-mcp-integration/flights/06_6-cleanup-and-connect-401/flight-log.md` — append `### L0 — cleanup-batch` entry under `## Leg Progress`; if Item 4 deviated, append `### App.areas dict-vs-array deviation` under `## Deviations`.
- `missions/07-mcp-integration/flights/06_6-cleanup-and-connect-401/legs/00-cleanup-batch.md` — status transitions to `landed` (NOT `completed`).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]` (NOT `[COMPLETE:leg]` — F6.6 batches review and commit at flight close):**

- [x] All acceptance criteria verified (run each verification step; record output where the AC names a specific count)
- [x] Tests passing: full unit suite green via `docker compose exec the-one pytest --ignore=tests/test_mcp_pool.py -q`; the 3 new tests passing individually; the 4 `test_oauth_modal_flow.py` tests transitioned FAIL → PASS
- [x] Update `missions/07-mcp-integration/flights/06_6-cleanup-and-connect-401/flight-log.md` with an L0 progress entry under `## Leg Progress` (timestamps, deliverable summary, test counts, deviations if any)
- [x] Set this leg's status to `landed` (NOT `completed`) in the artifact header
- [x] Do NOT check off this leg in `flight.md` (deferred to post-review commit)
- [x] Do NOT update `flight.md` status to `landed` (deferred to post-flight close)
- [x] Do NOT commit (deferred to post-review batch commit)
- [x] Signal `[HANDOFF:review-needed]`

## Citation Audit

10 citations verified against current code at leg design time + design review cycle 1:

- `the_one/mcp/oauth/provider_factory.py:57` — verified `def build_oauth_provider_for_source(` at exact line; `chat_session_id` is the third positional param at line 60; `allow_dcr_bootstrap: bool = False,` at line 66 — OK.
- `the_one/mcp/transports/streamable_http.py:60` — verified `def build_request_headers(source: MCPSource) -> dict[str, str]:` at exact line; the `OAUTH_MANAGED_SECRET_KEYS` filter at line 81 — OK.
- `the_one/mcp/oauth/storage.py:51` — verified `OAUTH_MANAGED_SECRET_KEYS: frozenset[str] = frozenset(` at exact line; six-key membership confirmed against lines 53–58 — OK.
- `the_one/mcp/_pool.py:66-97` — verified `_RegistryEntry` dataclass shape; `ttl_seconds` is the only required positional field at line 92; other fields have defaults — OK (added during cycle-1 review).
- `the_one/mcp/_pool.py:148` — verified `async def _entry_worker(source: MCPSource, entry: _RegistryEntry) -> None:` at exact line; `assert entry.client_ready is not None` / `assert entry.evict_event is not None` at lines 169–170; lazy import at line 196; synthetic-csid bootstrap at lines 197–200; `except BaseException as exc:` branch at line 210 — OK.
- `the_one/interfaces/web/static/js/app.js:2-3` — verified `var areas = {};` at line 2 (dict, keyed by descriptor.id); `var order = [];` at line 3 (sorted array of descriptors); `Object.assign(window.App, {…})` block at line 267 — OK.
- `tests/browser/test_oauth_modal_flow.py:31-51` — verified `_emit_ws_event` helper definition; `window.App.areas.find(a => a.id === 'chat')` at line 42 (Array.prototype.find semantics, NOT compatible with the dict shape of `var areas = {}`); `test_modal_closes_on_auth_resolved_event` at line 100; `test_button_clears_on_auth_resolved_event` at line 114 — OK (test names added during cycle-1 review).
- `the_one/mcp/oauth/handlers.py:1-26` — verified module docstring; expansion target confirmed; `_sessions.get` lookup at line 106 — OK.
- `the_one/interfaces/web/api.py:~867,~912` — verified `f"test:{source_id}"` synthetic-csid sites in the F6.5 Test connection endpoint — OK (added during cycle-1 review for the docstring's three-shapes claim).
- `the_one/db/models.py:~50,~57` — verified `MCPSource` model class and `secrets` field as plaintext dict (encryption boundary is the repository, not the model) — supports the leg's claim in Implementation Guidance Item 3.

Flight-spec citation `flight.md::Design Review Cycle 1::LOW — "_pool._entry_worker is at line 210, not 198"` was a Design Review Cycle 1 correction referring to the `except BaseException` branch (which IS at line 210); the function definition is at line 148. Both citations are consistent with the design review's correction.
