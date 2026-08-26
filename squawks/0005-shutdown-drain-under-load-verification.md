# Squawk 0005: Verify shutdown-drain under load for a surface-enabled agent

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-26
**Completed**: —

## Report

Flight 1 (Self-Configuration Surface) implemented the shutdown-drain WARNING
mitigation — the lifespan evicts every marked surface row's pool entries before
`_mcp_pool_shutdown_drain()`, so a loopback session can terminate while the
listener is still up. The mitigation is **reasoned but never exercised under
load**: neither Flight 1 nor Flight 2 ran a test with a surface-enabled agent
holding a *live pool connection at shutdown*. Add that verification. If it
surfaces a real drain defect, escalate to a flight rather than expanding this
squawk.

Carried forward from the Flight 1 debrief and re-homed here after being pulled
out of Mission 21 Flight 2 Leg 2 at design review (pool/lifecycle verification
debt, orthogonal to approval governance).

## Evidence

- Flight 1 debrief, "What Could Be Improved → Technical": "Shutdown-drain WARNING
  mitigation is reasoned but unproven under load."
- Mission 21 Flight 2 flight log (2026-08-25): the two Flight-1 carry-overs pulled
  out of Leg 2 at design review; Flight 2 debrief Action Items confirm neither was
  logged until now.
- Mitigation site: the app lifespan's pre-drain eviction of marked rows' pool
  entries ahead of `_mcp_pool_shutdown_drain()` (`the_one/interfaces/web/app.py`
  lifespan).

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
