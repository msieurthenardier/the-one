# Flight Log: Self-Configuration Surface

**Flight**: [Self-Configuration Surface](flight.md)

## Summary

In-flight. Leg 1 (`agent-config-secret-hardening`) designed 2026-08-24 and in design review.

---

## Reconnaissance Report

Mission 21 pre-enumerated findings with specific code citations, so each was
walked against current code before the leg breakdown was set. No commits landed
between the mission's authoring and this survey, so drift was expected to be
nil — the value here is in the **counts**, which the Mission 20 debrief named as
the recurring reconnaissance weakness ("strong at finding categories and weak at
counting within them").

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| `MCPSource.type` is a closed two-value literal guarded by a CHECK constraint | `confirmed-live` | `db/models.py:106`; `db/schema.py:400` | Avoided entirely by DD1 |
| "~14 production call sites switch on source type" | `confirmed-live` — count exact | `mcp/client.py:110,118,130`; `mcp/_tool_provider.py:88,90,93,157,168,181`; `api.py:985,1052,1081,1238,1730,1764,1766,1769` | 14 confirmed; untouched under DD1 |
| Transport rename precedent for a table-rebuild migration | `confirmed-live` | `db/schema.py:377-418` | Not needed under DD1 |
| Agent override columns are unencrypted JSON | `confirmed-live` | `db/schema.py:347-348,437-438` (plain `TEXT` via `ALTER`) | Leg 1 |
| Agent read endpoints return overrides unmasked | `confirmed-live` | `api.py:439-447,450-457` — both return bare `cfg.model_dump()` | Leg 1 |
| Substitutable override keys carry credentials | `confirmed-live` | `mcp/_overrides.py:60,89,90` — `env`, `headers`, `bearer_token` | Leg 1 |
| Per-agent tool provision runs in-process for every transport | `confirmed-live` | `mcp/_tool_provider.py:219-390` | Informs DD1 |
| System prompt baked once at construction; step loop never re-reads | `confirmed-live` — **but understated** | `agent/core.py:176-178`; loop re-binds `self.messages` per iteration at `:276-289` | See A1 below |
| Rejoin already rebuilds from the current agent row | `confirmed-live` | `app.py:1103-1111`, `:975` | `next_session` is free |
| Mission 20's three unspent seams | `confirmed-live` | Gate resolves identity; credential id distinct from secret; second-source registration | DD2 spends the first |
| M20 debrief action items (4 open) | `confirmed-live`, **out of scope** | Squawks 0001 and 0002 both still `open` | Flight 3 / squawk queue; none touch this surface |

### Items the mission did not enumerate, found during this survey

| Finding | Evidence | Disposition |
|---|---|---|
| **A1 — the propagation risk runs opposite to the mission's framing.** `_run_iterations` re-binds `request_messages = self.messages` *inside* its while loop, and tool dispatch happens in that same loop. A naive in-place mutation lands **mid-turn**, not next-turn. | `agent/core.py:276-289`, `:588` | DD7 — deferral required, not coordination |
| **A2 — no read path exposes a running agent's system prompt.** `session_joined` carries history, title, agent name, routing metadata; not the prompt. Propagation cannot be asserted by state inspection. | `app.py:1199-1220` | DD8 — behavioral assertion |
| **A3 — the type fall-throughs are silent.** `filter_mcp_tools_by_override` and `_apply_override` return input *unchanged* for an unrecognized type rather than raising. An unrecognized source type would have silently disabled the operator's per-tool control — mission criterion 8 failing with no error anywhere. | `mcp/_tool_provider.py:92-93`, `:181-185` | DD1's strongest argument |
| **A4 — ~26 further type-conditional sites in JavaScript**, uncounted by the mission. 22 in `mcp-server-editor.js`, plus `mcps-tab.js:148`, `studio.js:567-587`, `mcp-servers-grid.js:31`. | as cited | Untouched under DD1 |
| **A5 — `mcp/_pool.py` has zero `source.type` dispatch.** It delegates to `mcp/client.py`. | `mcp/_pool.py` (no matches) | Pre-declared split point does not fire |
| **A6 — agent credential overrides are already silently wiped by Studio.** `collectFormData` rebuilds `mcp_overrides` from the DOM while the MCPs tab renders no credential fields, so an API-set override does not survive the next save. | `studio.js:2064-2132`; `mcps-tab.js:21-26` | DD5 — preserve must be server-side |
| **A7 — `SQLiteAgentStore` carries no encryptor** and is constructed at 7 production + 30 test sites. | `db/repositories.py:74`; construction sites in `retention.py:58`, `connectors/_inbound.py:328`, `connectors/_pool.py:578`, `interfaces/cli.py:31`, `app.py:140,1283`, `api.py:68` | DD5 — defaulted parameter avoids the ripple |
| **A8 — `Encryptor.rotate_key` has no production caller.** Adding an encrypted column does not break an existing rotation path. | `encryption.py:53` | Recorded so the absence is not mistaken for a coupling |
| **A9 — the plaintext fallback removes the need for a data migration.** `_decrypt_secrets_blob` treats undecryptable input as plaintext. | `db/repositories.py:40-59` | DD5 — lazy re-encrypt on write |

**Retirements**: none. Every mission-cited item is live.

---

## Leg Progress

### agent-config-secret-hardening
**Status**: landed
**Started**: 2026-08-24 18:43 CDT
**Completed**: 2026-08-24 19:22 CDT

#### Changes Made
- `the_one/mcp/_overrides.py`: added `MCP_OVERRIDE_CREDENTIAL_KEYS`, a
  `frozenset` computed by scanning `StdioMCPOverride` /
  `StreamableHttpMCPOverride`'s `model_fields[...].metadata` for the
  `Substitute` marker (`{"env", "headers", "bearer_token"}`) — not
  hand-listed.
- `the_one/db/repositories.py`: `SQLiteAgentStore.__init__(conn, encryptor:
  Encryptor | None = None)` — defaulted, resolves via
  `get_encryptor(settings.data_dir)` when omitted, held by reference (39
  construction sites unaffected). Added `_encrypt_overrides_column` /
  `_decrypt_overrides_column` module-level helpers (the latter parses
  legacy plaintext on `InvalidToken` instead of `_decrypt_secrets_blob`'s
  `{}`-on-`InvalidToken`, per Decision D2). `save()` now encrypts both
  `tool_overrides` and `mcp_overrides`; `_row_to_config` is now an
  instance method (no external caller — confirmed via grep) decoding
  both columns through the tolerant helper.
- `the_one/interfaces/web/api.py`: added `_agent_response(cfg)` (masks the
  three marker-derived credential keys inside each `mcp_overrides[<source>]`
  entry; every other key, including all `tool_overrides`, passes through
  byte-identical) and `_merge_preserved_mcp_credentials(incoming, stored)`
  (per-`(source, credential key)` resolution: omitted/mask-shaped → keep
  stored, explicit `null` → clear, other → overwrite, dict-valued keys
  resolved per inner key; folds an empty result to `None` to preserve
  None/`{}` fidelity). `_agent_store()` now passes
  `get_encryptor(settings.data_dir)` explicitly. All six agent-config
  returns under `# ── Agents` (`list_agents`, `get_agent`, `create_agent`,
  `update_agent`, `detach_agent_from_connector`, `rename_agent`) route
  through `_agent_response`. `update_agent` resolves `mcp_overrides`
  against the stored row before validation; `create_agent` drops
  mask-shaped credential values (nothing to preserve against).
  `rotate_encryption_key` gained the agents columns as the fifth surface —
  `SELECT`/decode via `_decrypt_overrides_column` before the `try:`,
  `UPDATE agents SET tool_overrides = ?, mcp_overrides = ? WHERE name = ?`
  loop added inside the same `try:` as the other four UPDATE loops (only
  DML issued between the first SELECT and `commit()`); docstring updated
  to "ALL FIVE surfaces".
- Docs: `the_one/agents.md` ("Encryption rotation invariant" and
  "Encryption-rotation invariant" sections both updated to name the agents
  columns and, since the latter was already stale on the fourth
  `llm_providers.secrets` surface, corrected to list all five corpora
  accurately; new "Agent override secrets storage" section beside "Tool
  config secrets storage"), `SECURITY-MODEL.md` Secrets (new bullet),
  `rotate_encryption_key` docstring (five-surface count), `CLAUDE.md`
  (new one-line watch-out beside the `__MASKED__` note).
- Tests: extended `tests/test_db_repositories.py` (new
  `agent_store_encryptor` fixture, `agent_store` now built with it
  explicitly; AC1/AC2 ciphertext, legacy-plaintext, `{}`/`None`-fidelity,
  corruption, empty-string, and constructor-default-encryptor tests),
  `tests/test_db_api.py` (per-endpoint response-text regression net for
  all six agent-config returns, non-secret-stays-clear test, full
  preserve-on-PUT matrix incl. partial-header per-inner-key resolution,
  masked-with-nothing-stored drop, Studio-shaped PUT, `mcp_overrides:
  null` PUT, POST mask-drop, detach-does-not-clear-overrides),
  `tests/test_agent_tool_overrides_round_trip.py` (`{}`-vs-`None` fidelity
  for both columns through the API, incl. the merge-collapse-to-`None`
  edge case), `tests/test_mcp_overrides.py` (marker-set regression test),
  `tests/test_provider_api.py::TestEncryptionRotation` (agent-overrides
  rotation, legacy-plaintext-agent-row normalization, NULL-stays-NULL,
  commit-patch rollback, and a placement test that fails specifically on
  the `UPDATE agents` statement to prove it sits inside the shared
  `try:`).

#### Notes
- Full unit lane (`scripts/run-tests.sh tests/ -m 'not browser and not live
  and not pixel and not requires_bwrap and not discord_hat' -x --timeout
  30 --tb=short`): **4288 passed, 10 skipped, 676 deselected** in 366.45s.
  `ruff check the_one/ tests/` and `ruff format --check the_one/ tests/`
  both clean.
- Deviation from the leg's Implementation Guidance point 4 wording: the
  guidance's literal snippet (`data["mcp_overrides"] =
  _merge_preserved_mcp_credentials(data.get("mcp_overrides"),
  existing.mcp_overrides)`, unconditional) was followed as written for
  `update_agent`, but a type guard (`incoming_overrides is None or
  isinstance(incoming_overrides, dict)`) was added around the call so a
  malformed non-dict/non-null `mcp_overrides` (e.g. a list) still falls
  through to `AgentConfig.model_validate` for a 422 instead of raising
  inside the merge helper (`set(incoming)` on a list). Same guard applied
  to `create_agent`.
- Confirmed Anomaly A10 (circular import on a fresh-process
  `the_one.db.repositories` import) pre-exists on the base commit and is
  unaffected by this leg's additions (`the_one.config`,
  `the_one.encryption` are leaf modules) — reproduced directly, matches
  the existing flight-log entry; no new action needed here.
- `the_one/agents.md`'s "Encryption-rotation invariant (three corpora)"
  section was already stale before this leg (missing the M19
  `llm_providers.secrets` fourth surface that the code and the
  `rotate_encryption_key` docstring already covered). Corrected it to
  five corpora while adding the agents columns, rather than leaving a
  known-inaccurate count in place — noted here since it's a
  broader-than-strictly-required doc fix.

---

### self-configuration-surface-read
**Status**: landed
**Started**: 2026-08-24 19:40 CDT
**Completed**: 2026-08-24 22:20 CDT

#### Changes Made
- `the_one/api_credential.py`: `LocalApiCredential.parse`/`encode` gained a
  `prefix` keyword defaulting to `CREDENTIAL_PREFIX` — every existing call
  site (no prefix passed) is byte-identical; the self-configuration
  surface passes `AGENT_CREDENTIAL_PREFIX` ("agt").
- `the_one/self_configuration/` (new package): `constants.py` (leaf —
  `MOUNT_PATH`, `CONFINED_SOURCE_PATHS`, `AGENT_CREDENTIAL_PREFIX`,
  `CREDENTIAL_SECRET_KEY`), `credentials.py`
  (`SelfConfigurationCredentialSource`, the in-memory
  identifier→(source_id, secret) registry, `register`/`unregister`/
  `source_id_for`/`load_from_rows`/`credential_from_header`/
  `register_credential_source_once`), `surface.py` (the stateless
  `FastMCP` instance, `get_my_configuration`/`describe_my_capabilities`
  tools, `_calling_agent` — the first production reader of
  `CALLER_SCOPE_KEY` — and `list_surface_tools`), `projection.py`
  (`build_get_my_configuration`/`build_describe_my_capabilities`, pure
  functions over repositories, LD5's field lists verbatim), `manage.py`
  (`enable`/`disable`/`status`/`reconcile_on_startup`/`cascade_rename`/
  `cascade_delete`/`reject_foreign_surface_attachments`/
  `reject_surface_credential_overrides`, plus `is_surface_row`/`owner_of`/
  `surface_url`/`find_surface_row`).
- `the_one/interfaces/web/middleware.py`: `CredentialGateMiddleware`
  imports `CONFINED_SOURCE_PATHS` from the new leaf constants module;
  `_handle_http` refuses (403) a confined-source caller whose path
  doesn't start with its mapped prefix; `_handle_websocket` refuses every
  upgrade from a confined source outright. New `_send_403` helper. `file`
  and `session` sources are untouched (not in the map).
- `the_one/interfaces/desktop/shell.py`: `DesktopSession.run()` writes
  `settings.port = sel_port` immediately after `_select_port` resolves,
  on the branch that will actually serve (the `is_ours=True` early-return
  branch never reaches it — that path attaches to an existing window and
  runs no lifespan).
- `the_one/interfaces/web/app.py`: mounts the surface
  (`app.mount(MOUNT_PATH, surface.mcp.streamable_http_app())`) after the
  API router; `lifespan` wraps its entire body (not just the yield point)
  in a new `_self_configuration_session_scope()` helper that calls
  `session_manager.run()` **at most once per process** — a guard needed
  because the SDK's `StreamableHTTPSessionManager.run()` raises if
  entered twice on one instance, and the unit-test suite cycles
  `TestClient(app)` (and therefore `lifespan`) hundreds of times in one
  pytest process, while a real server process enters `lifespan` exactly
  once. Startup calls `register_credential_source_once()` then
  `manage.reconcile_on_startup(mcp_repo)` right after
  `migrate_json_to_sqlite`. Shutdown evicts every marked row's pool
  entries (`_evict_all_for_source`) **before** `_mcp_pool_shutdown_drain()`
  — see Notes on whether this eliminated the probe's WARNING.
- `the_one/interfaces/web/api.py`: three new endpoints (`GET`/`POST`/
  `DELETE /api/agents/{name}/self-configuration`); `list_mcp_sources`
  gained `include_agent_surfaces` (default omits marked rows);
  `update_mcp_source` 409s on a marked row; `delete_mcp_source` routes a
  marked row through `manage.disable` instead of the ordinary
  cache-cleanup delete path; `create_agent`/`update_agent` run the
  ownership guard and the credential-override guard on the validated
  config, after Leg 1's `mcp_overrides` merge; `rename_agent` cascades
  the marker; `delete_agent` cascades the deletion.
- Studio: `studio/self-configuration-tab.js` (new — enable/disable
  control + status line, modelled on `general-tab.js`); `agent-editor.js`
  gained the sixth tab (`data-tab-id="self-configuration"`,
  `data-testid="tab-self-configuration"`) and its panel; `studio.js`
  whitelisted the new hash-route tab, changed the editor's
  `fetchMcpSources()` to pass `?include_agent_surfaces=1` (the admin
  grid's separate `fetchMcpSources_()` is untouched), and added the
  enable/disable network calls plus a re-fetch-and-`doSelect()` refresh
  so the MCPs tab reflects the change without a reload; `mcps-tab.js`
  filters marked rows to the owning agent's own (create-mode: none) and
  renders that one row's attach toggle checked+disabled with a
  "managed on the Self-configuration tab" hint — the per-tool checkboxes
  beneath it stay fully editable. `index.html` gained the new script tag.
- Tests (new): `tests/test_self_configuration_api.py` (21 tests — AC1,
  AC2, AC4, AC9, AC10, AC11 — the `tests/test_db_api.py::client`
  fixture shape), `tests/test_self_configuration_projection.py` (8 tests
  — AC6, AC7, assertions on serialized result text), 
  `tests/test_self_configuration_surface.py` (7 tests — AC3, AC4's DD9
  in-tool-refusal half, AC8 — a real `uvicorn.Server` on an OS-allocated
  port in-process, mirroring the re-entrancy probe's mechanism; a fresh
  `FastMCP` instance per test via `importlib.reload` since the SDK's
  session manager is once-per-instance and the process-wide app singleton
  is long since consumed by the unit suite by the time this file runs),
  `tests/browser/test_studio_self_configuration_tab.py` (3 tests — AC12).
  Extended: `tests/test_api_credential.py` (+4 tests for the `prefix`
  kwarg), `tests/test_credential_gate.py` (`TestConfinedSourceScoping` —
  8 tests, the AC5 matrix), `tests/test_desktop_shell.py` (+2 tests for
  the port write-back), `tests/browser/test_flow_agent_tabs.py`
  (`test_tablist_renders_with_five_tabs` renamed
  `test_tablist_renders_with_six_tabs`, `assert to_have_count(5)` → `(6)`,
  plus the new `tab-self-configuration` assertion; the pre-existing
  `test_home_end_jump_to_first_last` updated — End now lands on the new
  last tab). Also fixed two pre-existing lock-tests that count
  static-asset references / documented testids and were correctly (not
  spuriously) tripped by the new script tag and the new `data-testid`s:
  `tests/test_index_asset_cache_busting.py` (61→62) and
  `docs/ui-testid-registry.md` (six new literal/prefix rows).
- Docs: `SECURITY-MODEL.md` (new "Self-configuration surface" subsection
  under Authentication — the confinement mechanism, the ownership guards,
  the indirect-prompt-injection residual risk explicitly deferred to
  Flight 2; a bullet under Secrets), `the_one/agents.md` (new
  "Self-configuration surface contract" section — module map, the
  ownership marker, the gate-confinement mechanism, the startup sequence
  and the once-per-process session-manager guard, the tool-name-length
  discovery, LD6's cache population), `CLAUDE.md` (operator-facing
  paragraph: the sixth tab, off by default, read-only this flight).

#### Notes
- Full unit lane (`scripts/run-tests.sh tests/ -m 'not browser and not
  live and not pixel and not requires_bwrap and not discord_hat' -x
  --timeout 30 --tb=short`): **4344 passed, 10 skipped, 679 deselected**
  in 372.5s (~6:13). `ruff check the_one/ tests/` and `ruff format --check
  the_one/ tests/` both clean. Browser lane (the two files named in
  Verification Steps — `tests/browser/test_flow_agent_tabs.py
  tests/browser/test_studio_self_configuration_tab.py`, run via
  `scripts/run-tests.sh -m browser <files>`): **15 passed, 1 skipped**
  (the pre-existing, unrelated skip) in 27.3s. The browser lane **did**
  run in this environment — Playwright + Chromium were already installed;
  no environment-capability caveat to record.
- **Stateless mode held throughout.** Every real-network test
  (`test_self_configuration_surface.py`'s five-plus tests, each driving a
  genuine loopback round trip through `MCPToolProvider.get_tools_for_agent`
  / `_pool.acquire` / the SDK's streamable-http client) passed with
  `FastMCP(stateless_http=True, ...)` as specified in LD4 — the stateful
  fallback the leg reserved was never needed.
- **Shutdown-drain WARNING: mitigation implemented per Implementation
  Guidance #6, not empirically re-verified against the probe's specific
  log line.** `app.py`'s lifespan now evicts every marked row's pool
  entries before `_mcp_pool_shutdown_drain()`, which — per the ordering
  the probe's Constraint 2 names — should let a loopback session
  terminate while the listener is still up rather than after it closes.
  However, the dedicated real-server tests in
  `test_self_configuration_surface.py` build their own minimal test app
  (with its own simplified lifespan, not `app.py`'s) so they do not
  exercise `app.py`'s actual shutdown path with a warm pool connection
  present; no test asserts the WARNING's absence in a live full-app
  shutdown. Recorded as an accepted, reasoned mitigation rather than a
  proven fix — a future leg or a squawk should add a direct repro if this
  needs closing definitively.
- **Real end-to-end round trip proven, not just unit-tested.**
  `test_self_configuration_surface.py` spins a genuine `uvicorn.Server` on
  an OS-allocated port in-process (mirroring the re-entrancy probe's own
  mechanism) and drives `AgentFactory.create()` / `MCPToolProvider
  .get_tools_for_agent()` against it with the row's `_cache` cleared
  first, forcing the real acquire+list_tools path rather than the
  cache-first hydrate. This is the strongest evidence for AC3's "not
  merely that a mint function exists" bar, and also caught a real,
  pre-existing, out-of-scope discovery (next bullet).
- **Discovery (logged, not fixed): the 64-char MCP tool-name ceiling
  interacts with the surface row's name template.**
  `mcp__{normalized_source_name}__{tool_name}` for a row named
  `self-configuration (<agent name>)` exceeds 64 characters (silently
  dropping the offending tool, per the existing per-tool ceiling guard)
  once the agent name is roughly 12+ characters for
  `describe_my_capabilities`, or roughly 16+ for `get_my_configuration`
  too. Found via a real failure in this leg's own surface test (an agent
  named `gate-stamp-agent`, 17 chars); fixed in the test by using shorter
  agent names, NOT in production code — this is a property of the
  existing, generic MCP tool-naming scheme (`the_one/mcp/_tool.py`),
  unrelated to this leg's own logic, and out of this leg's scope per the
  Post-Completion Checklist's "out-of-scope discoveries → Anomalies, not
  fixed" rule. See the Anomalies entry below.
- **Two test-isolation bugs found and fixed during implementation, both
  pre-existing-pattern-adjacent but newly exposed by this leg's code:**
  (1) `register_credential_source_once()`'s first implementation used a
  simple boolean flag; `tests/test_credential_gate.py`'s per-test
  isolation fixture wholesale-replaces `api_credential._sources` around
  every test (including ones that drive the real app's lifespan via
  `TestClient`), which silently orphaned the flag from the list it was
  guarding the moment such a swap happened after a real registration —
  the self-configuration credential source would then never resolve for
  the rest of the process. Fixed by checking ACTUAL LIST MEMBERSHIP
  instead of a flag (self-healing across any number of such swaps); this
  is now how `credentials.py` describes its own idempotency contract.
  (2) A `FastMCP` instance's `StreamableHTTPSessionManager.run()` is
  once-per-instance; `test_self_configuration_surface.py`'s
  `importlib.reload(the_one.self_configuration.surface)` mutates the
  shared module object IN PLACE, so it must reload the module AGAIN at
  fixture teardown — otherwise the NEXT lifespan cycle anywhere in the
  process (the real app's own first-ever cycle, or another test) would
  try to `.run()` an already-consumed session manager and crash. Both
  fixes are in the delivered test files, not workarounds outside them.
- Deviation from the leg's Implementation Guidance wording: step 6 says
  to evict marked rows' pool entries before `_mcp_pool_shutdown_drain`
  "if that removes the probe's DELETE warning (verify; otherwise
  document)" — implemented but the "verify" half is unmet (see the
  Notes bullet above); documented per the "otherwise document" fallback.
- AC9's "each credential's `get_my_configuration` returns its own row and
  never the other's" and "agent B's MCPs tab does not list A's row" are
  covered by construction (one credential resolves to exactly one
  registry entry to exactly one row to exactly one agent's config; the
  MCPs-tab filter is a three-line, directly-inspectable predicate keyed
  on `config.self_configuration.agent === agent.name`) and by the
  server-side ownership-guard tests (`TestOwnershipGuard`, 3 tests), but
  this leg did not add a dedicated two-agent-simultaneously browser or
  API test isolating "own row only, never the sibling's" end to end.
  Ticked AC9 on the strength of the server-side enforcement (the actual
  security boundary) plus code inspection of the client-side filter;
  flagging the gap here rather than silently.

---

### self-revision-write-path
**Status**: landed
**Started**: 2026-08-24 22:25 CDT
**Completed**: 2026-08-25 00:15 CDT

#### Changes Made
- `the_one/self_configuration/pending.py` (new): the in-process `next_turn`
  deferral registry — `record(agent_name, *, system_prompt=None,
  description=None)` (merges into any existing entry), `apply_pending_revision
  (agent_name, agent) -> bool` (pops the entry, mutates `agent.system_prompt`
  and replaces `agent.messages[0]` with a fresh `Message.system(...)` — never
  touches the rest of `agent.messages`), `clear_for_test()`. Logs at INFO with
  agent name, revised field(s), and a per-agent-per-process revision count
  (LD5's "at least visible" loop-detection line).
- `the_one/self_configuration/surface.py`: two new `@mcp.tool()` write tools,
  `update_my_description` / `update_my_system_prompt` (`text`, `apply` only);
  `_validate_write_input` (LD5 bounds — non-empty `str`, ≤ 64 KiB UTF-8-encoded,
  `apply ∈ {"next_turn","next_session"}`, else a plain `ValueError` — the
  module's one error mechanism, same as `_calling_agent`'s `PermissionError`);
  `_apply_revision` (persist via `store.load → model_copy → store.save`, then
  `pending.record(...)` iff `apply == "next_turn"`, returns LD4's truthful
  result shape).
- `the_one/self_configuration/manage.py` (LD7 / closes Anomaly A11):
  `SURFACE_ROW_NAME_TEMPLATE` → `SURFACE_ROW_NAME = "self-configuration"` (no
  more per-agent formatting); `enable()` uses the constant; `cascade_rename`
  narrowed to the ownership marker only (row name never changes); `reconcile_
  on_startup` gained a required `agent_store: SQLiteAgentStore` parameter and
  now runs UNCONDITIONALLY for every marked row on every startup: rewrites
  `_cache.tools` from `surface.list_surface_tools()` (LD6), renames a
  legacy-template row to the constant and migrates the owner's
  `mcp_overrides[old_name]` entry to the constant key via the new
  `_migrate_override_key` helper (skip + log if the constant key is already
  taken), persisting only when something actually changed.
- `the_one/interfaces/web/app.py`: imported `pending` as
  `_self_configuration_pending`; wired `apply_pending_revision(session.
  agent_name or "default", session.agent)` at exactly two sites — inside
  `_process_and_broadcast`'s `if not paused:` block (before its `done`
  broadcast) and inside `_resume_paused_session`'s `if not re_paused:` block
  (before ITS `done` broadcast, not the unconditional tail after it); updated
  the lifespan's `reconcile_on_startup` call to pass the existing `store`.
- `the_one/interfaces/web/api.py`: new `_reject_reserved_surface_name(source)`
  helper (409 when a non-surface source's name equals the constant); called
  from `create_mcp_source` (after `model_validate`, before
  `_validate_mcp_source_config`) and `update_mcp_source` (after the merge,
  which by that point is guaranteed non-surface since a marked-row PUT is
  already refused earlier in the function).
- `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js`: `_slugify`'s
  regex widened from `[^a-z0-9]+` to `[^a-z0-9_-]+` so it agrees with the
  backend's `mcp/_tool.py:_normalize_source_name` for the reserved constant
  (see Deviations/Discoveries below) — cosmetic (tooltip label only), not a
  gating-path change.
- Tests: `tests/test_self_configuration_write.py` (new, 25 tests — AC1–AC7,
  the two settle-hook sites via `_process_and_broadcast`/
  `_resume_paused_session` driven directly with stub agents, LD7's fixed
  tool-name-length and `_slugify` parity pins); `tests/test_self_configuration
  _api.py` (extended — LD7 name-literal updates at three existing call sites,
  the rename-cascade test rewritten for "marker only, name stays constant",
  three new `TestAC8bReservedName` tests, three new reconcile tests
  covering AC8's cache-refresh and LD7's rename/override-key migration incl.
  the skip-when-taken branch, `reconcile_on_startup` call sites updated for
  the new `agent_store` parameter); `tests/test_self_configuration_surface.py`
  (fixture's `reconcile_on_startup` call updated; one hardcoded row-name
  literal updated to the constant).
- Docs: `SECURITY-MODEL.md` ("Self-configuration surface" — the tool catalog
  bullet now names all four tools and a new bullet describes the write path;
  the indirect-prompt-injection bullet rewritten from a deferred risk to a
  LIVE one, with the per-tool-checkbox / disable-surface mitigation named as
  the only control until Flight 2); `the_one/agents.md` ("Self-configuration
  surface contract" — module map updated for `pending.py` and the four-tool
  `surface.py`, the tool-name-length paragraph rewritten to record LD7's
  closure of Anomaly A11, new "Write path and deferral contract" subsection
  covering persist-first/defer-second, the `_run_iterations` re-binding
  hazard that makes the deferral necessary, the exact two hook call sites and
  the `or "default"` normalization, merge/consumption semantics); `CLAUDE.md`
  (the self-configuration paragraph rewritten to name all four tools and the
  `apply` semantics, no longer says "read-only").

#### Notes
- Full unit lane (`scripts/run-tests.sh tests/ -m 'not browser and not live
  and not pixel and not requires_bwrap and not discord_hat' -x --timeout 30`):
  **4375 passed, 10 skipped, 679 deselected** in 370.18s (~6:10) — exactly
  +31 over Leg 2's 4344 (25 new in `test_self_configuration_write.py`, 6 new
  in `test_self_configuration_api.py`), no regressions elsewhere. `ruff check
  the_one/ tests/` and `ruff format --check the_one/ tests/` both clean.
- Browser lane (`tests/browser/test_studio_self_configuration_tab.py
  tests/browser/test_studio_mcps_tab.py`, run via `-m browser`): **11 passed**
  (3 + 8) in ~25s, 0 skipped, 0 failed. The lane **did** run in this
  environment.
- AC10 start/stop check: `THE_ONE_DATA_DIR=<scratch> THE_ONE_PORT=<OS-
  allocated free port> .venv/bin/the-one serve`, health-checked (`GET
  /api/live` → 200), `SIGTERM`'d, log read. Reproduced twice (once mid-
  implementation, once at wrap-up), both clean: `StreamableHTTP session
  manager started` → `Uvicorn running` → (after SIGTERM) `Shutting down` →
  `StreamableHTTP session manager shutting down` → `Application shutdown
  complete` → `Finished server process`. No session-manager `RuntimeError`
  (the once-per-process guard was not exercised twice in a single process
  here, so this only confirms the clean-shutdown shape, not the guard's
  double-entry branch — that is covered by the unit suite's `TestClient`
  cycling instead). **No shutdown-drain WARNING observed in either run** —
  expected and NOT new evidence for Leg 2's open item: no agent had the
  surface enabled in this bare server, so no marked-row pool entry existed
  to warn about. Leg 2's caveat (the mitigation is reasoned, not proven
  under a LIVE pool connection at shutdown) stands; this leg's check
  reconfirms only the start/stop shape.
