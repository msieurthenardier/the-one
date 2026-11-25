# Flight: Unit-tier runtime III

**Status**: in-flight
**Mission**: [Post-Mission-36 Maintenance](../../mission.md)

## Contributing to Criteria

- [ ] The unit tier is under 400 s (T1)
- [ ] Every browser lane's budget comes from a measured quiet reading (T2)

## Pre-Flight

### Objective

Bring the unit tier from about 455 s to under 400 s on a quiet host, without deleting, skipping or xfailing a test. Then re-read every browser lane budget from one quiet `--parallel 3` gate. Measure first: the existing profile cannot attribute about 290 s of sub-0.5 s phases.

### Open Questions

N/A. This is a maintenance flight. The measurement leg decides which of the conditional steps run.

### Design Decisions

**Measure before cutting.** The first leg runs one quiet unit pass with `--durations=0 --durations-min=0.001`, plus a `--setup-only` pass, and records per-file and per-fixture sums. This replaces the 0.5 s-cutoff profile from squawk 0403. Fixture hoisting and xdist go ahead only if that data points to them.

**Target: under 400 s.** That leaves about 100 s of headroom under the 500 s standing target (squawk 0403), roughly a mission's growth at the current rate.

**Squawk 0403 stays closed.** The standing target remains 500 s. This flight restates it only if the operator asks.

### Citation Audit

Citations are from the 2026-11-24 maintenance report. They are re-checked at leg design.

### Prerequisites

- [ ] PR #388 (squawk turnaround 2026-11-24) is merged, so the baseline includes its tests.
- [ ] A quiet host for the measurement and the closing gate.

### Pre-Flight Checklist

N/A. This is a maintenance flight with concrete fixes.

## In-Flight

### Technical Approach

**Baseline.** 12350 passed and 15 skipped in 453-457 s (quiet, `squawk/turnaround-2026-11-24`). The profile is in the 2026-11-24 report, finding T1.

1. **Measure** (T1, recommendation 1).
   - Run the fine-grained profile and `--setup-only` described above.
   - Report the top files and fixtures by setup, call and teardown time.
2. **Sample the sweeps.** This is safe before the measurement lands.
   - `test_gleepglorp_kind_tool_config.py`: 20.7 s. Its parametrized settable-fields test builds a seeded world for each case. Share one world per module, or sample.
   - `test_evals_gleepglorp_kinds.py` and `test_evals_gleepglorp_harness.py`: 16.6 s and 12.2 s. They sweep every scenario variant offline. Keep one variant per scenario in the unit tier, and move the full sweep to the eval tier.
   - `test_resolver_clip.py`: about 9.8 s. Pin Hypothesis `max_examples`.
   - `test_mcp_negotiation_fallback.py`: five revision cases, each paying about 1.2 s to spawn a server. Share one stdio fixture server.
3. **Use fake clocks.** Inject the clock and negotiation window into the MCP negotiation, stdio-connect and tool-call-timeout tests, which take about 30 s with real 2-4 s waits. Do the same for `test_routines_scheduler.py::test_once_routine_runs_without_waiting_for_the_tick`, which takes 2.1 s.
4. **Session-cache the static scans.** Cache the file walks in `test_unused_selectors_script.py` (3.4 s), `test_nav_helper.py` and `test_imports.py`.
5. **Shorten the KB teardown.** In `test_kb_manager.py`, three teardowns take about 1.8 s each. Use a shorter drain timeout in tests.
6. **Conditional, decided by step 1:**
   - hoist fixtures where setup dominates;
   - re-measure `pytest-xdist` (deferred since Mission 34). It needs a per-worker template database and serial markers for tests that bind ports.
7. **Closing quiet gate** (T2). Run `make gate` on a quiet host.
   - Re-budget per the rule in `the_one/agents.md`, including the six lanes with no measurement note (`knowledge`, `mcp-connection`, `settings-tools`, `providers`, `contracts-widget`, `chats-widgets`).
   - Restate the full-gate target.

### Checkpoints

- [ ] The profile is attributed (step 1).
- [ ] The tier is under 400 s, quiet and solo.
- [ ] Lanes are re-budgeted from one quiet gate.

### Adaptation Criteria

**Divert if**: the measurement shows the floor comes from the fixture or app infrastructure shared across lanes, in a way that needs a design change. Then raise it with the operator before changing shared test infrastructure.

**Acceptable variations**: reaching 400 s without the conditional steps.

### Legs

*(Designed by `/mission-control:agentic-workflow`. One finding maps to one leg where possible.)*

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] `the_one/agents.md` budget history and gate targets updated

### Verification

A quiet solo unit run is under 400 s, with the same pass count and no new skips. One quiet `--parallel 3` gate has every lane within its budget.
