# Squawk 0298: State the search_tools residual risk in SECURITY-MODEL's "Check this" section

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: —

## Report
`search_tools` is in the trusted-tool set, so its result never raises the "Check this" taint, but its result includes the descriptions of attached MCP tools, which come from the remote server. A malicious or compromised MCP server can plant instructions in a description that the agent reads through `search_tools`, and a later note or routine write is not flagged. The operator chose the server, and the same text already reaches the model as tool schemas, so this is a residual risk to state, not a defect. SECURITY-MODEL.md does not mention it. Changing the taint rule itself is a security-surface change and is out of scope here. From maintenance report 2026-10-30, finding #17.

## Evidence
- `the_one/agent/taint.py:28-34`: `TRUSTED_TOOL_NAMES` includes `"search_tools"`, with a comment calling its result "this agent's own catalogue".

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

SECURITY-MODEL.md's "Check this" / taint section names `search_tools` as trusted, says its result carries MCP-server-authored descriptions, and records why that is accepted.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
