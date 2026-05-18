# Flight Log: Platform-Send Built-in Tool and Outbound Routing

**Flight**: [Platform-Send Built-in Tool and Outbound Routing](flight.md)

## Summary

In-flight as of 2026-05-18. Flight 4 lands the outbound side of the connector subsystem: platform-send built-in tool, system-prompt composition extension, and dispatcher visibility tagging. Execution is via `/agentic-workflow` — per-leg design review, batched implementation, single flight-end code review and commit.

---

## Flight Director Notes

### Branching strategy: stacked on F3

F4 branched from `flight/03-session-model-key-and-visibility` tip (commit `8d6b681`, the F3 debrief commit) rather than from `main`. Rationale: F3 is `completed` per its artifacts but its branch has not yet been merged to `main` (main is at `d2351c7` — F3's "planning → ready" commit only, without F3's implementation/landing/debrief commits). F4 requires F3's code (`Message.visibility`, `OPERATOR_VISIBILITY`, `dispatch_inbound`, the v16 schema, etc.) to be present in the working tree — stacking on F3's tip is the only path that makes F4's prerequisites satisfiable without merging F3 first.

When F3's PR eventually merges to main, F4 can rebase onto main; the resulting F4 PR will then carry only F4's own commits.

### Per-leg execution discipline

Per agentic-workflow protocol: each leg gets per-leg design review (Developer agent reviews the leg artifact against codebase state before implementation) but NO per-leg code review or commit. All uncommitted changes flow into a single Reviewer pass at flight end, followed by one commit. This matches the `/agentic-workflow` skill's "batch implement, single review and commit at the end of the flight" stance.

---

## Leg Progress

(Append per-leg entries as legs land.)

### Leg Progress: agent-config-and-protocol-widen (2026-05-18)

**Status**: landed (per agentic-workflow batched-review — `completed` flips at flight-end commit).

**What landed:**
- `the_one/agent/config.py:AgentConfig` gained `connector_account_ids: list[str] = Field(default_factory=list)`, mirror-positioned immediately after `mcp_source_ids`.
- `the_one/connectors/base.py` gained the `SendResult` frozen-slotted dataclass (`platform_message_id: str | None`, `details: dict[str, Any] = field(hash=False, compare=False)`), placed between `DoctorReport` and `ConnectorClient`.
- `the_one/connectors/base.py:ConnectorClient` Protocol widened with `async def send(self, target: OutboundTarget, content: str) -> SendResult` after `is_alive`; docstring updated to past-tense Flight-4 widening note.
- `the_one/connectors/__init__.py` re-exports `SendResult`; adds `PLATFORM_SEND_OK_PREFIX = "[platform-send-ok]"` next to `OPERATOR_VISIBILITY`; `__all__` extended with both.
- `the_one/connectors/_stub.py:StubClient` gained `async def send(target, content)` returning `SendResult(platform_message_id="stub-msg-id", details={})` and recording via `StubPlugin.record_outbound`. Honors `StubPlugin.send_should_raise` (new ClassVar, mirror of `connect_should_fail`). `StubPlugin.reset_for_test` extended to clear it.
- `the_one/connectors/README.md` §3: skeleton split into `HypotheticalPlatformClient` (`is_alive` + `send`) and `HypotheticalPlatformPlugin` (`connect` + `disconnect` + `doctor` + `normalize_session_key`). `doctor`'s error branch fixed to `status="failed"` (was invalid `"error"`); both branches now pass non-empty `message=`. Imports updated to include `OutboundTarget` and `SendResult`. §3 prose updated to reflect `ConnectorClient` is now 2 methods.
- `tests/test_connectors.py`: `_MinimalClient` gained `async def send`; new `test_client_missing_send_fails_check` mirrors `test_plugin_missing_method_fails_check`; `test_canonical_and_re_exports_resolve_to_same_object` extended to assert `SendResult` is-identity; new `test_send_result_is_hashable_despite_dict_field`, `test_send_result_accepts_none_platform_message_id`, and `test_platform_send_ok_prefix_constant`.
- `tests/test_config.py:TestAgentConfigConstruction` gained three tests: defaults-empty-list, round-trip, pre-F4-row deserialization.

**Test trajectory:** F3 baseline 1881 unit tests passing → leg 1 lands 1888 passing (+7: 3 in `test_config.py`, 4 in `test_connectors.py`; the existing `test_minimal_client_satisfies_protocol` continues to pass after `_MinimalClient` gained the `send` method). Full suite: 1888 passed, 4 skipped, 405 deselected, 2 warnings (pre-existing `test_ollama_models` `AsyncMockMixin` warning — not introduced by this leg). 0 regressions.

**Lint:** `docker exec the-one ruff check the_one tests` — All checks passed.

**Deviations:** None. Implementation followed the leg artifact's Implementation Guidance steps 1–8 verbatim.

