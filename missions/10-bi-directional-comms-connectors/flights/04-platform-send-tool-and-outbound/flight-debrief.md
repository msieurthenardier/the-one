# Flight Debrief: Platform-Send Built-in Tool and Outbound Routing

**Date**: 2026-05-18
**Flight**: [Platform-Send Built-in Tool and Outbound Routing](flight.md)
**Status**: landed (transitioning to `completed` after this debrief)
**Duration**: planning → ready (`ac7ca05`, 2026-05-17) → in-flight (`13a9adf`, 2026-05-18) → landed (`de6b473`, 2026-05-18)
**Legs Completed**: 6 of 6

## Outcome Assessment

### Objectives Achieved

The flight's stated objective — "land the outbound side of the connector subsystem: register `send_to_platform_channel` as a built-in tool, widen the `ConnectorClient` Protocol to carry the outbound method, wire the tool through the existing F1 pool to a connector's `ConnectorClient.send(...)`, add per-agent attachment via `AgentConfig.connector_account_ids`, auto-load the tool's schema at session start for connector-attached agents (the deliberate F10 baseline carve-out), compose a connector-aware system prompt (enabled-tool vs disabled-tool directives), and tag the agent's outputs in connector-attached sessions with the right `visibility` value" — is met. The deliverables:

- **`SendToPlatformChannelTool`** at `the_one/tools/connector_send.py`, registered in `_TOOL_CLASSES`, surfacing via the existing built-in-tools admin grid (operator enable/disable via `/api/tools/configs/send_to_platform_channel`). Zero-arg construction works (`/api/tools` introspection path preserved).
- **`ConnectorClient` Protocol widening** at `the_one/connectors/base.py`: `async def send(target, content) -> SendResult` is now required on every connector in scope. F1's docstring invitation honored; `runtime_checkable` semantics pinned by `tests/test_connectors.py::test_client_missing_send_fails_check`.
- **`AgentConfig.connector_account_ids: list[str]`** as the per-agent attachment field, AND the v17 schema migration adding the corresponding SQLite column with full `SQLiteAgentStore.save`/`_row_to_config` round-trip (closed in leg 5 after surfacing as a leg-4 deviation).
- **`AgentFactory.create()` F10 baseline carve-out**: when `connector_attached AND send_tool_enabled`, the tool's schema is pre-loaded into `_loaded_schemas` so the connector-attached agent sees it at turn 1 without invoking `search_tools`. Documented as the second documented exception in `agent/core.py:30-34`'s F10 strict-baseline comment.
- **Connector-aware system prompt** via the new module-level `compose_system_prompt` in `agent/config.py` — enabled-tool directive vs disabled-tool directive; non-connector callers byte-identical to pre-F4.
- **Dispatcher post-step visibility tagging** at `the_one/connectors/_inbound.py:228-240`: peer messages stay `visibility=None`; successful platform-send tool_result tags `None` (peers saw it); every other new message gets `OPERATOR_VISIBILITY`. Tool_result→tool_call correlation via `m.tool_result.tool_call_id` against a `{tc.id → tc.name}` lookup built from new assistant messages.
- **`now_iso` promotion**: `db/models._now_iso → now_iso` (public); shadow definition at `db/repositories.py:25` and `_utc_now_iso` copies in `connectors/_session.py` and `connectors/_inbound.py` deleted. `grep -rn '_now_iso\|_utc_now_iso' the_one/ tests/` returns zero matches.
- **Two new codified Project Conventions** in `agents.md`: `optional-plugin-hook-via-getattr-sentinel` (n=1 from F3's `display_channel`); `protocol-widening-for-required-capability` (n=1 from F4's `ConnectorClient.send`).
- **Six new tests at the package level + 64 new tests overall**; 0 regressions. 1881 (F3 baseline) → 1945 (F4 landing).

### Mission Criteria Advanced

