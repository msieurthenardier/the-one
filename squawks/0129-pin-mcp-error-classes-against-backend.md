# Squawk 0129: Pin the MCP error classifier's classes against the backend

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: —

## Report

`App.mcpErrorMessage` (DD19) picks a headline by the leading exception class name in the raw `"{Class}: {message}"` text. If the backend adds or renames a class, that class silently falls back to the generic headline, and nothing fails. One test should list the classes the `test/connect` envelope can emit and assert each one is classified, or deliberately generic.

## Evidence

- **The classifier** recognises `MCPConnectionError`, `MCPVersionMismatch`, `MCPCapabilityMissing`, `SandboxError` and, through the sign-in path, `MCPAuthRequired` (`static/js/areas/studio/mcps-tab.js`, `mcpErrorMessage`).
- **The backend classes:**
  - `the_one/mcp/errors.py` defines `MCPClientError` and its subclasses `MCPVersionMismatch`, `MCPCapabilityMissing`, `MCPConnectionError`, `MCPToolNotFoundError`, `MCPArgumentError`, `MCPCallError`, `MCPAuthRequired` and `MCPRegistrationError`;
  - `the_one/platform/sandbox/errors.py` defines `SandboxError(MCPClientError)`;
  - `the_one/mcp/oauth/errors.py` defines the `MCPOAuth*` classes.
- **The envelope:** `api.py`'s `test/connect` `except` blocks format `type(e).__name__`.

## Corrective Action
*(written at completion)*

## Verification
A unit test enumerates the `MCPClientError` subclasses (including the sandbox and OAuth ones), and fails when one is neither classified nor in an explicit "generic on purpose" list. Prove it fails by adding a dummy subclass.

## Sign-Off
*(written at completion)*
