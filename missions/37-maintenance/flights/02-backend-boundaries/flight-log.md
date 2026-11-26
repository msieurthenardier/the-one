# Flight Log: Backend boundaries before connectors

**Flight**: [Backend boundaries before connectors](flight.md)

## Summary

*(In flight.)*

---

## Leg Progress

### Leg 1: mcp-connector-routers (landed)

- **Dependency map summary.**
  - Moved with their group: every route and helper in the MCP and connector sections (17 routes).
  - Stay in `api.py`, reached as `_api.<name>`: `_mcp_repo`, `_mcp_write_deps`, `_mcp_write_errors`, `_connector_repo`, `_connector_directory_repo`, `_agent_store`, `_agent_revisions_repo`, `_drop_source_agent_tool_cache`, `_read_json`, `_reject_reserved_binding`, `_mask_secrets`, `_oauth_driver_headers`, `_TEST_CONNECT_TIMEOUT`, `get_encryptor`, `settings`, `httpx2`, `logger`. The logger stays `api`'s, so log records keep the name `the_one.interfaces.web.api`.
  - Library names imported directly in the moved modules (no test patches them on `api`): `mcp_service`, `self_configuration_manage`, `forget_era`, `missing_values`, `configured_names`, `_looks_masked`, `_validation_detail`, `get_connector_manager`, `connector_registry`, `DoctorReport`, `ConnectorClientError`, `PAIRING_TTL_SECONDS`, `Connector`, `MCPSource`, the OAuth-managed key set and the mask sentinel.
  - Outside importers: `mcp_agent_test.py` (4 helpers) and 6 test files (below).
  - Dropped from `api.py` as unused: `connector_registry`, `DoctorReport`, `PAIRING_TTL_SECONDS`, `Connector`, `MCPSource`, `forget_era`, `configured_names`, `missing_values`, `_MASKED_API_KEY_SENTINEL` and the `_OAUTH_MANAGED_SECRET_KEYS` import.
  - `api.py` keeps `_looks_masked` as a re-export, because tests and `mcp_agent_test.py` reach it as `api._looks_masked`.
- **Design choice to avoid a cycle.** `mcp_connection_flow.py` reaches the builders and `_SIGNIN_REQUIRED` as attributes of `mcp_connection_api` at call time, through a function-local import. `mcp_connection_api` imports the flow's `_test_mcp_connection_inner` at the top. A patch on `mcp_connection_api._build_and_test_*` therefore applies to the Library Test, and `_SIGNIN_REQUIRED` is defined once.
- **AC1 (before and after dumps, scratchpad `f2l1/`).**
  - `app.openapi()` is identical (sorted-key dumps), at 145 routes both before and after.
  - Route table (path, methods, name, endpoint qualname, status code, dependency callables, `response_model`):
    - the 128 unmoved routes are identical and in the same order, including endpoint module;
    - the 17 moved routes are identical as a set, and only the endpoint module differs;
    - relative order within `/api/mcp-sources` (9 routes) and `/api/connectors` (8) is unchanged.
  - A read-only AST check shows 32 moved functions or constants are verbatim, modulo the `_api.`, `_conn.` and `_flow.` prefixes. The one difference is `_test_mcp_connection_inner`, which gains the function-local `mcp_connection_api` import.
- **AC2 (route order).** The 17 moved routes sit at indices 128-144 of 145, after every route in `api.py` and the other routers. No unmoved route matches a moved path and method, checked by pattern-matching each moved path against every unmoved route. `/mcp-sources/types` stays before `/mcp-sources/{source_id}`, and `/connectors/types` before `/connectors/{connector_id}`.
- **AC3 (patch rule grep).**
  - Each moved module imports `api` only inside the `_ApiModule.__getattr__` proxy.
  - No top-level import of `get_connection`, `get_encryptor`, `httpx`, `httpx2`, `settings`, `logger`, `_mcp_repo`, `_mcp_write_deps`, `_mcp_write_errors`, `_connector_repo` or any other `api` name.
  - A grep for bare uses finds only comments and docstrings.
  - Tests that patch `api.httpx2`, `api.get_connection`, `api.get_encryptor` and so on needed no change.
