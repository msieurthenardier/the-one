# Leg: mcp-connector-routers

**Status**: completed
**Flight**: [Backend boundaries before connectors](../flight.md)

## Objective
Move the MCP-source routes and the connector routes out of `the_one/interfaces/web/api.py` into three router modules. No path, method, dependency, status code or response shape changes.

## Context
- **Why this group first.** This is the flight design decision "Routers, not a rewrite", under its sequencing with Sortie 20: the group goes first because Sortie 20 does not touch it.
- **Existing pattern.** The four routers in `routines_api.py`, `secrets_api.py`, `gleepglorp_proposals_api.py` and `gleepglorp_fills_api.py` each define `router = APIRouter()`, and `api.py` includes them at the end (`api.py:6510-6529`).
- **The `_api` proxy.** Those routers reach every name that a test patches on `the_one.interfaces.web.api` through an `_ApiModule` proxy (`_api.<name>`, looked up at call time). A `patch("the_one.interfaces.web.api.X")` therefore still applies to the moved code. Mixing this with direct imports is the silent-no-op risk this leg must avoid.
- **The real sizes** (design review, at `7518aefa`):
  - **MCP section:** `api.py` about 3072-4148, roughly 1,080 lines and not contiguous. It holds the routes (3072-3140, 3266, 3625, 3634) and the connection-test machinery around them:
    - `_SIGNIN_REQUIRED` (3313), `_persist_oauth_posture`, `_clear_auth_posture`, `_CredentialsRejectedSignal`;
    - `_build_and_test_no_auth_mcp` (3348), `_protocol_fallback_of`, `_build_and_test_stdio_mcp` (3479);
    - `_clear_stale_oauth_secrets`, `_RECORDED_CHECK_STATUSES`, `_connect_with_tokens` (3660), `_test_mcp_connection_inner` (3753);
    - `_mcp_source_response` (3033).

    `delete_mcp_source` alone is about 135 lines.
  - **Connector section:** about 4149-4494, roughly 350 lines.
- **Shared helpers that stay in `api.py`** and are reached through `_api`: `_mcp_repo` (used by about 587 lines elsewhere), `_mcp_write_deps`, `_mcp_write_errors` and `_connector_repo`.
- **Outside importers of names this leg may move:**
  - `the_one/interfaces/web/mcp_agent_test.py` calls `_api._build_and_test_stdio_mcp`, `_connect_with_tokens`, `_build_and_test_no_auth_mcp` and `_SIGNIN_REQUIRED`.
  - `tests/test_connector_stale_save.py:15` imports `_connector_repo` and `_merge_paired_peers` from `api`.
- **Routes that stay in `api.py`** (explicit, so they are not dragged along):
  - `/agents/{name}/mcp-overrides/{source_id}/credentials`;
  - the OAuth routes (`/oauth/callback`, `/oauth/start`, `/providers/{id}/oauth*`);
  - the test seams `/_test/stub/inbound`, `/_test/stub/outbound` and `/_test/discord/sever` (about 4495-4570).
- **No other routes exist** under `/mcp-sources` or `/connectors`. The design review searched for connector directory and discoverable-refresh routes and found none.

## Inputs
- `main` at `7518aefa`.
- The existing router modules as templates. Use `routines_api.py`'s `_ApiModule` proxy pattern.

## Outputs
Three router modules, each `router = APIRouter()`, each under 800 lines, with no top-level `from the_one.interfaces.web.api import`. They reach `api.py` names through the `_api` proxy.
- **`mcp_sources_api.py`** (about 240 lines): MCP CRUD. That is `GET/POST /mcp-sources`, `GET /mcp-sources/types` and `GET/PUT/DELETE /mcp-sources/{source_id}`, plus `_mcp_source_response`. Only the CRUD routes call it.
- **`mcp_connection_api.py`:** the three connection routes and the builders. The routes are `DELETE /mcp-sources/{source_id}/connection` (`reset_mcp_connection`), `POST /mcp-sources/{source_id}/test/agent` and `POST /mcp-sources/{source_id}/test/connect`. It also holds:
  - `_build_and_test_no_auth_mcp`, `_build_and_test_stdio_mcp` and `_protocol_fallback_of`;
  - `_SIGNIN_REQUIRED`, defined exactly once, because `mcp_agent_test.py` compares by identity (`is`);
  - the posture and credential helpers: `_persist_oauth_posture`, `_clear_auth_posture`, `_CredentialsRejectedSignal` and `_clear_stale_oauth_secrets`;
  - `_RECORDED_CHECK_STATUSES`.
