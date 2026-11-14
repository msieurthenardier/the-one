# Leg: hat

**Status**: completed
**Flight**: [Port to the mcp 2.x SDK at parity](../flight.md)

## Objective
With the operator, confirm against real servers and the real Windows build that the port to `mcp` 2.3.0 changed nothing an operator relies on: Cloudflare sign-in, a handshake-era stdio server, and the packaged build's doctor gate.

## Context
- This is an interactive HAT leg. The Flight Director guides the operator one step at a time and fixes issues inline (spawning a Developer for code changes). Fix-vs-feature calls are made out loud.
- Apparatus:
  - A dedicated dev instance run from the worktree: port **8492**, scratch data directory `/tmp/claude-1000/-home-<user>-projects-the-one/875c2e63-eac8-4b6b-9502-e3cecc18639d/scratchpad/hat-data`. It never uses 8484/8485 or the default data dir.
  - The operator's browser, signed in through a minted handoff URL.
  - The `the-one` Concourse target for the Windows lane.
- From the flight log, watch for: Test connection with revoked tokens now keeps the stale secrets until the new sign-in replaces them. The operator should still get a fresh consent URL.
- Out of scope: protocol 2026-07-28 (Flight 2). Every server shows "protocol 2025-11-25" or older in this flight, by design.

## Prerequisites (re-verified at leg start)
- [x] `mcp.cloudflare.com/mcp` reachable from this host (a bare POST answered 401, as expected for an unauthenticated request).
- [x] The operator has a Cloudflare account and can sign in.
- [x] `fly -t the-one` is logged in (the operator runs `fly -t the-one login`) and a `platform: windows` worker is up.

## Acceptance Criteria (verification steps)
- [x] V1 (Windows lane): `fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i repo=<clean export of HEAD>` succeeds. Its frozen doctor output includes `mcp sdk: OK` and all other needles, and an installer is produced.
- [x] V2 (Cloudflare sign-in), on the dev instance:
  - Library → MCP servers → Add: a streamable-http source at `https://mcp.cloudflare.com/mcp`.
  - The first Test connection opens the consent popup. After the operator signs in, the auto re-test shows "Connected" with a tool list.
  - The editor's server details show "protocol 2025-11-25" (or the server's older revision) and the server's name and version.
  - No error, no sign-in loop.
- [x] V3 (stale-token path, the flight-log watch item): revoke or clear the source's tokens as the operator chooses, Test again, get a fresh consent URL, and sign in to recover.
- [x] V4 (tool runs): a Cloudflare tool runs from an agent's chat, if the operator has a provider to configure on the dev instance. Otherwise this is recorded as covered by the unit and integration suite.
- [x] V5 (handshake-era stdio server): an stdio MCP server of the operator's choice connects, lists its tools, and a tool runs, from Test connection or chat.
- [x] V6 (optional, a preview of Flight 2): the operator's Sonos server connects and shows "protocol 2025-11-25". Flight 2 makes it show 2026-07-28.

## Fixes
Any defect found is fixed inline, re-verified, and logged here and in the flight log.
- **Fix 1**: the UI's consent-wait ceiling went from 15 s to 2 minutes (`mcp-server-editor.js`, `CONSENT_WAIT_MS = 120000`). The operator re-verified it after a hard reload. Also corrected the stale `CLAUDE.md` sentence.

## Results (2026-10-12)
- V1 PASS: the Windows lane, frozen doctor `mcp sdk: OK`, installer built.
- V2 PASS: Cloudflare sign-in end to end. The callback carried `iss=https://mcp.cloudflare.com`. The 2-minute wait was confirmed after fix 1.
- V3 COVERED BY TEST, not run live (operator): `tests/test_mcp_test_connection_stale_tokens.py` runs the real endpoint with revoked tokens and observes a fresh consent URL.
- V4 COVERED BY TESTS (operator: "no its fine"): tool runs are proven by the unit and integration suite.
- V5 and V6 PASS: the operator's Sonos MCP server connects and works on the 2.x client (handshake era, as Flight 1 intends).

## Post-Completion
On all steps passing: the leg status goes to `completed`, the flight log is updated, any fix and the stale `CLAUDE.md` sentence (it still calls the `mcp sdk` gate "the next leg's") are committed, and the flight lands.
