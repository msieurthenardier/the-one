# Flight Debrief: Anthropic Plan Provider End-to-End

**Date**: 2026-07-31
**Flight**: [Anthropic Plan Provider End-to-End](flight.md)
**Status**: landed
**Duration**: 2026-07-28 – 2026-07-31
**Legs Completed**: 4 of 4

## Outcome Assessment

### Objectives Achieved

The `anthropic-plan` provider type shipped end-to-end and was verified live with the operator's real Pro/Max account: hand-rolled PKCE code-paste OAuth (spike-verified, first real exchange succeeded on the first attempt), Fernet-encrypted token storage on a new `llm_providers.secrets` column (migration v33, fourth key-rotation surface), a self-resolving single-flight credential source with rotation-safe refresh, an `AnthropicPlanProvider` subclass riding two new behavior-preserving seams (`_build_client`, `_before_request`), `/test` + `/models` support with static-catalog fallback, and a complete Administration sign-in UX (amended at HAT to auto-save-then-start per operator feedback). Delivered via 3 autonomous legs + 1 interactive HAT leg, one batched flight-end review, PR #164.

### Mission Criteria Advanced

All seven — verified by two new live behavior tests (`anthropic-plan-signin` 6/6; `anthropic-plan-chat-parity` 5/5 on claude-haiku-4-5), unit/browser suites (4133/0, 586/0), and two cite-vs-rerun spec re-runs (`save-preserves-config` 4/4, `system-provider-config` 20/20 both themes). **Criterion 2 (chat parity) closed at Haiku scope by explicit operator disposition**: extended thinking could not be exercised live because Anthropic routes third-party plan inference to an "extra usage" balance — without that entitlement, Sonnet/Opus hard-429 (bare `'Error'`, no retry-after) while Haiku passes. Recorded as a mission known issue (ref anthropics/claude-code#45326); the plan-provider variant of `extended-thinking-tool-turn` exists and is runnable whenever the account gains the entitlement.

## What Went Well

- **The spike-first hard stop earned its place**: the flight's central bet (code-paste PKCE against Anthropic's fixed public client) rested on unverified public-knowledge assumptions; the gated spike verified them before any migration or contract work, and every assumption held — the divert path was structured to fire but never needed.
- **The indivisible type-registration atom call was exactly right**: bundling tuple/Literal/migration/factory-map/registry-loader/consistency-test matched the real coupling (module-load asserts); no leg boundary had to be redrawn.
- **Design reviews were unusually high-yield**: every leg went "approve with changes, re-review skipped — direct adoption." The reviews caught, pre-implementation: the leg-1/leg-2 boundary that couldn't land green, a silently-failing second construction site (`connectors/_inference.py`), a "system browser" premise with no implementation path, an infeasible browser-test design (seeded revoked state can't produce `reauth_required` without hitting the real token endpoint), the missing key-rotation surface (which would have bricked stored tokens on the next rotation), and the `/test` contract break a 4xx would have caused. The in-place `client.auth_token` mutation premise was SDK-source-verified at review and pinned by a forward-defensive test.
- **Deviation discipline held**: both deviations (`_build_client` seam; pre-existing browser-test fix) were recorded with rationale rather than slipped in; the `PROVIDER_TYPE_MAP` lift was taken exactly when the third caller materialized, closing a documented layering smell.
- **HAT found what only a live human + live account could**: the extra-usage entitlement gate (differential diagnosis: same plan works in Claude Code, tiny `/test` calls pass, Sonnet chat 429s, Haiku works — confirmed against public issue reports), and the save-gate UX awkwardness — fixed inline same-day with the suite green.
- **Test rigor beyond shape-checking**: 6-caller single-flight concurrency assertions, re-read-inside-lock adoption tests, raw-column ciphertext assertions, and real seeded-encrypted-secrets browser fixtures exercising `oauth_active` derivation end-to-end.
- **The filmstrip apparatus technique** (performance-trace frames for sub-3s transient UI states) rescued the armed-delete checkpoint that discrete screenshot round-trips lost three times — proven in both themes and codified on the spec.

## What Could Be Improved

### Process
- **Developer agents repeatedly stalled by backgrounding test suites** and waiting on monitors that never re-invoke them — three separate spawns (Leg 3, HAT fix, debrief interview) required manual resumption. Crew spawn prompts (and `leg-execution.md`) should mandate foreground suite runs with explicit timeouts, no monitors, no ending the turn while waiting.
- **Test-count self-reports should be counted, not derived**: Leg 2's "+77 → 4148" back-derivation was wrong (actual 4130), inflating Leg 3's AC to an unmeetable bar; fully reconciled in the log, but a `pytest --collect-only` diff would have avoided the cycle.
- **Agent-message relay truncation** repeatedly dropped earlier items from multi-part crew responses during the behavior-test runs; a 2-items-per-response cap worked as mitigation and should be the default for multi-checkpoint crews.

