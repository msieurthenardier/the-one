# Flight Debrief: First Real Connector — Discord

**Date**: 2026-05-20
**Flight**: [First Real Connector — Discord](flight.md)
**Status**: landed
**Duration**: 2026-05-20 (planning) — 2026-05-20 (landed; single-day execution under `/agentic-workflow`)
**Legs Completed**: 11 of 11

> **Operator framing — debrief invocation**: "we did not fully test all of the criteria and its clear we have gaps, this flight and mission put most of the pieces together but its far from shippable." This framing is integrated through Outcome Assessment + What Could Be Improved + Key Learnings below.

---

## Outcome Assessment

### Objectives Achieved

The flight landed a working Discord connector against the F1-F7 substrate. Concretely:
- A real Discord bot (gleepglorp) is reachable from a real Discord server.
- Operator registers the bot identity in Studio Admin with masked BOT_TOKEN; doctor probe surfaces 5 read-only platform checks (token, application, intents, gateway, allowlist).
- Inbound peer messages route through F7's dispatcher to the configured agent; the agent responds via auto-relay (Fix #4) so the response posts back to Discord automatically.
- Multi-agent attachment on a single Discord account shares one pool entry / one gateway connection (Fix #6).
- Six v1 commands register as Discord slash commands per-guild via the F7 CommandHandler Protocol.

But this is the **substrate-validated, not shippable, posture** — see "What Could Be Improved" for the explicit gaps.

### Mission Criteria Advanced

F8 was the critical-path flight for M10's "Discord lands as the first real connector" promise. Walking the 27 active mission criteria (#2's two-connector half explicitly unmet per the operator-approved M10 scope reduction):

**Unit-tested at landing (12 criteria)**: #1 (Admin CRUD), #4 (pairing/allowlist gating), #5 (session-key normalization), #6 (multi-agent attach), #7 (credential override resolver), #11 (no-plaintext-credentials), #13 (cross-visibility context), #14 (platform-send tool registry), #15 (disabled-tool inbound persistence), #16 (tool-target validation), #18 (multi-agent routing), #19 (peer command surface), #20 (command surface plugin extension), #21 (per-layer automated coverage — broadly), #25 (no agent-loop modifications).

**Integration-tested multi-layer (4 criteria)**: #3 (peer→bot→agent→reply roundtrip — unit + HAT), #9 (per-(agent,account) lifecycle pool — `_pool.py` tests + Fix #6 structural pin), #12 (Chat UI unified history — F5 + browser tests), #17 (session lifecycle continue/fresh — F3 timeout/reset tests).

**Only HAT-validated (4 criteria, no automated proof)**: #3 actual Discord roundtrip with real LLM in loop; #8 doctor probe rendering in Studio inspector; #10 connector-failure-isolation degraded-status UX in Admin; auto-relay default-on behavior end-to-end with both Anthropic and Ollama.

**Deferred / not covered (8 criteria + Bug C data-model gap)**:
- **#2 (second connector)** — explicit mission deferral.
- **#22 (peer-name attribution end-to-end in UI)** — Bug C deferred multi-leg follow-on; `Message` dataclass needs `peer_name` field.
- **#23 (rate limiting + backpressure)** — L5 maps 429 to typed error; no live-load coverage.
- **#24 (edit/delete semantics)** — "do nothing" decision; no coverage.
- **#26 (Chat UI session list cross-source)** — F5 surface ships; no automated cross-source listing test.
- **#27 (DM-pairing flow against real platform)** — F6 pairs against stub; Discord DM pairing not HAT-exercised.
- **Operator-editable system-prompt directive** — explicit follow-on flight scope.
- **#21 (multi-agent routing under real traffic)** — structurally validated by Fix #6 tests + HAT routing-rules dry-run; real-traffic multi-agent run did NOT complete (the rule got hung up on `#channel-name` vs channel-ID UX). Structural integrity proved; real-traffic empirical proof did not.

The gap surface is intentionally honest. The substrate is structurally complete; the integration is HAT-validated for the happy path; the breadth of mission criteria that depend on real-traffic exercise + operator-tooling polish is the work that the follow-on Discord-depth mission must do.

### Were All Checkpoints Met?

