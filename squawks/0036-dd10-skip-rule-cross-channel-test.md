# Squawk 0036: Test pinning DD-10's cross-channel skip-rule trade-off

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-02
**Completed**: 2026-09-02

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

Added `test_round_trip_cross_channel_tool_send_suppresses_auto_reply` to
`tests/test_connectors_inbound.py`, modeled on the existing skip-rule proof
(`test_round_trip_paired_peer_gets_reply`). It admits an inbound turn on
channel `ch-1`, has the agent's first assistant step tool-send successfully
via `send_to_platform_channel` to a DIFFERENT channel (`ch-2`, same
connector), then produce a trailing plain-text `done`. Asserts: exactly one
`StubPlugin.outbound_records` entry (the tool's own send to `ch-2`, content
`"posted elsewhere"`), and the turn's final assistant message (`"done"`)
keeps `visibility == OPERATOR_VISIBILITY` — no auto-delivery back to the
originating `ch-1`. This pins DD-10's accepted trade-off: the skip rule in
`_auto_deliver_reply` is a whole-turn scan, not scoped to the originating
target, so a cross-channel tool-send still suppresses auto-delivery of the
turn's own reply-in-kind.

Checked `the_one/connectors/README.md`'s "Reply visibility" / DD-10 section
— the cross-channel trade-off is already stated there explicitly ("even
when the tool-send targeted a *different* channel; the agent's own plain
text then stays operator-only, by design"), so no doc change was needed.

No behavior change: `_auto_deliver_reply` in `the_one/connectors/inbound.py`
was not touched.

## Verification

`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_connectors_inbound.py -x --timeout 30`
→ 37 passed (was 36; +1 for the new test), no failures.

## Sign-Off
**Reviewer**: independent batch Reviewer (Haiku), squawk/turnaround-2026-09-02
**Verdict**: confirmed
**Commit**: squawk/turnaround-2026-09-02 batch commit (PR follows)
