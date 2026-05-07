# Flight Debrief: Local MCP Sandbox — Adapter Contract + Bubblewrap Linux Backend

**Date**: 2026-05-06
**Flight**: [Local MCP Sandbox](flight.md)
**Status**: landed
**Duration**: 2026-05-06 (single-day execution under `/agentic-workflow`)
**Legs Completed**: 8 of 9 (L6 HAT skipped per user; L5c styling polish added post-batch)

## Outcome Assessment

### Objectives Achieved

The flight delivered the OS-level sandbox layer that wraps F2's stdio MCP transport. Every locally-spawned MCP server process now runs inside `bwrap` with strict-by-default filesystem scope (`--ro-bind / /` + per-`writable_paths` `--bind PATH PATH`), operator-controlled network policy (`--unshare-net` unless `network_allowed=true`), env-allowlist enforcement (`_build_subprocess_env`'s 8-key host filter + bwrap `--clearenv` defense-in-depth), HOME-override sandbox-policy (`/tmp`), and process-supervision (`--die-with-parent`).

The cross-platform-ready `MCPSandbox` Protocol with `prepare_spawn(profile, command, args, env, cwd) -> SpawnSpec` shape (including Windows-only `creation_flags`/`attribute_list` fields) ships as a contract that future macOS `sandbox-exec` and Windows `AppContainer` backends can satisfy without rewriting the surface.

The L5b operator UI (Sandbox sub-section in the stdio MCP source editor with iOS-toggle for `network_allowed` + chip-list for `writable_paths`, plus L5c styling polish) makes the sandbox profile first-class operator surface area.

L6 HAT (real third-party MCP walkthrough) was skipped at user direction — the argument was that real-MCP HAT mostly proves operator-owns-pip-install (matching ecosystem norm) rather than F3-specific semantics already covered by L5a's 10 real-subprocess integration tests.

### Mission Criteria Advanced

The flight directly advanced mission criterion #4 ("Locally spawned MCP server processes run inside an OS-level sandbox with a fixed environment allowlist, no inherited host secrets, and a clear extension seam for additional platform backends; the implementation is verified on Linux against a reference local MCP server") and contributed to criterion #11 ("Each layer of the integration has automated coverage proving its contract — the encrypted persistence layer, the client-side connection lifecycle for both transports, the sandbox spawn path, the idle-TTL reaper, the resolver's substitution behavior on MCP-shaped overrides, the tool-name-spacing logic, and the inspector's tool-list / tool-call round-trip" — F3 contributes the sandbox spawn path).

The criterion checkboxes at the top of `flight.md` remain unticked because the criteria are mission-level: criterion #4's "verified on Linux against a reference local MCP server" is partially covered by L5a's FastMCP integration tests but the L6 HAT against a real third-party server (which is what the criterion's "reference local MCP server" implied) was skipped. F4 (idle-TTL reaper) needs to land before criterion #4 is fully met.

## What Went Well

**Phase 1b reconnaissance flowed verbatim into implementation.** The capability matrix gathered during reconnaissance (bubblewrap / sandbox-exec / AppContainer × env-allowlist / FS scope / network policy / process supervision, with citations) ported directly into L2's `base.py` module docstring. Same for the live-environment baselines (CapBnd dump, `unshare -U` EPERM verification) feeding the §10 privilege model. **Pattern worth standardizing**: when reconnaissance produces structured artifacts, port them verbatim rather than re-derive in implementation.

**Hard-gate-first leg ordering.** L1a as a probe-only hard gate (Dockerfile + docker-compose only, 5-assertion bash probe, NO code legs proceeding until probe green) prevented the failure mode "discover bwrap doesn't work mid-L4 and have to unwind." All 5 probe assertions passed first try after the §10 docker-compose privilege grants landed. **Pattern worth standardizing**: any flight that depends on environmental capabilities should pre-establish a hard-gate probe leg before code-touching legs.

**The cycle-1 architect coordinated cross-leg findings.** Four cycle-1 high-severity issues all touched cross-leg surfaces: L4-breaks-F2-fixtures, §10-must-commit-before-L1, cwd-handling-explicit, Protocol-shape-build_argv-vs-prepare_spawn (affecting L2+L3+L4 simultaneously). Single-leg-surface reviews (L1b, L2, L3, L5a, L5b) each got 0-1 cycle reviews with mostly low-severity findings. **The leading indicator of leg-design risk is cross-leg coordination, not single-leg complexity.**