10 of 11 flight.md Checkpoints checked. The HAT line carries an explicit "substantially passed; connectivity + filters + multi-agent routing validated; deeper polish/UX rolled into follow-on mission per operator's call to scope down M10" annotation.

---

## What Went Well

- **Pre-execution Architect review caught real bugs.** Phase 5b cycle 1 reversed the stub-in-production design decision before it shipped (would have created a `'stub'`-in-CHECK-constraint inconsistency). Cycle 1 caught the v19 migration commitment that the original spec accidentally dropped. The two-cycle discipline produced measurable value.
- **Per-leg autonomous Developer execution scaled.** L1-L10 ran without operator intervention through the leg cycle. Implementation Developers caught and fixed several smaller AC issues during execution (e.g. `register_builtin_connectors` idempotency guard at L2). Per the agentic-workflow orchestrator's design, individual leg quality stayed high.
- **F1-F7 substrate held up against a real platform.** Every abstraction the substrate established (Protocol contracts, encrypted-secrets pipeline, lifecycle pool, dispatcher 12-step, ACL, routing engine, command surface) composed cleanly into F8 with the predicted shape. The mission's "substrate-first then real connector" sequencing was vindicated.
- **HAT caught what unit tests couldn't.** Six inline fixes — four of them ones automated tests would never have surfaced (BOT_TOKEN double-decrypt against real Fernet, doctor inspector UX, multi-agent against real Discord gateway, LLM-prompt-effectiveness with real Sonnet/Ollama). HAT earned its keep.
- **Mechanical fallback design (Fix #4) preserved operator velocity.** Once Sonnet was observed asking for permission instead of replying, the auto-relay mechanism gave the operator a working bot in 30 minutes rather than days of prompt iteration. The pattern (mechanical fallback to absorb LLM-discretion-failure) is reusable.
- **Operator scope-down decision was decisive and well-documented.** F9 + F10 deferred mid-flight with a clear methodology rationale captured in mission.md. The follow-on Discord-depth mission framing means the work doesn't fall through the cracks — it gets its own planning surface.

---

## What Could Be Improved

### Process

- **Critical — Precedent-grep discipline missing in design reviews.** The L3/L7 BOT_TOKEN double-decrypt bug survived BOTH Phase 5b cycles AND the flight-level Reviewer pass. The `_stub.py:165-198` and `mcp/_tool_provider.py:180` precedents were available and inconsistent with the L3/L7 spec — but no reviewer was required to grep for them. **Add to Architect checklist: before approving any decision that says "mirror M07" or invokes `encryptor.decrypt(...)` at a new call site, the planning artifact MUST enumerate existing call sites and confirm contract delivery.**

- **Critical — Cross-subsystem pattern-transfer without premise validation.** The F1 `(agent_name, account_id)` pool keying was textually framed as "mirror M07's MCP pool"; "mirror precedent" was treated as a sufficient rationale through F1 + F2-F7 + F8 design reviews. The underlying premise (per-agent credential substitution is meaningful for this resource) is true for MCP and **false for gateway-protocol connectors (one IDENTIFY per token)**. The defect needed three preconditions to surface (multi-agent + single-account + gateway-protocol); L11 HAT was the first context with all three. **Codify `cross-subsystem-pattern-premise-revalidation` as an `agents.md` convention.**

- **Critical — Prompt-effectiveness shipped as a production contract.** F4's "tool-mediated outbound is the only conduit" invariant depended on LLM compliance with the `_CONNECTOR_TOOL_ENABLED_DIRECTIVE`. Sonnet 4.7 ignored the directive at HAT — twice, with the strengthened Fix #1 version. The decision-only path was insufficient as a contract. **Codify `prompt-discipline-needs-mechanical-fallback` — any agent behavior the system depends on but the LLM controls requires either empirical HAT validation against the production model OR a mechanical dispatcher-side fallback.**

- **Critical — Contract-reversal shipped inline.** F8 Fix #4 (auto-relay default-on) functionally reverses F4's "tool-mediated is the only conduit" invariant. Operator approved, but the orchestrator did not emit a `[CONTRACT-REVERSAL]` signal that would trigger fresh design review. **Codify in `/agentic-workflow`: HAT-time fixes that reverse a prior-flight invariant trigger a contract-reversal re-review before commit.**

- **Important — Lifespan-wiring deferred to HAT.** L4 explicitly scoped out lifespan-time auto-acquire ("HAT integration territory"), with the consequence that the entire L4 inbound code path was end-to-end unreachable in production until L11 Fix #3. The flight could have caught this — L4 ACs included "on_message handler registered" but NOT "on_message handler can actually fire end-to-end in production." **Codify `lifespan-wiring-same-leg-as-installation` — when a leg installs an event handler inside `connect()`, the lifespan call site that triggers `connect()` lands in the SAME leg, or the leg's ACs include a runtime end-to-end test.**

- **Important — Six inline HAT fixes is a flight-design signal.** The HAT iteration budget framed "3-5 iterations" in the planning artifact — but those iterations are typically of the same bug, not six distinct architectural fixes. Future planning should distinguish "iterations of the same bug" from "fixes of distinct bugs," with >3 fixes-of-distinct-bugs being a debrief-worthy planning signal.

- **Important — Test throughput regressed 14.4 → 12.5 t/s.** +142 tests added +34.45s wall-clock (worst per-test marginal cost of M10). Discord SDK fixture + lifespan-warm tests likely dominant. Should be probed in routine-maintenance before the follow-on Discord-depth mission planning.

### Technical

- **Critical — F1 pool keying needs proper refactor in follow-on mission.** Fix #6's sentinel-wrapper (`connector_acquire(account_id)` → `acquire("__connector__", account_id)`) works but leaves the bare `pool_acquire(agent_name, account_id)` API as a footgun for future connector authors. The proper fix is to introduce an account-keyed pool primitive at the connector layer; the per-agent-keyed pool stays as MCP-only territory. Discord-depth mission scope.

- **Critical — Prompt directives are hard-coded in source.** Operator's L11 observation: "I need to be able to see and modify the prompt that gets included with the connector." Three module-level constants in `agent/config.py:54-93`. Discord-depth mission must ship operator-editable per-account directive with default-visibility surface.

- **Important — `peer_name` data-model gap (Bug C).** Six surfaces (`Message` dataclass + codec + `messages_to_ui_events` + `Agent.step` signature + live broadcast + Chat UI `addMsg`/`renderAttribution`) need coordinated lockstep changes for peer attribution to flow through to the Chat UI. Multi-leg work; deferred.

- **Important — `DiscordClient.__init__` carries `account_id`** purely to compose typed error envelopes (L5 Deviation #1). Cleaner shape: lift the F1 `ConnectorConfigError(account_id, ...)` constructor requirement to optional, OR carry account context as a structured field on the client. Minor refactor in routine-maintenance.

- **Minor — Dead `try/except Exception: raise` wrapper at `_discord.py:1093-1094`** (flight-level Reviewer flagged; deferred to debrief). Cosmetic cleanup in routine-maintenance.

- **Minor — Bare `pool_acquire` import in `_inbound.py`** (kept for future test monkeypatch). Either document the rationale or remove. Routine-maintenance.

### Documentation

- **Important — `agents.md` needs the new conventions codified.** F8 introduced 4 patterns worth promoting to named conventions (see "Patterns to Codify" below). They live in the F8 flight log today; should land in `agents.md` Project Conventions section.

- **Important — Mission-level criteria-vs-evidence map missing.** This debrief did the walk for the first time. The mission could carry a continuously-updated "criterion → evidence/test" map so future debriefs don't reconstruct it from scratch.

- **Minor — Studio Routing Rules editor lacks Discord-channel-ID-vs-name UX cue.** HAT surfaced: operator typed `#channel-name`, got "No agents available for this conversation." Helper text or a "Get Discord channel ID" doc link would have prevented the misfire. UX polish for the follow-on mission.

---

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| L1 `_VALID_ROUTING_SCOPES` → `VALID_ROUTING_SCOPES` rename (vs adding `__all__`) | `db/models.py` has no `__all__`; rename is smaller blast radius | Yes — "prefer rename over retroactive `__all__`" heuristic |
| L2 `'stub'` in `CONNECTOR_TYPES` + v19 CHECK (operator decision) | Mirrors M07 `'mock'`-in-`PROVIDER_TYPES` precedent; avoids 69 test-site refactor | Yes — codified as M07-precedent application |
| L3 module-level `discord` import (vs function-local) | SDK is pinned; import-time cycle risk is moot | Yes |
| L4 deferred listener-startup wiring to L11 | L4 scope-creep avoidance | **NO** — leg-wiring-needs-its-own-leg-not-HAT pattern; CODIFY THE OPPOSITE |
| L5 `DiscordClient.__init__(account_id)` parameter | F1 typed errors require account_id | No — refactor in routine-maintenance |
| L7 `SimpleNamespace` in 2 doctor tests | Pre-L8 validator rejected `allowlist.guilds`; ducktype the account interface | No — cleanup once L8 lands (now done; remove in routine-maintenance) |
| L8 4-axis validator made `guilds` + `roles` OPTIONAL (vs all required) | Back-compat with existing 2-axis rows | Yes — per-axis-tri-state-override convention |
| L11 HAT Fix #1 BOT_TOKEN double-decrypt | Repository decrypts whole secrets blob at row-load | Yes — codify `encryptor-parameter-receive-but-not-consume` convention |
| L11 HAT Fix #4 auto-relay default-on | LLM-prompt-effectiveness insufficient as production contract | Yes — codify `prompt-discipline-needs-mechanical-fallback` |
| L11 HAT Fix #6 sentinel pool keying | Multi-agent on one gateway-protocol account requires one IDENTIFY per token | Yes — codify `cross-subsystem-pattern-premise-revalidation` |
| L11 HAT Fix #5 auto-relay-aware directive | Fix #4's mechanical change required prompt-truth audit | Yes — codify `mechanical-fallback-prompt-truth-pairing` |

---

## Key Learnings

1. **"It's working" ≠ "it's shippable."** The operator's debrief framing captures this exactly. F8 proves the integration works at the substrate + happy-path level; it does not prove the criteria-by-criteria mission promise. Future debriefs should explicitly distinguish "structural integrity" from "mission-criteria coverage" — the two are not the same property.

2. **HAT is a real testing discipline, not just an acceptance ritual.** Six inline fixes across six distinct architectural surfaces demonstrate that HAT is the only test cycle that exercises (a) real platform protocols, (b) real production LLM behavior, (c) real operator-side UX, and (d) real lifecycle wiring. The implication: HAT cycles need explicit AC coverage, not "iterate until it feels good."

3. **Pattern-transfer across subsystems requires premise re-validation.** F1's pool keying inherited from M07 is the canonical case. The cost of NOT re-validating is high — a structural defect that survives every subsequent review and only surfaces under specific empirical conditions. Add to `agents.md` and to Architect checklists.

4. **Prompt directives shipped as production contracts will fail.** Sonnet 4.7 ignored explicit "MUST call tool X" directives twice. Production behavior cannot depend on LLM compliance with prompt-level rules — either empirically validate against the production model OR design a mechanical fallback.

5. **The mission shape for "validate by replication" missions needs revision.** M10's "two connectors prove the contract is additive" criterion went unmet because the first connector consumed all of the substrate-validation appetite. Future replication missions should either land the second instance FIRST (load-bearing-leg-first) or accept a stub-based proxy validation as the empirical answer.

6. **Operator-driven scope reduction is healthy and should be expected.** Mid-mission scope changes are a positive signal that the methodology is producing visible learning, not a failure of planning. The mission.md "Mission Scope Change" section is the correct artifact; future missions should plan for the possibility of mid-flight scope re-evaluation rather than treat it as exceptional.

7. **The substrate paid off.** F1-F7's substrate-first sequencing was vindicated by F8 — every abstraction (Protocol contracts, encryption pipeline, pool, dispatcher, ACL, routing engine, command surface) composed into F8 with the predicted shape. The cost of substrate-first is a long delay before "see a real connector working;" the benefit is that the real connector is contained, additive, and HAT-validates the substrate too.

---

## Recommendations

1. **Codify five `agents.md` Project Conventions** (severity: Critical):
   - `encryptor-parameter-receive-but-not-consume` — plugins receive `encryptor` for Protocol compliance but read `account.secrets["X"]` directly.
   - `cross-subsystem-pattern-premise-revalidation` — mirroring a pattern from subsystem A to B requires a premise paragraph identifying the constraints each subsystem assumes.
   - `prompt-discipline-needs-mechanical-fallback` — agent behaviors the system depends on but the LLM controls require empirical-HAT-against-production OR mechanical fallback.
   - `mechanical-fallback-prompt-truth-pairing` — default-on mechanical outbound changes require a same-fix audit of every prompt-level claim.
   - `lifespan-wiring-same-leg-as-installation` — event handler installation and the lifespan call site that fires it land in the same leg.

2. **Extend the Architect checklist** for Phase 5b design review with three new mandatory items (severity: Critical):
   - **Precedent-grep**: planning artifact enumerates existing call sites of any precedent invoked.
   - **Protocol-signature-vs-actual-contract**: for any new Protocol consumer, two-line contract-delivery paragraph documenting what the repository layer delivers at the call site.
   - **Cross-subsystem premise validation**: when mirroring a pattern, explicit "the original design rests on premise P; does P hold here?" paragraph.

3. **Add `[CONTRACT-REVERSAL]` orchestrator signal** (severity: Important). HAT-time fixes that reverse a prior-flight invariant trigger a fresh design-review pass before commit. Update `/agentic-workflow` skill documentation.

4. **Plan the follow-on Discord-depth mission with the explicit gap list** (severity: Critical for project shippability). Use this debrief's "Deferred / not covered" criteria + "Patterns worth codifying" + the F8-flagged F10 carry-forwards as the explicit scope:
   - Operator-editable system-prompt directive (per-account override + default-visibility surface)
   - `peer_name` data-model thread-through (Bug C — 6 surfaces)
   - Audit-log inspector UI in Chat UI / Studio
   - Pool-keying proper refactor (account-keyed primitive at connector layer)
   - Live-traffic multi-agent routing HAT
   - Real-platform DM pairing HAT
   - Rate-limiting + backpressure under live load
   - Edit/delete reply correspondence
   - Discord channel-ID-vs-name UX cue in routing-rules editor
   - Plugin-handler-timeout
   - Idle-eviction exemption for listener entries
   - Ephemeral slash-command responses

5. **Run `/routine-maintenance` before the follow-on mission planning** (severity: Important). Address the 4 minor technical-debt items (dead `try/except`, bare `pool_acquire` import, `DiscordClient.__init__(account_id)` refactor, `SimpleNamespace` doctor-test cleanup) + investigate test throughput regression before adding more code.

---

## Action Items

**Immediate (before next mission planning)**:

- [ ] Codify the 5 new `agents.md` conventions from Recommendation #1.
- [ ] Update Architect checklist with the 3 mandatory checks from Recommendation #2.
- [ ] Add `[CONTRACT-REVERSAL]` signal to `/agentic-workflow` skill.
- [ ] Run `/mission-debrief` on M10 — capture the methodology insight on "validate-by-replication" missions and the mid-mission scope-reduction discipline.
- [ ] Run `/routine-maintenance` on the-one — address the 4 minor technical-debt items + probe the test throughput regression.

**Near-term (in follow-on Discord-depth mission scope)**:

- [ ] Operator-editable connector system-prompt directive surface.
- [ ] `peer_name` data-model thread-through (Bug C — 6 surfaces).
- [ ] Pool-keying proper refactor (account-keyed primitive).
- [ ] Live-traffic multi-agent routing HAT against real Discord.
- [ ] Real-platform DM pairing HAT.
- [ ] Rate-limiting + backpressure live-load HAT.
- [ ] Discord channel-ID-vs-name UX cue in Studio routing-rules editor.
- [ ] Audit-log inspector UI for `session_metadata["routing"]`.

**Long-term (separate mission / routine maintenance)**:

- [ ] `DiscordClient.__init__(account_id)` refactor (lift F1 typed-error account_id requirement).
- [ ] Cross-mission Architect-checklist effectiveness review after 3 follow-on flights run with the new conventions.
- [ ] Test throughput baseline + regression detection in CI.
