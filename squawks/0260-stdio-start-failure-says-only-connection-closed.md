# Squawk 0260: A stdio MCP server that can't start says only "Connection closed"

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-25
**Completed**: —

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
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
