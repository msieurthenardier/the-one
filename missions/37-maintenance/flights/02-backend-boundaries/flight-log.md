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
- **Leg 4 (`closing-gate`, with the 0428 fix): risk tier medium.** The `_nav.goto` change touches every browser lane. The gate's full run is the validation for it, and Leg 4 is that gate.
  - The design follows squawk 0424's pattern, so there is no separate design review.
  - The caller audit for pages that never boot the app is an acceptance criterion.
- **Leg 3 (`python-size-ratchet`, plus P5 logging): risk tier low.** It adds a test and info-level log lines, with no design review.
  - **Parallel-work rule:** a PR may raise a ceiling in its own diff, with a reason. That way Sortie 20's growth of `app.py`, `repositories.py`, `schema.py` and `api.py` stays visible without blocking its rebase.
  - Once the ratchet lands, the Flight Director tells the Sortie 20 session about it.
- **2026-11-26, #392 merged during Leg 4.** The Developer was paused, origin/main was merged in cleanly as `e8647483`, and the Developer resumed. It had four post-merge steps: the size ceilings, the 0428 evidence, the unit tier on the merged tree, then the gate.
- **Leg 4 landed** (Developer, about 8 h). The readiness wait found no quiet window, so the fallback ran: 23 lanes one at a time, 6 h 36 min, at load 2 to 25.
  - Seven failures, all load races. Six were fixed with a boot-ready wait or a longer timeout. The seventh is squawk 0433, open.
  - T2 is not met, and goes to the mission debrief as unmet.
- **Flight-end review of Leg 4 and the merge** (Reviewer, Haiku: only tests, docs and artifacts changed, no security-sensitive surface).
  - It found one blocking issue: squawk 0433's Verification recorded "passes 3 of 3 in isolation", but no such run happened. The only isolation run had failed.
  - Two non-blocking issues: the lane table had no budget column or total, and the readiness line was ambiguous.
  - The other checks passed: the `_nav.goto` boot wait comes after the handoff, the ceilings match `wc -l`, and the merge lost nothing from Legs 1-3.
  - These are artifact-only fixes, so the Flight Director made them, and a narrow Haiku re-review checked them.
  - Leg 4's evidence for pre-existing failures rests on Sortie 20's recorded `main` run (flight log line 257 there). This flight did not run `main` itself.

## Leg 4: closing-gate (Developer, 2026-11-26)

- **0428 fix.** `tests/browser/_nav.py::goto` takes keyword-only `boot=True` and calls `wait_router_started` after `page.goto`; `boot=False` skips it. `tests/test_nav_helper.py` updated (kwargs test uses `boot=False`) plus a new boot/no-boot test; 84 passed.
- **Caller audit** (grep of `tests/browser/`, about 107 files): no `_nav.goto` caller loads a non-app page or a failing `/api/config`, so none needed `boot=False`. Looked at: `test_flow_chat_time_zone.py` (held `/api/time-settings`; boot waits 2 s at most), `test_flow_studio_tool_override_state.py` (real `/api/config` fulfilled), `test_router_core.py` (`__held` is the leave guard, after boot). The gate found no `goto` caller broken by the wait.
- **Isolation of the squawk's test:** `test_the_empty_states_text_column_is_centred` passed 3 of 3 at load 12 to 15 (it was not failing at that load before; no slow-route stub was run, the host was not quiet).
- **Post-merge changes** (after `main` with Sortie 20 came in, `e8647483`): the four size-ratchet ceilings raised to 5126, 4171, 4170 and 3662, each with a reason; `test_python_module_size.py` passes. Squawk 0428 now carries Sortie 20's evidence plus the corrective action (status `in-progress`).
- **Unit tier on the merged tree** (start load about 14): **12387 passed, 15 skipped in 761.7 s**, rc=0.
- **Readiness (AC2):** one 60-minute wait. An unlogged attempt prepared at 02:42 was discarded; the counted wait ran 02:59:55 to 03:59:55 (scratchpad `wait.log`, one sample a minute). Load ranged 1.3 to 20 from other projects, never 3 consecutive minutes below 1.0 with no test process. **Outcome: NOT QUIET after 3600 s**, so the fallback ran. T2 not met: no quiet host.
- **Fallback per-lane run** (one lane at a time, `TEST_TIMEOUT=3600`, no overlap with any other test process, no `-x`, `--timeout 300`):

