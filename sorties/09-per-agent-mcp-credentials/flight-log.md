# Flight Log: Per-agent MCP credentials

**Flight**: [Per-agent MCP credentials](flight.md)

## Summary
Sortie planned 2026-11-03 from an operator request: let one Library MCP server be used by many agents, each with its own header or environment values (for example its own API key and permissions), instead of registering a duplicate server per agent. Charter agreed the same day, with the operator adding that switching a server on for an agent should test the connection immediately.

---

## Planning Notes

### Qualification (2026-11-03)
All four sortie criteria pass: one outcome (per-agent credentials on a shared server, end to end), one cluster of decisions (how the override is edited, secret handling, when a change takes effect, which tool list an agent sees), about two legs plus a HAT, no new subsystem. No open mission or sortie overlaps. Per-agent OAuth sign-in (M07 F08 Anomaly A4) is a separate cluster and out of scope.

Leg budget flagged as tight once the operator chose a per-agent tool list; re-check at the gate.

### Findings from code interrogation (at `2958510f`)
- **The backend already exists.** `the_one/mcp/_overrides.py` declares `StdioMCPOverride.env` and `StreamableHttpMCPOverride.headers` / `bearer_token` (all `Substitute`); `_tool_provider.py::_apply_override` overlays them flat onto `source.secrets` (agent wins); `agents.mcp_overrides` is Fernet-encrypted; `_agent_response` masks `MCP_OVERRIDE_CREDENTIAL_KEYS`; `_merge_preserved_mcp_credentials` keeps stored values per inner key.
- **No UI.** `mcps-tab.js:37` says overrides are not rendered (M07 F08 Anomaly A5: the bearer field was removed at HAT because it made no sense for OAuth servers; carry-forward #2 was a non-OAuth override surface, and #4 asked for browser coverage of the render-and-collect cycle).
- **The pool pins the first override.** `_pool.acquire` keys on `(agent_name, source_id)` and pins `source_override` for the entry's lifetime; an agent Save does not evict, so a changed key would not apply until the idle reap or a restart.
- **Agent builds use the shared tool cache.** `_tool_provider.py` Path B hydrates from `source.config["_cache"]["tools"]` when present and skips `acquire`; Path A (empty cache) already lists with the agent's effective source. The Tools tab's per-source tool list comes from the source-level `fetchMcpSourceTools`.
- **Blank Library values are sent.** `streamable_http.py::build_request_headers` merges config headers and secrets as-is, so a header saved with an empty value goes out as an empty header.
- **OAuth sets Authorization through the SDK provider** (`httpx2.AsyncClient(auth=provider)`), and the auth-posture probe classifies by the status it gets with the operator headers applied.
- **No eviction anywhere on credential edits.** Nothing in `create_agent`/`update_agent`/`rename_agent`/`delete_agent`/`update_mcp_source` evicts pool entries (`_pool._evict(key)` exists, `_pool.py:254`).
- **Open chats capture credentials at build.** `MCPClientTool` stores `_effective_source` (`_tool.py:126`) and passes it to every `acquire` (`_tool.py:174-177`); a session's agent is rebuilt only at a join (`app.py:~1956`). Eviction alone would reconnect with the old values. This drove DD7's resolve-at-connect.
- **The Library Test writes the shared cache even for a body override** (`api.py:4023-4444`; only `last_check` and the era are gated). A per-agent test through it would overwrite the shared tool list. This drove DD6's separate route.
- **Masking keeps names.** `_agent_response` masks each inner value of `headers`/`env` and keeps the keys (`api.py:255-266`), so the tile can show which names an agent has set.
- **Merge trap.** `_merge_preserved_mcp_credentials` takes a present entry's non-credential keys from the body (`resolved_entry = dict(incoming_entry)`), so a credentials-only entry would wipe stored tool filters (DD1 rule).
- **Debrief carry-forwards** (sorties 04, 07, 08; M34; M07 F08/F09): the sortie 07 422 shape and save-error route; open-and-close must stay clean and fields must name event/announcement/focus; raw-body validation before the merge; sortie 04's evidence rule for `MCPCredentialsRejected`; no probe on tile expand (M07 F09 A-L3-2); legs over ~15 ACs need a checkpoint; a leg touching agent write routes names the full `--parallel 3` gate; dry-run behavior-test setup; test servers use fast shutdown polling. Squawk 0301 (stdio start failure says only "Connection closed") will show in a per-agent stdio test; not fixed here.

### Operator decisions (2026-11-03)
- Charter agreed, with the switch-on test folded into criterion 3.
- Tile layout: "Credentials above tools" (DD10 mockup).
- Open chats: new credentials at the next tool call; tool-list changes at the next join or in a new chat.
- Leg shape: two legs plus HAT, kept as a sortie (over the soft limit in volume, not in decisions); leg 1 has a mid-leg checkpoint.
- Acceptance: behavior test `per-agent-mcp-credentials` plus an interactive HAT leg.

### Flight design (2026-11-03)
- DD1-DD11 written; behavior test drafted at `tests/behavior/per-agent-mcp-credentials.md`.
- While drafting the behavior test, two ambiguities were closed in DD10: "Needs a value for X" takes precedence over a connection result, and a Save that changed a tile's credentials re-tests once with the saved values to fill the per-agent cache.

### Architect review 1 (2026-11-03): approve with changes
All findings taken:
- **High, DD1:** the merge is per name only for masked values. A left-out inner name is dropped (pinned by `tests/test_db_api.py:407-449`), and a `null` inner value is stored and then breaks every build of the agent. DD1 now has Studio send the full name set (unchanged names as `__MASKED__`, removed names left out, all-removed as `headers: null`); the merge is unchanged; DD2 refuses any non-string inner value.
- **High, DD2/DD8:** `_cache.auth_posture == "oauth"` is written by Phase 0 for any 401, which is exactly a "Set per agent" server's answer. OAuth state is now `oauth_active` only.
- **High, behavior step 6:** the existing mask shows the last 4 characters of a long value. The step now asserts that no full key appears; DD9 acknowledges the tail.
- **Medium, DD6:** must not run Phase 0, and the no-token path was undefined. The steps are rewritten: Phase A extracted into a side-effect-free helper; the stdio and no-auth helpers gain `persist`/`record_era`; `auth_required` and `MCPCredentialsRejected` are reported separately.
- **Medium, DD3:** with blanks dropped, a 401 would read as a sign-in prompt. Configured names, blank or not, now count as evidence; `needs_values` names what is missing; the Library Test of a "Set per agent" server skips Phase 0 and Phase B.
- **Medium, shared cache:** the Tools tab's first-expand probe is what wrote the shared cache for agents with no override. DD6 now writes those shared fields for such an agent (never posture or `last_check`).
- **Medium, tile list:** a credentialed agent is never shown the shared list.
- **Medium, header values:** the RFC 9110 field-value grammar plus refused transport-managed names; a bad value would otherwise reach the agent inside an h11 error.
- **Medium, leg size:** split into three legs plus HAT (operator, 2026-11-03); legs 1 and 2 add the `mcp` and `mcp-connection` lanes.
- **Medium, 800-line rule:** the error mapping goes into the new module; the controller gets a delegate of at most 10 lines.
- **Low:** the drawer's shared count accepted as a known effect; behavior-test details (no request on `needs_values`, `max_iterations: 1`, `MCP_POOL_IDLE_TTL_SECONDS=3600`, `_cache` assertions); the `bearer_token` row; case-insensitive header overlay; the rename edge documented.
- **DD7 mechanism** adopted as proposed: `resolve_source` awaited on the worker task inside its `try`; the pre-`try` OAuth block moves inside it.
- **Suggestions taken:** the DD6 logic in a new module; a race guard (re-read before `put`) instead of a fingerprint column; a generation guard and a "Testing…" state.

### Architect review 2 (2026-11-03): approve with changes
Review 1's findings are resolved in the text. The rewrite introduced four medium issues, all fixed:
- **Medium, DD3:** skipping Phase B on the Library missing-values path would block sign-in for an OAuth server with a "Set per agent" header. The path now runs Phase A with live tokens; otherwise the no-auth path, falling through into Phase B on `MCPAuthRequired`. Only a bare 401 is `MCPCredentialsRejected`.
- **Medium, DD3/DD6:** "never writes `auth_posture`" can't be met by a `persist` switch, because the no-auth helper writes the posture in the same call as `tools`. The `cache_write: none | shared | shared_no_posture` modes are now defined once, in leg 1, with each caller's mode stated.
- **Medium, DD5:** check-then-write could store a stale list over one shared aiosqlite connection. The guard is now a single `INSERT OR REPLACE ... SELECT ... WHERE agents.updated_at = ?` statement, with an interleaving unit test.
- **Medium, DD6:** an unsaved removal carries no new value but tests different credentials. The route persists only when the merged credential keys equal the stored ones.
- **Low, all taken:**
  - the case-insensitive overlay covers `config.headers`, `missing_values` and case-duplicate refusal;
  - the value grammar covers `bearer_token`;
  - leg 1 evicts pool entries only and leg 2 adds the cache-row deletes; the order inside the worker's `try` is stated; resolver failures become `MCPConnectionError`;
  - `override_for` is used in DD4, DD6 and the cache exposure; DD6 refuses the self-configuration row, and an unknown agent is a 404;
  - a blank stdio value lets the host's allowlisted value through (intended);
  - DD11's log records the method and a sequence number, and behavior steps 10, 12 and 13 name `tools/call`;
  - the leg 3 client cache is keyed by agent and source, and the `mcp-error.js` prefix is kept;
  - `update_agent` ignores derived response fields (pinned in leg 2);
  - DD4 doesn't count a per-agent Authorization skipped on an OAuth server;
  - the Library Test still records `last_check` for a body-less Test.
- Both review cycles used. The changes after review 2 are precision fixes, so there was no third pass.

### Gate re-check and ready (2026-11-03)
- Still one cluster of decisions: what a per-agent credential changes, end to end (how it is edited and validated, when it takes effect, which tool list it yields, how it is tested). Per-agent OAuth sign-in stays out.
- Three legs plus a HAT is over the soft limit of two plus a HAT. The operator chose this shape explicitly after Architect review 1 (the alternatives were two legs with a mid-leg commit, or escalation). The size comes from volume (a migration, a refactor of the Library Test path, a new UI module), not from a second set of decisions.
- Status set to `ready`.

---

## Flight Director Notes

### Execution start (2026-11-03)
- Ran `/mission-control:agentic-workflow sortie 09`. Phase file `.flightops/agent-crews/leg-execution.md` loaded (Developer Sonnet; Reviewer Sonnet on security-sensitive diffs, else Haiku; Accessibility Reviewer Sonnet for UI).
- Branch `sortie/09-per-agent-mcp-credentials` created from `main` at `2958510f`. Flight status `ready` -> `in-flight`.
- **Review and commit cadence:** one review and commit per autonomous leg, not once per flight. The operator approved the three-leg shape on the option text "Each leg ends with a commit", and legs 1 and 2 both change the Library Test path, so an early review is worth its cost. Recorded as a deviation from the skill's default of one review at flight end.

### Leg 1 `credentials-take-effect`: design (2026-11-03)
- Risk tier: **high**. It touches a security-sensitive surface (credentials, the MCP sign-in classification), the pool's connect lifecycle, and a shared interface (`acquire`, the two test helpers' signatures, `MCPCredentialsRejected`). A Developer design review runs.
- Reviewer tier for this leg's code review: **Sonnet** (credentials).
- Developer design review (Sonnet): **approve with changes**. All taken:
  - **High:** a `cache_write` keyword passed from existing callers would break the stub at `tests/test_mcp_test_connection_negotiation.py:361`. It now defaults to `"shared"` and is passed only from the new branch; `record_era` already exists.
  - **High:** the existing fall-through into Phase B writes `auth_posture: "oauth"` and folds `MCPAuthRequired` with `MCPCredentialsRejected`. The no-auth helper gains `classify`, and the missing-values branch enters Phase B without `_persist_oauth_posture` and with `rejection_evidence=False`.
  - **Medium:**
    - branch placement before the `cached_posture == "no_auth"` return;
    - source-independent validation rules apply to orphan entries; top-level `null` clears stay valid;
    - the `bearer_token` overlay removes Library `Authorization` in any case;
    - `MCPCredentialsRejected` gains an optional `missing`, with the message unchanged when it's empty (four pinned tests);
    - the AC12 harness: factory-form `_test_http_client_override`, `LifespanManager`, async API client on the test loop.
  - **Low:**
    - `resolve_source` at the `create_task` call; the pinned OAuth import text;
    - the hook positions in `update_agent`/`update_mcp_source`;
    - fixture keys of at least 8 characters;
    - the full unit suite in the gate;
    - the resolver's `KeyError` fallback with a fixed error text.
  - The designer's questions were settled by the Flight Director:
    - a stdio Library Test takes no missing-values path;
    - orphan entries get the source-independent rules;
    - `rejection_evidence=False` on the missing-values entry into Phase B;
    - the rejection keeps "rejected the configured credentials" plus the names.
  - No second review cycle: the changes adopt the reviewer's own mechanisms, and one stale guidance line was corrected. Leg status `ready`.

