# Flight Debrief: Multi-Agent Routing and the Platform-Side Command Surface

**Date**: 2026-05-19
**Flight**: [Multi-Agent Routing and the Platform-Side Command Surface](flight.md)
**Status**: landed
**Duration**: 2026-05-19 (single-day flight; ~6-8h orchestrator wall-clock across 8 autonomous legs + 3 HAT iterations + commit + push)
**Legs Completed**: 9 of 9 (8 autonomous + 1 HAT)

## Outcome Assessment

### Objectives Achieved

F7's stated objective landed cleanly. Multi-agent routing now resolves an inbound to exactly one of N agents attached to a connector account via three composing layers: peer-issued `/talk-to` override → operator-configured rules (per-channel/thread/dm/peer + per-account default) → F6 per-agent ACL gating. Six v1 commands (`/agents`, `/talk-to`, `/whoami`, `/new`, `/reset`, `/help`) ship as a connector-agnostic primitive with text-prefix parsing; `CommandHandler` Protocol is declared as F8/F9's extension point for platform-native slash-command registration. Commands dispatch system-side, short-circuiting `agent.step` and emitting responses via the same `pool_acquire → client.send` path the platform-send tool uses.

No agent-loop changes (mission constraint preserved). No schema migration. F6 outbound reason strings preserved byte-identically by exact-equality regression tests at `tests/test_connector_send_tool.py:661-664, 692-695, 742-746`.

### Mission Criteria Advanced

F7 contributes to six M10 success criteria:

- **#6**: An inbound on a connector account with N attached agents routes to exactly one of them per operator-configured rules. **Met** — routing engine + rule-walk + override + default + first-eligible-alphabetical fallback all land and are dispatcher-wired.
- **#20**: Each connector-attached session's routing decision is logged in session metadata so the operator can see why each session went to which agent. **Met** with one narrowing: the audit log records the *eventual winner's* path, not the *chain* of skipped candidates (see Deviations).
- **#21**: A platform-side command surface lets peers invoke `/agents /talk-to /whoami /new /reset /help`; commands gated by per-(agent, peer) and per-(agent, channel) permissions composing with the connector-account-level allowlist. **Met** via the L6 handlers + L5 dispatcher intercept + the L7 `_acl.admits_inbound` ACL composition.
- **#22**: The command surface is a connector-agnostic primitive — adding a new connector inherits the full command set without re-implementing the parser, the permission checks, or the help text. **Met** for the built-in path. The `CommandHandler` Protocol (intended as the per-platform slash-command extension point) is **declared but not yet consulted by the dispatcher** — see "What Could Be Improved → Technical."
- **#28**: Studio surfaces meet the M04/M06 design-language quality bar (F7 adds the Routing Rules editor on the connector account). **Met** — cycle-1 design-language audit found ZERO new bespoke CSS selectors; HAT iteration 1 also addressed editor-page density via a 2-tab layout matching the Agent Editor pattern.
- **#29**: Each layer has automated coverage. **Met and then some** — 188 net new tests across routing-rule resolution, command parsing + execution, command-permission gating, ACL admission both directions, audit-log routing entries, repository inverse-query.

## What Went Well

