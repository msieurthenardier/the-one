# Leg: account-always-listen-storage-migration

**Status**: completed
**Flight**: [Mentions-Aware Response Policy](../flight.md)

## Objective

Replace the account-level `auto_relay_platform_replies` config key with the new `always_listen: bool` capability switch (default False); make auto-relay invariant on engaged turns (no more operator toggle); strip the legacy key on first F7-era save; migrate all touched Python + JS surfaces in one atomic-leg-pattern slice (validator, dispatcher, factory, four JS sites); update all tests that reference the legacy key.

## Context

- **Flight DD §3 (modes + composition)** — `always_listen` is the account-level capability switch (master gate for the inference path). Default False. When False, the inference LLM is never called for this account; per-agent toggles (L6) are forced off + disabled in UI.
- **Flight DD §4 (auto-relay invariant)** — `auto_relay_platform_replies` is removed; auto-relay becomes invariant when the policy gate (L8) engages. The legacy True/False values carry no useful info — they were a workaround for "Sonnet 4.7 doesn't reliably call send_to_platform_channel," which the new policy-gate-then-auto-relay invariant supersedes. Existing accounts: read paths gracefully ignore the legacy key (the consumers `_inbound.py:744-789` and `agent/factory.py:329-342` are gutted in L5), then the validator strips the key on first F7-era save (so the row gets cleaned up the next time the operator edits anything in the connector account).
- **Migration semantic** — Option (a) from recon: read paths gracefully ignore the legacy key (the existing `.get("auto_relay_platform_replies", True)` defaulting paths just go away when their callers are gutted); the validator strips the key from the dict on its return, so any save after L5 lands persists the cleaned row.
- **L5/L11 scope boundary** — L5 is the data-layer (schema validator + dispatcher / factory consumers + clean-up at the four JS data-path sites). L11 is the UI layer (the new "Always Listen" toggle in the connector-account editor, plus the per-agent toggle from L6). After L5 lands, the JS editor temporarily has NO toggle for either auto-relay or always-listen — auto-relay is invariant (no UI control needed); always-listen toggle ships in L11. The operator can still hand-edit the config raw JSON (the existing kv-config editor fallback) if they want to enable `always_listen=true` before L11 lands.
- **Atomic-leg-pattern (per agents.md convention)** — Pydantic validator + dispatcher consumer removal + factory consumer removal + JS clean-up + tests all land in one leg so the system is consistent at any commit checkpoint.

## Inputs