## Leg Progress

### Leg 1 `credentials-take-effect`: landed (not committed)
- **Built (AC1-AC15 all done):**
  - `mcp/override_validation.py` (DD2 rules, 422 shape) called from `create_agent`/`update_agent` before the merge;
  - `_overrides.py` helpers `has_oauth_state`, `configured_names`, `missing_values`;
  - `_apply_override` case-insensitive overlay across both Library layers, OAuth `Authorization`/`bearer_token` skip;
  - blank-drop in `build_request_headers` and `build_stdio_environ`;
  - `MCPCredentialsRejected(missing=())` and the `_signin_signal` configured-names evidence rule;
  - the Library Test missing-values branch plus `cache_write`/`classify` on the two helpers;
  - `acquire(resolve_source=...)` with the resolver and OAuth-provider block moved inside the worker `try`;
  - `make_source_resolver` in `_tool_provider.py`, passed by `MCPClientTool.execute`;
  - `_evict_all_for_agent` and the eviction hooks (agent create/update/rename/delete, `update_mcp_source`);
  - `tests/fixtures/mcp/key_server.py` (flags and `/_log` copied into the behavior spec);
  - docs: `the_one/agents.md` block, `SECURITY-MODEL.md` paragraph.
- **Tests:** new `tests/test_mcp_agent_credentials.py` (62), `test_mcp_library_test_missing_values.py` (18), `test_mcp_pool_resolve.py` (13), `test_mcp_key_server.py` (5). One existing pin changed: `tests/test_mcp_pool.py::test_entry_worker_uses_synthetic_csid_when_tokens_present` (a provider-build failure is now recorded as `entry.failure` instead of escaping the worker, which is the AC9 contract).
- **Verification:** `THE_ONE_TEST_NETNS=1 make test-unit` 8876 passed, 15 skipped (the netns count); `mcp` lane 87 passed; `mcp-connection` lane 94 passed; `ruff check` and `ruff format --check` clean.
- **Falsification (by editing the fix out, running, restoring by editing):**
  - eviction hook removed: end-to-end, the open-tool and hook tests fail (yes);
  - resolver bypassed with eviction kept: end-to-end and resolver tests fail (yes);
  - validation call disabled: 4 API tests fail (yes);
  - blank-drop removed: 2 tests fail (yes);
  - `_signin_signal` evidence reverted to `build_request_headers`: 4 tests fail (yes);
  - Library missing-values branch disabled: 4 tests fail (yes). The cached-`no_auth` test was strengthened (a 401 naming a sign-in must reach Phase B) so it discriminates the branch placement;
  - not separately falsified: the overlay case-insensitivity and OAuth-skip unit tests (they found a real bug on first run instead: a same-entry `authorization` header and `bearer_token` were both sent; fixed), the `cache_write`/`classify` mode tests, `_evict_all_for_agent` and the source-update eviction test.