- **Discovery, fixed in this leg (not a new out-of-scope anomaly): `mcps-
  tab.js`'s `_slugify` disagreed with `mcp/_tool.py`'s
  `_normalize_source_name` for the reserved constant.** `_normalize_source_
  name("self-configuration")` preserves the hyphen (`[a-zA-Z0-9_-]` is the
  allowed set); the JS `_slugify`'s original regex (`[^a-z0-9]+` → `_`)
  collapsed it to `self_configuration`. Found while writing the LD7 parity
  test the spec calls for. Impact was cosmetic only — `prefixedName` in
  `mcps-tab.js` feeds a `title` tooltip attribute, never the actual
  override key or dispatch path (both key on raw `source.name`) — but a
  wrong tooltip is still wrong, and the disagreement would have affected
  ANY hyphenated source name, not just this constant. Fixed by widening the
  JS regex to `[^a-z0-9_-]+`, which passes hyphens/underscores through
  unchanged; pinned by a new unit test asserting parity for the constant.
- Deviation from LD7's literal wording: the guidance names `manage.py`'s
  constant only as "the constant `self-configuration`" without prescribing
  a name; kept it in `manage.py` as `SURFACE_ROW_NAME` (module already owned
  the prior `SURFACE_ROW_NAME_TEMPLATE`) rather than adding a second,
  differently-scoped constant to `constants.py` alongside the existing
  `SOURCE_NAME` (the credential-source name for gate confinement, a
  different concept that happens to share the same literal value) — avoids
  conflating two constants that mean different things even though their
  string values currently coincide.
