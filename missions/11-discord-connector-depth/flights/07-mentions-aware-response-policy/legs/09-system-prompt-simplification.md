# Leg: system-prompt-simplification

**Status**: completed
**Flight**: [Mentions-Aware Response Policy](../flight.md)

## Objective

Drop `_CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE` entirely; rewrite `_CONNECTOR_AUTO_RELAY_DIRECTIVE` to reflect the F7 policy-gate behavior (mentions-aware engagement + auto-relay invariant when engaged + forward-references to L10's history tools); remove the `auto_relay` kwarg from `compose_system_prompt`; keep `send_tool_enabled` kwarg as a documented no-op for back-compat; clean up the 8 call sites + tests that exercise the now-removed OFF-mode path.

## Context

- **Flight DD §11** — Auto-relay is invariant in F7 (per DD §4 + L5). The OFF directive is dead code. The new ON directive informs the agent of:
  - Auto-relay invariant on engaged turns.
  - Engagement triggers per the L8 policy gate (mentions, DMs, `/talk_to` overrides, inference-yes turns).
  - L10-forthcoming history tools (`fetch_channel_history`, `fetch_thread_history`, `fetch_dm_history`, `list_visible_channels`) with "if available" hedging — the L9 directive forward-references these tools so the agent knows recent channel context can be reached via tools when L10 lands. The "if available" hedge keeps the prompt truthful until L10 ships (matching the existing OFF-directive pattern at config.py:99-100).
- **`send_tool_enabled` retained, no-op'd** — F5 R8 carryover; the factory still computes this for unrelated purposes (the F10 carve-out for pre-loading the send tool's schema). After L9, the directive is unconditional when `connector_attached=True`; `send_tool_enabled` is no longer consulted in the function body but stays in the signature.
- **`mechanical-fallback-prompt-truth-pairing` convention** — the new directive accurately describes both the auto-relay invariant AND the policy gate's existence; the agent knows the inference call may have decided to silence non-mentioned messages (the agent never sees those — they don't reach `agent.step` — but the directive's mention of the policy gate makes the system self-describing for debugging).
- **L5 already cleaned up the JS side** — `_DIRECTIVE_AUTO_RELAY_ON_DEFAULT` / `_DIRECTIVE_AUTO_RELAY_OFF_DEFAULT` JS constants AND helpers were removed in L5 (cycle-1 review of L5 caught the fifth JS site). Verified by recon: `grep _DIRECTIVE_AUTO_RELAY_ the_one/interfaces/web --include="*.js"` returns nothing. The F5 R14 KEEP-IN-SYNC concern is already resolved — Python is now the sole source of truth.
- **L5's hardcoded `auto_relay=True`** — L5 set the call site at `factory.py:433` to `auto_relay=True` with a TODO comment noting "L9 will remove the kwarg entirely." L9 closes that TODO.
- **L5 test triage already deleted the explicit opt-out tests** — `test_connector_attached_auto_relay_opt_out_includes_off_directive` and `test_connector_attached_multi_account_any_opt_out_wins` were deleted at L5 per cycle-1 review of L5 bucket (b). The remaining tests in test_config.py + test_factory.py that pass `auto_relay=False` need either deletion (if they exercise the OFF directive path) or signature simplification (if they happen to pass auto_relay=False but don't assert OFF-specific behavior).

## Inputs

- L1-L8 landed uncommitted; F7 policy gate is active.
- `the_one/agent/config.py:73-88` — `_CONNECTOR_AUTO_RELAY_DIRECTIVE` constant (current ON-directive text).
- `the_one/agent/config.py:90-107` — `_CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE` constant (to delete).
- `the_one/agent/config.py:110-170` — `compose_system_prompt` function (current signature has `auto_relay: bool = True` kwarg).
- `the_one/agent/config.py:162-166` — directive dispatch logic (currently branches on `auto_relay`; L9 removes the branch and unconditionally appends the new ON-only directive when `connector_attached=True`).
- `the_one/agent/factory.py:433` — call site, currently `auto_relay=True` post-L5.
- `the_one/agent/config.py:394` — `AgentConfig.get_system_prompt()` call site, currently `auto_relay=True`.
- 6 test call sites in `tests/test_config.py` (lines 218, 224, 248, 270, 277, 312) per recon.
- `tests/test_factory.py:605-650` — two factory tests exercising directive text (`test_connector_attached_tool_enabled_default_auto_relay_includes_auto_relay_directive`, `test_connector_attached_tool_disabled_uses_on_directive_when_relay_on`).
- `tests/browser/test_flow_studio_connector_directive_section.py:35-194` — browser tests exercising the directive section (may need updates if they reference the OFF directive text).

## Outputs

- `the_one/agent/config.py`:
  - **DELETE** `_CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE` constant (lines 90-107) entirely.
  - **REWRITE** `_CONNECTOR_AUTO_RELAY_DIRECTIVE` (lines 73-88) per the new shape — describes the F7 policy-gate-engagement model + auto-relay invariant + forward-references to L10's history tools. Suggested text:
    ```python
    _CONNECTOR_AUTO_RELAY_DIRECTIVE = (
        "This conversation is attached to a connector account on an external "
        "platform (Discord, Slack, etc.). You only see messages the system "
        "has decided to engage you on — direct messages, mentions of you, "
        "explicit `/talk_to` redirects from peers, or messages a lightweight "
        "inference pre-step decided are worth your response (the operator "
        "can configure this per-account). Messages the inference step "
        "silenced never reach you and are intentionally invisible.\n\n"
        "Auto-relay is on: your plaintext replies in this session ARE "
        "automatically delivered to platform peers — treat the conversation "
        "as the platform conversation itself. Do NOT ask the operator for "
        "permission to respond on the platform; do NOT narrate that you're "
        "'using send_to_platform_channel'; just reply naturally as you "
        "would in any chat. Messages tagged ``visibility=\"platform\"`` in "
        "the history came from platform peers; messages tagged "
        "``visibility=\"operator\"`` came from the operator's private "
        "local Chat console (operator-only — these are NOT relayed).\n\n"
        "If you need recent channel context beyond what's in this session "
        "(e.g. catching up after a silent stretch), use the "
        "``fetch_channel_history`` / ``fetch_thread_history`` / "
        "``fetch_dm_history`` tools if available. Use ``list_visible_channels`` "
        "to discover which channels and peers you can read. If you need to "
        "send a message to a different channel or thread on the platform "
        "(not the current one), use the ``send_to_platform_channel`` tool "
        "explicitly with a target specifying the destination."
    )
    ```
    Note: forward-references to L10's tools (`fetch_*_history`, `list_visible_channels`) use "if available" hedging — the directive is truthful for both pre-L10 and post-L10 states. After L10 lands, the agent has the tools and they actually exist; until then, the agent simply gets `"tool not available"` errors if it calls them.
  - **REMOVE** the `auto_relay` kwarg from `compose_system_prompt` signature. The new signature:
    ```python
    def compose_system_prompt(
        base: str,
        persona: str,
        *,
        connector_attached: bool = False,
        send_tool_enabled: bool = False,
    ) -> str:
    ```
  - **UPDATE** the directive dispatch in the function body — drop the `if auto_relay / else` branch; unconditionally append `_CONNECTOR_AUTO_RELAY_DIRECTIVE` when `connector_attached=True`:
    ```python
    if connector_attached:
        parts.append(_CONNECTOR_AUTO_RELAY_DIRECTIVE)
    ```
  - **UPDATE** the function docstring — remove the `auto_relay` parameter description; note that `send_tool_enabled` is retained for callers (factory's F10 carve-out for pre-loading the send tool's schema) but is no longer consulted in directive selection (the new directive's wording covers both tool-enabled and tool-disabled cases via the explicit `send_to_platform_channel` mention).
- `the_one/agent/factory.py:433`:
  - **REMOVE** the `auto_relay=True` kwarg from the `compose_system_prompt` call. Drop the L5 TODO comment about "L9 will remove the kwarg entirely" (it's done).
- `the_one/agent/config.py:394` (`AgentConfig.get_system_prompt`):
  - **REMOVE** the `auto_relay=True` kwarg from the call.
- `tests/test_config.py` (TestComposeSystemPrompt class at lines 212-342):
  - **DELETE** the tests that exercise the now-removed OFF-directive path. Cycle-1 review enumerated:
    - `test_connector_attached_auto_relay_off_includes_off_directive` (around line 259, the `auto_relay=False` + `send_tool_enabled=True` case)
    - `test_connector_attached_send_disabled_uses_off_directive_when_relay_on` (around line 300, the `auto_relay=False` + `send_tool_enabled=False` case)
    - `test_off_directive_carries_if_available_hedge` (around line 290) — pins the OFF directive's wording contract, disappears with the constant.
    - Any other test that asserts on `_CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE` text appearing.
  - **UPDATE** the remaining tests to remove the `auto_relay=True` / `auto_relay=False` kwargs from their `compose_system_prompt` calls. The 4 surviving tests:
    - `test_non_connector_no_persona_returns_base_only` (line 215) — no change (no kwargs).
    - `test_non_connector_with_persona_appends_after_separator` (line 222) — no change.
    - `test_connector_attached_auto_relay_on_includes_auto_relay_directive` (line 239) — rename to `test_connector_attached_includes_auto_relay_directive`; remove `auto_relay=True` kwarg; assertion stays (the directive is now unconditional when connector_attached=True).
    - `test_connector_attached_auto_relay_on_tool_disabled_includes_on_directive` (line 305-330) — same renaming + kwarg removal. The "tool disabled" angle remains relevant (the directive references `send_to_platform_channel` regardless of tool enablement; the test pins this).
  - **REMOVE** the import of `_CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE` from any surviving test that imported it.
- `tests/test_factory.py`:
  - **REMOVE** the import of `_CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE`.
  - **REMOVE** the two `assert _CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE not in agent.system_prompt` assertions at lines 622 and 650 (post-L9 they're vacuous NameErrors anyway).
  - Keep both `test_connector_attached_tool_disabled_uses_on_directive_when_relay_on` and `test_connector_attached_tool_enabled_default_auto_relay_includes_auto_relay_directive` — they pin that the engaged default directive lands; rename to drop the `_default_auto_relay` infix and just assert the ON directive appears. Update any `auto_relay` setup in the test bodies to remove the kwarg.
  - Optionally scrub stale `# auto_relay` comments at lines 123 and 648 to avoid future-reader confusion.
- `tests/browser/test_flow_studio_connector_directive_section.py`:
  - **DELETE THE ENTIRE FILE.** L5's flight-log entry confirms the UI surface this file exercises (the `[data-testid="connector-account-effective-directive-codeblock"]` codeblock + auto-reply toggle reactive swap) was removed in L5's fifth JS site clean-up. Cycle-1 review of L9 verified zero JS occurrences of the directive constants or the codeblock testid remain post-L5; the file's tests are broken-or-skipping and pin nothing meaningful. F5's debrief missed this side effect of the L5 removal; L9 closes the gap.

## Acceptance Criteria

- [ ] `_CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE` constant no longer exists in `the_one/agent/config.py`. `grep _CONNECTOR_AUTO_RELAY_OFF the_one/` returns NOTHING (Python side) and `grep _CONNECTOR_AUTO_RELAY_OFF tests/` returns NOTHING.
- [ ] `_CONNECTOR_AUTO_RELAY_DIRECTIVE` has been rewritten to describe the policy-gate engagement model + auto-relay invariant + forward-references to L10's `fetch_*_history` and `list_visible_channels` tools with "if available" hedging.
- [ ] `compose_system_prompt` signature has no `auto_relay` parameter; the function body unconditionally appends `_CONNECTOR_AUTO_RELAY_DIRECTIVE` when `connector_attached=True`.
- [ ] `send_tool_enabled` kwarg remains in the signature but is documented as a no-op (the docstring explains why it stays).
- [ ] All 8 call sites (2 non-test + 6 test) no longer pass `auto_relay=...`.
- [ ] OFF-directive-specific tests are deleted; ON-directive tests are renamed (drop the `_auto_relay_on` suffix) and assertions are unchanged (the directive is now unconditional).
- [ ] `docker exec the-one pytest tests/test_config.py tests/test_factory.py -x --timeout 30` passes (modified + deleted tests).
- [ ] `tests/browser/test_flow_studio_connector_directive_section.py` is DELETED entirely — the UI surface it exercises was removed in L5's fifth JS site clean-up.
- [ ] Full suite at leg-end: `docker exec the-one pytest -x --timeout 60` — no L9-introduced regressions.
- [ ] Flight log L9 entry under `## Leg Progress` documents the leg; leg checked off in `flight.md`; status set to `landed`.

## Verification Steps

- `grep -n "_CONNECTOR_AUTO_RELAY_OFF" the_one/` returns NOTHING.
- `grep -rn "_CONNECTOR_AUTO_RELAY_OFF" tests/` returns NOTHING.
- `grep -n "auto_relay" the_one/agent/config.py the_one/agent/factory.py` returns NOTHING (kwarg removed from signature + call sites + docstrings).
- `grep -rn "auto_relay=" the_one/ tests/ --include="*.py"` returns NOTHING.
- `grep -n "fetch_channel_history\|fetch_thread_history\|fetch_dm_history\|list_visible_channels" the_one/agent/config.py` returns at least one match (the new directive references these).
- `grep -n "send_tool_enabled" the_one/agent/config.py` returns the signature and docstring mentioning it (kwarg retained, body doesn't consult).
- Targeted: `docker exec the-one pytest tests/test_config.py tests/test_factory.py -x --timeout 30` — all green.
- Full suite: `docker exec the-one pytest -x --timeout 60` — all green.

## Implementation Guidance

1. **Update `the_one/agent/config.py`**:
   - Delete `_CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE` (lines 90-107).
   - Rewrite `_CONNECTOR_AUTO_RELAY_DIRECTIVE` (lines 73-88) per the Outputs code sketch. Use multi-paragraph structure (separate paragraphs for engagement-model, auto-relay invariant, history tools).
   - Remove `auto_relay` from `compose_system_prompt` signature; simplify the function body to unconditional directive append when `connector_attached=True`.
   - Update docstring — remove `auto_relay` parameter, retain `send_tool_enabled` with a clear "retained for back-compat; not consulted in directive selection" note.

2. **Update `the_one/agent/factory.py:433`**:
   - Remove the `auto_relay=True` kwarg from the `compose_system_prompt` call.
   - Drop the L5 `# M11 F7 L5: auto-relay is invariant when engaged; kwarg removal pending L9.` comment (the kwarg is now gone — comment is stale).

3. **Update `the_one/agent/config.py:394`** (AgentConfig.get_system_prompt):
   - Remove the `auto_relay=True` kwarg from the call.

4. **Triage `tests/test_config.py:TestComposeSystemPrompt`** per Outputs:
   - DELETE the OFF-directive tests (lines ~265-285 area).
   - RENAME + UPDATE the surviving ON-directive tests to drop `_auto_relay_on` from their names and `auto_relay=True` from their kwargs.
   - REMOVE the import of `_CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE` from the test file.

5. **Triage `tests/test_factory.py`** — read each remaining auto_relay-touching test and decide DELETE vs UPDATE per the same rule. The L5 cycle-1-review-named tests (`test_connector_attached_auto_relay_opt_out_includes_off_directive` and `test_connector_attached_multi_account_any_opt_out_wins`) were already deleted at L5; any other `auto_relay`-mentioning tests in this file get the same treatment.

6. **Triage `tests/browser/test_flow_studio_connector_directive_section.py`**:
   - If the test asserts on the OFF-directive text appearing somewhere → update to match the new directive OR delete if the assertion is about a UI surface that's been removed (L5 removed the codeblock helpers).
   - If the test asserts the directive section renders at all → likely still relevant after L9 (the new directive is still shown in the UI surface).

7. **Run targeted tests**, then full suite. Update flight log under `## Leg Progress` with `### L9 — system-prompt-simplification`. Check off in flight.md. Set L9 status to `landed`. Do NOT commit.

## Edge Cases

- **Forward-references to L10's tools** — the new directive mentions `fetch_channel_history`, `fetch_thread_history`, `fetch_dm_history`, `list_visible_channels` with "if available" hedging. Pre-L10, the agent has these tools NOT registered in its toolkit; the prompt mentions them but the agent's tool schema won't include them. The agent may attempt to call them and get a "tool not available" error — which is the same shape as today's `send_to_platform_channel`-when-disabled error. Acceptable per the `mechanical-fallback-prompt-truth-pairing` discipline.
- **`send_tool_enabled` is no-op in body but retained in signature** — the docstring must be explicit so a future reader doesn't think the kwarg is dead. The Developer agent writes a clear comment like:
  ```
  send_tool_enabled: retained for callers (notably the factory) that compute
  it for unrelated purposes — the factory uses this for tool-enable / pre-load
  decisions in F10. NOT consulted in directive selection — the directive
  is unconditional when connector_attached=True.
  ```
- **Test gain/loss math** — L9 deletes ~3-4 tests (OFF-directive paths) and renames/updates ~4 tests (ON-directive paths). Net test count: -3 to -4. Suite count drops slightly but test coverage is unchanged (the removed tests covered behavior that no longer exists).
- **Browser tests** — if `test_flow_studio_connector_directive_section.py` exercises the directive-section UI surface AND L5 removed that UI surface (the directive-codeblock render was site 5 of L5's removal), the test may already be failing post-L5 or skipping. The Developer agent reads the test and verifies its current state at L9 entry.
- **Persona text after directive** — the function body's `if persona:` clause is unchanged. Order: base → directive (if connector_attached) → separator → persona. Existing tests pin this ordering; L9 doesn't change it.
- **Cross-leg test interactions** — L8's policy-gate tests don't assert on directive text directly; they're orthogonal to L9. L7's inference tests use stub providers; they don't care about the directive. L4's provider-projection tests work on Message objects; orthogonal. L9 is self-contained for tests.

## Files Affected

- `the_one/agent/config.py` — DELETE `_CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE`; REWRITE `_CONNECTOR_AUTO_RELAY_DIRECTIVE`; REMOVE `auto_relay` kwarg from `compose_system_prompt`; UPDATE function body + docstring; REMOVE `auto_relay=True` from `get_system_prompt` call.
- `the_one/agent/factory.py` — REMOVE `auto_relay=True` from `compose_system_prompt` call.
- `tests/test_config.py` — DELETE OFF-directive tests; RENAME + UPDATE ON-directive tests; REMOVE OFF import.
- `tests/test_factory.py` — TRIAGE auto_relay-mentioning tests (delete OFF-specific, update others).
- `tests/browser/test_flow_studio_connector_directive_section.py` — TRIAGE per the Developer's read at impl time.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight-log.md` — APPEND L9 entry.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight.md` — CHECK OFF leg.

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing (targeted + full suite)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md
- [ ] Commit all changes — DEFERRED per F7 flight-level commit ordering.

## Citation Audit

Citations verified against current code at design time via the F7 L9 reconnaissance pass:

- `the_one/agent/config.py:73-88` — `_CONNECTOR_AUTO_RELAY_DIRECTIVE` (verified).
- `the_one/agent/config.py:90-107` — `_CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE` (verified; to delete).
- `the_one/agent/config.py:110-170` — `compose_system_prompt` signature + body (verified).
- `the_one/agent/config.py:162-166` — directive dispatch (verified).
- `the_one/agent/factory.py:433` — call site, post-L5 hardcoded `auto_relay=True` (verified).
- `the_one/agent/config.py:394` — `AgentConfig.get_system_prompt` call site (verified).
- `tests/test_config.py:212-342` — `TestComposeSystemPrompt` class with 6 test methods (verified).
- `tests/test_factory.py:605-650` — two factory tests touching the directive (verified).
- `tests/browser/test_flow_studio_connector_directive_section.py:35-194` — browser tests (file path verified; specific assertions pending Developer-agent triage).
- L5's JS removal of `_DIRECTIVE_AUTO_RELAY_*` constants confirmed (no remaining JS sites).
