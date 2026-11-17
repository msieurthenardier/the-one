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

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
