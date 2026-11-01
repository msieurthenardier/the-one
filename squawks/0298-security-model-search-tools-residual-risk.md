# Squawk 0298: State the search_tools residual risk in SECURITY-MODEL's "Check this" section

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-30
**Completed**: 2026-11-01

## Report
`search_tools` is in the trusted-tool set, so its result never raises the "Check this" taint, but its result includes the descriptions of attached MCP tools, which come from the remote server. A malicious or compromised MCP server can plant instructions in a description that the agent reads through `search_tools`, and a later note or routine write is not flagged. The operator chose the server, and the same text already reaches the model as tool schemas, so this is a residual risk to state, not a defect. SECURITY-MODEL.md does not mention it. Changing the taint rule itself is a security-surface change and is out of scope here. From maintenance report 2026-10-30, finding #17.

## Evidence
- `the_one/agent/taint.py:28-34`: `TRUSTED_TOOL_NAMES` includes `"search_tools"`, with a comment calling its result "this agent's own catalogue".

## Corrective Action
Added a sentence group to the "Residual risks" paragraph of SECURITY-MODEL.md's "Agent self-scheduling" section (the "Check this" flag section). It names `search_tools` as trusted, says what it surfaces is partly server-authored (it matches on descriptions, lists matching MCP tool names, and a match loads the full schema with description into the model's view), that a malicious server can plant instructions there with no flag on a later note or routine write, and that this is accepted because the operator chose the server and the same text already reaches the model as tool schemas. Wording corrects the report: the result string itself lists tool names only; descriptions arrive through the schema load on match. No code or taint rule changed.

## Verification
Confirmed in `the_one/tools/_search_tools.py` and `factory.py::_on_search_match`. `tests/test_desktop_shell.py` and `tests/test_mcp_wire_shapes.py` (the only tests mentioning SECURITY-MODEL.md, in comments) pass: 98 passed.

SECURITY-MODEL.md's "Check this" / taint section names `search_tools` as trusted, says its result carries MCP-server-authored descriptions, and records why that is accepted.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch states security-model residual risks, 0298 and 0299), batch review of the 2026-11-01 squawk turnaround, scoped to the diff, `[HANDOFF:confirmed]`. The Flight Director also confirmed the schema-loading claim: a match calls `factory._on_search_match`, which appends the matched schemas to `loaded_schemas`.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-01` commit on `squawk/turnaround-2026-11-01`. Unit tier under `THE_ONE_TEST_NETNS=1`: 8560 passed, 23 skipped, 3 failed (the known `tests/test_desktop_host.py` baseline, unchanged from main).
