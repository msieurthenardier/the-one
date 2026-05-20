# Flight Log: First Real Connector — Discord

**Flight**: [First Real Connector — Discord](flight.md)

## Summary

Planning complete; Phase 5b Architect design review landed (2026-05-20, 2 cycles); operator sign-off 2026-05-20. Status flipped `ready` → `in-flight` 2026-05-20; `/agentic-workflow` orchestrator engaged on branch `flight/08-planning-discord` (planning branch continues as execution branch — no separate execution branch). L1 design starting.

---

## Leg Progress

### Leg 1 — f7-carry-forward-bundle
**Status**: landed
**Started**: 2026-05-20 (design)
**Completed**: 2026-05-20 (implementation landed)

#### Design Review Cycles

**Cycle 1** surfaced 5 issues:
- HIGH: `tests/test_pairing_prefix.py` already exists (F7 L8, 8 tests) — original AC declared it "NEW" and contradicted shipped `test_leading_whitespace_fails` behavior. Reframed as EXTEND with 4 non-overlapping cases (ZWJ in code arg, NBSP between PAIR and code, smart quotes inside code, multi-line text remainder). Dropped contradictory "leading/trailing whitespace tolerated" case.
- HIGH: Plugin-consult vs built-in audit-write symmetry not documented. Added Edge Case explaining audit-then-send ordering matches built-in path.
- MEDIUM: No timeout on `plugin.handle_command` await. Deferred to F10 per existing built-in unbounded posture; explicit carry-forward note added to Post-Completion Checklist.
- MEDIUM: Audit-log discriminator missing. Added `intercept_source: "plugin" | "builtin"` sibling key to both consult-paths.
- LOW: Byte-identical regression wording and post-edit grep verification tightened.

**Cycle 2** surfaced drift fixes only:
- HIGH: "(NEW)" stale + "six" count in Files Affected / Verification Steps corrected to "(EXISTING)" + "four".
- HIGH: `agents.md` §2 conventions list was wrong (claimed 9, actual 12) and section is insertion-ordered NOT alphabetical. Rewrote AC #6 to drop alphabetical framing and name correct cluster positions.
- MEDIUM: Plugin-timeout F10 carry-forward needed explicit checklist step — added.
- LOW: Grep bound tightened to ≥6; ZWJ test case input made explicit.

Cycles consumed: 2 of 2 (max). Status flipped `planning` → `ready`.

#### Changes Made

Ten surfaces landed in the order prescribed by Implementation Guidance (independent items first, dispatcher consult last so it landed on a green baseline):

1. **`tests/test_pairing_prefix.py`** — extended the existing `TestValidatePairingPrefix` class with four new whitespace edge cases (ZWJ in code arg, NBSP between PAIR and code, smart quotes inside code, multi-line text remainder). Module docstring updated with M10 F8 L1 cross-reference alongside the F7 L8 citation. Class is now 12 tests (8 existing + 4 added).
2. **`the_one/db/models.py`** — `_VALID_ROUTING_SCOPES` → `VALID_ROUTING_SCOPES` rename at the declaration (line 121) and two consumers (lines 375, 378). Verified grep: 0 underscored hits, 3 unprefixed hits.
3. **F7 spec typo correction** — four `AgentConfigRepository` → `SQLiteAgentStore` replacements in `missions/10-bi-directional-comms-connectors/flights/07-multi-agent-routing-and-command-surface/flight.md` (lines 38, 104, 170, 233). Each carries a `<!-- F8 L1 post-hoc reconciliation -->` HTML comment for auditability. Verified post-edit: 0 `AgentConfigRepository` hits, 6 `SQLiteAgentStore` hits.
4. **`connectors/README.md` §13** — added a one-sentence note to the `whoami` paragraph promoting `_handle_whoami`'s same-turn semantic ("response reflects the same `RoutingDecision` the dispatcher just resolved for this inbound — never stale state from a prior message").
5. **`agents.md` §2 Project Conventions** — added two entries in insertion order at cited cluster positions:
   - `hat-driven-contract-flip-migration-discipline` after `host-side-bench-drift-detection` (methodology cluster). Cites F6 HAT3.
   - `per-axis-tri-state-override` after `optional-plugin-hook-via-getattr-sentinel` (connector-conventions cluster). Cites F6 `_acl.py` + F8 L8 future extension.