- L1+L2+L3+L4 landed uncommitted.
- `the_one/db/models.py:422-436` — `auto_relay_platform_replies` shape validator inside `_validate_config_reserved_keys` (Pydantic v2 `@field_validator` on `ConnectorAccount.config`, around line 190). Validator currently enforces "must be bool when present"; returns `value` unchanged.
- `the_one/db/models.py:195-204` — validator docstring enumerating the four reserved keys (`pairing`, `allowlist`, `routing`, `auto_relay_platform_replies`). L5 updates this docstring to enumerate `always_listen` in place of `auto_relay_platform_replies`.
- `the_one/connectors/_inbound.py:744-789` — F8 L11 auto-relay block. Reads `account.config.get("auto_relay_platform_replies", True)` at ~line 772-774; on True (default), checks `already_sent_via_tool`, then relays via `client.send`. L5 removes the config read; the relay path stays for engaged turns (L8's policy gate will enter this code only on engaged decisions).
- `the_one/agent/factory.py:329-342` — `auto_relay` computation: iterates `config.connector_account_ids`, reads `account.config.get("auto_relay_platform_replies", True)` per account, sets `auto_relay = False` if any account has it explicitly False. Passed via the `auto_relay=auto_relay` kwarg at line 468, within the **single** `compose_system_prompt` call at lines 463-469 (NOT two call sites — the cycle-2 review clarified this).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — **FIVE** sites (cycle-2 review caught a fifth surface the recon missed):
  - Lines 538-570 (toggle render — comment header at 538-548 + control markup at 549-570)
  - Lines 1030-1035 (form snapshot collection — leading comment 1030-1033 + lines 1034-1035)
  - Lines 1160-1177 (change listener — leading comment 1160-1169 + listener 1170-1177)
  - Lines 1734-1745 (config merge on form submission — leading comment 1734-1741 + merge 1742-1745)
  - Lines 188-213 + 572-597 (FIFTH SITE — `_DIRECTIVE_AUTO_RELAY_ON_DEFAULT`, `_DIRECTIVE_AUTO_RELAY_OFF_DEFAULT` consts + `_selectEffectiveDirective`, `_updateEffectiveDirectiveCodeblock` helpers at ~188-213, AND the "Effective system prompt" codeblock render at ~572-597, AND the initial codeblock-update call at line 1169. After sites 1+3 removal these become dead code AND the codeblock shows stale UI; the acceptance criterion grep `auto_relay_platform_replies` requires their removal too.)
- `tests/test_db_repositories.py:1557-1597` — direct validator tests (the two `auto_relay_platform_replies` accept/reject tests). L5 replaces these with `always_listen` equivalents.
- 6 other test files (~13 line-level references total) reference `auto_relay_platform_replies` in setup blocks per the recon's grep. Exhaustive list: `tests/test_factory.py`, `tests/test_connectors_inbound.py`, `tests/test_connectors_e2e_session.py`, `tests/_connector_dispatch_helpers.py`, `tests/test_connectors_e2e_platform_send.py`, `tests/test_connectors_inbound_broadcast.py`. L5 triages each per the three-bucket rule in Outputs.
- `the_one/agent/factory.py` `compose_system_prompt` call site — L5 hardcodes `auto_relay=True` (the new invariant) until L9 removes the kwarg entirely.

## Outputs

- `the_one/db/models.py:`_validate_config_reserved_keys`:
  - **UPDATE** the validator's class/method docstring at lines 195-204 to drop `auto_relay_platform_replies` from the enumerated reserved-keys list and add `always_listen` in its place. After this edit, `grep "auto_relay_platform_replies" the_one/db/models.py` returns at most one match (the strip-line's comment).
  - **REMOVE** the `auto_relay_platform_replies` shape-validation block (currently lines 429-437) entirely.
  - **ADD** an `always_listen` shape-validation block in its place:
    ```python
    # M11 F7 L5 — ``always_listen``: optional bool. Absent →
    # consume-time default-False (the policy gate at
    # ``_inbound.py`` reads ``account.config.get("always_listen", False)``).
    # Present → must be a bool; non-bool values rejected so the
    # operator can't accidentally smuggle truthy/falsy non-bools
    # through the kv-table editor path.
    if "always_listen" in value:
        always_listen = value["always_listen"]
        if not isinstance(always_listen, bool):
            raise ValueError(
                "config['always_listen'] must be a bool "
                "(True or False) when present; absent is treated as "
                "default-False at consume time"
            )
    ```
  - **ADD** a one-shot migration line BEFORE `return value` at the end of the validator (line 438):
    ```python
    # M11 F7 L5 — strip the legacy ``auto_relay_platform_replies``
    # key on every validate cycle. Existing rows with the key
    # continue to load (the reserved-keys validator above does
    # not touch it on read), but the first save after L5 lands
    # cleans the dict so persisted rows converge to the new
    # shape. Auto-relay became invariant in F7; the key carries
    # no useful information and is removed from the public
    # contract.
    value.pop("auto_relay_platform_replies", None)
    ```
- `the_one/connectors/_inbound.py` (F8 L11 auto-relay block, lines 744-789):
  - **REMOVE** the `auto_relay = account.config.get("auto_relay_platform_replies", True)` line (~772-774).
  - **REMOVE** the `if auto_relay:` conditional around the engaged-branch relay logic (~775+). The relay-if-not-already-sent-via-tool body becomes unconditional inside the engaged path. L8 will gate this entire block by the policy decision; for L5 the block runs whenever the dispatcher's existing pre-step accepts the inbound.
  - **UPDATE** the comment block at ~744-771 to reflect the invariant: drop the "opt-out via account.config" sentence; replace with a sentence stating auto-relay is invariant when engaged (post-F7) and the engagement decision is the policy gate's responsibility (L8).
- `the_one/agent/factory.py` (auto_relay computation block, lines 329-342):
  - **REMOVE** the entire `auto_relay = True` + `if connector_attached and ...` for-loop block (lines 329-342).
  - **UPDATE** the single `compose_system_prompt` call at lines 463-469: change the `auto_relay=auto_relay` kwarg (line 468) to hardcoded `auto_relay=True` (the post-F7 invariant) until L9 removes the kwarg entirely. Add a one-line comment above the call: `# M11 F7 L5: auto-relay is invariant when engaged; kwarg removal pending L9.` There is exactly ONE `compose_system_prompt` call site in this file.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — FIVE sites:
  - **REMOVE** the toggle render block including leading comment header (lines 538-570 — the "Auto-reply to platform messages (M10 F8 L11 HAT Fix #4)" comment header at 538-548 plus the control markup at 549-570).
  - **REMOVE** the form snapshot collection including leading comment (lines 1030-1035).
  - **REMOVE** the change listener including leading comment (lines 1160-1177). If the directive-codeblock update needs to fire on OTHER changes (e.g., the L11 always_listen toggle), L11 wires that hook; L5 just removes the auto-relay-driven hook.
  - **REMOVE** the config merge on form submission including leading comment (lines 1734-1745).
  - **REMOVE** the directive-codeblock helpers + render — the cycle-2-review-discovered fifth site: the constants `_DIRECTIVE_AUTO_RELAY_ON_DEFAULT` + `_DIRECTIVE_AUTO_RELAY_OFF_DEFAULT` and the helpers `_selectEffectiveDirective` + `_updateEffectiveDirectiveCodeblock` at lines ~188-213; the "Effective system prompt" codeblock render at lines 572-597; and the initial codeblock-update call at line 1169. After sites 1+3 removal these become dead code AND the codeblock would show stale UI; removing them in L5 is the clean atomic-leg-pattern move. (L11 may introduce a new always-listen-driven preview if needed — out of L5 scope.)
  - The resulting editor temporarily has no toggle UI for these concerns; L11 adds the new "Always Listen" toggle (account-level) + per-agent toggle.
- New tests in `tests/test_db_repositories.py` (replacing the two removed tests at 1557-1597):
  - `test_validate_config_accepts_always_listen_bool` — both True and False validate cleanly; absent is valid (consume-time default-False).
  - `test_validate_config_rejects_non_bool_always_listen` — rejects string "yes", int 1, None.
  - `test_validate_config_strips_legacy_auto_relay_platform_replies` — when the legacy key is in the input dict, the validator returns a dict that no longer contains it (regardless of the bool value).
  - `test_validate_config_strips_legacy_auto_relay_with_always_listen_present` — both keys in input: legacy stripped, always_listen retained.
  - `test_validate_config_accepts_legacy_auto_relay_value_in_input_silently` — input has `auto_relay_platform_replies: "not-a-bool"` (a string). The validator MUST NOT reject — it strips the key from the dict before returning (the strip happens regardless of value), so the row migrates cleanly even if the legacy value was somehow corrupt. (Edge defense; the strip-then-return order matters.)
- Updates to all OTHER tests that reference `auto_relay_platform_replies` — **three-bucket triage rule**:
  - **(a) Setup-only references with True/default**: tests setting `config["auto_relay_platform_replies"] = True` (or relying on the True default) → simply remove the key from the setup. It's the default invariant; the test setup is cleaner without it. No assertion changes needed.
  - **(b) Tests of removed opt-out semantics**: tests setting `config["auto_relay_platform_replies"] = False` AND asserting on the OFF-mode behavior (e.g., that the OFF directive renders, that the send_tool_enabled wording is used, that no auto-relay fires) → DELETE these tests. The opt-out is gone; the L8 policy-gate tests cover the new silence semantic. Named candidates flagged by cycle-2 review: `tests/test_factory.py::test_connector_attached_auto_relay_opt_out_includes_off_directive` and `tests/test_factory.py::test_connector_attached_multi_account_any_opt_out_wins` (around lines 614-712 — the two F8-L11-opt-out factory tests; safe to delete with the OFF-directive code path).
  - **(c) Tests using False as test isolation (NOT testing opt-out itself)**: tests in `tests/test_connectors_inbound.py:810-830, 836-869, 1253` use `auto_relay_platform_replies=False` to disable auto-relay so they can test some OTHER concern (e.g., visibility tagging on the pre-relay branch — these tests assert OPERATOR_VISIBILITY survives without being flipped by relay). After L5, relay fires unconditionally and these tests fail not because the opt-out is gone but because the relay flips visibility. Rewrite by monkeypatching `relay_client.send` (the client's send method) to a no-op — preserves the test's intent ("assert visibility tagging") without re-introducing the opt-out config. The Developer agent locates the actual variable / mock target in each test file; the pattern is "stub the platform-send side effect, not the config."
  - **Exhaustive file list** (six files, ~13 line refs total): `tests/test_factory.py` (lines 629, 644, 675), `tests/test_connectors_e2e_session.py` (line 159), `tests/_connector_dispatch_helpers.py` (line 144), `tests/test_connectors_inbound.py` (lines 815, 852, 1253, 1319, 1329), `tests/test_connectors_e2e_platform_send.py` (lines 204, 287), `tests/test_connectors_inbound_broadcast.py` (line 540). For each: classify into bucket (a) / (b) / (c) and apply the rule.

## Acceptance Criteria

- [ ] `the_one/db/models.py` `_validate_config_reserved_keys` validator no longer mentions `auto_relay_platform_replies` in its shape-validation logic AND `value.pop("auto_relay_platform_replies", None)` runs before the final `return value`.
- [ ] The validator has a new `always_listen` shape-validation block enforcing `bool when present`; rejects non-bool values; allows absent (consume-time default-False).
- [ ] `the_one/connectors/_inbound.py` (lines 744-789) no longer reads `account.config["auto_relay_platform_replies"]`; the relay path is unconditional (gated only by `already_sent_via_tool` short-circuit). Comment block updated to reflect the invariant.
- [ ] `the_one/agent/factory.py` (lines 329-342) no longer computes `auto_relay` from account configs; the `compose_system_prompt` call hardcodes `auto_relay=True` (with an L9-pending-kwarg-removal note).
- [ ] `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` no longer has the five `auto_relay_platform_replies`-touching sites (four data-field sites + the directive-codeblock helpers/render). `grep -n auto_relay_platform_replies the_one/interfaces/web/static/js/` returns NOTHING. `grep -n _DIRECTIVE_AUTO_RELAY the_one/interfaces/web/static/js/` returns NOTHING. `grep -n _selectEffectiveDirective the_one/interfaces/web/static/js/` returns NOTHING.
- [ ] `tests/test_db_repositories.py` has the five new validator tests listed in Outputs (replacing the two old tests).
- [ ] No Python test file references `auto_relay_platform_replies` after L5: `grep -rn auto_relay_platform_replies tests/` returns NOTHING. Any historical-context comments referencing the legacy key are removed alongside the setup keys — the legacy key is fully retired from the test suite.
- [ ] `docker exec the-one pytest tests/test_db_repositories.py tests/test_factory.py tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py tests/test_connectors_e2e_platform_send.py tests/test_connectors_inbound_broadcast.py -x --timeout 30` passes.
- [ ] Full suite at leg-end: `docker exec the-one pytest -x --timeout 60` — no L5-introduced regressions.
- [ ] Flight log L5 entry under `## Leg Progress` documents the leg; leg checked off in `flight.md` under `### Legs`. Leg artifact status set to `landed`.

## Verification Steps

- `grep -n auto_relay_platform_replies the_one/db/models.py` returns at most one match (the strip-line's comment) — the validator block is gone.
- `grep -n auto_relay_platform_replies the_one/connectors/_inbound.py the_one/agent/factory.py` returns NOTHING.
- `grep -n auto_relay_platform_replies the_one/interfaces/web/static/js/` returns NOTHING.
- `python -c "from the_one.db.models import ConnectorAccount; a = ConnectorAccount(id='x', name='n', type='stub', config={'auto_relay_platform_replies': True, 'always_listen': True}); print('auto_relay_platform_replies' in a.config, a.config.get('always_listen'))"` prints `False True` (legacy stripped, always_listen retained).
- `python -c "from the_one.db.models import ConnectorAccount; a = ConnectorAccount(id='x', name='n', type='stub', config={'always_listen': True}); print(a.config.get('always_listen'))"` prints `True`.
- `python -c "from the_one.db.models import ConnectorAccount; ConnectorAccount(id='x', name='n', type='stub', config={'always_listen': 'yes'})"` raises `ValueError` containing `"always_listen"`.
- Targeted suite: `docker exec the-one pytest tests/test_db_repositories.py tests/test_factory.py tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py tests/test_connectors_e2e_platform_send.py tests/test_connectors_inbound_broadcast.py -x --timeout 30` — all green.
- Full suite: `docker exec the-one pytest -x --timeout 60` — all green.

## Implementation Guidance

1. **Update `the_one/db/models.py` validator** per Outputs. Remove old block, add new block, add strip-line before return.

2. **Update `the_one/connectors/_inbound.py`** per Outputs:
   - Remove the `auto_relay = account.config.get(...)` line.
   - Remove the `if auto_relay:` conditional (de-indent the body).
   - Update the comment block — replace the "opt-out via account.config" sentence with "auto-relay is invariant on engaged turns (post-F7); the policy gate at L8 controls engagement."
   - Test the dispatcher tests pass after this change (the engaged behavior is unchanged for the True/default case).

3. **Update `the_one/agent/factory.py`** per Outputs:
   - Remove the `auto_relay = True` + for-loop block (lines 329-342).
   - At the single `compose_system_prompt` call site at lines 463-469, change the `auto_relay=auto_relay` kwarg at line 468 to hardcoded `auto_relay=True` with the M11 F7 L5 comment above the call. There is exactly ONE call site in this file.
   - Test the factory tests pass — these likely include factory creation tests that exercise the `auto_relay` parameter; those need to assert the new invariant (True always).

4. **Update the JS editor** per Outputs — five sites:
   - Remove the five code blocks at the cited line ranges (538-570 + 1030-1035 + 1160-1177 + 1734-1745 + the fifth site at 188-213 + 572-597 + 1169). Run grep confirmation passes for `auto_relay_platform_replies`, `_DIRECTIVE_AUTO_RELAY`, and `_selectEffectiveDirective` — all must return NOTHING.
   - Make sure the surrounding markup still renders cleanly (no orphan div / no orphan event listener registration / no orphan import of the removed constants).
   - Behavior note: the editor temporarily loses the "Effective system prompt" live-preview feature; L11's Always Listen toggle may reintroduce a preview if needed (out of L5 scope).

5. **Replace the validator tests** in `tests/test_db_repositories.py:1557-1597`:
   - Delete the two old tests.
   - Add the five new tests per Outputs.

6. **Triage and update OTHER test files** referencing `auto_relay_platform_replies` per the three-bucket rule in Outputs:
   - **Bucket (a) — setup-only references with True/default**: remove the key from the setup; no assertion changes needed.
   - **Bucket (b) — opt-out-semantics tests**: DELETE. Explicitly named deletion candidates: `tests/test_factory.py::test_connector_attached_auto_relay_opt_out_includes_off_directive` and `tests/test_factory.py::test_connector_attached_multi_account_any_opt_out_wins` (around lines 614-712). The L8 policy-gate tests cover the new silence semantic.
   - **Bucket (c) — test-isolation rewrite**: tests in `tests/test_connectors_inbound.py` around lines 810-830, 836-869, and 1253 that use `auto_relay_platform_replies=False` as test isolation (to stop the relay from interfering with the assertion target, not to test the opt-out itself) → REWRITE: monkeypatch the platform-send callable (e.g., `relay_client.send`) to a no-op so the test's actual assertion target (visibility tagging, etc.) survives. Do NOT delete these tests — they cover other surfaces. The Developer agent resolves the line ranges to test function names and rewrites each one.

7. **Run targeted tests, then full suite** per Verification Steps.

8. **Update flight log** under `## Leg Progress` with `### L5 — account-always-listen-storage-migration`. Check off in flight.md. Set L5 status to `landed`. Do NOT commit (F7 flight-level commit ordering).

## Edge Cases

- **Existing accounts with `auto_relay_platform_replies` AND no `always_listen`** — load cleanly (legacy key passes through the validator; new key absent → consume-time default-False). On first save after L5, legacy key is stripped, `always_listen=False` is the effective state. Bot becomes mentioned-only (the F7 default). Operator can flip to True via raw JSON edit before L11 ships the toggle UI.
- **Existing accounts with `always_listen` set somehow (impossible pre-L5)** — defensive: the validator accepts True/False, rejects non-bool. No realistic data path can produce this state before L5 lands.
- **JS form submission with no toggle UI** — the merge path at sites 2 and 4 is being removed; the saved config dict will not contain `auto_relay_platform_replies` (the toggle is gone). The validator strips any incoming `auto_relay_platform_replies` from existing rows; the JS path no longer writes it; the field is fully retired from the surface.
- **Tests that monkeypatch `account.config.get("auto_relay_platform_replies", True)` expecting the get-with-default pattern** — the `.get(..., True)` call sites are gone; monkeypatch tests targeting those sites need to be deleted or rewritten to monkeypatch the new policy-gate read (which is L8's surface).
- **Legacy-key strip during a validate-only flow** (e.g., admin tool calling `ConnectorAccount.model_validate(d)` without saving) — the strip happens at validate time, so the in-memory model has no `auto_relay_platform_replies` key even if the on-disk row still does. This is correct: the strip is the migration; any consumer reading the model sees the new shape.
- **Tests in `test_connectors_inbound.py:1319+` that test the OFF-mode opt-out** — these are the cleanest candidates for deletion (they document the removed behavior). The L8 policy-gate tests cover the new silence semantic.
- **Cross-stage concern (L9 system prompt simplification)** — L9 removes the `auto_relay=` kwarg from `compose_system_prompt`. L5 hardcodes the value `True` at the call sites; L9 deletes both the parameter and the L5 call-site hardcodes. The hardcoded `True` is a 2-leg-window expedient explicitly noted in the comment.

## Files Affected

- `the_one/db/models.py` — UPDATE `_validate_config_reserved_keys`: remove `auto_relay_platform_replies` validator, add `always_listen` validator, add strip-line.
- `the_one/connectors/_inbound.py` — UPDATE auto-relay block: drop config read; drop conditional; update comment.
- `the_one/agent/factory.py` — UPDATE: remove auto_relay computation; hardcode `auto_relay=True` at the single `compose_system_prompt` call site (line 463-469, kwarg at line 468).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — REMOVE five code blocks (sites 1-5, including the directive-codeblock helpers/render at lines 188-213 + 572-597 and the initial codeblock-update call at line 1169).
- `tests/test_db_repositories.py` — REPLACE two old validator tests with five new ones.
- `tests/test_factory.py`, `tests/test_connectors_inbound.py`, `tests/test_connectors_e2e_session.py`, `tests/_connector_dispatch_helpers.py`, `tests/test_connectors_e2e_platform_send.py`, `tests/test_connectors_inbound_broadcast.py` — TRIAGE per the three-bucket rule: (a) remove setup key, (b) delete test, (c) rewrite with monkeypatch.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight-log.md` — APPEND `## Leg Progress` entry.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight.md` — CHECK OFF leg.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (targeted + full suite)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Commit all changes — DEFERRED in F7 per `/agentic-workflow` flight-level commit ordering; do NOT commit per leg.

## Citation Audit

Citations verified against current code at design time via the F7 L5 reconnaissance pass:

- `the_one/db/models.py:422-436` — `auto_relay_platform_replies` validator (verified).
- `the_one/connectors/_inbound.py:744-789` — F8 L11 auto-relay block; config read at line 772-774 (verified).
- `the_one/agent/factory.py:329-342` — auto_relay computation block (verified).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — FIVE sites: 538-570, 1030-1035, 1160-1177, 1734-1745, AND the cycle-2-discovered fifth site at 188-213 + 572-597 + 1169 (directive-codeblock helpers/constants + render + initial codeblock-update call). Minor drift from flight DD's original four-site enumeration — cycle-2 review caught the fifth surface.
- `tests/test_db_repositories.py:1557-1597` — direct validator tests (verified).
- 6 other test files (~13 line-level references total) referencing `auto_relay_platform_replies` per recon grep: `tests/test_factory.py`, `tests/test_connectors_inbound.py`, `tests/test_connectors_e2e_session.py`, `tests/_connector_dispatch_helpers.py`, `tests/test_connectors_e2e_platform_send.py`, `tests/test_connectors_inbound_broadcast.py` (verified file paths).

The JS line ranges in the flight DD §8 are slightly drifted from current state; the recon recovered the actual current ranges. L5 uses the recon-confirmed ranges.
