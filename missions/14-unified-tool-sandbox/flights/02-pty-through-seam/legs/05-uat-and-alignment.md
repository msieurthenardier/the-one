# Leg: uat-and-alignment

**Status**: completed *(accepted via operator review of the live behavior-test run — the guided step-by-step was waived as redundant)*
**Flight**: [PTY Through the Seam](../flight.md)

## Objective

A guided human acceptance test: the operator personally drives the real
`the-one` chat UI / agent surface to confirm PTY-session sandbox behavior feels
right and is genuinely contained, with the Flight Director fixing any issue inline
until the operator is satisfied. (Optional leg, interactive — no autonomous agents.)

## Context

- Automated verification is already green: `@requires_bwrap` PTY suite (12 bwrap
  tests total), full suite 3008 passed, and the live `/behavior-test
  pty-session-containment` run (6/7 PASS, 1 inconclusive covered deterministically).
- This leg is human acceptance + alignment — the operator pokes the real surface
  they actually use and signs off on the ergonomics (capable-yet-contained posture,
  interactive usability), not just the assertions a test makes.
- App is live at `http://localhost:8484`; the **Sonnet** agent has the
  `shell_session_*` tools and runs them in a real bwrap PTY on Linux.

## Acceptance Criteria (operator-verified, one at a time)
- [ ] **Capable workspace**: a tool-launched shell session can do real work in
      `$HOME` (write + read a file) — it's not a useless cage.
- [ ] **Filesystem escape denied**: a write outside the allowlist (e.g. `/etc`) is
      refused with an OS-level error.
- [ ] **Secret protected**: the denylisted secret area (`~/.ssh`,
      `~/.the-one/secrets`) is not writable from a session.
- [ ] **Network containment**: a session is network-isolated by default (loopback-
      only / outbound refused).
- [ ] **Clean teardown**: closing a session reaps its processes (no orphan).
- [ ] **Ergonomics**: the interactive session feels usable (multiple commands,
      prompt returns, no surprising breakage) — operator judgment.

## Verification Steps

Driven interactively by the Flight Director with the operator (one step at a time;
issues fixed inline before moving on). Steps are operator-performable in the chat UI
or via `POST /api/chat`. See the flight log's HAT session entry for the running record.

## Files Affected
- None expected (verification only). Any inline fix surfaced here gets its own
  follow-up commit with rationale in the flight log.

---

## Post-Completion Checklist
- [ ] All acceptance criteria operator-confirmed
- [ ] Flight log updated with the HAT session record
- [ ] Leg status → `completed`; checked off in flight.md
- [ ] Any inline fixes committed separately with rationale
