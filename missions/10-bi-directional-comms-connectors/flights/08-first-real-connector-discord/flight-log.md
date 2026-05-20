# Flight Log: First Real Connector — Discord

**Flight**: [First Real Connector — Discord](flight.md)

## Summary

Planning complete. F8 is designed; Phase 5b Architect design review landed (2026-05-20, 2 cycles); high-severity feedback incorporated. Operator signed off 2026-05-20; status flipped `planning` → `ready`. F8 is ready for leg cycle start via `/agentic-workflow`.

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

---

## Design Review — Phase 5b (2026-05-20)

Architect agent ran against the F8 spec. Verdict: **needs rework** — three high-severity issues, six medium-severity issues. All incorporated:

**High-severity (must-fix, all addressed)**:
1. **v19 schema migration commitment was missing.** Spec said "Schema migrations — none" but `agents.md:302`, `connectors/README.md:307-311`, and `db/schema.py:488-489` all commit F8 to landing v19 (`CHECK (type IN ('discord'))` via table-rename ceremony). L2 expanded to include the migration; Key Non-Modifications updated.
2. **8-layer connector-type extension checklist under-covered.** Spec only addressed layer 3 (registry); `agents.md:299-306` enumerates layers 1, 2, 3, 4 as F8-owned plus participation in 5, 6, 8. L2 expanded to bundle layers 1 (Literal narrowing) + 2 (`CONNECTOR_TYPES`) + 3 (registry body) + 4 (v19 migration) + 5 (API gating verify) + 6 (Studio frontend badge/tokens). Layer 8 already shipped by F4.
3. **Stub-in-dev-mode contradicts `_stub.py:18-19` invariant.** Even a gated `import` violates "Production code MUST NOT import this module." Compounded by the v19 CHECK — `'stub'` would have to be in the constraint, re-introducing the leak that `agents.md:302` says v13/v14 deliberately avoided. Design Decision reversed; OQ7 resolved (b) "F8 HAT IS the F1-F7 integration HAT."

**Medium-severity (all addressed)**: pool-budget mitigation misread (reconnect lives in `DiscordClient`, not the pool — Adaptation Criteria fixed); pairing-prefix whitespace tests added to L1; stale `editor.js` Enable-toggle refs added to L8 cleanup; Mission #10 added to Contributing to Criteria; step-11 docstring rewrite added to L1; `_VALID_ROUTING_SCOPES` resolved as rename (drop underscore) instead of `__all__`; `test_db_repositories.py:1024-1029` seed-data rename added to L2.

**Low-severity / suggestions absorbed**: L1 bundle accepted as-is (8 surfaces but each independently revertible); F6 F10-candidate races added as divert clauses in Adaptation Criteria; discord.py exact-patch pin pinned at L2 design-time; `_translate_discord_message_to_envelope` belongs in pure-function module (L4); slash-command registration is PUT-style idempotent (L9); Playwright snapshot baselines gitignored per user-global rule (L10).

**Open questions from Architect, deferred to per-leg design**:
- `_default_not_dm` shape: bool-returning function vs `None`-sentinel — pinned at L6.
- Interactions translator: extend `_translate_discord_message_to_envelope` or sibling module — pinned at L4/L9.

Spec is now codebase-validated. Per the Phase 5b workflow, this counts as design-review cycle 1 of 2; if a re-review pass surfaces nothing material, F8 proceeds to leg cycle start.

### Design Review Cycle 2 (2026-05-20)

Second Architect pass against the edited spec. Verdict: **approve with changes**. All cycle-1 high-severity items confirmed resolved:

- v19 migration: sufficient for an implementer; v6/v12 pattern aligns with `db/schema.py:488-489`.
- 8-layer extension bundle: L2 still sub-day credible; layer-5 framing as "verify type-agnostic" matches `api.py:2088-2372`.
- Stub-in-dev-mode reversal: watertight on the import-time invariant.
- Pool-budget mitigation: correctly fixed against `_pool.py:91-95, :187-228` actual semantics.
- Stale `editor.js` Enable-toggle refs: verified present at `:658` and `:1361`.
- F6 race divert clauses: appropriately scoped.
- Mission #10 evidence pointers (L3 + L7): accurate.
- `VALID_ROUTING_SCOPES` rename safe — only consumer outside `db/models.py` is the JS at `connector-account-editor.js:1451-1487` which hard-codes the array literal independent of the Python symbol.

Cycle-2 drift fixes incorporated:
- Pre-Flight Checklist OQ count: 7 → 8 (1 resolved + 7 deferred-to-leg).
- Pre-Flight Checklist Design Decisions count: 9 → 12.
- Post-Flight `agents.md` doc list: replaced "dev-mode-conditional-stub-registration pattern" with "reaffirm `_stub.py` invariant + v19 CHECK cross-reference."
- v19 Design Decision title: "Layers 1, 2, 5, 6" → "Layers 1-6" (matches body).
- Carry-forward row for `_VALID_ROUTING_SCOPES`: updated from "Export to `__all__`" to "Rename (drop underscore)."
- F6/Architect carry-forward table row for 8-layer checklist: language tightened to enumerate all 6 layers correctly.

**Substantive cycle-2 question — L2 Literal-vs-stub clash** (69 test-site instantiations of `ConnectorAccount(type="stub")`): resolution defaulted in the v19 Design Decision to **include `'stub'` in `CONNECTOR_TYPES`** per the M07 `'mock'`-in-`PROVIDER_TYPES` precedent. The `_stub.py:18-19` import-time invariant is the right enforcement layer for production-purity, not the CHECK. Final call deferred to L2 design with explicit reference to the M07 precedent. The stub-in-dev-mode rejection and the stub-in-CHECK question are now decoupled — the former is closed (rejected); the latter defaults open with M07-precedent guidance.

Spec is now ready for operator sign-off and leg cycle start. Design review cycles consumed: 2 of 2 (max).

### 2026-05-20 — Operator sign-off

Operator endorsed:
1. **Mark as ready** — status flipped `planning` → `ready`.
2. **Keep `'stub'` in `CONNECTOR_TYPES` and v19 CHECK** (default (a) from the L2 stub-placement Open Item) — aligns with the M07 `'mock'`-in-`PROVIDER_TYPES` precedent; avoids touching 69 test sites. Registry-side stub registration stays test-only via `register_for_test`; the `_stub.py:18-19` production-import invariant is the enforcement layer for production-purity.
3. **L2 stays as one leg** — bundle of SDK pin + plugin skeleton + 8-layer extension checklist (layers 1-6) + v19 CHECK migration + test seed-data updates approved as a single sub-day leg.

L2 design language firmed up accordingly:
- `Literal["discord", "stub"]`, `CONNECTOR_TYPES = ("discord", "stub")`, `CHECK (type IN ('discord', 'stub'))` derived via `_CONNECTOR_TYPES_SQL` projection.
- `register_builtin_connectors()` registers `'discord'` only.
- Pre-Flight Checklist items all ticked.

Next: spawn `/agentic-workflow` to drive the leg cycle starting at L1.
