# Squawk 0382: Editing a local-command MCP server's command is not treated as a change of server

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-18
**Completed**: 2026-11-23

## Report
When an MCP server's record is saved, the app decides whether the record now points at a different server, and if so drops what it had stored about the old one's connection (the last check, the auth posture and, since sortie 19, the protocol-fallback note). The rule compares the type and the URL only. A local-command server has no URL: its identity is its command and arguments. So after an edit that replaces the command (a different server altogether), the editor still shows the old server's last check, and the fallback note if there was one, until the next Test.

To reproduce: on a local-command server whose stored record holds a fallback note (or any last check), change the command or its arguments and Save. Expected: the stored last check and the note are dropped, as they are when an HTTP server's URL changes. Actual: both stay.

The gap is older than sortie 19; that sortie added one more stale fact to it. Found by the sortie 19 debrief's Developer. No test covers it.

Scope note: which keys identify a local-command server is a small judgement (the command and arguments, probably not the environment or the sandbox settings). If it turns out to need more than adding those two to the existing comparison, or if the tools list should be dropped as well, that is a design decision and this squawk is escalated, not grown.

## Evidence
- `the_one/mcp/service.py::_prune_cache_on_server_change` (moved out of `api.py::update_mcp_source` in Mission 36 F4 L4a) — `server_changed` compared the type and the `url` only; the keys dropped on a change are `last_check`, `auth_posture` and `protocol_fallback`.
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-info.js::update` — the note is shown whenever the stored cache holds `protocol_fallback: "no_answer"` beside a protocol.
- `sorties/19-local-mcp-servers-newest-protocol/flight-debrief.md`, "What Could Be Improved / Technical".

## Corrective Action
`the_one/mcp/service.py::_prune_cache_on_server_change`: when both rows are `stdio`, a changed
`command` (compared as stored) or changed `args` (`or []`, so absent and `[]` are equal) is also a
server change. The same three keys are dropped; env and sandbox are not part of the identity.
Both the PUT and a proposal (`change_mcp_source`) go through it.

## Verification
`tests/test_mcp_service.py::test_a_stdio_command_or_args_change_prunes_the_old_servers_cache`
(command and args, PUT and change), `test_a_stdio_env_or_sandbox_change_keeps_the_cache`,
`test_a_stdio_args_absent_to_empty_is_not_a_change`. The first fails with the old comparison
restored (falsified). Three existing tests pinned the defect and were adjusted with the operator's
authorization: `tests/test_mcp_last_check.py::test_put_server_change_drops_the_protocol_fallback_note`
and `test_sequence_keeps_every_key_then_reset_drops_all`, and
`tests/test_mcp_service.py::test_only_the_named_fields_change_and_rows_merge_per_row`.

## Sign-Off
- **Fixed in:** Mission 36 Flight 5, Leg 1b.
- **Reviewed:** by the Flight 5 Batch A Reviewer (Sonnet): `[HANDOFF:confirmed]`, 2026-11-23.
  The Reviewer confirmed that the three adjusted tests keep their subjects.
- **Committed:** in the Flight 5 Batch A checkpoint commit (its ref is in the flight log).