| Criterion | Status | How advanced |
|---|---|---|
| #13 (platform-send tool registered + operator enable/disable + auto-available for connector-attached agents) | **COMPLETE** (F4 scope) | Tool registered in `_TOOL_CLASSES`; F10 baseline carve-out at `factory.py:347-360`; `test_e2e_enabled_state_platform_send_delivers` pins delivery |
| #14 (tool-disabled state: inbound received, no outbound, re-enabling restores) | **COMPLETE** | Dispatcher accepts inbound regardless of tool state; disabled directive in prompt; `test_e2e_disabled_state_inbound_received_no_outbound` + `test_e2e_disabled_to_enabled_re_dispatch_restores_outbound` pin both clauses |
| #15 (tool can only target attached accounts) | **COMPLETE** (account-scope; F6 layers ACLs) | `SendToPlatformChannelTool.execute` validates `target.account_id ∈ self._connector_account_ids`; `test_e2e_target_validation_rejects_unattached_account` pins; F6 ACL hook-point comment at `connector_send.py:131` |
| #11 (Chat opens with unified history + clear visual distinction) | **advances** (F5 owns rendering) | Dispatcher tags `Message.visibility` so F5's Chat UI has the data to drive the two-layer render |
| #12 (operator console doesn't leak to platform; agent's responses stay local by default) | **advances structurally** | Tool-only outbound + visibility tagging make leakage impossible by construction — F4 establishes the path-of-record, F5 surfaces it |
| #29 (each layer has automated coverage) | **advances** | 6 e2e + ~30 unit tests on the F4 surface; F1/F2/F3 regression baselines hold |

## What Went Well

- **Per-leg design review with a fresh Developer caught the high-impact issues at design time.** Across the 6 legs the per-leg pre-implementation review surfaced: `_now_iso` 4th-copy in `db/repositories.py:25` (would have been "promote helps by 50% only"); the `runtime_checkable` Protocol-widening semantics correction (the original spec claimed widening was non-breaking for isinstance — wrong); `Role.USER` skip in the visibility-tagging walk (would have re-tagged the peer message as operator); patch-scope correctness on the `_Ctx` fixture (would have left every `factory.create()` call un-patched); the AsyncMock-warning short-circuit-verification-first approach (warning had been re-opened by F6.5 L04 — fix needed extension, not retirement). Each is the kind of bug that becomes a debug session at implementation time; each was caught at design-review time.
- **The agentic-workflow batched-review cadence held cleanly across 6 legs.** No leg required mid-leg redesign. The single flight-end Reviewer pass + commit cycle replaced 6 individual review/commit cycles — net efficiency win, no quality cost (Reviewer confirmed without blocking issues).
- **The `_now_iso` promotion is the cleanest cross-cutting refactor F4 shipped.** Four definitions reduced to one (the public `db/models.now_iso`). Zero `_now_iso` / `_utc_now_iso` references survive anywhere in `the_one/` or `tests/`. The architect's prerequisite-time catch of the `db/repositories.py:25` shadow was the single highest-leverage architect correction in F4 — without it leg 4 would have shipped a "two→three" promotion that left 2 surviving copies + the public name, an incomplete reduction.
- **Two new codified conventions emerged organically and align with prior debriefs' recommendations.** F3 debrief recommendation #2 ("codify `optional-plugin-hook-via-getattr-sentinel` at n=1") landed in leg 6 verbatim. `protocol-widening-for-required-capability` is the symmetric companion; F4 leg 1 was the first instance, leg 6 codified.
- **Sixth-consecutive-flight AsyncMock-warning carry-forward FIXED.** Leg 5 sub-leg D verified the warning still fires (despite the F5 L01.5 short-circuit) — F6.5 L04 had re-opened the surface with a sibling `get_model_context_length` call. The fix extended the existing `with patch(...)` block to also patch `the_one.interfaces.web.api.ollama_api.get_model_context_length` with `new_callable=AsyncMock, return_value=None`. Carry-forward officially closed; 5-flight streak ends.
- **Leg-4 deviation closure in leg 5 was textbook in-flight scope expansion.** The persistence gap surfaced at first-test-run; leg 4 worked around with a documented monkeypatch + flagged the gap explicitly for the flight debrief; leg 5 expanded to four sub-legs (A: v17 migration, B: e2e tests, C: helper extraction, D: AsyncMock closure) and landed all four atomically. The monkeypatch was removed in the same leg that landed the persistence — no dangling test debt.
- **Test trajectory + lint clean throughout.** Full-suite green at every leg landing (F3 baseline 1881 → leg 1 1888 → leg 2 1916 → leg 3 1929 → leg 4 1934 → leg 5 1945 → leg 6 1945). Ruff clean at every leg.
- **The flight log captured per-leg discipline with no gaps.** Each leg-progress entry covered files modified, test count delta, deviations (named), anomalies (named). The fly-by-the-seat-of-the-leg-artifact culture didn't survive F4 — the artifact was the contract and the log was the receipt.

