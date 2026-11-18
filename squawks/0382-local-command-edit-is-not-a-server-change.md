# Squawk 0382: Editing a local-command MCP server's command is not treated as a change of server

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-18
**Completed**: —

## Report
When an MCP server's record is saved, the app decides whether the record now points at a different server, and if so drops what it had stored about the old one's connection (the last check, the auth posture and, since sortie 19, the protocol-fallback note). The rule compares the type and the URL only. A local-command server has no URL: its identity is its command and arguments. So after an edit that replaces the command (a different server altogether), the editor still shows the old server's last check, and the fallback note if there was one, until the next Test.

To reproduce: on a local-command server whose stored record holds a fallback note (or any last check), change the command or its arguments and Save. Expected: the stored last check and the note are dropped, as they are when an HTTP server's URL changes. Actual: both stay.

The gap is older than sortie 19; that sortie added one more stale fact to it. Found by the sortie 19 debrief's Developer. No test covers it.

Scope note: which keys identify a local-command server is a small judgement (the command and arguments, probably not the environment or the sandbox settings). If it turns out to need more than adding those two to the existing comparison, or if the tools list should be dropped as well, that is a design decision and this squawk is escalated, not grown.

## Evidence
- `the_one/interfaces/web/api.py::update_mcp_source` — `server_changed = updated.type != existing.type or (updated.config or {}).get("url") != (existing.config or {}).get("url")`; the keys dropped on a change are `last_check`, `auth_posture` and `protocol_fallback`.
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-info.js::update` — the note is shown whenever the stored cache holds `protocol_fallback: "no_answer"` beside a protocol.
- `sorties/19-local-mcp-servers-newest-protocol/flight-debrief.md`, "What Could Be Improved / Technical".

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
