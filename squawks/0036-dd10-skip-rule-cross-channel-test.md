# Squawk 0036: Test pinning DD-10's cross-channel skip-rule trade-off

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: —

## Report

DD-10's skip rule suppresses the auto-reply for any turn containing a successful
`send_to_platform_channel` result — including one targeting a DIFFERENT channel than
the originating conversation. That trade-off is accepted and recorded in the DD, but
no test asserts the behavior for the cross-channel case (an agent that tool-sends
elsewhere mid-turn leaves the originating peer with no reply, text staying
operator-only). Add one test pinning the accepted behavior so a future change to the
skip rule is deliberate, and a one-line note in the README's auto-reply section if
absent.

## Evidence

- `the_one/connectors/inbound.py::_auto_deliver_reply` — whole-turn skip-rule scan
- Flight 3 flight.md DD-10 trade-off clause
- Raised by the Flight 3 debrief (2026-09-02), Architect interview

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
