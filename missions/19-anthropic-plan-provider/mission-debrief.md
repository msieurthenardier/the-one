# Mission Debrief: Anthropic Individual Plan Provider

**Date**: 2026-07-31
**Mission**: [Anthropic Individual Plan Provider](mission.md)
**Status**: completed
**Duration**: 2026-07-28 – 2026-07-31
**Flights Completed**: 1 of 1

## Outcome Assessment

### Success Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| Operator creates a plan provider and signs in with an Anthropic account; no API key ever entered | Met | `anthropic-plan-signin` PASS 6/6 live with the operator's real Pro/Max account; first real OAuth exchange succeeded on the first attempt |
| Agent chat parity — streaming, tool use, extended thinking | **Met at Haiku scope** (operator disposition) | `anthropic-plan-chat-parity` PASS 5/5 on `claude-haiku-4-5` (plain turn, streaming, `python_exec` tool loop, restart persistence). Extended thinking not exercised live: Sonnet/Opus are hard-blocked by Anthropic's extra-usage entitlement gate, and Haiku has no adaptive thinking. Operator accepted explicitly; a runnable `extended-thinking-tool-turn` plan variant is parked. |
| Credentials survive restart; encrypted at rest; never unmasked in responses/logs | Met | Restart step of the parity test; repository ciphertext-at-rest test (raw column contains no token substring); API returns `oauth_active` only — the whole `secrets` surface is stripped, not masked |
| Expired short-lived credentials renew automatically | Met | Credential-source unit tests against a mocked token endpoint (proactive 120s margin, single-flight, rotation-safe merge write-back) |
| Terminal renewal failure → clear re-authenticate affordance + actionable agent error | Met | Typed `ReauthRequiredError` path; `/test` returns `status: "reauth_required"`; browser test drives the affordance via a route-stubbed response |
| Multiple plan providers coexist, independently bound | Met | Two-config independence integration test (distinct sources, independent locks, no cross-writes) |
| Connection test and model listing work, consistent with other provider types | Met | `/test` verified live at HAT; `/models` live-with-static-fallback, verified live and by unit tests |

### Overall Outcome

The mission delivered its stated outcome — agents can authenticate against and run on an Anthropic individual plan — but the **premise behind the outcome turned out to be only partly true**, and that is the mission's single most important finding. Anthropic's current policy routes third-party application inference to an account's *extra usage* balance rather than the plan's included window. Sign-in, connection test, and model listing all succeed on any Pro/Max account; agent chat only works if the account has an active extra-usage entitlement, otherwise Sonnet/Opus return a bare, unactionable `429 'Error'` while Haiku passes.

So the honest framing of value delivered: **the capability is complete and correct; the economics are not what the mission assumed.** The operator got real working value (Haiku-class agents on the plan, and the full path ready for the rest the moment entitlement exists), and the project gained a diagnosed, documented constraint that would otherwise have surfaced as a confusing production mystery. No code change could have avoided the constraint — it is account-side.

The outcome was still the right goal by the end. Nothing about the design would have been decided differently in light of the discovery (per both the flight-level and mission-level architect reviews); what the discovery changes is the *product* conversation, which now belongs to a future mission.

## Flight Summary

| Flight | Status | Key Outcome |
|--------|--------|-------------|
| 01 — Anthropic Plan Provider End-to-End | completed | PKCE code-paste OAuth, migration v33 encrypted secrets + fourth rotation surface, self-resolving single-flight credential source, `AnthropicPlanProvider` on two new base-class seams, `/test` + `/models`, full Administration sign-in UX (amended at HAT), 4 legs, PR #164 |

Single-flight missions are legitimate when the work shares one risk profile, and this one did: every design decision (auth flow, storage, refresh, provider mechanics, UI) belonged to a single entangled cluster. Splitting it would have created review gates without decision boundaries. The pre-declared split point (credential acquisition vs. provider+UI) was never needed.

## What Went Well

1. **The empirical-premise discipline.** The mission rested on two unverified claims — that Anthropic's fixed public OAuth client would accept our authorize-URL shape, and that the SDK reads `auth_token` per request. Both were treated as premises to verify rather than facts to assume: the first became a hard-stop spike at the top of Leg 1 (passed, via a browser-apparatus fallback when a Cloudflare challenge made the raw HTTP probe inconclusive), the second was verified against SDK source at design review and pinned by a test that will fail loudly on a future SDK bump. Neither bit us — which is the point.
2. **Design reviews that changed the plan.** Every leg came back "approve with changes," and the changes were substantive, not cosmetic: a leg boundary that could not have landed green (module-load asserts), a second provider-construction site that would have failed *silently* (`connectors/_inference.py`), a "system browser" premise with no implementation path, a browser test that was physically impossible as specified, and the missing key-rotation surface that would have bricked stored tokens on the next rotation. Each was caught before implementation, at review cost rather than rework cost.
3. **HAT earned its keep twice.** Both findings that mattered most were invisible to autonomous verification: the entitlement gate (diagnosed differentially — same plan works in this Claude Code session, `/test` passes, Sonnet 429s, Haiku works — then confirmed against public issue reports) and the save-before-sign-in awkwardness the operator hit within minutes of real use. Both were resolved same-session; the second shipped as an inline fix with the full browser suite green.

## What Could Be Improved

