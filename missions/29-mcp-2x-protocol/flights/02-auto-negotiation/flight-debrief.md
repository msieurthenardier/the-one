# Flight Debrief: Automatic negotiation of protocol 2026-07-28

**Date**: 2026-10-13
**Flight**: [Automatic negotiation of protocol 2026-07-28](flight.md)
**Status**: completed (landed 2026-10-13; PR #277 ready for review, not yet merged)
**Duration**: 2026-10-12 (planning, flight start) - 2026-10-13 (HAT, landed). A WSL crash between H5 and H1 cost the HAT apparatus.
**Legs Completed**: 5 of 5 (`client-hardening`, `auto-negotiation-core`, `auto-negotiation-api`, `discover-401-signin` (added in flight), `hat`)
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved
The-one's MCP client now negotiates the protocol automatically. It tries `server/discover` at 2026-07-28 and falls back to the initialize handshake. A server that speaks 2026-07-28 connects on it, and the MCP editor says so.

Proven live in the HAT:
- **New-protocol servers.** The operator's Sonos server and two Cloudflare servers (Docs, and the OAuth-gated read-only API) all negotiated **2026-07-28**. Each one's tools ran from an agent's chat through the connection pool.
- **An older server.** A real `mcp==1.28.1` stdio server negotiated **2025-11-25** and its tool ran from chat. Repeat Tests took 0.4-0.6 s.
- **Windows.** The frozen Windows build's doctor now proves the full HTTP closure: `mcp sdk: OK — mcp 2.3.0, handshake 2025-11-25, modern 2026-07-28, httpcore2 2.13.1`.

Every Flight 1 carry-forward item touching this code landed:
- era-agnostic `_meta` (DD3);
- the doctor proving `httpcore2` (DD11);
- one shared failure classifier with a written matrix, replacing three near-copies (DD5);
- cancellation translated only on the transport's owner task (DD6);
- Test connection clearing stale OAuth secrets again, now without writing the operator's unsaved form values (DD7);
- squawk 0199's stale docs (DD12).

Two operator-visible gaps were also closed:
- a tool asking for input now gives a plain one-line error (DD8);
- a server that speaks only 2026-07-28 and rejects `initialize` can be tested and signed in to (DD9, plus leg 4).

### Mission Criteria Advanced
| Mission criterion | This flight |
|---|---|
| 2026-07-28 server connects on it, editor shows it, tools run from chat | **Met** (HAT H1: Sonos; also both Cloudflare servers). |
| Older-revision servers connect over stdio and HTTP, every older revision proven, no noticeable delay after first connect | **Met.** Every older revision was proven on a real 2.3.0 fixture labelled with it (DD13). 2025-11-25 was proven on both transports, with every fallback mode (fast error, bare 404, silent drop). The second connect sends no discover (structural check). A real 1.x server ran live (H4). The fixture's limit is stated: it proves the client accepts each revision, not 1.x wire behaviour; H4 covers that for one revision. |
| OAuth sign-in works end to end, tools run afterwards, RFC 9207 | **Met** (H2: the Cloudflare API sign-in went through discover 401, then initialize 401, then OAuth; then a live tool run). This closes Flight 1's gap of no live tool run. RFC 9207 was proven in Flight 1. |
| Self-configuration tools work, refusals one line | **Met.** The loopback negotiates 2026-07-28, and the existing real-client tests pass in that era. |
| Plain errors for no shared revision, input-required, oversized event | **Met.** No shared revision (DD5) and input-required (DD8) are new. The oversized event was done in Flight 1. Since checkpoint 2a, the SSE cap only applies on the handshake era (see Technical). |
| Windows build builds, doctor passes | **Met** (H5), now including `httpcore2`. |
| Unit and browser suites pass; changed expectations listed | **Met.** Unit 6228/12/0. Browser: one flake per full run, each passing in isolation (see Key Learnings). Every changed expectation is in the flight log. |

## What Went Well
- **The design reviews again caught defects before any code existed.**
  - The cycle-1 probe disproved DD6's `cancelling() == 0` premise: anyio delivers its own cancel-scope cancellation through `task.cancel()`. That led to the owner-task rule.
  - The same cycle found that DD2's planned `_cache.protocol_version` hint would have pinned every existing source, Sonos included, to the handshake era. Every saved value had been written by a handshake-only client. This led to in-memory era memory.
  - Leg 3's review caught that Phase B's `initialize`-driven sign-in could never see a 401 from a server that 400s `initialize`. That became the narrow DD10 amendment.
- **Re-implementing on the public API with a parity-drift test worked.** `_negotiate.py` maps each of its branches to the SDK's `negotiate_auto`. The private SDK function is imported only in one test, which checks the two still agree. The Architect proposes this as the model for any port of third-party logic: a branch table, a drift test, and an explicit "departures" section.
- **Real-server fixtures over injected exceptions,** carried from Flight 1.
  - Every older revision, every fallback mode and the structural latency check run against real subprocess servers.
  - The stdio silent-drop fixture shape (`--legacy-only --drop-discover`) was found by experiment: a dual-era server commits to the modern era on any discover.
- **Two passes with a hard checkpoint (leg 2) paid off.** Checkpoint 2a caught a stale `agents.md` reference and produced the finding that the SSE cap only applies on the handshake era.
- **The in-flight leg was the right call** (operator, 2026-10-13). Leg 3 surfaced that a modern-only, sign-in-requiring server would get no sign-in prompt. The FD promoted it to leg 4 rather than deferring it, and Cloudflare's real sign-in then took exactly that path in H2.
- **The HAT found nothing to fix.** That is a first for this project's recent HATs: Flight 1, sortie 02 and sortie 03 each found something. The operator reports no notable friction apart from the HAT instructions and the crash.

## What Could Be Improved

### Process
- **A leg finding was nearly deferred to the debrief.** Leg 3's report filed "discover 401, then initialize 400 loses the sign-in" as "out of scope; noted for the debrief". Leg 3's own test (b) had already been bent around the gap: it switched to a wrapper that 401s both methods. Only the FD's triage at landing turned it into leg 4. Any "noted for the debrief" item in a leg report should get an explicit FD fix-now-or-defer decision at landing.
- **The failure matrix didn't cross the two phases.** DD5 listed failures per operation, but not discover status × initialize status. The 401-loss bug lives in exactly that product. The Architect's root cause: DD1 treated SDK parity as a virtue, but the-one's last-status 401 detection is a stateful side channel the SDK lacks, so the parity port needed auditing against it. Future negotiation or fallback designs should list the per-phase status product up front.
- **A leg spec was lost and rebuilt.** The leg 3 Developer accidentally truncated its untracked leg file and rebuilt it from what it had read. The FD checked the structure and accepted it. Committing leg specs before handing them to a Developer would make such a loss recoverable from git.
- **The HAT apparatus lived in `/tmp`.** The scratch data dir sat in the session scratchpad under `/tmp`. The WSL crash wiped it, along with the operator's provider, three sources and the agent, so they had to be set up again. The new session also has a different scratchpad path. A HAT that spans a session or a day should keep its data dir under `$HOME`, as H4's server already did.
- **HAT instructions were hard to follow one step at a time** (operator feedback; see Methodology Observations). In H4 the setup step didn't say Command needs `Custom…`, and the "tell me after the second Test" request came at the end of the list. The operator had already finished by the time they read it.
- **H3 (live stale-token clear) was skipped again**, by operator decision. It was skipped in Flight 1 as V3 too. DD7 is proven by unit tests only, so it is recorded as not verified live rather than as a pass.

### Technical
- **The auth-record side channel keeps growing.**
  - What threads through `_full_policy`, the remembered shortcut and the classifier: `baseline`, `seq`, `saw_401_since` and `last_resource_metadata`.
  - Correctness depends on call order ("the caller must have read `record` before it", `client.py` ~414).
  - Flight 1's `_signin_record.py` smells are unchanged: the transport imports the private `_AUTH_RECORDS` (`transports/streamable_http.py:33`), and `MAX_SSE_EVENT_BYTES` lives there (`_signin_record.py:15`).
- **The hand-built OAuth flow drivers are a second MCP client that drifts.** DD10 aligned their version header but not their request shape. They send no `Accept: application/json, text/event-stream`, so Cloudflare answered the post-token retry with **406** (`api.py` ~3916, ~4788). The response is thrown away and sign-in still completes, so it is only noise. With the probe, there are now three places that build raw MCP HTTP requests.
- **`_full_policy` is the hardest function in the flight to maintain.** It has a two-attempt loop, the deferred-exception pattern (`deferred`, `handshake_exc`) and three nested `try` levels. Splitting out a `_handle_discover_error` step is worth doing next time the policy is touched.
- **`DiscoverSignInRequired` is the one deliberate departure from SDK parity.** The parity-drift test can't flag it on an SDK bump, so it needs its own named test in that suite.
- **Accepted gaps, each pinned or logged:**
  - A -32022 on the re-probe that lists a mutual modern version gives the generic "MCP connect failed" (leg 2, resolution 1).
  - Whether a modern server can stream SSE over the 1 MiB cap (progress notifications) is untested. The cap tests now seed the handshake era.
  - The modern-era input-required case is tested only through a mock session.
  - A server that gains 2026-07-28 mid-run stays on the handshake until a restart, Reset, an edit or a Test (DD2 trade-off, accepted).
  - The era map is process-global and unlocked. That is safe on a single asyncio loop, but nothing says so.
- **A remembered modern era still runs the full policy,** costing one discover round trip per connect. Only a remembered handshake era takes the shortcut. That's cheap and safe, but the choice isn't documented.
- **The `api.httpx2` proxy in tests is a dual-HTTP-stack symptom.** Patching `api.httpx2.AsyncClient` breaks the transport's `isinstance` check, so leg 3's test replaces the whole module with a proxy. It is documented in `agents.md`.
- **Debt carried, not introduced:** the anyio shutdown noise from Mission 07, the `AsyncMockMixin` "never awaited" warnings (squawk 0027's family), and squawk 0198 (`verify-serving`).

### Documentation
- **`the_one/mcp/_era.py:7-8`** still says "nothing reads or writes the map yet beyond that". That has been false since leg 2.
- **`the_one/agents.md`** should say:
  - why a remembered modern era doesn't skip discover;
  - that the era map assumes a single event loop.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| DD2: the persisted `_cache` hint replaced by in-memory era memory | Design review: every saved `protocol_version` came from a handshake-only client, so it was a false signal | Yes: prefer an in-memory hint with a "fresh" bypass over persisted state of unknown origin |
| DD6: `cancelling()` gate replaced by owner-task identity | The design-review probe disproved the premise | Yes: decide cancellation by task identity |
| DD5 row 1 amended: `connect` keeps wrapping `UrlElicitationRequiredError` | A pass-through would crash `MCPToolProvider`'s agent build | No |
| Leg 2 run as two passes with a hard checkpoint | Developer design review: too large for a single pass | Yes: for HIGH-risk legs that change lifecycle |
| DD10 amended: on DD9's fall-through, the driver posts `server/discover` | Leg 3 review: an `initialize`-driven sign-in can't see a 401 from a server that 400s `initialize` | No (narrow) |
| Leg 4 `discover-401-signin` added in flight | Leg 3 finding in the mission's target class; operator: right call | Yes: an FD fix-now-or-defer triage of every "noted for the debrief" item at leg landing |
| Leg 3's leg file truncated and rebuilt | Developer accident on an untracked file | Commit leg specs before implementation |
| HAT data dir set up again after a WSL crash | `/tmp` scratchpad wiped | Keep a multi-session HAT data dir under `$HOME` |
| HAT H3 skipped | Operator's call ("confident it works") | No: record it as not verified live |

## Key Learnings
- **Porting a third party's fallback policy means auditing it against your own side channels.** The SDK's "any error from discover → try initialize" is safe for the SDK. The-one's "last MCP POST status wins" 401 rule turned the same fallback into lost sign-ins. Parity is a starting point, not a proof.
- **Last-status side channels are fragile across multi-request phases.** Capture what you need from the earlier phase (here, `resource_metadata` on the discover 401) before the later phase overwrites it.
- **A modern-era 2.3.0 server answers a single-response POST as plain JSON, not SSE.** So protections tied to SSE, like the 1 MiB event cap, only apply on the handshake era. Recheck any SSE-specific limit when the era changes.
- **Real servers behaved better than feared.** Sonos, both Cloudflare servers and a 1.28.1 server all negotiated correctly at once. The serverInfo versions were not blank, and the 1.x server rejected discover quickly. The 10 s silent-drop worst case has not been seen in the wild.
- **Test metrics** (debrief run, `bf42907`, Developer):
  - **Unit: 6228 passed / 12 skipped / 0 failed, 226.4 s.** Against Flight 1 (6068/12, 194.7 s) that is +160 tests and +32 s (+16%). Nearly all the new tests are MCP:
    - `test_mcp_negotiate.py`: 46
    - `test_mcp_failure_matrix.py`: 24
    - `test_mcp_negotiation_fallback.py`: 12
    - `test_mcp_test_connection_negotiation.py`: 10
    - sign-in additions

    Many of them spawn real subprocess fixture servers, which accounts for the time. Skips are the normal 12.
  - **`requires_bwrap`: 41 passed / 3 skipped, 22.6 s.** Unchanged.
  - **Browser: `PARALLEL_RESULT rc=1 total=1034s lanes=9 failed=chats`** (Flight 1: 1055 s, -2%; the in-flight run was 1128 s under extra load). The flight added no browser tests. Per lane against budget, with Flight 1 in brackets:

    | Lane | Seconds / budget (Flight 1) |
    |---|---|
    | routing | 511/600 (521) |
    | **agents** | **507/510** (508) |
    | chats | 348/360 (351), rc=1 |
    | mcp | 313/360 (315) |
    | providers | 288/300 (293) |
    | shared | 277/300 (291) |
    | settings | 253/300 (263) |
    | library | 250/300 (256) |
    | contracts | 240/270 (261) |

  - **Flakes: two different load-timing flakes in two consecutive full runs, none MCP-related.**
    - The in-flight run: `test_oauth_modal_flow.py::test_second_auth_required_event_navigates_popup_to_consent_url` (squawk 0201).
    - The debrief run: `test_flow_chat_list.py::test_row_delete_arms_confirms_and_focuses_the_neighbour`, where focus was "inactive". Its lane passed alone, 181/181.

    Five lanes are within 10% of budget, and `agents` has 3 s of headroom. The re-budget recommendation is now open across three debriefs (sortie 03, Flight 1, this one). Focus-under-load flakes also appeared earlier (squawks 0168, 0187). The pattern is near-budget lanes plus focus assertions failing under host load.

## Methodology Observations
- **HAT step instructions (agentic-workflow HAT leg / leg skill HAT template, 1.2.0). Operator feedback, verbatim intent.**
  - **What the methodology did.** The FD wrote H4 as a four-step numbered list with a closing "tell me when you've pressed Test the second time". Its setup step said "Command: …" without naming the `Custom…` dropdown entry.
  - **What the operator does instead.** They follow HAT steps one at a time, switching to the app for each one, and never hold the whole list in their head. So they finished every step before reading the report-back request, and needed several tries to configure the source.
  - **What was expected.** Each step names the exact screen, control and value. Every check, and every "tell me now", is its own numbered step at the point where it happens, never in a closing paragraph. Wording is plain, with any reason given in one line after the step.
  - **Cost.** Several setup retries, and a lost mid-step check: the FD couldn't observe the second-Test timing live and re-ran it through the API afterwards.
  - The operator intends to embed this into the methodology themselves. It was **not** applied to the project's `CLAUDE.md`.
- **Leg-landing triage of deferred findings (agentic-workflow, leg landing / `[LAND:leg]` handling, 1.2.0).**
  - **What happened.** A leg report can file a real defect as "noted for the debrief", and nothing in the landing checklist requires the FD to decide on it. Here the FD did triage it, which produced leg 4, the fix H2 then exercised.
  - **What was expected.** The checklist asks for an explicit fix-now / squawk / defer decision on every such item.
  - **Cost if missed.** The mission's target class (modern-only, sign-in-requiring servers) would have shipped broken.
- **Leg specs left untracked during implementation (agentic-workflow, Phase 2 leg design → implementation, 1.2.0).**
  - **What happened.** Leg files are created untracked and are only committed with the flight. A Developer truncated one and rebuilt it from memory.
  - **Cost.** An FD structure check. The risk was a silently changed spec.
  - **What was expected.** Commit, or at least `git add`, each leg spec before the implementation hand-off.
- **Flight design review didn't cross phases (flight skill, Phase 5 Architect review, 1.2.0).**
  - **What happened.** Neither review cycle asked for a cross-product of statuses across discover and initialize, so the 401-loss bug passed both cycles and two leg reviews.
  - **Cost.** One added leg; no rework.
  - **What was expected.** A suggested prompt line for multi-phase protocols: "enumerate each status combination across phases".
  - **Data point on Flight 1's question.** Two Architect cycles were enough for this flight's design. The defect that slipped through came from the missing cross-product, not from too few review cycles.
- **HAT apparatus location (flight skill, HAT/apparatus design, and the FD's choice, 1.2.0).**
  - **What happened.** DD14 put the HAT data dir in the session scratchpad under `/tmp`. That path is session-scoped and was wiped by a host crash.
  - **Cost.** All the HAT configuration had to be set up again.
  - **What was expected.** Apparatus that must outlive a session lives under a durable path. That covers a HAT spanning days, or one with operator-entered setup like providers and OAuth sign-ins.

## Recommendations
1. **Fold the HAT-instruction feedback into the methodology** (operator-owned), then send it upstream with `/mission-control:service-report`. Of everything here, it has the most direct effect on the operator's experience.
2. **Re-budget the browser lanes from a fresh measurement,** at least `agents` (507/510) and `chats` (348/360), and look at focus assertions under load (squawks 0168, 0187, 0201 and the new chat-list flake). This is now the third debrief to carry it. Near-budget lanes plus load-sensitive focus checks make every full gate flaky.
3. **Give the raw MCP HTTP requests one shared request builder.** Three places build them: the two OAuth flow drivers and the auth-posture probe. A shared builder covering `Accept`, the version header and the body shape would end the 406 noise and the next header drift.
4. **For the future MCP-capabilities mission** (resources, prompts, subscriptions, input-required fulfilment):
   - Start with a real modern-era fixture that asks for input, and one that streams over the SSE cap. Both cases are mock-only or untested today.
   - Do Flight 1's `_signin_record.py` tidy-up before more state threads through it: a `register_auth_record()` function, and `MAX_SSE_EVENT_BYTES` moved out.
5. **Small doc fixes:** the `_era.py` docstring, plus `agents.md` notes on the modern-era no-shortcut choice and the single-loop assumption.

## Action Items
- [x] Squawk **0202** logged (open): the OAuth flow drivers' missing `Accept` header (406 after sign-in).
- [x] Squawk **0203** logged (open): the stale `_era.py` docstring, plus `agents.md` notes on the modern-era no-shortcut choice and the single-loop assumption, and a correction of the overgeneralised serverInfo `version: ''` claim (the HAT showed real versions).
- [x] Squawk **0204** logged (deferred with 0201): the `test_row_delete_arms_confirms_and_focuses_the_neighbour` load flake.
- [ ] Re-budget the browser lanes (Recommendation 2). The operator declined a squawk for this after Flight 1, so it stays a recommendation unless re-decided.
- [ ] Stdio source editor: make an absolute interpreter path discoverable. The `Custom…` command entry wasn't obvious to the operator in H4. This is a UX change, so it goes to the next UI flight or a sortie, not a squawk.
- [ ] Methodology: the operator embeds the HAT-instruction rule; later `/mission-control:service-report`.
- [ ] Mission 29 debrief (`/mission-control:mission-debrief`): both flights have landed.
