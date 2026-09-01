# Flight Debrief: Channel Contract

**Date**: 2026-09-01
**Flight**: [Channel Contract](flight.md)
**Status**: landed
**Duration**: 2026-08-31 (single day, three legs + one behavior-test fix pass)
**Legs Completed**: 3 of 3

## Outcome Assessment

### Objectives Achieved
The platform-agnostic connector core is rebuilt on Flight 1's kept seams at 1,060 Python lines — an 88% reduction from the pre-reset 9,050 — and the whole contract was proven live: `stub-connector-round-trip` passed 7/7 against a real instance with a real model (run `2026-08-31-22-43-08`), witnessing masked credentials, one-time pairing, silence-by-default admission, session keying under `session_locks`, binding-derived send authorization, the operator's private console, and agent-initiated sends. Suite 3,669 green (+108 net, all additive); four browser lanes green; no dependency changes; agent loop and MCP drain block untouched and verified. Flight-end review: zero blocking issues, with the security pass (authorization construction-binding, Fernet/rotation, dual-gated seams, pairing atomicity) explicitly confirmed.

### Mission Criteria Advanced
- Criterion 5 (credentials encrypted/masked/rotation-enrolled) — met, with rotation now *restarting listeners* (a robustness the mission never asked for but needed).
- Criterion 6 (flat allowlist + pairing, silence for unknowns, no gate/ACL/queue) — met and live-verified.
- Criterion 7 (default agent + channel map, no routing engine) — met; the map is also a send boundary by construction.
- Criterion 4 (unified history, visibility distinction, operator messages never reach the platform) — retained AND improved (peer attribution and top-level peer-visible tool results were broken/imperceivable until this flight's behavior test caught them).
- Criterion 9 (size ceilings) — running totals 1,060/3,000 Python, ~675/1,000 JS.
- Criterion 11 (docs) — five docs rewritten, forbidden-term greps clean.

## What Went Well
- **The behavior test as flight acceptance gate, authored at flight-design time — validated decisively.** It caught three real defects (missing peer attribution in the live pipeline, peer-visible tool-results buried in a collapsed accordion, live-vs-reload marker inconsistency) that 3,665 passing unit tests and four green browser lanes structurally could not see, and forced the two fix passes that made the criterion true rather than nominally checked. Authoring the draft during flight design (not leg 3) also let leg 3 catch a *spec* defect (the operator-only suppression wording) against the real surface before it could produce a false failure.
- **Each review cycle caught a distinct class** — leg-1 review: the missing per-session lock + the authorization-matrix under-specification; leg-2 review: the rotation-strands-listeners bug (the flight's subtlest latent outage), the plugin-less doctor norm, and the stub-registration gap; flight-end: clean confirmation; behavior gate: the three perceptual defects. Unlike Flight 1's four-cycles-one-bug-class pattern, no miss repeated — the Flight 1 debrief's recon-step-zero fix demonstrably worked.
- **The Witnessed pattern earned its keep twice**: run 1's Validator overrode the Executor's DOM-visible claim with rendered-state evidence (the decisive accordion finding), and run 2's Executor caught the Orchestrator's own clobbered-precondition before any step ran.
- **Honest dispositions over green checkmarks**: the tool-call reliability gap was recorded as an unsolved model finding (raw n=1 fail / n=1 success preserved), not declared fixed by the nudge; the `enabled` gap became an unconditional-restart workaround with an explicit deferral, not a silent migration.
- **Line budgets held with room**: leg 1, the predicted trip point, landed at 959; the flight closed at 1,060/1,500. The stop-and-split ceiling again shaped behavior without firing.

## What Could Be Improved

### Process
- **DD-to-acceptance-criteria traceability for operator-facing affordances** (the flight's one recurring planning failure): both real gaps — no persisted `enabled` field (DD-2/DD-7/DD-9 assumed one), no Studio Tools-tab checkbox for the connector tools (DD-4's "operator toggles it") — were DD prose describing an affordance no leg's acceptance criteria enforced. Rule for future flights: every DD clause naming an operator-visible affordance maps to at least one leg AC line.
- **Seam risk-tiering had to be re-derived** (single→dual gate, caught at second-pass review) — the second flight in a row re-learning the squawk 0020/0021 seam-hygiene lesson; name the dual-gate pattern as a convention with risk tiers (inert-metadata vs live-loop-injecting) so it's pattern-matched, not re-argued.
- **Behavior-test precondition amendments worked but took three iterations** (no nudge → discipline nudge → mechanism-aware nudge). The final discipline — amend in place with recorded rationale, one sanctioned rerun, declared escalation fallback — is worth canonizing in the behavior-test AUTHORING guide as the standard "the precondition was wrong, not the system" path.

### Technical
- **Missing pre-fix coverage of persisted message *shape***: leg 1 tested session resolution and concurrency thoroughly but never asserted what `dispatch_inbound` persists for a peer message — the peer-attribution defect was foreseeable at unit level. The live-vs-reload marker inconsistency was likewise a testable parity property.
- Debt carried, all labeled: the source-textual pin test in `test_connector_send_tool.py` (layering-driven, narrow residual risk); the promoted-bubble check running on non-connector sessions (dead weight for `chat.js`'s next cleanup); squawk 0027's AsyncMock warnings now two debriefs old and still open.
- The promoted-bubble structural contract (direct child of `.messages`, not nested in a trace shell) is pinned only by one browser test + the behavior test's dump — add a cheap DOM-shape assertion before Flight 3 touches `chat.js` again.

### Documentation
- Two patterns deserve `agents.md` convention entries: the dual-gate seam pattern (with risk tiering) and the composition-disjoint post-step mutator pair (`_bind_peer_name` touches only USER; `tag_post_step_visibility` skips USER — non-conflicting by construction).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| `llm/base.py` pin via source inspection, not import | `llm/` importing `tools/` would invert layering for two literals | Yes — layering wins; textual pin is acceptable debt when documented |
| No persisted `enabled` field; PUT restarts unconditionally | DD prose assumed a field no leg built; migration out of leg scope | No — fix the root cause (DD-to-AC traceability); the workaround itself was sound |
| Eighth route (`GET /connectors/types`) + dual-gated stub startup hook | Leg-2 review: nothing registered the stub in a live process; "stub" creatability needed gating | Yes — plugin-type gating via a `/types` route is the template for dev-only platform types |
| Rotation restarts listeners + `_run` fresh-row re-fetch | Review caught the stale-snapshot stranding bug | Yes — standing checklist item: any flight combining credential-lifecycle work with long-lived connections gets a joint review pass |
| Behavior spec precondition amended live, twice, with recorded rationale + one sanctioned rerun | The reliability gap was nudge-shaped, not code-shaped | Yes — canonize the amendment discipline in AUTHORING.md |
| Tool-use-discipline nudge made mechanism-aware (search-first) | The loop's strict baseline defers all tools behind `search_tools`; the model didn't know | Yes — any live agent-behavior test on this codebase should document the discovery mechanism in its preconditions |

## Key Learnings
- **Unit/browser lanes prove mechanics; only a live two-agent run proves perception.** All three run-1 defects were in the gap between "the data is correct" and "a human can see it" — the exact category the Witnessed pattern's rendered-state precedence exists for.
- **The binding-direction flip moved authorization to call time** — simpler than ACL overlays, but it makes the send tool's `execute()` the entire enforcement surface; the construction-bound `agent_name` is the trust anchor and must stay server-derived.
- **Partial-field PUTs reset unset fields** — the project's own CLAUDE.md watch-out bit the Orchestrator's test setup; live config verification before agent-behavior runs is now demonstrated practice, not paranoia.
- **A model narrating a tool call is not a model calling a tool** — with search-deferred tools, small models follow the indirection unreliably (1 of 3 raw turns); prompt wording that names the *mechanism* (search first, then call) fixed the test, but the product question (mechanical fallback vs documented limitation) remains open and now blocks a third deferral.

## Recommendations
1. **Flight 3 design must resolve, not re-carry, the send-tool discoverability question** — config/registration-level direct visibility, or a documented small-model limitation in operator docs. A third consecutive "known issue" carry is a flag to the mission owner. Also design in the `enabled` field (Discord's gateway makes pause-without-delete operationally real) and the Tools-tab category.
2. **Adopt the DD-to-AC traceability rule** at flight design time (methodology change, mission-control side): every operator-visible affordance named in a DD gets a checkable leg acceptance criterion.
3. **Budget the remainders explicitly in Flight 3's spec**: 1,940 Python / ~325 JS for Discord + Telegram combined; the Discord estimate (700–1,100) alone consumes most of the Python remainder, and 325 JS for two platform forms is under half what the shared editor cost — rerun the stop-and-split math against actuals, not the mission's original estimates.
4. **Reuse the proven apparatus wholesale for the Discord live HAT**: dev-instance + credential/handoff conventions, the seven-checkpoint structure, and run 2's evidence discipline (raw POST bodies, structural DOM dumps, pre-interaction default-render captures) as house style.
5. **Before Flight 3 touches `chat.js`**: add the DOM-shape assertion for the promoted-bubble contract; fold the non-connector dead-weight check into that pass.

## Action Items
- [x] Logged as **squawk 0028**: Studio Tools-tab category + checkboxes for the two connector tools — defect, routine
- [x] Logged as **squawk 0029**: DOM-shape browser assertion pinning the promoted tool-result bubble's structural contract — servicing, routine
- [x] Logged as **squawk 0030**: suppress the last-4 mask tail for short secrets — defect, routine
- [x] Logged as **squawk 0031**: `agents.md` convention entries for the dual-gate seam pattern + the composition-disjoint post-step mutator pair — servicing, routine
- [ ] Carried to Flight 3 design (not squawks — need design): send-tool discoverability resolution; `enabled` field migration; budget re-math
- [ ] Mission-control methodology feedback (for `/mission-debrief`): DD-to-AC traceability rule; joint rotation/long-lived-connection review checklist item; behavior-test precondition-amendment discipline for AUTHORING.md
- [ ] Still open from Flight 1's debrief: squawk 0027 (AsyncMock warnings) — second debrief surfacing it unresolved
