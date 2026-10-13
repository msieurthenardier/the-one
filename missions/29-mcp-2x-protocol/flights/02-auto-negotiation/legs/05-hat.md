# Leg: hat

**Status**: completed
**Flight**: [Automatic negotiation of protocol 2026-07-28](../flight.md)

## Objective
With the operator, confirm against real servers and the real Windows build that automatic negotiation works (flight DD14).

## Context
- **This is an interactive HAT leg.** The Flight Director guides the operator one step at a time, fixes issues inline (spawning a Developer for code changes), and makes fix-vs-feature calls out loud.
- **The apparatus:**
  - **The dev instance**, from the worktree on port **8492**, with scratch data dir `…/scratchpad/hat-data` (holding the operator's Cloudflare and Sonos sources). It is restarted on Flight 2's code (`bf42907`) before step 1, because Python changes need a restart. It never uses 8484/8485 or the default data dir.
  - **The operator's browser**, signed in through a minted handoff URL.
  - **A real `mcp==1.28.1` stdio server** for H4, at `~/.cache/the-one-hat/legacy_server.py`, run by `~/.cache/the-one-hat/mcp1x/bin/python`. It lives under `$HOME`, not `/tmp`, because the stdio sandbox mounts a fresh tmpfs at `/tmp`.
  - **The `the-one` Concourse target** for H5.
- **Expected observations:**
  - A modern server's editor may show no version on the server-details line: the modern serverInfo stamp carries `version: ''`.
  - The 1 MiB SSE cap only applies on the handshake era.

## Prerequisites (re-verified at leg start)
- [x] The dev instance has been restarted on `bf42907` and is serving.
- [x] The operator has a model provider to configure on the dev instance.
- [x] Cloudflare and the Sonos server are reachable.
- [x] The `mcp==1.28.1` server starts (`mcp1x/bin/python legacy_server.py`).
- [x] `fly -t the-one` is logged in and the Windows worker is up.

## Acceptance Criteria (verification steps)
- [x] H1, Sonos: Test connection shows "protocol 2026-07-28", and a Sonos tool runs from an agent's chat. The chat goes through the pool, which exercises the era memory. Record whether the version line is blank.
- [x] H2, Cloudflare: a sign-in under negotiation completes, and a Cloudflare tool runs from chat. Record the protocol Cloudflare negotiates.
- [~] (skipped by operator) H3, stale tokens (live): the operator revokes the-one's Cloudflare access. Test then clears the stored sign-in and offers a fresh consent URL, and signing in recovers.
- [x] H4, a real 1.x server: a stdio source running the `mcp==1.28.1` server connects on its handshake revision (2025-11-25), `echo` runs, and a second Test shows no added delay.
- [x] H5, Windows: the installer-build lane re-run passes, and its frozen doctor shows `mcp sdk: OK — …, modern 2026-07-28, httpcore2 …`.

## Fixes
Each defect is fixed inline, re-verified, and logged here and in the flight log.

## Post-Completion
When every step passes:
- the leg goes to `completed`;
- the flight log is updated;
- any fixes are committed;
- the flight lands.
