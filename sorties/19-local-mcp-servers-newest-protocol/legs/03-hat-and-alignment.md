# Leg: hat-and-alignment

**Status**: completed
**Flight**: [Local-command MCP servers: newest protocol and Forget](../flight.md)

## Objective
The operator walks the slow-server fix, the fallback note and the Forget button on a scratch instance, one step at a time, and anything they flag is fixed before the sortie lands.

## Context
- Interactive leg: the Flight Director presents one step, the operator performs it and reports, then the next. No Developer runs this leg; a Developer is spawned only for a fix.
- Legs 1 and 2 are implemented and reviewed (code and accessibility, both confirmed), and the closing gate has finished on the final tree, before the instance for this leg is started (sortie 18 debrief, recommendation 4: the gate and the HAT do not overlap).
- **Fix or feature.** A look-and-feel fix found here is made inline. A request that adds behaviour gets a scoped design review first. A fix that touches more than the MCP editor's two area modules (the connect path, a shared control, another page) gets a Developer design-review pass before it is built.
- **Gate for a fix.** A fix to the editor re-runs the `mcp-connection`, `mcp`, `library`, `agents` and `agent-tabs` lanes and the unit tier. A fix to the connect path or to anything shared re-runs the full gate. No source edit while a test run is on the host.
- **Contracts the tests rely on** (a change to one is a deliberate re-author of tests, not an inline tweak): the testids `forget-mcp-connection-btn` and `mcp-server-protocol-fallback`; the labels "Forget tools list" and "Forget tools list?"; the message "Tools list forgotten"; the note's exact sentence; the stored key `protocol_fallback` with the value `no_answer`; the 20 s window (the 30 s limit less the 10 s reserve).
- **Open choices for the operator** (from the reviews):
  1. The note appears silently: a screen-reader user who presses Test hears the Test's result but not the note. The accessibility reviewer rated this non-blocking and, if an announcement is wanted, advises adding the note's sentence to the Test result's spoken text when the record holds the key (not making the note itself a live region). That adds behaviour to the status module, so it would go through the fix-or-feature call.
  2. The note's wording.
  3. A local-command server that fell back in chats and was never tested has no Forget button until a Test (an accepted gap of the design).

