# Leg: directive-substrate

**Status**: landed
**Flight**: [Pool-Keying Refactor + Per-Account System-Prompt Directive Surface](../flight.md)

## Objective

Land the substrate half of the per-account system-prompt directive surface: extend the API validator to accept `account.config["system_prompt_directive"]: str | None`, extend `compose_system_prompt` with a 4th `operator_directive` parameter that APPENDS after the selected default, and extend `AgentFactory.create` to collect directives across attached connector accounts joined with `sorted(config.connector_account_ids)`. Validator + composer + factory + tests land atomically per `atomic-leg-pattern`.

## Context

- **Why now**: M10 F8 debrief critical action item #2 ("Operator-editable connector system-prompt directive — three hardcoded constants in `agent/config.py`; operator's L11 observation: 'I need to be able to see and modify the prompt that gets included with the connector.'"). F2 flight spec Design Decisions §2 binds the substrate shape: APPEND mode (not replace), per-account config field, `sorted()` join, `operator_directive=None` default preserves byte-identical legacy behavior.
- **L3 is substrate-only**: no UI. L4 ships the Studio textarea + 3 read-only defaults + `data-account-id` refactor + `MASKED_SENTINEL` lift. L3 unblocks L4 by making the config field acceptable at the API write path.
- **Why APPEND, not replace**: per `mechanical-fallback-prompt-truth-pairing` (L1-codified F1). Replacing the default would let the operator overwrite the substrate's MUST-call-tool / auto-relay-truth contract — exactly the prompt-discipline failure mode the convention warns against. APPEND lets the operator add persona/formatting/peer-engagement guidance without overriding the substrate's behavioral contract.
- **Why `sorted()` for multi-account composition** (Design Decisions §2): factory iterates `for account_id in config.connector_account_ids` in persisted list order (line 332). Auto-relay aggregation correctly stays in list-order because its first-opt-out short-circuit is order-sensitive (line 340-342). Directive collection diverges deliberately — uses `sorted(config.connector_account_ids)` for deterministic prompt-cache stability. `sorted()` on `str` is lexicographic-by-Unicode-codepoint, Timsort-stable, locale-independent, identical across CPython 3.x.
- **`operator_directive=None` byte-identical legacy preservation**: existing non-connector callers — verified at cycle-1 review to be exactly two: `AgentConfig.get_system_prompt()` at `config.py:308` and `AgentFactory.create` at `factory.py:452`. The `get_system_prompt` path uses `connector_attached=False, send_tool_enabled=False, auto_relay=True` and now also picks up the implicit `operator_directive=None` default → byte-identical output to today. (No WS-handler prompt-equivalence caller exists in the current tree — that reference was stale from F1 planning notes.) Verifiable via the existing `tests/test_config.py:compose_system_prompt` test suite — every existing test must pass UNMODIFIED.

## Inputs

Files that must exist:

**Production source**:
- `the_one/interfaces/web/api.py` (`_validate_connector_account_config` at `:872+`; Discord branch at `:893+` — extend with `system_prompt_directive` validation block)
- `the_one/agent/config.py` (`compose_system_prompt` at `:96-148`; the three hardcoded constants at `:_CONNECTOR_TOOL_ENABLED_DIRECTIVE` / `:_CONNECTOR_AUTO_RELAY_DIRECTIVE` / `:_CONNECTOR_TOOL_DISABLED_DIRECTIVE` — referenced but UNCHANGED)
- `the_one/agent/factory.py` (`AgentFactory.create` at `:auto_relay aggregation` lines 329-342 — directive collection is the parallel block; `compose_system_prompt` call at lines 452-458 receives the new `operator_directive` kwarg)

**Tests**:
- `tests/test_api_connector_account_config_validation.py` — extend the existing `TestConnectorAccountConfigValidation` class with `system_prompt_directive` rejection-matrix + happy-path
- `tests/test_config.py` (`compose_system_prompt` test cluster starts at line 208) — add `operator_directive` append-mode tests; CRITICALLY, every existing test in the cluster must pass UNMODIFIED (byte-identical legacy preservation)
- `tests/test_factory.py` — add multi-account directive collection test (deterministic sort order); existing auto-relay + connector-attached tests must pass UNMODIFIED

State that must be true:
- F2 L1 + L2 are `landed`
- F2 branch checked out; branched from F1
- F1 baseline (2804) + L2's +2 pool tests (2806) all pass
- `compose_system_prompt`'s 3-param signature is what every existing caller uses; the 4th param is purely additive with a `None` default

## Outputs

State changes after this leg:

