# Leg: behavior-test-and-docs

**Status**: completed
**Flight**: [Windows PTY Parity (ConPTY)](../flight.md)

## Objective

Author the Windows PTY parity Witnessed behavior-test spec (DD8 — operator runs
it on real Windows hardware, doubling as the definitive Leg-3 orphan-reap proof),
update the docs to reflect the Windows PTY backend + its platform differences,
and run the final verify-integration pass.

## Context

- **DD8:** the mission marks "PTY parity (behavior-test-backed)"; the spec is
  `tests/behavior/windows-pty-parity.md` (authored at leg design — present). The
  operator runs it on a `the-one` instance on their Windows box. It also gives
  the **definitive orphan-reap answer** the Leg-3 CI harness couldn't (the
  `tasklist`-based grandchild check after close + parent-death).
- **DD9:** Windows is passthrough/unsandboxed — docs must state this plainly; the
  Job Object is *lifecycle teardown*, NOT containment.
- Two real gaps to document (already in mission Known Issues): the `run_shell`
  (non-PTY) Windows timeout tree-kill gap, and the orphan-reap CI-harness
  flakiness (xfailed; proven instead by the behavior test).
- This is the final leg — verify-integration confirms all lanes green + the
  import cascade on Windows + no Linux/macOS regression.

## Inputs

- `tests/behavior/windows-pty-parity.md` — authored (this leg's spec).
- `SECURITY-MODEL.md` — documents the sandbox model; needs a Windows section.
- `CLAUDE.md` / `the_one/agents.md` — developer/agent guidance; need Windows PTY
  notes.
- `missions/15-native-installers/mission.md` Known Issues — already carries the
  `run_shell` Windows tree-kill gap (added Leg 4); review for completeness.

## Outputs

- `SECURITY-MODEL.md` — a Windows subsection: interactive tools run **unsandboxed**
  (passthrough, DD9); the PTY Job Object is lifecycle teardown (reaps the tree on
  close / parent-death) NOT a containment boundary; the `run_shell` non-PTY
  timeout tree-kill gap noted.
- `CLAUDE.md` / `agents.md` — Windows PTY notes: `WindowsPtySession` via
  `pywinpty`/ConPTY; the **socket-timeout idle-read** mechanism (not `proc.read()`
  / `read_blocking`); the split-module structure (`pty.py` dispatcher /
  `pty_unix` / `pty_windows`); the `_WINDOWS_ENV_ALLOWLIST`; the **curated
  `windows-2022` CI lane** (platform-relevant subset, DD7-revised — and the
  rule: a new platform-divergent test file must be added to the workflow's
  curated list or it won't run on Windows); that the bwrap teardown branch is
  never taken on Windows.
- Behavior-test run log (after the operator runs it) at
  `tests/behavior/windows-pty-parity/runs/{ts}.md` — referenced from the flight log.
- Final verify-integration confirmation in the flight log.

## Acceptance Criteria

- [ ] `tests/behavior/windows-pty-parity.md` exists, is well-formed (Witnessed
      format), and its orphan-reap rows resolve the Leg-3 DD-OQ. *(Authored at
      leg design — confirm present.)*
- [ ] `SECURITY-MODEL.md` has a Windows subsection (passthrough/unsandboxed;
      Job Object = lifecycle not containment; `run_shell` tree-kill gap).
- [ ] `CLAUDE.md` and `agents.md` carry the Windows PTY notes (pywinpty/ConPTY,
      socket-timeout read, split-module, env allowlist, curated CI + the
      add-new-file rule, never-taken bwrap branch).
- [ ] Mission Known Issues reviewed; the `run_shell` gap + orphan-reap-CI-harness
      note are present and accurate.
- [x] ~~Operator runs `/behavior-test windows-pty-parity` this flight~~ →
      **DEFERRED 2026-06-14 (operator): run against the real Windows installer**
      (Flight 7/8 acceptance), not a pip-dev-install — a stronger apparatus. Spec
      authored + ready (`tests/behavior/windows-pty-parity.md`). The DD-OQ
      orphan-reap is CI-proven at the plumbing level (Job Object code correct;
      round-trip 7/7); its definitive tree-reap proof rides the deferred run.
- [ ] verify-integration: all CI lanes green (test/browser/bwrap/lint + curated
      windows); the app/CLI import cascade succeeds on Windows (Leg-1 contract
      holds); no Linux/macOS regression.

## Verification Steps

Docs (implementing agent, locally):
- The docs edits are accurate against the shipped code (cross-check the
  socket-timeout read, the Job Object, the curated CI list).
- `.venv/bin/python -m pytest tests/ --timeout=300 -q` — green (docs-only edits
  shouldn't affect tests; run as a regression guard).
- Markdown/lint as the project conventions require.

Behavior test (operator, on the Windows box):
- Stand up a `the-one` instance on Windows (`pip install -e ".[all-llms,dev]"`),
  configure an agent with `shell_session_*` tools, run
  `/behavior-test windows-pty-parity`, and confirm pass — especially the
  orphan-reap rows (steps 6-8), the definitive DD-OQ check.

Integration (Flight Director):
- Confirm the latest PR run is green across all lanes; record the final state.

## Implementation Guidance

1. **Docs are the implementable part of this leg** (the behavior spec is already
   authored; the operator runs it). Spawn the docs work:
   - `SECURITY-MODEL.md`: add the Windows subsection (see Outputs). Keep it
     factual — Windows is a documented unsandboxed gap, not a regression.
   - `CLAUDE.md` / `agents.md`: add the Windows PTY developer notes. Be precise
     about the socket-timeout read (the `read_blocking`-after-spawn no-op trap is
     worth a sentence so a future maintainer doesn't reintroduce it) and the
     curated-CI add-new-file rule.
2. Do NOT change backend/test code — docs + spec only. If a doc edit reveals a
   code inaccuracy, flag it to the FD rather than silently fixing.
3. The behavior-test RUN is the operator's (interactive, real Windows box) — the
   FD guides the operator; do NOT spawn agents to run it autonomously (no Windows
   app instance is reachable from the Linux dev/CI environment).

## Notes for the Flight Director

- Spawn a Developer for the docs; review; then guide the operator through the
  behavior test on their Windows box (record the run log + disposition).
- The behavior test is the definitive orphan-reap proof — if it passes, the DD-OQ
  is fully resolved (CI proved the Job Object plumbing; the operator's box proves
  the actual tree-reap). If the operator defers running it, land the flight with
  the criterion noted as "spec authored, operator-run pending" per DD8.
- On completion: flight → landed, check off in mission.md, `[COMPLETE:flight]`,
  then `/flight-debrief`.