- **AC4 (importer repoints).**
  - `mcp_agent_test.py` imports `mcp_connection_api` and `mcp_connection_flow` as modules and calls `_conn._build_and_test_*`, `_conn._SIGNIN_REQUIRED` and `_flow._connect_with_tokens`.
  - Tests repointed:
    - `test_connector_stale_save.py` (`_merge_paired_peers` from `connectors_api`).
    - `test_mcp_last_check.py` (module alias `conn_mod`, for `_test_mcp_connection_inner`, `_persist_oauth_posture`, `_clear_auth_posture` and `_build_and_test_stdio_mcp`).
    - `test_mcp_library_test_missing_values.py` (patches and calls of the builders and `_SIGNIN_REQUIRED`; `api_mod.httpx2` kept).
    - `test_mcp_test_connection_negotiation.py:380`.
    - `test_mcp_agent_test_route.py` (`_spy`, the stdio patch, and the `_connect_with_tokens` patches on `mcp_connection_flow`).
    - `test_mcp_httpx_guard.py` (extra pin; see Anomalies).
  - No re-export was needed beyond `_looks_masked`, which is not a moved name. `test_api_name_rule.py` passes unchanged.
- **AC7 (sizes).**

  | File | Lines |
  | --- | --- |
  | `api.py` | 6529 -> 5083 (-1446) |
  | `mcp_sources_api.py` | 272 |
  | `mcp_connection_api.py` | 436 |
  | `mcp_connection_flow.py` | 517 |
  | `connectors_api.py` | 385 |

  All are under 800 lines. `ruff check` and `ruff format --check` are clean over `the_one tests scripts evals`.
- **AC8.** `the_one/agents.md` has a new "Web route modules (M37 F2 L1)" paragraph, with the `_api` proxy rule, after the architecture overview. Three stale lines were updated: the `_connect_with_tokens` home, the route home for `test/agent`, and the `httpx2` drivers.
- **Tests (AC5, AC6).**
  - Named and related API files (`test_connector_*`, `test_mcp_*`, `test_oauth_*` and others): 1422 passed.
  - `THE_ONE_TEST_NETNS=1 make test-unit`: **12356 passed, 15 skipped** (the expected skip count under netns) in 299.68 s. The load was 10-17, and the other worktree's tier had finished.
  - Browser lanes under `THE_ONE_TEST_NETNS=1`, `TEST_TIMEOUT=3600`, one at a time, load 21-26 from other projects:

    | Lane | Passed | Time |
    | --- | --- | --- |
    | `mcp` | 105 | 1150 s |
    | `mcp-connection` | 102 | 1186 s |
    | `library` (holds the connector editor) | 122 | 1497 s |

  - There were no failures and no flakes, and 0428 was not hit.
  - I waited about 90 minutes for the `the-one-sortie-20` worktree's gate to finish before starting any lane.

### Leg 2: agent-write-lock (squawk 0327)

- **What changed.**
  - `the_one/agent/service.py::agent_write_lock(name)`: a refcounted registry `{name: [Lock, count]}`; the entry is popped at zero with no await between the decrement and the pop, so the dict stays bounded.
  - `replace_agent` and `change_agent` keep their public signatures. Each now takes the lock and calls a `_..._locked` body that is the old body unchanged (`change_agent`: whole body, retry loop included).
  - In `api.py`, the credentials, approve and restore routes keep their decorator, signature and docstring. Each wraps a `_..._locked` function holding the old body. The one new import is `agent_write_lock`. Nothing near `delete_agent` or `app.py` was touched.
  - The lock rule is in `the_one/agents.md`, service section, bullet "Agent write lock (squawk 0327)". There is no "Agent PUT preserves credentials" section.
- **AC2 call-graph note.**
  - No writer renames. `replace_agent` forces `data["name"] = name`. `store.rename` is a separate store method with its own transaction; it is not a load-merge-save writer.
  - No writer calls another under the lock. The routes call only the repositories and `write_checks`.
  - No `agent_write_lock` is taken inside a `precheck` or `on_commit` hook. The order is always agent lock, then the store write lock inside `save`.
  - `proposals/apply.py::apply` calls `kinds/agent.py::apply`, which calls `change_agent` outside any `write_transaction`. It only runs a busy-session check, `kind.exists` and `summary_text` first. The `on_commit` hook (`_mark_applied`) runs inside the save's transaction, under the agent lock, and never takes the lock itself.
  - A concurrent `change_agent` for the same agent from the proposal path serializes behind the lock, so the precheck retry loop no longer races a PUT.
