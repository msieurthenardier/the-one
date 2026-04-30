# Flight Debrief: Execution Expansion & Constraints

**Date**: 2026-04-30
**Flight**: [Execution Expansion & Constraints](flight.md)
**Status**: completed
**Duration**: 2026-04-29 (start of L1a) — 2026-04-30 (auto-reload follow-up landed)
**Legs Completed**: 10 of 10 (8 autonomous + 1 HAT + 1 integration verification)

## Outcome Assessment

### Objectives Achieved

The flight delivered the full F4 surface as designed:

- **`ExecutionConfig`** with six Narrow/NarrowSuperset fields, `default ≤ max` cross-field validator, frozen.
- **Migrated execution tools** — `ShellTool` → `ExecutionConfig`, `PythonExecTool` → `PythonExecConfig` (90s default subclass). Three-clause try/except envelope (`ConstraintError → asyncio.TimeoutError → Exception`) standardized.
- **Four PTY session tools** — `shell_session_start/send/close/list`. Per-explicit-handle session addressing. Per-call denylist on `_send`.
- **Platform layer** — `the_one/platform/env.py` (env allowlist) + `the_one/platform/pty.py` (`PtySession` ABC + `UnixPtySession` with fork-then-execvp). Windows ConPTY explicitly deferred.
- **Session registry** — `the_one/tools/_session_registry.py` keyed on `(agent_name, session_id)`. Idle reaper as FastAPI-lifespan-bound `asyncio.Task`. Two-phase lock-and-await close pattern.
- **Cross-Config dispatch** — `Tool.Requires`, `cross_configs` per-call dict, `agent_name` plumbed `AgentFactory → BuiltinToolProvider → Tool`. `FilesystemConfig` retroactively frozen.
- **`ConstraintError`** moved to `the_one/tools/base.py` next to the `Tool` ABC, with backward-compat re-export.
- **17 tools** registered (was 13).
- **Documentation refreshed** — `agents.md`, `CLAUDE.md`, mission Known Issues.

### Mission Criteria Advanced

This flight contributed to all five mission success criteria scoped for F4:

| Criterion | Status |
|---|---|
| Execution tooling supports one-shot + interactive multi-command sessions, isolated per-agent | ✓ shipped |
| Hardcoded subprocess env allowlist at all 3 execution call sites | ✓ verified by HAT scenario 5 + unit tests |
| Tool-level + agent-level constraint narrowing (output, timeout, cwd for execution) | ✓ shipped |
| Automated coverage for happy-path + every constraint type per kept tool | ✓ ~150+ net new tests |
| Cross-platform-ready architecture (`PtySession` ABC, Windows ConPTY deferred behind import-time guard) | ✓ shipped |

## What Went Well

**Design quality at flight-design time was high.** Architect's two-round review (one deep, one validation pass) caught all structural issues before legs started. Round 2 surfaced only stale-text inconsistencies — none of the 11 design decisions had to be reversed during implementation.

**The L1a/L1b split was the right call.** Per Decision 8, separating the mechanical `ConstraintError` move from the architectural `cross_configs` plumbing kept each leg reviewable. L1a was ~30 LoC; L1b was ~120 LoC + tests. Bundling would have made the architectural change opaque under the move's noise.

**Pre-flight bind-mount maintenance commit removed `docker cp` overhead.** Pre-existing F3 friction was eliminated before F4 implementation legs started. Mid-flight `tests/` bind-mount extension (between L1b and L2) was a foreseeable miss in the pre-flight scope, but trivially recoverable.

**Two-phase lock-and-await pattern in `_session_registry`.** Snapshot under `_lock`, release lock, then `await session.close()`. This pattern ships in three places (`close`, `_reap_once`, `_reap_loop` cancel-handler) and is the central correctness invariant for the registry. The Reviewer's HIGH-severity catch on the original L5b spec (which would have held the lock across `~1s` SIGTERM/SIGKILL ladder) prevented a real deadlock pattern from shipping.

**The HAT was a force multiplier.** All 10 HAT scenarios passed cleanly with no inline fixes to error wording. The HAT also surfaced two genuine integration findings:
1. **Uvicorn import-cache anomaly** — the timeout cap clip from L3-L4 was not engaging through the chat API until container restart. Documented in flight-log Anomalies. Resolved via `--reload` follow-up.
2. **Pre-existing WebSocket blocking pattern** — surfaced because F4's 120s timeout cap turned previously-unbounded sleeps into deterministic 2-minute UI hangs.

**Post-HAT WebSocket fixes were well-bounded.** Three commits (`d10d0c5`, `2563d37`, `105ce35`) addressed each part of the WS UX bug. Each had a clear regression test. The fixes ride the F4 branch because the operator was already in the area; the underlying issues are pre-existing (`_process_and_broadcast` traces back to commit `09bd91f`).

