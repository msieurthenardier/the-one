# Mission Debrief: Bi-directional Communication Connectors

**Date**: 2026-05-20
**Mission**: [Bi-directional Communication Connectors](mission.md)
**Status**: completed (scoped down — F9 + F10 deferred to a follow-on Discord-depth mission)
**Duration**: ~6 months (planning to landed) — F1 landed late 2025; F8 landed 2026-05-20
**Flights Completed**: 8 of 10 (F1-F8 completed; F9 + F10 deferred past M10)

> **Operator framing — debrief invocation**: "we did not fully test all of the criteria and its clear we have gaps, this flight and mission put most of the pieces together but its far from shippable." This honest assessment is the through-line of the debrief: the substrate is structurally complete, the first real connector lands, but mission-criteria coverage is partial and operator-tooling/UX polish is deferred.

---

## Outcome Assessment

### Overall Outcome

**Partial success.** The mission's foundational promise — "land a connector contract and prove it against one real platform" — was achieved. M10 shipped a working Discord connector that an operator registers in Studio, attaches to agents, and receives/sends messages through. The F1-F7 substrate held up architecturally; F8's HAT empirically validated the integration.

But the mission's second promise — "validate the contract is additive by replicating on a second platform" — went unmet. Operator decision after F8 HAT: Discord's depth requirements exceeded the original flight plan, F9 (second connector) and F10 (cross-connector hardening) deferred past M10.

The mission is "substrate-validated, happy-path-validated, far from shippable." Several mission criteria carry only HAT-validation (no automated proof) or are deferred entirely to the follow-on Discord-depth mission.

### Success Criteria Results