### Technical
- **Create-mode double-click race** (new, minor): the sign-in button's click handler has no in-flight `disabled` guard (`provider-editor.js` ~:466-473); a fast double-click can fire two provider creates. The manual Save button shares the gap (pre-existing). Untested. Cheap fix.
- **Bare-429 operator experience** (deferred by operator choice): without extra-usage entitlement, a connected plan provider passes `/test` and lists models but fails chat with a raw, unactionable error — a confusing "connected but broken" state. Candidate small flight: map the bare 429 to an actionable message; consider surfacing entitlement proactively in the connected-state UI.
- **Unit-suite wall-clock watch item**: debrief re-run measured 433s vs the historical 296–392s band (leg-level runs measured ~350-354s); most likely host-load noise on shared WSL2, but re-measure clean at the next maintenance cycle before concluding.
- **Restart-between-start-and-code** loses the in-process pending verifier map (degrades gracefully to 409, but the leg-spec wording "pending window survives server-side" is only true within one process lifetime — minor doc/test mismatch).

### Documentation
- None missing — CLAUDE.md, testid registry, and `agents.md` checklist all updated in step. The filmstrip technique note currently lives on one spec; see recommendations.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| `_build_client()` seam extracted in `AnthropicProvider` (vs assumed existing seam) | No client-construction seam existed; extraction was behavior-preserving and enables subclass auth swap without `__init__` duplication | Yes — with `_before_request`, this seam pair is the template for future providers needing pre-request hooks |
| DD-7 save-gated sign-in → auto-save-then-start | Operator HAT feedback: manual save-first felt awkward; backend contract unchanged | Yes — and the meta-lesson: precedent-cited UX gates deserve a "does this feel right" check at design review, not just technical-consistency review |
| chrome-devtools used for the two spec re-runs despite the goldfinch preference | Specs document goldfinch wedges on those flows and lacks `ignoreCache` reload | Yes — spec-documented apparatus constraints override general preference; record the exception |
| `PROVIDER_TYPE_MAP` lifted into `registry.py` (optional variation, taken) | Third caller materialized (credential source) — the code's own forward-note trigger | Yes — "third caller triggers the lift" is a good standing heuristic |
| Pre-existing `test_flow_chat_peer_attribution.py` fix in passing | Failed identically at pristine main; test-only, behavior-accepting | No — one-off cleanup |

## Key Learnings

1. **Third-party plan OAuth ≠ plan-window usage.** Authentication rides the plan; inference bills to the account's extra-usage balance under current Anthropic policy. Any future work assuming "plan = free capacity for agents" must account for the entitlement gate; the differential symptom (Haiku passes, Sonnet/Opus bare-429) is now documented for fast diagnosis.
2. **Empirical premises deserve spikes and pins.** The two premises that could have sunk the flight (authorize-endpoint parameter acceptance; SDK per-request `auth_token` reads) were both verified before dependence and the SDK one is pinned by a test that will fail loudly on an SDK upgrade.
3. **Live HAT verification catches what autonomous legs cannot** — both findings that mattered most (entitlement gate, save-gate UX) were only observable with a real human, real account, and real consent flow.
4. **Rendered-state evidence discipline works**: the Validator's refusal to pass the armed-state checkpoint on DOM-only evidence (later satisfied via the filmstrip technique) is the Witnessed pattern functioning as designed — and produced a reusable apparatus technique in the process.

## Recommendations

1. **Author a small follow-up flight for the 429/entitlement UX**: map bare plan-provider 429s to an actionable message ("third-party usage bills to extra usage — check claude.ai/settings/usage") and consider a proactive entitlement indicator in the connected state. Root cause fully diagnosed; low risk, high operator value.
2. **Fix the create-mode double-click race** (one-line disabled-guard + one browser test) — bundle into the next flight touching `provider-editor.js`.
3. **Run the extended-thinking plan variant** once the account has extra-usage entitlement — the one mission criterion resting on Haiku-only evidence; no flight needed, a lightweight task.
4. **Update `leg-execution.md` crew prompts** (mission-control side) to mandate foreground suite runs — no backgrounding/monitors — eliminating the thrice-repeated Developer stall.
5. **Promote the filmstrip technique** from a per-spec note into the behavior-test AUTHORING guide (mission-control side) as the standard method for sub-round-trip transient UI states.
6. **Direct test-count measurement** (`pytest --collect-only` diff) in leg self-reports, replacing delta arithmetic.

## Action Items

- [ ] Follow-up flight candidate: plan-provider 429/entitlement UX (message mapping + optional proactive indicator)
- [ ] Bundle the sign-in double-click guard + test into the next `provider-editor.js` flight
- [ ] Run `extended-thinking-tool-turn` (plan variant) post-entitlement; update the mission known issue when done
- [ ] Mission-control: foreground-suite mandate in leg-execution crew prompts; filmstrip technique into behavior-test AUTHORING.md
- [ ] Re-measure unit-suite wall-clock on an unloaded host at the next maintenance cycle (watch: 433s vs 296–392s band)
