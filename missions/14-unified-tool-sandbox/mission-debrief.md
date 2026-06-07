# Mission Debrief: Unified Tool-Execution Sandbox

**Date**: 2026-06-07
**Mission**: [Unified Tool-Execution Sandbox](mission.md)
**Status**: completed
**Duration**: 2026-06-06 (Flight 1) → 2026-06-07 (Flights 2–4) — batched `/agentic-workflow` execution; Flights 3–4 fully autonomous in one session
**Flights Completed**: 4 of 4 planned core flights (optional Flight 5 "Alignment" declined by operator)

## Outcome Assessment

### Success Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| All four subprocess spawn paths route through **one shared boundary** | **Met** | F1 routed shell + python_exec + MCP stdio; F2 routed the PTY path. The `prepare_spawn → SpawnSpec` seam + `get_sandbox_backend()` factory is the single chokepoint. |
| On Linux, a built-in tool **cannot write outside scope**; network policy-constrained | **Met** | F1 (operator-verified live: `/etc` write blocked, `ENETUNREACH`); kernel-enforced via bwrap `--ro-bind / /` + `--unshare-net`. |
| On Linux, a built-in tool **cannot read outside scope** | **Partially met** | **Boxed path: met** (F4 — minimal rootfs, no user FS). **Host-workspace path: open** — denylist is `--ro-bind-try` (write-protect, still readable). Reframed as a successor flight (needs `ldd`/overlayfs + its own behavior test); documented in the mission known-issue. |
| Interactive **PTY session** governed by the boundary on Linux | **Met** | F2 (behavior-test-backed + `@requires_bwrap`; live `pty-session-containment`). |
| A tool from the **CLI** is sandboxed identically to the web | **Met** | F3 — `@requires_bwrap` parity test on the shared `AgentFactory` tool-construction path; the CLI is not a bypass. |
| No-backend platform routes via **passthrough**, no construction error, enforcement-absence observable | **Met** | F1 — factory + one-time WARNING; F4 extended with a per-call no-enforcement WARNING (`_seam.py`) for boxed-on-passthrough. |
| Sandbox policy applied **uniformly** from one source (built-in + MCP) | **Met** | F1 (`SandboxProfile` model + `_build_tool_profile` + `from_dict`); F3 reinforced with a parity test, not just structure. |
| Existing behavior preserved (MCP launches, suite passes, ruff passes) | **Met** | No regressions across all four flights. |

**Plus an additive capability beyond the original criteria**: F4 delivered **agent-selectable boxed isolation** (box-by-default + `host_access` escalation; true isolation via minimal rootfs), which is what *advanced the read half* of the scope criterion for the boxed path.

### Overall Outcome

The mission achieved its stated outcome: every subprocess GleepGlorp spawns — built-in shell/Python, interactive PTY, and MCP stdio — now passes through one shared, kernel-enforced sandbox boundary on Linux, governing the web and CLI identically, with a passthrough seam for backend-less platforms. **7 of 8 criteria fully met; the 8th (read-scoping) is met for the boxed path and explicitly carried forward for the host path** — a gap that pre-dated the mission and was always scoped as "its own future flight" (F1 debrief). The mission also delivered an additive boxed-isolation capability the original criteria did not require. The operator is satisfied with the outcome (no changes requested). Stakeholder value: the agent's full action surface — not just MCP — is now under one auditable boundary, and Mission 15 (Native Desktop Installers) has a seam a new per-OS backend slots in behind without re-plumbing.

## Flight Summary

| Flight | Status | Key Outcome |
|--------|--------|-------------|
| 01 — Sandbox Seam + Built-in Tool Retrofit | completed | Created the `prepare_spawn → SpawnSpec` seam + bubblewrap/passthrough factory; routed shell/python/MCP through it; the `_build_tool_profile` hook (a deliberate F4 branch point); renamed MCP→ToolSandbox/SandboxError in place. |
| 02 — PTY Through the Seam | completed | Routed the 4th path (PTY `fork`/`execvp`) — single-path (retired F1's dual-path debt for PTY); single-pid SIGKILL + `--die-with-parent` teardown; established the **agent-safe-observable** rule (the mission's canonical behavior-test lesson). |
| 03 — Uniform Policy, CLI Parity & Seam Hardening | completed | `@requires_bwrap` CLI-parity test on the shared `AgentFactory` path; consolidated the bwrap suite behind `_sandbox_fixtures.py`; proved the host-crash PTY-orphan window already mitigated by bwrap's `--die-with-parent`; cleared light debt. |
| 04 — Agent-Selectable Execution Isolation (Boxed Mode) | completed | True isolation via minimal RO system rootfs + host-bound scratch; box-by-default + `host_access`; per-call-ephemeral + per-session-persistent scratch; advanced read-scoping for the boxed path. Live behavior test 9/9. |