- **`mcp_connection_flow.py`** (a plain module, not a router; about 490 lines): `_connect_with_tokens` and `_test_mcp_connection_inner` (`api.py` about 3660-4148).
  - This split is planned up front. Kept whole, the connection group would be about 900 lines, over the 800-line cap.
  - `mcp_connection_api` imports from it. Whichever module holds a shared helper defines it once, and the other imports it, with no cycle.
  - Move another helper here if `wc -l` shows `mcp_connection_api.py` still over 800.
- **`connectors_api.py`:** the 8 connector routes, plus connector-only helpers such as `_merge_paired_peers`.

`api.py` includes the three routers in the existing block, in the order MCP sources, MCP connection, connectors, each with a one-line comment.

## Acceptance Criteria
- [ ] **AC1, no behaviour change.** Take two in-process dumps, before any edit and after the move, using a read-only scratchpad script.
  - (a) `app.openapi()`.
  - (b) For every route in the real app's `app.routes`, in order, record:
    - path and methods;
    - name;
    - endpoint `__module__.__qualname__`;
    - `status_code`;
    - the dependant's dependency callables;
    - the `response_model`.
  - Compare the dumps:
    - (a) shows no difference except key order;
    - in (b), routes that did not move are identical and in the same order;
    - in (b), moved routes are identical as a set, except their endpoint module;
    - in (b), the relative order within each prefix is unchanged.

  Both dumps and the comparison are recorded in the flight log. 4xx behaviour is covered by the existing tests (AC4 and AC5).
- [ ] **AC2, route order.**
  - Moved routes now sit after every route declared in `api.py`. Confirm that no route left in `api.py` or in another router matches a moved path, and say so in the flight log.
  - Within each prefix, keep the declaration order: `/mcp-sources/types` before `/mcp-sources/{source_id}`, and `/connectors/types` before `/connectors/{connector_id}`.
- [ ] **AC3, the patch rule.**
  - Moved code reaches `get_connection`, `get_encryptor`, `httpx`, `httpx2`, `_mcp_repo`, `_mcp_write_deps`, `_mcp_write_errors`, `_connector_repo` and every other name a test patches on `api`, only through `_api`.
  - A grep check, recorded in the flight log, shows no moved module has a top-level import of those names.
  - Tests that patch these names on `api` need no change.
  - Tests that import, patch or call a name that actually moved are repointed to the defining module. Known cases:
    - `_merge_paired_peers` in `tests/test_connector_stale_save.py:15`;
    - `api_mod._persist_oauth_posture` (lines 312, 359), `api_mod._clear_auth_posture` (363) and `api_mod._build_and_test_stdio_mcp` (506) in `tests/test_mcp_last_check.py`.
  - No test is skipped, xfailed or deleted.
- [ ] **AC4, outside importers.**
  - `mcp_agent_test.py` imports the moved connection helpers from `mcp_connection_api.py` (canonical import).
  - Grep both `the_one/` and `tests/` for every moved name reached as `api.<name>` or `api_mod.<name>`. Repoint each one to the defining module, as AC3 says.
  - `api.py` keeps a re-export only where repointing is impossible. Record each such case and why.
  - `tests/test_api_name_rule.py` needs no change, because it iterates `api.router.routes`. It passes.
- [ ] **AC5, the unit tier.**
  - These pass: `THE_ONE_TEST_NETNS=1 make test-unit` with the same counts as `main`, together with `tests/test_seam_routes_403_sweep.py`, `tests/test_api_app_guard.py`, and the MCP and connector API tests.
  - The MCP and connector API tests include at least `test_mcp_test_connection_negotiation.py`, `test_mcp_last_check.py`, `test_mcp_agent_test_route.py`, `test_oauth_test_connection_endpoint.py`, `test_oauth_start_endpoint.py`, `test_connector_stale_save.py` and `test_mcp_cache_cleanup.py`; grep `tests/` for more.
  - Run the tier only when no other test process is on the host.
- [ ] **AC6, browser lanes.**
  - The lanes exercising MCP and connector pages pass: `mcp`, `mcp-connection` and any connector lane; check with `scripts/run-tests.sh --list`.
  - Use `TEST_TIMEOUT=3600` if the host is loaded, and record the load.
  - A failure that reproduces in isolation is investigated; a known load issue such as squawk 0428 is cited.
- [ ] **AC7, size and lint.**
  - `api.py` shrinks by about 1,400 lines.
  - Each new module is under 800 lines. If one is not, split it further and record how.
  - `ruff check` and `ruff format --check` are clean.
- [ ] **AC8, docs.**
  - The module map in `the_one/agents.md` lists the three new modules and the `_api` proxy rule they follow.
  - Any `agents.md` or `CLAUDE.md` text saying these routes live in `api.py` is updated.