1. **Acceptance plans need a disposition path for out-of-our-control blockers.** The flight's verification section assumed "a real Pro/Max account" was a sufficient precondition for extended-thinking parity. When entitlement turned out to gate it, the Flight Director made a reasonable ad hoc call (accept Haiku scope, record a known issue) — but ad hoc, because no contingency existed. Future flights whose criteria depend on external account state, quota, or third-party policy should pre-declare what happens if that state is unavailable.
2. **Agent operational discipline cost real wall-clock.** Three separate Developer spawns stalled by backgrounding a test suite and waiting on a monitor that never re-invokes them; each needed manual resumption. Separately, crew relay messages truncated repeatedly during behavior-test runs, requiring re-emission and a two-items-per-response cap. Neither affected correctness; both are avoidable with prompt-level rules.
3. **Self-reported metrics should be measured, not derived.** Leg 2's test-count arithmetic (`+77 → 4148`) was wrong, which set Leg 3 an unmeetable acceptance bar. It was caught and fully reconciled test-by-test in the flight log rather than waived — good behavior — but direct measurement (`pytest --collect-only` diff) would have avoided the cycle entirely.

## Lessons Learned

**Technical**
- Third-party plan OAuth authenticates against the plan but bills against extra usage. The diagnostic signature is now documented: sign-in/test/listing succeed, Haiku chats fine, Sonnet/Opus return a bare `429 'Error'` with no `retry-after`.
- Extracting a base-class seam to fit a subclass is fine at one subclass; `AnthropicProvider` now carries `_build_client`/`_before_request` whose only caller is the plan variant, and the seam's shape (sync build + async no-op pre-hook) may not generalize past "swap the auth mechanism."
- The credential-source registry generalizes to any OAuth-backed provider *except* for one hardcoded call to `anthropic_oauth.refresh_token()`. When a second OAuth provider lands, inject that call rather than copying the class.
- Two PKCE implementations now coexist (MCP's discovery/DCR stack; this mission's fixed-client single file). The split was correctly argued, but the generic primitives — verifier, S256 challenge, state — are duplicated and should be shared the next time either stack is touched for security reasons.
- Code-paste consent is a template for *fixed-public-client* consumer OAuth only. Where an operator can register their own OAuth app, the existing MCP loopback machinery is the right precedent; don't reach for code-paste out of precedent momentum.

**Process**
- Precedent-citing UX decisions deserve a "does this feel right" check, not only a technical-consistency check. DD-7's save gate was copied from the MCP editor's constraint and was technically correct; it took a live human thirty seconds to find it annoying.
- The Witnessed pattern behaved exactly as designed under pressure: the Validator refused to pass an armed-state checkpoint on DOM-only evidence, and the resulting hunt for real rendered evidence produced a reusable apparatus technique (performance-trace filmstrips for sub-round-trip UI states) that now applies to any timing-sensitive behavior test in this project.
- "Third caller triggers the lift" worked cleanly as a refactoring heuristic (`PROVIDER_TYPE_MAP`) and is worth standing status.

**Domain**
- Provider-type extension in this codebase is a 7-layer checklist and the checklist is accurate — this mission exercised every layer without bending it. The centralization touches made it slightly lighter, not heavier.

## Methodology Feedback

- **The risk-tiered leg design review is the highest-value gate in the workflow.** All three legs tiered HIGH; all three reviews found substantive issues. The "when in doubt, tier high" instruction was followed and repaid.
- **Batched flight-end review suited this flight** — three legs building one coherent surface, reviewed once against the combined diff, zero rework. Per-leg review would have added ceremony without new signal.
- **Interactive HAT legs are correctly excluded from autonomous execution.** Everything valuable in the HAT required a human: real credentials, real consent, real judgment about what feels awkward.
- **Recommended skill changes** (mission-control side): mandate foreground suite runs in `leg-execution.md` crew prompts (no backgrounding, no monitors, explicit timeouts); promote the filmstrip technique into `behavior-test/AUTHORING.md` as the standard method for sub-round-trip transient states; add a two-items-per-response cap guidance for multi-checkpoint crew relays.

## Action Items

- [x] **Product decision, extra-usage entitlement gate** — **adjudicated by the operator 2026-07-31: no action. The bare 429 is acceptable as-is.** Neither the message-mapping fix nor proactive entitlement surfacing will be pursued; the constraint stays documented as a mission known issue for diagnosis purposes. Re-open only if the entitlement gate starts affecting operators other than the device owner.
- [ ] Bundle the create-mode double-click guard (+ test) into the next `provider-editor.js` flight.
- [ ] Run the `extended-thinking-tool-turn` plan variant once the account has extra-usage entitlement; update the mission known issue. Add as a `routine-maintenance` checklist line so it doesn't age silently.
- [ ] Promote two conventions into `the_one/agents.md`: "third caller triggers the lift," and "OAuth stack choice depends on fixed-vs-registrable client."
- [ ] Mission-control skill updates: foreground-suite mandate; filmstrip technique into AUTHORING.md; direct test-count measurement in leg self-reports.
- [ ] Watch items for the next maintenance cycle: unit-suite wall-clock (433s measured vs 296–392s historical band — re-measure on an unloaded host); model-catalog pruning (2024-dated IDs still in the Studio picker's static fallback).
- [ ] Trigger-based, not scheduled: extract shared PKCE primitives when either OAuth stack is next touched for security; extract a shared secrets-column helper if a 5th secrets-bearing table appears; parameterize the credential source's refresh call when a 2nd OAuth-backed provider lands.