## Inputs
- The sortie branch with legs 1 and 2 and the review fixes in the working tree, gated.
- A scratch dev instance: port 8485, a scratch data directory under the home folder, `THE_ONE_DEV_MODE=true`, started from a scratch working directory (never `make up`, never port 8484, never the default data directory). An API credential minted for that data directory and a one-time handoff link for the operator's browser.
- The npm registry reachable from this host (checked on the day, before the walk): the real server is the published `@modelcontextprotocol/server-everything`, the operator's own server.
- Four seeded servers, all with network access allowed in the sandbox settings:
  - `everything-prompt`: local command, `npx -y @modelcontextprotocol/server-everything@latest`.
  - `everything-slow`: the same server started 12 s late (a custom command, `sh -c "sleep 12; exec npx -y …@latest"`). This is the operator's case.
  - `everything-late`: the same server started about 18 s late, so its total start is past the 20 s window and inside the 30 s limit.
  - `http-fixture`: an HTTP server with no sign-in (the repo's own `tests.fixtures.mcp.rich_http_server` on a scratch port), for the unchanged-behaviour step.

## Outputs
- The operator's verdict on each step, recorded in the flight log.
- Any fixes, each tested and reviewed, on the sortie branch.

## Acceptance Criteria
- [x] Step 1 [never tested → tested, prompt server]: `everything-prompt` opens with no Server section and no Forget button. After Test: Connected; Protocol 2026-07-28; the full tool list (22); "Forget tools list" beside the status line; no warning note; no error message.
- [x] Step 2 [the operator's case]: `everything-slow`, Test (it takes about 16 s): Connected; Protocol 2026-07-28; 22 tools; no warning note. Before this sortie the same server gave 2025-11-25 and 16 tools.
- [x] Step 3 [past the window → fallback, with the note]: `everything-late`, Test (it takes about 22 to 25 s): Connected; Protocol 2025-11-25; fewer tools (16); the warning note sits under the facts and before Instructions, with the approved sentence; no error message. It looks right in the light and the dark theme.
- [x] Step 4 [fallback → cleared by Forget]: on `everything-late`, "Forget tools list" arms as "Forget tools list?" and on the second press the button, the Server section and the note disappear, the Tools section shows its "Press Test…" hint, the "Tools list forgotten" message shows, and keyboard focus is on Test.
- [x] Step 5 [Forget → Test, prompt server]: on `everything-prompt`, Forget, then Test: the button comes back as "Forget tools list" (one press arms it, it does not delete at once); Protocol 2026-07-28; no note.
- [x] Step 6 [HTTP unchanged]: `http-fixture`: Test, Forget, Test behave as before this sortie; no warning note at any point; "Reset connection" is not shown (no sign-in).
- [x] Step 7 [an agent sees the full list]: an agent with `everything-slow` switched on shows that server's full tool list in its Tools tab.
- [x] Step 8 [open choices]: the operator decides open choices 1 to 3.
- [x] Every fix made during the walk has its tests, an independent review, and a green run of the gate named in Context. (No fix was made.)

## Verification Steps
- Each step is performed by the operator in their browser on the scratch instance and reported back; the Flight Director records the result and any wording the operator objects to.
- After steps 2 and 3 the Flight Director also reads the stored record through the scratch instance's `GET /api/mcp-sources/{id}` (`config._cache.protocol_version`, `protocol_fallback`, the number of tools) and records it beside the operator's report.
- After any fix: the gate named in Context, then the step is walked again.

## Implementation Guidance

1. **Check first**: the closing gate has finished and nothing else is running tests; the npm registry answers (`npm view @modelcontextprotocol/server-everything version`); ports 8485 and the fixture's scratch port are free.
2. **Start the instance** from a scratch working directory with the venv's `the-one serve`, port 8485, a scratch data directory, dev mode on. Record the PID of the listener (from the port, then its `/proc/<pid>/environ`, not from the shell's `$!`). Mint the credential with `the-one rotate-api-credential` against that data directory. Confirm `/api/live`.
3. **Start the HTTP fixture** on a scratch port, in its own process group; record the group id.
4. **Seed** the four servers through `POST /api/mcp-sources` with the credential. Run one Test of `everything-prompt` through the API before the walk so the package is already in the package runner's cache and the delays in steps 2 and 3 are the ones intended; then use the route behind Forget to return it to "never tested" for step 1.
5. **Hand the operator a link**: mint a one-time handoff URL (`POST /api/session/handoff`); a second browser or a fresh tab needs a second mint.
6. **Walk the steps in order**, one at a time. Static JS and CSS edits are live on the next page load in dev mode; a Python edit needs the instance restarted.
7. **Stop** the instance by its recorded PID and the fixture by its recorded group when the walk ends, remove the scratch folder, and say so.

## Edge Cases
- **Step 3's server starts inside the window after all** (a fast package runner): the result is 2026-07-28 with no note. Lengthen the delay by a second or two and test again; do not shorten the window.
- **Step 3's server takes longer than 30 s**: the Test fails with the existing timeout error. Shorten the delay and test again.
- **The registry is unreachable on the day**: the walk waits; do not substitute a different server for steps 2 and 3 (the point is the operator's own server).
- **The operator asks for the note to be announced** (open choice 1): new behaviour in the status module; a scoped design review comes first.
- **The operator wants different wording**: a text change in one area module and its tests; inline, with the `mcp-connection` lane and the accessibility reviewer's eye on the new sentence.

## Files Affected
- `sorties/19-local-mcp-servers-newest-protocol/flight-log.md` - the walk's results
- Source and tests only if a step fails or the operator asks for a change

## Citation Audit
- `CLAUDE.md` "Behavior-test credential convention" - a fresh `serve` data directory has no credential until `the-one rotate-api-credential` is run against it; `POST /api/session/handoff` with the bearer credential returns a one-time URL; `/api/live` needs no credential - verified
- `CLAUDE.md` "UI test apparatus" - port 8485 is the Flight Director's preview instance - verified
- Squawk 0372, Evidence - on a scratch instance the published 2.3.0 server as a local command with network access allowed connects in 3 to 5 s, and a custom command `sh -c "sleep N; exec npx -y …"` is accepted and runs in the sandbox - verified (run on 2026-11-17)
- `tests/browser/test_flow_studio_mcp_editor_status.py` (`real_http_server` fixture) - `tests.fixtures.mcp.rich_http_server --mode ok --port 0` serves an HTTP MCP server with no sign-in - verified

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
