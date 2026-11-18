# Flight Debrief: Local-command MCP servers: newest protocol and Forget

**Date**: 2026-11-18
**Flight**: [Local-command MCP servers: newest protocol and Forget](flight.md)
**Status**: landed
**Duration**: 2026-11-18 (charter, design, three legs, landing, debrief)
**Legs Completed**: 3 of 3
**Plugin version**: mission-control 1.2.4

The debrief ran on the flight branch before the merge, so it is part of the sortie's PR (#379). The version bump to 0.16.6 was added to the same branch at the operator's request.

## Outcome Assessment

### Objectives Achieved
- A local-command MCP server that has not answered the newer-protocol check yet is asked again, until 20 s after the connect began, before the app falls back to the older handshake. The operator's case is fixed in a real run: the published server started 12 s late connects on 2026-07-28 with 22 tools, where it used to connect on 2025-11-25 with 16 and no error.
- A fallback caused by no answer is a recorded fact: on the client, in the rule for what is remembered, and in the stored record that the editor reads. The MCP editor's Server section shows one warning line for it.
- "Forget tools list" is shown on a local-command server with a stored tools list.
- HTTP servers' negotiation is unchanged by construction: only a local-command connect is given a deadline, and without one the policy is the same code path as before.

### Charter Criteria

| Criterion | Result | Note |
|---|---|---|
| A local-command server that takes 12 seconds to start connects on 2026-07-28 with its full tool list, from Test and from a chat | **Met for Test; met by tests only for a chat** | Test: HAT step 2 with the real published server (stored record 2026-07-28, 22 tools, no fallback key) and `tests/test_mcp_negotiation_fallback.py::test_stdio_slow_dual_era_server_ends_modern_with_more_than_one_probe`. Chat: a chat's pooled client runs the same `MCPClient._connect_once`, which the client-level tests drive directly; no chat connect to a slow server was run. HAT step 7 showed an agent's Tools tab, which is not a chat connect |
| An older-protocol server still connects, and a server that starts promptly connects no slower than today | **Met by tests** | `::test_stdio_prompt_servers_send_one_probe_and_record_no_fallback` (one probe, as before) and the handshake-only fixture tests. HAT step 1 showed a prompt server at about 3.4 s; no before-and-after timing was taken |
| "Forget tools list" is shown on a local-command server that has a stored tools list; pressing it clears the list, the per-agent tool lists and the remembered protocol, and it returns after the next Test that connects | **Met** | HAT steps 4 and 5; `tests/browser/test_flow_studio_mcp_editor_status.py` (the rewritten predicate test, the Forget test, the Forget-then-real-Test test). That the route clears the per-agent lists and the remembered protocol is its existing behaviour, covered by its existing tests, not re-proved here |
| When a local-command connection falls back for lack of an answer, the Server section says so in plain words | **Met** | HAT step 3 (stored record 2025-11-25, 16 tools, `protocol_fallback: "no_answer"`, the note shown in both themes); `tests/browser/test_flow_studio_mcp_editor_server_info.py` |

Constraints: all held. No private SDK module is imported; the `mcp` pin is unchanged; an HTTP connect gets no deadline; the connect is still under the one 30 s limit.

Checkpoints: all four met.

Not verified by anyone: the operator's own app on Windows, where this bug was reported. Every run in this flight was on Linux.