## What Could Be Improved

### Process

- **Leg-1 missed the DB persistence layer for `AgentConfig.connector_account_ids`.** Leg 1's "mirror `mcp_source_ids` exactly" Design Decision was textually correct but operationally incomplete — the Pydantic field was added; `SQLiteAgentStore.save`/`_row_to_config` and the `agents` table schema were NOT touched. F1 debrief recommendation #3 (mirror table at flight-design) was directly applicable here — and was not produced. The gap surfaced as a leg-4 deviation (account-scope rejected a valid input mid-test) and forced a v17 migration in leg 5. **Recommendation**: when a leg adds a Pydantic field that is intended to persist, the architect's design-review walk MUST grep `the_one/db/` for the analog field and enumerate every site that needs the rewire. For F4 leg 1, `grep -rn 'mcp_source_ids' the_one/db/` would have returned `repositories.py:99,116,132,214` + `schema.py:628+` (the migration site) — all five sites needed v17 rewires. **Codify as a leg-planning checklist item**: "if the model adds a persisted field, the migration is in the same leg, not a future one."
- **Architect citation drift caught at design-review time, fixed in-place.** F4 architect surfaced citations off by 1-2 lines on `agent/config.py:99-105` (actually L101-107) and `109-113` (actually L109-114). Symbol anchors protect against drift but line numbers are still useful for the implementer; the Citation Audit at the bottom of each leg artifact caught both. Pattern is paying for itself; keep doing it.
- **Test-helper extraction (F3 debrief recommendation) landed cleanly in leg 5 but raised an implementation surprise.** The leg artifact recommended explicit imports for greppability over conftest fixtures. Ruff's F811 (overlapping imports) flagged 29 test signatures; the leg author fell back to the documented "fixture in `tests/conftest.py`, helpers in `_connector_dispatch_helpers.py`" split. The leg artifact already noted "Either path works"; the fallback was sanctioned. Methodology lesson: when extracting fixtures from per-file scope to a shared module, prefer the `conftest.py`-for-fixtures + helper-module-for-functions split by default.

### Technical