- **Deviations / notes:**
  - the API client in the end-to-end tests is `httpx.AsyncClient` over `ASGITransport` (the project's existing API-test client, async on the test loop), not `httpx2`;
  - `_entry_worker` is spawned with the two-argument call when no resolver is given, so existing stubs of the old signature keep working;
  - validation also refuses a non-dict top-level `headers`/`env` and non-empty `headers` on stdio / `env` on HTTP at the field loc;
  - the AC14 leak assertions are in the refused-save, rejected-connection and resolver-failure tests. Note a plaintext `config.headers` value does appear in aiosqlite DEBUG statement logs (config is plaintext by design); secrets are encrypted before they reach it.
- **Anomalies:** none beyond the above. Static JS/CSS untouched; no schema change; no per-agent cache table or `/test/agent` route.
- Leg 1 landed (Developer `[LAND:leg]`): 16/16 ACs; `make test-unit` (netns) 8876 passed, 15 skipped; `mcp` 87 passed; `mcp-connection` 94 passed; ruff clean. Per-leg code review spawned. Reviewer tier: **Sonnet** (credentials, the sign-in classification).
- Leg 1 review-fix pass: name/value grammar regexes in `override_validation.py` now use `fullmatch` (a trailing newline in a header or env name is refused; tests added, falsified); `_apply_override` returns the source unchanged when the OAuth skip empties the headers (identity test added, falsified).
- Leg 1 code review (Sonnet): no blocking issues; two non-blocking issues fixed (name regexes now `fullmatch`, so a trailing newline is refused; `_apply_override` returns the source unchanged when the OAuth skip empties the agent headers), three new test cases, all falsified; `make test-unit` (netns) 8878 passed, 15 skipped. Accepted without a second review: the fixes are small and tested. Leg 1 status `completed`; checkpoint commit.

### Leg 2 `per-agent-tool-list`: design (2026-11-03)
- Leg 1 committed as `4b274ae4`.
- Risk tier: **high**: a schema migration (v50), cache freshness, the Library Test's Phase A extraction, and credentials. A Developer design review runs. Reviewer tier for this leg's code review: **Sonnet**.
- Deviation from DD6's suggested module path: the route logic goes in `the_one/interfaces/web/mcp_agent_test.py`, not `the_one/mcp/agent_test.py`. The helpers it reuses live in `interfaces/web/api.py`, and an `mcp/` module must not import from `interfaces/`.
- Developer design review (Sonnet): **approve with changes**. All taken:
  - **High:** there was no reusable `shared_no_posture` writer, and the response lacks the shared fields. The persistence mode is now decided before connecting and passed as `cache_write` to the helpers, and the Phase A helper writes for itself.
  - **High:** the rule for agents not in the store contradicted AC5. Such an agent (an injected config) keeps the shared cache, as today; Flight Director call.
  - **Medium:**
    - `agent_updated_at(name)` on the new repository;
    - the reader context, with the projection reaching the table through `get_connection()`;
    - a cold per-agent cache: the projection reports `tools_known: False` and the index skips the source (only Path B/A lists live), and the provider runs before the index;
    - the Phase A helper keeps function-local imports and re-raises errors untouched;
    - an OAuth source plus a per-agent header: a test.
  - **Low:**
    - the layering precedent (the `routines_api.py` proxy);
    - `extra: ignore` on `AgentConfig`;
    - the version pins are symbolic, plus a v50 migration test;
    - `updated_at` writers;
    - the upgrade effect;
    - converting `MCPTool` objects before the put.
  - No second cycle: these are precision fixes taken from the review itself. Leg status `ready`.

### Leg 2 `per-agent-tool-list`: landed (not committed)
- **Built (AC1-AC15 done; AC16 results below):**
  - schema v50 `agent_mcp_tool_cache` and `AgentMcpToolCacheRepository` (`get`, `get_for_agent`, `agent_updated_at`, single-statement `put_if_unchanged`, `delete`, `delete_for_source`);
  - `mcp/_overrides.py::has_credential_override` and the new `mcp/_agent_cache.py` (`per_agent_tools`, `to_cache_payload`) that the three readers share;
  - readers: `_tool_provider` Path B/A (a cold row lists live and fills the row with the pre-listing stamp), `factory._build_source_index`, `self_configuration/projection.py`;
  - cache-row deletes at leg 1's hooks (`_evict_changed_mcp_credentials`, `update_mcp_source`, `reset_mcp_connection`);
  - Phase A extracted as `api.py::_connect_with_tokens`; the Library Test calls it and keeps token clearing, eviction and fall-through;
  - the route `POST /api/mcp-sources/{source_id}/test/agent` with its logic in `interfaces/web/mcp_agent_test.py`;
  - `mcp_tool_cache` on GET, create, update and rename (not `list_agents`);
  - docs: `the_one/agents.md`, `CLAUDE.md`, `SECURITY-MODEL.md`.
- **Tests:** new `tests/test_agent_mcp_tool_cache.py` (38), `tests/test_mcp_agent_test_route.py` (14), shared harness `tests/_agent_mcp_world.py`; v50 class in `tests/test_db_migration.py` (3); an ordering test in `tests/test_mcp_tool_provider.py`.
- **Verification:** `THE_ONE_TEST_NETNS=1` full unit tier (`-m 'not browser and not live and not pixel'`) 8974 passed, 19 skipped (that marker expression adds the 3 `requires_bwrap` skips to the netns 15; the 19th is one more load-timing skip, the watcher file passed alone with only its root-permission skip); the Library Test files (`test_oauth_test_connection_endpoint`, `test_mcp_library_test_missing_values`, `test_mcp_test_connection_negotiation`, `test_mcp_stdio_test_connect`, plus stale-tokens, last-check, reset) pass untouched after the Phase A extraction; `ruff check` and `ruff format --check` clean; browser lanes through `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1`, one at a time: `mcp` 87 passed, `mcp-connection` 94 passed, `agents` 180 passed.
- **Falsification (by editing the fix out, running, restoring by editing):**
  - DD4 switch off in Path B: 5 tests fail, including the end-to-end test (yes);
  - race guard `= ?` replaced: 2 tests fail, the repository interleave and the save-during-listing build test (yes);
  - cache-row delete in `_evict_changed_mcp_credentials` removed: 1 fails (yes);
  - `_drop_source_agent_tool_cache` body removed: 1 fails (yes);
  - route persistence mode for a stored credentialed agent changed to `shared_no_posture`: 3 fail (yes);
  - not separately falsified: `has_credential_override` cases (parametrized truth table), the projection and index readers (covered by the same table plus the cold-row tests, but their individual switches were not removed), the `mcp_tool_cache` response field, the Phase A extraction (covered by the untouched Library Test files).
- **Deviations / anomalies:**
  - **The version pins in `tests/test_db_migration.py` were NOT symbolic** (about ten literal `== 49`); updated to 50 or `CURRENT_VERSION`, and one `TestSchemaV49` check relaxed to `>= 49`. `tests/test_schema.py`, `test_schema_template.py` and the template needed no edit.
  - **Index ordering:** the leg said `get_tools_for_agent` already ran before the index build. It ran after, so `AgentFactory.create` now builds the MCP tools before `_build_source_index` and registers them where it did (ordering test added).
  - The projection reaches the table through `mcp_repo.conn` rather than `get_connection()`, so existing projection tests on their own connection keep working.
  - `tests/test_mcp_tool_provider.py::patch_provider_deps` now stubs the per-agent repository as "agent not in the store" (its connection is a bare `AsyncMock`).
  - `tests/test_api_name_rule.py` classifies the new route.
  - Responses of the route carry `error` text of the form `Class: message` for typed MCP errors (as the Library Test does); an unexpected exception on the token path returns the class name only.
  - Static JS/CSS untouched.
- Leg 2 landed (Developer `[LAND:leg]`): 16/16 ACs; unit 8974 passed, 19 skipped (one skip unidentified); `mcp` 87, `mcp-connection` 94, `agents` 180 passed. Deviations: literal version pins in `test_db_migration.py`; the factory now builds MCP tools before the search index. Code review spawned (Sonnet), with the skip and the factory order as named checks.
- Leg 2 code review (Sonnet): `[HANDOFF:confirmed]`, no blocking issues.
  - **Skip count resolved:** with `not requires_bwrap`, the unit tier is 8934 passed, 15 skipped, all 15 known netns skips (3 root-permission, 11 Windows-only, 1 locale). The Developer's 19 came from a marker expression without `not requires_bwrap`, which adds 3 bwrap skips; the 4th was likely a timing-conditional watcher skip and did not recur.
  - **Factory order** confirmed: same registration order and filters, an unchanged index for agents with no override, and no extra read for them.
- Leg 2 status `completed`; checkpoint commit.

### Leg 3 `credentials-ui`: design (2026-11-03)
- Leg 2 committed as `4b6071f1`.
- Risk tier: **high**. It changes a shared write path (the agent Save body for `mcp_overrides`) and a security-sensitive UI (credential entry), and replaces the Tools tab's `/test/connect` call. A Developer design review runs.
- Flight-level review for this leg: **Sonnet Reviewer** plus the **Accessibility Reviewer** (UI change).
- Developer design review (Sonnet): **approve with changes**. All taken:
  - **High:** the post-save re-render drops `mcp_tool_cache`. Copy it as `kb_tool_names` is copied.
  - **High:** the tab handle wasn't reachable from the form or the save path. Add an `mcpsTab` getter through the controller, `studio.js` and `ctx`.
  - **High:** the controller has only 29 lines of room. The split helper and shared tab logic move into the new module.
  - **High:** unlisted test breaks: the `tests/test_store_static.py` pin; `test_studio_mcps_tab.py`'s `/test/connect` mocks, Refresh shape test and dirty test.
  - **Medium:**
    - `setAgent` always rebases;
    - the pre-existing snapshot drift (an empty `{}` entry is dropped when nothing is stored);
    - masks go under the stored name spelling;
    - `secretInput` show/hide labels;
    - lane choice: the new file is `test_flow_studio_tools_mcp_credentials.py`, in `agent-tabs`, with a budget check.
  - **Low:**
    - Refresh moves into the body;
    - the master's user-only `onChange`, with `loadStarted` and `gen` set on toggles;
    - the Library hint goes in the section description;
    - loc names are mapped to tiles;
    - `mcp-sources` is invalidated after a no-override `ok`.
  - The designer's questions were settled by the Flight Director:
    - one leg with a mid-leg checkpoint commit (part A AC1-9/12/13 testids/test migrations; part B AC10/11/14-16), keeping the operator's three-leg shape;
    - `setAgent` always discards pending edits;
    - an empty entry is dropped when nothing is stored;
    - `secrets` keys are row names;
    - on a mixed 422, the MCP refusal gets focus.
  - No second review cycle: precision fixes taken from the review. Leg status `ready`.

### Leg 3 part A (checkpoint): built, not committed (leg stays `in-flight`)
- **Built:** `areas/studio/mcp-agent-credentials.js` (`App.studio.mcpAgentCredentials`: `create`, `hasStoredCredential`, `splitItems`; handle `setAgent/setSource/payload/isDirty/missing/showErrors/setStatus/destroy`); `mcps-tab.js` mounts the section, status line (Refresh moved there), `runTest` on `testMcpAsAgent`, switch-on/first-expand/Test/Refresh/afterSave triggers, per-tile `gen`, list choice (`listedTools`), handle methods `credentialPayloads/changedSourceIds/afterSave/showCredentialErrors`; `agent-data.js::testMcpAsAgent` (fetchMcpSourceTools deleted); `agent-form-data.js` merges payloads (stored tool filters copied when rows never loaded; empty entry dropped); controller: `mcpsTab_()` getter, `found.mcp_tool_cache` copy, `credIds` + `afterSave` call (783 lines); `studio.js` `mcpsTab` wiring; CSS `mcp-agent-cred-*`; `index.html`; registry rows.
- **ACs done:** AC1-AC9, AC12, AC13 (testids, registry), AC15 test migrations and new file (16 tests). AC10 (`mcpsTab_` plumbing, `showErrors`, `showCredentialErrors` exist but the controller 422 delegate and its test are part B), AC11, AC14, AC16 left.
- **Verification:** static guards (ui_guards, token_definitions, a11y, ownership, emitted_classes, area_module_size, store_static, nav_helper, run_tests_lanes) 479 passed; ruff check/format clean; `test_studio_mcps_tab.py` 32 passed; new file 16 passed; lanes `agent-tabs` 179 passed (330 s), `agents` 179 passed + 1 failure (`test_flow_agents_focus_after.py::test_form_is_clean_and_shows_the_stored_model_while_loading`, model-loading timing; 3/3 pass isolated), `routing` 186 passed (450 s).
- **Falsified (edit out, run, restore):** tool-filter copy (yes), empty-entry drop (yes, after adding a later dirty check to the test), `mcp_tool_cache` copy (yes, after keeping the tile unopened), switch-off gen bump (yes, after restructuring the test). Not falsified: row-state/focus/payload matrix tests, list choice, post-save re-test, stdio, switch-on request body.
- **Deviations:** (1) the empty-entry drop applies whenever the stored entry has no tool filter (not only when no stored entry), else opening a credentialed agent's tile reads dirty; (2) tests for existing behaviour changed: switch-on now expands the tile, so `test_real_clicks_dirty_the_form` and `test_one_save_covers...` no longer click expand; `test_refresh_on_collapsed_tile...` became `test_switch_on_expands_the_tile_and_tests_once`; (3) an error shows both the status line text and the existing role=alert block (test pins the alert), so it announces twice; (4) cached lists show "Last checked (with this agent's values) · N tools" (wording mine); (5) `mcp-error.js` regex untouched (still matches the old prefix and "Server error").
- Leg 3 part A checkpoint (Developer `[HANDOFF:review-needed]`): AC1-9, AC12, AC13 testids and the AC15 migrations done; static guards 479 passed; `agent-tabs` 179 passed (330 s, budget 510); `routing` 186 passed. `agents` had 179 passed and 1 failed: `test_flow_agents_focus_after.py::test_form_is_clean_and_shows_the_stored_model_while_loading`, which passed 3/3 isolated. It is the same model-loading timing flake noted in sortie 08's log, so it is accepted under the flake rule.
- Flight Director calls on part A's deviations:
  - The broadened empty-entry drop (whenever the stored entry has no tool filter) is accepted. An omitted entry keeps the stored one server-side, so nothing is lost.
  - The "Last checked · N tools" wording is accepted, and goes to the HAT to confirm.
  - The double announcement (status line plus the existing `role=alert`) goes to part B to resolve.
