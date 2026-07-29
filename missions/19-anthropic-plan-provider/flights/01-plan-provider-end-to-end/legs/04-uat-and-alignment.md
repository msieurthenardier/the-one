# Leg: uat-and-alignment

**Status**: ready
**Flight**: [Anthropic Plan Provider End-to-End](../flight.md)

## Objective

Guided HAT session: the operator verifies the full plan-provider experience against the real system with a real Pro/Max account — live sign-in, chat parity, extended thinking, and the invalidated editor behavior specs — with issues fixed inline until the operator is satisfied.

## Context

- Interactive leg — no autonomous Developer/Reviewer spawns. The Flight Director guides the operator step by step; fixes ride the inline protocol (fix-vs-feature gate: new behavior → scoped design review first; look-and-feel fixes → inline; multi-surface "cosmetic" fixes → lightweight design-review pass first).
- Legs 1–3 committed @ bf1e1d2 on `flight/01-plan-provider-end-to-end`, draft PR #164.
- `provider-editor.js` changed → `system-provider-config` and `save-preserves-config` behavior specs are invalidated and must be re-run (M17 F07 cite-vs-rerun rule).
- Sign-in control testids (from Leg 3): `plan-signin-btn`, `plan-signin-url`, `plan-signin-open-btn`, `plan-signin-copy-btn`, `plan-code-input`, `plan-code-submit-btn`, `plan-connected-indicator`, `plan-reauth-btn`, `plan-reset-btn`, `plan-signin-error`, `plan-test-reauth`.
- Expected nuance: the auto-popup after Sign in is often popup-blocked (gesture lost post-fetch — documented, accepted); the copyable URL + "Open sign-in page" button is the first-class path.
- Dev server has no hot reload — `make restart` before the session and after any fix.

## Verification Steps (acceptance criteria)

- [ ] **0. Session setup**: `make restart`; operator confirms the web UI loads and they can reach claude.ai signed in (decay-prone precondition probe).
- [ ] **1. HAT prep**: add the plan-provider Variant entry to `tests/behavior/extended-thinking-tool-turn.md` (input delta: provider under test = the plan provider created in step 2).
- [ ] **2. `/behavior-test anthropic-plan-signin`** passes (operator performs the consent + hands over the code; run log committed).
- [ ] **3. `/behavior-test anthropic-plan-chat-parity`** passes (operator names the deterministic tool in preconditions; performs the restart step; run log committed).
- [ ] **4. `extended-thinking-tool-turn` (plan variant)** passes (run log committed).
- [ ] **5. Re-runs**: `system-provider-config` and `save-preserves-config` pass (run logs committed).
- [ ] **6. Free-form UAT**: operator exercises anything else they care about (reset/re-auth flow, second account, Studio binding); issues fixed inline per the gate until the operator is satisfied.
- [ ] **7. Close-out**: leg `completed`; flight → `landed`; flight checked off in mission.md; final commit; PR marked ready for review.

## Notes

- A failing behavior test is an unmet acceptance criterion — the leg does not land while it fails, unless the operator explicitly accepts a failure as a known issue (recorded in the flight log with the run-log path).
- Behavior-test runs go through `/behavior-test {slug}` (the run skill orchestrates its own Executor/Validator crew); evidence stays out of the repo, run logs are committed.