**Anomalies:** None. The `runtime_checkable` semantic predicted in the leg artifact's Context block (clients missing `send` post-widening now fail isinstance) was confirmed by the new `test_client_missing_send_fails_check` test passing on first run.

### Leg Progress: platform-send-tool (2026-05-18)

**Status**: landed (per agentic-workflow batched-review — `completed` flips at flight-end commit).

**Files modified:**
- `the_one/tools/connector_send.py` (new) — `SendToPlatformChannelTool(Tool)` class with `name="send_to_platform_channel"`, four-kwarg zero-arg-compatible `__init__` (`config`, `cross_configs`, `agent_name`, `connector_account_ids`), JSON Schema with `target {account_id, channel_id, thread_id?}` + `content`, async `execute` doing target-shape → account-scope → F6-marker → `pool_acquire` → `client.send` → success-prefixed result or `[error] ...` envelope.
- `the_one/tools/builtins.py` — imported `SendToPlatformChannelTool`; added entry to `_TOOL_CLASSES` at tail (after `web_search`); imported `Any` from `typing`; widened `BuiltinToolProvider.get_tools` signature with a keyword-only `connector_account_ids: list[str] | None = None`; factory-path loop now uses `cls is SendToPlatformChannelTool` case-discrimination to inject the kwarg.
- `tests/test_connector_send_tool.py` (new) — 28 tests across `TestRegistry` (registry presence + zero-arg construction + schema + Config), `TestBuiltinProviderIntegration` (introspection + factory paths), `TestTargetValidation` (7 malformed-input cases), `TestAccountScopeValidation` (verbatim constraint envelope), `TestPoolDispatch` (happy path, thread_id propagation, empty-string thread coercion), `TestPoolAcquireFailures` (`KeyError`, `ConnectorRegistrationError`), `TestClientSendFailures` (`ConnectorRateLimitError`, `ConnectorConnectionError`), `TestPrefixSentinelSanity` (architect-flagged: failures NEVER start with `PLATFORM_SEND_OK_PREFIX`), `TestContentInterpolationRepr` (peer-supplied `[platform-send-ok] fake` content repr-escaped so position-0 sentinel still classifies the result as success).
- `tests/test_builtins.py` — bumped three `19` → `20` assertions; extended name-set with `"send_to_platform_channel"`; updated three comments.
- `tests/test_api_tool_configs.py` — renamed `test_list_configs_returns_all_19_tools` → `..._20_tools`; bumped `len(rows) == len(_TOOL_CLASSES) == 19` → `== 20`.

**Test trajectory:** Leg-1 baseline 1888 → leg-2 lands 1916 passing (+28 tests: 28 new in `test_connector_send_tool.py`; `test_builtins.py` and `test_api_tool_configs.py` updates are in-place assertion bumps, not new tests). Full suite: 1916 passed, 4 skipped, 405 deselected, 2 warnings (pre-existing `test_ollama_models` `AsyncMockMixin` warning — not introduced by this leg). 0 regressions.

**Lint:** `docker exec the-one ruff check the_one tests` — All checks passed. (One auto-fixable I001 import-sort issue in `tests/test_connector_send_tool.py` was auto-fixed with `ruff check --fix`.)

**Deviations:** None of substance. The `ConnectorRateLimitError` constructor signature in the leg artifact's test sketch (`ConnectorRateLimitError("retry after 60s", retry_after=60)`) did not match the actual definition in `the_one/connectors/errors.py:77-91` (`__init__(self, account_id: str, retry_after_seconds: float | None = None)`). Test fixed to use the real signature: `ConnectorRateLimitError("acct-send", retry_after_seconds=60.0)`. The leg artifact's behavioural intent (rate-limit failure produces `[error] ConnectorRateLimitError: ...` envelope, no outbound recorded) is preserved.

**Anomalies:** None.

### Leg Progress: factory-baseline-carveout-and-system-prompt (2026-05-18)

**Status**: landed (per agentic-workflow batched-review — `completed` flips at flight-end commit).

