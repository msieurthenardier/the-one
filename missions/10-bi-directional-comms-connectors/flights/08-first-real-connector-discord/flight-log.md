# Flight Log: First Real Connector — Discord

**Flight**: [First Real Connector — Discord](flight.md)

## Summary

Planning complete. F8 is designed; awaiting operator sign-off before Architect design review + leg cycle start.

---

## Leg Progress

_(no legs executed yet)_

---

## Decisions

_(no runtime decisions yet)_

---

## Deviations

_(no deviations yet)_

---

## Anomalies

_(none observed yet)_

---

## Flight Director Notes

### 2026-05-20 — Flight planning

- F7 merged to main as commit `dfff8ac flight/07: multi-agent routing and platform-side command surface (#67)`. F6 merged as `93c4120` (#65). Both predecessors landed.
- F7 debrief enumerated 14 actionable recommendations. Operator instruction at F8 design time: "pull in every recommendation." F8 spec carries a disposition table at the bottom: 9 absorbed into F8 scope (across L1 carry-forward bundle + L6 DM hook + L8 allowlist axes + L10 browser test); 5 explicitly deferred to F10 / routine-maintenance with rationale; zero silent drops.
- 7 Open Questions captured with documented defaults: discord.py 2.4+ pin; Message Content intent required; per-guild slash-command registration; `is_dm` via `getattr` sentinel (not Protocol widening); allowlist axes extended on existing reserved key (not plugin-specific); reconnect budget 5 attempts (1s/2s/4s/8s/16s); stub plugin registered in dev mode.
- 9 Design Decisions documented. The two highest-impact: (i) `CommandHandler` consult site lands in L1 (closes F7's Critical #1 gap before F8's slash-command work depends on it); (ii) stub plugin registered in dev mode behind `settings.environment` gate (resolves F6 debrief K3 / F7 debrief deferral — operator can drive F1-F7 commands end-to-end without a real Discord bot).
- 11 legs planned. F8 is larger than F7 (8 + HAT = 9) because it's the first real-connector validator AND pulls in F7 debrief carry-forward. The L1 bundle absorbs all small F7 carry-forwards (CommandHandler consult + audit-log doc fix + 2 agents.md codifications + 3 minor doc fixes + 1 spec-text typo + stub-in-dev). L2-L9 ship the Discord plugin. L10 closes the F7 routing-rules-editor browser-test gap. L11 is the operator HAT.
- Per the `/agentic-workflow` protocol, this flight artifact lands on main as a planning commit; legs are designed + reviewed + implemented one at a time during execution. No code changes yet.

---

## Reconnaissance Report

F7 debrief action items walked against current main code. All 14 items classified:

| Item | Classification | Evidence | Disposition |
|---|---|---|---|
| `CommandHandler` consult missing in dispatcher | confirmed-live | `_inbound.py` step 11 calls only `_dispatch_builtin_command`; no `getattr(plugin, "handle_command", ...)` consult; `base.py:377-419` Protocol declared but unused | L1 wires |
| HAT-driven contract-flip migration discipline not codified | confirmed-live | `agents.md` grep for "HAT" yields no methodology paragraph | L1 codifies |
| `per-axis-tri-state-override` convention not codified in `agents.md` | confirmed-live (partial) | `_acl.py:19-37` carries the framing; `agents.md` Connector subsystem references but doesn't formally name | L1 codifies |
| Audit-log "original failed pick" promise unfulfilled | confirmed-live | `_routing.py` emits single `RoutingDecision`; F7 flight spec at `legs/04-routing-resolution-engine.md` promises chain | L1 doc-fix |
| No Playwright test for routing-rules editor | confirmed-live | `tests/browser/test_flow_studio_connector_account_editor.py` has the `_activate_access_and_routing_tab` helper from HAT1 but no test using it for the routing-rules section specifically | L10 adds |
| `_handle_whoami` same-turn semantic only in docstring | confirmed-live | `_commands.py:165-167` docstring; `connectors/README.md` §13 doesn't surface | L1 promotes |
| Pool-acquire branches step 10/12 not sharing state — no comment | confirmed-live | `_inbound.py` step 10 acquires `client`; step 12 uses `factory.create`; no comment explaining | L1 adds |
| `_VALID_ROUTING_SCOPES` not in `__all__` | confirmed-live | `db/models.py:121` module-level constant; `__all__` doesn't export | L1 exports |
| `AgentConfigRepository` → `SQLiteAgentStore` typo in F7 spec | confirmed-live | `legs/03-inverse-query-helper-and-dispatcher-rename.md` notes the typo as "deferred to debrief"; F7 `flight.md` Design Decisions section still references the wrong name | L1 corrects |
| Keyboard-fallback for drag-reorder | confirmed-live | `connector-account-editor.js` move buttons are mouse-only | Deferred to F10/routine-maintenance |
| F10 audit-log inspector (Studio for `session_metadata["routing"]`) | confirmed-live | No Studio surface renders routing audit entries; HAT step 6 accepted unit-test coverage | Deferred to F10 |
| DM-classification consult site | confirmed-live | `_acl.py:95` + `:171` carry the `# F8: DM classification lands here` markers | L6 implements |
| Stub plugin not in production registry | confirmed-live | `registry.py:147` `register_builtin_connectors` body is empty in production paths; `register_for_test` is test-only | L1 adds dev-mode conditional registration |
| Dispatcher decomposition (12 steps / ~450 LOC) | confirmed-live | `_inbound.py` dispatch_inbound spans ~lines 156-599 | Deferred to F10 hardening |

All 14 items remain real at flight-design time. Six are absorbed into L1 (carry-forward bundle); three into L6/L8/L10; five deferred to F10/routine-maintenance with documented rationale. Zero already-satisfied / partially-satisfied / drifted classifications.