- **Pre-flight Open Questions resolution was exemplary.** 13 of 15 resolved at planning time with documented defaults; the 2 deferred (thread-vs-channel scope shape; `/new` vs `/reset` distinct-or-alias) were resolved at L2 design and L6 implementation respectively. **Zero questions surfaced at implementation time that hadn't been pre-vetted.**
- **Pure-function discipline paid for itself in test throughput.** Despite +188 tests, full-project wall-clock DECREASED 2.19s vs F6 (157.08s vs 159.27s). Throughput recovered to ~14.4 t/s, back near pre-F6 levels. The four new pure-function modules (`_routing.py`, `_acl.py`, `_commands.py` parser portion, plus the L5 sibling primitive) each run against tiny inline fixtures rather than DB-backed setups.
- **Design-review cycle caught real defects pre-implementation.** L3's class-name typo `AgentConfigRepository` (actual: `SQLiteAgentStore`); L7's missing `chevron-up` icon + nonexistent `.btn-icon` primitive (would have surfaced as 18+ HAT defects per F6's precedent); L6's `/help` permission-filter contradiction with the flight Design Decision; L2's wrong-test-file citation for the F6 outbound exact-equality regression net. Every one of these was caught before code landed.
- **L3 fixture-default cascade was textbook**. The `_seed_provider_and_agent` helper's `connector_account_ids` default flip (`None → ["acct-test"]`) was an unanticipated dividend — 29 bare-call tests adopted the attachment for free; 13 explicit callers stayed byte-identical. The fixture audit upfront (53 bucket-a / 0 bucket-b / 0 bucket-c) gave high confidence the transition was safe.
- **HAT iteration 1's tabs refactor finished in one cycle with zero new CSS primitives.** The Developer agent recognized the Agent Editor's `App.tabs` pattern as the canonical shape and slotted the connector account editor into it. Existing tab styles already covered the layout; only the `connector-routing-section` got minimal additive CSS via slot-extension of existing rule groups.
- **HAT iteration 2's chip-list match landed cleanly across backend + frontend + tests** in a single cycle — schema validator, routing engine `_scope_matches`, frontend chip-list editor, 6 affected test files, and a `RoutingDecision.match` semantic clarification. The change scope was large but well-contained per leg/file.
- **The 12-step dispatcher composition is documented as a docstring contract**, not just code. `_inbound.py:53-124` reads as a specification — a future maintainer dropping or reordering a step has the spec in hand. F6 hinted at this discipline; F7 raised the density.
- **F1-F6 byte-identical regression.** 39 exact-equality outbound reason-string assertions at `test_connector_send_tool.py` pass unchanged. Agent loop untouched. F4 platform-send tool's contract preserved. Mission constraint stewardship was tight.

## What Could Be Improved

### Process

- **Design Decision #8's audit-log promise was narrowed silently.** The flight artifact says "audit-log preserves the original failed pick (rule_index, scope, match, reason)" — meaning when a rule's targeted agent fails ACL, the audit log should record both the failed pick AND the eventual winner. Shipped behavior: the routing engine emits a SINGLE `RoutingDecision` from a linear sweep; only the winner's path lands in `session_metadata["routing"]`. An operator debugging "why did this rule not fire" has no audit trail. **Either revise the engine to emit a chain of decisions, or revise the doc to acknowledge the narrower contract.** Spec-vs-ship gap, not a defect.
- **HAT-driven contract flips need a data-migration design checkpoint.** HAT2 tightened `match: str → list[str]` on both read AND write paths in one stroke; HAT3 was the hotfix when existing dev-DB rows failed validation on read and took down `GET /api/connector-accounts`, cascading into the Agent Studio (which fetches connector accounts on mount). The hotfix (validator read-path coercion in-place) is the right pattern, but it should have shipped *with* HAT2, not after the operator-visible regression. **Codify as a project pattern**: HAT-driven contract flips require either backward-compat read coercion or an SQL migration in the same iteration.
- **HAT scope projection was off.** The flight projected "~3-5 iterations max" (Design Decision #12: "Optional lightweight HAT — single-surface scope"). Actual: 3 iterations, but iteration 2 was a backend schema flip (not the single-surface UX issue the projection anticipated), and iteration 3 was a regression-recovery hotfix. **HAT is the right axis for both UX-density and semantic-expressiveness discoveries; the planning team should expect either kind from a HAT cycle.**

### Technical

- **CRITICAL: `CommandHandler` Protocol shipped without dispatcher consult site.** `base.py:377-419` declares the Protocol with docstring promising "Connectors that do NOT implement it … fall through to the dispatcher's built-in text-prefix command parser." `_inbound.py` step 11 calls only `_dispatch_builtin_command(...)`; there is **no `getattr(plugin, "handle_command", None)` consult** anywhere. A reader of the Protocol's docstring will look for the fall-through point and not find it. F8 will need to wire this — but the spec advertises it as F7-landed. **Recommended fix**: add a one-line consult to step 11 (`plugin_response = await plugin.handle_command(...)` if `getattr(plugin, "handle_command", None) else None`) as F7 cleanup. ~3 LOC. Alternative: explicitly retitle the convention to "Protocol type ships F7 L1; dispatcher consult wires F8."
- **Dispatcher decomposition is on the horizon.** `_inbound.dispatch_inbound` is at 12 steps / ~450 LOC. F8 (Discord) is likely to add a DM-classification step (deferred at `_acl.py:95, 171` per L8 markers); F9 (Slack) may add slash-command registration. At step 15+, decomposition becomes mandatory. Pre-plan an `InboundContext` dataclass that carries `account`, `session_row`, `working_envelope`, `audit_entry`, `eligible_attached_agents`, `client` across the steps, and split on the per-session-lock boundary.
- **Pool-acquire failure overloads `disposition: no-eligible`.** Step 10's pool-acquire-failure branch and step 9's no-eligible-agents branch both write the same `no-eligible` disposition. An operator inspecting the audit log cannot distinguish "no agent eligible" from "pool acquire failed." A `"pool-failure"` disposition would surface the distinction; F10 hardening territory.
- **`_handle_whoami` reports the routed agent of THIS turn, not the override target.** If a peer types `/talk-to bravo` then `/whoami` in the same session before the next inbound, `/whoami` reports the agent that handled the `/whoami` itself — which is NOT bravo (overrides apply to the next inbound). The docstring acknowledges this; the UX defect is documented but un-fixed. Surface for F10 or mission-debrief.
- **Mouse-only drag-reorder for routing rules.** HAT2 explicitly deferred keyboard-fallback reorder. Keyboard-accessibility regression for operators on keyboard-only workflows. F10 hardening or routine-maintenance candidate.

### Documentation

- **Flight spec's L3 class-name typo persists.** `flight.md` Design Decision section references `AgentConfigRepository` (planning-time wrong name); actual class is `SQLiteAgentStore`. The leg-3 artifact corrected this in its own body and noted the flight.md correction as deferred to the debrief. **This debrief acknowledges the typo and flags it; future spec readers should disregard.**
- **Per-axis tri-state codification still partial.** F6 debrief rec #3 asked for codification in `agents.md` Connector subsystem; F7 added a routing-convention paragraph but the asymmetric "defaulting (account-scope) vs narrowing (per-agent)" framing remains only in `_acl.py`'s module docstring. **Recommend full codification in `agents.md` as a named project convention** alongside `optional-plugin-hook-via-getattr-sentinel` and `structural-Protocol-satisfaction`. The pattern is now n=2 (F6 ACL + F7 routing); worth elevating.
- **No Playwright/browser test for the routing-rules editor.** L7 added a single API round-trip test in `test_db_api.py`; the actual UI behaviors (drag-drop reorder, chip-list multi-value, default-agent stale-selection preservation, snapshot-after-async-population baseline) were HAT-validated only. A `_activate_access_and_routing_tab` helper landed at HAT iteration 1 specifically for browser-test use; the follow-up Playwright test never landed. **F8 prerequisite or routine-maintenance.**

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Intercept ordering: spec said 8 steps; shipped 12 | L5 surfaced that explicit `list_by_connector_account` enumeration deserves its own dispatcher step; audit-entry construction + the no-eligible / pool-failure branches each needed distinct steps for clarity | **Yes** — codify "if a dispatcher step needs distinct error-handling, it deserves its own numbered step in the docstring contract" |
| ACL admission absorbed INTO routing engine (not a separate post-routing gate) | Engine's `_agent_admits` lets every candidate (override / rule / default / first-eligible) check ACL before being picked; cleaner than dispatcher-side retry loop | **Yes** — but audit promise needs adjustment (see Spec-vs-ship gap above) |
| `RoutingDecision.match` stays as `str` (the matched envelope value) even after `match: list[str]` schema flip | Audit-log clarity — operator wants to know which value hit, not the whole rule's match list | **Yes** — codify "decision dataclasses carry the matched VALUE, not the rule's accepted-set" |
| HAT iteration 2 schema flip without data migration → HAT iteration 3 hotfix | HAT2 tightened validator on both read + write paths; existing dev-DB rows failed validation; agent studio cascaded into 500s | **Yes (negative)** — codify "HAT-driven validator-contract flips require either backward-compat read coercion or an SQL migration in the same iteration" |
| Studio editor refactored from flat → 2-tab layout (HAT iteration 1) | Page grew to 9 sections; operator declared too dense | **No** — situational; UI density triggers vary per editor. The tab-pattern itself (`App.tabs` reuse) is the standardization, not the threshold |
| L7 `_VALID_ROUTING_SCOPES` hoisted to module-level (project's first module-level constant in `db/models.py`) | F7 L7 Studio editor will want to enumerate scopes for the rule-form dropdown | **No** — situational; cited the hoist rationale in a one-line comment so it stands |
| F8 marker site moved from `tools/connector_send.py:202` → `_acl.py:95, 171` post-L2 extraction | The DMs-only branch moved when ACL was extracted; markers followed | **No** — naturally tracked the code |

## Key Learnings

1. **Pure-function modules with `__all__`-declared private subsystem surface is now the connector subsystem's canonical module shape.** `_pairing.py` (F6), `_acl.py` (F7), `_routing.py` (F7), `_commands.py` parser portion (F7) all follow it. Codify in `connectors/README.md` "Conventions" section.
2. **5-step routing algorithm shape generalizes**: override → operator-rules → default → first-eligible → no-eligible. Pattern (peer-explicit → operator-configured → operator-default → conservative-default → fail-with-audit) extends to any decision-resolution surface. Worth naming as a project convention if F8 needs DM-classification or F9 needs role-based-routing.
3. **The `disposition` field pattern for audit-log entries spanning multiple branches** — `stepped | command-intercepted | no-eligible` lets a single writer cover all dispatcher outcomes. F6's `outcome: permit | deny` was the predecessor; F7's `disposition` is the sibling. Worth considering for any future audit-log additions.
4. **Spec-vs-ship gaps surface fast when the design-review cycle scrutinizes citation accuracy.** L3's class-name typo was caught by the design-review's "verify cited symbols exist" pass; L7's missing `chevron-up` icon was caught by the cycle-1 design-language audit. **Make citation verification an explicit step in every design review.** Already partially codified via the `/leg` skill's Citation Audit step; F7's evidence reinforces.
5. **The cycle-1 design-language uptake audit (F6 debrief rec #1) is load-bearing.** L7 cycle-1 caught at least 5 would-be HAT defects pre-implementation (no `.btn-icon` primitive, no `arrow-up`/`chevron-up` icons, missing `connector-account-config-table` precedent reference, citation drift, wrong wire-up line number). F6's recommendation was vindicated; **continue applying it to every UI leg in M10 and beyond**.
6. **HAT-as-catch-all (F6 precedent) caught real semantic bugs F7 planning missed.** Multi-value `match` (HAT2) and tab-density (HAT1) were operator-driven discoveries the design phase didn't anticipate. **Trust the HAT cycle to surface UX semantic gaps.**

## Recommendations

1. **(Critical) Wire `CommandHandler` Protocol consult into dispatcher step 11.** ~3 LOC change at `_inbound.py:496-516`. Without this, F8 will need to either retroactively wire the Protocol OR plugin authors will have to inherit the unwired Protocol contract. Suggested patch: before calling the built-in dispatcher, attempt `plugin_response = await plugin.handle_command(working_envelope, command_name, args)` if `getattr(plugin, "handle_command", None)`; if non-None, emit it via the system-outbound path; otherwise fall through to `_dispatch_builtin_command`. Same audit-log treatment as the built-in path (`disposition="command-intercepted"`).
2. **(Important) Add Playwright/browser test for the routing-rules editor.** Use the `_activate_access_and_routing_tab` helper from HAT iteration 1. Cover: add rule, fill chips, drag-reorder, save, reload-baseline-not-dirty. Validates the HAT-validated UI behaviors against regression.
3. **(Important) Codify the per-axis-tri-state-override convention in `agents.md`.** F6 debrief rec #3 still partial. Now n=2 across allowlist + routing; worth a named convention in the Connector subsystem section: account-scope axes are DEFAULTING anchors (`[]` = unrestricted); per-agent axes are NARROWING modifiers (`[]` = strongest narrowing — DMs-only for channels; no-peers for peers).
4. **(Important) Document HAT-driven contract-flip migration discipline.** Add to `agents.md` (or wherever HAT methodology lives): "HAT-driven validator-contract flips that change Pydantic schemas storing JSON data require either backward-compat read coercion (validator coerces legacy form in-place) OR an SQL data migration in the same iteration, not after."
5. **(Important) Reconcile the routing-audit "original failed pick" promise.** Pick one: (a) revise engine to emit a chain of skipped candidates (richer audit, larger surface); (b) revise the flight-design language to acknowledge the narrower "eventual winner only" contract. (b) is cheaper; (a) gives operators better debugging.

## Action Items

- [ ] Wire `CommandHandler` Protocol consult into `_inbound.py` step 11 — F7 cleanup, ~3 LOC. **Critical**.
- [ ] Add Playwright test for the routing-rules editor — covers drag-drop, chip-list, snapshot-baseline. **Important**.
- [ ] Codify per-axis-tri-state-override convention in `agents.md` — closes F6 debrief rec #3. **Important**.
- [ ] Codify HAT-driven contract-flip migration discipline — n=1 pattern (HAT2→HAT3). **Important**.
- [ ] Reconcile Design Decision #8's audit-log "original failed pick" promise vs shipped "eventual winner only." Pick (a) richer audit or (b) doc fix. **Important**.
- [ ] Document `_handle_whoami`'s same-turn semantic (reports current-turn agent, NOT override target) more visibly — promote from docstring to `connectors/README.md` v1 command vocabulary section. **Minor**.
- [ ] Document the two pool-acquire branches at steps 10+12 not sharing state — single-line comment at step 10 noting "`client` is consumed only by step 11; step 12 builds its own access via `factory.create`." **Minor**.
- [ ] Add `_VALID_ROUTING_SCOPES` export from `db/models.py` to `__all__` so the L7 Studio editor (and any future routing UI) can import the enum rather than hardcoding. **Minor**.
- [ ] Correct the `AgentConfigRepository` → `SQLiteAgentStore` typo in `flight.md`'s Design Decisions section (planning-time error). **Cosmetic**.
- [ ] **Keyboard-fallback for drag-reorder** in routing-rules editor — F10 hardening or routine-maintenance candidate. **Minor**.
- [ ] **F10 audit-log inspector** — operator-facing Studio surface that renders `session_metadata["routing"]` + `["audit"]` entries. F7 ships the write side only; HAT step 6 accepted unit-test coverage as sufficient for now. **Important for operator UX, deferred to F10**.
- [ ] **F8/F9 DM-classification consult** — replace the fail-closed DMs-only branches at `_acl.py:95, 171` with "permit if envelope is a DM; else deny" using a future `is_dm(envelope) -> bool` plugin hook. **F8/F9 prerequisite**.
- [ ] **Resolve stub-plugin-not-in-production-registry**. F6 debrief K3 carries forward; F7 L9 step 7 deferred smoke commands to F8+. Resolve at F8 planning entry: register stub in dev mode, OR accept "F8 HAT is the F1-F7 integration HAT". **F8 planning decision**.
- [ ] **Dispatcher decomposition** — `_inbound.dispatch_inbound` is at 450 LOC / 12 steps. Pre-plan `InboundContext` extraction for F10 if F8/F9 push toward 15+ steps. **F10 hardening candidate**.

## Test Metrics

**Captured this debrief**:
- F7 regression bundle (`tests/test_connectors*.py + test_connector_send_tool.py + test_db_repositories.py + test_db_api.py + test_pairing*.py`) → **557 passed in 55.03s** (throughput ~10.1 t/s).
- Full project, excl. browser → **2262 passed, 4 skipped, 12 deselected, 1 warning** in **157.08s** (throughput ~14.4 t/s).
- Zero failures, zero flakes observed. 1 pre-existing `aiosqlite` teardown warning (persisted since F3 per F6 debrief; not F7-introduced).

**Comparison vs prior M10 debriefs**:

| Flight | Full-suite count | Wall-clock | Throughput | Net delta |
|---|---|---|---|---|
| F3 | 1881 | 127.40s | 14.8 t/s | baseline |
| F4 | 1945 | 133.73s | 14.5 t/s | +64 tests / +6.33s |
| F5 (unit) | 1983 | 131.69s | 15.1 t/s | +38 tests / -2.04s |
| F6 | 2074 | 159.27s | 13.0 t/s | +91 tests / +27.58s |
| **F7** | **2262** | **157.08s** | **14.4 t/s** | **+188 tests / -2.19s** |

F7 is the largest single-flight test delta in M10, but wall-clock actually decreased. Pure-function module discipline (no DB-backed setup per test) explains the throughput recovery to ~14.4 t/s, back near pre-F6 levels. F6's wall-clock bump (+27.58s for +91 tests) was the outlier; F7 normalizes.
