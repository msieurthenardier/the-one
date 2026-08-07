# Leg: behavior-test-apparatus

**Status**: landed
**Flight**: [Authenticated Local API End-to-End](../flight.md)

## Objective

Establish, project-side, the convention by which a behavior-test Executor obtains
a credential and constructs a handoff URL — so the **24 active** behavior-test
specs keep working under the gate without any spec's step table being edited.

## Context

This leg exists because the flight's reconnaissance missed an entire caller
category twice over: neither the initial scoping nor the mission-level review
noticed that behavior-test specs drive a real browser at the app root with no
credential step. Of **33** specs, **24** are `active`, and **11** name the
default port `:8484` directly — the operator's production instance. Every one of
them breaks at step 1 the moment the gate goes live.

They are separated from `operational-callers` because this is mechanism design
rather than header attachment, and because correctness is judged by *running
specs*, not by a green suite.

Design decision implemented: **DD13** — the apparatus is a first-class caller,
credentialed project-side by standing instruction.

### Why instruction rather than code

`CLAUDE.md` is auto-loaded into any session working in this repository, so an
Executor driving the app inherits the convention without any spec being touched,
and every *future* spec gets it for free rather than acquiring the same footgun.
It also respects Mission Control's boundary rule: the `/behavior-test` skill must
not encode a convention owned by one project.

The trade-off is real and should be stated in the text itself: instruction-
carried conventions are softer than code — an agent can miss them in a way a
fixture cannot. Two things mitigate it. The specs' own Preconditions are checked
by the runner before agents are spawned, and a missed credential fails loudly at
step 1 rather than silently.

### Prior-leg learnings

- Leg 2 built `mint_handoff_credential()` in
  `the_one/interfaces/web/handoff_store.py` for in-process minting, **and** an
  authenticated mint endpoint for out-of-process callers (LD2). A behavior-test
  Executor is an out-of-process caller: it must use the **endpoint**, presenting
  the long-lived credential read from the target instance's data directory.
- The handoff credential is single-use and short-lived (DD12). A spec that
  navigates twice needs two mints — this is exactly why the endpoint exists.
- `/api/live` is unauthenticated, so a spec's "is the app up" precondition needs
  no credential.

## Acceptance Criteria

- [x] `CLAUDE.md` carries the convention: how to read the long-lived credential
      from a given instance's data directory, how to obtain a handoff URL from
      the mint endpoint, and that a handoff credential is single-use so a second
      navigation needs a second mint.
- [x] The `.flightops/agent-crews/` prompts where a crew drives the app carry it
      too — at minimum `behavior-tests-execution.md`, which is where the Executor
      and Validator prompts live.
- [x] The convention states the **safety rule** explicitly: never point a
      behavior test at the operator's production instance on the default port;
      use a dedicated dev instance with a scratch data directory.
- [x] The active specs naming `:8484` are updated so they do not target the
      production instance by default. This is a Preconditions-level change, not
      a step-table change. (Actual count found by inspection: 8 active specs
      literally defaulted to or allowed `:8484`, corrected to a non-default
      port + scratch data directory; 8 more active specs named no port at all
      and were given explicit non-default-instance guidance to close the
      ambiguity; 6 already correctly targeted a non-default port and only
      needed the convention reference added; the 2 Windows specs were left
      intentionally targeting `:8484` — see their Preconditions for why. All
      24 active specs' Preconditions were touched. Detail in the flight log.)
- [x] No spec's Action/Expected-Result step table gains a credential step. Two
      specs resisted a pure-Preconditions fix and are recorded as findings in
      the flight log rather than forced: `windows-native-frame-splash` Step 9,
      and (as a scope/authorization question, not a mechanism gap)
      `discord-approval-flow` / `discord-slash-end-to-end`'s dependency on
      whichever instance holds the live Discord bot connection.
- [x] The new `local-api-auth-session-lifecycle` spec is consistent with the
      convention it documents — it is the one spec that tests the credential
      machinery itself; Steps 6 and 14 described the launcher's in-process
      mint (`mint_handoff_credential()`), which an out-of-process Executor
      cannot reach — corrected to the `POST /api/session/handoff` endpoint
      path, matching what Legs 1-5 actually built.
- [ ] A representative existing spec is **actually run** via `/behavior-test`
      against a dev instance with the gate live, and passes. **Not done in
      this leg execution** — the orchestrating instructions for this leg
      explicitly excluded running any behavior test (needs a dev instance and
      an operator, and other concurrent work is using the shared test
      apparatus). Documentation/convention review stands in for this criterion
      for now; the actual run is a follow-up once Legs 1-5 land and a dev
      instance is available — see the flight log.

## Verification Steps

- Run one representative existing spec end-to-end via `/behavior-test <slug>`
  against a **dedicated dev instance on a non-default port**, gate live.
- Confirm its run log records a credentialed navigation.
- Review the remaining active specs' Preconditions by inspection.

## Edge Cases

- **A spec that navigates to the app root more than once** — each navigation
  past the first must either reuse the established session cookie (normal) or
  mint a fresh handoff. Reusing a spent handoff URL will fail, by design.
- **A spec whose apparatus is shell-only** and never opens a browser — it needs
  the `Authorization` header, not a handoff URL. The convention should cover
  both shapes rather than assuming browser.
- **Specs marked `draft` or `archived`** — 9 of the 33 are not `active`. Decide
  whether they are in scope; leaving a `draft` spec stale is defensible, leaving
  an `active` one broken is not.
  **Decision**: out of scope for this leg, left untouched (except
  `local-api-auth-session-lifecycle`, handled separately below because it is
  explicitly named in the Acceptance Criteria). The other 8
  (`chat-loop-hang-and-cancel`, `discord-engagement`, `discord-multi-agent-
  routing`, `discord-multi-channel-routing`, `discord-multi-user-routing`,
  `gemma-tool-use-recovery` [retired], `studio-smoke` [archived],
  `windows-pty-parity`) are not currently run by anything and several
  (`discord-engagement`, `studio-smoke`) still default to `:8484`. Rationale:
  a `draft`/`archived`/`retired` spec gets a full review at promotion time
  regardless (drafts are unfinished by definition; archived/retired specs are
  not going to run again), so pre-emptively fixing preconditions on specs that
  may be substantially rewritten before ever executing is scope creep this leg
  doesn't need to take on. Residual risk: an operator who manually runs one of
  these against a live-gated instance today must apply CLAUDE.md's convention
  by hand, since the spec file doesn't yet reference it — accepted and
  recorded in the flight log.
- **The operator's real instance already running on `:8484`** — the convention
  must make targeting it hard, not merely discouraged.

## Files Affected

- `CLAUDE.md` — the standing convention.
- `.flightops/agent-crews/behavior-tests-execution.md` — Executor/Validator
  prompts.
- The `active` specs' Preconditions where they name the default port.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified by inspection (one criterion — the
      actual `/behavior-test` run — deliberately not executed this pass; see
      above and the flight log)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md — left to the Flight Director /
      flight-end review gate (this leg's scope note said documentation only;
      flight.md is a flight-level artifact, not one of this leg's Files
      Affected)

> Commit is deferred to the flight-end review gate. Do **not** commit and do
> **not** signal `[COMPLETE:leg]`.
