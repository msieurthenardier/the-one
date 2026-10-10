# Leg: hat-and-alignment

**Status**: completed
**Flight**: [HAT and Alignment](../flight.md)

## Objective

Walk the operator through Mission 27 end to end, fix what surfaces, and settle
the open criterion and every autonomous judgement call.

## Context

- **Environment:** a scratch dev instance at `http://127.0.0.1:8490`, with a
  scratch data directory in the Flight Director's scratchpad. It runs
  `THE_ONE_DEV_MODE=true` and `THE_ONE_STUB_TEST_ENDPOINT=1`.
- **Seeded:**
  - the provider "Local Ollama" (`gpt-oss:20b`);
  - the agent `hat-agent` (persona "You are a concise assistant.", no rules,
    notes off);
  - `fetch_url` and `http_request` with `extra_allowed_hosts: ["127.0.0.1"]`;
  - the stub connector `hat-stub` (`default_agent` `hat-agent`, with `peer-1`
    paired);
  - the planted page at `http://127.0.0.1:8794/planted.html`.
- **Inputs:** the draft walk in the flight spec, and the HAT review list in
  Flight 2's flight log.
- **Fix routing:** look-and-feel fixes are made inline by a Developer. New
  behaviour goes through the fix-vs-feature gate. Changes to the behavior-spec
  contract go through DD2.

## Acceptance Criteria

- [ ] Every walk step (1-10 in the flight spec) is verified by the operator,
      or its finding is fixed and re-verified.
- [ ] The open criterion ("notes presented as notes") is settled.
- [ ] Every judgement call is confirmed or reversed, and recorded in the flight
      log.
- [ ] Any fixes are reviewed, the gate is green, and both behavior specs are
      re-run if their contracts changed.

## Verification Steps

- The operator's verdict per step, recorded in the flight log's Leg Progress.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