**Forward-compat Protocol shape paid for itself.** The cycle-1 refactor from `build_argv() -> (cmd, args, env)` triple to `prepare_spawn() -> SpawnSpec` dataclass with Windows-only `creation_flags`/`attribute_list` cost ~10 LOC and zero runtime overhead on Linux. Saves a Protocol-rewrite migration when a future Windows AppContainer mission lands.

**Strict-by-default profile required no F2 test modifications.** L4 wired `connect_stdio` to apply the strict-floor `SandboxProfile.from_dict({})` to F2's existing 14 stdio integration tests. The hypothesis was that strict-floor would suffice for FastMCP's hello fixture (no FS writes, no network); reality matched. Zero per-test profile customization needed. Strong validation of "secure default is also the convenient default."

**Layered test coverage with no major redundancy.** L2 contract → L3 argv compilation → L4 mocked transport → L5a real-subprocess integration is a clean ladder. L3's argv tests prove emission shape; L5a's real-subprocess tests prove OS-level enforcement. L4's mocked tests focus on `connect_stdio`'s decision logic (sandbox vs bypass). 63 new tests across the layers; the only deliberate small overlap is L4's single `/bin/cat` real-subprocess test that verifies the bwrap boundary is crossed.

**Verbatim-message-equality test for the error catalog.** L3's `assert str(exc_info.value) == _BWRAP_NOT_FOUND_MSG` locks the §6 catalog message as a regression invariant against future text drift. **Pattern worth standardizing** whenever a design decision specifies an error-message catalog.

**Architecture patterns crystallized**: canonical-import + convenience-re-export for cross-package errors (`MCPSandboxError` canonical at `the_one/mcp/errors.py`, re-exported from `the_one/platform/sandbox/__init__.py`); structural-not-subclassing Protocol satisfaction (`BubblewrapSandbox` does NOT inherit from `MCPSandbox`, satisfies via `@runtime_checkable`); flat-kebab `data-field` convention in editor JS (`sandbox-network-allowed`, `sandbox-writable-paths`); opt-in test-fixture extension via CLI flag (`--with-naughty-tools` preserves F2 regression naturally).

## What Could Be Improved

### Process

- **Leg-design final-pass test-count reconciliation.** L4's leg artifact had three different test-count numbers in three sections (`Objective: ~6`, `Outputs: ~7`, `Acceptance Criteria: ~9`). Section-by-section authoring without a reconciliation pass — cycle-2 polish refined Outputs and Acceptance independently without backporting to Objective. Final landed count was 9, but Objective shipped wrong. **Recommendation**: add `grep -E "~[0-9]+ tests"` reconciliation to the leg-design closing checklist (`/leg` skill).

- **Leg-design must trace integration-point code paths line-by-line for non-textual form inputs.** L5b's two cycle-1 high-severity issues (cancel-revert + dirty-tracking checkbox handling) came from a leg sketch that assumed `revertEditorToSource` and `getFormSnapshot` were generic when they actually used explicit per-field whitelists AND read `el.value` (no-op for checkboxes). **Recommendation**: when a leg adds a non-textual form input (checkbox, radio, multi-select, file) to an existing edit form, leg-design MUST trace the dirty-tracking + cancel-revert code paths line-by-line. Text inputs hide the asymmetry.

- **Error-catalog design decisions need a discrimination-mechanism specifier.** Anomaly A02 traces to §6: the spec listed four canonical error messages (bwrap missing, writable_paths nonexistent, bwrap exited code N, EPERM on unshare) without specifying HOW `connect_stdio` discriminates among them in `stdio_client`'s error paths. Cycle-1/cycle-2 architect cycles polished message wording but didn't pressure-test "how does the implementation pick which message?" **Recommendation**: when a design decision lists a catalog of error messages, the spec MUST also specify the source-of-truth signal that picks among them (stderr regex? exit code? exception type?).

- **Layered-filesystem-semantics design decisions need argv-ordering invariants.** Anomaly A03 traces to §2 + Technical Approach: `--bind PATH` and `--tmpfs /tmp` were listed as two bullets in the same flag enumeration without analyzing that `--bind /tmp/foo` is silently shadowed by a later `--tmpfs /tmp`. **Recommendation**: when a flight design depends on argv-order-dependent layered filesystem (or any layered) semantics, specify ordering explicitly with rationale, OR defer to leg design with an explicit probe.

