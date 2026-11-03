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