Walking the 27 active criteria (criterion #2's "two-connector half" explicitly UNMET):

| # | Criterion | Status | Evidence / Notes |
|---|---|---|---|
| 1 | Admin CRUD for connector accounts (encrypted credentials, masked-edit pattern) | **Met** | F2 unit + browser tests; L11 HAT registered Discord bot via Studio |
| 2 | At least two connector implementations against single contract; at least one persistent connection | **PARTIAL — Discord half met; second connector UNMET** | F8 ships Discord (gateway WebSocket); F9 deferred past M10. Contract-validation empirical answer DEFERRED |
| 3 | Peer-to-agent-to-platform-reply roundtrip on same platform | **Met** | F8 L11 HAT exercised against real Discord bot, both Sonnet and Ollama models |
| 4 | Unknown-sender pairing/allowlist gating; approval state survives restart | **Met** | F6 unit + DB round-trip tests |
| 5 | Stable, reversible mapping between external conversation identity and chat session | **Met** | F3 session-key normalizer; restart-survival pinned by tests |
| 6 | Connector account → N agents via Studio; tool registry unchanged | **Met** | F4 attach UI + F7 multi-agent dispatcher; structurally validated by Fix #6 multi-agent pool tests |
| 7 | Per-connector-account credential override via resolver pattern | **Met** | F4 + F6 resolver; F8 L11 confirmed via attached Sonnet |
| 8 | Doctor-style probe in Admin matching M07 inspector shape | **Met (structural); HAT-validated UX** | F8 L7 5-check probe; L11 inspector UX patched inline |
| 9 | Persistent connections via per-(agent, account) lifecycle pool with idle-TTL | **PARTIAL — keying refactored mid-mission** | F1 pool shipped; F8 L11 Fix #6 wrapped pool keying for multi-agent on one gateway-protocol account |
| 10 | Failures isolated to connector layer don't kill chat session; degraded-status in Admin | **Met (structural); UX HAT-validated** | F3+F4+F6 graceful-failure tests; L11 HAT inspector rendering |
| 11 | Credentials never plaintext outside encryption boundary; `__MASKED__` sentinel preserved | **Met** | F1-F4 unit tests; L11 HAT BOT_TOKEN double-decrypt bug surfaced + fixed (post-hoc — repository layer is the contract) |
| 12 | Chat UI lists connector-bound sessions alongside Chat-UI-native; unified history visible | **Met** | F5 + browser tests |
| 13 | Cross-visibility context (operator console + platform channel feed same agent context) | **Met** | F5 visibility-tag tests |
| 14 | Platform-send tool auto-loaded when connector attached + tool enabled | **Met** | F4 + F8 L9 invariant tests |
| 15 | Tool-disabled-while-connector-attached: inbound received, no outbound; re-enable restores | **Met** | F4 e2e tests `test_e2e_disabled_state_inbound_received_no_outbound` |
| 16 | Tool can only target attached connector accounts + ACL-allowed channels | **Met** | F4 + F6 unit tests |
| 17 | Per-session lifecycle (continue vs fresh); platform reset command + operator action | **Met (structural)** | F3 lifecycle tests; HAT did not exercise the reset command in L11 |
| 18 | Multi-agent routing: layered scheme (default → peer command → permissions); decisions logged | **Met (structural); not HAT-exercised with real traffic** | F7 unit tests; L11 multi-agent routing got hung up on `#name` vs ID UX before real traffic |
| 19 | Platform-side command surface (`/agents`, `/talk_to`, `/whoami`, `/new`, `/reset`, `/help`) | **Met (structural)** | F7 unit + F8 L9 slash-command tests; L11 did not exhaustively exercise each command |
| 20 | Command surface as connector-agnostic primitive; plugin native commands extend additively | **Met** | F7 declared, F8 L1 wired consult, F8 L9 implemented for Discord |
| 21 | Per-layer automated coverage (persistence, contract, key-norm, pairing/allowlist, resolver, pool, doctor) | **Met (substrate); partial for Discord layer** | 2404 tests pass; auto-relay LLM-behavior coverage gap is unavoidable |
| 22 | Admin connector surface, Studio attach, doctor probe, in-Chat connector-session view meet M04/M06 design bar | **Mostly met (HAT-validated)** | L11 inspector UX patched inline; peer-name attribution gap (Bug C) DEFERRED to follow-on |
| 23 | Outbound rate limiting and backpressure for platform-send tool | **NOT MET** | L5 maps 429 to typed error; no live-load coverage. DEFERRED |
| 24 | Reply correspondence — edits and deletes | **Decision: do nothing** | Explicit "do nothing" via flight-log decision; no coverage. DEFERRED |
| 25 | Agent loop (`agent/core.py`, `factory.py`) NOT modified | **Met** | Byte-identical to F7 ship; verification step 11 in F8 spec |
| 26 | Second connector adds no files outside its own directory + registration site | **N/A** | Mission criterion premised on F9 landing; UNMET by deferral |
| 27 | Webhook-driven platforms explicitly out of scope | **Met (constraint preserved)** | F8 implementation uses persistent WebSocket only |

**Met (full)**: 16
**Met (partial / HAT-validated / structural-only)**: 7
**Not Met / Deferred**: 4 (#2 second-connector, #23 rate limiting, #26 contract-additive empirical proof, peer-name attribution within #22)

The mission is at roughly **77% (21/27) criteria-met-or-substantially-met**, with the 4 unmet/deferred criteria rolling into the follow-on mission's explicit scope.

---

## Flight Summary

| Flight | Status | Key Outcome |
|---|---|---|
| F1: Connector plugin contract + lifecycle foundation | completed | `ConnectorPlugin` Protocol, encryption-rotation-integrated `ConnectorAccountRepository`, lifecycle pool (worker-task-per-entry pattern), registry, no-op stub end-to-end |
| F2: Admin surface for connector accounts | completed | CRUD UI + doctor-probe surface; encrypted-credentials with `__MASKED__` sentinel; idle-timeout per-account |
| F3: Session model — schema migration, key normalization, two-visibility-layer storage | completed | v16 migration; `SessionKey` shape; `Message.visibility` field; inbound dispatcher prototype against stub |
| F4: Platform-send built-in tool + outbound routing | completed | `send_to_platform_channel` tool; system-prompt composition extension; outbound through stub; tool-disabled state pin |
| F5: Chat UI — unified history, visibility distinction, operator console | completed | Chat UI cross-source listing; visibility-tagged rendering; operator-typing path via shim (preserves "agent loop is not modified") |
| F6: Pairing, allowlists, per-agent ACLs | completed | DM-pairing flow; account-scope + per-agent-overlay allowlists with per-axis tri-state semantic (HAT-redesigned to "empty = unrestricted") |
| F7: Multi-agent routing + platform-side command surface | completed | 5-step routing engine; `CommandHandler` Protocol declared; 6 v1 commands; Studio routing-rules editor with drag-reorder + chip-list |
| F8: First real connector — Discord | completed | `discord.py 2.4.x` plugin; gateway client + intents + reconnect; HAT-validated end-to-end; 6 inline fixes shipped during L11 |
| ~~F9: Second connector (Slack default)~~ | **DEFERRED** | Operator decision after F8 HAT — depth exceeded scope |
| ~~F10: Hardening + observability~~ | **DEFERRED** | Cross-connector premise moot with F9 dropped; Discord-specific hardening rolls into follow-on mission |

### Flight Patterns

**What went smoothly**: F1, F2, F3 — these were close to one-shot. The substrate Protocols + DB schema + dispatcher prototype each landed in a single planning + execution pass with no scope-changing surprises. Per the F1+F3 debriefs, this was because each flight was *one architectural commitment* with a small surface area.

**What struggled**: F5 ("Chat UI" — paid 6+ HAT iterations rebalancing operator-broadcast vs platform-broadcast surfaces) and F6 ("allowlists" — paid 3 HAT iterations including a contract-flip from "empty = locked" to "empty = unrestricted"). Both flights' designs collided with operator UX intuition only at HAT; both made the conventions list: `hat-driven-contract-flip-migration-discipline` was codified in F8 L1 retroactively.

**F8 — the integration moment** — caught what unit tests couldn't but at the cost of 6 inline fixes during one HAT. The Architect's M10 debrief calls this out: "Phase 5b cycles got more effective on individual legs, less effective on cross-leg architectural drift."

---

## What Went Well

- **Substrate-first sequencing was the right architectural call.** F1-F7 established each abstraction in isolation; F8 composed them into a real connector with predicted shape. The cost was 7 flights of waiting before "Discord works"; the benefit is that F9-F10 (when they land in the follow-on mission) will have a substrate-validated foundation.

- **The Architect role + Phase 5b 2-cycle review caught real bugs.** Cycle 1 reversed the stub-in-production design in F8; cycle 1 reinstated the v19 migration commitment when the original spec dropped it. Per-leg defects (citation drift, missing tests, wrong selectors, malformed acceptance criteria) were caught consistently across all 8 flights.

- **Conventions accumulated organically across flights and got codified.** `optional-plugin-hook-via-getattr-sentinel` (F3+F6+F8 = n=3); `protocol-widening-for-required-capability` (F4); `per-axis-tri-state-override` (F6+F8 = n=2). The codification discipline produced reusable architectural vocabulary.

- **HAT-driven design refinement, when triggered, was decisive.** F6 redesigned the allowlist semantic mid-HAT (empty=locked → empty=unrestricted) and the operator approved within minutes. F8 spawned 6 inline fixes during L11, each diagnosed and shipped within hours. The methodology supports tight iteration.

- **F8 HAT empirically validated the substrate end-to-end.** The Discord bot is reachable from real Discord clients; messages flow through every layer (gateway → translate → dispatcher → ACL → routing → agent → auto-relay → outbound). 2404 tests pass. The substrate's claim that "future connectors are additive plugins against a stable SDK" survives — Discord landed with no F1-F7 source-code changes outside the carve-outs the flight specs anticipated.

- **Operator-driven scope reduction was healthy.** F9 + F10 deferral after F8 HAT was clear-headed, well-documented, and produced a clean follow-on mission framing rather than a mission failure narrative. The mission.md "Mission Scope Change" section is exemplary as a scope-change artifact.

---

## What Could Be Improved

### Process

- **Critical — Precedent-grep discipline missing in Architect reviews.** The F1 pool-keying decision was textually "mirror M07's MCP pool" and survived seven flights' design reviews before F8 L11 HAT exposed the gateway-protocol-vs-MCP premise mismatch. Same shape with the L3/L7 BOT_TOKEN double-decrypt: the spec said `encryptor.decrypt(account.secrets["X"])` but no reviewer was required to grep for existing call sites of the precedent. The fix is structural: **add to the Architect checklist a mandatory "enumerate existing call sites of any precedent invoked and confirm contract delivery."**

- **Critical — Cross-subsystem pattern-transfer without premise validation.** Every "mirror X" rationale that survived design review treated the precedent as self-justifying. The proper question is "the original design rests on premise P; does P hold here?" For pool keying: P = "per-agent credential substitution is meaningful." For MCP: true. For gateway connectors: false. Codify as `agents.md` convention `cross-subsystem-pattern-premise-revalidation`.

- **Critical — Prompt-discipline shipped as production contract.** F4's invariant "tool-mediated outbound is the only conduit" depended on LLM compliance with the system-prompt directive. Sonnet 4.7 ignored the directive at F8 HAT — twice, with the strengthened version. The decision-only path was insufficient as a contract. **Codify `prompt-discipline-needs-mechanical-fallback`:** any agent behavior the system depends on but the LLM controls requires either empirical HAT validation against the production model OR a mechanical dispatcher-side fallback.

- **Important — Mid-mission re-scoping checkpoints should be a standard artifact.** The operator's F9+F10 deferral after F8 HAT was the right call but happened ad-hoc. Future missions should plan an explicit checkpoint at "first real consumer flight + 1" to re-evaluate remaining scope. Add to `/mission` skill: missions with >2 substrate flights before any real-consumer flight must define an explicit mid-mission re-scoping point.

- **Important — Contract-reversal across flights needs a re-review trigger.** F8 L11 Fix #4 (auto-relay default-on) functionally reverses F4's "tool-mediated outbound is the only conduit" invariant. Operator approved, but the orchestrator did not emit a `[CONTRACT-REVERSAL]` signal that would trigger fresh design review. **Add to `/agentic-workflow`**: HAT-time fixes that reverse a prior-flight invariant trigger fresh design review before commit.

- **Important — Substrate flights need integration-reachability ACs.** F8 L4 explicitly deferred lifespan-time auto-acquire to L11 HAT; the entire L4 inbound code path was end-to-end unreachable in production until L11 Fix #3 wired the lifespan walk. Codify `lifespan-wiring-same-leg-as-installation`: event-handler installation and the lifespan call site that triggers it land in the same leg, or the leg's ACs include a runtime end-to-end test.

- **Minor — Mission criteria-vs-evidence map was built ad-hoc at debrief.** The F8 debrief constructed the criterion-by-criterion walk for the first time. Missions should carry a continuously-updated "criterion → evidence/test" map so debriefs don't reconstruct it from scratch.

### Technical

- **Critical — F1 pool keying needs proper refactor in follow-on mission.** Fix #6's sentinel-wrapper works but leaves the bare `pool_acquire(agent_name, account_id)` API as a footgun. The Discord-depth mission must introduce an account-keyed pool primitive at the connector layer; the per-agent-keyed pool stays as MCP-only territory.

- **Critical — Operator-editable connector system-prompt directive.** Three hard-coded constants in `agent/config.py:54-93`. Operator's L11 observation: "I need to be able to see and modify the prompt that gets included with the connector." Follow-on mission scope.

- **Critical — `peer_name` data-model thread-through (Bug C).** Six surfaces (`Message` dataclass + codec + `messages_to_ui_events` + `Agent.step` signature + live broadcast + Chat UI `addMsg`/`renderAttribution`) need coordinated lockstep changes. Multi-leg work; deferred to follow-on mission.

- **Important — Wire the F7 `CommandHandler` Protocol consult site.** F7 declared the Protocol at `base.py:377-419` but `_inbound.py` step 11 never consults it; F8 L1 was supposed to wire it. The audit during F8 L11 confirmed L1 shipped the consult — but the spec-vs-ship gap at F7 ship-time is the methodological lesson, not a current code defect.

- **Minor — Test throughput regression in F8.** 14.4 → 12.5 t/s, +34.45s wall-clock for +142 tests (3x marginal cost vs project average). Discord SDK fixtures + lifespan-warm tests likely dominant. Probe in routine-maintenance.

### Documentation

- **Important — Five new conventions to codify in `agents.md`** (F8 debrief + Architect addition):
  - `encryptor-parameter-receive-but-not-consume` (M10-specific shape; project-wide principle)
  - `cross-subsystem-pattern-premise-revalidation` (project-wide, highest leverage)
  - `prompt-discipline-needs-mechanical-fallback` (project-wide; will recur)
  - `mechanical-fallback-prompt-truth-pairing` (companion to above)
  - `lifespan-wiring-same-leg-as-installation` (project-wide)
  - **Architect addition**: `atomic-leg-pattern` (Pydantic field + migration + repository + ripple-sites in one leg; F4 L5 + F6 L1c are n=2)

- **Important — Project-conventions vs mission-conventions distinction.** The new conventions above are project-wide but emerged in M10. `agents.md` should distinguish "project conventions" (cross-mission) from "mission-specific conventions" (emerged-in-this-mission, may not generalize). Currently conflated.

---

## Lessons Learned

### Technical Lessons

1. **Substrate-first works architecturally but under-specifies abstractions.** F1-F7's substrate was structurally complete but had hidden assumptions (pool-keying premise, encryption-boundary contract, prompt-effectiveness-as-contract) that only surfaced under real-platform constraints. Future substrate flights should include "constraint validation against a thinnest-possible real consumer" as an explicit AC, not just "stub passes."

2. **Protocols carry contracts at two layers: signature and call-site.** The Protocol's method signature is the type-level contract; the call-site delivery (what the repository actually hands the plugin) is the runtime contract. Both must be specified in flight planning. Protocol-signature-only specs ship double-decrypt bugs.

3. **The "operator console + platform channel" two-visibility model is sound but missing peer attribution.** F5's data model survived eight flights of pressure; what's missing is content (peer_name) and a mechanism for the operator to redirect/intercept platform-bound messages (the operator-editable prompt directive).

4. **Auto-relay default-on with a mechanical fallback is the right shape for bot UX.** F4's "tool-mediated outbound is the only conduit" invariant was architecturally elegant but UX-hostile — operators expect bots to reply to peers automatically. The Fix #4 mechanical fallback respects operator intuition while preserving the tool's audit trail (tool path is still the conduit; dispatcher is just an additional caller).

5. **Per-axis tri-state allowlist generalizes.** F6 introduced the pattern (peers, channels); F8 extended cleanly to guilds+roles. The pattern is durable and should be the default for any future ACL design with platform-specific axes.

### Process Lessons

6. **Phase 5b 2-cycle design review catches local defects, not structural drift.** Both cycles consistently caught typos, citation drift, missing fixtures, malformed ACs. Both consistently missed cross-flight architectural assumptions inherited unexamined ("mirror M07"). The fix is not more cycles; it's checklist additions targeting category gaps (precedent-grep, premise validation, contract delivery).

7. **HAT iteration budget framing matters.** F8 planned "3-5 HAT iterations" and shipped 6 inline fixes across 6 distinct architectural surfaces. Future plans should distinguish "iterations of the same bug" from "fixes of distinct architectural defects" — the latter is a flight-design signal, not a HAT-process signal.

8. **Validate-by-replication missions have a fragility problem.** M10's "two-connector contract validation" criterion depended on the second instance landing. When F8's depth grew, F9 was the marginal flight that got cut, and the validation criterion went unanswered. Future replication missions should land the load-bearing replication leg FIRST or accept a stub-based proxy validation as the empirical answer.

9. **Mid-mission operator scope-down is healthy and should be expected.** The F9+F10 deferral was clear-headed, fast (<1 day), and produced a clean follow-on framing. Mission methodology should treat scope-change as an expected possibility, not an exceptional failure.

### Domain Lessons

10. **Gateway protocols are one-IDENTIFY-per-token by physical necessity.** Discord, Slack Socket Mode, and similar gateway-style protocols admit exactly one concurrent connection per credential. Pool designs that key per-agent are incompatible. Future connector additions must declare upfront which pool-keying axis applies.

11. **LLM directive compliance is not a production contract.** Models trained for politeness / safety / deference (Sonnet 4.7 is the case in point) will ignore directives like "MUST call tool X" if the surrounding context suggests deliberation is preferred. Production behavior must either (a) empirically validate against the production model AND pin via HAT criteria, or (b) ship a mechanical fallback.

12. **Discord-specific UX details matter operationally.** Channel IDs vs channel names; mention-resolution (`<@id>` vs `@displayname`); ephemeral vs visible slash-command responses; intent-coverage gating. The connector substrate is platform-agnostic but operator-facing UX is platform-specific. Future connector flights should plan a "platform-UX polish" leg explicitly.

---

## Methodology Feedback

### Flight Control Process Improvements

1. **Add 3 mandatory Architect-checklist items** for Phase 5b design review:
   - **Precedent-grep**: enumerate existing call sites of any precedent invoked and confirm contract delivery.
   - **Cross-subsystem premise validation**: when mirroring a pattern, explicit "original premise P; does P hold here?" paragraph.
   - **Protocol-signature-vs-actual-contract**: two-line contract-delivery paragraph for any new Protocol consumer.

2. **Add `[CONTRACT-REVERSAL]` orchestrator signal** to `/agentic-workflow`. HAT-time fixes that reverse a prior-flight invariant trigger fresh design review.

3. **Add mid-mission re-scoping checkpoint** as a standard `/mission` artifact. Missions with >2 substrate flights before any real-consumer flight must define an explicit "first real consumer + 1" re-evaluation point.

4. **Add `lifespan-wiring-same-leg-as-installation`** to `/leg` and `/flight` design guidance. Event-handler installation and the lifespan call site that fires it land in the same leg, or the leg's ACs include runtime end-to-end coverage.

5. **Add "criterion → evidence/test" map** as a mandatory mission artifact. Continuously updated across the mission. Debriefs read it; don't reconstruct it.

### Mission Shape Improvements

6. **For "validate-by-replication" missions**: land the load-bearing replication leg first, OR accept a stub-based proxy validation. The pattern of "build substrate, then replicate twice to validate" exposes the substrate to the worst version of "the second instance gets cut" — exactly what happened to M10.

7. **For substrate-heavy missions**: require an integration-reachability AC at each substrate flight ("a thinnest-possible real consumer can exercise this code path end-to-end"). Stub-based ACs are necessary but not sufficient.

### `agents.md` Codification

8. **Codify the 5 + 1 new conventions** (5 from F8 debrief + `atomic-leg-pattern` from Architect):
   - `encryptor-parameter-receive-but-not-consume`
   - `cross-subsystem-pattern-premise-revalidation`
   - `prompt-discipline-needs-mechanical-fallback`
   - `mechanical-fallback-prompt-truth-pairing`
   - `lifespan-wiring-same-leg-as-installation`
   - `atomic-leg-pattern`

9. **Distinguish project-wide vs mission-specific conventions** in `agents.md` structure. Currently conflated; future missions need clearer codification categories.

---

## Action Items

**Immediate (before follow-on Discord-depth mission planning)**:

- [ ] Codify the 6 new `agents.md` Project Conventions.
- [ ] Update Architect checklist with the 3 mandatory checks.
- [ ] Add `[CONTRACT-REVERSAL]` signal to `/agentic-workflow` skill.
- [ ] Add mid-mission re-scoping checkpoint to `/mission` skill template.
- [ ] Add "criterion → evidence/test" map requirement to mission artifact format.
- [ ] Run `/routine-maintenance` on the-one — 4 minor technical-debt items + test throughput regression probe.

**Near-term (in follow-on Discord-depth mission scope)**:

- [ ] Pool-keying proper refactor (account-keyed primitive at connector layer).
- [ ] `peer_name` data-model thread-through (Bug C, 6 surfaces).
- [ ] Operator-editable connector system-prompt directive (per-account override + default-visibility surface).
- [ ] Live-traffic multi-agent routing HAT against real Discord.
- [ ] Real-platform DM pairing HAT.
- [ ] Rate-limiting + backpressure live-load HAT (mission criterion #23).
- [ ] Audit-log inspector UI for `session_metadata["routing"]`.
- [ ] Discord channel-ID-vs-name UX cue in routing-rules editor.
- [ ] Plugin-handler-timeout, ephemeral slash-command responses, idle-eviction exemption for listener entries.

**Mission-shape (in the follow-on mission's planning)**:

- [ ] Second-connector flight (Slack? Matrix? Signal?) — land the load-bearing leg first or accept a proxy validation; resolves M10 criterion #2 retroactively.
- [ ] Cross-mission Architect-checklist effectiveness review after 3 follow-on flights run with the new conventions.

**Long-term (separate missions / continuous)**:

- [ ] Mission-criteria reporting dashboard or surface in Studio (visibility into which criteria are met/partial/unmet).
- [ ] Methodology audit: do the 5 new `agents.md` conventions actually prevent the recurrence of their target defects in subsequent flights? Re-evaluate after Discord-depth mission's debrief.