- **Adaptation Criteria non-triggering should be documented as a positive signal.** §Adaptation Criteria included a co-fixture fallback ("`mcp_fixture_stdio_params_sandboxed` if updating `mcp_fixture_stdio_params` breaks more F2 tests than expected"). The fallback was never triggered — strict-floor sufficed naturally. **Recommendation**: when an adaptation criterion isn't triggered, that's a positive design signal — document the non-triggering in the flight log so future debriefs can refine the prediction.

### Technical

- **A02 (deferred bwrap-side error translation)** is operational debt: three of the four §6-cataloged `MCPSandboxError` messages are unreachable code today. Operators encountering bwrap-side post-setup failures see `MCPConnectionError` from F2's existing translation. Severity: cosmetic (correctness preserved). **Resolution path**: stderr-scraping or bwrap exit-code inspection inside `connect_stdio` — fits F4's scope (F4 touches the same `connect_stdio` path for the AsyncExitStack refactor).

- **A03 (argv ordering: `--bind` before `--tmpfs /tmp`)** is correctness debt for a documented use case. Spec promises "MCPs writing large temp files should add `/tmp` to writable_paths to host-bind-mount it" — silently doesn't work. Severity: low (workaround is `/var/tmp`); higher if anyone reads the spec literally. **Resolution path**: single-block argv reorder in `bubblewrap.py:107-112` (move `--tmpfs /tmp` before the `--bind` loop). Trivial fix; carry into F4.

- **Dead-code fixture: `mcp_fixture_sandbox_profile`.** Added in L4 per spec as forward-looking for L5a; L5a constructed `MCPSource` directly without using it. **Recommendation**: F4 should either find a consumer or delete it.

- **Namespace flags lack end-to-end coverage.** L3 unit-tests `pid_unshare=False` argv emission; no integration test exercises a `pid_unshare=False` config.sandbox round-trip. The "JSON-edit-only via API" advanced-use case isn't proven end-to-end. Low priority.

- **No structured-logging emission from sandbox setup failures.** `BubblewrapSandbox.__init__` raises silently; `SandboxProfile.from_dict` debug-logs unknown keys but nothing else. Operator observability is purely error-message-driven. Worth a routine-maintenance pass to add structured logs at the same boundary points.

### Documentation

- **`agents.md` lacks a `### the_one/platform/` section pointer** for the new sandbox sub-package. L2's leg-design noted this and explicitly deferred to routine maintenance ("don't fabricate one"). Worth picking up now that there's enough mass in `platform/` (env, pty, sandbox).

- **CLAUDE.md F3 contracts §5 needs an A02 caveat.** Three of the four cataloged `MCPSandboxError` messages are currently unreachable code. Future readers expecting them will be misled. **Recommendation**: add "messages 2-4 surface as `MCPConnectionError` until A02 is resolved" to the §5 entry.

- **L5b operator UI lacks help-text for the `/tmp` shadowing edge case.** The chip-list lets operators add `/tmp/anything` paths that will silently be shadowed by `--tmpfs /tmp`. Until A03 is fixed, a one-line help-text near the chip-list ("Paths under `/tmp` are not persisted; use `/var/tmp` or another mount.") would reduce operator confusion.

- **F2's `the_one/mcp/README.md`** (originally an F2-debrief item, removed from F3 scope per Architect feedback) is still missing. Now that F3 has expanded the surface (sandbox layer, sandbox sub-section in the editor, sandbox profile schema), the README would be more useful than at F3 design time.