- No new out-of-scope anomalies found. Anomaly A11 (64-char tool-name
  ceiling colliding with the surface row's per-agent name) is CLOSED by
  this leg's LD7, not superseded — the row name is now a fixed constant for
  every agent, so the collision cannot recur. Anomaly A10 (circular import
  on a fresh-process first-touch of `the_one.db.repositories`) remains
  open, unaffected by this leg's additions, and unchanged from Leg 1/Leg 2's
  characterization — still pending its squawk at flight end.

---

## Decisions

*(runtime decisions not in the original plan)*

### D1 — Agent override columns join the encryption-rotation transaction
**Context**: DD5 stated `Encryptor.rotate_key` has no production caller. That is
literally true and practically wrong: `POST /api/encryption/rotate`
(`api.py:rotate_encryption_key`) re-encrypts four corpora inline without calling
`rotate_key`. A fifth encrypted column outside that transaction is orphaned the
first time the operator rotates.
**Decision**: Leg 1 adds `agents.tool_overrides` / `agents.mcp_overrides` as the
fifth rotated surface, inside the same `try:` block so rollback covers it.
**Impact**: Leg 1 scope grows by one SELECT/UPDATE pass and two doc sections;
Flight 3's credential store must do the same when it lands.

### D2 — Agent columns get their own decode; `_decrypt_secrets_blob` is not reused
**Context**: DD5 said the shared helper "treats undecryptable input as plaintext".
It returns `{}` on `InvalidToken` (`repositories.py:_decrypt_secrets_blob`) —
correct for a `'{}'`-defaulted column, destructive for agent rows whose legacy
plaintext is real operator data.
**Decision**: `_decrypt_overrides_column` parses legacy plaintext on
`InvalidToken`; corruption (non-JSON) still raises.
**Impact**: No data migration, and no silent loss of pre-leg overrides.

### D3 — Mask three `mcp_overrides` keys; encrypt both columns; leave `tool_overrides` values clear
**Context**: The mission asked for a concrete list of unsafe-to-serialize fields.
The credential keys are exactly the `Substitute`-marked override-schema fields
(`env`, `headers`, `bearer_token`). `tool_overrides` has no credential today
(the only built-in `Substitute` field is `WebConfig.default_user_agent`), and
Studio's Tools tab reads its values back into the form.
**Decision**: Masked-key set is derived from the markers, not hand-listed.
`enabled_tools`/`disabled_tools` and all `tool_overrides` stay in the clear.
Both columns are encrypted at rest for parity.
**Impact**: Studio's existing round-trips are unaffected; a future `Substitute`
credential on an override schema is masked without an `api.py` edit.

### D4 — Preserve-on-PUT keys off omission and mask shape; explicit `null` clears
**Context**: Studio never sends credential keys; API callers may send masked
GET output back. Neither may silently wipe a stored credential (the defect DD5
names).
**Decision**: Per `(source, credential key)`: omitted or mask-shaped → keep
stored; explicit `null` → clear; other → overwrite. Detaching a source does not
clear its overrides.
**Impact**: Clearing a credential via the API requires an explicit `null`;
documented in `agents.md`.

### D5 — Per-agent credentials are admitted only to the surface path
**Context**: Mission 20's gate resolves any registered credential to an
identified caller and then admits it everywhere; per-route scope enforcement
was deferred "because it had no consumer". The re-entrancy probe confirmed the
gate yields operator-level identity. A per-agent `agt` credential admitted
everywhere would be a platform credential with a different prefix — the M20
debrief carry-forward names exactly this hazard.
**Decision**: a leaf constants map `CONFINED_SOURCE_PATHS` (credential-source
name → allowed path prefix) tells `CredentialGateMiddleware` which sources are
confined; a caller from a confined source is admitted only to HTTP requests
under its prefix, and every other path and every WebSocket upgrade is refused
with 403. `file` and the cookie channel's `session` are not in the map and are
admitted exactly as today. (The Leg 2 design review caught that an earlier
wording — "any source that is not `file`" — would have refused the session
cookie everywhere; corrected before implementation.)

### D6 — Surface rows share the constant name `self-configuration`
**Context**: Leg 2's Anomaly A11 — `MCPClientTool` silently drops prefixed
tool names over 64 chars, and the row template `self-configuration (<agent>)`
left ~11 chars of agent name before a surface tool vanished. In this flight's
path, and tighter once Leg 3 adds `update_my_system_prompt`.
**Decision**: the row name is the constant `self-configuration` for every
agent (no UNIQUE on `mcp_sources.name`; ownership is the marker; overrides are
per agent). Fixed in Leg 3 (LD7) rather than as a squawk, because the flight
must not continue over a silent capability loss in its own surface.
**Impact**: prefixed surface tool names are a fixed 48 chars; `cascade_rename`
touches only the marker; reconcile renames legacy rows.
**Impact**: One bounded change to Mission 20's middleware (adaptation criterion
checked: identity resolution itself still needs only `register_source`, so DD2
stays as designed). Flight 3's external clients inherit the same scoping.