- `the_one/interfaces/web/api.py:_validate_connector_account_config`:
  - Discord branch (the existing `if account.type == "discord":` block) extended with a new validation block for the optional `system_prompt_directive` key. Sits after the existing `presence` block (or in alphabetical order with the existing three keys — implementer choice). Shape: if absent → pass; if present → must be `isinstance(value, str)` (NOT bytes; NOT bytearray); no length cap; no content validation. Empty string `""` is rejected with a verbatim 422 detail string (empty-string directives are operator-confusing AND would round-trip as a meaningless config noise key).
  - Verbatim 422 detail strings per `verbatim-message-equality` (L1-codified F1):
    - Non-string: `"Discord connector config.system_prompt_directive must be a string if present; got {type(value).__name__}."`
    - Empty string: `"Discord connector config.system_prompt_directive must be a non-empty string if present (use absence to mean 'no override')."`

- `the_one/agent/config.py:compose_system_prompt`:
  - Signature extended: `compose_system_prompt(base, persona, *, connector_attached=False, send_tool_enabled=False, auto_relay=True, operator_directive: str | None = None) -> str`. The 4th keyword param has default `None` so every existing caller produces byte-identical output.
  - Body: after the existing if/else tree appends the selected default (lines 137-144), AND BEFORE the `if persona:` branch appends the persona separator (line 145), append `operator_directive` to `parts` IFF truthy (`if operator_directive: parts.append(operator_directive)`).
  - Docstring updated: new paragraph describing the append behavior + the `operator_directive=None` default's byte-identical guarantee.

- `the_one/agent/factory.py:AgentFactory.create`:
  - After the existing auto-relay aggregation block (lines 329-342) — which collects per-attached-account auto-relay state in PERSISTED LIST ORDER (preserved) — add a parallel directive-collection block. **Guards differ**: auto-relay only runs when `connector_attached AND send_tool_enabled AND config.connector_account_ids` (auto-relay is moot when the tool is disabled); directive collection runs when `connector_attached AND config.connector_account_ids` (operators may author directives for the disabled-tool case too — the directive is appended to the tool-disabled default just as much as to the tool-enabled defaults).
  - **Do NOT hoist `account_repo`** above the auto-relay block (rejected at design-review cycle 1 — hoisting would conflict with the differing guards). Instantiate `account_repo = ConnectorAccountRepository(conn, encryptor)` LOCALLY at the head of the directive block. The repo construction is cheap (reuses the already-resolved `conn` + `encryptor`); the duplicate instance in the connector-attached-but-tool-disabled path is acceptable overhead.
  - Iterates `sorted(config.connector_account_ids)`. For each account_id, calls `account_repo.get(account_id)`. Collects `account.config.get("system_prompt_directive")` values, drops None, joins with `"\n\n"`. The joined string is passed as `operator_directive` to `compose_system_prompt`.
  - Handle the KeyError-on-deleted-account case the same way the auto-relay block does — skip silently with a debug log; do not crash agent creation.
  - **Composition check**: factory passes `"d1\n\nd2"` as `operator_directive` when two accounts have directives; composer appends it after the selected default with its own `"\n\n".join(parts)` (config.py:148); resulting prompt is `base\n\n<selected_default>\n\nd1\n\nd2\n\n---\n\npersona`. The double-`\n\n` between concatenated directives matches the inter-block separator the composer already uses — clean composition.