- **`isinstance(provider, BuiltinToolProvider)` branch in `agent/factory.py:315-331` is the second factory-time-kwarg case (after `SearchTools`).** One more occurrence and a `ToolProvider`-Protocol-widening conversation is justified. F6 (allowlist resolver wiring for the platform-send tool) or F8 (Discord-specific tool initialization) will likely tip this. **Recommendation**: surface as an F6 architect-review item.
- **`[platform-send-ok]` literal-prefix sentinel coordinates tool→dispatcher via string-prefix matching.** F4 ships with a tool-side regression net (`tests/test_connector_send_tool.py:482-508` pins that failure envelopes do NOT start with the prefix), but the dispatcher-side is unsymmetric: if a future flight adds a second success-shape that also starts with `[platform-send-ok]`, the dispatcher mistags silently. Long-term: consider a structured side-channel (e.g. `Message.tool_result.platform_send_ok: bool` field on `ToolResult`) when the next consumer surfaces — likely F5 Chat UI distinguishing peer-visible from operator-only at render time without re-checking the prefix. **For now (F4)**: acceptable; the methodology cost of conversion is bounded.
- **Visibility-tagging block runs inside the dispatcher's outer `try:`, not in a defensive sub-try.** If `tool_call_names.get(...)` somehow raises (it can't with `.get`'s default, but future evolution might), the `encode_messages` step is skipped. F3 debrief already flagged the broader `agent.step` raise-mid-stream gap; F4's new tagging block inherits the same try-budget. F10 hardening should add an exception-budget pass for the new tagging block.
- **`**_extra: Any` swallow in `SendToPlatformChannelTool.execute` masks contract drift from the LLM tool-call dispatcher.** Defensible (mirrors web/filesystem tools), but a future debug session will benefit from a logged warning when `_extra` is non-empty. Small post-flight improvement.
- **Multi-call platform-send turn untested.** If an agent emits multiple `send_to_platform_channel` tool_calls in one turn, the visibility-tagger should handle each independently — the `tool_call_names` dict is built from ALL new assistant messages — but no test pins this. Worth one regression test in F10.
- **`SendResult(platform_message_id=None)` end-to-end untested.** Unit-pinned at `test_send_result_accepts_none_platform_message_id`; e2e uses `StubClient`'s hardcoded `"stub-msg-id"`. F8 (Discord) will exercise the None branch organically because some Discord API calls don't return ids; low risk for F4.

### Documentation

- **Leg-6's codification of `optional-plugin-hook-via-getattr-sentinel` and `protocol-widening-for-required-capability` is clean**, but a third pattern emerged this flight and was not codified: **`module-local-rebinding-isolates-callsite-patching`**. `tests/test_connectors_e2e_platform_send.py:464-503` patches `the_one.connectors._inbound.registry` to break the dispatcher's defensive second-resolve while leaving `the_one.connectors._pool._resolve_plugin` intact — different module-local capture sites resolved at different import-time bindings. This is what made the F1-carry-forward catch testable without poisoning the pool. **Recommendation**: codify in `agents.md` Project Conventions at the same n=1 codification level F3's `display_channel` got. Add as a follow-on docs PR or as part of the next flight that touches `agents.md`.
- **Zero-arg tool construction for `/api/tools` introspection is an inherited project rule with no documentation.** `SendToPlatformChannelTool.__init__` defaults every kwarg to None because `BuiltinToolProvider.get_tools` zero-arg-constructs every class in the introspection branch — but this rule lives only as an inline comment at `the_one/tools/connector_send.py:91-93`. Any future tool author with factory-time kwargs needs to know this. **Recommendation**: add a one-line invariant to `agents.md` Tool authorship contract section.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| **Leg 1**: `AgentConfig.connector_account_ids` Pydantic field added without DB persistence | "Mirror `mcp_source_ids` exactly" framing was textual, not operational; mirror table not produced at design time per F1 debrief recommendation | **YES** — codify mirror-table-at-flight-design for any "mirror $existing" criterion; grep the analog's persistence touchpoints |
| **Leg 2**: `ConnectorRateLimitError` constructor signature mismatch in test sketch | Leg-spec sketch lagged the F1-shipped definition at `errors.py:77-91` | No (one-off); spec sketches inherit drift risk |
| **Leg 3**: `_Ctx.__enter__/__exit__` first-arg `self_` → `self` | Ruff `N805` naming violation | No (lint-only) |
| **Leg 4**: monkeypatch on `SQLiteAgentStore._row_to_config` to re-inject `connector_account_ids` field | Discovered leg-1 persistence gap at first-test-run; worked around explicitly; flagged for leg-5 closure | The deviation → expanded-leg-5-sub-leg-A pattern is the right move. **Standardize**: in-flight scope expansion for surfaced-gap closure is preferable to deferring to maintenance leg or next-flight |
| **Leg 5 sub-leg C**: fixtures in `conftest.py` instead of explicit `_connector_dispatch_helpers.py` imports | Ruff F811 on 29 overlapping test signatures forced the documented fallback | No (one-off; the leg artifact sanctioned both shapes). Methodology note: prefer the `conftest.py`-fixture + helper-module-function split as the default extraction shape |
| **Leg 5 sub-leg D**: AsyncMock-warning FIXED (not retired) | Verified still firing; F6.5 L04 had re-opened the surface | Yes — the verify-first methodology is the right pattern for any "is this carry-forward still real?" check |

