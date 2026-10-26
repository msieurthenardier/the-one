# Squawk 0203: Stale `_era.py` docstring and three negotiation doc gaps

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-13
**Completed**: 2026-10-25

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
Documentation only, no logic change (folded into Mission 31 Flight 5 leg 12, operator decision 2026-10-25):
1. `the_one/mcp/_era.py` module docstring rewritten: it now says who reads and writes the map (`era_for` in `connect`, `remember_era`/`forget_era` from the connect path, update, delete, Reset and the mid-use failure paths).
2. `the_one/agents.md` "Automatic protocol negotiation": a remembered modern era still runs the full policy (one discover round trip per connect, deliberate).
3. The same bullet: the era map is process-global and unlocked, safe only on a single asyncio event loop.
4. The same bullet: the `version: ''` stamp is the `mcp` 2.3.0 SDK's own servers; real modern servers report real versions (sonos 0.6.1, docs-ai-search 0.4.13, cloudflare-api 0.1.0).

## Verification
`git diff` shows only the docstring and `agents.md` text; `tests/test_mcp_era.py` and `make test-unit` pass (see the Mission 31 Flight 5 leg 12 log); `make gate` after the main merge: unit 7659 passed, 15 skipped; browser `PARALLEL_RESULT rc=0 total=1579s`.

## Sign-Off
**Reviewer**: Mission 31 Flight 5 batch B6 Reviewer (Haiku; docs and docstring only, no security surface)
**Verdict**: `[HANDOFF:confirmed]`: the docstring matches `era_for`/`remember_era`/`forget_era`'s callers; no logic changed
**Commit**: the Mission 31 Flight 5 leg 12 checkpoint commit (B6)

## Disposition
