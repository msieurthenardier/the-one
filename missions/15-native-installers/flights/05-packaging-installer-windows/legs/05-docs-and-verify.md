# Leg: docs-and-verify

**Status**: completed
**Flight**: [Packaging & Installer — Windows](../flight.md)

## Objective

Close the flight: record the `run_shell` Windows tree-kill disposition (carry, not
fix), confirm the docs reflect the new `the-one doctor` command + Windows packaging,
verify all lanes (host-native unit suite green + the `windows-2022` packaged-smoke
green on the PR) and that `serve`/`chat`/`app` are unchanged, and present the
**optional operator HAT** (install the real `.exe` on a Windows box) as an early
preview of the F9 comprehensive acceptance.

## Context

This is the flight's closing leg. Unlike Legs 1–4 it is **not** a code leg — most of
its docs work was front-loaded into Legs 1–4 (the `the-one doctor` entries in
CLAUDE.md/README.md, the `packaging/windows/README.md` build + SmartScreen +
CI-smoke sections all landed already). What remains is: (a) the explicit `run_shell`
tree-kill disposition record, (b) the final verification gate (the packaged-smoke is
the load-bearing one — it runs on the PR, not on this host), and (c) the optional
operator HAT, which needs the operator's Windows box + the CI-built installer artifact.

Per the agentic-workflow skill, the HAT portion is **operator-guided, not
agent-executed** — the Flight Director presents steps; the operator performs them.

## Inputs

- All Legs 1–4 committed (`22da0f4`), draft PR #112 open (base `flight/04`).
- `windows-packaged-smoke` CI job running on the PR — the spawn-fix's real proof.
- Mission Known Issues (`missions/15-native-installers/mission.md`) already carries the
  `run_shell` Windows tree-kill item *(discovered F3 L4, 2026-06-14)* with a
  "Follow-up (Flight 5 or a maintenance pass)" note — Leg 5 records the **F5
  disposition**.
- Flight Open Questions already resolved the tree-kill **OUT** of this flight
  (`_kill_process_tree` Windows path is a bare `proc.kill()`; wiring a Job Object into
  the non-PTY shell proc is more than a one-liner → not a freeze blocker, a robustness
  gap; Windows ships unsandboxed per mission DD9).
- Docs already updated: `the-one doctor` in CLAUDE.md + README.md; Windows packaging in
  `packaging/windows/README.md` (build, installer, SmartScreen, CI-smoke).

## Outputs

- The `run_shell` tree-kill disposition recorded in the flight log (and the mission
  Known Issue annotated with the F5 outcome: carried to F7/maintenance).
- A verification summary (host lanes + PR packaged-smoke + no-regression) in the flight
  log.
- The optional operator HAT presented; its result (run / deferred) recorded.

## Acceptance Criteria

- [ ] The `run_shell` Windows tree-kill disposition is recorded: **OUT of Flight 5**
      (robustness gap, not a freeze blocker; Windows unsandboxed per DD9) → **carried
      to F7/maintenance**. The mission Known Issue is annotated with this F5 outcome.
- [ ] Docs verified to reflect the flight's new surface: `the-one doctor`
      (CLAUDE.md + README.md), Windows build/installer/SmartScreen/CI-smoke
      (`packaging/windows/README.md`). (Already landed in Legs 1–4 — this is a
      confirm, not new work.)
- [ ] Host-native unit suite green (confirmed: 3115 passed) and the **`windows-2022`
      packaged-smoke green on PR #112** (the spawn-fix's real proof). A red
      packaged-smoke is the Divert signal → investigate/fix in a new commit, re-run.
- [ ] No regression: `serve` / `chat` / `app` / `version` dispatch unchanged
      (confirmed by the flight Reviewer; the packaged-smoke also exercises frozen
      `serve`).
- [ ] The **optional operator HAT** is presented to the operator (install the
      CI-built `the-one-setup-*.exe` on a Windows box; confirm the window launches, a
      child process spawns via `the-one doctor`, single-instance holds). Its outcome
      (performed / deferred to F9) is recorded. The flight may land with the HAT
      deferred — it is an early preview, not a landing gate (the comprehensive HAT is
      F9).

## Verification Steps

- Confirm the mission Known Issue annotation names the F5 disposition.
- `grep -n "doctor" CLAUDE.md README.md packaging/windows/README.md` → present.
- Read PR #112 checks: `windows-packaged-smoke` = pass (frozen `doctor` exit 0 +
  `child spawn: OK` + `RESULT: PASS`; frozen `serve` → `/api/info` 200; single-instance
  probe). If red, treat as Divert.
- Operator HAT (optional, operator-run): download the `the-one-windows-installer`
  artifact from the PR's CI run, install on a Windows box, launch the Start-menu
  shortcut, run `the-one doctor` from the install dir, launch a second instance to
  confirm single-instance.

## Implementation Guidance

1. **Tree-kill disposition.** Annotate the mission Known Issue's `run_shell` item with
   the F5 outcome (carried to F7/maintenance, with the one-line rationale). Record the
   same in the flight log. No code change — `_kill_process_tree`'s Windows bare
   `proc.kill()` stays as-is this flight.
2. **Docs confirm.** Verify (don't re-add) the `the-one doctor` + Windows-packaging
   docs landed in Legs 1–4. If any gap, fill it tightly.
3. **Verification gate.** Wait for the PR's `windows-packaged-smoke` to go green; record
   its result. If red → Divert (investigate, fix in a new commit — no amend — re-run).
4. **Operator HAT (optional).** Present the HAT steps to the operator. If they run it,
   record the outcome; if they defer, record "deferred to F9 comprehensive HAT". Do not
   block landing on it.

## Edge Cases

- **Packaged-smoke red** — the flight's central-risk Divert. Do not land; fix + re-run.
- **CI still running at flight-close time** — record the in-flight CI state; the flight
  lands once the packaged-smoke is green (the spawn criterion is behavior-test/CI-backed
  per the mission). If the operator accepts landing with CI pending, record that
  disposition explicitly.
- **No operator Windows session available** — defer the HAT to F9 (documented as
  optional/early-preview); not a blocker.

## Files Affected

- `missions/15-native-installers/mission.md` — annotate the `run_shell` tree-kill
  Known Issue with the F5 disposition.
- `missions/15-native-installers/flights/05-packaging-installer-windows/flight-log.md`
  — disposition + verification summary + HAT outcome.
- (No `the_one/` runtime changes.)

---

## Post-Completion Checklist

- [ ] Tree-kill disposition recorded (flight log + mission Known Issue)
- [ ] Docs confirmed
- [ ] Packaged-smoke green on PR (or landing-with-pending-CI disposition recorded)
- [ ] Operator HAT presented; outcome recorded
- [ ] Update flight-log.md
- [ ] Set this leg's status to `completed`
- [ ] Flight completion (Phase 3): flight → `landed`, check off flight in mission.md

## Citation Audit

Citations verified at leg design time (2026-06-14): mission Known Issues `run_shell`
item present; flight Open Questions tree-kill resolution present; `the-one doctor` in
CLAUDE.md/README.md/packaging README (landed Legs 1–4); PR #112 + the
`windows-packaged-smoke` job. No drift; all `OK`.