## Key Learnings

- **The per-leg architect-review catch rate continues to pay dividends.** Across F1 (~7 substantive issues), F2 (~6), F3 (~12), F4 (~7) — every flight has caught design issues at the time they're cheapest to fix. The pattern is the methodology's load-bearing investment.
- **"Mirror $existing_thing exactly" is a methodology trap when the mirror touches multiple layers.** F1 debrief flagged it for the `name` column on `connector_accounts`; F4 hit the symmetric trap on `agents.connector_account_ids`. The methodology fix (mirror table at flight design) was on file; it was not enforced. Foreclose at leg-design-review for any future "mirror" criterion.
- **In-flight scope expansion is acceptable when it closes a same-flight deviation.** Leg 5 sub-leg A landed the v17 migration in the same flight that surfaced the gap. Cleaner than deferring to a maintenance leg AND cleaner than papering over with permanent test workarounds. The agentic-workflow batched-review model accommodates this without disrupting the per-leg review cadence.
- **Two architectural patterns crystallized this flight that deserve codification: `protocol-widening-for-required-capability` (leg 1) and `optional-plugin-hook-via-getattr-sentinel` (codified at n=1).** A third — `module-local-rebinding-isolates-callsite-patching` — emerged in leg 5's plugin-resolve test and is uncodified. Codify on next flight that touches `agents.md`.
- **Test metrics**: 1881 → 1945 (+64) in F4; 1376 → 1945 (+569) since M07 F8. Wall-clock 127.40s → 133.73s (+6.33s); throughput 14.8 → 14.5 tests/s (essentially flat). Per-test wall ~68ms — F3's continuation-supersede tests + leg-4 event-coordinated concurrency dominate the throughput baseline; F4 didn't move it. **The aiosqlite teardown-loop warning (single `PytestUnhandledThreadExceptionWarning`) persists across multiple flights** — F4 didn't cause it, F4 didn't clear it. Eligible for next maintenance ticket; small, deterministic, not a flake.
- **Per-leg flight-log discipline held.** Every leg has a "Files modified", "Test trajectory", "Deviations", "Anomalies" block. The flight log is the receipt for the contract the leg artifact established.

## Test Metrics Capture

**`docker exec the-one pytest -x --timeout 30`** (deselects browser via pyproject `addopts`):
- 1945 passed, 4 skipped, 405 deselected, 1 warning
- Wall-clock: 133.73s
- Throughput: ~14.5 tests/s
- Per-test wall: ~68.8ms

**Comparison against prior flights**:

| Flight | Tests | Wall (s) | Throughput (tests/s) |
|---|---|---|---|
| M07 F8 baseline | 1376 | — | — |
| F1 (M10) | 1774 | 100.58 | 17.6 |
| F2 | 1805 | 106.69 | 16.9 |
| F3 | 1881 | 127.40 | 14.8 |
| F4 | **1945** | **133.73** | **14.5** |

F4 added +64 tests, +6.33s wall-clock. Throughput is essentially flat — F3's per-test SQLite + event-coordinated concurrency setup dominates the baseline; F4 inherits without adding meaningful per-test overhead. No infrastructure drag visible.