| lane | result | wall s | budget s | load start to end |
|---|---|---|---|---|
| chats | 5 failed, 173 passed | 1470 | 540 | 9.5 to 24.4 |
| chats-transcript | 1 failed, 151 passed | 1595 | 540 | 24.4 to 21.7 |
| chats-widgets | 32 passed | 430 | 240 | 21.7 to 20.7 |
| gleepglorp-chat | 84 passed | 892 | 330 | 20.7 to 6.7 |
| gleepglorp-fill | 45 passed | 396 | 210 | 6.7 to 7.9 |
| gleepglorp-kinds | 102 passed | 1180 | 450 | 7.9 to 17.0 |
| agents | 196 passed | 2119 | 780 | 17.0 to 6.8 |
| agent-tabs | 221 passed | 1628 | 750 | 6.8 to 7.6 |
| agent-routines | 84 passed | 806 | 360 | 7.6 to 13.6 |
| library | 122 passed | 1469 | 570 | 13.6 to 21.5 |
| knowledge | 65 passed | 843 | 420 | 21.5 to 10.2 |
| mcp | 105 passed | 1192 | 450 | 10.2 to 24.6 |
| mcp-connection | 102 passed | 1047 | 390 | 24.6 to 3.7 |
| routing | 193 passed | 1650 | 810 | 3.7 to 11.0 |
| settings | 126 passed | 1349 | 480 | 11.0 to 21.6 |
| settings-tools | 174 passed | 1133 | 330 | 21.6 to 21.1 |
| providers | 1 failed, 143 passed | 1400 | 420 | 21.1 to 21.4 |
| contracts-overlay | 558 passed, 1 skipped | 427 | 240 | 21.4 to 10.9 |
| contracts-chat | 358 passed | 113 | 180 | 10.9 to 3.5 |
| contracts-widget | 156 passed, 2 skipped | 226 | 300 | 3.5 to 1.6 |
| contracts-widget-lifecycle | 113 passed | 112 | 150 | 1.6 to 7.7 |
| contracts-controls | 1308 passed, 4 skipped | 860 | 540 | 7.7 to 11.4 |
| shared | 365 passed | 1396 | 420 | 11.4 to 20.2 |
| **total** | 7 failed, 4976 passed, 7 skipped | 23733 (6 h 36 min, sequential) | 9900 (sum of lane budgets) | |

  The budgets are the `scripts/run-tests.sh --help` table, which assumes a quiet `--parallel 3` run. A sequential run at load 2 to 25 is not comparable to them, so no wall time here is a budget reading and nothing is re-budgeted. No lane was killed by `TEST_TIMEOUT`.
- **Triage (AC4).** Seven failures, all re-run in isolation at load 17 to 22 and all reproduced:
  - `test_flow_new_chat.py` (4 tests) and `test_flow_provider_setup.py::test_first_start_provider_setup_flow`: raw `page.goto(base)` then a first `expect` on an empty `<main>`; the squawk 0428 class (they are in 0428's Sortie 20 evidence list, failing on pristine `main`). Fixed with `_nav.wait_router_started(page)` after the goto; 13 passed at load 18 to 22.
  - `test_flow_context_overlay_thresholds.py::test_overlay_custom_warn_threshold_moves_transition`: `httpx` 5 s `ReadTimeout` on `/api/config` under load, also failing on pristine `main` per Sortie 20. Timeout raised to 30 s; passes.
  - `test_flow_chat_live_updates.py::test_a_message_sent_during_a_mid_turn_join_is_held_then_delivered`: fails in isolation at load 18; also on pristine `main` per Sortie 20's record. Not touched. **Logged as squawk 0433.**
  - No failure is new to this flight. I did not run `main` myself; I relied on Sortie 20's recorded failure of these tests on `main` `7518aefa`. The new `test_flow_agents_delete_dialog.py` ran in the `agents` lane and passed.
  - About 98 other raw `page.goto(<base>)` sites remain unwrapped; they passed. Follow-up noted in 0428.
- **Re-budget (T2): not met, no quiet host.** `scripts/run-tests.sh` is unchanged. One sentence added to `agents.md` "Budget history".
- **Lint:** `ruff check` and `ruff format --check` clean on `tests/` and `the_one/`; `tests/test_nav_helper.py` and `tests/test_run_tests_lanes.py` pass (106).
- **Files changed:** `tests/browser/_nav.py`, `tests/test_nav_helper.py`, `tests/test_python_module_size.py`, `tests/browser/test_flow_new_chat.py`, `tests/browser/test_flow_provider_setup.py`, `tests/browser/test_flow_context_overlay_thresholds.py`, `the_one/agents.md`, `squawks/0428-...md`, `squawks/0433-...md`, the leg file, this log.