- **"Trust the runtime" pattern** spans F1, L1b, and L3. Worth promoting to a named pattern in `agents.md` since reviewers will keep encountering it.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| §6 error catalog partially deferred (A02) | Spec didn't specify how `connect_stdio` discriminates between bwrap-side and target-side failures inside `stdio_client`'s error paths | Yes — flight-design must specify discrimination mechanism whenever an error catalog is part of a design decision |
| §2 `/tmp` writable-path silently shadowed by `--tmpfs` (A03) | Spec listed bwrap flags as bullets without analyzing argv-order dependencies | Yes — flight-design must specify argv-ordering invariants OR defer to a leg-design probe |
| L5c styling polish leg added post-flight-commit | Visual inconsistency surfaced after browser tests passed but operator review caught it (toggle-switch UX + chip-list wrapper styling) | Yes — operator-review on UI-touching legs catches what browser tests don't (visual quality) |
| `register_naughty_tools` opt-in helper + `--with-naughty-tools` CLI flag (vs. always-registered tools) | Implementation refinement to preserve F2 regression naturally — F2 tests don't pass the flag, so naughty tools never appear in their tool list | Yes — opt-in fixture extension via CLI flag is a clean pattern for "enable test-only behaviour without touching the production code path" |
| Hard-gate-then-implement L1a ordering | Cycle-1 architect insistence to commit §10 BEFORE any code legs (not "decide and probe in L1") | Yes — already covered above |
| Dropped HAT for L6 | Real-MCP HAT mostly proves operator-owns-pip-install (matches ecosystem norm) rather than F3-specific semantics already covered by L5a integration tests | Per-mission decision; should defer to mission-debrief whether HATs against third-party software are worth running |
| Forward-compat Windows-only fields on `SpawnSpec` | Cycle-1 architect refactor from `build_argv()` triple to `prepare_spawn()` dataclass to avoid Protocol-rewrite migration on future Windows AppContainer mission | Yes — additive growth doesn't break consumers; the asymmetric cost ratio (10 LOC vs whole-leg of contract churn) justifies the forward-compat shape |
| Cross-leg flat-kebab `data-field` convention | L5b reused existing OAuth/args convention (`oauth-issuer-url`, `oauth-scopes`, `args`) rather than introducing dotted paths (`sandbox.network_allowed`) | Yes — flat-kebab convention is consistent with the codebase; future UI legs should match |

## Key Learnings

1. **Cross-leg coordination findings are the leading indicator of leg-design risk.** Cycle-1 architect's 4 high-severity issues all touched cross-leg surfaces (L4-fixtures, §10 timing, cwd handling, Protocol shape). Single-leg-surface reviews ran clean. Future flight design should pressure-test cross-leg integration BEFORE polishing per-leg detail.

2. **Reconnaissance-as-design-input is high ROI when artifacts are structured.** Phase 1b's capability matrix flowed verbatim into L2's `base.py` docstring; the live-environment baselines flowed verbatim into §10's privilege model. Less time re-deriving in implementation, fewer drift opportunities. Generalizable to any flight where the design-input set has authoritative external sources (man pages, vendor docs, published references).

3. **Strict-by-default + cross-platform-ready Protocol survives the most pressure tests.** `--ro-bind / /` + empty `writable_paths` + `--unshare-net` worked for F2's 14 stdio integration tests with zero per-test customization. The Windows-only `creation_flags`/`attribute_list` fields cost ~10 LOC for a multi-mission migration savings. Both choices vindicate the principle: lock the strictest plausible default and shape the contract for the broadest plausible consumers.

4. **Leg-design pre-splits (L1 → L1a + L1b; L5 → L5a + L5b) reflect blast-radius isolation, not just complexity.** L1a (Dockerfile + docker-compose, hard-gate probe) is a different blast radius from L1b (validator + docs). L5a (Python integration with real bwrap) needs a different reviewer skill set from L5b (DOM/playwright). When in doubt, splitting earlier is cheaper than discovering during implementation that two surfaces shouldn't have shared a leg.

5. **Operator-review catches what browser tests don't.** L5b's 11 browser tests passed cleanly; the human reviewer caught visual inconsistencies (checkbox should be a toggle switch in the second column; chip-list wrapper unstyled) that prompted L5c. Browser tests verify behavioral correctness; visual quality requires human review. Worth scheduling a human-review pass on UI-touching legs before flight-commit.

6. **Skipping HATs against third-party software is acceptable when integration coverage is comprehensive.** L6 was structured as a 5-step verification against a real third-party MCP server. The user's argument for skipping (most of what would be tested is operator-owns-pip-install, not F3-specific semantics) was correct — L5a's 10 integration tests against the FastMCP fixture cover the F3-specific surface (FS refusal, env-allowlist, network policy, opt-in directionality). The HAT would have validated ecosystem-compatibility (does mcp-server-fetch actually work?), not F3-correctness.