## What Could Be Improved

### Process

**Leg-spec contradictions slipped through twice.** Both L3 and L4 leg specs gave the float-preserving timeout clip as both `if clipped < 1: clipped = 1` AND "agent passing `timeout=0.5` stays `0.5`". Internally contradictory. Both developers correctly chose the F2-contract-preserving variant, but the spec should have been corrected after L3 surfaced it — L4 inheriting the same trap was avoidable.

**Recommendation**: when a leg-design review surfaces an internal contradiction in spec wording, propagate the correction to all downstream leg specs that copy the pattern. Treat leg specs as a family, not in isolation.

**L2 shipped a helper without exercising it through a real consumer.** `_truncate_output` was specified to concatenate raw bytes (`stdout + stderr`); L3 then had to refine it to insert `\n[stderr]\n` between streams (the F1 test contract required it). The gap was that L2 tested helpers in isolation, not through a shell-tool call.

**Recommendation**: scaffolding legs (helpers ahead of consumers) should ship at least one consumer-facing test that exercises the helper end-to-end through a stub tool, not just isolated helper tests. OR: helpers should land **with** their first consumer in a single leg.

**L4 hit Pydantic v2's `json_schema_extra` non-inheritance gap.** Re-declaring `timeout_seconds_default` on `PythonExecConfig` without `json_schema_extra` lost `ui_choices`. Developer correctly hoisted to a module-level constant, but this was discovered, not specified.

**Recommendation**: add a CLAUDE.md callout: "Pydantic v2 does NOT inherit `json_schema_extra` on `Annotated` field re-declaration; hoist shared metadata to module-level constants when subclassing Configs."

### Technical

**Three documented-and-bounded pieces of technical debt:**