**Warning trajectory**: 0 AsyncMock-never-awaited warnings (down from 2 in F1/F2/F3 — sixth-consecutive carry-forward officially closed). 1 surviving `PytestUnhandledThreadExceptionWarning` (aiosqlite teardown-loop, pre-existing, eligible for next maintenance).

**Flakes**: none observed; no indeterminism warranting a re-run.

## Recommendations

1. **Codify the mirror-table-at-flight-design discipline as enforceable.** F1 debrief recommended it; F4 ignored it for `connector_account_ids`. Add to `flight.md` design-review checklist as a hard requirement when any criterion contains the word "mirror".
2. **Codify `module-local-rebinding-isolates-callsite-patching` in `agents.md` Project Conventions** at n=1 (citation: `tests/test_connectors_e2e_platform_send.py:464-503`). Same justification as F3's `display_channel`.
3. **Add a one-line invariant to `agents.md` Tool authorship contract section**: "every Tool's `__init__` MUST accept zero-arg construction (`cls()`) — the `/api/tools` introspection path at `the_one/tools/builtins.py:104-105` calls `cls()` on every class in `_TOOL_CLASSES`."
4. **F6 architect-review item: revisit `ToolProvider` Protocol widening.** The `isinstance(provider, BuiltinToolProvider)` branch at `factory.py:315-331` is the second factory-time-kwarg case. F6 (allowlist resolver) or F8 (Discord init) will likely add a third; the conversation is justified at that point.
5. **F10 hardening list additions** (carry-forward from this debrief):
   - Tagging-loop-survives-step-raise edge case (visibility-tagging block inside the outer `try:`)
   - Multi-call platform-send turn (multiple `send_to_platform_channel` tool_calls in one agent turn)
   - `SendResult(platform_message_id=None)` end-to-end propagation
   - `[platform-send-ok]` sentinel structured side-channel conversion (only if a second consumer surfaces — likely F5)
   - aiosqlite teardown-loop warning closure
6. **Pin down the F4-leg-1-omits-persistence pattern in `agents.md`** as a methodology trap with the canonical citation: F1 leg-2 `name` column miss + F4 leg-1 `agents.connector_account_ids` miss are the two instances. The mirror-table convention is the prophylactic.

## Action Items

- [ ] **(Methodology, mission-control)** Codify mirror-table-at-flight-design as a hard requirement in the `/flight` skill's design-review pass when a criterion contains "mirror"
- [ ] **(Methodology, mission-control)** Codify `module-local-rebinding-isolates-callsite-patching` in `agents.md` Project Conventions at n=1
- [ ] **(Documentation, agents.md)** Add "zero-arg tool construction for introspection" invariant to the Tool authorship contract section
- [ ] **(F6 architect-review)** Revisit `ToolProvider` Protocol widening before adding a third factory-time-kwarg case
- [ ] **(F10 hardening)** Tagging-loop-survives-step-raise; multi-call-turn tagging; `platform_message_id=None` e2e; aiosqlite teardown warning
- [ ] **(F5 leg planning)** When Chat UI consumes the `visibility` tag, decide whether the `[platform-send-ok]` literal-prefix sentinel should convert to a structured `ToolResult.platform_send_ok: bool` side-channel
- [ ] **(F8 prereq, flagged)** F4's persistence substrate (v17 column + repository round-trip) is the load-bearing surface for Discord-driven attach via Studio UI; F8 acceptance must verify operator-attached accounts survive process restart
- [ ] **(Maintenance, eligible next flight)** Clear the aiosqlite teardown-loop warning; codify whether it's a `pytest-asyncio` config issue, an aiosqlite version artifact, or a fixture-ordering quirk
- [ ] **(Mission known issues — log under `mission.md`)** Optional: capture that F4's tool-side regression net for the success-sentinel prefix is unsymmetric (dispatcher-side has no analog test); flag for F10 hardening
