# Leg: 05-hat-tier-1-with-caplog-retirement

**Status**: completed
**Flight**: [Per-agent MCP attach + tool-routing in agent loop](../flight.md)

## Objective

Author the Tier-1 HAT test scaffold (`tests/test_mcp_attach_hat.py`) covering the 5-step verification sequence per flight §7, and the Tier-2 manual HAT procedure (`tests/HAT.md`). The Tier-1 test file's caplog assertion is the binary go/no-go gate for retiring the F2-known-issue from `mission.md::Known Issues` — PASS retires; FAIL files a follow-up flight to revert F5 L1's dispatcher rewrite. **L5 lands the test file and docs in this session; the actual PASS gate runs inside docker at flight-end (per A1/A2/A3 env-dependence) before the F2-known-issue line is removed.**

## Context

**Hybrid leg shape** (per agentic-workflow protocol's HAT framing): L5 is part autonomous, part deferred. The autonomous part is writing the Tier-1 test scaffold + Tier-2 HAT.md procedure — pure file authoring; no test execution. The deferred part is running the Tier-1 test inside `docker compose exec the-one pytest` for the binary PASS gate. F6 cannot land the F2-known-issue retirement without the docker PASS — this is documented as a flight-end checkpoint.

**Why two tiers**: per flight §7 + §10 — Tier-1 is CI-runnable, automated, and gates the retirement claim. Tier-2 is manual operator verification against a real OAuth-protected MCP server (e.g., live GitHub MCP via the F5 manual-entry path); not blocking; documented for operator self-verification post-merge.

**Why the F2-known-issue retirement is binary**: F5 L1 added `_open_*_transport_stack` helpers to retire the `MCPClient transport close failed` warning under F4-pool-routed paths. F5 shipped the mechanism speculatively because the warning surfaces only during real subprocess teardown (not unit-mockable). The Tier-1 HAT exercises real bwrap-spawned subprocess + real MCP session + real teardown across 5 distinct lifecycle scenarios — caplog captures any WARNING records during the run. Zero hits = retirement OK. Any hits = revert F5 L1.

**Why the test file scaffolding lands now even though execution is deferred**: writing the test now (a) commits the L5 design to executable code that the flight-end docker run can simply execute, (b) lets cycle-1 design review verify the test structure before the docker run, (c) avoids a second F6-design-cycle pass when docker is reachable. The flight-end docker run becomes a single-command gate: `docker compose exec the-one pytest tests/test_mcp_attach_hat.py -v`.

**Cache freshness contract**: this leg writes test code and docs only — no caches, no schemas, no migrations. The HAT test does spawn pool entries and assert on them, but those pool entries reset between tests via the `_clear_pool_after_each_test` autouse fixture (already in place per F4 / per `tests/test_mcp_pool.py:45`).

**Prior leg outcomes** (flight log):
- L0-L3 landed (uncommitted in working tree).
- L0/L1/L2 anomalies A1/A2/A3 lock the env-dependence pattern: `tests/test_mcp_pool.py` (and any test that constructs a real `_entry_worker`) hangs outside docker. L5's HAT test inherits this constraint.
- L2 deferred `tests/test_mcp_pool.py::test_acquire_with_source_override` to flight-end docker run; L5 inherits the same pattern.

**Stake**: ~250 LOC test code + ~80 LOC HAT.md doc + ~5 LOC mission.md edit (deferred to PASS confirmation). No production code change.

## Inputs

What exists before this leg runs (post-L0-L3):

- `the_one/mcp/_pool.py::_entry_worker` (post-L3) — reads csid + tcid from canonical ContextVars; passes both to `build_oauth_provider_for_source`.
- `the_one/mcp/_pool.py::acquire` (post-L2) — accepts `source_override: MCPSource | None = None` kwarg.
- `the_one/mcp/_tool.py::MCPClientTool` (L2) — `mcp__{source}__{tool}` prefixed names, 64-char ceiling.
- `the_one/mcp/_tool_provider.py::MCPToolProvider.get_tools_for_agent` (L2) — agent build-time MCP tool registration with all 4 failure classes + 64-char sub-case.
- `the_one/agent/_context.py` (L3) — canonical ContextVar definitions.
- `the_one/agent/factory.py::AgentFactory` (post-L2) — accepts `mcp_provider: MCPToolProvider | None`.
- `tests/test_mcp_pool.py` lines 1-45 — autouse `_clear_pool_after_each_test` fixture. The HAT test reuses this pattern.
- F5 OAuth fixture: per F5 flight log "L5 ships an in-repo OAuth-fixture-driven Tier-1 HAT" — the fixture lives in `tests/fixtures/oauth/` per F5 §10. Verify path at L5 implementation time.
- F4 HAT precedent: `mcp-server-fetch` reference server — installed in dev container per L0 anomaly A1 ("Pool tests timeout in `aiosqlite._connection_worker_thread`-bound waits"; the dev container has working aiosqlite + bwrap).
- `missions/07-mcp-integration/mission.md:104` — F2-known-issue line: `- [ ] **\`MCPClient.disconnect\` teardown noise** — discovered in F2 L7 HAT...` This is the line to retire on PASS.
- F5 L1's `MCPClient transport close failed` warning emit site — `the_one/mcp/client.py:333` (per F6 design Phase 1b reconnaissance — comment reads "Cross-task safety net... real fix is the F4 pool's worker-task pattern"). The HAT caplog asserts NO records match this exact substring during the 5-step run.
- `tests/HAT.md` — does NOT exist (verified by Phase 1 grep at L5 design time).
- `tests/test_mcp_attach_hat.py` — does NOT exist.

## Outputs

- `tests/test_mcp_attach_hat.py` (NEW) — Tier-1 HAT test file. ~250 LOC. ~7 tests covering the 5 verification steps + caplog assertion + bonus per-agent isolation step. Marked with `pytest.mark.skipif` for environments where bwrap or `mcp-server-fetch` are unavailable (skips outside docker rather than hanging).
- `tests/HAT.md` (NEW) — Tier-2 manual HAT procedure (~80 LOC). Documents the GitHub MCP via manual-entry path operator-runnable test, plus the Tier-1 docker-run command for self-verification.
- `missions/07-mcp-integration/flights/06-mcp-attach-and-tool-routing/flight-log.md` — Leg Progress entry; explicitly documents that the F2-known-issue retirement is **deferred to flight-end docker run** (NOT included in this leg's commit since the PASS gate hasn't run yet).
- **NOT in this leg**: the `mission.md` line removal. The retirement is gated on docker PASS at flight-end; only AFTER PASS does the FD edit `mission.md:104` to mark the issue retired.

## Acceptance Criteria

- [ ] `tests/test_mcp_attach_hat.py` exists; collected by pytest (`pytest --collect-only tests/test_mcp_attach_hat.py` reports the expected ~7 tests).
- [ ] All HAT tests use `pytest.mark.skipif` for `bwrap` AND `mcp-server-fetch` availability — outside docker, the tests skip cleanly (do NOT hang).
- [ ] HAT test #1 (pre-state): registers stdio + streamable-http MCP sources via the F1 admin path; configures agent A and agent B with attach + override.
- [ ] HAT test #2 (tool-list visibility): builds agent A; asserts `agent.tools.all_schemas()` contains both `mcp__{stdio_name}__*` and `mcp__{http_name}__*` entries; asserts NO collision (different prefixes).
- [ ] HAT test #3 (tool-call dispatch): agent A invokes `mcp__{stdio_name}__fetch(url=...)`; asserts result text returned; `pgrep -f mcp_server_fetch` shows ONE bwrap-wrapped subprocess.
- [ ] HAT test #4 (per-agent isolation): agent B (with different `mcp_overrides[stdio.name].env`) invokes the same tool; asserts `pgrep -f mcp_server_fetch` shows TWO distinct PIDs (one per agent).
- [ ] HAT test #5 (graceful-degrade — restructured per cycle-1 M5): deletes the http source via API; rebuilds agent A; asserts `agent_v2.tools.all_schemas()` no longer contains any `mcp__{http_name}__*` entries; the stdio source's tools still register.
- [ ] HAT caplog assertion: across the 5-step sequence, `pytest caplog` captures records at WARNING level for `the_one.mcp.client`. `assert not any("MCPClient transport close failed" in r.message for r in caplog.records)`. This is the binary gate.
- [ ] Bonus test (per F4 HAT precedent): per-(agent, source) keying — agent A and agent B against the SAME source produce DISTINCT bwrap PIDs even with default override (no `mcp_overrides`).
- [ ] `tests/HAT.md` exists; documents (a) Tier-1 docker run command, (b) Tier-2 GitHub MCP manual procedure, (c) the F2-known-issue retirement criterion, (d) the follow-up-flight scope to file on FAIL.
- [ ] Flight log entry for L5 explicitly states "F2-known-issue retirement deferred to flight-end docker run" — this is NOT a documentation gap; it's the protocol.
- [ ] `ruff check the_one/ tests/` is clean.
- [ ] No HAT test runs in the autonomous-implementer's targeted gate (would hang per A1/A2/A3) — collection-only verification is the L5 implementation gate.

## Verification Steps

```bash
# Test file collection (lightweight; does not execute)
./.venv/bin/python -m pytest --collect-only tests/test_mcp_attach_hat.py -q 2>&1

# Skipif behavior outside docker (tests must SKIP, not HANG)
./.venv/bin/python -m pytest tests/test_mcp_attach_hat.py -v --timeout=10 2>&1
# Expected: all tests SKIPPED (bwrap or mcp-server-fetch unavailable on host)

# HAT.md format check (markdown lints clean)
ls -l tests/HAT.md  # exists
head -30 tests/HAT.md  # has the expected sections

# Lint
./.venv/bin/ruff check the_one/ tests/

# At flight-end (docker reachable):
# docker compose exec the-one pytest tests/test_mcp_attach_hat.py -v
# PASS → edit mission.md:104 to remove the F2-known-issue line
# FAIL → file follow-up flight per HAT.md's "On FAIL" section

# DO NOT include tests/test_mcp_pool.py or tests/test_mcp_attach_hat.py
# in any other targeted gate (env-dependent).
```

## Implementation Guidance

L5 is short and focused. ~7 test functions + 1 markdown doc. No production code.

1. **Create `tests/test_mcp_attach_hat.py` skeleton.**
   - Module docstring: explain the 5-step Tier-1 sequence; reference flight §7; document the binary go/no-go caplog assertion; explain the `pytest.mark.skipif` pattern for outside-docker skip-don't-hang.
   - Skip-conditions:
     ```python
     import shutil, subprocess
     _BWRAP_AVAILABLE = shutil.which("bwrap") is not None

     def _mcp_server_fetch_available() -> bool:
         """Probe whether `mcp-server-fetch` is importable in the current env."""
         try:
             subprocess.run(
                 ["python", "-c", "import mcp_server_fetch"],
                 check=True,
                 capture_output=True,
                 timeout=5,
             )
             return True
         except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
             return False

     _HAT_AVAILABLE = _BWRAP_AVAILABLE and _mcp_server_fetch_available()

     pytestmark = pytest.mark.skipif(
         not _HAT_AVAILABLE,
         reason="HAT requires bwrap + mcp-server-fetch (run inside `docker compose exec the-one`)",
     )
     ```
   - This makes EVERY test in the file skip when run on the host, but execute inside docker where both are available.

2. **Write the 5 step tests + caplog gate + bonus.**
   - `test_step_1_pre_state_register_sources_and_configure_agents` — exercise the F1 admin path; create stdio + http sources; configure two agents with attach + override; assert DB state.
   - `test_step_2_tool_list_visibility_under_agent_build` — `agent_a = await factory.create("agent-a")`; assert prefixed tool names in `agent_a.tools._tools`.
   - `test_step_3_tool_call_dispatch_via_pool_to_real_subprocess` — agent A calls a tool; assert `pgrep -f mcp_server_fetch` shows 1 PID; assert result text round-trips.
   - `test_step_4_per_agent_isolation_distinct_subprocesses` — agent B (different override) calls same tool; assert `pgrep` shows 2 distinct PIDs.
   - `test_step_5_graceful_degrade_delete_source_then_rebuild_drops_tools` (per cycle-1 M5 restructure) — delete source via API; rebuild agent A; assert deleted source's tools absent.
   - `test_caplog_no_transport_close_failed_warnings` — runs the full 5-step sequence under a single `caplog.at_level(WARNING, logger="the_one.mcp.client")` block; asserts `not any("MCPClient transport close failed" in r.message for r in caplog.records)`.
   - `test_bonus_per_agent_source_keying_no_override` (per F4 HAT precedent) — agent A and agent B against the same source with NO override; assert per-(agent, source) keying still produces distinct PIDs (or document if F4 dedup-on-same-config kicks in).

3. **Create `tests/HAT.md`.**
   - Sections:
     - "Tier 1 (CI / always-run)" — single-line docker command + expected output (all 7 tests pass).
     - "Tier 2 (Manual / quarterly) — GitHub MCP via manual-entry path" — operator setup steps (register OAuth app at github.com/settings/developers; copy client_id; navigate to chat UI; trigger tool call; click Login-required; paste manual-entry fields; consent at github.com; verify successful tool call).
     - "F2-known-issue retirement gate" — explains the caplog assertion as the binary gate; references `the_one/mcp/client.py:333`'s WARNING site.
     - "On FAIL" — pre-written follow-up flight scope: revert F5 L1's `_open_*_transport_stack` helpers + `_transport_connect` dispatcher rewrite + README §3 scoping update; file as a separate flight; mission.md:104 stays open with a real diagnosis plan.

4. **Update flight log.**
   - Append L5 Leg Progress entry per L0-L3 precedent.
   - Explicitly note: "F2-known-issue retirement DEFERRED to flight-end docker run. mission.md:104 NOT yet edited; gated on Tier-1 PASS."

5. **Test gate (L5 verification only — no execution of HAT tests outside docker).**
   - `./.venv/bin/python -m pytest --collect-only tests/test_mcp_attach_hat.py -q` — collection succeeds; all tests visible.
   - `./.venv/bin/python -m pytest tests/test_mcp_attach_hat.py -v --timeout=10` — all tests SKIPPED (no bwrap on host); pytest exits 0 (skipped is not failure).
   - `./.venv/bin/ruff check the_one/ tests/` — clean.
   - L0-L3 regression: `./.venv/bin/python -m pytest tests/test_imports.py tests/test_mcp_overrides.py tests/test_mcp_tool_provider.py tests/test_agent_context.py tests/test_oauth_provider_factory.py tests/test_mcp_oauth_errors.py tests/test_mcp_oauth_integration.py tests/test_agent.py tests/test_mcp_client.py tests/test_db_repositories.py tests/test_db_migration.py -q --timeout=15`.

6. **Update leg status to `landed`** in this leg artifact.

7. **DO NOT** edit `mission.md:104`. **DO NOT** run the HAT tests inside docker (out of L5 scope; flight-end does this). **DO NOT** commit.

## Edge Cases

- **`mcp-server-fetch` not in dev container**: F4 HAT precedent says it's installable via `pip install mcp-server-fetch`. If the docker container doesn't have it, the HAT skipif prevents hangs. Add a one-line note in HAT.md's Tier-1 section: "If skipped, `docker compose exec the-one pip install mcp-server-fetch` and re-run."
- **Caplog assertion across 5 steps**: pytest's `caplog` fixture is per-test by default. To assert across the full 5-step sequence, the caplog test must replay the sequence inside a single test function (NOT span 5 separate tests). Implementation: write the caplog test as the LAST test, where it imports/replays the operations from the prior 4 tests' helpers, then asserts. Alternative: use a session-scoped log capture. Pick whichever is cleaner at implementation time.
- **F2-known-issue PASS-but-degraded**: if the Tier-1 PASSes but produces other unrelated warnings (e.g. a deprecation notice from the SDK), the assertion still passes (only matches the specific substring). Acceptable — the gate is for the F5 L1 specific mechanism.
- **F2-known-issue FAIL handling**: do NOT auto-revert F5 L1 in this leg. The HAT.md "On FAIL" section pre-writes the follow-up flight scope; the FD escalates to user with that scope.
- **Tier-2 GitHub MCP unavailable**: GitHub MCP at `https://api.githubcopilot.com/mcp/` is operator-credentials-dependent. Document in HAT.md but accept that not every operator can run it.
- **L5 leg artifact's missing `04` neighbor**: per the flight artifact, L4 was folded into L2 (default disposition). The legs/ directory will have `00`, `01`, `02`, `03`, `05` — no `04`. This is intentional; the flight-log + leg artifacts document the fold.
- **L6 (optional docs sweep) folding**: per the flight artifact, L6 defaults to fold into L5's docs-pass. L5 includes `tests/HAT.md` authoring. L6's additional content (5th convention `same-task-anyio-cm-ownership` in agents.md, README.md F5 Lazy-path Two-Event UX section, F5→F6 carry-forwards table, provider_factory.py docstring flowchart) is OUT OF L5 SCOPE — defer to a follow-up routine-maintenance pass. F6 debrief notes this.

## Files Affected

- `tests/test_mcp_attach_hat.py` (NEW) — ~250 LOC.
- `tests/HAT.md` (NEW) — ~80 LOC.
- `missions/07-mcp-integration/flights/06-mcp-attach-and-tool-routing/flight-log.md` — Leg Progress entry (~+30 LOC).
- **NOT modified in this leg**: `missions/07-mcp-integration/mission.md` (line 104 retirement gated on docker PASS).

Net delta: ~+360 LOC across 3 files; zero production code change.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified (collection succeeds; skipif works on host; lint clean)
- [ ] Update `flight-log.md` with leg progress entry; explicitly note F2-known-issue retirement DEFERRED
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md, do NOT update mission.md, do NOT commit
- [ ] Do NOT run HAT tests inside docker (flight-end does this)
- [ ] Signal `[HANDOFF:review-needed]` once all checklist items above are done

---

## Citation Audit

8 citations verified against current code at leg design time. All `OK`:

| Citation | Classification | Evidence |
|----------|----------------|----------|
| `the_one/mcp/client.py:333` — `MCPClient transport close failed` WARNING site | OK | F6 design Phase 1b reconnaissance verified this line; comment reads "Cross-task safety net" |
| `the_one/mcp/_pool.py::_entry_worker` — reads csid + tcid from canonical ContextVars (post-L3) | OK | L3 implementation just landed |
| `the_one/mcp/_pool.py::acquire` — accepts `source_override` kwarg (post-L2) | OK | L2 implementation landed |
| `the_one/mcp/_tool.py::MCPClientTool` (post-L2) | OK | L2 NEW file |
| `the_one/mcp/_tool_provider.py::MCPToolProvider.get_tools_for_agent` (post-L2) | OK | L2 NEW file |
| `tests/test_mcp_pool.py:45` — `_clear_pool_after_each_test` autouse fixture | OK | grep confirmed at L2 design time |
| `missions/07-mcp-integration/mission.md:104` — F2-known-issue line | OK | Read at flight design time; line numbers may have drifted slightly but the entry exists under "Known Issues" |
| `tests/HAT.md` and `tests/test_mcp_attach_hat.py` — do NOT exist | OK | grep confirmed at L5 design time |
