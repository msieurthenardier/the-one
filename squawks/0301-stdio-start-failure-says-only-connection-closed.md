# Squawk 0301: A stdio MCP server that can't start says only "Connection closed"

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-25
**Completed**: 2026-11-14
**Related**: renumbered from 0260 on 2026-10-30; that id was also used by the completed `0260-model-catalog-never-refreshes`. Mission 31 and 32 documents that cite "squawk 0260" for the stdio cause text mean this squawk ([maintenance 2026-10-30](../maintenance/2026-10-30.md)).

## Report
Mission 31 Flight 5's planning survey found that when a stdio MCP server fails to start, the operator sees only `MCPConnectionError: MCP connect failed: MCPError: Connection closed`. The cause never reaches them. Two cases gave the same text: a sandbox writable path that doesn't exist, and a uvx package that doesn't exist.

The stdio transport already has a translation for exactly this. `_translate_bwrap_stderr` turns bwrap's "Can't find source path" into a `SandboxError` naming the path. A second pass translates the inner process's stderr, such as a missing Python module. `MCPClient._cleanup_after_failed_connect` is meant to let that `SandboxError` win over the "connection closed" wrapping. Something on that path no longer delivers it.

Flight 5 fixes only the stdio headline wording (ledger row 18, A18), not the missing cause.

## Evidence
- **Repro** (`f5-presentation-debt.md` §0.1 in the Flight 5 FD scratchpad):
  1. `POST /api/mcp-sources` with `type: stdio`, `command` = the venv python, `args` `["-m","tests.fixtures.mcp.hello_server","--stdio"]`, `cwd` = the repo, `env.PYTHONPATH` = the repo, and `sandbox.writable_paths` `["$HOME/the-one-f5-debt/cwd/missing-dir"]`.
  2. `POST /api/mcp-sources/{id}/test/connect` returns `{"status":"error","error":"MCPConnectionError: MCP connect failed: MCPError: Connection closed"}`.
  3. Create the directory, and the same call returns `ok` with 2 tools.
- `the_one/mcp/transports/stdio.py:159` `_translate_bwrap_stderr` and `_BWRAP_NONEXISTENT_PATH_RE` (`:132`) are the existing translation. Its docstring says the probe text was captured against bwrap 0.11.0 in the old dev container.
- `the_one/mcp/client.py:770-790` `_cleanup_after_failed_connect` holds the precedence contract.
- **Caveat:** the survey ran inside `unshare -rn` (the `THE_ONE_TEST_NETNS` namespace), so bwrap ran in a user namespace. First reproduce on the plain host, and record the bwrap version and its exact stderr. The cause may be:
  - the stderr text drifting from the regex;
  - the `errlog=` capture or exception propagation changing under the `mcp` 2.x SDK (Mission 29);
  - something specific to the namespace.

**Expected:** the test/connect error names the cause, for example "the sandbox writable path … does not exist", or the inner process's own error line, as the F3 §6 contract says. A test proves it for the missing-path case.

**Not in this squawk:** checking writable paths when the server is saved (rejecting them, or creating them) is a separate design choice.

## Corrective Action
Cause found on the plain host (bubblewrap 0.9.0, stderr `bwrap: Can't find source path <path>: No such file or directory`, which the existing regex matches): `_translate_bwrap_stderr` and `_cleanup_after_failed_connect` worked, but in `MCPClient.connect` the final `except (Exception, BaseExceptionGroup)` arm wrapped the cleanup in `_safe_cleanup`, whose catch-all swallowed the `SandboxError` the cleanup raised, so the generic "Connection closed" wrapping won. `the_one/mcp/client.py` `_safe_cleanup` now lets an `MCPClientError` from cleanup propagate (abandoning the stack first). The previously skipped `test_sandbox_writable_paths_nonexistent_raises_at_connect` is un-skipped and is the proof (its skip reason blamed this same swallowed path).

## Verification
Falsified: with the new `except MCPClientError` replaced the test fails with "MCP connect failed: MCPError: Connection closed"; with it, it passes. `tests/test_mcp_sandbox_integration.py`, `tests/test_mcp_stdio_sandbox.py` and `tests/test_mcp_client.py` pass (100 passed, 2 pre-existing skips); ruff clean. The inner-process (uvx package) case was not separately reproduced. Run under the plain host, not the netns.

The missing-uvx-package case in the report was not reproduced separately.

Gate (Flight Director, full gate on the final tree, 2026-11-14): unit tier 10155 passed, 15 skipped (under `THE_ONE_TEST_NETNS=1`); browser `PARALLEL_RESULT rc=0 total=2253s lanes=20 failed=-`.

## Sign-Off
**Reviewer**: independent Reviewer (Sonnet tier, because the batch diff touches the MCP sandbox error path), who confirmed the batch diff with `[HANDOFF:confirmed]` on 2026-11-14 with no high or medium issues.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-14` commit on `squawk/turnaround-2026-11-14`