## What Went Well

- **The F1 seam abstraction held across all four flights with zero re-architecture.** `SpawnSpec` was unchanged F1→F4; `_build_tool_profile` (introduced as an F4 hook in F1) was reused verbatim in F2 and F3, and F4 added `_build_boxed_profile` as a *sibling* — not a touch to the host-workspace hook. `BubblewrapSandbox.prepare_spawn` took only additive changes. The Architect's verdict: the seam is genuinely reusable and M15-ready (the `runtime_checkable` `ToolSandbox` Protocol + Windows-forward `SpawnSpec` fields mean a macOS Seatbelt backend slots in by satisfying the Protocol, with no call-site changes).
- **Design-time empirical verification of the load-bearing premise paid off in three of four flights.** F1 (killpg vs SIGKILL, answered by the timeout-kill test), F3 (the orphan window *measured* and found already-mitigated → a standalone leg collapsed into a regression test), and F4 (the minimal-rootfs mount set *run in-container at design time* → discovered Python lives under `/usr/local` and pre-empted a silent breakage). This is the mission's standout methodology win — verify the key feasibility claim against reality at design time, don't trust the spec.
- **Per-leg design review caught a ship-blocking or load-bearing bug before implementation in every flight.** F1 (lazy-import test-patch break), F2 (the `create_pty_session` mock signature — would have shipped red tests), F3 (the `read_file` cross-config keying — a vacuous-pass trap), F4 (function-local `settings` import; `path_denylist=[]`; the BASE_PROMPT exact-equality test break). The "1-cycle approve-with-changes, skip second review" pattern was right every time — findings were self-verifying with file/line citations.
- **`@requires_bwrap` kernel-enforcement tests grew 7 → 14 → 31 and prove real OS enforcement, not argv shape** — host filesystem assertions, real TCP connects, host `pgrep` process-table reads, with sibling-allowed controls proving the boundary is directional. Paired with live behavior tests (agent-safe observables) that exercise the whole agent→tool→seam path.
- **The agent-safe-observable rule (F2) produced zero inconclusive checkpoints in F3 and F4** — a methodology improvement that directly bought clean live-test runs after the F2 network-checkpoint inconclusive taught the lesson.
- **Reviewer-scaled-to-diff-risk** (Sonnet for security-critical sandbox diffs, never Opus) was standardized in F1 and applied every flight.

## What Could Be Improved

- **Operator feedback — too many confirmation points.** The operator wanted *less interruption*: several questions could have been decided with a sensible default and a stated assumption (routine confirmations like "mark completed?", "patch this obvious latent bug now?", "run the planned verification?") rather than a pause. The genuine *product/scope* decisions (the boxed-mode 4-way design interview; HAT-keep-or-skip; accept-vs-tune the over-escalation) were warranted; the routine confirmations were not. **Concrete change (below).** This is the single most actionable process lesson of the mission.
- **Read-scoping was deferred in F1 and never scoped as its own flight *within* the mission.** It was carried as an open item through all four flights; F4 closed it for the boxed path (the higher-value path) almost as a side effect. Had the host-path read-scoping been planned as a dedicated flight mid-mission, the criterion might have fully closed. **Lesson:** when a mission criterion is deferred at the first flight as "needs its own flight," schedule that flight explicitly rather than carrying it as an open item to the end.
- **Behavior-test spec confounds needed post-run fixes twice** — F2 (network step authored around agent cooperation, not an agent-safe observable) and F4 (step-3 conflated a containment check with a selection-judgment check). Both produced the right rule afterward, but both were learned the hard way. **Lesson:** a containment checkpoint and a judgment checkpoint must be separate steps with phrasing that admits exactly one correct outcome — apply at authoring, not after a run.
- **A small set of debts kept being "deferred to end-of-mission maintenance" across all four flights** (the `SandboxError` import-cycle inversion; a few doc/footgun notes). That maintenance pass is now genuinely owed (see Action Items). Carrying the same item through four debriefs is a smell — a mid-mission maintenance checkpoint would have prevented the pile-up.

## Lessons Learned

- **A `prepare_spawn → SpawnSpec` seam with a pure profile-derivation hook generalizes across heterogeneous spawn types** (SDK stdio transport, `create_subprocess_exec`, `pty.fork()`/`execvp`) and across policy variants (host-workspace vs boxed) — keep the policy uniform, let runners stay site-specific, and add profile shapes as sibling builders.
- **bwrap is a per-execution policy dial, not an outer cage.** The same backend serves host-workspace (capable-in-workspace, leakage-prevented) and boxed (no user FS) by varying the profile. True isolation (boxed) is achievable with bwrap binds alone — no overlayfs needed for the *write*+*box-read* properties.
- **Box-by-default's security is the model's adherence, not a guarantee.** Containment is kernel-enforced and solid; the *experienced* default depends on the model not over-escalating `host_access`. This is why an operator enforcement layer (`allow_host_access`) is a distinct necessity from model guidance.
- **Spec-level dispatch beats backend-name dispatch** (`self._wrapped = spec.command == "bwrap"`) — survives backend refactors. Single-locus resource cleanup (`PtySession.close()` owns scratch) beats N-locus.

## Methodology Feedback

- **Calibrate confirmation frequency to the operator (this operator: fewer interruptions).** Reserve `AskUserQuestion` for genuine product/scope/architecture decisions where the answer changes *what* gets built. For routine lifecycle confirmations (mark landed→completed, apply an obvious self-evident bug fix, run the verification the flight already planned), **decide with the sensible default, state the assumption, and proceed** — the operator can reverse it. This is the operator's explicit request and should carry into Mission 15.
- **Codify "design-time empirical verification of the load-bearing DD" into the `/flight` skill.** Three of four flights had the Architect *run* the key feasibility claim at design time (not just reason about it), each pre-empting a mid-flight scramble. The flight-design phase should prompt: "Which single DD, if wrong, breaks the flight? Verify it empirically now." (Mission-control-side improvement.)
- **The agent-safe-observable rule still needs to land in mission-control's `behavior-test/AUTHORING.md`** (cross-repo follow-up open since F2/DD6). It was *applied* on the the-one side; the methodology doc that would prevent the next project re-learning it is still pending.
- **Schedule a mid-mission maintenance checkpoint** when a debrief defers the same debt item twice — don't let it ride to the end.
- The mission/flight/leg hierarchy + batched `/agentic-workflow` + per-leg design review + single Phase-2d code review worked well for a security-critical, multi-flight refactor; no structural change recommended.

## Action Items

- [ ] **End-of-mission maintenance (now owed)** — run `/routine-maintenance`: resolve the `SandboxError` import-cycle inversion out of `mcp/errors.py` (F1 DD8, deferred all mission; **blocks clean M15 backend errors**); add the non-merged-usr `--symlink` portability caveat + the `_build_boxed_profile` "network unconditionally off" note to `SECURITY-MODEL.md`; add the `_TOOL_CLASSES` cross-config note, the fork-safety convention, the `@requires_bwrap` workspace-under-`$HOME` constraint, and the PTY-echo sentinel footgun to `agents.md`/`CLAUDE.md`; investigate the pre-existing `test_connectors_e2e.py::test_e2e_full_lifecycle` flake.
- [ ] **Successor flight — host-workspace read-scoping** (the one unmet criterion): `ldd`-derived bind set or overlay-namespace; its own behavior test for "cannot read outside scope." Its own flight/mission, not maintenance.
- [ ] **Successor flight — operator `allow_host_access` control**: `ExecutionConfig.allow_host_access: bool = True`; tool `execute()` forces `host_access=False` when disabled; tool-config UI surface. The enforcement backstop for box-by-default; a flight (changes the tool contract + UI), not maintenance.
- [ ] **Cheap forward-proofing for M15**: add a `network_allowed: bool = False` param to `_build_boxed_profile` (decouples a future boxed-network profile from a code change); add a `@requires_bwrap` reaper-path boxed-session cleanup test.
- [ ] **Cross-repo (mission-control)**: land the agent-safe-observable rule in `.claude/skills/behavior-test/AUTHORING.md`; consider codifying "design-time empirical verification of the load-bearing DD" in the `/flight` skill.
- [ ] Cleanup (optional): the `sandbox-test` agent + `/root/.box_test_canary` + `~/.ssh` fixtures left on the running instance for behavior-test re-runs.