**Files modified:**
- `the_one/agent/config.py` — added `_CONNECTOR_TOOL_ENABLED_DIRECTIVE` and `_CONNECTOR_TOOL_DISABLED_DIRECTIVE` module-level string constants; added `compose_system_prompt(base, persona, *, connector_attached=False, send_tool_enabled=False) -> str` module-level free function; simplified `AgentConfig.get_system_prompt()` to delegate to `compose_system_prompt` with both connector flags = False. Non-connector callers see byte-identical output to the pre-F4 `{base}\n\n---\n\n{persona}` shape.
- `the_one/agent/factory.py` — widened import from `from the_one.agent.config import AgentConfig` to `from the_one.agent.config import BASE_PROMPT, AgentConfig, compose_system_prompt`; added `connector_attached` + `send_tool_enabled` flag computation after `disabled_names`; widened the `provider.get_tools(...)` call site to branch on `isinstance(provider, BuiltinToolProvider)` (passing `connector_account_ids=config.connector_account_ids` to builtin only); added F10 baseline carve-out block after the MCP tool loop (defensive `registry.tool_names` guard); replaced `system_prompt = config.get_system_prompt()` with the connector-aware `compose_system_prompt(...)` call using the new flags.
- `the_one/agent/core.py` — appended F4 (M10) carve-out sentence to the F10 L1 strict-baseline comment block at L30-34, documenting `send_to_platform_channel` as the second exception (after the search_tools/search_mcps merge) and pointing readers to the factory carve-out site and the paired prompt directive.
- `tests/test_config.py` — added `TestComposeSystemPrompt` class with 5 round-trip tests: non-connector empty persona, non-connector with persona, connector-attached + tool-enabled directive presence/absence, connector-attached + tool-disabled directive presence/absence, persona+directive ordering shape (`BASE_PROMPT < directive < "---" < persona`).
- `tests/test_factory.py` — imported `_CONNECTOR_TOOL_ENABLED_DIRECTIVE`, `_CONNECTOR_TOOL_DISABLED_DIRECTIVE`, `BASE_PROMPT`, and `BuiltinToolProvider`; added the `factory_with_builtin_tool_configs` fixture (yields a callable returning an `_Ctx` context manager with patches active during `factory.create()`, matching the patch-scope correctness of the existing `factory` fixture); added `TestConnectorBaselineCarveOut` (4 tests: carveout fires on attach+enabled, no carveout on no-connector / operator-disabled / per-agent-disabled), `TestConnectorSystemPrompt` (3 tests: non-connector base prompt, connector+enabled has enabled directive only, connector+disabled has disabled directive only), and `TestFactoryToolProviderWiring` (1 test: `BuiltinToolProvider` receives `connector_account_ids=["acc-1"]` while a non-builtin stub provider does NOT).
- `tests/test_agent_search_integration.py` — added an F4 (M10) L3 note comment inside `test_baseline_visible_at_session_start` pointing to the new carve-out tests in `tests/test_factory.py::TestConnectorBaselineCarveOut` and the prompt-composition tests in `tests/test_config.py::TestComposeSystemPrompt`. Assertion unchanged.

**Test trajectory:** Leg-2 baseline 1916 → leg-3 lands 1929 passing (+13 tests: 5 new in `test_config.py::TestComposeSystemPrompt`, 4 new in `test_factory.py::TestConnectorBaselineCarveOut`, 3 new in `test_factory.py::TestConnectorSystemPrompt`, 1 new in `test_factory.py::TestFactoryToolProviderWiring`). Full suite: 1929 passed, 4 skipped, 405 deselected, 2 warnings (pre-existing `test_ollama_models` `AsyncMockMixin` warning — not introduced by this leg). 0 regressions. `test_baseline_visible_at_session_start` continues to pass byte-identically (non-connector baseline preserved). Existing `TestGetSystemPrompt` 2 tests pass byte-identically after the `get_system_prompt` delegation refactor.

**Lint:** `docker exec the-one ruff check the_one tests` — All checks passed.

**Deviations:** One stylistic — the leg artifact's mandatory `_Ctx` fixture sketch used `self_` as the first argument of `__enter__`/`__exit__` to clarify it's the inner-class self vs the outer fixture closure. Ruff's `N805` lint rule flags this as a naming violation. Renamed to `self` (the inner class doesn't need the closure-vs-self distinction because all closed-over values — `tool_configs`, `extra_tool_providers`, `mock_repo`, `store` — are read directly from the enclosing scope, not via the outer `self`). Patch-scope semantics unchanged: `__enter__` starts patches, `__exit__` stops them, and the patches live for the duration of the `with` block (and therefore during `factory.create()`).

**Anomalies:** None.

### Leg Progress: dispatcher-visibility-tagging-and-now-iso-promotion (2026-05-18)

**Status**: landed (per agentic-workflow batched-review — `completed` flips at flight-end commit).

