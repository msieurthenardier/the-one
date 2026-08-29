# Squawk 0006: Verify two-agent-simultaneous self-configuration isolation

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-08-26
**Completed**: 2026-08-29

## Report

The self-configuration surface binds one credential to exactly one agent, and
Flight 1 asserted two-agent isolation (Leg 2 AC9) by enforcement inspection plus
code review — **not** a dedicated two-agent-simultaneous end-to-end test. Add an
e2e test that stands up two surface-enabled agents at once and proves their
surfaces and credentials do not cross: agent A's credential resolves only to A,
cannot read or write B's configuration, and vice versa, with both live
concurrently. If it surfaces a real cross-agent leak, escalate.

Carried forward from the Flight 1 debrief and re-homed here after being pulled
out of Mission 21 Flight 2 Leg 2 at design review.

## Evidence

- Flight 1 debrief, "What Could Be Improved → Technical": "Two-agent isolation
  (Leg 2 AC9) was ticked on enforcement + code inspection, not a dedicated
  two-agent-simultaneous end-to-end test."
- Identity resolution: `the_one/self_configuration/surface.py` `_calling_agent`
  (resolves the agent from the credential; DD9 refuses a disabled/foreign
  surface). Credential registry: `the_one/self_configuration/credentials.py`.
- Mission 21 Flight 2 debrief Action Items (2026-08-26): confirmed not yet logged
  until this squawk.

## Corrective Action

Added `TestSquawk0006TwoAgentSimultaneousIsolation::test_two_live_agt_credentials_never_cross`
to `tests/test_self_configuration_surface.py`, using the file's existing
`running_surface` fixture unmodified (a real in-process `uvicorn.Server` on
loopback) — no new fixture. The test stands up two surface-enabled agents,
`a-iso6a` and `a-iso6b`, and keeps both real `agt_`-prefixed credentials
live at once for the whole test (both rows fetched from `MCPSourceRepository`
up front, before either is exercised), driving all four confined tool calls
through a real `MCPClient` (the same construction the file's existing DD9
tests already use to present a fetched `MCPSource` row — not
`MCPToolProvider`/`AgentFactory`):

- **Reads never cross**: A's credential's `get_my_configuration` returns
  `name == "a-iso6a"`; B's returns `name == "a-iso6b"` — never the other's.
- **Writes never cross, in both directions**: A's `update_my_description`
  changes only A's stored row (verified via `SQLiteAgentStore.load`, the
  same store the fixture's other tests read back through); B's row stays
  `""`. B's `update_my_description` then changes only B's stored row
  without clobbering the write A already made to its own row.
- **Negative — disable refuses only the disabled agent's credential**:
  after `DELETE /api/agents/a-iso6b/self-configuration`, A's credential
  still resolves and reads correctly; B's now-revoked `agt_` credential is
  refused at the MCP gate with `MCPAuthRequired` or `MCPConnectionError`
  (the same failure classes the file's existing single-credential AC9
  disable test — `TestAC9ExternalDiesWithSurface.
  test_disabled_surface_401s_ext_token` — asserts for the `ext_` path).
  The refusal check is ordered as the LAST statement in the test (A's
  post-disable live check runs before it), mirroring every other
  `pytest.raises(MCPAuthRequired ...)` use already in this file — an
  `MCPClient` connect attempted immediately after an expected auth failure,
  in the same event loop, hits an unrelated `anyio`/SDK cancel-scope
  cleanup ordering issue (not a self-configuration bug) that every
  existing test in the file already avoids by the same ordering.

No cross-agent leak surfaced — both directions of isolation and the
disable-refusal held on every run. No source files were touched; this is a
test-only servicing item, consistent with the squawk's report.

## Verification

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_self_configuration_surface.py -x --timeout 120`
  — whole file, to prove no fixture interference: **10 passed** (9 pre-existing
  + the new test), 0 failed.
- New test: `TestSquawk0006TwoAgentSimultaneousIsolation::
  test_two_live_agt_credentials_never_cross` — asserts, with two agents'
  `agt_` credentials live concurrently: (1) each credential's
  `get_my_configuration` resolves only to its own agent, never the other's;
  (2) each credential's `update_my_description` writes only its own agent's
  stored `description`, leaving the other's untouched, verified in both
  directions; (3) after disabling one agent's surface, that agent's
  credential is refused (`MCPAuthRequired`/`MCPConnectionError`) while the
  other agent's credential still works.
- `.venv/bin/ruff check . && .venv/bin/ruff format --check .` — both clean
  (`All checks passed!`, `455 files already formatted`) across the whole
  tree, including the untouched squawks 0001–0004 working tree.
- `git status --short` confirms only `tests/test_self_configuration_surface.py`
  and this squawk artifact changed as part of this squawk; all other
  modified files are the pre-existing, untouched squawks 0001–0004 work.

## Sign-Off
**Reviewer**: Reviewer agent (independent, diff-scoped batch review of turnaround 2026-08-29; Sonnet — batch touches `api_credential.py`, the DB import graph, and self-configuration identity)
**Verdict**: confirmed
**Commit**: `{sha}` on `squawk/turnaround-2026-08-29` — PR #{pr}

Full unit suite at close-out: 4586 passed, 10 skipped, 704 deselected, 20 warnings in 557.56s (0:09:17).
**Reviewer**:
**Verdict**:
**Commit**:
