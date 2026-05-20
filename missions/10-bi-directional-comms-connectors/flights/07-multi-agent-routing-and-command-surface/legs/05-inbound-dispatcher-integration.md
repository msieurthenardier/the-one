# Leg: inbound-dispatcher-integration

**Status**: landed
**Flight**: [Multi-Agent Routing and the Platform-Side Command Surface](../flight.md)

## Objective

Wire L1's `_parse_command` text-prefix parser + L4's `resolve_routing` engine + L2's `admits_inbound` per-agent ACL gating + an audit-log writer + a new sibling primitive `ChatSessionRepository.set_session_metadata_key` into the inbound dispatcher at `the_one/connectors/_inbound.py`. Remove L3's transitional helper `_resolve_single_attached_agent_or_first_alphabetical`. Add a system-outbound path for command responses and for the "No agents available" peer-facing error. Audit-log every routing decision under `session_metadata["routing"]`. L5 is the only F7 leg that integrates the pieces L1–L4 produced; no new pure-function modules ship here. F1–F7 (post-L4) regression suite passes byte-identically; new dispatcher tests cover routing-match, override, default, fallback, no-eligible, command-intercept, and command-only-vs-message-only paths.

## Context

This is the fifth and largest F7 leg. Per Design Decisions in `flight.md`:

- **"Post-resolver, post-routing, post-ACL, pre-command-parse, pre-lock intercept ordering"** — the dispatcher's composition (canonical 12-step numbering used throughout this leg artifact):
  1. Function-local imports (load-cycle convention)
  2. Account load (existing F1-F2, retained)
  3. Plugin resolve (existing F1-F2, retained)
  4. Enumerate eligible attached agents via L3's `SQLiteAgentStore.list_by_connector_account(account_id)` (REPLACES the transitional helper from L3) — early-return if empty (preserves L3's silent-ignore semantic)
  5. `resolve_session` (existing F3) — uses `eligible_attached_agents[0].name` as the creation-time anchor for new rows; reuse path ignores agent_name
  6. F6 resolver consult (`Permit` / `NeedsPairing` / `Deny`) — retained; sets `working_envelope` (NeedsPairing-success path rewrites text)
  7. **F7 routing engine consult (NEW)** — `resolve_routing(account, working_envelope, eligible_attached_agents, session_metadata)` → `RoutingDecision`. The L4 engine internally consults `admits_inbound` for each candidate; L5 does NOT re-check ACL on the engine's output.
  8. **Build audit_entry (NEW)** — populate `{ts, agent, rule_index, scope, match, reason}` from `RoutingDecision`; `disposition` filled in by step 9 / 10 / 11 / 12 before the entry is appended.
  9. **No-eligible branch (NEW)** — if `decision.agent is None`: set `disposition: "no-eligible"`; append audit entry; emit the peer-facing "No agents available for this conversation." via system-outbound (using `eligible_attached_agents[0].name` as the pool key — the bot identity reflects the alphabetically-first attached agent's pool entry, which IS valid for outbound emission regardless of inbound-ACL state); return.
  10. **Pool acquire for routed agent (NEW position)** — `pool_acquire(decision.agent, account_id)` is the F1 ratification anchor moved here (after routing). If pool fails, set `disposition: "no-eligible"` (overload — see Edge Cases); append audit entry; return.
  11. **Command parse + intercept (NEW)** — `_parse_command(working_envelope.text)` → if recognized:
      - Dispatch to L6's command handler (L5 ships a minimal handler-not-yet-wired guard; L6 implements the six command handlers).
      - If handler returns `CommandResponse(text)`: emit response via system-outbound `client.send(OutboundTarget(channel_id=working_envelope.channel_id, thread_id=working_envelope.thread_id), response.text)`; set `disposition: "command-intercepted"`; append audit entry; return without per-session lock or `agent.step`.
      - If handler returns `None`: fall through to step 12.
  12. **Per-session lock + agent.step (existing F3+F4)** — unchanged from F3 except `agent_name` is now `decision.agent`. Set `disposition: "stepped"`; append audit entry; run lock + step + visibility-tagging.
- **"System outbound via pool_acquire + client.send"** — command responses and the no-eligible error use the same pool path the platform-send tool (`tools/connector_send.py:183-200`) uses, invoked dispatcher-internally with function-local imports for cycle-break. The platform-send tool is NOT involved; commands work even when the tool is operator-disabled.
- **"Peer-issued routing override via session-scoped persistence + sibling primitive `set_session_metadata_key`"** — L5 ships the sibling primitive (`ChatSessionRepository.set_session_metadata_key(session_id, key, value)`) but does NOT consume it for `routing_override` writes yet — that's L6's `/talk-to` handler. L5 ships the primitive + repository tests; L4's engine already reads `session_metadata["routing_override"]` so the read side is ready.
- **"Routing audit key — `session_metadata["routing"]`, list-append semantics, disposition field"** — each routing decision appends one entry to `session_metadata["routing"]`. Entry shape: `{"ts": iso, "agent": slug | None, "rule_index": int | None, "scope": str | None, "match": str | None, "reason": str, "disposition": "stepped" | "command-intercepted" | "no-eligible"}`. The `disposition` field distinguishes "routed-and-stepped" from "command-intercepted" from "no-eligible-error-emitted." Mirror F6's `session_metadata["audit"]` entry shape — `ts`, `reason` keys reuse F6's naming.
- **L6 / L7 are downstream**: L6 ships the command-handler functions that L5's command-intercept dispatch calls into; L7 ships the Studio Routing Rules editor. L5 is the integration; L6 and L7 are leaves.

Key learnings from prior legs:

- L1: `_parse_command(text)` returns `(command_name, args)` or `None`; pure function.
- L2: `admits_inbound(account, agent_acl, peer_id, channel_id)` — pure ACL admission function with per-axis tri-state. Reason vocabulary "admitted."
- L3: `SQLiteAgentStore.list_by_connector_account(account_id) -> list[AgentConfig]` returns alphabetically-ordered list. L5 calls this; replaces the L3 transitional helper.
- L4: `resolve_routing(account, envelope, eligible_attached_agents, session_metadata) -> RoutingDecision`. Scope-uniformity invariant for renderer. `decision.agent is None` on no-eligible.
- F6: `append_to_session_metadata(session_id, key, value)` is a list-append primitive at `db/repositories.py:846-885`. L5's audit-log writes consume this for the new `routing` key.
- F4: `pool_acquire(agent_name, account_id)` returns the client; the platform-send tool path at `tools/connector_send.py:183-200` is the system-outbound shape L5 mirrors.

## Inputs

What exists before this leg runs:

- L3-shape `the_one/connectors/_inbound.py`: `dispatch_inbound(account_id, envelope, *, factory)` — agent_name resolved via transitional helper at top of body (lines 77-102 and 144-158). The full body spans `_inbound.py:105-345` (approximate; verified via Read at L5 design time).
- `the_one/connectors/_acl.py:admits_inbound` — L2 pure function. (L5 does NOT call directly; L4's engine consumes it.)
- `the_one/connectors/_commands.py:_parse_command` — L1 pure function. L5 calls in step 10.
- `the_one/connectors/_routing.py:resolve_routing, RoutingDecision` — L4 pure function + dataclass. L5 calls in step 6.
- `the_one/connectors/base.py:OutboundTarget, CommandResponse` — L5 uses `OutboundTarget` for system-outbound; `CommandResponse` is reserved for L6's handlers (L5 ships a placeholder until L6 lands).
- `the_one/connectors/_pool.py:acquire` (re-exported as `pool_acquire`) — F4 path L5 reuses for system-outbound.
- `the_one/db/repositories.py:ChatSessionRepository.append_to_session_metadata` (lines 846-885) — F6 primitive for list-append entries under a session_metadata key. L5 reuses for the new `routing` key.
- L3-shape `_inbound.py` test suite green: 437 tests pass (post-L4 baseline: 404 prior + 33 routing).
- No existing `set_session_metadata_key`, command-intercept logic, routing-audit entries, or no-eligible peer-facing-error emission anywhere in `the_one/` or `tests/`.

## Outputs

What exists after this leg completes:

- `the_one/connectors/_inbound.py` substantially rewritten — composition order per Design Decisions; L3 transitional helper removed; system-outbound path added; audit-log writes added; command parse + intercept added.
- `the_one/db/repositories.py` — new method `ChatSessionRepository.set_session_metadata_key(session_id: str, key: str, value: Any) -> None`. Adjacent to `append_to_session_metadata` (lines 846-885).
- `the_one/connectors/_commands.py` — placeholder handler dispatcher `_dispatch_builtin_command(command_name, args, context)` that L5 ships as "not-yet-implemented; falls through to agent.step like a non-command message." L6 replaces the placeholder with real handlers.
- New tests in `tests/test_connectors_inbound.py` AND `tests/test_db_repositories.py` covering the new integration points + the new primitive.
- All existing F1–F7 (post-L4) tests pass byte-identically.

## Acceptance Criteria

- [ ] `the_one/db/repositories.py:ChatSessionRepository.set_session_metadata_key(session_id: str, key: str, value: Any) -> None` ships:
  - Reads the row's current `session_metadata` JSON (empty dict if NULL).
  - Sets `metadata[key] = value` (overwrite semantic — distinct from `append_to_session_metadata`'s list-append).
  - Writes the updated JSON back.
  - Concurrency posture: last-writer-wins (as per F7 Design Decisions). Documented in docstring with one-paragraph rationale citing the override semantic.
  - Raises `KeyError` if `session_id` doesn't exist (mirrors `append_to_session_metadata`'s contract).
  - Placed in `repositories.py` adjacent to `append_to_session_metadata`.
- [ ] `the_one/connectors/_inbound.py:_resolve_single_attached_agent_or_first_alphabetical` REMOVED. The function's helpers are now needed only at the eligible-list resolution step (which calls `SQLiteAgentStore.list_by_connector_account` directly).
- [ ] `dispatch_inbound` body restructured per the canonical 12-step composition order in Context above. AC bullets below refer to the same step numbers.
  - Steps 1-3 (imports + account load + plugin resolve): unchanged from F3 dispatcher.
  - Step 4 (enumerate eligible agents): `eligible_attached_agents = await store.list_by_connector_account(account_id)`. If empty: log + return (preserves L3's silent-ignore on the no-attachment case).
  - Step 5 (resolve_session): uses `eligible_attached_agents[0].name` as the `agent_name` argument — preserves the F3 byte-identical chat_sessions row creation semantic. Reuse path unaffected.
  - Step 6 (F6 resolver consult): unchanged from F3 dispatcher. Sets `working_envelope` (envelope or cleaned-text NeedsPairing-success rewrite).
  - Step 7 (routing engine): `decision = resolve_routing(account, working_envelope, eligible_attached_agents, session_metadata)`. Reads `session_metadata` via `chat_repo.get(session_row.id)` (or via the row's metadata field if it's already in scope) and decodes JSON.
  - Step 8 (build audit entry): populate `{ts, agent, rule_index, scope, match, reason}` from `decision`; `disposition` deferred.
  - Step 9 (no-eligible branch): if `decision.agent is None`:
    - Set `disposition: "no-eligible"`; append audit entry.
    - System-outbound: `pool_acquire(eligible_attached_agents[0].name, account_id) → client.send(OutboundTarget(channel_id=working_envelope.channel_id, thread_id=working_envelope.thread_id), "No agents available for this conversation.")`.
    - If system-outbound emit raises: log the exception; do NOT re-raise. Return.
  - Step 10 (pool acquire for routed agent): `pool_acquire(decision.agent, account_id)`. On failure: set `disposition: "no-eligible"` (overload — see Edge Cases); append audit entry; return.
  - Step 11 (command parse + intercept):
    - `parsed = _parse_command(working_envelope.text)`.
    - If `parsed is None`: fall through to step 12.
    - If `parsed is not None` (a command was parsed): call placeholder `_dispatch_builtin_command(command_name, args, context)` which returns a `CommandResponse` (or `None` on "not implemented yet — fall through"). L5 ships the placeholder returning `None` for ALL commands (L6 fills in real handlers). The placeholder's `None`-return means: NO command intercept — fall through to agent.step in step 12. (This is the "L5 ships the integration; L6 ships the handlers" split.)
    - If the placeholder returns a `CommandResponse(text)`: set `disposition: "command-intercepted"`; append audit entry; emit response via system-outbound (using the pool client from step 10); on emit failure, log + swallow; return.
  - Step 12 (per-session lock + agent.step): existing F3+F4 logic using `decision.agent` as the `agent_name` substituted at `factory.create(agent_name)`. Set `disposition: "stepped"`; append audit entry; run lock + step + visibility-tagging.
- [ ] `the_one/connectors/_commands.py` ships a `_dispatch_builtin_command` placeholder:
  - Signature: `async def _dispatch_builtin_command(command_name: str, args: list[str], context: dict[str, Any]) -> CommandResponse | None`.
  - L5 returns `None` for ALL command_name values (placeholder).
  - L5's `context` dict includes: `account`, `envelope`, `eligible_attached_agents`, `routed_agent_name`, `session_id`, `chat_repo` (for `routing_override` writes in L6). L6 replaces the body with real handlers.
  - Module docstring updated to reference L6 as the implementation site.
- [ ] Audit-log entries under `session_metadata["routing"]` carry the entry shape:
  ```python
  {
      "ts": iso_timestamp,
      "agent": str | None,
      "rule_index": int | None,
      "scope": str | None,
      "match": str | None,
      "reason": str,
      "disposition": "stepped" | "command-intercepted" | "no-eligible",
  }
  ```
- [ ] System-outbound path: `pool_acquire(agent_name, account_id) → client.send(...)` invoked dispatcher-internally with function-local imports for cycle-break. Mirrors `tools/connector_send.py:183-200`'s call shape. NOT routed through the platform-send tool registry.
- [ ] All existing F1–F7 (post-L4) regression tests pass byte-identically:
  ```
  docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py -x --timeout 30'
  ```
  Including: 28 `test_connectors_commands` (L1), 33 `test_connectors_routing` (L4), 62 routing-schema + ACL tests (L2), 39 `test_connector_send_tool` exact-equality reason-string tests (F6 verbatim), and the ~55 migrated `dispatch_inbound` test-fixture sites (L3).
- [ ] New tests in `tests/test_connectors_inbound.py` (mirror existing test style — uses `_seed_provider_and_agent`, `_seed_stub_account`, `_envelope`, etc.):
  - **Routing-match tests**: `test_dispatch_inbound_routes_to_agent_per_rule_match` — seed two agents (`alpha`, `bravo`); attach both to `acct-test`; configure `routing.rules = [{"scope": "channel", "match": "ch-1", "agent": "bravo"}]`; envelope on `ch-1` → `agent.step` runs on `bravo` (verify via assertion on `chat_repo.list()` agent_name or via a mock `factory.create` that records which name was passed). Audit-log entry has `agent=bravo, rule_index=0, scope="channel", reason="rule-match", disposition="stepped"`.
  - **Override tests**: `test_dispatch_inbound_routing_override_short_circuits_rule_walk` — pre-write `session_metadata["routing_override"] = "alpha"` via the new `set_session_metadata_key` primitive; inbound on `ch-1` (which would match the bravo rule) → routes to `alpha` instead. Audit: `reason="override"`.
  - **Default fallback**: `test_dispatch_inbound_falls_back_to_default_when_no_rule_matches` — `routing.default = "alpha"`; no rules; inbound → `alpha`. Audit: `reason="default"`.
  - **First-eligible fallback**: `test_dispatch_inbound_falls_back_to_first_eligible_when_no_default` — no rules, no default, two attached agents `alpha`/`bravo` → `alpha` (alphabetical first). Audit: `reason="first-eligible"`.
  - **No-eligible**: `test_dispatch_inbound_no_eligible_emits_peer_error_via_system_outbound` — single agent with ACL denying the peer; routing returns `decision.agent=None`; assert StubPlugin's `outbound_records` captured `"No agents available for this conversation."` to the right `(channel_id, thread_id)`; audit: `agent=None, reason="no-eligible-agent", disposition="no-eligible"`; no chat_sessions row beyond what resolve_session created; no `agent.step` invocation (assert via a recording factory).
  - **No-attached-agents**: `test_dispatch_inbound_no_attached_agents_silent_return_no_peer_error` — seed an agent with `connector_account_ids=[]`; inbound; assert no exception, no peer-facing error emission (StubPlugin's `outbound_records` empty), no audit entry (no session row created either). Preserves L3 semantic.
  - **Command-parse-falls-through-in-L5**: `test_dispatch_inbound_command_text_falls_through_to_agent_step_in_L5` — envelope text is `"/agents"`; L5 placeholder returns `None`; the dispatcher falls through to step 12; `agent.step` runs with the command text as the user message; audit: `disposition="stepped"`. (L6 must REWRITE this test to reflect `/agents` being intercepted by the L6 handler — L5's leg pins the placeholder semantic; L6's leg scope explicitly includes this rewrite.)
  - **Pool-failure-overload**: `test_dispatch_inbound_pool_failure_at_step_10_logs_no_eligible_disposition` — seed routing to pick a specific agent; mock `pool_acquire` to raise `ConnectorRegistrationError` only for that agent; assert audit entry has `reason="rule-match"` (the routing decision) but `disposition="no-eligible"` (the pool-failure overload). Pins the documented overload behavior so a future refactor doesn't silently flip it.
  - **System-outbound emit failure on no-eligible**: `test_dispatch_inbound_no_eligible_system_outbound_emit_failure_is_swallowed` — mock the stub's `client.send` to raise; assert dispatcher returns cleanly (no exception propagated); assert audit entry was still written with `disposition="no-eligible"`. Pins the swallow-and-log contract.
  - **Per-agent ACL inbound check via routing**: `test_dispatch_inbound_acl_denied_routed_agent_falls_back_to_next_eligible` — two attached agents `alpha`/`bravo`; `alpha`'s ACL denies the peer; routing engine's step 4 (first-eligible-alphabetical) skips `alpha`, picks `bravo`; agent.step runs on `bravo`. Audit: `agent=bravo, reason="first-eligible"`.
- [ ] New tests in `tests/test_db_repositories.py` for `set_session_metadata_key`:
  - `test_set_session_metadata_key_writes_new_key` — empty `session_metadata`; write `"foo": "bar"`; assert read-back has `{"foo": "bar"}`.
  - `test_set_session_metadata_key_overwrites_existing_value` — write `"foo": "bar"`; write `"foo": "baz"`; read-back `{"foo": "baz"}`.
  - `test_set_session_metadata_key_preserves_other_keys` — write `"foo": "bar"`; write `"other": [1, 2]`; write `"foo": "baz"`; read-back `{"foo": "baz", "other": [1, 2]}`. Pins last-writer-wins on the key + preserve-other invariant.
  - `test_set_session_metadata_key_raises_on_unknown_session` — `KeyError` for unknown session_id.
  - `test_set_session_metadata_key_accepts_any_value_type` — write a dict, write a list, write a string, write None; each round-trips.
- [ ] Documentation updates:
  - `the_one/connectors/README.md` — verify the current section that describes the inbound dispatcher composition via `grep -n "dispatch_inbound\|inbound" the_one/connectors/README.md`; update that section to reflect the new 12-step canonical order: account-load → plugin-resolve → enumerate-eligible → resolve_session → F6-resolver → F7-routing → audit-build → no-eligible-branch → pool-acquire → command-parse → lock+step.
  - `the_one/agents.md` — Connector subsystem section adds a paragraph on the F7 routing convention. Required facts the paragraph must convey: (i) routing engine (`connectors/_routing.py:resolve_routing`) is pure (no I/O); (ii) ACL admission (`connectors/_acl.py:admits_inbound` / `admits_outbound`) is pure; (iii) the inbound dispatcher composes them (routing decides which agent; ACL is checked inside routing); (iv) routing decisions are audit-logged under `session_metadata["routing"]` with `disposition` field discriminating "stepped" / "command-intercepted" / "no-eligible"; (v) audit shape mirrors F6's `audit` key shape (same `ts` and `reason` keys, plus routing-specific fields). Cite `_routing.py` and `_acl.py`. Mirror the prose style of the existing F6 audit-log paragraph (locate via `grep -n "audit" the_one/agents.md`).

## Verification Steps

How to confirm each criterion is met:

**Repository primitive** (in `tests/test_db_repositories.py`):

- 5 tests for `set_session_metadata_key` per Acceptance Criteria.

**Dispatcher integration** (in `tests/test_connectors_inbound.py`):

- 8 new tests covering routing-match / override / default / first-eligible / no-eligible / no-attached / command-falls-through / ACL-denied-fallback.
- For routing-match assertions: use a recording factory or recording stub that captures which `agent_name` was passed to `factory.create()` for `agent.step`. The existing `_make_factory()` builds an `AgentFactory` that the dispatcher's step 11 invokes; tests can inspect the most-recently-built agent's `name`.
- For system-outbound assertions: `StubPlugin.outbound_records` is the existing F4 buffer that captures `client.send` calls. Assert the buffer contains exactly the expected text + target.

**Regression**:

- `docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py -x --timeout 30'` — expected ~445+ tests pass (~437 prior + ~8 new dispatcher tests + ~5 new repository tests). No regressions in the 55 migrated dispatch_inbound test fixtures.

**Documentation**:

- `grep -n "routing engine" the_one/connectors/README.md` — finds the new section.
- `grep -n "_routing.py" the_one/agents.md` — finds the cite.

## Implementation Guidance

### 1. New primitive in `the_one/db/repositories.py`

Add adjacent to `append_to_session_metadata` (after line 885). The implementation mirrors `append_to_session_metadata`'s pattern: read JSON column, decode dict, mutate, encode back, UPDATE the row.

```python
    async def set_session_metadata_key(
        self,
        session_id: str,
        key: str,
        value: Any,
    ) -> None:
        """Set ``session_metadata[key] = value`` (overwrite semantic).

        Sibling primitive to :meth:`append_to_session_metadata`. Where
        ``append_to_session_metadata`` accumulates a list under a key
        (F6's ``"audit"`` log + F7's ``"routing"`` log), this primitive
        is for last-writer-wins single-value sets — F7 L6's
        ``routing_override`` key.

        Concurrency posture: last-writer-wins, by design. Two
        concurrent ``/talk-to`` inbounds for the same session land in
        non-deterministic order; the last writer's intent wins
        silently. This is the correct semantic for an override ("most
        recent operator/peer intent wins") and is documented at the
        call sites in F7 L6's command handlers.

        Raises ``KeyError`` if ``session_id`` doesn't exist (mirrors
        :meth:`append_to_session_metadata`'s contract).
        """
        # ... implementation mirrors append_to_session_metadata ...
```

### 2. Restructure `dispatch_inbound` in `the_one/connectors/_inbound.py`

Delete `_resolve_single_attached_agent_or_first_alphabetical` (lines 77-102). Rewrite `dispatch_inbound`'s body to match the 11-step composition order. Key code skeleton:

```python
async def dispatch_inbound(
    account_id: str,
    envelope: InboundEnvelope,
    *,
    factory: AgentFactory,
) -> None:
    # ... docstring updated to reflect L5 composition ...

    # 1. Function-local imports per the load-cycle convention.
    from the_one.config import settings
    from the_one.db.connection import get_connection
    from the_one.db.repositories import (
        ChatSessionRepository,
        ConnectorAccountRepository,
        SQLiteAgentStore,
    )
    from the_one.encryption import get_encryptor

    conn = await get_connection()
    encryptor = get_encryptor(settings.data_dir)
    acc_repo = ConnectorAccountRepository(conn, encryptor)
    chat_repo = ChatSessionRepository(conn)
    agent_store = SQLiteAgentStore(conn)

    # 2. Account load.
    try:
        account = await acc_repo.get(account_id)
    except KeyError:
        logger.warning(
            "dispatch_inbound: account %s not found (deleted mid-flight?)",
            account_id,
        )
        return

    # 3. Plugin resolve.
    try:
        plugin = registry.resolve(account.type)
    except ConnectorRegistrationError as exc:
        logger.error(
            "dispatch_inbound: unknown connector type %r for account %s: %s",
            account.type, account_id, exc,
        )
        return

    # 4. Enumerate eligible attached agents.
    eligible_attached_agents = await agent_store.list_by_connector_account(account_id)
    if not eligible_attached_agents:
        logger.info(
            "dispatch_inbound: no agents attached to account_id=%s; ignoring inbound",
            account_id,
        )
        return
    first_eligible_name = eligible_attached_agents[0].name

    # 5. Resolve session (creation-time anchor: first-eligible alphabetical).
    session_row = await resolve_session(
        envelope, account, chat_repo,
        agent_name=first_eligible_name,
        plugin=plugin,
    )

    # 6. F6 resolver consult.
    resolver = getattr(plugin, "resolve", _default_permit)
    outcome = resolver(account, envelope)
    ts = now_iso()
    if isinstance(outcome, Deny):
        await chat_repo.append_to_session_metadata(
            session_row.id, "audit",
            {"outcome": "deny", "peer_id": envelope.peer_id, "ts": ts,
             "reason": outcome.reason},
        )
        return
    working_envelope = envelope
    if isinstance(outcome, NeedsPairing):
        # ... existing NeedsPairing handling unchanged ...
        # On failure: return. On success: working_envelope = replace(...).
        pass
    else:
        # ... existing Permit audit-log entry unchanged ...
        pass

    # 7. F7 routing engine consult.
    db_session = await chat_repo.get(session_row.id)
    session_metadata: dict[str, Any] = (
        json.loads(db_session.session_metadata)
        if db_session.session_metadata else {}
    )
    decision = resolve_routing(
        account, working_envelope, eligible_attached_agents, session_metadata,
    )

    # 8. Audit-log routing decision (disposition filled in after dispatch).
    audit_entry: dict[str, Any] = {
        "ts": now_iso(),
        "agent": decision.agent,
        "rule_index": decision.rule_index,
        "scope": decision.scope,
        "match": decision.match,
        "reason": decision.reason,
        # "disposition" set below per branch.
    }

    # 9. No-eligible branch.
    if decision.agent is None:
        audit_entry["disposition"] = "no-eligible"
        await chat_repo.append_to_session_metadata(
            session_row.id, "routing", audit_entry,
        )
        # System-outbound: emit peer-facing error.
        try:
            from the_one.connectors._pool import acquire as pool_acquire
            from the_one.connectors.base import OutboundTarget
            client = await pool_acquire(first_eligible_name, account_id)
            await client.send(
                OutboundTarget(
                    channel_id=envelope.channel_id,
                    thread_id=envelope.thread_id,
                ),
                "No agents available for this conversation.",
            )
        except Exception:
            logger.exception(
                "dispatch_inbound: no-eligible peer-error emit failed for (agent=%s, account=%s)",
                first_eligible_name, account_id,
            )
        return

    # 10. Pool acquire for routed agent.
    from the_one.connectors._pool import acquire as pool_acquire
    try:
        client = await pool_acquire(decision.agent, account_id)
    except (KeyError, ConnectorRegistrationError) as exc:
        logger.warning(
            "dispatch_inbound: pool acquire failed for (agent=%s, account=%s): %s",
            decision.agent, account_id, exc,
        )
        audit_entry["disposition"] = "no-eligible"  # treat as no-eligible for audit
        await chat_repo.append_to_session_metadata(
            session_row.id, "routing", audit_entry,
        )
        return

    # 11. Command parse + intercept.
    from the_one.connectors._commands import _parse_command, _dispatch_builtin_command
    parsed = _parse_command(working_envelope.text)
    if parsed is not None:
        command_name, args = parsed
        context = {
            "account": account,
            "envelope": working_envelope,
            "eligible_attached_agents": eligible_attached_agents,
            "routed_agent_name": decision.agent,
            "session_id": session_row.id,
            "chat_repo": chat_repo,
        }
        response = await _dispatch_builtin_command(command_name, args, context)
        if response is not None:
            # Emit response via system outbound.
            try:
                from the_one.connectors.base import OutboundTarget
                await client.send(
                    OutboundTarget(
                        channel_id=working_envelope.channel_id,
                        thread_id=working_envelope.thread_id,
                    ),
                    response.text,
                )
            except Exception:
                logger.exception(
                    "dispatch_inbound: command-response emit failed",
                )
            audit_entry["disposition"] = "command-intercepted"
            await chat_repo.append_to_session_metadata(
                session_row.id, "routing", audit_entry,
            )
            return
        # Placeholder returned None → fall through to agent.step.

    # 12. Per-session lock + agent.step (existing F3+F4 logic, using decision.agent).
    audit_entry["disposition"] = "stepped"
    await chat_repo.append_to_session_metadata(
        session_row.id, "routing", audit_entry,
    )
    async with session_locks[session_row.id]:
        # ... existing F3+F4 lock+step+visibility logic with agent_name=decision.agent ...
```

### 3. Placeholder dispatcher in `the_one/connectors/_commands.py`

Add a placeholder `_dispatch_builtin_command` that L6 will fill in. L5 ships the function returning `None` for all command_name values so the dispatcher falls through to agent.step. The placeholder lets L5's integration tests assert the full code path (parse → placeholder → fall-through → step) without depending on L6.

```python
async def _dispatch_builtin_command(
    command_name: str,
    args: list[str],
    context: dict[str, Any],
) -> CommandResponse | None:
    """Built-in command dispatcher placeholder — F7 L5 ships, L6 fills.

    L5 returns ``None`` for every command_name, which the inbound
    dispatcher treats as "fall through to agent.step" (no command
    intercept). L6's leg implements the six v1 command handlers
    (``/agents``, ``/talk-to``, ``/whoami``, ``/new``, ``/reset``,
    ``/help``) and replaces this placeholder.

    The ``context`` dict carries the dispatcher's per-invocation
    state: ``account``, ``envelope``, ``eligible_attached_agents``,
    ``routed_agent_name``, ``session_id``, ``chat_repo``.
    """
    return None
```

### 4. Test fixtures + new tests

Existing fixture pattern in `tests/_connector_dispatch_helpers.py` (already used by 55 dispatch_inbound test sites) is the foundation. New tests live in `tests/test_connectors_inbound.py`. Use the existing `_make_scripted_factory(responses)` for tests that need the agent.step to produce specific output, or `_make_factory()` for tests that just want to confirm "agent.step ran with the right agent_name."

For asserting "which agent ran agent.step", inspect the most-recently-built agent's `factory.create`-call history. The existing `AgentFactory.create(agent_name)` is the integration point; tests can monkeypatch or wrap with a recording shim.

### 5. Order of file edits

1. `the_one/db/repositories.py` — add `set_session_metadata_key`. Run repo tests.
2. `tests/test_db_repositories.py` — add 5 new tests for the primitive. Run.
3. `the_one/connectors/_commands.py` — add `_dispatch_builtin_command` placeholder. Run L1 tests (still pass).
4. `the_one/connectors/_inbound.py` — delete transitional helper; restructure `dispatch_inbound` body per the 11-step order.
5. `tests/test_connectors_inbound.py` — add 8 new integration tests. Run.
6. Full regression: `docker exec the-one sh -c 'pytest tests/test_connectors*.py tests/test_connector_send_tool.py tests/test_db_repositories.py -x --timeout 30'`.
7. `the_one/connectors/README.md` + `the_one/agents.md` documentation updates.

### 6. Things NOT in scope for this leg

- The six command handlers (L6 — `_dispatch_builtin_command` placeholder returns `None`; L6 fills body).
- Studio Routing Rules editor (L7).
- F6 carry-forward bundle (L8 — orthogonal).
- HAT (L9).
- Schema migrations (none for F7).
- Changes to L1's `_parse_command`, L2's `admits_inbound` / `admits_outbound`, L3's `list_by_connector_account`, or L4's `resolve_routing` / `RoutingDecision` — all consumed verbatim.

## Edge Cases

- **Command parse but L5 placeholder returns None**: dispatcher falls through to step 12 (agent.step). The command text becomes the user message to the agent. L6 changes this for the six known commands; L5's behavior is the default fall-through. Pinned by `test_dispatch_inbound_command_text_falls_through_to_agent_step_in_L5`.
- **Routing override pointing to an agent that was unattached mid-conversation**: L4's engine ignores the override (override → fall through to rule-walk). L5 audit-logs the FINAL decision; the override is NOT visible in the audit log (only the final route is — the engine's `reason` field tells the operator how the route was picked).
- **`session_metadata` doesn't yet have a "routing" key**: `append_to_session_metadata`'s list-append semantic creates the key on first write (per the F6 primitive's contract).
- **Pool acquire fails for the routed agent at step 10**: log + return. Audit-log entry marks `disposition: "no-eligible"` (the pool failure has the same observable shape as no-eligible — the inbound goes unanswered). Alternative: a new `disposition: "pool-failure"` could be added, but L5 keeps the disposition vocabulary minimal; F10 hardening can refine.
- **No-eligible system-outbound emission fails**: log the exception; do NOT raise. The peer's message goes unanswered; the audit log preserves the "no-eligible" disposition for the operator to debug.
- **`agent_step` raises an unhandled exception**: existing F3+F4 behavior — the ContextVar is reset; the exception propagates. F8's gateway-listener catches and degrades. L5 does not change this.
- **Concurrent inbounds on the same session — routing-override race**: L5 ships the `set_session_metadata_key` primitive with last-writer-wins concurrency posture. L6's `/talk-to` handler relies on this. L5's tests pin the per-session-lock serialization at step 12, so the routing decision is computed BEFORE the lock — concurrent inbounds compute routing independently, then serialize at the lock. This is fine for v1; the audit log preserves both decisions.
- **Concurrent `append_to_session_metadata` writes — pre-existing F6 race**: the F6 primitive does read-modify-write under a single connection without a transaction boundary. Two concurrent appends to `session_metadata["routing"]` can lose one entry (the second-to-fire reads BEFORE the first-to-fire writes; both write back the SAME pre-modified state with their own entry added). L5 inherits this F6 limitation for both `"audit"` and `"routing"` keys. Acceptable for v1 — concurrent inbounds on the same session are an uncommon path (per-session lock serializes the consequential agent.step work); F10 hardening can wrap the primitive in a transaction.
- **`db_session.session_metadata is None`** (a brand-new session with no metadata written yet): `json.loads(... if ... else {})` collapses to `{}`. The engine reads `session_metadata.get("routing_override")` → `None`. Step 1 of L4 falls through. Correct.

## Files Affected

- `the_one/db/repositories.py` — add `ChatSessionRepository.set_session_metadata_key`.
- `the_one/connectors/_inbound.py` — restructure `dispatch_inbound`; remove `_resolve_single_attached_agent_or_first_alphabetical`.
- `the_one/connectors/_commands.py` — add `_dispatch_builtin_command` placeholder.
- `tests/test_db_repositories.py` — 5 new tests for `set_session_metadata_key`.
- `tests/test_connectors_inbound.py` — 8 new integration tests for the new dispatcher flow.
- `the_one/connectors/README.md` — document the new 11-step composition order.
- `the_one/agents.md` — document the F7 routing-engine convention.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)

## Citation Audit

Citations verified against current code at leg design time:

| Citation | Status | Notes |
|----------|--------|-------|
| `the_one/connectors/_inbound.py:77-102` (`_resolve_single_attached_agent_or_first_alphabetical`) | OK | L3-landed transitional helper |
| `the_one/connectors/_inbound.py:105-419` (`dispatch_inbound` body — full span) | OK | Body extends to line 419; spans 144-345 are the L3+F6 head sections that L5 restructures; 320-419 is the per-session lock + agent.step + visibility-tagging tail that L5 preserves verbatim except for `factory.create(agent_name)` substitution of `decision.agent` |
| `the_one/connectors/_inbound.py:240-319` (F6 resolver consult + audit entries) | OK | Permit/Deny/NeedsPairing handling spans the cited lines |
| `the_one/db/repositories.py:846-885` (`append_to_session_metadata`) | OK | F6 primitive verified |
| `the_one/connectors/_commands.py:_parse_command` | OK | L1 pure function |
| `the_one/connectors/_routing.py:resolve_routing, RoutingDecision` | OK | L4 pure function + dataclass |
| `the_one/connectors/_acl.py:admits_inbound` | OK | L2 pure function (consumed by L4 internally, NOT by L5) |
| `the_one/db/repositories.py:SQLiteAgentStore.list_by_connector_account` | OK | L3 helper |
| `the_one/tools/connector_send.py:183-200` (system-outbound shape) | OK | `pool_acquire → client.send` call pattern verified |
| `the_one/connectors/_pool.py:acquire` (re-exported as `pool_acquire`) | OK | F4 pool path |
| `the_one/connectors/_session.py:resolve_session` (signature with `agent_name` kwarg) | OK | F3 resolver; `agent_name` is creation-time anchor for new rows; reuse path ignores |

11 citations verified against current code at leg design time.
