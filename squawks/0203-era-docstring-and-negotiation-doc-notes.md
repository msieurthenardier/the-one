# Squawk 0203: Stale `_era.py` docstring and three negotiation doc gaps

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-13
**Completed**: —

## Report
These are doc gaps left by Mission 29 Flight 2, found in its debrief:
1. **The `the_one/mcp/_era.py` module docstring is out of date.** It still says "nothing reads or writes the map yet beyond that", which is false since leg 2.
2. **`the_one/agents.md`'s "Automatic protocol negotiation" bullet doesn't say a remembered *modern* era still runs the full policy.** Only a remembered handshake era skips discover, so a modern server costs one discover round trip per connect. That is cheap and deliberate, but undocumented.
3. **The same bullet doesn't say the era map is process-global and unlocked.** Being unlocked is safe only because there is a single asyncio event loop.
4. **The same bullet overgeneralises "a modern `server/discover` stamps `serverInfo` with `version: ''`".** That holds for the `mcp` 2.3.0 SDK's own servers. In the HAT, real modern servers reported real versions: sonos 0.6.1, docs-ai-search 0.4.13 and cloudflare-api 0.1.0.

## Evidence
- `the_one/mcp/_era.py:7-8` — "Leg 1 creates the module so the failure matrix's ``forget_era`` cells exist; nothing reads or writes the map yet beyond that."
- `the_one/agents.md` "Automatic protocol negotiation (Mission 29 Flight 2)" bullet (~`:1066`): "A remembered handshake revision makes `connect` call `initialize()` directly"; "A modern `server/discover` stamps `serverInfo` with `version: ''`".
- `the_one/mcp/_negotiate.py::negotiate`: only a handshake `remembered` takes the shortcut.
- The Flight 2 flight log's HAT entry has the serverInfo versions.

## Corrective Action
*(written at completion)*

## Verification

## Sign-Off
*(written at completion)*

## Disposition