---

## Deviations

*(departures from the planned approach)*

---

## Anomalies

*(unexpected issues encountered)*

### A10 — `the_one.db.repositories` fails as a first-touch import in a fresh process
**Observed**: Found by the Leg 1 design reviewer. `.venv/bin/python -c "import
the_one.interfaces.web.api"` on the clean base commit raises a circular-import
error: `repositories.py`'s `from the_one.agent.config import AgentConfig`
transitively re-enters `the_one.mcp._pool`'s `from the_one.db.repositories
import MCPSourceRepository` before the class is defined. Does not manifest in
`make test-unit` or the real entrypoints (other modules are imported first).
**Severity**: cosmetic (latent; no production path hits it)
**Resolution**: logged as **squawk 0003** (`squawks/0003-repositories-first-touch-circular-import.md`),
status `deferred` — out of this flight's scope. Leg 1's own additions
(`the_one.config`, `the_one.encryption`) are leaf modules and neither touch nor
worsen it.

### A12 — `next_session` does not reach an already-open conversation on reopen
**Observed**: Behavior test `agent-self-revision-propagation` (run
`2026-08-25-02-39-45`, 6/8 checkpoints pass). An agent's `next_session`
revision persists to the store (step 4 pass) and is honored by any conversation
built fresh afterward (diagnostic probe E: a brand-new conversation returned the
newly-stored sentinel on its first turn), but reopening the SAME conversation —
via an in-app rejoin (step 5, probe D2) OR a full hard browser reload with a
fresh WebSocket and `join` (probe D3) — does not rebuild that conversation's
in-memory agent from the stored row; it keeps serving the sentinel that was live
when the session object was created. The tool-result-echo confound is ruled out:
at step 5 the PELICAN instruction was present in conversation history yet the
reply carried no sentinel, so the model follows the live system prompt, not
history. `next_turn` propagation is correct (step 7 clean turn; `pending.py`
logged "applied pending system_prompt revision"). The secret-free read is correct
across steps 2/4/8.
**Severity**: degraded — mission success criterion 4 is half-met. `next_turn`,
new-conversation `next_session`, and the secret-free read all work; only
`next_session` into an already-open conversation is broken.
**RESOLVED — no product defect. DD7's premise holds.** Operator chose
"investigate and fix." Server-side instrumentation of `_restore_session`
(`app.py:1054`) proved the rebuild IS correct: on every WS `join`, and over both
`POST /api/chat` and the WebSocket path, the cached session's `.agent` is replaced
with a freshly-built agent whose `messages[0]` carries the current stored prompt
(reproduced deterministically with a mock agent and a real-LLM probe; the rebuilt
bt-agent held the edited prompt). The step-5/D1–D3 failures were a
**spec-observability confound**, not a propagation bug: the sentinel-in-reply
oracle is only reliably obeyed on the first turn of a FRESH conversation, because
inside an established conversation the model anchors on its own prior replies and
on the revision tool call's arguments (which necessarily carry the new prompt text
into context) more strongly than on a freshly-swapped system instruction — a real
model, asked outright to read its current instructions, still reported the old
sentinel while its live prompt held the new one. The instrumentation was reverted.
`next_session` into an already-open conversation is *applied at the agent level*
but not reliably *observable via reply sentinels* — a model-behavior property, not
a code defect. **Disposition: closed.** Fix was to the test/spec, not the product.
First run: `runs/2026-08-25-02-39-45.md`; corrected 8/8 re-run:
`runs/2026-08-25-14-13-57.md`.

### A13 — behavior-test spec confounds: tool-result echo and rebuild-vs-imitation
**Observed**: Both crew agents independently flagged (1) `update_my_system_prompt`'s
result echoes the full new prompt text into the same turn's visible transcript,
so a compliant model can emit the new sentinel that turn by imitating its own
tool output — making step 6's "must not end with WALRUS this turn" negative
unprovable as written; and (2) steps 5/6 rely on distinguishing "same object
rebuilt vs. not" and "real mid-turn swap vs. imitation" without stating the
disambiguating evidence in the Expected Results.
**Severity**: cosmetic (test-quality, not product) — but it gates trusting step 6
as a clean signal in future runs.
**Resolution**: RESOLVED — spec corrected 2026-08-25. The confound is deeper
than the tool-*result* echo: the revision tool *call's arguments* (the full new
prompt text) are inherently in the transcript, and the model also anchors on its
own prior replies, so any within-conversation sentinel assertion is confounded.
The corrected spec measures `next_session` via a fresh conversation (the only
unconfounded observable), drops the reopen-sentinel and mid-turn-negative
assertions (the latter is unit-test territory), and documents the discipline in a
new "Observability discipline" section. Re-run: 8/8 PASS.

### A11 — the 64-char MCP tool-name ceiling can silently drop a self-configuration tool for a longer agent name
**Observed**: Found by Leg 2's own `test_self_configuration_surface.py`
during implementation (an agent named `gate-stamp-agent`, 17 chars, lost
`describe_my_capabilities` from its tool list with a logged WARNING, not
an error). `MCPClientTool.__init__` (`the_one/mcp/_tool.py`) prefixes
every tool name as `mcp__{normalized_source_name}__{tool_name}` and, per
existing (pre-Leg-2) behavior, silently drops any tool whose prefixed
name exceeds 64 characters rather than failing the build. The
self-configuration surface row's name is `self-configuration (<agent
name>)`; normalizing spaces/parens to underscores, the budget works out
to roughly 11 characters of agent name before `describe_my_capabilities`
(25 chars) is dropped, and roughly 15 before `get_my_configuration` (21
chars) is dropped too.
**Severity**: functional but silent — an operator with a longer agent
name who enables self-configuration gets a partially- or non-functional
surface with no error anywhere, only a WARNING-level log line.
**Resolution**: CLOSED in Leg 3 (LD7 / flight Decision D6). The surface
row name became the constant `self-configuration` for every agent — the
row-name template was the shorten-the-template candidate fix named here.
Prefixed surface tool names are now a fixed 45–49 chars, comfortably under
the 64-char ceiling regardless of agent name; a unit test pins this. The
generic 64-char ceiling on *other* MCP sources is unchanged and remains a
property of the existing tool-naming mechanism, not tracked here.

---

## Session Notes

### Flight Director Notes

- **2026-08-24 — Flight start.** Phase file `.flightops/agent-crews/leg-execution.md`
  loaded and validated (Crew / Interaction Protocol / Prompts present). Flight
  moved `planning` → `in-flight` after ticking the pre-flight checklist; the
  one unticked prerequisite is the re-entrancy probe, which gates Leg 2, not
  Leg 1 — it will be run before Leg 2 design. Branch
  `flight/01-self-configuration-surface` created off `main` at `0e8278d`.
- **Leg 1 design.** Ground truth gathered by reading the store, the agent API
  endpoints, the rotation endpoint, the override schemas, Studio's collect/render
  paths, and the existing masking/round-trip tests. Three corrections to DD5
  surfaced (D1–D3 above) and were folded into the leg rather than deferred.
- **Leg 1 risk tier: HIGH.** Rationale: changes the stored shape of two
  columns (encryption at rest, lazy migration), widens a shared interface
  constructed at 39 sites, touches the key-rotation transaction, and is the
  security-sensitive fix the mission's Known Issue 1 depends on. A wrong leg
  here is data loss. Design review spawned (Developer, Sonnet).
- **Leg 1 design review: approve with changes.** Every substantive claim
  verified against code. Two citation errors fixed (AC6 test-file pointer →
  `tests/test_provider_api.py::TestEncryptionRotation`; `:723` dropped — it is
  `update_knowledge_base`). Reviewer's open question on the rollback test
  answered in the leg: both the precedent commit-patch test *and* an
  `UPDATE agents`-intercept placement test. Changes are citation-only, so no
  second review cycle. Leg 1 → `ready`. `[HANDOFF:review-needed]` emitted;
  implementation Developer spawned (Sonnet).
- **Leg 1 landed (1/3).** Developer reported 4288 passed / 10 skipped on the
  full unit lane, ruff clean, AC1–AC9 verified. One additive deviation (a type
  guard so malformed `mcp_overrides` still 422s) and one doc correction (the
  "three corpora" rotation section was already stale on the M19 fourth
  surface) — both recorded in the Leg Progress entry. Per the workflow, code
  review and commit are deferred to flight end; the tree stays uncommitted on
  the flight branch.
- **Leg 2 design.** Drafted while Leg 1 was in flight from read-only ground
  truth (credential seam, gate, pool, tool provider, Studio tabs, SDK), then
  finalised against the post-Leg-1 tree. Six leg decisions LD1–LD6; LD2 is
  recorded as flight Decision D5 because it touches Mission 20's middleware.
  Flight open question on `describe_my_capabilities` listing the surface itself
  resolved: yes.
- **Leg 2 risk tier: HIGH.** Rationale: a second credential source behind the
  gate (security-sensitive by definition), a behavioural change to
  `CredentialGateMiddleware`, a new mounted sub-app with lifespan coupling,
  ownership/attachment guards on the agent API, and a sixth Studio tab. A
  missed path check in LD2 would hand an agent a platform credential. Design
  review spawned (Developer, Sonnet).
- **Leg 2 design review: approve with changes.** High: LD2 as worded would
  have 403'd session-cookie callers (the cookie resolves to
  `source="session"`, not `file`) — corrected to a confined-source map, D5
  reworded. Medium: the desktop launcher's fallback port never reaches
  `settings.port`; pulled into Leg 2 as a one-line fix plus test rather than
  deferred. Suggestions adopted: stateless GET edge case corrected (no GET is
  sent without a session id), surface row's attach toggle locked on the MCPs
  tab, AC5 matrix as an internal go/no-go before mounting. Fixes are exactly
  the reviewer's recommendations and AC5's cookie→200 matrix nets a regression,
  so no second review cycle. Leg 2 → `ready`. `[HANDOFF:review-needed]`
  emitted; implementation Developer spawned (Sonnet).
- **Leg 2 landed (2/3).** Developer reported 4344 passed / 10 skipped on the
  full unit lane and 15 passed on the two browser files (the lane runs here),
  ruff clean, AC1–AC14 ticked with two honest caveats recorded in its entry
  (shutdown-drain warning not re-verified against the probe's log line; no
  dedicated two-agent-simultaneous test). Stateless HTTP held. Anomaly A11
  (64-char tool-name ceiling) found by its own surface test — disposition:
  in-path, fixed in Leg 3 as LD7 / D6.
- **Leg 3 design.** Drafted during Leg 2 from read-only ground truth (agent
  loop, settle sites, restore path, connector inbound), finalised against the
  landed Leg 2 modules. Key finding: contextvars do not cross the loopback
  hop, so the `next_turn` deferral is keyed by agent name and applied at the
  two non-paused settle sites in `app.py` (LD1), with persist-first semantics
  (LD2) making the flight's rebuild-before-exit question moot (LD3).
- **Leg 3 risk tier: HIGH.** Rationale: mutates the live agent's system
  message on the turn-settle path (lifecycle/state change), opens the write
  path to agent configuration (the mission's central risk), and carries the
  behavior-test acceptance. Design review spawned (Developer, Sonnet).
- **Leg 3 design review: approve with changes.** Three highs, all in-leg
  spec gaps with exact fixes: the resume hook must sit inside
  `if not re_paused:` (the tail after it runs on a re-pause — AC4 violation);
  `session.agent_name` is `None` for the default agent and must be normalized
  to `"default"` rather than skipped (else `next_turn` silently degrades for
  single-agent installs); the constant row name needs a reservation guard
  because override application is keyed by source name. Mediums adopted:
  `record()` merges, reconcile refreshes tools/name/override-key
  unconditionally, LD5 uses the module's single raise-to-`isError`
  mechanism. Fixes mirror the reviewer's recommendations verbatim, so no
  second cycle. Leg 3 stays `ready`. `[HANDOFF:review-needed]` emitted;
  implementation Developer spawned (Sonnet).
- **Leg 3 code landed (3/3 implemented; AC9 pending).** Developer reported
  4375 passed / 10 skipped on the full unit lane, 11 passed on the two
  browser files, ruff clean, AC1–AC8b and AC10 ticked. Two small
  discoveries folded in: `mcps-tab.js`'s `_slugify` needed a hyphen/underscore
  parity fix (found by the LD7 parity test), and the AC10 start/stop check
  ran clean but with no surface-enabled agent, so Leg 2's shutdown-drain
  caveat stays neither confirmed nor refuted (the behavior-test instance
  below has one — its shutdown log is checked at teardown).
- **Behavior test `agent-self-revision-propagation` — setup.** Scratch dev
  instance started via `THE_ONE_PORT=8485 THE_ONE_DATA_DIR=<scratch> make up`
  (never 8484); credential minted with `rotate-api-credential` against the
  scratch dir; Anthropic provider `anthropic-bt` seeded from the operator's
  `.env` key; agent `bt-agent` (`claude-sonnet-5`) created with a prompt free
  of the sentinel words; surface enabled via the new endpoint. Preconditions
  were performed by the Flight Director in the operator's absence and are
  recorded as such in the run log. **Apparatus**: the operator's preferred
  goldfinch MCP is not connected in this session; the crew's discovery falls
  back to chrome-devtools, which is the sanctioned fallback when goldfinch is
  unavailable. Noted for the operator.
- **Behavior test run — PARTIAL (6/8), one real defect surfaced.** Ran
  `/behavior-test agent-self-revision-propagation` in live two-agent mode
  (Executor+Validator, Witnessed pattern) against the scratch instance. PASS:
  1,2,3,4,7,8. FAIL: 5,6. The secret-free read and `next_turn` propagation are
  verified clean; `next_session` into an already-open conversation is broken
  (A12); step 6's negative is confounded by a spec-quality gap (A13). Two
  Orchestrator diagnostic probes (out-of-band store edit to a third sentinel,
  then in-app rejoin / hard reload / fresh conversation) isolated the defect from
  execution and spec artifacts. Run log committed at
  `tests/behavior/agent-self-revision-propagation/runs/2026-08-25-02-39-45.md`.
  Scratch dev instance (port 8485) torn down.
- **Flight HELD for operator decision.** Leg 3 AC9 is unmet; the flight is NOT
  landed. Per the workflow, a failing behavior test keeps the leg unlanded unless
  the operator accepts the failure as a known issue. Because A12 contradicts a
  flight design premise (DD7) and its root cause may lie in pre-existing shared
  session-lifecycle code rather than this flight's own, the disposition is a
  genuine operator decision (fix scope vs. land-with-known-issue vs. revisit
  criterion 4), not an autonomous fix. All code remains uncommitted on
  `flight/01-self-configuration-surface`; unit lane 4375 green, browser 11 green,
  ruff clean.
- **Investigation outcome — NO product defect; A12 closed.** Per the operator's
  "investigate and fix" choice, instrumented `_restore_session` on a scratch
  instance and reproduced the rejoin path deterministically (mock agent + real-LLM
  probe). The live agent IS rebuilt from the stored prompt on every join — DD7
  holds. The behavior-test failure was a spec-observability confound (model
  anchors on conversation history over a freshly-swapped system prompt; the
  sentinel oracle is only clean on a fresh conversation's first turn). Reverted
  the instrumentation, corrected the behavior-test spec (fresh-conversation
  observable + documented Observability discipline), and re-ran.
- **Behavior test re-run — 8/8 PASS** (`runs/2026-08-25-14-13-57.md`), Witnessed
  two-agent mode. Persistence, non-propagation-to-issuing-conversation,
  `next_session` (fresh conversation), `next_turn` (following turn), and the
  secret-free read all verified clean. Leg 3 AC9 met; all Leg 3 ACs checked.
- **Leg 3 landed (3/3). Flight complete on all criteria.** `next_turn`,
  `next_session` (new conversation), and the secret-free read satisfy mission
  criterion 4 and the flight's contributing criteria. `next_session` into an
  already-open conversation is applied at the agent level but not reliably visible
  via reply sentinels — a documented model-behavior property, not a defect.
  Proceeding to the flight-end code review (all three legs' changes reviewed
  together, still uncommitted) and then commit + PR.
- **2026-08-24 — Re-entrancy probe: PASS. DD1's premise holds.** A probe agent
  mounted a throwaway streamable-http MCP server on the *real* app object
  (`the_one.interfaces.web.app:app`, gate and origin middleware live) and drove
  the platform's own client path (`_pool.acquire()` → `MCPClient.connect()` →
  SDK `streamable_http_client`) from inside an HTTP handler and inside a
  WebSocket handler. `initialize` + `list_tools` + two `call_tool`s completed in
  ~45 ms in every variation; no deadlock. Mechanism: one asyncio loop, one
  thread; each client request is a fresh inbound connection uvicorn dispatches
  as its own task while the outer handler awaits. Negative controls behaved: no
  bearer → gate 401 → `MCPConnectionError` graceful-skip in 38 ms; sub-app
  mounted without its session-manager lifespan → `RuntimeError: Task group is
  not initialized`, a 500, not a hang. Versions: mcp 1.28.1, uvicorn 0.44.0,
  starlette 1.3.1, fastapi 0.136.0, httpx 0.28.1, anyio 4.13.0. Scratch script
  lives outside the repo; nothing under the tree was touched.

  **Constraints Leg 2 inherits from the probe** (carried into its design):
  1. The mounted MCP sub-app's lifespan never runs on its own — the-one's
     lifespan must wrap `session_manager.run()` around its body; `run()` is
     once-per-instance.
  2. `_mcp_pool_shutdown_drain` runs after the listener closes, so loopback
     sessions' DELETE termination logs a benign WARNING at shutdown — either
     accept it or evict loopback entries before the listener closes.
  3. Set the loopback source's cached `auth_posture` to `no_auth` so a 401 never
     triggers a DCR/OAuth attempt, and never route it through the
     Test-connection OAuth path (`_probe_auth_posture` would misreport `oauth`).
  4. **The gate resolves the operator's file credential to a single
     operator-level identity.** Per-agent identity (DD2) therefore requires
     registering the minted per-agent credentials (DD4) as a second source
     behind the gate's lookup seam so `resolve_caller` yields an agent-scoped
     caller — the probe used the operator credential and did not exercise that
     seam; it is Leg 2's central integration.
  5. FastMCP defaults `streamable_http_path="/mcp"`; a trailing slash on the
     source URL avoids Starlette's 307. Build the URL from `settings.port` at
     runtime, never persist a hardcoded port.
  6. With `_cache.tools` populated the provider skips `acquire()` at agent build
     and connects lazily on first `execute()` — same loop, same mechanism.

**Flight design** — Design decisions DD1–DD9 recorded in the flight spec. The
mission's pre-declared split point was evaluated against a counted survey and
**does not fire**: it required the transport enum to widen *and* the widening to
ripple into transport dispatch, the pool and the sandbox. DD1 avoids the widening
altogether, and A5 shows the pool carries no type dispatch regardless.

One scope shift from the mission's plan: DD1 makes a credential unavoidable on
the agent's own path, so credential minting moves from Flight 3 into Flight 1
(self-only, no operator UI). Flight 3 is correspondingly smaller but remains a
genuine boundary — it introduces the credential store as a secrets-bearing table
and settles the rotation semantics Mission 20 deferred.

- **Flight-end review** (Phase 2d) spawned over all uncommitted changes for the
  three legs together. Reviewer on **Sonnet**, not the crew's default Haiku:
  deliberate deviation given the security surface (credential gate change, a
  second credential source, at-rest encryption of agent overrides, the loopback
  auth-scoped MCP endpoint). Complies with the methodology rule "never Opus for
  the Reviewer." Single review + commit at flight end per the deferred-review
  workflow.

  **Flight-end review outcome: `[HANDOFF:confirmed]`, no blocking issues.** The
  Reviewer independently ran ~440 tests, confirmed ruff clean, and validated the
  security-critical paths (encryption/masking/rotation with the atomic-transaction
  placement test; gate confinement in both directions; DD9 refusal via a real
  client; `next_turn` mid-turn safety). Seven non-blocking findings; the
  worthwhile ones were applied before commit:
  - **[medium — security] Route-prefix bypass in the confinement check.**
    `CredentialGateMiddleware` used a bare `path.startswith(MOUNT_PATH)`, which
    would admit an `agt`-scoped caller to any sibling route sharing the string
    prefix (e.g. `/mcp/self-configuration-admin`). Fixed to a route-boundary
    check (`path == MOUNT_PATH or path.startswith(MOUNT_PATH + "/")`) with a
    dedicated test. No such route exists today; hardened before it could.
  - **[medium — coverage] `next_session` mechanism had no permanent test.** Added
    `tests/test_web_session_reaper.py::test_cached_session_rebuilds_agent_from_edited_stored_config`
    — a real `AgentFactory` + `SQLiteAgentStore` test proving a cached session's
    agent is rebuilt from an edited stored prompt on rejoin (converting the A12
    investigation into a durable, deterministic regression net independent of the
    LLM-driven behavior test).
  - **[low] `manage.status()` orphaned-row state untested** → added tests.
  - **[low] Studio tab copy** not updated for the write tools → corrected the
    consent surface. `__init__` docstring "two read tools" → four.
  - **[non-blocking, forward] `next_session`-into-open-conversation closed on
    narrative evidence only** — now backed by the regression test above.
  - **[non-blocking, deferred] shutdown-drain WARNING** never verified against a
    live pool connection at shutdown (see below); **two-agent isolation (AC9)**
    ticked on enforcement + inspection, no dedicated simultaneous e2e test.
  Documentation note (process, from the debrief): itemizing flight-end-review
  findings in the flight log — as this entry now does — should be standard, the
  same as leg-design-review findings; the first commit recorded only that the
  review ran.