**Files modified:**
- `the_one/db/models.py` — renamed `_now_iso` → `now_iso` (public, no leading underscore); all 13 internal `Field(default_factory=_now_iso)` references updated to `now_iso`.
- `the_one/db/repositories.py` — deleted the shadow `_now_iso` def at the old L25-26; deleted the `from datetime import datetime, timezone` import (no longer used after the shadow's removal); extended the `from the_one.db.models import (...)` block with `now_iso`; all 10 call sites (L100, L179, L248, L389, L539, L633 ×2 on one line, L778, L800, L910) updated to `now_iso()`. Ruff auto-fixed the import-block ordering after the deletion (`ruff check --fix`).
- `the_one/connectors/_session.py` — deleted the NOTE block at old L37-41 and the `_utc_now_iso` def at old L42-43; extended the `from the_one.db.models import ChatSession, ConnectorAccount` import with `now_iso`; rewrote stale comments at L145 (`last_inbound_at = _utc_now_iso()` → `last_inbound_at = now_iso()`) and L172 (`_utc_now_iso writes UTC` → `now_iso writes UTC`); renamed the local variable at L183 from `now_iso = _utc_now_iso()` to `current_iso = now_iso()`; updated the 3 dependent call sites at L189, L190, L197 to use `current_iso`.
- `the_one/connectors/_inbound.py` — deleted the `_utc_now_iso` def at old L54-55; deleted the unused `from datetime import datetime, timezone` import at old L31 (sole consumer was the helper); added `from the_one.db.models import now_iso`; folded `OPERATOR_VISIBILITY, PLATFORM_SEND_OK_PREFIX` into the existing `from the_one.connectors import ... registry` line; updated the L171 call site to `now_iso()`. Added the post-step visibility-tagging block inside the per-session lock's `try:` body, after the `agent.step` async-iter loop and before `encode_messages`: captures `pre_step_len = len(agent.messages)` outside the try; builds `tool_call_names: dict[str, str]` from new assistant msgs' `tool_calls`; walks the new-msgs slice tagging visibility per the F4 L4 rules (USER skip; successful platform-send tool_result → `None`; everything else → `OPERATOR_VISIBILITY`).
- `tests/test_connectors_inbound.py` — inverted `test_dispatch_inbound_persists_agent_reply_with_visibility_none` → renamed to `test_dispatch_inbound_persists_agent_reply_with_visibility_operator`, assertion flipped to `assert m.visibility == OPERATOR_VISIBILITY`, docstring rewritten. Added a one-line F4 L4 note to `test_dispatch_inbound_persists_inbound_with_visibility_none` documenting the USER-skip rule (test continues to pass byte-identically). Added `OPERATOR_VISIBILITY`, `PLATFORM_SEND_OK_PREFIX` imports from `the_one.connectors`; added `ConnectorConnectionError` from `the_one.connectors.errors`; added `ToolCall` to the existing `the_one.llm.base` import. Widened `_seed_provider_and_agent` with a new `connector_account_ids` kwarg (passes through to the saved `AgentConfig`). Added `_ScriptedProvider(LLMProvider)` — a stateful test-only provider that returns pre-scripted `Message`s in sequence per `complete()` call (the leg artifact's recommended workaround for `MockProvider`'s statelessness, which would infinite-loop on canned tool_call responses). Added `_make_scripted_factory(...)` helper: builds an `AgentFactory` wired to a `_ScriptedProvider` via monkeypatched `factory_mod.get_provider`; optional `connector_account_ids` kwarg monkeypatches `SQLiteAgentStore._row_to_config` to re-inject the in-memory `connector_account_ids` field that the current `agents` schema does not persist (F4 L1 widened the Pydantic field only — no DB column added). Added 5 new tests: `test_dispatch_inbound_tags_assistant_text_as_operator` (plain-text reply default branch), `test_dispatch_inbound_tags_successful_send_tool_result_as_platform_visible` (carve-out fires on all-three predicate), `test_dispatch_inbound_tags_failed_send_tool_result_as_operator` (prefix-check branch fails for `[error] ConnectorConnectionError: ...` envelope), `test_dispatch_inbound_tagging_uses_tool_result_tool_call_id_correlation` (name-check guard against future mis-simplification to prefix-alone), `test_dispatch_inbound_continue_tool_call_is_operator_visible` (default branch for the agent's virtual `continue` synthesised tool_result).
- `tests/test_connectors_e2e_session.py` — updated `test_e2e_both_visibility_paths_coexist_in_session` to reflect F4 L4's dispatcher tagging: the assistant reply produced by `dispatch_inbound` now carries `OPERATOR_VISIBILITY` (was `None` under F3), so the operator-count assertion bumps from 2 to 3 (1 from dispatcher + 2 appended) and the peer-count assertion drops to `>= 1` (only the inbound USER message). Docstring extended with an F4 L4 update note explaining the behavior change.
- `tests/test_db_repositories.py:1019` and `tests/test_session_lifecycle.py:131` — stale comments mentioning `_now_iso` rewritten to `now_iso` (architect-flagged in design review for cross-file consistency).

**Test trajectory:** Leg-3 baseline 1929 → leg-4 lands 1934 passing (+5 tests: 5 new in `test_connectors_inbound.py`; the inverted-rename test stays at the same count). Full suite: 1934 passed, 4 skipped, 405 deselected, 2 warnings (pre-existing `test_ollama_models` `AsyncMockMixin` warning — not introduced by this leg). 0 regressions.

**Lint:** `docker exec the-one ruff check the_one tests` — All checks passed. One auto-fixable `I001` import-block ordering in `the_one/db/repositories.py` (post-`_now_iso` deletion the `now_iso` re-insertion into the `the_one.db.models` import block left it slightly mis-ordered) was auto-fixed with `ruff check --fix`.

**Deviations:**
- The leg artifact assumed the `AgentConfig.connector_account_ids` field round-trips through the DB. It does NOT — the `agents` table schema lacks the column, and `SQLiteAgentStore.save`/`_row_to_config` do not persist or read it (F4 L1 widened the in-memory Pydantic field only). This was discovered when the platform-send tool's account-scope check rejected the inbound dispatch with `[error] [constraint] account_id 'acct-test' is not attached to this agent`. Worked around by monkeypatching `SQLiteAgentStore._row_to_config` in the test helper to re-inject the field after the DB read. Production fix (schema migration adding a `connector_account_ids TEXT` column + `save`/`_row_to_config` JSON round-trip) is OUT OF SCOPE for L4 — flagged here for the flight debrief / F8 dependency review. Real Discord-driven inbound (F8) will need the persistence fix before connector accounts attached via the operator UI survive a process restart.

**Anomalies:**
- `_ScriptedProvider.__init__` accepts the `model`/`base_url`/`api_key`/`config` kwargs that the factory's `get_provider(...)` resolver passes through (mirrors `_BlockingProvider`'s shape at L207-249). Without these, the monkeypatched resolver would have raised `TypeError` on the `model=config.llm_model, base_url=..., api_key=..., config=...` call site at `factory.py:218-224`.
- Cross-leg interaction: F3's `test_connectors_e2e_session.py::test_e2e_both_visibility_paths_coexist_in_session` was authored as a regression net AROUND the F3-shipped behavior (dispatcher leaves assistant replies untagged), with the docstring explicitly noting "F3 contract proof that F5 inherits". F4 L4 by design changes that contract — the dispatcher now tags assistant replies as `OPERATOR_VISIBILITY` by default. Updating the test in-place (vs. inverting + renaming) was the right call here: the test's INTENT (peer + operator visibility coexist in one session, codec emits no `visibility` key for `None`-tagged messages) survives intact; only the bookkeeping counts shift. The state-machine reachability audit rule (a test that pins behavior the new state machine breaks must be inverted, renamed, or deleted as part of the leg) is satisfied because the counts ARE updated as part of this leg, not deferred.

### Leg Progress: e2e-tests-and-coverage-carry-forward (2026-05-18)

**Status**: landed (per agentic-workflow batched-review — `completed` flips at flight-end commit).

**Scope**: four sub-legs — (A) v17 schema migration closing the leg-4 `AgentConfig.connector_account_ids` persistence deviation; (B) six new e2e platform-send tests pinning F4's mission-mandated invariants + F1 debrief carry-forward; (C) extraction of the in-file connector-dispatch helpers to `tests/_connector_dispatch_helpers.py` (THIRD-consumer trigger per F3 debrief); (D) AsyncMock-warning verify-or-retire (sixth-consecutive-flight carry-forward).

**Files modified:**

*Sub-leg A — v17 migration (closes leg-4 deviation):*
- `the_one/db/schema.py` — `CURRENT_VERSION = 16` → `17`; new `if version < 17:` migration block adding `ALTER TABLE agents ADD COLUMN connector_account_ids TEXT` with the v8/v9/v10/v11/v14/v15 PRAGMA-guarded ALTER pattern; renumber comments at L547, L587 (v17 → v18 for Flight 8's CHECK migration).
- `the_one/db/repositories.py:SQLiteAgentStore.save` — extended INSERT column list, VALUES placeholder count (14 → 15), parameter tuple (added `json.dumps(config.connector_account_ids)`), and `ON CONFLICT DO UPDATE SET` block with `connector_account_ids=excluded.connector_account_ids`. Mirrors the `mcp_source_ids` handling.
- `the_one/db/repositories.py:SQLiteAgentStore._row_to_config` — added `connector_account_ids=json.loads(row["connector_account_ids"] or "[]")` to the `AgentConfig(...)` constructor (mirror of `mcp_source_ids` line; `or "[]"` defends against pre-v17 NULL rows).
- `the_one/db/_connector_types.py` — docstring v17 → v18 (Flight 8's CHECK migration renumbered); added v17 → `agents.connector_account_ids` (F4 L5) line.
- `the_one/agents.md:290` — connector-type checklist item 4 updated (v17 = F4 L5; v18 = F8 CHECK).
- `tests/test_db_migration.py` — `assert CURRENT_VERSION == 16` → `== 17` with updated error-message string citing F4 L5; TestSchemaV13/V14/V15/V16 docstrings renumbered v17 → v18; NEW `TestSchemaV17` class (3 tests: fresh-DB column presence, idempotent re-apply, legacy-v16-row decodes with empty list); hand-built schema fixtures in V14, V15, V16 tests extended with a v16-era `agents` table so the v17 ALTER target exists (ALTER-on-previously-untouched-table addendum per F3 debrief two-pass-planning convention).
- `tests/test_db_repositories.py` — 2 new tests: `test_save_round_trips_connector_account_ids` (covers INSERT and ON CONFLICT update branches), `test_load_pre_v17_agent_has_empty_connector_account_ids` (covers the NULL → [] back-compat path).

*Sub-leg B — e2e platform-send tests:*
- `tests/test_connectors_e2e_platform_send.py` (new) — 6 tests:
  1. `test_e2e_enabled_state_platform_send_delivers` — mission criterion #13: tool_call delivers; assistant tool_call message tagged OPERATOR_VISIBILITY; tool_result tagged visibility=None; loaded schemas include `send_to_platform_channel`; system prompt contains enabled-tool directive.
  2. `test_e2e_disabled_state_inbound_received_no_outbound` — mission criterion #14: no outbound; inbound USER persists peer-visible; assistant reply persists operator-only; tool absent from loaded schemas; system prompt contains DISABLED-tool directive substring.
  3. `test_e2e_disabled_to_enabled_re_dispatch_restores_outbound` — mission criterion #14 final clause: flipping `ToolConfigRepository.upsert(...enabled=True)` mid-test restores outbound on next inbound without re-configuring the connector account or restarting any session. Uses two separate factories because each `factory.create()` builds a fresh `_ScriptedProvider` instance; cross-dispatch response-index sharing isn't supported by the leg-4 helper shape.
  4. `test_e2e_target_validation_rejects_unattached_account` — mission criterion #15: the platform-send tool's account-scope short-circuit rejects targets whose `account_id` is not in the agent's attached set BEFORE invoking `pool_acquire`. Test patches `the_one.tools.connector_send.pool_acquire` to count per-account calls and asserts the wrong account never reached the pool.
  5. `test_e2e_pool_acquire_touches_last_activity_on_outbound` — F3 ratification's `last_activity` touch verification on the outbound path (the inbound-path equivalent lives in `test_connectors_inbound.py::test_dispatch_inbound_touches_pool_last_activity`).
  6. `test_e2e_plugin_resolve_failure_dispatcher_logs_and_returns` — F1 debrief carry-forward: covers the dispatcher's "deliberately redundant" plugin-resolve catch at `_inbound.py:143-152` by patching the dispatcher's MODULE-local `registry` binding (NOT the registry module's `resolve` function) with a fake whose `resolve` raises `ConnectorRegistrationError`. The pool's captured `_resolve_plugin` reference is unaffected — pool acquire succeeds, then the dispatcher's second resolve hits the patched code and raises. The catch is then exercised: the dispatcher logs at WARNING and returns cleanly; no new chat_sessions row is created.

*Sub-leg C — helper extraction:*
- `tests/_connector_dispatch_helpers.py` (new) — helper functions: `_seed_provider_and_agent` (with `connector_account_ids` kwarg — now persists naturally through sub-leg A's v17 column), `_seed_stub_account` (with `session_continuation_seconds` kwarg for F3 L6 needs), `_make_factory`, `_envelope`, `_ScriptedProvider` (stateful test-only LLM provider), `_make_scripted_factory` (no longer monkeypatches `_row_to_config` — the v17 column round-trip is real now).
- `tests/conftest.py` — `isolated_db` pytest fixture moved here for pytest auto-discovery (fixtures defined in non-conftest modules aren't auto-discovered). Helper FUNCTIONS stay in `_connector_dispatch_helpers.py` because function imports don't require auto-discovery. This matches the leg artifact's documented "fall back to defining the fixture in `tests/conftest.py` and the helper functions in `_connector_dispatch_helpers.py` separately" path; chosen on first lint pass to avoid F811 redefinition errors that the explicit-import approach triggered on every test function parameter.
- `tests/test_connectors_inbound.py` — removed the in-file `isolated_db` fixture + `_seed_provider_and_agent` / `_seed_stub_account` / `_make_factory` / `_envelope` / `_ScriptedProvider` / `_make_scripted_factory` definitions; now imports the helper functions from `tests._connector_dispatch_helpers` (the fixture is auto-discovered from conftest). Removed unused imports (`AgentConfig`, `aiosqlite`, `InboundEnvelope`, `LLMProviderConfig`, `LLMProviderRepository`, `SQLiteAgentStore`, `ensure_schema`). The leg-4 monkeypatch on `SQLiteAgentStore._row_to_config` is GONE — the helper's `connector_account_ids` kwarg flows through sub-leg A's persisted column.
- `tests/test_connectors_e2e_session.py` — removed in-file helper definitions; imports helpers from `tests._connector_dispatch_helpers`.

*Sub-leg D — AsyncMock-warning closure (FIX applied, not retired):*
- `tests/test_provider_api.py::TestModelDiscovery::test_ollama_models` — extended the F5 L01.5 short-circuit `with patch(...)` block to ALSO patch `the_one.interfaces.web.api.ollama_api.get_model_context_length` with `new_callable=AsyncMock, return_value=None`. The F6.5 L04 addition of a sibling `get_model_context_length` call in `list_provider_models` re-opened the AsyncMock-never-awaited warning surface that F5 L01.5 thought it had closed: the original F5 L01.5 patch covered only the capabilities-path show_model invocation; F6.5's context-length path also falls through to `show_model`'s mocked-incomplete `.post()` chain, which left auto-AsyncMock coroutines un-awaited. The new patch closes that path the same way. Verified clean under both `-W error::RuntimeWarning:unittest.mock` AND broader `-W error::RuntimeWarning` filters. Docstring not updated separately because the existing F5 L01.5 prose now reads correctly with the additional context — F4 L5's comment block above the new patch explains the additive nature.

**Test trajectory:** Leg-4 baseline 1934 → leg-5 lands 1945 passing (+11 tests: +3 in `TestSchemaV17`, +2 in `test_db_repositories.py`, +6 in `test_connectors_e2e_platform_send.py`). Full suite: 1945 passed, 4 skipped, 405 deselected, 1 warning. The leg-4 carry-forward "pre-existing AsyncMock warning" is GONE after sub-leg D — warning count dropped from 2 to 1 (the remaining warning is a pytest-asyncio teardown-loop `Event loop is closed` from aiosqlite's worker thread, unrelated to AsyncMock).

**Lint:** `docker exec the-one ruff check the_one tests` — All checks passed. Two auto-fixable `I001` import-sort issues in `tests/_connector_dispatch_helpers.py` and `tests/test_connectors_e2e_platform_send.py` auto-fixed with `ruff check --fix`. F811 redefinition errors initially surfaced from the explicit-import-of-fixture pattern but were eliminated by moving `isolated_db` to `conftest.py` (helpers stay in the dedicated module; only the fixture moves).

**Grep verifications:**
- `grep -n 'monkeypatch\.setattr.*_row_to_config' tests/` → ZERO matches (leg-4 monkeypatch workaround removed by sub-leg A's real persistence).
- `grep -n 'v17\|v18' the_one/ tests/` → coherent renumber: v17 universally = F4 L5 `agents.connector_account_ids`; v18 universally = F8's CHECK migration. No drift.

**Deviations:**
- The leg artifact's sub-leg C guidance suggested either splitting (fixture in `conftest.py`, helpers in `_connector_dispatch_helpers.py`) OR importing the fixture explicitly into each consumer file. The explicit-import path was tried first (it works at the pytest level — tests pass) but triggers ruff `F811 Redefinition of unused 'isolated_db'` on every test function whose parameter is named `isolated_db` (29 occurrences total). Suppressing per-line would add noise to 29 test signatures; the cleaner path is the documented fallback — fixture in `conftest.py`, helpers in the module. Both paths are explicitly sanctioned by the leg artifact ("Either shape works"); the choice was made based on lint hygiene rather than pytest semantics.
- Test 3 (`test_e2e_disabled_to_enabled_re_dispatch_restores_outbound`) needed two separate factories rather than one shared factory with a longer response script. Reason: each `factory.create()` builds a fresh `_ScriptedProvider` instance via the monkeypatched `get_provider` resolver — the response index is per-instance, so a 3-response script consumed in two separate dispatches restarts at index 0 each time. Two factories with separate response scripts achieves the test intent (operator flips switch mid-session, second dispatch sees the new state). The state-machine semantics being tested (re-enabling restores outbound) are preserved.

**Anomalies:**
- Sub-leg A's v17 migration was correctly hand-built-schema-aware: TestSchemaV14, V15, V16's hand-built fixtures CREATE the schema_version table and a `connector_accounts` and/or `chat_sessions` table, but they do NOT create an `agents` table. When `ensure_schema` ran on a fresh fixture, the v17 block's `PRAGMA table_info(agents)` returned no rows because no `agents` table existed → the `ALTER TABLE agents ADD COLUMN` then failed with `no such table: agents`. The fix was to extend each affected hand-built schema fixture with a v16-era `agents` table definition (post-v11 shape with `mcp_overrides`, no `connector_account_ids`). This is exactly the F3 debrief's ALTER-on-previously-untouched-table addendum: when a v(N) migration touches a table that earlier-version hand-built test fixtures don't seed, those fixtures need extending. Caught on the first sub-leg A test run; no production-code impact (production DBs upgrade through SCHEMA_V1 + the full migration loop, so the `agents` table always exists by the time v17 runs).

### Leg Progress: agents-md-and-readme-codify (2026-05-18)

**Status**: landed (per agentic-workflow batched-review — `completed` flips at flight-end commit).

**Scope**: docs-only leg. Codify two named project conventions, document F4's outbound contract in agents.md's Connector subsystem section, add Item 8 to the Connector type extension checklist, correct README §4's tail paragraph + append two new README sections (§10 Required capabilities, §11 Outbound flow trace).

**Files modified:**

- `the_one/agents.md`:
  - Project Conventions: added `### \`optional-plugin-hook-via-getattr-sentinel\`` (codified at n=1 per F3 debrief recommendation; first instance was F3's `display_channel`) and `### \`protocol-widening-for-required-capability\`` (codified by F4's `ConnectorClient.send` widening). Both follow the existing 2-paragraph shape (explanation + concrete citation) used by sibling conventions. Inserted BEFORE the `---` divider at the end of Project Conventions, so order is: existing conventions → optional-hook → protocol-widening → divider → Subsystem contracts.
  - Connector type extension checklist: appended Item 8 (Tool-target validation) after Item 7. Cites `the_one/tools/connector_send.py:SendToPlatformChannelTool.execute` and the `# F6: AllowlistResolver consultation lands here` hook-point marker. Items 1-7 unchanged (no renumbering).
  - Connector subsystem section: inserted new `### Outbound contract` subsection between `### Encryption-rotation invariant (three corpora)` and `### Known Issues`. Documents (a) the platform-send tool as the sole production caller of `send`, (b) the F10 baseline carve-out with the two-layer enable composition, (c) the visibility-tagging contract with the post-step dispatcher pass, (d) the system-prompt directive pair for enabled/disabled states, (e) the account-scope target validation + the F6 hook point, (f) cross-reference to README §11.

- `the_one/connectors/README.md`:
  - §4 tail paragraph corrected. Removed the F4-forward-looking prediction ("if it lands as optional") that was overtaken by F4's actual choice; replaced with statement that F4 widened (not optional-hook) and cross-reference to §10 + `protocol-widening-for-required-capability` in agents.md. The `display_channel` precedent above remains the canonical optional-hook example.
  - NEW §10 "Required capabilities (Protocol-widening)" appended after §9. Three paragraphs: F4's widening of `ConnectorClient.send`, the runtime_checkable isinstance semantics (with `tests/test_connectors.py::test_client_missing_send_fails_check` as the pin), and the choice rubric between Protocol-widening and optional-hook.
  - NEW §11 "Outbound flow trace" appended after §10. 8-step end-to-end walk: (1) LLM tool_call → (2) `SendToPlatformChannelTool.execute` validation → (3) pool acquire → (4) `client.send` call → (5) success-sentinel return with `PLATFORM_SEND_OK_PREFIX` → (6) tool_result message append → (7) dispatcher post-step visibility tag → (8) dispatcher persist via `ChatSessionRepository.update`. Each step carries the file:symbol citation.
  - Existing §1-§9 unchanged (no renumbering). Verified via `grep -n '## §' README.md`: §1 through §11 in order, no duplicates.

- `missions/10-bi-directional-comms-connectors/flights/04-platform-send-tool-and-outbound/flight-log.md` — this entry.
- `missions/10-bi-directional-comms-connectors/flights/04-platform-send-tool-and-outbound/legs/06-agents-md-and-readme-codify.md` — `**Status**` → `landed`.

**Test trajectory:** No test changes (docs-only leg). Sanity full-suite run: 1945 passed, 4 skipped, 405 deselected, 1 warning — identical to leg 5's landing snapshot. The single remaining warning is the pre-existing aiosqlite teardown-loop `Event loop is closed` (pytest-asyncio worker-thread teardown ordering; unrelated to this leg).

**Lint:** `docker exec the-one ruff check the_one tests` — All checks passed. No code changes, no surprises.

**Grep verifications:**
- `grep -n '### \`optional-plugin-hook-via-getattr-sentinel\`\|### \`protocol-widening-for-required-capability\`' the_one/agents.md` → both heading lines present at L96 and L102 (note: agents.md uses backticks around convention names in headings, matching the existing sibling conventions like `### \`function-local-import-to-break-load-cycle\``).
- `grep -n 'optional-plugin-hook-via-getattr-sentinel\|protocol-widening-for-required-capability' the_one/agents.md` → 4 matches (heading + in-text cross-reference for each convention; meets the ≥2-each acceptance criterion).
- `grep -n '### Outbound contract' the_one/agents.md` → present at L351 (between Encryption-rotation at L328-336 and Known Issues at L370).
- `grep -n '^8\. \*\*Tool-target validation\*\*' the_one/agents.md` → present at L306 (immediately after Item 7's last line, before the `---` divider).
- `grep -n '## §' the_one/connectors/README.md` → §1 through §11 in order with no duplicates: §1 L22, §2 L46, §3 L69, §4 L198, §5 L242, §6 L277, §7 L292, §8 L312, §9 L327, §10 L349, §11 L357.
- `grep -n "F4's.*outbound.*extension.*if it lands as optional" the_one/connectors/README.md` → ZERO matches (the corrected paragraph took effect).

**Citation audit applied at leg-design time:** the leg artifact's Citation Audit table (18 file:symbol references) was verified against current code by the leg author before this implementation began. All citations land on real symbols in the codebase as of legs 1-5 of F4.

**Deviations / anomalies:** none. Docs-only leg landed clean on first pass.

---

## Decisions

Runtime decisions not in original plan.

---

## Deviations

Departures from planned approach.

---

## Anomalies

Unexpected issues encountered.

---

## Session Notes

Chronological notes from work sessions.
