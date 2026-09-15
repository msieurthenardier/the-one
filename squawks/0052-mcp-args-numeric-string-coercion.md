# Squawk 0052: MCP tool calls rejected when the model sends an integer as a string

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-14
**Completed**: —

## Report

`MCPClient.call_tool` validates arguments against the tool's `inputSchema`
with `jsonschema` before the wire call. Claude Haiku 4.5 (via the
`anthropic-plan` "Claude MAX" provider) intermittently emits integer fields as
numeric strings — `{"wcId": "7"}`, `{"delayMs": "3000"}`,
`{"level": "25"}` — even when the tool result it just read carried the value
as a bare number. Every such call is rejected before it leaves the process:
`[error] Tool execution failed: MCP tool 'evaluate' rejected arguments: '7'
is not of type 'integer'`. The model then tends to repeat the identical
string-typed call, burning the turn's iteration budget. Observed against the
Goldfinch browser server (`wcId`, `delayMs`) and the Sonos server
(`set_volume.level`) — not server-specific.

Reproduce: any agent on the Claude MAX provider with an MCP source whose
tools declare `type: integer`; drive a multi-step browsing task and watch the
tool results for `is not of type 'integer'`.

Fix: a schema-guided coercion pass immediately before `jsonschema_validate`
— when a property's schema declares `integer` / `number` / `boolean` and the
supplied value is a string that parses cleanly to that type, convert it;
leave everything else untouched. One direction only (string → declared
scalar), so `test_type_mismatch_raises_argument_error` (int supplied for a
`string` field) stays red-on-mismatch. Shape it as a pure stdlib helper
(e.g. `the_one/mcp/_arg_coerce.py`) with its own unit tests.

## Evidence

- `the_one/mcp/client.py:call_tool` — "L6b: input validation against the tool's JSON Schema … `jsonschema_validate(arguments, tool_meta.input_schema)` … `raise MCPArgumentError(...)`"
- `the_one/agent/core.py:_execute_tool` — `content=self._govern(f"[error] Tool execution failed: {e}")` is the wrapper the model sees
- `the_one/llm/anthropic_provider.py` — `ToolCall(id=block.id, name=block.name, arguments=block.input)`: arguments pass through untouched; the same session mixes int and string values from this one path, so the stringification is the model's, not ours
- Packaged-app data dir (`AppData/Local/the-one/the-one.db`), sessions on agents "School Checkins" and "Sonos Agent", 2026-09-04 → 2026-09-14: four sessions, 168 rejections; the 2026-09-14 session sent `wcId` as a string 55 times vs 39 as an int, with `enumerateTabs` results in the same session showing `"wcId":7` numeric
- `tests/test_mcp_client.py` L6b class ("jsonschema-driven input validation") — the existing pin the coercion must not break

## Corrective Action
*(written at completion)*

## Verification
New unit tests for the helper (numeric string → int/float, `"true"`/`"false"`
→ bool, non-parsing strings and non-string values left as-is, nested objects
/ arrays untouched unless the schema describes them) plus a `call_tool` test
that a `{"x": "42"}` argument for an `integer` field reaches the wire as
`42`. Existing L6b tests stay green; `ruff check` / `ruff format --check`
clean.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
