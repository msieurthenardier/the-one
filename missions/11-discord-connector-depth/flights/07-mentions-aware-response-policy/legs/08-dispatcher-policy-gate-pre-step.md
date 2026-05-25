# Leg: dispatcher-policy-gate-pre-step

**Status**: completed
**Flight**: [Mentions-Aware Response Policy](../flight.md)

## Objective

Insert a new "policy gate" pre-step between the dispatcher's command-intercept fallthrough (step 11) and the per-session lock + `agent.step` block (step 12) in `the_one/connectors/_inbound.py`. The gate decides engaged-vs-silent per Flight DD §1 five-path decision tree. Silent branches terminal-return with a `policy-silent` routing audit entry (no session lock, no `update_last_inbound`, no agent build, no `agent.step`, no auto-relay, no WS broadcast). Engaged branches flow through unchanged. This is the pivotal leg that activates the F7 behavioral change.

## Context

- **Flight DD §1 decision tree** (in order; first match wins):
  1. `envelope.raw["is_dm"]` is True → engage (DMs ignore policy gate)
  2. `decision.scope == "override"` → engage (peer's explicit `/talk_to` bypasses policy)
  3. `plugin.is_mention(envelope)` returns True → engage (explicit @mention)
  4. `account.config["always_listen"]` AND `agent_config.connector_always_listen[account_id]` both True → run inference; engage if "yes"
  5. Otherwise → silent
- **Flight DD §13 (silent terminal-return semantics)**:
  - Silent branches return from `dispatch_inbound` immediately after appending the audit entry.
  - NO `async with session_locks[session_row.id]` acquired.
  - NO `update_last_inbound` called (silent turns don't extend the continuation window — mirrors F6 Deny / NeedsPairing-failure precedent at step 6).
  - NO agent built; NO `agent.step` called.
  - NO auto-relay (lives inside the engaged branch's step 12).
  - NO WS broadcast (silent turns don't surface in the Chat UI per DD §3 privacy invariant).
  - The audit append at `session_metadata["routing"]` IS the only side effect (plus the silent decision log line).
- **Routing-audit shape extension** — the silent-branch audit entry is a NEW list entry on `session_metadata["routing"]` with `disposition = "policy-silent"` and a NEW `policy` sub-dict containing the decision-tree outcome path + inference details (if inference ran). Engaged paths keep their existing entries unchanged (disposition stays `"stepped"` / `"command-intercepted"` etc.); enriching engaged-path entries with the policy sub-block is OUT OF L8 scope (F9 audit-log inspector can read engaged entries' implicit "non-silent" disposition).
- **Audit log free-shape** — `ChatSession.session_metadata` is `dict[str, Any] | None`; no Pydantic constraint. The new disposition string `"policy-silent"` and the `policy` sub-block sit naturally.
- **Plugin-hook consultation** — `getattr(plugin, "is_mention", _default_no_mention)(envelope)` mirrors the F8 L6 `is_dm` consult pattern at `_routing.py:168-171`. `_default_no_mention` (added by L1) returns False, preserving silent-by-default for plugins without a mention concept (stub, webhook).
- **Always-listen reads** — L5 ships `account.config["always_listen"]` (default False per DD §4); L6 ships `agent_config.connector_always_listen: dict[str, bool] | None`. Both reads at decision-tree step 4. Per DD §8 ("accept-and-document"), the per-agent True with account-level False is structurally inert — the account check short-circuits.
- **Inference call** — when step 4 fires (both toggles True), invoke `run_engagement_inference(account, envelope, session_messages, settings, provider_repo, fallback_provider_config_id, fallback_llm_model)`. The L7 function returns bool; True → engage, False → silent.
- **Session_messages source** — the session row is resolved at step 5 (BEFORE the gate). The session's history is available via the resolved `db_session_for_routing` (variable name per recon, around _inbound.py:357). Decode the persisted messages JSON via `decode_messages` (imported at line 157 of _inbound.py).
- **Provider_repo construction** — instantiate inside the gate: `LLMProviderRepository(conn, encryptor)` — `conn` is in scope from step 1's `get_connection()`; `encryptor` is available via the function-local import pattern (step 1).
- **Fallback id + model** — `fallback_provider_config_id = agent_config.provider_config_id` (the routed agent's provider id); `fallback_llm_model = agent_config.llm_model` (the routed agent's model name). Both are AgentConfig fields verified by recon.

## Inputs

- L1-L7 landed uncommitted.
- `the_one/connectors/_inbound.py` post-L5 12-step dispatcher with:
  - Step 5 (session resolve) at lines ~258-269 — provides `db_session_for_routing` (or equivalent variable; the Developer agent confirms the exact name at impl time).
  - Step 11 (command-intercept fallthrough) at lines 470-583 — `parsed` is None OR the builtin/plugin handler returned None → fall through.
  - Step 12 (per-session lock + agent.step) at lines 587-866 — disposition set to "stepped" at line 589; audit append at 590-593; lock acquire at 595; `update_last_inbound` at 598.
- `the_one/connectors/_acl.py:_default_no_mention` (L1 addition).
- `the_one/connectors/_discord.py:DiscordPlugin.is_mention` (L1 addition).
- `the_one/connectors/_inference.py:run_engagement_inference` (L7 addition) with the signature `(account, envelope, session_messages, settings, provider_repo, fallback_provider_config_id, fallback_llm_model) -> bool`.
- `the_one/agent/config.py:AgentConfig` with `connector_always_listen` (L6) and existing `provider_config_id` + `llm_model` fields.
- `the_one/db/models.py:ConnectorAccount` with `always_listen` validator (L5).
- `the_one/connectors/_routing.py:RoutingDecision` with `scope` field (override path verified).
- `the_one/db/codec.py:decode_messages` for parsing session.messages JSON.
- `tests/test_connectors_inbound.py` — existing dispatcher tests + the F6 Deny precedent (silent-return without lock).
- `tests/_connector_dispatch_helpers.py:_seed_provider_and_agent`, `_envelope`, etc. — test scaffolding.

## Outputs

- `the_one/connectors/_inbound.py`:
  - **Imports** — `decode_messages` is already imported at module top (line 157 — confirmed by recon). Add to the function-local imports at step 1 (top of `dispatch_inbound`):
    - `from the_one.connectors._acl import _default_no_mention`
    - `from the_one.connectors._inference import run_engagement_inference`
    - `from the_one.db.repositories import LLMProviderRepository` (NOT currently imported in `_inbound.py` — add it alongside `ChatSessionRepository`, `ConnectorAccountRepository`, `SQLiteAgentStore`).
  - **New helper function** at module-private level (above `dispatch_inbound`), named `_policy_gate_decision`. Returns a tuple `(should_engage: bool, policy_audit: dict[str, Any])` so the caller can append the audit even on engaged paths if needed (engaged paths in L8 do NOT append; the helper just exposes the decision shape for symmetry + testability):
    ```python
    async def _policy_gate_decision(
        *,
        envelope: InboundEnvelope,
        account: ConnectorAccount,
        agent_config: AgentConfig,
        plugin: ConnectorPlugin,
        decision: RoutingDecision,
        session_messages: list[Message],
        conn: Any,  # aiosqlite connection
        encryptor: Encryptor,
        settings: Settings,
    ) -> tuple[bool, dict[str, Any]]:
        """Evaluate the F7 policy gate (Flight DD §1 five-path decision tree).

        Returns ``(should_engage, policy_audit)``:
        - ``should_engage`` — True → proceed to step 12; False → silent terminal-return.
        - ``policy_audit`` — dict describing the decision path, suitable for embedding
          in ``session_metadata["routing"]`` under the ``policy`` key.

        Decision tree (first match wins):
        1. envelope.raw["is_dm"] → engage; outcome="dm".
        2. decision.scope == "override" → engage; outcome="override".
        3. plugin.is_mention(envelope) → engage; outcome="mention".
        4. account.always_listen AND agent.connector_always_listen[account_id] → run inference;
           outcome="inference-yes" (engage) or "inference-no" (silent).
        5. Otherwise → silent; outcome="always-listen-off" (with sub-reason indicating
           which toggle was False).
        """
        # 1. DM
        if envelope.raw.get("is_dm") is True:
            return True, {"outcome": "dm"}
        # 2. Override
        if decision.scope == "override":
            return True, {"outcome": "override"}
        # 3. Mention
        is_mention_fn = getattr(plugin, "is_mention", _default_no_mention)
        if is_mention_fn(envelope):
            return True, {"outcome": "mention"}
        # 4. Always-listen composition
        account_listen = account.config.get("always_listen", False)
        agent_listen_dict = agent_config.connector_always_listen
        agent_listen = (
            agent_listen_dict.get(account.id, False)
            if agent_listen_dict is not None
            else False
        )
        if not account_listen:
            return False, {
                "outcome": "always-listen-off",
                "account_always_listen": False,
                "agent_always_listen": agent_listen,
            }
        if not agent_listen:
            return False, {
                "outcome": "always-listen-off",
                "account_always_listen": True,
                "agent_always_listen": False,
            }
        # Both toggles True → inference
        provider_repo = LLMProviderRepository(conn, encryptor)
        engaged = await run_engagement_inference(
            account=account,
            envelope=envelope,
            session_messages=session_messages,
            settings=settings,
            provider_repo=provider_repo,
            fallback_provider_config_id=agent_config.provider_config_id,
            fallback_llm_model=agent_config.llm_model,
        )
        outcome = "inference-yes" if engaged else "inference-no"
        return engaged, {
            "outcome": outcome,
            "account_always_listen": True,
            "agent_always_listen": True,
            "inference_provider_id": (
                settings.inference_provider_config_id
                or agent_config.provider_config_id
            ),
            "inference_model": (
                settings.inference_model
                or agent_config.llm_model
            ),
        }
    ```
  - **Gate insertion site** in `dispatch_inbound` — between current step 11 (command-intercept fallthrough at lines 470-583) and step 12 (lock + agent.step starting at line 587). The new block:
    ```python
    # Step 11.5 (M11 F7 L8): policy gate.
    # Decides engaged-vs-silent per Flight DD §1 decision tree before
    # the per-session lock acquires. Silent branches terminal-return
    # with an audit-only side effect (no lock, no update_last_inbound,
    # no agent build, no agent.step, no auto-relay, no WS broadcast —
    # mirrors the F6 Deny / NeedsPairing-failure precedent at step 6).
    #
    # The engaged branch flows through to step 12 unchanged; the policy
    # sub-block is NOT embedded in the engaged-path audit entry (F9's
    # audit-log inspector reads engaged entries' implicit non-silent
    # disposition).
    session_messages = decode_messages(db_session_for_routing.messages)
    should_engage, policy_audit = await _policy_gate_decision(
        envelope=working_envelope,
        account=account,
        agent_config=agent_config,
        plugin=plugin,
        decision=decision,
        session_messages=session_messages,
        conn=conn,
        encryptor=encryptor,
        settings=settings,
    )
    if not should_engage:
        # Silent terminal-return per DD §13.
        audit_entry["disposition"] = "policy-silent"
        audit_entry["policy"] = policy_audit
        await chat_repo.append_to_session_metadata(
            session_row.id,
            "routing",
            audit_entry,
        )
        logger.info(
            "dispatch_inbound: policy gate silent on envelope "
            "(account=%s, channel=%s, peer=%s, outcome=%s); "
            "no engagement without mention/override/inference consent",
            account_id,
            working_envelope.channel_id,
            working_envelope.peer_id,
            policy_audit.get("outcome"),
        )
        return
    # Engaged → flow through to step 12 (lock + agent.step).
    # audit_entry is NOT appended here; step 12 sets disposition="stepped"
    # and appends. The silent path above is the only L8 append site.
    ```
  - **`agent_config` resolution** — cycle-1 review verified `agent_config` is NOT in scope at the gate position. Resolve it from the already-loaded `eligible_attached_agents` list by name match (no extra DB round-trip):
    ```python
    agent_config = next(
        a for a in eligible_attached_agents if a.name == decision.agent
    )
    ```
    Guaranteed to succeed because `decision.agent` is selected from this same list by `resolve_routing` (step 7).
  - **`db_session_for_routing` variable** — verified by recon at `_inbound.py:357`. Use this variable name verbatim. The session row was resolved at step 5 (line 263 — `session_row`) and re-fetched at line 357 (`db_session_for_routing = await chat_repo.get(session_row.id)`). At the gate position, both variables exist; the gate uses `db_session_for_routing.messages` for the inference history (the post-routing snapshot).
- New tests in `tests/test_connectors_inbound.py` (or a new file `tests/test_connectors_policy_gate.py` — the Developer agent decides at impl time based on file size). Tests cover each branch of the decision tree:
  - `test_policy_gate_engages_on_dm` — `envelope.raw["is_dm"] = True` → dispatcher calls agent.step + persists USER/ASSISTANT messages.
  - `test_policy_gate_engages_on_override` — `session_metadata["routing_override"] = "agent-name"` produces `decision.scope == "override"` → engaged.
  - `test_policy_gate_engages_on_mention` — `DiscordPlugin.is_mention` returns True (synthesize via stub or monkeypatch the plugin's `is_mention` to True) → engaged.
  - `test_policy_gate_silent_when_account_always_listen_off` — account.config has no always_listen (or False); no mention, no DM, no override → silent. Verify NO USER/ASSISTANT messages in history; verify routing audit has one entry with `disposition="policy-silent"` and `policy.outcome="always-listen-off"`.
  - `test_policy_gate_silent_when_account_on_agent_off` — account True, agent dict empty or False for this account → silent.
  - `test_policy_gate_engages_on_inference_yes` — both toggles True, monkeypatch `run_engagement_inference` to return True → engaged.
  - `test_policy_gate_silent_on_inference_no` — both toggles True, monkeypatch `run_engagement_inference` to return False → silent; audit has `policy.outcome="inference-no"`.
  - `test_policy_gate_silent_on_inference_exception` — both toggles True, monkeypatch `run_engagement_inference` to raise → silent (the inference function itself returns False on exception; L8 gate sees False as silent). Strictly speaking, this exercises L7's safe-default; the L8 test asserts the dispatcher silently returns rather than crashes.
  - `test_policy_gate_silent_branch_does_not_acquire_session_lock` — verify `update_last_inbound` is NOT called on the silent path (assertion: session's `last_inbound_at` is None or unchanged from pre-dispatch).
  - `test_policy_gate_silent_branch_does_not_call_agent_step` — verify factory.create / agent.step are not invoked (use a scripted factory that fails if called, OR assert that no ASSISTANT messages appear in history).
  - `test_policy_gate_silent_branch_appends_routing_audit_with_policy_subblock` — assert the audit entry has `disposition="policy-silent"`, `policy` is a dict, `policy.outcome` is one of the expected strings.
  - `test_policy_gate_engaged_audit_disposition_stepped` — engaged paths (DM/override/mention/inference-yes) hit step 12 → audit entry has `disposition="stepped"` (existing engaged path; pin that L8 didn't break it).
  - `test_policy_gate_inference_path_uses_correct_provider_and_model_fallbacks` — both toggles True, settings.inference_provider_config_id unset → `run_engagement_inference` is called with `fallback_provider_config_id=agent.provider_config_id` and `fallback_llm_model=agent.llm_model`. Use a mocked inference function to verify the kwargs.
  - `test_policy_gate_audit_has_silent_branch_for_command_no_response_fallthrough` — a command parses but the handler returns None (fallthrough); the gate then evaluates and may go silent. Assert the silent audit lands as expected. (This pins the L11 command-fallthrough interaction with the gate.)
  - `test_policy_gate_command_intercept_in_dm_does_not_invoke_gate` — DM message with text `/help` hits step 11's command-intercept path; the audit entry has `disposition="command-intercepted"` (NOT "policy-silent" and NOT "stepped"); the gate never runs. Pins DD §1's "DMs ignore policy gate" against the step-11-before-gate ordering reality.

## Acceptance Criteria

- [ ] `the_one/connectors/_inbound.py` has a new `_policy_gate_decision` async helper above `dispatch_inbound`, implementing the five-path decision tree per DD §1 and returning `(bool, dict)`.
- [ ] `dispatch_inbound` invokes the gate between step 11 (command-intercept fallthrough) and step 12 (lock + agent.step). Silent branches `return` early after appending the audit entry; engaged branches flow through to the existing step 12.
- [ ] The silent-branch audit entry has `disposition="policy-silent"` and a `policy` sub-dict with `outcome` ∈ {`"always-listen-off"`, `"inference-no"`}.
- [ ] Engaged-branch paths (DM, override, mention, inference-yes) flow through step 12 unchanged; their audit entries keep `disposition="stepped"` (existing behavior).
- [ ] Silent branches do NOT call `update_last_inbound` (verified by test).
- [ ] Silent branches do NOT acquire the session lock or build the agent (verified by test).
- [ ] Plugin hook consultation uses the `getattr(plugin, "is_mention", _default_no_mention)` sentinel pattern.
- [ ] `tests/test_connectors_inbound.py` (or new test file) has the 14 new policy-gate tests listed in Outputs (13 from the initial list + the DM-command-intercept edge case), all passing.
- [ ] `docker exec the-one pytest tests/test_connectors_inbound.py tests/test_connectors_policy_gate.py tests/test_connectors_inference.py -x --timeout 30` passes (the second file path applies if the Developer chooses to split; otherwise omit).
- [ ] Full suite at leg-end: `docker exec the-one pytest -x --timeout 60` — no L8-introduced regressions.
- [ ] Flight log L8 entry under `## Leg Progress` documents the leg; leg checked off in `flight.md`; status set to `landed`.

## Verification Steps

- `grep -n "_policy_gate_decision" the_one/connectors/_inbound.py` returns the helper definition + the call site.
- `grep -n "policy-silent" the_one/connectors/_inbound.py` returns at least one match (the disposition assignment).
- `grep -n "run_engagement_inference" the_one/connectors/_inbound.py` returns at least one match (the helper's invocation).
- Targeted: `docker exec the-one pytest tests/test_connectors_inbound.py tests/test_connectors_inference.py -x --timeout 30` — all green.
- Full suite: `docker exec the-one pytest -x --timeout 60` — all green.

## Implementation Guidance

1. **Add the function-local imports** at step 1 of `dispatch_inbound`. Confirm `decode_messages`, `LLMProviderRepository`, and `run_engagement_inference` are imported; add `_default_no_mention` import.

2. **Define `_policy_gate_decision`** as a module-private async helper above `dispatch_inbound`. Implement the five-path tree per the code sketch in Outputs.

3. **Locate `agent_config`** — find where the dispatcher loads the routed agent's config between step 7 (routing) and step 12 (lock). If not in scope, fetch via `agent_store.load(decision.agent)`. The Developer agent reads the surrounding code to determine the right approach.

4. **Insert the gate call** between step 11's fallthrough and step 12's lock acquire. Use the code sketch in Outputs verbatim, adapted to the actual variable names in the dispatcher.

5. **Audit shape**: the silent-branch audit entry is the existing `audit_entry` dict (built at step 8) plus `disposition="policy-silent"` and `policy=policy_audit`. The engaged path falls through to step 12, which sets `disposition="stepped"` (existing).

6. **Run targeted tests**, then full suite. Update flight log under `## Leg Progress` with `### L8 — dispatcher-policy-gate-pre-step`. Check off in flight.md. Set L8 status to `landed`. Do NOT commit.

## Edge Cases

- **No `db_session_for_routing` in scope** — the Developer agent uses whatever variable name holds the resolved session row at this point. Per recon, step 5 resolves it; the variable is likely named `session_row` or similar.
- **`decision.agent is None` (no eligible agent)** — handled at step 9 BEFORE the gate; the gate never runs. No interaction with L8.
- **Pool acquire failure at step 10** — handled at step 10 BEFORE the gate; the gate never runs.
- **Command-intercepted at step 11** — handled at step 11 BEFORE the gate; the gate never runs.
- **`agent_config` not loaded yet** — gate logic depends on the routed agent's config. If the dispatcher's existing flow doesn't load `agent_config` before step 12 (it's likely loaded inside step 12 for the factory), L8 must load it earlier. The Developer agent verifies the current flow and inserts an early `agent_config = await agent_store.load(decision.agent)` if needed; ensure this read is cached (don't reload for the factory at step 12).
- **`run_engagement_inference` returns False on exception** — L7's contract is safe-default-False; L8 gate sees False as silent. No additional exception handling needed at the gate.
- **`account_id` in audit's policy sub-block** — the audit entry already has `account` (no, that's `agent`). Confirm at impl time whether the existing audit shape carries account_id; if not, the L8 audit doesn't need to re-include it (the entry lives under a session's metadata; the session is already account-scoped).
- **Silent turns accumulate in audit log size** — DD §13 explicitly accepts this. F9 audit-log inspector handles rendering/pagination.
- **Tests for an inference path that doesn't trigger** — the `test_policy_gate_silent_when_account_always_listen_off` and `_when_account_on_agent_off` tests must verify `run_engagement_inference` is NOT called (use a mocked inference function that fails-if-called).
- **Order of decision-tree evaluation** — strictly first-match-wins per DD §1. Test `test_policy_gate_engages_on_dm` verifies DM is checked first (e.g., a DM message with no mention still engages).
- **`envelope.raw.get("is_dm")` defensive read** — the gate uses `.get()` with no default (returns None), then checks `is True` strictly. This rejects truthy-but-not-True values (defensive against malformed envelopes).
- **`decision.scope == "override"` check** — case-sensitive exact string. Per recon, the routing engine writes the literal string `"override"`.
- **L1's `_default_no_mention` returns False for the stub plugin** — verified at recon. The stub plugin in test scaffolding doesn't implement `is_mention`; the gate sees False; falls through to the always-listen check.
- **DM + command intercept interaction (cycle-1 review)** — step 11 (command-intercept) runs BEFORE the gate. A DM message that's ALSO a slash command (e.g., a peer DMs the bot `/help`) hits step 11 first, gets intercepted by `_dispatch_builtin_command`, emits the response, and returns early. The gate NEVER evaluates. This is intentional: DMs ignore the policy gate but do NOT bypass the command-intercept system. Tests should pin this with `test_policy_gate_command_intercept_in_dm_does_not_invoke_gate` — a DM with text `/help` hits step 11's path, returns early, audit has `disposition="command-intercepted"` (NOT "policy-silent" and NOT "stepped").
- **`session_messages` staleness window (cycle-1 review)** — `db_session_for_routing.messages` was fetched at line 357 (post-routing). Between that fetch and the gate, an interleaved inbound on the same session could have stepped through step 12's lock and mutated `messages`. The inference call would then see a slightly-stale history projection. Acceptable: the inference is bias-toward-silent and a sub-millisecond staleness window doesn't change the safe-default semantic. Do NOT re-fetch before the gate (would double the DB read; the engaged path's step 12 acquires the lock and gets fresh data anyway).

## Files Affected

- `the_one/connectors/_inbound.py` — ADD imports + `_policy_gate_decision` helper + gate call between step 11 and step 12.
- `tests/test_connectors_inbound.py` (or `tests/test_connectors_policy_gate.py` if split) — ADD 13 new tests.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight-log.md` — APPEND L8 entry.
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

Citations verified against current code at design time via the F7 L8 reconnaissance pass:

- `the_one/connectors/_inbound.py:470-583` — step 11 command-intercept (verified).
- `the_one/connectors/_inbound.py:587-866` — step 12 per-session lock + agent.step + auto-relay (verified post-L5).
- `the_one/connectors/_inbound.py:589-593` — step 12 disposition assignment + audit append (verified).
- `the_one/connectors/_inbound.py:598` — `update_last_inbound` call site (verified).
- `the_one/connectors/_routing.py:RoutingDecision:109-138` — RoutingDecision shape with `scope` (verified).
- `the_one/connectors/_routing.py:168-171` — `is_dm` getattr-sentinel consult pattern (verified).
- `the_one/connectors/_acl.py:_default_no_mention:86-102` — L1 sentinel (verified).
- `the_one/connectors/_inference.py:run_engagement_inference:236-244` — L7 function signature (verified).
- `the_one/agent/config.py:AgentConfig.connector_always_listen` (L6 addition, verified).
- `the_one/agent/config.py:AgentConfig.provider_config_id, llm_model:183-184` — fallback fields (verified).
- `the_one/db/models.py:ChatSession.session_metadata` — `dict[str, Any] | None`, free-shape (verified).
- `the_one/db/codec.py:decode_messages` — session.messages JSON decode (verified).
- F6 Deny precedent test at `tests/test_connectors_inbound.py:test_deny_outcome_logs_and_returns` — silent-return-without-lock test shape (verified).