- **AC2b, whole-row agent writers found by `grep store.save(` (and `agent_store.save(`).**

  | Site | Disposition |
  | --- | --- |
  | `service.py` `create_agent` | Not a load-merge-save. It inserts, with a `_must_not_exist` precheck under the store lock. Out of scope. |
  | `service.py` `replace_agent` | **Locked.** |
  | `service.py` `change_agent` | **Locked.** |
  | `api.py` credentials route | **Locked.** |
  | `api.py` revision approve | **Locked.** |
  | `api.py` revision restore | **Locked.** |
  | `self_configuration/manage.py:212, 253, 380` | Out of scope: a background cascade. Follow-up. |
  | `mcp/rename_references.py:162` | Out of scope: a background cascade. Follow-up. |
  | `knowledge/kb_rename.py:126` | Out of scope: a background cascade. Follow-up. |
  | `db/override_cleanup.py:130` | Out of scope: a background cascade. Follow-up. |
  | `db/migration.py:42` | Out of scope: startup migration. Follow-up. |
  | Sortie 20 `delete_agent` | Out of scope (Sortie 20's change); a delete racing a save is a possible follow-up. |

  - **Column-level UPDATEs, not whole-row saves:**
    - the notes toggle, `set_notes_enabled` (`repositories.py:380`);
    - the routines switches, `set_routines_self_config` (`:409`);
    - the self-revision approval mode (`:365`);
    - `apply_revision` (`:441`).
- **Tests.** New `tests/test_agent_write_lock.py`, 9 tests, gated on `asyncio.Event` (no sleeps).
  - 3 registry tests: dropped when idle, released on an error and on cancellation, and different agents do not block each other.
  - Credentials save + PUT, in both orders. This pair is the falsification target.
  - Revision approve + PUT, in both orders.
  - `change_agent` + PUT, in both orders. A regression guard.
  - The wait for "second writer parked at its gate, or queued on the lock (refcount at least 2)" is deterministic: `sleep(0)` yields only, bounded by `wait_for`.
  - 502 passed over the related files (agent service, name rule, plain names, agent credentials, self-configuration API, write and agent writes, and the new file).
- **Falsification.**
  - I edited the lock out of the credentials route.
  - Both credentials/PUT tests then failed: `assert 'sp' == 'new'`, the PUT's change was lost.
  - I put the lock back, and they pass.
- **Tier (incomplete).**
  - `THE_ONE_TEST_NETNS=1 make test-unit` ran with the default 1200 s timeout and was killed by `run-tests.sh` at 98% (the `test_resolver_clip` tests), after 12169 PASSED lines and no FAILED or ERROR line.
  - The load was 17-28 throughout. The `the-one-sortie-20` worktree started browser lanes (`chats-transcript`, then `settings`, then `gleepglorp-kinds`) soon after my tier began and has run them back to back since. A clean quiet-host rerun with `TEST_TIMEOUT=3600` was therefore not possible.
  - Instead: 502 passed over the related files (`-x`), and `ruff check` and `ruff format --check` over `the_one/` and `tests/` are clean.
  - **A full-tier rerun is outstanding** (expected: 12356 + 9 passed, 15 skipped). The Flight Director should run it when the host is quiet.

### Leg 3: python-size-ratchet (landed)

The Developer implemented the leg. The Flight Director ran the tier and landed it: the Developer handed back before the tier, because the other worktree was running browser lanes.

- **AC1 and AC2, the ratchet** (`tests/test_python_module_size.py`).
  - It scans `the_one/**/*.py` with `LIMIT = 800`, using the three rules of `test_area_module_size.py` and synthetic self-tests.
  - A fourth check requires a comment on every `ALLOWANCE` entry.
  - The failure messages name the remedy: split the module, or raise its ceiling in the same PR with a reason.
  - No Python under `the_one/` is generated or vendored, so nothing is excluded.
  - `ALLOWANCE`, from the line counts on this branch:

    | Module | Ceiling |
    |---|---|
    | `interfaces/web/api.py` | 5108 |
    | `interfaces/web/app.py` | 4139 |
    | `db/repositories.py` | 4121 |
    | `db/schema.py` | 3627 |
    | `diagnostics.py` | 1364 |
    | `mcp/client.py` | 1171 |
    | `interfaces/desktop/shell.py` | 1162 |
    | `visuals/chart_image.py` | 1095 |
    | `tools/filesystem.py` | 844 |
    | `agent/factory.py` | 836 |
    | `tools/resolver.py` | 826 |
    | `routines/service.py` | 805 |

- **AC3, P5 logging.** One `logger.info` line per successful write, giving the kind, the id or name, and the action. Each line is logged after the commit, never inside a hook.
  - The writes covered:
    - `agent/service.py`: create, replace, change;
    - `rules_service.py`: create, change;
    - `provider_service.py`: create, replace, change;
    - `knowledge/service.py`: create, replace, change;
    - `secret_store/service.py`: create, replace, metadata change;
    - `proposals/apply.py`: apply, dismiss.
  - Two caplog tests in `tests/test_secret_service.py` check the logging. One asserts a single line per action, with the secret value and description text absent. The other asserts a refused write logs nothing.
- **AC5.** One sentence in `CLAUDE.md` Conventions names the Python and JS 800-line guards.
- **Tests.**
  - The ratchet and secret-service tests: 29 passed.
  - The agent, knowledge, provider, rules, agent-rules API and proposals files: 280 passed.
  - `ruff check` and `ruff format --check` are clean, across 1072 files.
  - **Unit tier (Flight Director):** `THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=3600 make test-unit` gave **12370 passed, 15 skipped in 786 s**, rc=0. That is 12365 plus the 5 new tests. It started at 02:23, with no other test process running and load 18 from other projects.
- **Deviation:** the Developer tried three shell writes (an inline Python edit script, a heredoc append and a `sed -i`). The shell-write hook blocked all three, and the Developer redid them with Edit and Write. This breaks the crew rule against shell writes (squawk 0286); it goes to the debrief.

## Anomalies (Leg 1)

- `tests/test_mcp_httpx_guard.py` pinned `api.py` for the two `httpx2.AsyncClient(auth=...)` drivers by AST (`ast.Name`). One driver moved, and it is now spelled `_api.httpx2.AsyncClient`. The guard now scans `api.py` and `mcp_connection_flow.py` and accepts the attribute form.

## Decisions

## Deviations

## Anomalies

## Session Notes

### Flight Director Notes

- **2026-11-25, flight start.**
  - Flight 2 is `in-flight` on branch `flight/02-backend-boundaries`, from `main` at `7518aefa`. `main` already holds PRs #390 (Flight 1) and #391 (turnaround: 0422, 0424-0427).
  - The crew file is `.flightops/agent-crews/leg-execution.md`, now with the 0410 and 0427 hygiene rules.
- **Operator decisions in force:**
  - the operator merges each PR, and the Flight Director stops there;
  - the debrief goes in the flight's PR;
  - take the recommended option at each decision point.
- **Design decisions added at flight start** (see `flight.md`): the sequencing with Sortie 20, the closing gate's quiet-host check and fallback, T2 carried from Flight 1, and squawk 0428 folded in.
- **Sortie 20 at flight start:** a local branch only, with no PR. It changes 24 lines of `api.py` around `delete_agent`, and also touches `app.py`, schema v57, `connection.py` and `repositories.py`.
- **Leg plan**, designed one at a time:
  1. `mcp-connector-routers`;
  2. `agent-routers`, only if Sortie 20 has merged, otherwise deferred;
  3. `agent-write-lock` (squawk 0327);
  4. `python-size-ratchet` (T3), plus optional write-service logging (P5);
  5. `closing-gate`, with the squawk 0428 fix first.
- **Host at flight start:** load about 20 to 23 from other projects.
- **Leg 1 risk tier: high.** The move touches 17 routes, their helpers, the route order inside FastAPI, and 35 test references to `api.py` names. It gets a design review.
- **Leg 1 design reviews** (Sonnet, two cycles). Both reviews said "approve with changes".
  - **Cycle 1** raised 2 high, 3 medium and 2 low issues. The highs:
    - The MCP group is about 1,080 lines, not the small group the leg assumed, so it is split three ways.
    - There was no rule for names that tests patch on `api.py`, so the `_api` proxy is now required.
  - **Cycle 2** raised 2 medium and 3 low issues: test files to name, the grep scope, and pre-splitting `mcp_connection_flow`.
- **Leg 1 landed** (Developer, Sonnet). Details are in the Leg 1 entry.
  - `api.py` went from 6529 to 5083 lines, into four new modules.
  - The OpenAPI and route-table comparisons are identical.
  - The unit tier passed: 12356 passed, 15 skipped.
  - The `mcp`, `mcp-connection` and `library` browser lanes passed, run one at a time at load 21-26.
- **Leg 2 decision (2026-11-25, at about 22:27): the `agent-routers` move is deferred.** Sortie 20's PR #392 is open and not merged. Under the sequencing decision, the agent route group is recorded for the connectors mission's leg 0, which is the flight's existing "acceptable variation". The legs are renumbered:
  - 02 `agent-write-lock`;
  - 03 `python-size-ratchet`;
  - 04 `closing-gate`.
- **Leg 2 (`agent-write-lock`) risk tier: high.** It is concurrency work on a shared write path. It gets a design review.
- **Leg 2 design review** (Sonnet): approve with changes. Three medium and three low issues, all folded in:
  - the two revision routes are now locked;
  - every whole-row writer is listed, and the background cascades are recorded as out of scope;
  - the lock order and the rule against locking inside hooks are stated;
  - the falsification test is the credentials-plus-Save pair;
  - the lock registry is refcounted.

  The Flight Director corrected two references: the revision routes are at `api.py:1867` and `:1932`, and the `agents.md` section name was wrong.
- **Leg 2 landed** (Developer).
  - The new lock tests and 502 related tests pass.
  - The falsification works: with the lock removed from the credentials route, both credentials-plus-Save tests failed (`'sp' == 'new'`).
  - The unit tier was killed at 98% by the 1200 s timeout, with no failures, at load 17-28. Sortie 20's worktree was running browser lanes at the same time. The Flight Director owes a re-run once no other test process is running.
- **Leg 2 unit tier re-run by the Flight Director, 2026-11-26 01:18.** It started once no test process from any worktree was running (load 2.79 at the start, 15.1 at the end, from other projects). Command: `THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=3600 make test-unit`. Result: **12365 passed, 15 skipped in 310.5 s**, rc=0. That is 12356 plus Leg 2's 9 new tests, so the tier result Leg 2 owed is closed.
- **Flight-end review of Legs 1-3** (Reviewer, Sonnet; credentials, OAuth and secret-logging surfaces): `[HANDOFF:confirmed]`, with no blocking issues.
  - 157 targeted tests passed, and ruff is clean.
  - Leg 1: every patched name goes through `_api`. `_SIGNIN_REQUIRED` is defined once, and the imports have no cycle.
  - Leg 2: the refcounted lock is correct, the five writers hold it from load to save, and it is never taken inside a hook.
  - Leg 3: the ratchet matches the JavaScript guard, and no log line can carry a value.
  - Two nits were accepted for the debrief:
    - in `agent/service.py`, the new `logger =` line separates the retry comment from `_MAX_ATTEMPTS`;
    - the `api.py` ceiling of 5108 matches the current count. Leg 2 added 25 lines over Leg 1's 5083.

  Legs 1-3 are marked `completed`, with a checkpoint commit before Leg 4.
- **Leg 3 (`python-size-ratchet`, plus P5 logging): risk tier low.** It adds a test and info-level log lines, with no design review.
  - **Parallel-work rule:** a PR may raise a ceiling in its own diff, with a reason. That way Sortie 20's growth of `app.py`, `repositories.py`, `schema.py` and `api.py` stays visible without blocking its rebase.
  - Once the ratchet lands, the Flight Director tells the Sortie 20 session about it.
