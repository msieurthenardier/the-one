# Squawk 0372: MCP editor keeps showing protocol 2025-11-25 after the server moved to a newer protocol

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-17
**Completed**: —

## Report
A local-command (stdio) MCP server was upgraded from a release that speaks protocol 2025-11-25 to one that speaks a newer protocol. After the upgrade the operator pressed Test several times, some time apart. The Server section's Version row shows the new server version, but its Protocol row still reads 2025-11-25.

Expected: a Test negotiates again from scratch, so the Protocol row shows the revision the upgraded server now offers.

Not reproduced, and the root cause is not known. The Version row moving proves the Test reached the new server and rewrote the cache, so the stored `protocol_version` itself is 2025-11-25: the negotiation ended on the older handshake. The first step is to reproduce with the operator's server (its name and command are still to be supplied) and capture what the server answers to `server/discover`.

Scope note: if the cause is the negotiation policy itself (when a failed discover may fall back to the older handshake, or whether a downgrade is shown to the operator), that is a design decision on the shared connect path and this squawk is escalated, not grown.

## Evidence
- `the_one/interfaces/web/api.py::_build_and_test_stdio_mcp` — builds `MCPClient(..., fresh_negotiation=True)` and writes `server_info` and `protocol_version` in one `merge_cache`, so the two rows cannot come from different Tests.
- `the_one/mcp/_negotiate.py::_full_policy` — any `MCPError` from `send_discover` that is not a 401 or a modern-only `-32022` falls through to `session.initialize()`, and an invalid discover result or one with no modern version does the same. Each of these ends on a handshake revision with no error and nothing shown to the operator.
- `mcp.client.session.DISCOVER_TIMEOUT_SECONDS` is 10.0 (mcp 2.3.0) — a discover probe that times out is one such silent fallback. Unverified as the cause; repeated Tests of an already-installed server make a cold-start timeout less likely.
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-info.js::update` — Version and Protocol are painted from the same cache object in one call (`App.ui.facts.set` replaces every row), so the display is not the stale part.

- **Reproduction, 2026-11-17** (scratch instance on port 8485 with its own data directory, this tree at `bc497ab2`, the public `@modelcontextprotocol/server-everything` from npm; API calls only, `POST /api/mcp-sources/{id}/test/connect` then `GET /api/mcp-sources/{id}`):
  - Local command, `npx -y …@latest` (2.3.0): Test takes 3 to 5 s; the record holds protocol `2026-07-28`, server version 2.3.0, 22 tools. The negotiation works.
  - The same server started 4 s late (`sh -c "sleep 4; exec npx -y …@latest"`): Test takes about 8 s; still `2026-07-28`, 22 tools.
  - **The same server started 12 s late: Test succeeds in about 16 s and the record holds protocol `2025-11-25` with server version 2.3.0 and 16 tools.** Two Tests in a row gave the same result. This is the operator's symptom exactly: a new Version row beside an old Protocol row, with no error. The session also has six fewer tools, so it is not only a display matter.
  - HTTP, the saved server's process replaced by 2.3.0 while the cache still held 1.0.0 and `2025-11-25`: the first Test wrote `2026-07-28`, 2.3.0 and 22 tools. No fault on that path.
- Cause of the 12 s case: `mcp.client.session.DISCOVER_TIMEOUT_SECONDS` (10.0) runs from the moment the process is spawned. A local-command server that needs more than 10 s to start (a package runner's download or registry check, a slow disk) has not answered `server/discover` in time, and `_negotiate.py::_full_policy` then calls `session.initialize()`, which the now-started server answers on the older revision. Every Test spawns the server again, so every Test repeats it.
- Still to confirm: that this is what happens on the operator's server. The tell is a Test that takes more than about 10 s on it.
- Found beside it: a bare `npx -y <package>` reuses a version already in the npx cache and does not move to the newest release (this host ran 1.0.0 while 2.3.0 was published). That is npx's behaviour, not the app's, and it does not explain a Version row that did change; the Command hint could say so.

## Disposition
Recommended for escalation (2026-11-17), awaiting the operator's word; status stays `open` until then. The scope note above applies: the cause is the negotiation policy on the shared connect path. The fix is a design decision with more than one reasonable answer (give a local-command server's first `server/discover` the same time as its start-up, try `server/discover` once more after a fallback handshake, show the operator that a connection fell back), so it fails the "no design decisions" and "bounded blast radius" criteria. Vehicle: a sortie.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
