# Leg: behavior-gate-and-docs

**Status**: completed
**Flight**: [Channel Contract](../flight.md)

## Objective
Finalize and pass the `stub-connector-round-trip` behavior test against a live dev instance, rewrite the connector docs to the new contract, revisit the Flight-1-accepted stale comments, and record the flight's final metrics.

## Context
- The behavior spec draft is at `tests/behavior/stub-connector-round-trip.md` (Status: draft). Leg 2 delivered everything its apparatus needs: the dual-gated seams, the stub-registration lifespan hook, the `/types` gate, the Studio form with registered testids. Finalize the steps with the real testids/routes, set Status `active`.
- Dev instance: `THE_ONE_PORT=8485`, scratch `THE_ONE_DATA_DIR`, `dev_mode`, `THE_ONE_STUB_TEST_ENDPOINT=1`. Never 8484 / default data dir. The instance needs an agent (`test-agent`) with the send tool enabled and a working provider — provider choice is the operator's environment (Ollama if running locally, else a configured key); CONFIRM with the operator before the run if no provider is reachable.
- The behavior test is run by the Flight Director via `/behavior-test stub-connector-round-trip` — NOT by this leg's Developer. This leg's Developer prepares: docs, spec finalization, and a small `scripts/`-style or documented one-liner to boot the dev instance with the right env (documented in the spec's Preconditions, not a committed helper unless one already fits conventions).
- Docs to rewrite (Flight DD scope + mission criterion 11 partial):
  - `the_one/connectors/README.md` — NEW: the contract (Protocol, envelope flags, manager lifecycle, inbound pipeline stages, pairing, reply policy, authorization rule incl. the DM/peer-keyed union, config schema, seams + gates). Short — the contract, not a novel.
  - `the_one/agents.md` — a new connector-subsystem section describing the reset contract; update any convention exemplars that should now cite the new modules.
  - `README.md` — replace the Flight-1 "reset; contract lands in Flight 2" placeholder with a real architecture paragraph.
  - `SECURITY-MODEL.md` — pairing/allowlist admission, send-tool authorization, the dual-gated seams, credentials masking/rotation coverage for connectors.
  - `CLAUDE.md` — new env vars (`THE_ONE_STUB_TEST_ENDPOINT`) and anything lane-relevant.
- **Flight-1 debrief comment revisit** (debrief recommendation 4): `app.py:230-234` and `agent/factory.py:129-174` present-tense comments about gateway-listener consumers — the factory accessor and send tool have real callers again; update each comment to the new true shape (some become correct as-is, verify).
- **Open item to record, not fix**: no persisted `enabled` concept (leg 2 deviation 1) — deferred to Flight 3 design. State it in `connectors/README.md`'s known-limitations note and the flight log.
- Public repo: no usernames/home paths anywhere.

## Inputs
- Legs 1–2 landed (uncommitted): Python 1,028 / JS 608; suite 3,665 green; lanes green.

## Acceptance Criteria
- [x] `tests/behavior/stub-connector-round-trip.md` finalized (real testids, exact seam payloads, provider-agnostic agent prompt), Status `active`
- [x] `/behavior-test stub-connector-round-trip` PASSES — run 2026-08-31-22-43-08, 7/7 checkpoints (checkpoint 5 via sanctioned rerun under the documented spec amendment); run logs for both runs committed; flight log references them
- [x] Docs rewritten per Context; `grep -rn "routing engine\|connector_acls\|peer approval\|engagement gate\|discoverable dropdown" the_one/connectors/README.md the_one/agents.md README.md SECURITY-MODEL.md CLAUDE.md` returns nothing
- [x] Stale-comment revisit done: `app.py:230-234` and `factory.py:129-174` read true against the current tree
- [x] Final metrics in the flight log: Python connector total vs 1,500 and the mission 3,000 running count; JS total vs 650/1,000; suite + lane numbers
- [x] `make test-unit` and all four lanes green (docs-only changes shouldn't move them — verify anyway)

## Verification Steps
- The behavior-test run IS the flight's end-to-end verification (criteria 2/4/6/7 of the mission trace through it).
- Docs greps above; foreground suite + lanes at close.

## Implementation Guidance (Developer portion)
1. Finalize the behavior spec against the real UI/routes (walk the leg-2 testid registry entries).
2. Docs rewrite; comment revisit; known-limitations note (enabled-field deferral).
3. Verify suite + lanes; append flight-log entry with final metrics; hand back for the Flight Director's behavior-test run.

## Edge Cases
- **Behavior test failure**: an unmet acceptance criterion — the leg does NOT land while it fails; investigate, fix, re-run (new commit cycle handled at flight level).
- **No reachable provider on the dev instance**: STOP and ask the operator — do not fake a provider or stub the agent loop; the test's value is the real loop.

## Files Affected
`tests/behavior/stub-connector-round-trip.md`, `the_one/connectors/README.md` (new), `the_one/agents.md`, `README.md`, `SECURITY-MODEL.md`, `CLAUDE.md`, `app.py`/`factory.py` (comments only), flight log.

---

## Post-Completion Checklist
- [ ] All acceptance criteria verified (behavior-test pass included)
- [ ] Update flight-log.md (final metrics + run-log reference)
- [ ] Set this leg's status to `landed` — commit happens at flight end
- [ ] Check off this leg in flight.md