1. **`max_concurrent_sessions` race** (`the_one/tools/sessions.py:120-126`) — `(count_for_agent, register)` is non-atomic. Accepted for F4 (small-model agents don't pipeline). HAT scenario 8 confirmed the asyncio `_lock` serialization holds in practice. **Escape hatch**: a `register_if_under_cap()` registry helper at F6+ if the HTTP API exposes parallel agent invocations.

2. **`command_denylist` resolver default-factory limitation** (`tests/test_execution_config.py::TestResolverDefaultFactoryFallback`) — when `tool_config={}` AND agent override sets `command_denylist`, the resolver hits `NotImplementedError` because `field_info.default` is `PydanticUndefined` for default-factory fields. Real-world impact is low (operators setting agent-level overrides typically also set tool-level rows). **Asymmetry to watch**: F5/F6 NarrowSuperset on similarly-defaulted fields.

3. **`Requires` is documentation-only** in L1b — provider passes the full `cross_configs` dict regardless. This was the right F4 call (no security boundary at dispatch; tools self-select), but the F5 `download_file` forward-reference (flight.md:266) needs a clarifying sentence: `Requires` is *declarative metadata*, not enforced injection. **Revisit when MCP integration arrives** — MCP servers crossing trust boundaries may want enforced gating.

**`python_exec` exit-code-suffix behavior change** (L4) — F4 aligned PythonExecTool to append `[exit code: N]` for non-zero rc via `_truncate_output`. F2's `test_nonzero_exit_no_exit_code_suffix` was deliberately flipped. This is a contract change visible to agents and to any prompts that referenced the old shape. **Should be flagged in mission Known Issues** — currently isn't.

### Documentation

- **"PTY testing patterns"** belongs in CLAUDE.md — `stty -echo` to suppress PTY echo before timeout-on-empty-buffer tests; idle-mark vs prompt-regex trade-offs.
- **Cross-Config dispatch "first-tool-wins" semantics** is in flight-log notes only; should be in `the_one/tools/builtins.py` docstring at the dispatch site.
- **Float-preserving timeout clip idiom** (`if clipped <= 0: clipped = 1`, NOT `max(1, min(...))`) deserves a short section in CLAUDE.md's tool-authorship contract.
- **Snapshot-under-lock / close-after-release** is the central registry pattern — worth a one-paragraph "async lock idiom" doc.

### Coverage Gaps

- **Real-PTY drain in lifespan** was deferred from L5b to L8, but L8 was verification + docs only. **No real-PTY drain test was added.** Only the HAT happy-path exercised PTY through the full stack with lifespan teardown.
- **Reaper-vs-shutdown race** is covered in code (belt-and-suspenders direct drain after cancel) but no test forces "session expires same tick reaper is cancelled."
- **`max_concurrent_sessions` race** (documented debt) is not unit-exercised; HAT scenario 8 ran serial-enough that the lock held trivially.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| `_truncate_output` refined in L3 to insert `[stderr]` marker | L2 spec gap; F1 test contract required marker | Yes — scaffolding legs ship a consumer-facing test |
| `_TIMEOUT_DEFAULT_UI_CHOICES` hoisted to module constant in L4 | Pydantic v2 doesn't inherit `json_schema_extra` | Yes — document in CLAUDE.md |
| Env helpers moved from `tools/execution.py` to `platform/env.py` in L5a | `platform → tools` reverse dep would be smell | Yes — platform-layer primitives consumed by tools live in `platform/`, with re-exports in `tools/` only when needed for migration |
| `bash`/`zsh`-only `-i` flag in `UnixPtySession.start` | `dash -i` emits "can't access tty" warning | Yes — gate `-i` on shell basename |
| `tests/_pty_fixtures.py` shared module | Cross-test-module imports are fragile under pytest collection | Yes — promote shared fixtures to non-test module, not `tests/test_*.py` |
| Three-clause envelope on execution tools | F2 wording (`"Command timed out after Ns"`) preserved by existing test | Yes — standardize three-clause for tools with deadlines |
| `tests/` bind-mount added mid-flight (between L1b and L2) | Pre-flight only mounted `the_one/` | Yes — bind-mount source AND tests in pre-flight |
| Container restart required after L3-L6 to clear uvicorn cache | Pre-fix workaround | No — superseded by `--reload` (commit `a41789a`) |

## Key Learnings

**HAT scope should explicitly include "operator-driven multi-tab/multi-session flows during in-flight tool execution"** for any flight that touches the WebSocket surface or long-running tool calls. The L7 HAT covered constraint enforcement (which all passed cleanly) but did not cover concurrent UX flows. The three post-HAT WebSocket fixes all required the operator to manually exercise these flows. The bugs were pre-existing, but the timeout cap made them deterministic — exactly the kind of UX exposure HAT should catch.

**Mission-level Known Issues should treat "exposed-by-this-mission" as a first-class category, separate from "introduced-by-this-mission".** F4's WebSocket bugs were pre-existing; F4's 120s timeout cap made them deterministic. The mission Known Issue (now resolved) captures both lineage and resolution. Future missions should adopt this distinction.

**Scaffolding legs need consumer-facing tests.** L2 helper tested in isolation; L3 had to refine the helper. The pattern recurs whenever a scaffolding leg lands ahead of its first consumer.

**The `--reload` follow-up should have been pre-flight maintenance, not post-flight.** The uvicorn cache problem is foreseeable for any flight that modifies tool source under a long-running uvicorn worker. Future missions should verify "are dev-loop friction primitives (bind-mounts, auto-reload) wired?" as a `routine-maintenance` check before flights start.

**The cross-Config dispatch shape is MCP-ready.** When MCP integration arrives, the same `Requires` + provider-built `cross_configs` view is the natural fit. Document the F4 shape in `agents.md`'s tool-architecture section as the canonical pattern.

## Recommendations

1. **Add a "Tool authorship contract" section to CLAUDE.md** covering: three-clause envelope (with timeout wording divergence note), float-preserving timeout clip idiom, two-phase lock-and-await for any registry-style state, `json_schema_extra` non-inheritance on Pydantic Config subclassing, frozen Configs for cross-tool sharing.

2. **Tighten the `routine-maintenance` skill's pre-mission check** to verify dev-loop friction primitives (source bind-mount, tests bind-mount, uvicorn `--reload`) are wired. Catches the L7 anomaly class before HAT.

3. **Update HAT rubric in the flight skill** to require "operator-driven multi-tab/multi-session flows during in-flight tool execution" for any flight that touches WebSocket lifecycle or introduces long-running tool semantics.

4. **Add the deferred maintenance items to a tracked list** (post-F4):
   - `_filesystem_check_*` helper unification (deferred from L1 per Decision 8 — sharper now that `_cwd_check` adds a 6th call site).
   - Real-PTY lifespan-drain test (deferred from L5b to L8, never landed).
   - `python_exec` exit-code-suffix behavior change → mission Known Issues.

5. **Mark the cross-Config dispatch shape canonical in `agents.md`** — `Requires = (FilesystemConfig,)` declaration + `self._cross_configs[FilesystemConfig]` consumption — as the pattern future flights and MCP integration should follow.

## Action Items

- [ ] Promote post-flight tracked maintenance items to a maintenance leg or `/routine-maintenance` pass before F5 starts.
- [ ] Add `python_exec` exit-code-suffix behavior change to mission Known Issues.
- [ ] Document scaffolding-leg consumer-facing test requirement in the `/leg` skill prompt.
- [ ] Update the `/flight` skill prompt to include WebSocket/long-running HAT scenarios when relevant.
- [ ] Update the `/routine-maintenance` skill to check dev-loop friction primitives before mission start.
- [ ] Mark the cross-Config dispatch shape canonical in `agents.md` for MCP forward-reference.
