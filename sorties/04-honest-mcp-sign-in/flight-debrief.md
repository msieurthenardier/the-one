# Flight Debrief: Honest MCP sign-in in the desktop app

**Date**: 2026-10-15
**Flight**: [Honest MCP sign-in in the desktop app](flight.md)
**Status**: completed
**Duration**: 2026-10-14 (diagnosis, charter, design, leg 01, HAT) - 2026-10-15 (HAT fixes, final review, merge, release 0.11.8)
**Legs Completed**: 2 of 2
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved
In the desktop app, MCP sign-in now works through the system browser in both the MCP editor and chat. A server that rejects the configured key reports `MCPCredentialsRejected` ("The server rejected the configured credentials") instead of offering a sign-in. Merged as `8925e1a` (PR #288: leg 01 `d4059be`, HAT fixes `321b334`) and shipped in v0.11.8 (PR #295, tag `v0.11.8`, Windows installer published).

The HAT found and fixed two defects that had been on `main` since the pause/resume design (Mission 7 F5): the agent's pause state was set after the `yield`, so no resume ever ran after a real sign-in, and the resume left the "auth required" placeholder beside the real tool result, which providers reject. Without those fixes, chat sign-in could never have completed in the real app, with or without this sortie.

### Charter Criteria Assessment
| Criterion | Result | Note |
|---|---|---|
| 1. Desktop chat: "Log in" opens consent in the system browser; finishing consent resumes the tool call; no "Popup blocked" | **Met** | H2 passed on the fourth run, after the `ownFlow` amendment, the set-before-yield fix and the placeholder removal. The system browser opened by itself, which answered the open question about WebView2. The reconnect case is pinned by browser tests; it was not seen live (the desktop window has no reload). |
| 2. Desktop MCP editor sign-in opens the system browser, notices completion, lists tools with no re-test | **Met** | H1 passed first time. |
| 3. Rejected key with no OAuth metadata: plain "rejected the configured credentials" in the editor and chat, no sign-in button, not recorded as a sign-in server | **Met** | H3 passed first time on all three Test connection paths (cached `no_auth`, fall-through, Phase B after Reset) and in chat. After the reset path, `_cache` holds no `auth_posture`. |
| 4. Normal browser behaves as today; real OAuth servers still sign in | **Met** | H4: the popup opens, returns and closes; `echo` is listed. |

## What Went Well
- **The HAT did exactly its job.** The operator called it "a very good use of time, exactly what the HAT is for". It turned up the sortie's own chat regression, two pre-existing pause/resume defects, an operator-preference layout fix and an alignment fix, and it answered the WebView2 auto-open question.
- **Two Architect cycles hardened DD4 before any code existed.** They added the single `_signin_signal` factory, which covers the `DiscoverSignInRequired` route a Goldfinch-shaped server takes, and made `MCPCredentialsRejected` a subclass of `MCPConnectionError`, so existing catch sites needed no edits. H3 then passed first time on every path.
- **The leg design review caught DD4(c)'s evidence gap** (Phase B sends no operator headers, so its 401 proves nothing) before implementation. The rule was narrowed to this request's probe or fall-through evidence.
- **Root-cause investigation instead of guessing.** A read-only Opus investigator reproduced both H2 failures outside the desktop, on this branch and on a `main` export. It pinned the exact mechanisms: the 30 s connect `asyncio.timeout` cancelling the task group, and `_deferred_tool_calls` being set after the `yield`. Each fix was then specified exactly.
- **Falsification was routine.** Every new key test was shown to fail with its fix reverted. One accessibility test was caught not failing (an auto-retrying `expect` waited out the 2 s flash) and was rewritten.
- **The safety apparatus held.** The Windows test copy refused a non-sentinel root, and was bracketed by `snapshot --out`/`--compare` (clean, the installed app untouched). Processes were stopped by recorded PID. The test folder, which held the operator's provider tokens, was deleted at the end.
- **Diagnosis before charter.** The sortie grew out of a live support session. Reading the installed app's log, probing Goldfinch and hashing keys against Goldfinch's stored hashes showed the operator's "new key" was a revoked vault token. That kept the product fix separate from operator error.

## What Could Be Improved

### Process
- **Planning reasoned about frame sequencing, not about how long the server-side state behind a URL lives.** DD2's original "render the block for any frame with a consent URL" stored the SDK's in-band consent URL. That URL is dead after the client's 30 s connect timeout (`client.py:553`), while the pending-flow TTL is 10 minutes. Both constants were in the cited code, and the charter itself names the pending-flow lifetime. A lifetime-and-producer check would have caught it: for each server-issued URL or token the UI keeps, name every producer, what backs it and what ends it.
- **"Why does `main` work?" was not asked.** On `main`, the pause frame (`consent_url: null`) overwrote the dead URL, so "Log in" started a fresh, working flow. The sortie's per-flow replay map preserved the dead URL and turned a working accident into a regression.
- **Criterion 1 depended on a path that had never run in the real app.** The pause → resume path was assumed to work. Nothing in planning asked whether it had ever completed end to end with real components. It had not.
- **Too many restarts of the test copy.** The HAT needed a fresh root and five syncs and restarts, with a manual clear of the WebView2 cache each time; a desktop window has no hard reload. The first fixture runner also produced a false H2 failure: it accepted the old token again before the click, so sign-in was never needed. A committed, reviewed HAT fixture runner would have avoided that.

### Technical
- **Debt introduced or exposed:**
  - **`consent-link.js` is a third copy of the consent-and-copy block,** after `provider-editor.js::buildConsentBlock` and the editor's old button. Mission 31's consolidation should pick it up.
  - **`ownFlow` in `chat.js` is a frontend guard against backend in-band behaviour.** It should become defence-in-depth once the #290 direction lands (the chat/pool `redirect_handler` raises instead of waiting).
  - **`api.py::test_mcp_connection` keeps growing:** three posture paths, a private sentinel on the consent future, a `rejection_evidence` flag and `_clear_auth_posture`, around a ~300-line function. It is a candidate for a phase-based extraction.
  - **DD4(c) depends on the SDK's message text** (`str(exc).startswith("Registration failed:")`, `api.py:3946`, matching `mcp/client/auth/utils.py:302` in mcp 2.3.0). It is covered indirectly: path (c)'s tests run the real SDK registration code against a `MockTransport`, so a wording change in a future SDK fails them.
  - **`chat.js` grew by ~188 lines** in an already large file.
- **Test seams hid two defects.** `tests/test_app_websocket_pause_resume.py` used a `StubAgent` with `_deferred_tool_calls` preset, which encoded exactly the wrong assumption. `FakeLLM` (`tests/conftest.py`) accepts any history, so two tool results for one `tool_use` id passed every unit test. New tests now drive a real `Agent` through `_process_and_broadcast` and `_resume_paused_session` and assert one result per id. The test double itself still does not check.
- **The `expect_request` vs route-handler race** in `test_oauth_modal_flow.py` was fixed with `_wait_for_posts`. A deliberate delay did not reproduce it, so the mechanism is plausible but unproven; green gates since support the fix. `test_desktop_webview_skips_the_about_blank_pre_open` failed once early on, and is consistent with the same race.

### Documentation
- `the_one/agents.md` now records the "set state before the `yield`" rule (end of "MCP error translation"), the placeholder removal and the `ownFlow` chat rule. The generator rule is general, not MCP-specific, so it belongs in "Project Conventions" as a named pattern.
- The HAT apparatus pattern used here (an OAuth stub runner with a control endpoint, a stub that rejects until sign-in, and `bare_401` mode) is not documented; it lived in a scratchpad script.

## Test Metrics
Measured at the debrief on `main` `c3f0785`:
- **Unit:** `make test-unit` gives 6653 passed, 12 skipped (the documented count), 0 failed, in 288.6 s (wall 5m09s). Sortie 03 recorded 6019 passed in 194.8 s. That is +634 tests (+10%), mostly Mission 30 and work between the debriefs (this sortie added about 25 unit tests), against +48% time. The time growth is out of proportion and is not split by flight. Profile with `--durations` before treating it as real.
- **Browser gate** (`THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 --parallel 3`): `PARALLEL_RESULT rc=0 total=1052s lanes=9 failed=-`, with no flakes. Sortie 03: 1023 s; sortie 02: 939 s.

| lane | wall / budget (s) | passed | trend |
|---|---|---|---|
| routing | 508 / 600 | 186 | |
| agents | 500 / 510 | 190 | 506 at sortie 03; this sortie's gates 504, 501, **523**, 503, 500 |
| chats | 343 / 360 | 181 | |
| mcp | 334 / 360 | 110 | |
| library | 251 / 300 | 50 | |
| settings | 253 / 300 | 115 | 260 at sortie 03 |
| providers | 281 / 300 | 111 | 260 at sortie 03; flat this sortie |
| shared | **301 / 300** | 263 | ~235 at the M26 re-budget, 283 at sortie 03; 283-302 this sortie (+18 tests in `test_oauth_modal_flow.py`) |
| contracts | 243 / 270 | 723 (+4 skipped) | |

- **`agents` re-budget slipped again.** Sortie 03 flagged it at 506/510 and asked for a re-budget, which did not happen. This sortie's gates crossed it once (523). `shared` is now at its budget. The next sortie that adds browser tests will cross both.
- **Flakes this sortie:** the `test_oauth_modal_flow.py` race (fixed); `test_mcp_test_connection_button.py::test_test_connection_button_click_shows_result` (squawk 0216, pre-existing strict assert on transient text, failed once under load, 7/7 isolated, lane 50/50 on re-run).

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| DD4(c) narrowed in the leg design review (rejection evidence must come from this request's probe or fall-through) | Phase B's requests carry no operator headers, so its 401 is not evidence | yes: when a rule rests on "evidence", check the request that produced it actually carried what is being judged |
| DD2 chat half amended in the HAT: render only flows this client started (`ownFlow`); "Log in" always starts a fresh flow | The SDK's in-band consent URL dies at the 30 s connect timeout; the replay map preserved it and regressed `main`'s working path | yes: the lifetime-and-producer check at planning |
| Sign-in group moved out of the collapsible "Tool activity" trace | Operator: the control the user must act on must not hide in a collapsed panel (reverses an earlier mission's placement) | yes: action-required UI never inside a collapsible disclosure |
| `core.py`: pause state set before the `yield`; placeholder dropped before re-dispatch (pre-existing, fixed in sortie by operator decision) | Charter criterion 1 could not pass without them | yes: state that consumers read after a `yield` must be set before it |
| MCP editor connection row de-guttered | Operator-noticed misalignment (legacy `.field-row` label gutter) | no (one-off) |
| Three accessibility nits fixed in the HAT | Operator chose to fix all three | no |
| HAT fixture runner replaced mid-HAT (v2: reject until sign-in) | v1 re-accepted the old token, producing a false H2 failure | yes: HAT fixtures are designed and reviewed up front |
| Final gate accepted with one untouched-test flake after a full-lane re-run | Pre-existing transient-text race (squawk 0216) | already the project's triage rule |

## Key Learnings
- **A consent URL, or any server-issued handle the UI keeps, has a lifetime set by whatever holds the server-side state,** here a cancel scope 30 s long. UI replay or caching must be designed against that lifetime, not just against the frame order.
- **When a stub presets a state, it can hide the bug in how the real component reaches that state.** A stub may supply a state only if a real-component test shows the real collaborator reaches it through the same consumer.
- **Test doubles for providers should enforce provider invariants** (one result per `tool_use`, results after their call). A permissive fake is how a resume bug ships for months.
- **A sortie whose criterion leans on an existing path should cite a test that runs that path with real components,** or mark it "unverified in the real app" and expect the scope to grow.
- **The in-band vs out-of-band sign-in split was the hidden structure of this whole area.** The follow-up cluster (#289-#293) is the second decision cluster this sortie surfaced and correctly deferred. The recommended direction is on #290/#291: refresh in-band, interactive consent only through "Log in".

## Methodology Observations
- **Sortie skill, Plan (qualification), mission-control 1.2.0.** The qualification gate checks decision clusters, leg count and subsystems. It does not ask whether a criterion depends on an existing path that has never been exercised end to end. Expected: a prompt such as "for each criterion that relies on existing behaviour, cite the test or observation that shows it works today". Cost: two pre-existing defects in the agent loop (outside the planned files) were found only in the HAT, adding two fix rounds and three HAT re-runs. The sortie was still the right vehicle, because the fixes were exactly specified.
- **Flight skill, Phase 4 (crew interview / design decisions), mission-control 1.2.0.** The flight design's premise audit covers "can the apparatus act / observe". It has no equivalent for the *lifetime* of state the design stores or replays. Expected: alongside the citation audit, a check that for every server-issued URL, token or handle the design keeps, the spec names its producers and what ends it. Cost: DD2's chat half regressed `main`'s working recovery path, and the HAT had to diagnose it, amend DD2 and re-test. Both Architect cycles reviewed the chat design and did not raise it; the reviewers' prompts ask about soundness and citations, not lifetimes.
- **Flight skill, Phase 5 (spec / HAT leg) and agentic-workflow Phase 2b (HAT legs), mission-control 1.2.0.** The HAT leg is offered as "optional" and its apparatus is improvised during the HAT. Here the HAT was the only place charter criterion 1 could be proven end to end, and the improvised fixture runner produced one false failure (it accepted the old token before the click). Expected: when a criterion can only be verified in the real environment, the HAT is mandatory and its fixtures are specified (and ideally committed) at flight design. Cost: one wasted H2 run and a runner rewrite mid-HAT.
- **agentic-workflow Phase 2b (HAT inline fixes), mission-control 1.2.0.** The fix-vs-feature gate and the multi-surface trigger handled five inline fixes well. One fix (the `core.py` resume change) touched the agent loop's lifecycle, a high-risk surface by the workflow's own Phase 2a tiers, but the HAT path only defines a design review for features and multi-surface cosmetic fixes. The Flight Director relied on the investigator's exact spec plus the flight review. That worked here, but the skill gives no rule for a high-risk defect fix that turns up mid-HAT. Cost: none observed; recorded as a gap.
- **agentic-workflow Phase 2d (flight review), mission-control 1.2.0.** Reviewers flagged lane-budget overruns as warnings, and the workflow has no step that turns a repeated budget warning into an action. The `agents` re-budget was recommended at sortie 03 and slipped again. Expected: a debrief-to-squawk conversion that catches it, which Phase 6 of this skill now offers.

## Recommendations
1. **Plan the "chat sign-in lifecycle" sortie** (#289-#293) on the recommended direction: refresh in-band; interactive consent only through "Log in" (the chat/pool `redirect_handler` raises instead of waiting); Stop clears a paused turn; a fresh flow that needs no consent counts as resolved. Write #293's repro test first. Include a live desktop check of the reconnect case.
2. **Make `FakeLLM` enforce provider invariants by default** (squawk 0218) (one `tool_result` per `tool_use` id, results after their call), with an explicit opt-out for tests that build malformed histories deliberately.
3. **Re-budget the browser lanes now** (squawk 0217) (`agents` about 560 s, `shared` about 330 s), and consider splitting `agents` the way `mcp` was split from `library`. This is the second debrief in a row to ask.
4. **Add two planning checks to this project's flight design** (the crew prompts in `.flightops/agent-crews/flight-design.md`, or a CLAUDE.md flight-design note): a lifetime-and-producer check for any server-issued URL or token the UI keeps; and "does this path run in the real app?" for criteria that rely on existing behaviour, answered with a real-component test.
5. **Move the "set state before the `yield`" rule into `agents.md`'s Project Conventions** (squawk 0219) as a named pattern, next to the stub rule ("a stub may preset only a state a real-component test shows is reachable").

## Action Items
- [ ] Plan the chat sign-in lifecycle sortie (#289-#293) — `/mission-control:sortie`
- [ ] Squawk 0217: re-budget the `agents` and `shared` lanes
- [ ] Squawk 0218: `FakeLLM` enforces tool_use/tool_result pairing
- [ ] Squawk 0219: agents.md Project Conventions: set-state-before-yield, stub rule
- [ ] Squawks 0214, 0215, 0216 (deferred) at the next turnaround
- [ ] Profile the unit tier (`--durations`): 195 s to 289 s between sortie 03 and now
- [ ] Watch `test_desktop_webview_skips_the_about_blank_pre_open` (one early failure, consistent with the fixed race)
- [ ] Mission 31: fold `consent-link.js` into the consent-block consolidation
- [ ] Consider extracting `api.py::test_mcp_connection` into phases when it is next touched
- [ ] Commit (or specify) the HAT OAuth fixture runner pattern for future MCP sign-in HATs
