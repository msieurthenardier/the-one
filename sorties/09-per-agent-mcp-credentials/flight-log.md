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