- Tests:
  - `tests/test_api_connector_account_config_validation.py` — extend `TestConnectorAccountConfigValidation`:
    - `test_discord_system_prompt_directive_non_string_rejected` — POST with `config["system_prompt_directive"] = 42` → 422 with verbatim detail
    - `test_discord_system_prompt_directive_empty_string_rejected` — POST with `""` → 422 with verbatim detail
    - `test_discord_system_prompt_directive_absent_passes` — POST without the key → 201 (M10 F8 byte-identical)
    - `test_discord_system_prompt_directive_short_string_passes` — POST with `"Sign replies with a coffee emoji."` → 201
    - `test_discord_system_prompt_directive_long_string_passes` — POST with a 5000-char string → 201 (no length cap)
    - `test_stub_system_prompt_directive_pass_through` — POST stub-type with `system_prompt_directive` → 201 (stubs don't validate per-type config)
  - `tests/test_config.py` — extend the `compose_system_prompt` test cluster (starts at line 208):
    - `test_operator_directive_appended_when_truthy` — pass a non-empty `operator_directive`; verify it appears after the selected default and before the persona
    - `test_operator_directive_none_is_byte_identical_to_legacy` — call with `operator_directive=None` vs without the kwarg; assert output strings are equal
    - `test_operator_directive_empty_string_is_no_op` — call with `operator_directive=""`; verify output equals the no-directive baseline (the `if operator_directive:` falsy-check handles this naturally; pin the contract)
    - Every existing test in the cluster passes UNMODIFIED.
  - `tests/test_factory.py` — extend the connector-attached test cluster:
    - `test_multi_account_directives_collected_in_sorted_order` — agent attached to 3 accounts with IDs `"zeta"`, `"alpha"`, `"mike"`, each with distinct directives; verify the resulting system prompt contains all three in lexicographic order (`alpha` first, then `mike`, then `zeta`)
    - `test_directive_absent_account_skipped_in_join` — agent attached to 3 accounts, ONE has the directive set, the other two don't; verify the join is just the one directive (no empty-string padding, no separator noise)
    - `test_deleted_account_skipped_silently` — agent's `connector_account_ids` references an account that's been deleted; verify the KeyError is swallowed (mirroring the auto-relay block's handling)
    - Existing prompt-equivalence + auto-relay tests must pass UNMODIFIED (no regressions on the auto-relay collection — it still uses list-order).

## Acceptance Criteria

- [ ] `_validate_connector_account_config` Discord branch accepts the optional `system_prompt_directive` key per the rules above. Absent → pass. Present + valid string → pass. Present + non-string → 422 with verbatim detail. Present + empty string → 422 with verbatim detail. Length cap NOT enforced.
- [ ] `compose_system_prompt` signature extended with `operator_directive: str | None = None` keyword param; body appends after the selected default + before the persona separator IFF truthy.
- [ ] `compose_system_prompt(base, persona)` (no kwargs) returns byte-identical output to the pre-L3 shape — preserved by the `None` default. Verified by the existing test cluster passing UNMODIFIED.
- [ ] `AgentFactory.create` collects `system_prompt_directive` values across `sorted(config.connector_account_ids)`, drops None, joins with `\n\n`, passes as `operator_directive` to `compose_system_prompt`. Deleted accounts are skipped silently (mirrors the auto-relay block's KeyError handling).
- [ ] `AgentFactory.create`'s existing auto-relay aggregation is UNCHANGED — still iterates persisted list order; first-opt-out short-circuit semantics preserved.
- [ ] Verbatim 422 detail strings pinned by tests per `verbatim-message-equality` (L1-codified F1).
- [ ] Tests added per Outputs above (~12 new tests across 3 files: 6 validator + 3 composer + 3 factory); all existing tests in `test_api_connector_account_config_validation.py`, `test_config.py`, `test_factory.py` pass UNMODIFIED.
- [ ] **`AgentConfig.get_system_prompt()` output is byte-identical to pre-L3** — confirmed by the existing `TestGetSystemPrompt` cluster at `tests/test_config.py:TestGetSystemPrompt` (lines 178-191) passing UNMODIFIED. The `operator_directive=None` default ensures `compose_system_prompt(BASE_PROMPT, self.system_prompt, connector_attached=False, send_tool_enabled=False, auto_relay=True)` (the `get_system_prompt` call shape at `config.py:308`) produces identical output to today.
- [ ] No UI changes — no studio JS touched, no `index.html` change, no `connector-form-discord.js` change. That's L4's scope.
- [ ] Full suite at or above F2 L2's 2806 baseline (plus the ~12 new tests).

## Verification Steps

- `grep -n "system_prompt_directive" the_one/interfaces/web/api.py` — at least 3 hits (validation block).
- `grep -n "operator_directive" the_one/agent/config.py the_one/agent/factory.py` — at least 4 hits (signature, body, factory collection, factory call site).
- `docker exec the-one pytest -x --timeout 30 tests/test_api_connector_account_config_validation.py` — all tests pass including the new directive tests.
- `docker exec the-one pytest -x --timeout 30 tests/test_config.py` — every existing `compose_system_prompt` test passes UNMODIFIED plus 3 new directive tests.
- `docker exec the-one pytest -x --timeout 30 tests/test_factory.py` — every existing connector-attached + auto-relay test passes UNMODIFIED plus 3 new directive tests.
- `docker exec the-one pytest -x --timeout 30 -q -m "not pixel"` — full suite at or above 2806 + 7 new tests. Zero regressions.

## Implementation Guidance

1. **Read the surface end-to-end**:
   - `the_one/interfaces/web/api.py:_validate_connector_account_config` (line 872+) — Discord branch shape; F1 L2 conventions (verbatim detail strings, `isinstance(..., bool)` over `int`).
   - `the_one/agent/config.py:compose_system_prompt` (line 96-148) — current signature + body; understand the three-state if/else tree.
   - `the_one/agent/factory.py:AgentFactory.create` — auto-relay aggregation at lines 329-342 (the parallel pattern the directive collection mirrors); compose call at lines 452-458.
   - `tests/test_config.py:compose_system_prompt cluster` at line 208 — the test patterns the new directive tests follow.
   - `tests/test_factory.py:connector-attached test cluster` (around the auto-relay tests at line 604+) — the existing test patterns.

2. **Extend the API validator** (`api.py:_validate_connector_account_config` Discord branch):
   - Add a new `system_prompt_directive` block AFTER the existing `presence` validation (or in alphabetical order with the existing three keys — implementer's choice; doesn't affect semantics).
   - Implementation:
     ```python
     # ── system_prompt_directive ──────────────────────────────
     if "system_prompt_directive" in cfg:
         directive = cfg["system_prompt_directive"]
         if not isinstance(directive, str):
             raise HTTPException(
                 status_code=422,
                 detail=(
                     f"Discord connector config.system_prompt_directive must be "
                     f"a string if present; got {type(directive).__name__}."
                 ),
             )
         if not directive:
             raise HTTPException(
                 status_code=422,
                 detail=(
                     "Discord connector config.system_prompt_directive must be "
                     "a non-empty string if present (use absence to mean 'no override')."
                 ),
             )
     ```

3. **Extend `compose_system_prompt`** (`agent/config.py:96-148`):
   - Add keyword-only param `operator_directive: str | None = None` after `auto_relay`.
   - Body change at the end of the connector-attached branch — after the existing append of the selected default constant and BEFORE the `if persona:` block:
     ```python
     if operator_directive:
         parts.append(operator_directive)
     ```
   - Update the docstring to add a paragraph describing the append behavior and the `None` default's byte-identical guarantee.

4. **Extend `AgentFactory.create`** (`agent/factory.py:AgentFactory.create`):
   - Just AFTER the auto-relay aggregation block (around line 343 in current shape, after the `break` on first opt-out), add the directive collection block. **The directive block has a DIFFERENT guard than auto-relay** — operator directives apply even when the tool is disabled (the disabled-state directive can be appended-to just like the enabled-state ones), so don't gate on `send_tool_enabled`:
     ```python
     # M11 F2 L3: per-account system-prompt directive collection.
     # Iterates sorted(account_ids) for deterministic prompt-cache stability
     # — explicit divergence from auto-relay's list-order iteration above
     # (which keeps list-order because its first-opt-out short-circuit is
     # order-sensitive). Drops None / missing values; joins remaining with
     # "\n\n". Empty result → None (no operator_directive kwarg effect).
     #
     # Guard differs from auto-relay: directives apply even when the tool
     # is disabled (the operator can author guidance for the disabled-tool
     # default just as much as for the enabled-tool ones). So DO NOT
     # short-circuit on send_tool_enabled.
     operator_directive: str | None = None
     if connector_attached and config.connector_account_ids:
         # Local instantiation: don't hoist above auto-relay (the two blocks
         # have different guards). Repo construction is cheap (reuses the
         # already-resolved conn + encryptor); duplicate instance in the
         # connector-attached-but-tool-disabled path is acceptable overhead.
         directive_account_repo = ConnectorAccountRepository(conn, encryptor)
         directives: list[str] = []
         for account_id in sorted(config.connector_account_ids):
             try:
                 account = await directive_account_repo.get(account_id)
             except KeyError:
                 # Deleted account in the ID list — skip silently;
                 # mirrors the auto-relay block's handling above.
                 continue
             directive = account.config.get("system_prompt_directive")
             if directive:
                 directives.append(directive)
         if directives:
             operator_directive = "\n\n".join(directives)
     ```
   - Update the `compose_system_prompt` call at lines 452-458 to pass `operator_directive=operator_directive`.

5. **Add tests** per Outputs above. Specifically:
   - `tests/test_config.py` directive tests live in the existing `compose_system_prompt` cluster (around line 208+). Use the existing test fixtures.
   - `tests/test_factory.py` directive tests live in the connector-attached cluster (around line 604+; reuse the `seed_connector_account` + repo-mock pattern the auto-relay tests use).
   - `tests/test_api_connector_account_config_validation.py` directive tests extend the existing `TestConnectorAccountConfigValidation` class.

6. **Run tests in order**:
   - `docker exec the-one pytest -x --timeout 30 tests/test_config.py` — composer tests first (smallest surface; isolates the composer change).
   - `docker exec the-one pytest -x --timeout 30 tests/test_factory.py` — factory + collection tests.
   - `docker exec the-one pytest -x --timeout 30 tests/test_api_connector_account_config_validation.py` — validator tests.
   - `docker exec the-one pytest -x --timeout 30 -q -m "not pixel"` — full suite final check.

## Edge Cases

- **Operator sets `system_prompt_directive` to the empty string**: rejected at the API validator (422). Operator's intent must be expressed via key absence, not empty string.
- **Operator sets the directive on ONE of N attached accounts**: collection picks up just that one; the join is the single directive (no `\n\n` separator since there's only one element).
- **All attached accounts have None directives**: `directives` stays empty; `operator_directive` is None; `compose_system_prompt` receives `None`; output is byte-identical to legacy.
- **`connector_account_ids` is empty (agent not connector-attached)**: directive collection skipped entirely; `compose_system_prompt` receives `None`; output byte-identical to legacy non-connector compose.
- **Account in `connector_account_ids` was deleted**: KeyError on `account_repo.get(account_id)` is swallowed; that account contributes nothing. Mirrors auto-relay's handling.
- **Same directive text on multiple accounts**: the join produces duplicates (e.g., `"X"` on alpha and zeta → `"X\n\nX"`). This is acceptable — the operator chose to set the same text twice; the substrate doesn't dedup. If duplication produces LLM confusion, that's an operator-config issue, not a substrate concern.
- **Existing prompt-equivalence checks at the WS handler**: pass `operator_directive=None` (or omit the kwarg) → byte-identical to legacy. Verified by the existing test cluster passing UNMODIFIED.

## Files Affected

**Production source**:
- `the_one/interfaces/web/api.py` — `_validate_connector_account_config` Discord branch + 4th validation block
- `the_one/agent/config.py` — `compose_system_prompt` signature + body + docstring
- `the_one/agent/factory.py` — `AgentFactory.create` directive collection block + compose call kwarg + possible `account_repo` hoist

**Tests**:
- `tests/test_api_connector_account_config_validation.py` — 6 new test methods
- `tests/test_config.py` — 3 new test methods in the composer cluster
- `tests/test_factory.py` — 3 new test methods in the connector-attached cluster

**Flight artifacts**:
- `missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/flight-log.md` — Leg Progress entry
- `missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/legs/03-directive-substrate.md` — status transitions

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All ~7 new tests pass; all existing tests in the three test files pass UNMODIFIED
- [ ] `compose_system_prompt(base, persona)` (no kwargs) produces byte-identical output to pre-L3 — preserved by `None` default
- [ ] `AgentFactory.create`'s auto-relay aggregation untouched (still list-order, first-opt-out semantics preserved)
- [ ] Full suite at or above F2 L2's 2806 + ~7 new tests
- [ ] Update flight-log.md with Leg Progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off the leg in flight.md
- [ ] Do NOT commit

## Citation Audit

Citations verified at leg design time (2026-05-21, post-L2):

- `the_one/interfaces/web/api.py:_validate_connector_account_config` — verified at line 872; Discord branch at line 893+; existing keys validated: intents, guilds, presence.
- `the_one/agent/config.py:compose_system_prompt` — verified at lines 96-148; 3-state if/else tree at lines 137-144; persona separator append at line 145+.
- `the_one/agent/config.py:_CONNECTOR_TOOL_ENABLED_DIRECTIVE` / `:_CONNECTOR_AUTO_RELAY_DIRECTIVE` / `:_CONNECTOR_TOOL_DISABLED_DIRECTIVE` — three hardcoded constants at lines 54-67, 69-84, 86-95. UNCHANGED by L3.
- `the_one/agent/factory.py:AgentFactory.create` — auto-relay aggregation at lines 329-342 (iterates persisted list order; first-opt-out short-circuit at line 342); compose call at lines 452-458. Repository instance `account_repo = ConnectorAccountRepository(conn, encryptor)` at line 331.
- `tests/test_config.py:compose_system_prompt cluster` — starts at line 208; existing tests at lines 217-280+; new directive tests extend this cluster.
- `tests/test_factory.py:connector-attached test cluster` — auto-relay tests at lines 604-680+; existing patterns for multi-account + opt-out behavior.
- `tests/test_api_connector_account_config_validation.py` — exists from F1 L2; `TestConnectorAccountConfigValidation` class extends naturally.

Seven citation clusters verified live against the post-L2 tree. No drift.