7. **The install affordance gap is a real product question.** Operators currently `pip install` MCP servers themselves (matching Claude Code / Cline / Cursor / Claude Desktop). The flight didn't probe whether the-one should ship an installer surface. Worth raising explicitly at mission-debrief so the trade-off is owned, not just deferred-by-convention.

## Recommendations

1. **F4 should bundle A02 + A03 fixes** (bwrap-side error translation + argv reorder). Both touch `connect_stdio` and `bubblewrap.py`; F4 already plans to refactor `connect_stdio` for the AsyncExitStack disconnect cleanup. Cleaner to fix all three together than carve a separate routine-maintenance pass.

2. **Update the `/leg` skill with a closing reconciliation pass.** Specifically: grep for `~[0-9]+ tests` across the leg artifact and reconcile any drift; verify acceptance-criteria-test-count matches outputs-test-count matches objective-test-count. Catches the L4 root cause without relying on cycle-1/cycle-2 reviewers to spot it.

3. **Update the `/flight` skill with two new design-decision integrity checks.** (a) When a design decision specifies an error-message catalog, the spec must also identify the discrimination signal (stderr regex / exit code / exception type) that picks among messages. (b) When a design decision depends on argv-order-dependent layered semantics (filesystem, env, network), specify the order explicitly with rationale OR defer to a leg-design probe.

4. **Update the `/agentic-workflow` leg-design phase prompt** to add: "When a leg adds a non-textual form input (checkbox, radio, multi-select, file) to an existing edit form, trace the dirty-tracking + cancel-revert code paths line-by-line — text inputs hide asymmetries (`el.value` vs `el.checked`, generic vs whitelist-keyed snapshot)." Catches the L5b root cause.

5. **Promote four patterns to named conventions in `agents.md`**: (a) trust-the-runtime validation (shape at API, semantics at runtime), (b) canonical-import + convenience-re-export for cross-package errors, (c) structural-not-subclassing Protocol satisfaction with `@runtime_checkable`, (d) verbatim-message-equality test for cataloged error strings. All four span F1/F2/F3 already; documenting them named makes future legs pattern-match instead of re-derive.

## Action Items

### Immediate (block F4 or routine-maintenance pass)
- [ ] **A02**: Wrap `stdio_client` failure path in `connect_stdio` with bwrap-stderr inspection / exit-code translation to emit §6 messages 2-4. Bundle with F4's AsyncExitStack refactor.
- [ ] **A03**: Reorder bwrap argv in `the_one/platform/sandbox/bubblewrap.py` so `--tmpfs /tmp` precedes the `--bind` loop. Update L3's argv-ordering tests to lock the new invariant.
- [ ] **Update L5a Test #6** (`test_sandbox_writable_paths_nonexistent_raises_at_connect`) to expect `MCPSandboxError` once A02 lands. Currently locks the deferred-translation gap as a positive test.

### Near-term (mission-debrief or routine-maintenance)
- [ ] Add `### the_one/platform/` section pointer to `the_one/agents.md` for the sandbox sub-package.
- [ ] Add A02 caveat to CLAUDE.md F3 contracts §5 ("messages 2-4 surface as `MCPConnectionError` until A02 is resolved").
- [ ] Add help-text near the L5b chip-list ("Paths under `/tmp` are not persisted; use `/var/tmp` or another mount.") until A03 fixed.
- [ ] Decide at mission-debrief: should the-one ship an installer surface for MCP servers, or accept the ecosystem norm (operator-owned `pip install`)?
- [ ] Write `the_one/mcp/README.md` (carried from F2 debrief; F3 expanded the surface).
- [ ] F4 leg-design: decide whether to keep or delete `mcp_fixture_sandbox_profile` (currently dead code).

### Methodology improvements (mission-control side)
- [ ] **`/leg` skill**: add reconciliation grep for test counts at end of leg-design.
- [ ] **`/flight` skill**: add discrimination-mechanism check for error-catalog design decisions.
- [ ] **`/flight` skill**: add argv-ordering / layered-semantics check.
- [ ] **`/agentic-workflow` leg-design phase prompt**: add "trace dirty-tracking + cancel-revert paths" check for non-textual form inputs.
- [ ] Promote four named patterns (trust-the-runtime, canonical-import + convenience-re-export, structural-Protocol-satisfaction, verbatim-message-equality) to `agents.md`.
