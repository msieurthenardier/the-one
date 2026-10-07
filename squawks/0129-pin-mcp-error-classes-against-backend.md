# Squawk 0129: Pin the MCP error classifier's classes against the backend

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-10-07

## Report

`App.mcpErrorMessage` (DD19) picks a headline by the leading exception class name in the raw `"{Class}: {message}"` text. If the backend adds or renames a class, that class silently falls back to the generic headline, and nothing fails. One test should list the classes the `test/connect` envelope can emit and assert each one is classified, or deliberately generic.

## Evidence

- **The classifier** recognises `MCPConnectionError`, `MCPVersionMismatch`, `MCPCapabilityMissing`, `SandboxError` and, through the sign-in path, `MCPAuthRequired` (`static/js/mcp-error.js`, `mcpErrorMessage`; moved there from `areas/studio/mcps-tab.js` by squawk 0128).
- **The backend classes:**
  - `the_one/mcp/errors.py` defines `MCPClientError` and its subclasses `MCPVersionMismatch`, `MCPCapabilityMissing`, `MCPConnectionError`, `MCPToolNotFoundError`, `MCPArgumentError`, `MCPCallError`, `MCPAuthRequired` and `MCPRegistrationError`;
  - `the_one/platform/sandbox/errors.py` defines `SandboxError(MCPClientError)`;
  - `the_one/mcp/oauth/errors.py` defines the `MCPOAuth*` classes.
- **The envelope:** `api.py`'s `test/connect` `except` blocks format `type(e).__name__`.

## Corrective Action
Added `tests/test_mcp_error_classes_pinned.py` (unit tier). It walks `MCPClientError.__subclasses__()` recursively (importing the sandbox and OAuth error modules so `SandboxError` and `MCPOAuth*` register), reads the classifier's recognised names from the `cls === '...'` literals in `static/js/mcp-error.js` (asserting at least 4 matched), and requires every backend class to be recognised or listed in `DELIBERATELY_GENERIC` with a reason. It also fails on a classifier name that no longer exists in the backend, and on stale or overlapping generic entries. No classifier, backend or envelope change. Recognised: MCPConnectionError, MCPVersionMismatch, MCPCapabilityMissing, SandboxError. Generic on purpose: MCPClientError, MCPAuthRequired (sign-in control flow), MCPToolNotFoundError, MCPArgumentError, MCPCallError, MCPRegistrationError (not raised by test/connect), and the four MCPOAuth* classes (reach the envelope only via its catch-all).

## Verification
Falsified: a dummy `MCPNewThing(MCPClientError)` failed the classified-or-generic test naming it; renaming `SandboxError` to `SandboxErr` in `mcp-error.js` failed both the unaccounted-class test (SandboxError) and the stale-name test (SandboxErr). Both edits restored. The new test file passes (3 tests); ruff check and format are clean; `make test-unit`: 5453 passed, 10 skipped, 2 failed (`test_self_configuration_surface.py` two live-MCP tests, unrelated to this change); both pass when re-run alone (2 passed), so they look load-flaky.

Original plan: a unit test enumerates the `MCPClientError` subclasses (including the sandbox and OAuth ones), and fails when one is neither classified nor in an explicit "generic on purpose" list. Prove it fails by adding a dummy subclass.

## Sign-Off

**Reviewer**: independent batch Reviewer (Haiku tier: no credential, gate, sandbox or self-configuration-identity surface in the diff); `make test-unit` 5496 passed, 10 skipped; static guards 265 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-07` on branch `squawk/turnaround-2026-10-07`