- Checkpoint commit.

### Leg 3 part B: landed (not committed)
- **Built:** AC10: `onSaveError_` splits `mcp_override` details with `splitItems` and calls the new `mcp-agent-credentials.js::placeSaveErrors(tab, items)` (selects the Tools tab, expands named tiles, row/section errors, focus the first, unplaced details to the header); MCP focus wins over a `tool_override` one; `mcps-tab.js::showCredentialErrors` now returns `{placed, unplaced}`. Controller 792 lines. A real defect found by the new test: a refused ADDED row was not found by `showErrors` (new rows are not in `byKey`), so its message went to the section; `showErrors` now matches a new row by its typed name, puts the error on it and focuses its name input. AC11: Library value placeholder "Set per agent" and the hint (section `description`, testid `mcp-env-headers-hint`). AC13: behavior spec cites the testids; registry rows added. AC14: `agents.md` (Tools-tab half of the sortie 09 block, the MCPs-tab paragraph, the store table row) and one `CLAUDE.md` paragraph. Deviation 3 resolved: on an `error` result the status line drops its `role=status` (restored for every other state), so the tile's `role=alert` block is the one announcement.
- **Tests added (5):** `test_a_real_save_422_lands_on_its_row_with_focus` (a real server 422), `test_an_mcp_refusal_gets_focus_over_a_tool_override_one` (mocked PUT 422 with both kinds), `test_an_mcp_refusal_with_no_row_or_tile_goes_in_the_header`, `test_a_failed_test_is_announced_once` (all in `test_flow_studio_tools_mcp_credentials.py`, 20 tests now) and `test_kv_empty_value_says_set_per_agent_and_the_hint_is_shown` (lane `mcp`).
- **Falsification:** announced-once (yes: with the role removal disabled it failed); MCP-focus-over-tool (NO: with the `|| placed.focus` term removed the test still passed, because the tool field's focus does not land in this setup, so the test does not prove the ordering; the HAT should check it); real 422 test found the new-row defect (failed before the fix); unplaced-to-header and Library placeholder not falsified.
- **Verification:** static guards plus `test_store_static`, `test_nav_helper`, `test_run_tests_lanes`, `test_ui_control_inventory` 485 passed; ruff check and format clean; `THE_ONE_TEST_NETNS=1 make test-unit` 8934 passed, 15 skipped (the netns count); full gate (start load 0.67, quiet): `PARALLEL_RESULT rc=1 total=1931s lanes=17 failed=routing,agent-tabs`. The two failures: `routing`: `test_store_library.py::test_invalidate_mid_flight_then_get_issues_a_second_request[knowledge-bases]` (unrelated to this change; passes isolated); `agent-tabs`: my own new `test_a_real_save_422...` (asserted `.editor-error` count 0, but the element exists hidden; fixed to `not_to_be_visible`, then the file passes 20/20 and the pair passes isolated). Both lanes were not re-run in full after the fix.
- **Lane budgets:** none over (`agent-tabs` 439 s vs 510, `routing` 573 s vs 720, `chats` 392 s vs 420 is the tightest at 93%); no re-budget.
- **Deviations:** the detail about the focus test above; `showCredentialErrors` return shape changed from an array to `{placed, unplaced}` (no other caller).

### Leg 3 review fix pass (not committed)
- Accessibility: "Set for this agent: {name}" and "Use server value for {name}" (WCAG 2.5.3; the other buttons already began with their visible text); the status line keeps `role=status` and toggles `aria-live` off while it shows an error, restored to polite one task before the next text is written; `aria-invalid` on a refused row's input (cleared on input); the section-level error node exists only while there is an error; row error ids use a sequence, not the raw name. `agents.md` export list corrected (`testMcpAsAgent`).
- Tests: label-in-name assertion (not falsified), announced-once extended with an aria-live-at-write recorder (not falsified), focus-ordering test now logs every focusin (MCP-focus rule falsified: yes; "tool field steals focus" term not reachable in this flow, so not falsifiable).
- Results: unit 8934 passed, 15 skipped; `agent-tabs` 183 passed (335 s); `routing` 186 passed (449 s, the earlier store_library failure did not recur).
- Leg 3 reviews: code review (Sonnet) `[HANDOFF:confirmed]`, no blocking issues. The accessibility review (Sonnet) was **not confirmed**: one blocking issue (WCAG 2.5.3, Label in Name, on "Set for this agent" and "Use server value") and four non-blocking ones. One fix pass handled all five plus two code-review notes. Results: unit 8934 passed, 15 skipped; `agent-tabs` 183 passed (335 s); `routing` 186 passed (the part B `test_store_library.py` failure didn't recur). The accessibility re-review is spawned.
- **Anomaly (process):** the fix-pass Developer ran one `sed -i` on `the_one/interfaces/web/static/js/areas/studio/mcp-agent-credentials.js`. That breaks the edit-tool-only rule (squawk 0286), and the `block_shell_writes.py` hook (squawk 0292) did not block it, although it blocked a second `sed` on `the_one/agents.md`. The two changed lines are as intended and are covered by the accessibility re-review. Carried to the debrief as a possible hook gap.
- Accessibility re-review (Sonnet): `[HANDOFF:confirmed]`; all five findings verified fixed, including the `sed`-edited lines.
- **Leg 3 gate disposition:** the part B parallel gate was `PARALLEL_RESULT rc=1 total=1931s lanes=17 failed=routing,agent-tabs` (start load 0.67). Accepted for these reasons:
  - The `agent-tabs` failure was the new test's own wrong assertion (`count 0` on a hidden node), fixed and re-run green: 183 passed, 335 s.
  - The `routing` failure (`test_store_library.py::test_invalidate_mid_flight_then_get_issues_a_second_request[knowledge-bases]`) is unrelated, passed isolated, and the full lane re-ran green: 186 passed.
  - No lane was over budget (`agent-tabs` 439 s of 510 in the gate; `chats` the tightest at 392 of 420).
- Leg 3 status `completed`; commit. All three autonomous legs are complete.

### Behavior test `per-agent-mcp-credentials` (2026-11-04)
- **Run `2026-11-04-00-59-35`: PASS, 14/14 checkpoints** (live mode, Sonnet Executor and Validator, build `794a4d30`). Run log: `tests/behavior/per-agent-mcp-credentials/runs/2026-11-04-00-59-35.md`.
- **What it proved:**
  - two agents on one key-less Library server each reached it with their own key and saw their own tools (`echo`; `echo` and `add`);
  - the key-less agent got `needs_values` without a connection;
  - a key saved from a second browser context applied on an open chat's next tool call, with the idle TTL pinned at 3600 s, so eviction was the only explanation;
  - the shared cache was never written;
  - no full key appeared in any log or data file, the database WAL included.
- **Preconditions:** set up by the Flight Director, including a dry run of steps 1-2 against a throwaway data directory; teardown by PID, with all ports free afterwards.
- **For the HAT:**
  - the row reads "Set per agent · missing" between typing a key and Save (no pending state shown);
  - the cached wording after a reload is "Last checked with this agent's values · N tools";
  - switch-on with a known missing value doesn't call `/test/agent` (computed in the client);
  - the switch track overlay intercepts locator clicks (real pointer clicks work).
- **Spec follow-ups** (Validator closing): name the pre-save row state, the cached wording and the `editor-unsaved` observable; note that the mock response is global; consider a positive encrypted-column check in step 14.

### Leg 4 `hat` (2026-11-04)
- Session environment (Flight Director):
  - scratch instance on port 8486 (`~/the-one-bt-s09/hat-data`, `THE_ONE_SANDBOX_DISABLED=1` for the stdio step) and a key server;
  - seeded with `alpha`, `beta`, `plain`, `keyed` (blank `X-Api-Key`), `signin-demo` (fake OAuth tokens written to the scratch database through the encrypted repository, so `oauth_active` is true) and `hello-stdio` (blank `HELLO_TOKEN`).
- Two handoff links lapsed for the operator. The log shows the second was used and the app loaded with every request at 200 before the WebSocket closed, which is consistent with the window being closed or a different browser opened. A third link was minted with guidance to keep the same browser window.
- **H1, operator decision (changes charter criterion 1's wording):** the Library wording was confusing.
  - The value placeholder returns to its pre-sortie `value`; "Set per agent" is dropped from the Library editor.
  - The hint becomes "Optionally override headers in agent settings." (stdio: "Optionally override environment variables in agent settings.").
  - A blank Library value is still never sent, and the agent tile's "Set per agent · missing" row state is unchanged.
  - Fix-vs-feature: a look-and-feel **fix**, one surface, inline.
  - Behavior spec step 3 re-authored to the new wording.
- H1 fix committed: placeholder `value`, hint by table type; `make test-unit` (netns) 8934 passed, 15 skipped; `mcp` lane 88 passed.
- **H1 PASS** (operator, after the wording fix).
- **H2: feature promoted through the fix-vs-feature gate.** The operator found the tile works but is off-style (the wrong font, a value field that is too short) and asked for it to match the Library headers table, with one "Override headers" button replacing the per-row buttons.
  - Flight Director call: a **feature**. It reshapes an approved surface and changes behaviour: per-agent sensitivity, a table model, and a narrower write-only rule.
  - Operator answers: a Sensitive toggle per row, like the Library, so a non-sensitive value is shown in clear again. The locked table shows the effective headers with Key and Value only; the toggle and trash appear once Override is on.
  - Recorded as **DD12** in flight.md. Next: a scoped design review, then implementation, then accessibility and code review, then re-verifying H2.
- **Debrief item (operator, 2026-11-04): "another time a mockup prior to implementation would have been good."**
  - DD10 had an operator-approved mockup, but it was ASCII. It fixed the structure and couldn't show the font, field widths or visual consistency with the Library headers table, the existing control the operator expected the section to match.
  - The gap surfaced only at the HAT and cost a redesign (DD12).
  - Lesson for the debrief and the methodology: squawk 0293's mockup rule should require a **rendered** mockup in the app's real styles and controls for any new or reshaped surface, and should ask "which existing surface should this look like?" when a comparable control exists.
  - Applied immediately: DD12 is not implemented until the operator approves a rendered mockup.
- **DD12 scoped design review (Sonnet): approve with changes.** About two legs:
  - four generic `App.ui.keyValueTable` options (`readOnly`, `lockBy`, `onBeforeRemove`, `markerBy`) with two-engine contract tests and catalogue rows;
  - a server `plain_names` field (not a credential, stripped before the resolver, pruned in the merge, unmasked in `_agent_response`, `Authorization` never plain);
  - a module rewrite on the table, with a shared column builder extracted from `mcp-env-headers.js`;
  - a rewrite of `test_flow_studio_tools_mcp_credentials.py`, the retired testids, and behavior spec steps 4, 5, 7 and 11.
- Flight Director calls on the review's questions:
  - emptying an overridden server value reverts to the server value (as trash does);
  - a per-agent `Authorization` is always sensitive, refused as plain server-side;
  - trash on a server row with no override is disabled;
  - the locked view uses the Library's mask shape;
  - Test, Refresh and the status line stay as they are, and Cancel appears only while unlocked.
- **Operator decision (2026-11-04): add legs to sortie 09** (5: server `plain_names` plus the table-control options; 6: the tile rewrite plus tests). Each starts after a **rendered** mockup is approved; then the HAT resumes at H2. Sortie 09 grows to five legs plus HAT, above the soft limit; the operator chose this over a follow-up sortie 10. Still one decision cluster (the per-agent credential surface).
- **DD12 rendered mockup approved (operator, 2026-11-04)** after three rounds:
  - the section title is just "Headers";
  - the action row is status, then Override headers and Test while locked, and Cancel, Save and Test once unlocked; Refresh is removed;
  - the tile's Save saves immediately through a targeted route;
  - the row pill reads **"overridden"** (meaning this agent sends its own value instead of the Library's, or has a header the Library lacks).
  
  The mockup page was served from the Flight Director's scratchpad on port 8491 (screenshots `dd12-mockup/mockup-{dark,light}.png`). Legs 5 and 6 are designed from it.

### Leg 5 `sensitivity-and-table-options`: design (2026-11-04)
- Risk tier: **high**. It adds a path that returns a credential value in clear, a new route, and a shared control-library API change. Reviewer tier for its code review: Sonnet, plus the Accessibility Reviewer (factory changes).
- Developer design review: **approve with changes**, all taken as a binding addendum in the leg:
  - the validation gate widened to cover `plain_names`;
  - the targeted route seeds the stored tool filters and resolves the source id to its name;
  - the `readOnly` null-remove guards;
  - a disabled-remove CSS override and click guard;
  - `setRow` re-evaluates the lock, marker and removable state.
- Flight Director calls:
  - the targeted route accepts an unattached source (404 only for an unknown agent or source);
  - the list route returns plain values too;
  - native `disabled` for the non-removable trash;
  - toggles are disabled under `readOnly`/`lockBy: 'row'`;
  - the narrow main-PUT race is accepted and documented.
- No second review cycle (precision fixes from the review itself). Leg status `ready`.

### Leg 5 `sensitivity-and-table-options`: landed (not committed)
- **Server:** `plain_names` on both override schemas (plain field; `MCP_OVERRIDE_CREDENTIAL_KEYS` unchanged; stripped in `_apply_override`); validation (list of strings; `Authorization` refused) with the gate widened to entries carrying `plain_names`; merge keeps/clears/replaces it and `_prune_plain_names` prunes before the empty-entry check; `_agent_response` returns plain values in clear (headers case-insensitive, env exact; `bearer_token` and `Authorization` never); new `PUT /api/agents/{name}/mcp-overrides/{source_id}/credentials` (404 unknown agent/source, 422 surface row, unattached source accepted, tool filters seeded from the stored entry, evicts via the existing helper, `_full_agent_response`). Classified in `test_api_name_rule.py` EXEMPT.
- **Factory:** `readOnly`, `lockBy`, `onBeforeRemove`, `markerBy`/`markerLabel`, `removableBy`, `setRow` re-evaluation; CSS `.ui-kv .ui-kv-remove:disabled` (opaque token) and `.ui-kv-marker`. No change when no option is passed (a contract test pins it).
- **Docs:** `ui-control-inventory.md` row, `agents.md` sortie 09 block, `SECURITY-MODEL.md` paragraph (incl. the `_looks_masked` limitation).
- **Verification:** new `tests/test_mcp_plain_names.py` (29 tests) plus 7 new contract tests x 2 engines; related files 488 passed; `make test-unit` (netns) 8963 passed, 15 skipped; `contracts-controls` (WebKit required) 1186 passed, 4 skipped; `mcp` 88; `agent-tabs` 183; `agents` 180, all passed; static guards and inventory/ownership/emitted-class tests 388 passed.
- **Falsification:** removing the `:disabled` CSS rule fails `test_removable_by_disables_with_the_opaque_look`; disabling the `onBeforeRemove` hook fails `test_on_before_remove_can_cancel` (both yes, restored by edit). Other new tests not falsified.
- **Deviations / notes:** the credential-gate 401 is covered by the generic gate sweep, not a route test. `ruff check` reports one pre-existing E501 at `tests/browser/test_flow_studio_tools_mcp_credentials.py:777` (committed leg 3 code, untouched here).
- Leg 5 reviews: code review (Sonnet) `[HANDOFF:confirmed]`, no blocking issues (532 unit and guard tests, 134 contract tests, ruff format clean; the one E501 predates leg 5). Accessibility review (Sonnet) `[HANDOFF:confirmed]`: marker pill contrast about 5.7:1 dark and 5.9:1 light; the disabled remove uses opaque tokens. Notes carried into leg 6: move focus before a `setRow` that disables a focused remove button; two style nits in `key-value-table.js` (a long line at ~250, a missing space at ~535). Leg 5 status `completed`; commit.

### Leg 6 `tile-on-the-table`: design (2026-11-04)
- Leg 5 committed as `56057a65`.
- Risk tier: **high**. It rewrites a credential UI and changes the main Save's write path. Reviewers: Sonnet code review plus the Accessibility Reviewer.
- Developer design review: **approve with changes**, all taken as a binding addendum:
  - the tile Save rebases only its own tile (never the tab-level `setAgent`);
  - an `onCredentialsSaved` callback keeps the controller's copies current;
  - the dead main-Save credential code is deleted;
  - a separate leave-guard source;
  - the shared helper's load order;
  - the testid retirement list corrected (`-cancel-`/`-add-` reused, not retired);
  - stable `data-rid` row addressing;
  - mapping rules (case, stored spelling, duplicate keys, emptying an override reverts it);
  - focus before disabling a focused remove button.
- Flight Director calls:
  - a sign-in server shows no `Authorization` row, only a note;
  - other `Authorization` rows keep an editable value with the toggle locked on, via a new `lockBy: 'toggle'` factory value in this leg;
  - the main Save and Cancel leave a dirty unlocked tile alone;
  - create mode disables the tile Save (a change from leg 3).
- Leg status `ready`. Part A then a checkpoint commit, then Part B.

### Leg 6 part A (checkpoint): built, not committed (leg stays `in-flight`)
- **Built:**
  - `mcp-editor-shared.js`: `titleFor`, `hintFor`, `rowsFromSource`, `SENSITIVE_INFO` and `tableColumns(readOnly)` (columns + info button, no testids; callers build the table so testids stay literal for the registry guard). `mcp-env-headers.js` uses them, no behaviour change (`mcp` lane 88 passed untouched).
  - `ui/key-value-table.js`: `lockBy` now a space-separated token list (`key`, `row`, new `toggle` = toggle checked and disabled, the rest editable; `setRow` re-evaluates); style nits fixed. Contract tests `test_lock_by_toggle_*` (x2 engines) and the catalogue row. CSS: the marker pill sits at the right end of the key input (as in the mockup).
  - `mcp-agent-credentials.js` rewritten (697 lines): locked read-only table (effective rows, "overridden" pill, masks, clear plain values), Override/Cancel/Save/Test action row, unlocked Library table (server keys read-only, empty value + disabled trash on non-overridden server rows, trash reverts an overridden server row with focus moved to its value first, Authorization toggle locked on, no Authorization row on a sign-in source but a note, duplicate-name row error blocking Save, Add row defaults to sensitive), the DD12 payload (`__MASKED__` under the stored spelling, `plain_names`, `bearer_token: null`), the tile Save with 422 placement on rows, the create-mode note.
  - `mcps-tab.js`: mounts it; tile Save rebases only that tile (`onCredSaved`, never tab `setAgent`) and re-tests with `overrides: null`; credential edits no longer call the editor's `onChange`; `setAgent` leaves a dirty unlocked tile alone (`adoptAgent`); `anyDirty()`; the leg 3 payload/afterSave/showCredentialErrors hooks and Refresh are gone.
  - `agent-data.js::saveMcpCredentials` (the targeted PUT, then merges `mcp_overrides` and `mcp_tool_cache` into `_selectedAgent` and the list entry and invalidates `agents`), wired through `agent-editor-controller.js` and `agent-editor.js`. `agent-form-data.js` no longer merges credentials. `studio.js` registers the separate `studio-mcp-tiles` leave-guard source.
  - Controller 783 lines (was 792); `studio.js` 783. `.mcp-agent-cred-row*` CSS deleted. Registry and `RETIRED_SELECTORS` updated (12 retired prefixes; `-cancel-`/`-add-` reused; new `-override-`, `-save-`, `-table-`, `-oauth-note-`, `-create-note-`).
- **Tests:** `test_flow_studio_tools_mcp_credentials.py` rewritten (21 tests: locked view, stdio, sign-in note, Override/Cancel, trash on server/agent rows, Add row + duplicates, Authorization, typed Authorization, set + Save body + re-test + pill + lock, non-sensitive round trip across a reload, attach and tool check surviving a tile Save with the main Save body carrying no credentials, main Save keeping credentials, real 422 on a row, create mode, leave guard, plus the kept switch-on, missing-value, stale-result, shared-list, announced-once and clean-open tests). `test_studio_mcps_tab.py` Refresh clicks re-driven with Test (merge-on-reload checks kept; the shape test now pins Test at 32px and the Override button).
- **Verification:** static guards (ui_guards, token_definitions, a11y, ownership, emitted_classes, control_inventory, area_module_size, store_static, nav_helper, run_tests_lanes) 485 passed; ruff check and format clean; key-value-table contract with `THE_ONE_REQUIRE_WEBKIT=1` 138 passed; new file 21 passed; lanes (`THE_ONE_TEST_NETNS=1`, one at a time): `agent-tabs` 184 passed (356 s), `agents` 180 passed (433 s), `mcp` 88 passed (223 s).
- **Falsified:** `lockBy: 'toggle'` (enforcement removed: the 4 new contract tests failed; restored). Not falsified: the tile tests (tile-only rebase, targeted body, retest, leave guard).
- **Deviations:** (1) the controller callback is one function, `agentData.saveMcpCredentials`, that does the PUT and merges the copies itself (no separate `onCredentialsSaved` callback). (2) The two leg 3 tests about a main-Save 422 with mcp_override details (focus over a tool override, header placement) are dropped: the main Save no longer carries credentials; the tile's own 422 test replaces them. (3) The "Needs a value" line clears while typing (existing follow-the-names rule). (4) `lockBy` accepts a token list so a server-defined Authorization row can lock key and toggle together. (5) A blank new row counts as an unsaved tile change (row set differs). (6) Added `-oauth-note-` and `-create-note-` testids (not in AC8).
- **Screenshots (compare with the approved mockup):** `scratchpad/tile-locked-dark.png`, `tile-unlocked-dark.png`, `tile-locked-light.png`, `tile-unlocked-light.png`.
- **Left for part B:** remaining AC9 cases, AC10 (behavior spec), AC11 (docs), AC12 (full gate).
- Leg 6 part A checkpoint (Developer `[HANDOFF:review-needed]`):
  - static guards 485 passed; key-value-table contract tests 138 passed (WebKit required);
  - the new credentials test file 21 passed;
  - `agent-tabs` 184 passed (356 s), `agents` 180 (433 s), `mcp` 88 (223 s); ruff clean.
  
  The Flight Director compared the real tile's screenshots (locked and unlocked, dark) with the approved mockup: they match (the "Headers" title, the "overridden" pill, masks and clear values, Override/Test, then the Library table with Cancel/Save/Test).
- Deviations accepted:
  - `saveMcpCredentials` in `agent-data.js` merges the editor's copies, in place of a separate callback;
  - the leg 3 main-Save 422 tests are dropped, replaced by the tile's real 422 test;
  - `lockBy` is a token list (`key`/`row`/`toggle`), because a server `Authorization` row needs key and toggle locked together;
  - a blank new row counts as dirty;
  - two added testids (`-oauth-note-`, `-create-note-`).
- Checkpoint commit.
- Leg 6 part B (Developer): landed, not committed.
  - **Built:** three new tests in `test_flow_studio_tools_mcp_credentials.py` (24 total): a mocked 422 whose `loc` name is lowercase lands on the mixed-case header row; emptying an overridden server row's value reverts it (name omitted from the body, pill gone, stored headers match); two unlocked tiles save independently. Behavior spec steps 4, 5, 6, 7 and 11 re-authored around Override, the table, the tile's Save and the locked table with the pill (testids named); Validator follow-ups folded in (pre-save state in step 5, "Last checked ..." wording and `editor-unsaved` in step 7, client-computed needs-values in step 4, global mock response in step 10, `/_log` baselines in Observables). `the_one/agents.md` (Tools-tab half, MCPs-tab paragraph) and `CLAUDE.md` tile sentence updated.
  - **Verification:** static guards 485 passed; ruff check and format clean; `THE_ONE_TEST_NETNS=1 make test-unit` 8963 passed, 15 skipped; full browser gate `PARALLEL_RESULT rc=0 total=1855s lanes=17 failed=-` (start load about 0.96, no other test process). No lane over budget (`agent-tabs` 425 s against 510 s), so no re-budget.
  - **Falsified:** none of the three new tests were falsified (no).
  - **Deviations:** the 422 test mocks the route response, since the real server cannot be made to return a lowercase loc. The focus-before-disable case is already pinned by part A's trash test.
- Leg 6 review-fix pass (Developer): focus returns to Save (else the first value, else Cancel) after a failed tile save with no row to blame (WCAG 2.4.3); the disabled Save is linked to the create-mode note by `aria-describedby` (the duplicate-name reason already sits on the key row, so no second link); the marker pill is `top: 1.25rem` and a key input in a row with a visible marker reserves `7.5rem` right padding (`:has`), marker contrast `--accent` on `--accent-translucent` over `--surface` is 5.60:1 dark and 5.98:1 light; the `lockBy`/`onBeforeRemove` doc comment is wrapped. New tests (all falsified, yes): main Save and main Cancel leave an unsaved unlocked tile alone (falsified by making `adoptAgent` rebase), focus to Save after a mocked 500, and the `aria-describedby` assertion.
- Leg 6 reviews: code review (Sonnet) `[HANDOFF:confirmed]`; accessibility review (Sonnet) `[HANDOFF:confirmed]`; no blocking issues.
- A fix pass took the useful non-blocking items:
  - focus after a save failure with no row to place it on;
  - the create-mode note linked to the disabled Save;
  - padding reserved for the marker pill (contrast 5.60:1 dark, 5.98:1 light);
  - a test that a dirty unlocked tile survives the main Save and Cancel;
  - a comment wrapped.
  
  All new tests falsified. Results: unit 8934+ green (8963 passed, 15 skipped); `agent-tabs` 190, `contracts-controls` 1190, `mcp` 88. The part B parallel gate was `PARALLEL_RESULT rc=0 total=1855s lanes=17`. Leg 6 status `completed`; commit.
- **HAT resumed (2026-11-04)** on the rebuilt tile. Legs 5 and 6 are committed (`56057a65`, `da200b99`, `1bce9b4b`) and the session instance was restarted on the new code (same data).
- **H2 PASS** (operator: "looks great, pass"):
  - locked view;
  - Override into the Library table, with a read-only server key and disabled trash;
  - Test with the agent's key;
  - tile Save locks with the "overridden" pill;
  - reload shows the cached state.
- **H3 PASS** (operator): beta's own key lists echo and add; plain is told it needs a value; the Library key stays blank.
- **H4 PASS**: the key server log shows the open chat's first `tools/call` with `-7Q2` (seq 3), the tile Save's re-test with `-3K8` (seq 4-5), then the same open chat (not reloaded) reconnecting and calling with `-3K8` (seq 6-8).
- **H5:** Cancel, trash-reverts, duplicate names and clean-up PASS. **Defect:** a refused header **name** (`Bad Header`) showed its message on the value field. Cause: the `mcp_override` 422 detail doesn't say whether the name or the value was refused, and `placeErrors` always targets the value. Fix (Flight Director design, two surfaces, small): an additive `part: name|value` on each detail, and the tile places on the key when `part=name`. Spawned; re-verify after it lands.
- **H5 fix (developer):** every `mcp_override` 422 detail now carries an additive `part` ("name" or "value"); the tile puts a `"name"` refusal on the Key input and focuses it. Tests: `tests/test_mcp_agent_credentials.py::test_refusals_say_whether_the_name_or_the_value_was_refused` and browser `test_a_refused_header_name_lands_on_the_key_input` (falsified); the old real-422 test now uses a value refusal.
- **H6:** the sign-in note shows; there is no Authorization row; another header can be overridden; Test works ("Connected with this agent's values · 1 tool").
  - **Operator change:** Override blanked the server's `acme` value to the "value" placeholder until Save, which is confusing. The unlocked view should keep the existing value.
  - New rule: a server row starts with the server's current value (clear, or its mask); unchanged means no override; changed means an override; trash reverts to the server's value.
  - A single-surface interaction **fix**, inline. Queued behind the name-vs-value fix, which edits the same module.
- HAT H6 (inline fix): the unlocked agent-tile table starts a non-overridden server row at the server's own value (clear, or its mask in stored-secret mode); unchanged = no override (omitted, no pill), changed = override, cleared = none; trash reverts to the server value; sensitivity alone is not an override. Supersedes DD12's empty-with-placeholder start.
- **H5 and H6 re-verified PASS** after the fixes (`7b5a822a` name-vs-value placement, `926b08c4` Override keeps the server value); session instance restarted on the new code.
- **H7 PASS** (operator): the stdio tile reads "Environment variables"; alpha's `HELLO_TOKEN` reached the spawned server (`dump_env` in chat). keyed's missing attachment on alpha was the operator switching it off, not a defect.
- **Defect found before H8 (operator):** with an unsaved duplicate-key row in an unlocked tile, the leave guard's **Continue** didn't discard the tile edits, and the guard re-prompted on every navigation; the duplicate row stayed. Cause: the `studio-mcp-tiles` `App.nav` source has a no-op `discard`, on the assumption that teardown discards, but the agent editor stays mounted across destinations. Fix (a defect, Studio area): `discard` cancels every dirty unlocked tile (restores the baseline and locks).
- HAT fix: leave-guard Continue now cancels unlocked MCP tiles (studio-mcp-tiles discard -> mcpsTab.discardAll); tests added in test_flow_studio_tools_mcp_credentials.py.
- **Leave-guard re-check PASS** (Continue discards the tile edits and doesn't re-prompt; Stay keeps them). Fix `07e05fff`.
- **H8 PASS** (operator, "all pass"): keyboard order through the locked tile, the unlocked table and the trio; focus rings; Save by keyboard returns focus to Override and re-tests.
- **HAT complete (H1-H8 pass; H9 operator satisfied).**
  - Fixes committed during the HAT: `53f441ef` (H1 Library wording), `7b5a822a` (a refused name lands on the key), `926b08c4` (Override keeps the server value), `07e05fff` (leave guard discards on Continue).
  - Feature promoted through the gate: DD12 (the Library-table tile), built as legs 5 and 6 after a rendered mockup was approved.
  - The session environment was torn down by PID.
- **Anomaly (Flight Director, HAT apparatus):** the restart after `926b08c4` did not take effect.
  - The recorded PID (`$!` of the `nohup` launch) was not the server's PID. The kill missed the running server (3993222), the new instance failed to bind 8486 (`Errno 98` in `hat-serve.log`) and exited, and `/api/live` kept answering from the old process.
  - **Impact:** the re-checks of H5, H6, the leave guard and H8 ran on server code from `1bce9b4b`. Static JS/CSS is served live from disk, so every client-side fix was live, but **the server half of the H5 fix (`part: name`) was not.** The operator's H5 re-check therefore couldn't have exercised it as built.
  - H5 rests on the browser test `test_a_refused_header_name_lands_on_the_key_input` (a real server, falsified) unless the operator re-verifies it.
  - The stale process was stopped by PID after its identity was checked through `/proc/<pid>/environ` (scratch `hat-data`, port 8486).
  - Lesson for the debrief: after a restart, verify the new PID owns the port (`ss -ltnp`), not just that `/api/live` answers.
- Operator decision: accept the automated browser test for H5's server half (no manual re-verify). Next: re-run the re-authored behavior test on the final build (`07e05fff`).

### Behavior test run 2 and landing (2026-11-04)
- **Behavior test `per-agent-mcp-credentials`, run `2026-11-04-18-29-45`** on the final build `07e05fff`: **13/14 PASS**. Step 5 **FAIL on a spec error**: the "overridden" pill shows on a changed, unsaved value, which is the behaviour the operator approved at H6. The operator confirmed it mid-run and the spec's step 5 was amended.
  - Every other check held, witnessed by the key server log: per-agent keys; `needs_values` without a connection; the tile Save writing immediately with no agent PUT; the open chat picking up the new key through eviction; the shared cache clean; no full key in any log or data file.
  - Run log: `tests/behavior/per-agent-mcp-credentials/runs/2026-11-04-18-29-45.md`. Teardown by PID with the port ownership verified (`ss -ltnp`).
- **Flight status `landed`.**
  - Legs 1-6 and the HAT are `completed`.
  - Commits on the branch: `4b274ae4`, `4b6071f1`, `0bfdfd38`, `794a4d30`, `9bcc2fe4`, `53f441ef`, `56057a65`, `da200b99`, `1bce9b4b`, `7b5a822a`, `926b08c4`, `07e05fff`, plus this landing commit.
  - Debrief items collected in this log:
    - the ASCII-vs-rendered mockup lesson;
    - the HAT restart PID miss;
    - the `sed -i` hook gap;
    - the Validator's spec follow-ups;
    - sortie scope growth (three legs plus HAT, grown to six legs plus HAT through the DD12 feature).
- **Debrief (2026-11-04):** `flight-debrief.md` written. The Developer and Architect interviews, plus the operator (a sortie was the right vehicle; the UI mismatch and the HAT bugs slowed things most). Squawks 0327-0329 were logged as deferred. Version bumped to 0.14.0 (`0e96ea17`). **Sortie status `completed`.**
