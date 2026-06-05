# Mission Debrief: Maintenance (Post-M11)

**Date**: 2026-06-05
**Mission**: [Maintenance (Post-M11)](mission.md)
**Status**: completed
**Duration**: 2026-06-04 – 2026-06-05
**Flights Completed**: 6 of 6 (all landed + merged; PRs #88, #89, #90, #91, #92, #95, plus the test-infra fix #96)

## Outcome Assessment

### Success Criteria Results
| Criterion | Status | Notes |
|-----------|--------|-------|
| D1 — runtime CVEs patched, lockfile regenerated, suite green | **Met** | aiohttp/idna/starlette (runtime) + urllib3 (toolchain) bumped via explicit `pyproject.toml` floors — the mechanism that actually governs the image build. urllib3 reclassified runtime→toolchain at design review. |
| Q1 — pre-commit AND CI gate fail on ruff violations; clean on `main` | **Met** | `.pre-commit-config.yaml` + `.github/workflows/lint.yml`, all pinned to ruff 0.15.15. CI green on every flight PR and on `main`. The mission centerpiece. |
| T2 — broad-except narrowed, programming errors propagate, noqa removed | **Met** | Split into typed `except ConnectorClientError` (records) + `except Exception` (logs w/ account_id, re-raises, no record). |
| T1 — ephemeral-followup non-401 maps to typed error | **Met** | Now `raise ConnectorConnectionError(...) from exc`, matching the channel ladder. |
| Q2 — `ConnectorAuthRequired` raised or removed | **Met (removed)** | Deleted — investigation found no caller branches on connector error subtype; wiring would have left it dead-in-practice. |
| A2 — keyboard-operable routing-rule reorder | **Met** | Focusable handle + arrow keys, focus retained, position/boundary announced. Operator chose this over move-buttons. |
| A3 — named attach toggle | **Met** | `aria-label="Attach <name>"`. |
| A1 — live-status announced to SR | **Met** | `aria-live="polite"` on the text span, `role="alert"` on the error wrap. |
| A4/A5 — presence controls labeled; section titles are headings | **Met (A5 scoped)** | A5 applied to the connector editor (10 `<h2>`); app-wide `section-title` remainder deferred. |
| A6/A7 — dropdown focus ≥3:1; transitions respect reduced-motion | **Met (A7 scoped)** | New `--motion-medium` token; `components.css` literals deferred. |
| P4 — web `_sessions` idle reaper; bounded growth | **Met** | Idle-TTL reaper (default 1800s) with `Agent.aclose()` teardown + a WS-subscriber/not-processing guard so open tabs work without refresh. |
| P5 — shared `_StreamAccumulator`, no behavior change | **Met** | `llm/_streaming.py`; **zero test files changed**; per-provider constants preserved. |
| Q4 — shared `App.api.fetchJson` | **Met** | `static/js/api.js`; 2 of 13 `.ok` sites migrated (the rest bespoke, left alone). |
| DOC1–DOC5 — doc/env scrub | **Met** | Phantom event corrected to the real optimistic-update mechanism; stale Slack/F9 refs reframed; `.env.example` deadvars dropped + tunables documented; `agents.md` anchors added. |
| G1 — 3 stale remote branches deleted | **Met (already done)** | Verified absent on `origin` at flight start; verify-only. |
| G2 — oversized brand PNGs re-exported | **Met** | `gleepglorp_small.png` 1712K→264K @ 512×512; `_med` optimize-only (operator decisions). |
| Maintenance report backlink | **Met** | Done at scaffold time. |

### Overall Outcome
**Achieved in full.** Every mission criterion was met (two with deliberate, documented scope-narrowing — A5/A7 to the connector-editor surface). The mission's stated outcome — patch the CVEs, stop the recurring lint drift with a *gate*, wire the connector error taxonomy, bring the M11 UI to WCAG Level-A, bound session growth, and land the cleanup grab-bag — was delivered. The single highest-value deliverable is the **enforcement gate (Q1)**: it converts a finding with a *proven 100% recurrence rate* (M06→M09) into a structurally-prevented class of problem.

A **post-mission root-cause fix** (PR #96) eliminated the multi-hour `pytest tests/` exit hang that had dogged the project since F11 (mislabeled as a "benign aiosqlite teardown warning") — arguably the most consequential single fix of the whole effort, since it unblocks ever wiring the suite into CI.

## Flight Summary
| Flight | Status | Key Outcome |
|--------|--------|-------------|
| 01 Dependency CVE Refresh | landed (debriefed) | 4 CVEs closed via pyproject floors; learned the image builds from `pyproject.toml`, not `uv.lock` |
| 02 Lint/Format Enforcement Gate | landed | First CI + pre-commit; ruff pinned 0.15.15 everywhere — the centerpiece |
| 03 Connector Error-Handling | landed | T2 narrow+reraise, T1 typed error, Q2 dead-type deletion; 3 regression tests |
| 04 M11 UI Accessibility | landed | A1–A7 (WCAG Level-A + AA/AAA cleanup); Witnessed behavior test 8/8 |
| 05 Long-Lived Session Hygiene | landed | Idle-TTL reaper + new `Agent.aclose()` lifecycle contract |
| 06 Cleanup Grab-Bag | landed | `_StreamAccumulator`, `App.api.fetchJson`, DOC1–5, G1/G2 |

> Flights 02–06 were landed and merged but not individually `/flight-debrief`-ed; their lessons are captured in their flight logs and synthesized here. Flight 01 was debriefed (`completed`).

## What Went Well

1. **The per-leg design-review gate repeatedly prevented wrong work from landing.** It caught a *flight-killing* premise in F01 (regenerating `uv.lock` would have shipped **zero** fixes — the image resolves from `pyproject.toml`), the post-reformat stale line-numbers + a missed `agents.md` count edit + a non-driveable test fixture in F03, the required log-and-reraise path + lock discipline in F05, and the Ollama dict-arg / OpenRouter-override edges in F06's P5. Pattern to keep: **independently verify every load-bearing design-review claim before acting.**
2. **Enforcement-gate-not-cleanup (Q1).** Reframing the deliverable from "reformat the tree" (symptom) to "install a gate that fails on violations" (cause) is the mission's signature methodological win and the standard response to any Nth-recurrence finding.
3. **Behavior-preserving discipline on refactors.** P5 landed with **zero test edits** and all provider constants preserved; the "if a test needs changing, it's not behavior-preserving — divert" rule held. Q4 extracted only the 2 cleanly-duplicated sites and left 11 bespoke ones alone (anti-over-abstraction).
4. **New resource-lifecycle primitive (Agent.aclose / LLMProvider.aclose)** plus the thrice-instantiated idle-reaper pattern (PTY → MCP → web) — real structural maturity, not just fixes.
5. **Orchestration autonomy was right (operator confirmed).** The design-review→implement→review loop with the operator consulted only at genuine forks (open questions / scope) was the right level of autonomy across ~16 crew agents and 6 flights.

## What Could Be Improved

1. **The test-container wedge cost hours and nearly derailed the final flight.** The true cause was an `aiosqlite` non-daemon worker thread orphaned on a torn-down per-test event loop, joined at interpreter exit → the process hung *after* the suite passed. It had been misdiagnosed as a "benign teardown warning" for many flights. **Lesson: stop dismissing recurring teardown warnings as benign — a recurring warning is a finding.** Fixed at root in PR #96.
2. **Concurrent full-suite runs gridlock a shared container** (shared SQLite DB + ports). Leg developers leaving background `pytest tests/` runs piled up hung processes. **Lesson: never run the suite concurrently against one shared container; CI needs per-run DB isolation or ephemeral test containers.** (PR #96 fixed single-run exit; concurrent contention is still an open infra concern.)
3. **Per-flight debriefs were skipped for 02–06.** Acceptable here (rich flight logs + this synthesis), but individual debriefs would have surfaced the aiosqlite signal sooner (it was logged as an anomaly in multiple flights but never escalated).
4. **Several F01 documentation/tooling recommendations remain open** (the `pyproject`-vs-`uv.lock` build-path note; the `audit-image` make target; the dependency-flight pre-flight checklist). Cheap, high-leverage, not yet done.

## Lessons Learned

- **Technical:** the image builds from `pyproject.toml` ranges, not `uv.lock` — dependency fixes must be expressed as floors (and the host `make audit` audits the wrong tree). aiosqlite worker threads are non-daemon and loop-bound — any per-loop test harness must close connections on their creating loop or daemonize them.
- **Process:** reframe Nth-recurrence findings as *gates*; verify build/runtime paths before authoring dependency legs; treat recurring "benign" warnings as findings.
- **Domain:** the web `_sessions` cache is UI-chat-only (connector sessions are DB-direct) — scoping the reaper correctly hinged on that distinction, which only surfaced through operator clarification.

## Methodology Feedback

- The **design-review gate** is the strongest signal in Flight Control as practiced here — it paid for itself multiple times. Worth reinforcing as non-skippable for dependency/refactor/deletion legs.
- **Behavior tests** integrated cleanly as acceptance verification (F04, Witnessed 8/8) even in a degraded re-spawn-per-step mode (no `SendMessage` that session). The Witnessed pattern's independence held.
- **Skipping per-flight debriefs** to move fast is a viable mode for a tightly-scoped maintenance mission, but it defers the cross-flight signal (the aiosqlite anomaly) to the mission debrief. Recommend at least a lightweight per-flight anomaly-escalation check.

## Action Items
- [ ] **(quick win, highest priority)** `delete_session` (`app.py:1754`) does a bare `del _sessions[sid]` — add `await agent.aclose()` for symmetry with the reaper (the primitive already exists).
- [ ] **(quick win)** Add `make audit-image` (`docker exec the-one pip-audit --skip-editable`) and document the host `make audit` as non-authoritative.
- [ ] **(infra)** Make a CI/test plan that isolates the suite per-run (ephemeral DB / container) so concurrent runs can't gridlock; then — now unblocked by #96 — wire the full `pytest` suite + in-container audit into CI alongside the lint gate.
- [ ] **(docs)** Add the `pyproject.toml`-vs-`uv.lock` build-path invariant + a dependency-flight pre-flight checklist (install-source → direct/transitive → runtime/toolchain triage → audit-surface==ship-surface) to `CLAUDE.md`/`agents.md`.
- [ ] **(follow-up flight)** A5-remainder (`section-title` `<div>`s in 6 other studio files) + A7-remainder (`components.css` transition literals).
- [ ] **(carried, next ACL flight)** Q6 `_acl.py` (776 LOC) axis-level extraction as a prerequisite of the next ACL-touching flight.
- [ ] **(low)** Annotate each transient CVE floor in `pyproject.toml` with a "safe to drop when…" note.
- [ ] **(deferred, re-evaluate only if posture changes)** Architectural cluster P1/P2/P3/P8/I1 — correct under single-process; no compounding cost.

## Next Cycle
The lint/CI gate is now a foundation: the highest-leverage next step is extending CI (audit-image + the now-unblockable full test suite + the behavior tests). The backlogged **Chat History Retention (XX)** mission was deferred behind this maintenance cycle and is now eligible for re-evaluation.