6. **`_inbound.py` step-10/step-12 boundary comment** — single-line annotation noting the two pool acquisitions do NOT share state.
7. **`_routing.py` module docstring + `agents.md` Connector subsystem cross-reference + F7 spec language reconciliation** — three coordinated doc updates landing the audit-log "single-winner" clarification. F7 spec's "fallback is audit-logged with the original failed pick" promise reconciled with an explicit "F8 L1 post-hoc reconciliation" paragraph; matching paragraphs in `_routing.py` docstring and `agents.md` Connector subsystem section cross-reference the canonical contract.
8. **`_inbound.py` step-11 docstring rewrite** — replaced the F7-leg-referencing block at lines 450-456 with shipped-behavior language describing the (i) parse, (ii) plugin consult via `getattr` sentinel, (iii) built-in dispatch, (iv) fall-through-to-agent.step flow. New comment cites M10 F8 L1.
9. **`_inbound.py` step-11 plugin-consult sub-step insertion** — added the `getattr(plugin, "handle_command", None)` consult BEFORE `_dispatch_builtin_command` per the exact code shape in AC #1. Plugin-raised exceptions are logged + treated as `None`. `audit_entry["intercept_source"] = "plugin"` write on the plugin-intercept path; matching `audit_entry["intercept_source"] = "builtin"` write added to the existing built-in path. Both paths preserve the existing `disposition="command-intercepted"` value.
10. **`tests/test_connectors_inbound.py`** — two new tests appended to `TestF7RoutingIntegration` per AC: (a) `test_dispatch_inbound_plugin_handle_command_intercepts_before_builtin` — plugin returns non-None response, asserts outbound emit + audit-log `intercept_source="plugin"` + `_dispatch_builtin_command` not called (monkeypatch-spied); (b) `test_dispatch_inbound_plugin_handle_command_returning_none_falls_through_to_builtin` — plugin returns None, dispatcher falls through to built-in handler, audit-log carries `intercept_source="builtin"`. Both tests use a per-test `_CommandHandlingStub` / `_NoneReturningPlugin` subclass of `StubPlugin` registered via `register_for_test`.

#### Test Results

- `docker exec the-one pytest tests/test_pairing_prefix.py -x --timeout 30` — 12 passed (8 existing + 4 added).
- `docker exec the-one pytest tests/test_connectors_inbound.py -x --timeout 30` — 40 passed (38 existing + 2 added).
- `docker exec the-one pytest tests/ -x --timeout 30` — 2268 passed, 4 skipped, 411 deselected (default-excluded browser tests). No F1-F7 regression. A pre-existing aiosqlite teardown warning ("Event loop is closed") is unrelated to L1 changes.

#### Notes

- The dispatcher's function-local import pattern for `_dispatch_builtin_command` made the plugin-intercept spy patch reach via `the_one.connectors._commands._dispatch_builtin_command` (the source module attribute) — not via `the_one.connectors._inbound._dispatch_builtin_command` (which doesn't exist at module scope). Documented inline in the test.
- All ten AC items verified. Bundle is sub-day total; each surface is independently revertible.

##### F10 Carry-Forward

- **Plugin-handler-timeout** — L1's plugin `handle_command` consult is NOT wrapped in `asyncio.wait_for(...)`. The built-in `_dispatch_builtin_command` is also unbounded — matching the F7-shipped posture. Adding a timeout for plugin paths only would introduce an asymmetry the leg shouldn't carry. **Revisit in F10 hardening** if F8 L11 HAT surfaces actual stall scenarios; F10 design should add a uniform per-handler timeout (both paths) rather than asymmetric coverage.

---

### Leg 2 — discord-plugin-foundation-and-type-registration
**Status**: ready (design complete; implementation pending)
**Started**: 2026-05-20 (design)
**Completed**: _(pending)_

#### Design Review Cycles

**Cycle 1** surfaced four issues, all incorporated:
- HIGH: `DiscordPlugin.__init__(self, account, encryptor)` was wrong against the F1 construction site (`registry.py:76` calls `cls()` zero-arg; `StubPlugin` at `_stub.py:72+` is stateless). Reshaped to stateless plugin matching the StubPlugin precedent — methods take `account, encryptor` as parameters from the pool's call site; L3 places per-connection state on the returned `ConnectorClient`, not on the plugin.
- HIGH: Registry-vs-tuple consistency check was a subset (too loose — wouldn't catch drift like adding `"slack"` to `CONNECTOR_TYPES` without registering it). Tightened to `set(registry.types()) == set(CONNECTOR_TYPES) - {"stub"}` exact equality with `"stub"` carved out by literal name.
- MEDIUM: `_CONNECTOR_TYPES_SQL` placement wording ambiguous ("at schema.py:17" could be read as "overwrite line 17"). Changed to "immediately below `_PROVIDER_TYPES_SQL`."
- MEDIUM: v13 `connector_accounts` comment at `schema.py:485-490` still reads as forward-looking. Added new AC to update the comment + cite the v3/v6-vs-v13/v19 divergence (v3 had CHECK from day one; v13 deferred because `CONNECTOR_TYPES` was empty).

Plus a JS module-scope cache edge case added (operators with Studio already mounted will see stale empty list until refresh).

**Cycle 2**: API hit transient 529 Overloaded errors twice; review skipped. Cycle-1 fixes verified by direct code-read against `StubPlugin` (`_stub.py:72-200`) and `registry.py:76` `cls()` call site. Implementation Developer is the safety net for any remaining drift.

Cycles consumed: 1 of 2 (cycle 2 attempted but the API was overloaded; proceeding to implementation).

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
