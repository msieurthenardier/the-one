# Leg: hat-and-alignment

**Status**: in-flight
**Flight**: [HAT and Alignment](../flight.md)

## Objective

Walk the operator through Mission 33 (Routines) end to end, fix what
surfaces, confirm or reverse every judgement call in the flight's DD4, and
record the operator's verdict on every mission criterion.

## Context

- **Environment (DD2):** a dev instance from this branch at
  `http://127.0.0.1:8490`, scratch data dir `$HOME/the-one-hat-m33/data`,
  scratch cwd `$HOME/the-one-hat-m33/cwd`, dev mode off, started and stopped
  by recorded PID. The operator browses through a handoff link.
- **Not seeded:** the operator adds the Anthropic provider (Claude Haiku)
  and the Discord connector (a newly created bot token) in the UI, so no
  secret passes through the Flight Director.
- **Inputs:** the draft walk (Parts A-J) and DD4's judgement-call table in
  the flight spec.
- **Fix routing (DD6):** look-and-feel fixes inline through a Developer;
  new or changed behaviour through the fix-vs-feature gate as an added leg;
  a DD5 contract change is a deliberate re-author with its re-runs.

## Acceptance Criteria

- [ ] Every walk step in Parts A-H is verified by the operator, or its
      finding is fixed and re-verified, or recorded as accepted.
- [ ] A real Discord DM routine delivered (Part D).
- [ ] Every DD4 call is confirmed or reversed, recorded in the flight log.
- [ ] Every mission criterion has the operator's verdict (DD7), the upgrade
      clauses resting on the v45-v48 migration tests.
- [ ] Any fixes are reviewed; the HAT instance is stopped and its data dir
      deleted; the closing gate is green on one commit; DD5 re-runs done if
      needed.

## Verification Steps

- The flight log's Judgement-Call Verdicts, Mission Criteria Verdicts and
  Leg Progress sections.
- The closing gate's unit counts and `PARALLEL_RESULT` line.