## Verification Steps
- **AC1, AC2, AC3:** the dumps, the comparison, the order note and the grep in the flight log.
- **AC4:** the importer grep and the name-rule test output.
- **AC5, AC6:** test outputs with load.
- **AC7:** `wc -l` and ruff.
- **AC8:** the doc diff.

## Implementation Guidance
1. **The rule before any move.** Read `routines_api.py`'s `_ApiModule` proxy. Every name that tests patch on `api`, and every shared helper that stays in `api.py`, is reached as `_api.<name>`. Only group-only code moves.
2. **Take the before dumps** (AC1 a and b).
3. **Build the dependency map.** For each route and helper in the two sections, list the names it uses and its callers across `the_one/` and `tests/`. Classify each name:
   - moves with its group;
   - stays, reached through `_api`;
   - outside importer, to repoint.

   Record the map in the flight log.
4. **Create `mcp_connection_api.py` first,** because `mcp_agent_test.py` depends on its helpers. Then `mcp_sources_api.py`, then `connectors_api.py`. Move code verbatim, in its original relative order, changing only how names are reached.
5. **Include the three routers** at the end of `api.py`, in the existing block.
6. **Repoint the outside importers** (`mcp_agent_test.py`, `test_connector_stale_save.py`) and any tests that patch a moved name.
7. **Take the after dumps and compare** (AC1, AC2). Run the grep (AC3).
8. **Run the tests in this order:** the named API test files, then `make test-unit`, then the lanes.
9. **Update the docs.** Then write the "Leg 1" entry in the flight log, and `[LAND:leg]`.

## Edge Cases
- **Module-level state:** any lock, cache or manager getter must stay one instance. Reach it through `_api` instead of copying it.
- **Sortie 20:** do not touch agent routes, `delete_agent` or `app.py`.
- **`app.py`** imports only `read_execution_sandbox` and `router` from `api`, so it needs no change.
- **Credential gate:** it is middleware, so the routers need no per-router dependency, the same as the existing routers.

## Files Affected
- `the_one/interfaces/web/api.py`
- new `the_one/interfaces/web/mcp_sources_api.py`, `mcp_connection_api.py` and `connectors_api.py`
- `the_one/interfaces/web/mcp_agent_test.py`
- new `the_one/interfaces/web/mcp_connection_flow.py`
- `tests/test_connector_stale_save.py`, `tests/test_mcp_last_check.py`, and any other test that imports, patches or calls a moved name
- `the_one/agents.md`

## Citation Audit
Verified by the design review at `7518aefa`:
- `api.py` route lines:
  - MCP: 3072, 3089, 3105, 3115, 3123, 3131, 3266, 3625, 3634;
  - connectors: 4205, 4211, 4220, 4230, 4306, 4385, 4408, 4454.
- The MCP section runs about 3033-4148 and the connector section about 4149-4494.
- The test seams are at about 4495-4570.
- The `include_router` block is at 6510-6529.
- The `_ApiModule` proxy is in the existing routers.
- `mcp_agent_test.py` uses four `_api` connection helpers.
- `tests/test_connector_stale_save.py:15` imports `_connector_repo` and `_merge_paired_peers`.
- `tests/test_mcp_test_connection_negotiation.py` (lines 209, 258, 440, 473) and `tests/test_oauth_start_endpoint.py` (lines 142, 217) patch `api.httpx2`.
- `tests/test_api_name_rule.py` iterates `api.router.routes`.

**Design review 1 (Sonnet): approve with changes.** It raised:
- **2 high:**
  - the size estimate was inverted, so the MCP group is now split in two;
  - there was no patch-name policy, so the `_api` proxy is now mandated.
- **3 medium:**
  - the importers are now named;
  - AC1 is strengthened with a route-table dump;
  - AC2 is specified.
- **2 low:**
  - the test seams stay, and are named;
  - the `app.py` imports are recorded.

Its answers:
- the MCP group is split into two modules;
- `mcp_agent_test.py` is repointed to `mcp_connection_api.py`.

**Design review 2 (Sonnet): approve with changes.** Both highs are resolved, and the MCP boundary is clean: every caller in `api.py` was checked. The changes it asked for:
- `tests/test_mcp_last_check.py` is now named;
- the AC4 grep now covers `tests/`;
- the hedge on `_mcp_source_response` is removed;
- the connection module, about 900 lines whole, is pre-split into `mcp_connection_flow.py`;
- `_SIGNIN_REQUIRED` is defined once.

The leg is `ready`.