## What Went Well
- **The reproduction came before the design.** Squawk 0372 had the cause, the numbers and a way to produce it on demand (a start delay in front of the real server) before the charter was written. The HAT reused the same apparatus, and the dry run before the walk showed the fix on the operator's own server.
- **Two review layers each found the flight's most serious flaw at its level.** The Architect's flight review found that a timeout cannot be told from a server's own error by its code (a re-send loop would have spun). The Developer's leg review found that HTTP servers would have been swept into the new rule, against a charter constraint, and that the existing tests would have stayed green by accident.
- **The recorded consumer searches worked.** The flight listed its search patterns and folders in the Prerequisites (sortie 18's lesson). Neither leg and neither review found a consumer the searches had missed.
- **The outcome object.** Reporting the fallback through a small object the policy fills in, instead of changing `negotiate`'s return type, left 28 test call sites untouched.
- **The gate ran once, on the final tree, on a quiet host, before the HAT, by someone other than an implementer.** No lane was over budget and nothing flaked. The debrief could reuse it.
- **The HAT needed no fix.** Eight steps, all passed.
- **Falsification that was honest about its misses.** Two falsifications did not behave as predicted (one needed a second edit, one failed a different test than the leg named); both were reported as such and judged by the Reviewer.

## What Could Be Improved

### Process
- **A commit missed its PR.** The Flight Director pushed one more commit to the sortie 18 debrief branch after telling the operator the PR was ready; the operator merged minutes before the push. The commit (squawk 0373's last evidence) had to ride on this sortie's branch. After a PR is handed over, later changes need a new branch or a plain "the PR changed" message.
- **Squawk 0373 was logged as a defect without the one fact its rule depends on.** The first interview asked the server's type for the other bug only. The Forget button has only ever existed for HTTP servers; the operator's server was a local command. A day and one reproduction went into a symptom that was by design.
- **The fix pass after the review was not re-reviewed.** It changed four tests' limits and one comment, and the gate ran after it. Recorded because the workflow has no rule for a change made after `[HANDOFF:confirmed]`.
- **A Developer edited sortie files with `sed`, against the brief.** The shell-write hook does not cover `sorties/` or `squawks/`. The log was intact.
- **Idle notifications.** Each build leg's Developer stopped four or five times to wait on its own test run, and each stop woke the Flight Director with nothing to act on.

### Technical
- **Editing a local-command server's command is not treated as a change of server.** `api.py::update_mcp_source`'s rule compares the type and the URL only. After a command or arguments edit the stored `last_check`, the Server facts and now the fallback note still describe the old server until the next Test. The gap is older than this flight; the flight added one more stale fact to it. No test covers it (squawk 0382).
- **"Twice in a row" is approximate.** The count goes up once per successful no-answer connect of any client. Two agents' pooled clients that connect to the same slow server at the same moment (each spawns its own process) reach 2 from what the operator would call one slow start, and the older protocol is then remembered for the run. A Test also counts: two unchanged Tests that both fall back arm the memory for chats. A failed connect resets the count; a cancelled one does not, by design. None of this is written in `the_one/agents.md`.
- **The count may not be worth its state.** It helps only a local server that never answers the check at all; a server that follows the protocol answers with an error at once. The debrief Architect, having seen the code, would have taken "never remembered": no state, and no Test-arms-chats subtlety. Kept for now; see Recommendations.
- **One probe is outside the reserve.** The probe the existing recovery sends after a refused `initialize` is bounded by the SDK's 10 s and the connect's 30 s limit, not by the window. A server that stalls there fails the connect at 30 s. The design's sentence "the handshake keeps the full reserve" does not hold on that path. Accepted; the server has just answered, so it is up.
- **Test-shaped production code.** `_protocol_fallback_of` (a `getattr` with a type check) and the numeric guard on `timeout_seconds` exist because about a dozen fake clients and some tests pass objects the real code never sees.
- **`_negotiate.py` now carries two departures from the SDK function it ports.** The parity test runs only the no-deadline half. The re-send exists because the SDK's probe timeout is a module constant; if a later SDK takes a timeout argument, the loop becomes one call.
- **`_probe` has a dead assignment** (the flag is cleared again after a successful send), and the reason the first probe is unbounded is in an inline comment, not in the module docstring's "Patient probe" passage. `remember_era` now has no caller outside tests.
- **The chat-only gap is real.** A fallback that happens only in a chat leaves no trace anywhere: no note, no log line. The operator accepted it at the HAT.
- **Not tested**: a command edit with a stored note; two clients connecting at once; a keyboard-only walk of Forget on a local-command server (the accessibility review was by reading).

### Documentation
- `the_one/agents.md` does not say that a Test's result counts toward the "twice in a row" rule, that an agent Test with per-agent credentials never changes the shared note, or that "in a row" means successive successful connects.
- `_era.py`'s docstring says the unlocked maps are safe because there is one event loop. True for data races; it should also state the count's meaning.
- The flight artifact's DD2 says the handshake keeps the full reserve; see the note in Technical.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| DD3 went against the Architect's recommendation ("never remembered") | The Flight Director weighed the cost to a local server that ignores the check: the full window on every connect | No. Take the reviewer's simpler option unless a measured cost says otherwise |
| "No answer" exists only when a deadline was given (added at the leg review) | As first written, HTTP servers would have fallen under the new rule | Yes: when a rule is meant for one transport, say so in the criterion and prove the other transport with a test that would fail |
| The first probe of each attempt is unbounded by the policy, not only the very first | The Developer's reading of the leg; keeps the no-deadline path identical | No (accepted; documented) |
| Leg 2 was drafted while leg 1 was being built, and finalised after it landed | The two legs touch different files; the wait was otherwise idle | Yes, when the legs share no file and the citations into shared files are re-checked |
| The fix pass ran only the affected unit files; the Flight Director ran the full gate after it | One gate on the final tree instead of a unit tier twice | Yes: one named gate on the final tree beats a partial run by each fixer |
| The debrief reused the closing gate | It was on the final code, started quiet, and only artifacts changed after it | Yes (the crew file's rule, used as written) |
| The version bump was committed on the sortie branch before the merge | Operator's request; v0.16.4 shipped the same way | No rule needed |
| AC3 of leg 2 used a real local-command Test in a browser test | It ran in about 4 s and was reliable | Yes: prefer the real fixture when it is fast |

## Key Learnings
- **Ask for the fact the rule turns on.** For a "the button is missing" report, the server's type and what is shown in its place settle it in one message. Squawk 0373 spent a day without them.
- **A constraint needs a test that would fail.** "HTTP is unchanged" was a charter line, and the first design broke it invisibly: the existing HTTP tests timed out at 0.5 s, under the new 1 s floor. The leg now has a test with a timeout longer than the floor.
- **Shorten every clock a test depends on, and write down the slack.** Patching the SDK's probe timeout alone did not shorten the window. The fix pass's table of window, delay, limit and slack per test is the form to keep.
- **Reproduce with the operator's own server when it is public.** The published package behind a `sleep` gave the bug, the fix check and the HAT from one apparatus.
- **A stored fact with several writers needs every writer to clear it.** Three writers and one update rule delete the fallback key; a fourth place (a command edit) was missed because it was already missing for the older facts.

### Test metrics
Reused from the flight's closing gate, as the crew file allows: it ran on the final code (`75d9456c`'s tree; only artifacts and the version line changed after it), unit tier first, with no other test process on the host. Nothing was run for the debrief.
- **Unit tier** (start load 0.82): 10263 passed, 15 skipped, 0 failed, 299.4 s. Prior: sortie 18 debrief 10222 passed, 302.4 s (loaded, one flake); sortie 17 10220, 283.0 s; sortie 16 10137, 271 s alone. The count rose by 41 (42 test functions in the diff). The new real-fixture tests add about 27 s of real time. The tier is at its 300 s standing target with no room left.
- **Browser gate** (start load 0.87): `PARALLEL_RESULT rc=0 total=2179s lanes=20 failed=-`; no lane over budget. Prior: sortie 18 debrief 2643 s (loaded, one flake), sortie 18 closing gate 2240 s (loaded), sortie 17 2349 s (loaded), sortie 16 2180 s (load 0.95). This matches the best earlier reading.
- **Whole gate**: 2496 s, about 41.6 minutes, against the 43-minute target: 84 s of room.
- **Lanes near their budgets**, all from this one quiet-start run: `mcp` 322 s of 330 (97.6%; this flight added nothing to it; squawk 0376 has the reading), `agent-routines` 287 of 300 (95.7%; untouched), `chats` 387 of 420 (92.1%; untouched). `mcp-connection`, which gained seven flow tests, is at 323 of 390.
- Skips: 15, the expected count under the namespace. Flakes: none in the gate. Squawks 0377 and 0378 (two load flakes from the sortie 18 debrief) did not recur.

## Methodology Observations
All on mission-control 1.2.4.

1. **Squawk skill, Verb: Log, step 2 (the brief interview: "what was observed, where, and how to reproduce").** The Flight Director asked one type question for two reports and attached the answer to the wrong one. The skill's interview does not prompt for the fact that separates "broken" from "by design" (here: which kind of server). Expected: nothing wrong with the skill's text; recorded because the cost was real. Cost: squawk 0373 stayed "not reproduced" for a day, one reproduction run was spent on it, and it ended as a request for new behaviour.
2. **Squawk skill, Verb: Escalate, into the sortie skill.** Two squawks, one a defect needing a design decision and one a small behaviour request, were escalated together into one sortie at the Flight Director's recommendation, against the sortie skill's "One Sortie, One Outcome". The Architect confirmed the gate held (one cluster of decisions plus a small independent rule), the second item was one low-risk leg, and nothing in the flight was confused by the pairing. A data point that a small rider on the same surface can share a sortie.
3. **Flight skill, Pre-Flight ("Prerequisites MUST be verified, not assumed"), applied with recorded searches.** The Prerequisites listed the patterns, folders and hits of each "who else uses this" search. Neither leg and neither review found a miss. A positive data point after sortie 18's observation 1.
4. **Agentic-workflow skill, Phase 2a step 3 (the Developer design review of a high-risk leg).** It found a high-severity flaw the Architect's flight review had not (a constraint silently broken for another transport). Cost: one more review cycle, about two and a half minutes of agent time. A positive data point for tiering the shared-path leg high.
5. **Agentic-workflow skill, Phase 2d steps 1 and 2 (review, then fix until the Reviewer confirms).** The Reviewer confirmed with two non-blocking notes; the Flight Director had them fixed anyway. The workflow does not say whether a change made after `[HANDOFF:confirmed]` needs another review. Expected: a stated rule (for example: test-only and comment-only changes after confirmation need the gate, not a review). Cost: none found; the choice is recorded in the flight log.
6. **Agentic-workflow skill, Phase 2d step 3 and Phase 2b (the gate and the HAT).** With the order fixed by the project (gate, then HAT instance) and the gate run by the Flight Director on the final tree, there was no overlap, no void lane time and no HAT fix waiting on a run. Sortie 18's observations 2 and 3 did not recur under the project rule. The methodology itself still does not name the order.
7. **Flight-debrief skill, Phase 2 ("run the full test suite once"), narrowed by the project crew file to "reuse the flight's gate".** Reused as written; it saved about 45 minutes and lost nothing, because the gate was complete, on the final tree and quiet at its start. Sortie 17's observation 5 (a reuse that would have hidden a failure) and sortie 18's observation 4 (a fresh run that only measured load) are the two failure modes; this is the case the narrowing was written for.
8. **Flight-debrief skill, Phase 1 step 3, and agentic-workflow Phase 3 step 7.** The recommended order (debrief on the flight branch before the merge) was taken this time, and the debrief's artifacts are in the flight's PR. A data point beside sortie 18's observation 5, where the merge and a release came first.
9. **Crew spawn behaviour.** A background Developer that stops to wait on its own test run produces a "completed" notification each time; two build legs produced nine such notifications before their real reports. Expected: one hand-back per agent. Cost: nine Flight Director turns with nothing to act on. Sortie 17's observation 6 is the same family. Which component owns it (the crew prompt's "run it in the background and wait" wording, or the harness) is not clear.
10. **Sortie skill, Verb: Plan, step 5 (re-check the gate after design).** The Architect was asked directly whether a second cluster of decisions had appeared, and answered no with reasons. Worked as written.

## Recommendations
1. **Decide the fate of the "twice in a row" count.** Either write its real meaning into `_era.py` and `the_one/agents.md` (successive successful connects of any client, Tests included), or drop it for "a no-answer fallback is never remembered", which the debrief Architect prefers now that the code exists. A design call on the shared connect path: part of the next flight that touches MCP negotiation, not a squawk. **Important.**
2. **Check the fix on the operator's Windows app after the release.** Press Test on the local server that showed 2025-11-25 and read the Protocol row and the tool count. No test or HAT step ran on Windows. **Important.**
3. **Treat a local-command server's command as its identity** in `update_mcp_source`'s server-changed rule (squawk 0382). **Important.**
4. **Give the unit tier room.** Trim the two 6.5 s real-fixture tests (a smaller window with a smaller delay proves the same wiring) and let the silent-drop and reset tests share spawns, or move the standing target to about 345 s (squawk 0383). **Important**: the next flight that adds a unit test crosses 300 s.
5. **Ask for the deciding fact when logging a "missing" or "stuck" report**: what kind of thing it is, and what is shown in its place. One line in the project's squawk practice. **Minor.**
6. **Do not push to a PR after handing it over** without saying so, or use a new branch. **Minor.**
7. **A fallback seen only in a chat should leave a trace** (a log line at least). A design call for a later flight. **Minor.**
8. **A per-server connect limit.** A package runner's first download can exceed 30 s whatever the window is. A design call for a later flight. **Minor.**

## Operator Interview
Skipped. The flight log is complete, and the operator's decisions (the charter, the mockup, the three HAT choices, the bump and the debrief before the merge) are recorded where they were made.

## Action Items
- [ ] Squawk 0382 (logged from this debrief): editing a local-command server's command or arguments is not treated as a change of server, so stale facts and the fallback note stay until the next Test.
- [ ] Squawk 0383 (logged from this debrief): the unit tier sits at its 300 s target; trim the real-time tests or move the target.
- [ ] Squawk 0384 (logged from this debrief): documents and tidy-ups from sortie 19 (`the_one/agents.md`, the `_era.py` and `_negotiate.py` docstrings, the dead assignment in `_probe`).
- [ ] Squawk 0385 (logged from this debrief): the shell-write hook does not cover `sorties/` and `squawks/`.
- [ ] Squawk 0381 (logged at landing): the contrast audit does not gate warning text on the warning banner's own tint.
- [ ] Squawk 0376 (open): re-budget the `mcp` lane; it now has a quiet-start reading of 322 s.
- [ ] Operator, after installing v0.16.6: Test the local server on the Windows app and say what the Protocol row and the tool count read (recommendation 2).
- [ ] Recommendations 1, 7 and 8 need design and are left for the next flight in this area.
