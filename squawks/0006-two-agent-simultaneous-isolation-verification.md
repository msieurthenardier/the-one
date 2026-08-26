# Squawk 0006: Verify two-agent-simultaneous self-configuration isolation

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-26
**Completed**: —

## Report

The self-configuration surface binds one credential to exactly one agent, and
Flight 1 asserted two-agent isolation (Leg 2 AC9) by enforcement inspection plus
code review — **not** a dedicated two-agent-simultaneous end-to-end test. Add an
e2e test that stands up two surface-enabled agents at once and proves their
surfaces and credentials do not cross: agent A's credential resolves only to A,
cannot read or write B's configuration, and vice versa, with both live
concurrently. If it surfaces a real cross-agent leak, escalate.

Carried forward from the Flight 1 debrief and re-homed here after being pulled
out of Mission 21 Flight 2 Leg 2 at design review.

## Evidence

- Flight 1 debrief, "What Could Be Improved → Technical": "Two-agent isolation
  (Leg 2 AC9) was ticked on enforcement + code inspection, not a dedicated
  two-agent-simultaneous end-to-end test."
- Identity resolution: `the_one/self_configuration/surface.py` `_calling_agent`
  (resolves the agent from the credential; DD9 refuses a disabled/foreign
  surface). Credential registry: `the_one/self_configuration/credentials.py`.
- Mission 21 Flight 2 debrief Action Items (2026-08-26): confirmed not yet logged
  until this squawk.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
