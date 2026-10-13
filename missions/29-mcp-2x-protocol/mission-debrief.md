# Mission Debrief: MCP servers connect on the newest protocol

**Date**: 2026-10-13
**Mission**: [MCP servers connect on the newest protocol](mission.md)
**Status**: completed
**Duration**: 2026-10-11 (squawk attempt, escalated to a sortie and then to a mission) - 2026-10-13 (Flight 2 debriefed; PR #277 not yet merged)
**Flights Completed**: 2 of 2
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Success Criteria Results
| Criterion | Status | Notes |
|-----------|--------|-------|
| A server that supports 2026-07-28 connects on it, the editor shows it, tools run from chat (Sonos, behavior-test-backed) | **met** | F2 HAT H1: Sonos negotiated 2026-07-28 and a tool ran from chat through the pool. Cloudflare Docs and Cloudflare API also negotiated 2026-07-28. |
| Older-revision servers (2024-11-05 to 2025-11-25) connect and run tools over stdio and HTTP; every older revision proven; no noticeable added delay after the first connect | **met** | F1 proved parity. F2 proved each older revision on a real 2.3.0 fixture labelled with it, and 2025-11-25 on both transports with every fallback mode. The second connect sends no discover, checked structurally. A real `mcp==1.28.1` server ran live on 2025-11-25 (H4), with repeat Tests at 0.4-0.6 s. Stated limit: the fixtures prove the client accepts each revision; real 1.x wire behaviour is proven live only for 2025-11-25. |
| OAuth sign-in works end to end, tools run afterwards, including RFC 9207 (Cloudflare, behavior-test-backed) | **met** | F1: a live Cloudflare sign-in carrying `iss`, plus real-fixture issuer tests. F2 H2: the Cloudflare API sign-in under negotiation (discover 401, then initialize 401, then OAuth), with a live tool run. That closes F1's gap of no live tool run. |
| Self-configuration tools work; refusals read as one line | **met** | F1: `ToolError`-typed refusals under `MCPServer`. F2: the loopback negotiates 2026-07-28, and the existing real-client tests pass in that era. |
| Plain one-line errors for no shared revision, input-required and an oversized event | **met** | F1: oversized event. F2: no shared revision (`MCPVersionMismatch`) and input-required (`MCPCallError`). Caveats: the modern-era input-required case is tested only through a mock session, and since F2 the SSE cap only applies on the handshake era (a modern single-response POST is plain JSON). |
| The Windows packaged build builds and `the-one doctor` passes | **met** | The F1 Windows lane run passed. In F2 H5 the frozen doctor prints `mcp sdk: OK — mcp 2.3.0, handshake 2025-11-25, modern 2026-07-28, httpcore2 2.13.1`, which closes F1's `httpcore2` gap. |
| Unit and full browser suites pass; changed expectations listed | **met** | Unit 6228/12/0, `requires_bwrap` 41/3. Every changed expectation is listed in both flight logs. The browser suite: F1 `rc=0`. Each F2 full run had one load-timing flake outside MCP (squawks 0201, 0204), each passing in isolation. |

### Overall Outcome
**Achieved.** The Sonos server (the trigger for the mission) connects on 2026-07-28, and the MCP editor says so. Every older server keeps working, OAuth sign-in included, with no setting for the operator to change. The four behaviour changes the SDK forces each fail with a plain error.

The outcome was still the right goal at the end. Two of the three real remote servers the operator uses already speak 2026-07-28, so negotiation matters now, not just later.

The operator judged the mission's shape correct: a squawk that escalated to a sortie, then to a two-flight mission (port at parity, then negotiation), before any code existed.

## Flight Summary
| Flight | Status | Key Outcome |
|--------|--------|-------------|
| 1. Port to the `mcp` 2.x SDK at parity | completed (merged `06e1e39`) | `mcp` 1.28.1 → 2.3.0 with every server still on the handshake. Sign-in detection was redesigned around a response hook and a per-session record, because 2.x swallows 401s. RFC 9207 `iss` flows through the callback. Self-configuration moved to `MCPServer` with its one-line refusals kept. Twelfth doctor gate. HAT fix: the OAuth consent wait went from 15 s to 2 min. |
| 2. Automatic negotiation of 2026-07-28 | completed (PR #277 ready, not merged) | Negotiation on the public SDK API behind one seam, with a parity-drift test. In-memory era memory. One shared failure classifier. Owner-task cancellation. Stale tokens cleared on Test without leaking the form's override. The probe's fourth verdict. The doctor proves `httpcore2`. A leg was added in flight, so a modern-only, sign-in-requiring server gets a sign-in prompt. The HAT needed no fixes. |

## What Went Well
- **The escalation gates found the right shape before any code existed.** The squawk gate turned down "bump the SDK" once 2.x proved breaking. The sortie re-check then found the second decision cluster: sign-in detection, RFC 9207 and the dual HTTP stack. Port first, then negotiate, gave each flight one coherent risk. The operator confirms the shape and found the gating useful rather than a burden.
- **The design reviews caught real defects in both flights before code.**
  - **F1:** the record's scope; the DD8 error surface; three unacknowledged forced behaviour changes; the last-status rule; and three `api.httpx.AsyncClient` patch sites that would have silently stopped intercepting.
  - **F2:** the disproved `cancelling()` premise; the `_cache` era hint that would have pinned Sonos to the handshake; and the Phase B sign-in that could never see a 401.

  Probes against the installed SDK, rather than reasoning about it, decided most of these.
- **Flight 1's debrief recommendations steered Flight 2.** Every one of its technical carry-forwards was confirmed live by reconnaissance and landed as a Flight 2 design decision: era-agnostic `_meta`, the `httpcore2` doctor proof, consolidating the translation ladder, stale-token behaviour, cancellation attribution and the probe for modern-only servers. Flight 2 also applied Flight 1's process lessons: a lock-synced venv, a live Cloudflare tool run, and running H3 as V3's replacement (later skipped, see below).
- **Architecture improved.** Era handling now has three small modules: the evidence (`_signin_record.py`), the decision (`_negotiate.py`) and the memory (`_era.py`). They are layering-pinned leaf modules. Three diverging per-operation failure ladders became one first-match classifier with a written matrix and a test twin (`_classify_failure`, `tests/test_mcp_failure_matrix.py`). Neither flight added a dependency on a private SDK module.
- **Real fixtures over mocks and injected exceptions.** Real 401s, OAuth flows, redirects, older-revision servers and fallback modes exposed what mocks had hidden. Examples: wire-shape changes, and a dual-era server committing to the modern era on any discover.
- **HATs against real servers.** F1's found the 15 s consent ceiling. F2's confirmed negotiation against four real servers and needed no fixes.
- **Worktree isolation held across both flights.** Main's unrelated work was never touched.
- **Coordination was smooth** (operator). Status was clear, and the decisions routed to the operator were the right ones.

## What Could Be Improved
- **HAT instructions** were the operator's one coordination pain point. Steps were written as lists to read through, not as single actions to do. Checks and report-back requests sat at the end, and controls weren't named exactly (the stdio `Custom…` command). The operator works one step at a time, switching to the app for each. See Methodology Feedback.
- **The live stale-token check was skipped in both flights:** F1 V3, then F2 H3, both operator decisions. That behaviour changed in F1 and was deliberately reversed in F2 (DD7), yet it has only been proven by unit tests. It stays "not verified live".
- **Multi-phase protocol logic needs a status cross-product at design time.** The discover-401-lost-to-an-initialize-failure defect passed two Architect cycles and two leg reviews. It was caught only at leg landing. Porting the SDK's fallback was safe for the SDK, but not alongside the-one's own last-status side channel.
- **Browser-gate fragility is the mission's largest carried risk.**
  - Lane re-budgeting has now been recommended in three debriefs in a row (sortie 03, F1, F2), with `agents` at 507/510 s.
  - The two F2 full runs each failed on a different load-timing flake (0201, 0204), in the same family as 0168 and 0187.
  - A gate that flakes on every full run makes every later mission's verification more expensive and less trusted.
- **The HAT apparatus wasn't durable.** F2's HAT data dir was in the session scratchpad under `/tmp`, and a WSL crash wiped it. The provider, three sources and the agent all had to be set up again.

## Lessons Learned
- **Technical**
  - **When a dependency hides a transport signal, recover it on the client you own.** F1's 401 record shows how: a response hook, a weak-keyed per-session record and a "last status since baseline" rule. But every later multi-request phase has to be audited against that side channel, as F2's leg 4 showed. Capture what you need from an earlier phase before a later one overwrites it.
  - **Port third-party policy behind one seam, with a branch-parity table, a drift test against the original, and a named "departures" section.** `_negotiate.py` is the model.
  - **Prefer an in-memory hint with a fresh bypass to persisted state of unknown origin.** Every saved `protocol_version` predated negotiation.
  - **Decide cancellation by task identity, not `cancelling()`.** anyio delivers its own cancel-scope cancellation through `task.cancel()`.
  - **A frozen-build gate proves only what it constructs.** The `httpx2` → `httpcore2` import is lazy.
  - **SSE-specific limits depend on the era.** Modern single-response POSTs are plain JSON.
  - **A dual HTTP stack needs an AST guard and a patch-target rule.**
- **Process**
  - Apply a debrief's carry-forwards through reconnaissance (confirmed-live, or not) before design. This worked well from F1 to F2.
  - Every "noted for the debrief" item in a leg report needs an FD fix-now, squawk or defer decision at landing.
  - Commit leg specs before handing them to a Developer.
  - Put long-lived HAT apparatus under `$HOME`.
  - Write HAT steps as single actions, with checks inline.
- **Domain**
  - Real third-party MCP servers adopted 2026-07-28 quickly: two of three remote servers, by the time of this mission.
  - Real 1.x servers answer discover fast, and real modern servers report real `serverInfo` versions (only the SDK's own servers stamp `''`).
  - The 10 s silent-drop worst case hasn't been seen in the wild.

## Methodology Feedback
These restate observations already in the flight debriefs; a sweep should count each once. Plugin version: mission-control 1.2.0 throughout.

| # | Finding | Skill / phase | Flights | Cost | Destination |
|---|---|---|---|---|---|
| 1 | **HAT instructions written as a list to read, not single steps to do.** The FD put checks and the "tell me when" request at the end and named controls loosely (the stdio `Custom…` entry). The operator does one step at a time, switching apps, and never holds the list in their head. Expected: each step names the exact screen, control and value; every check and report-back is its own numbered step where it happens; plain wording, reasons after the step. | agentic-workflow HAT leg; leg skill HAT template | F2 (recorded); the operator names it the mission's one coordination pain point | Several setup retries; a lost mid-step check (the FD re-ran the timing through the API) | **Methodology observation.** The operator will embed it themselves; not applied locally. |
| 2 | **No required FD decision on "noted for the debrief" items at leg landing.** Leg 3 filed the discover-401 loss as out of scope, and its test was bent around the gap. The FD's discretionary triage turned it into leg 4. | agentic-workflow, leg landing / `[LAND:leg]` | F2 | An unplanned leg and design-review cycle. Without the FD's triage, the mission's target server class would have shipped without a sign-in prompt. | **Methodology observation** |
| 3 | **Design review does not prompt a cross-phase status product** for multi-phase protocols (discover × initialize). The defect passed two Architect cycles and two leg reviews. | flight skill, Phase 5 Architect review | F2 (F1's last-status rule came from the same review blind spot, caught in cycle 2) | One added leg (no rework) | **Methodology observation** |
| 4 | **Leg specs stay untracked through implementation.** A Developer truncated one and rebuilt it from memory. | agentic-workflow, leg design → implementation hand-off | F2 | An FD structure check, plus the risk of a silently changed spec | **Methodology observation** |
| 5 | **A fresh worktree's venv is not built from the lock.** It was a fresh resolve that drifted `openai`. | agentic-workflow, Phase 1/2a worktree strategy | F1 (F2 avoided it by applying F1's lesson by hand) | 5 spurious baseline failures, a rebuild and a re-run | **Methodology observation** |
| 6 | **Sequence numbers assigned against a stale default branch.** A concurrent sortie 03 merged first. | sortie skill, Plan step 3 | F1 planning | A rename, absorbed by the escalation | **Methodology observation** |
| 7 | HAT data dir placed in the session scratchpad (`/tmp`), lost on a host crash | FD choice in DD14 (the methodology doesn't specify a location) | F2 | All HAT setup redone | **Local lesson.** Doesn't reproduce from the methodology alone. |
| 8 | Agent commit hand-back flagged "Self-Modification" by auto mode for touching `CLAUDE.md` | agentic-workflow Phase 2d (harness interaction) | F1 | An FD diff check, no rework | **Local lesson.** Harness behaviour; recorded for a sweep. |
| 9 | Are two Architect cycles enough for security-sensitive flights? | flight skill, Phase 5b | F1 (question), F2 (answer: yes; the slip came from #3, not the cycle count) | None | **Local lesson** (data point) |
| 10 | Stale numbers from project docs copied into acceptance criteria | flight and leg skills | F1 (the `requires_bwrap` count; corrected in F2 leg 1) | The Developer reported it; low | **Local lesson** |
| 11 | The squawk → sortie → mission escalation gates fired correctly | squawk and sortie skills | F1 planning | Expected planning cost | **Working as designed** (positive record) |

No local fixes to this project's `ARTIFACTS.md` or crew files are taken now. The operator asked to embed #1 into the methodology themselves rather than patch the project.

## Action Items
- [ ] Merge PR #277 (Flight 2).
- [ ] **Re-budget the browser lanes and clear the focus/timing flake family** (squawks 0168, 0187, 0201, 0204). This is the top priority: it is carried across three debriefs, and a flaky gate taxes every future mission.
- [ ] Squawks from F2, at the next turnaround: 0202 (flow drivers' `Accept` header, 406) and 0203 (era docs). 0198 (`verify-serving`) is still deferred.
- [ ] **Small refactor before the next MCP work:** one builder for the hand-built MCP HTTP requests (both flow drivers plus the probe; three copies of the `initialize` body and clientInfo `"0.1"`; `api.py:3910`, `:4784`, `transports/streamable_http.py:269`). It would end the 406 and the next header drift. Routing all source mutations through one helper that calls `forget_era` is a related item. Today there are four separate call sites (`api.py:3110`, `:3189`, `:3220`, `:3290`), and a new mutation path that forgets one leaves a stale era.
- [ ] **For the future MCP-capabilities mission** (resources, prompts, subscriptions, input-required fulfilment), from the Architect:
  - Every new MCP operation goes through `_classify_failure` and the failure-matrix tests, with a new `op` value, before any feature code.
  - Sampling and elicitation are a trust-model design flight (`SECURITY-MODEL.md`), not a port.
  - Subscriptions need the pool's request/response assumptions and the owner-task rule re-examined.
  - Large resource reads need a size or pagination policy, because of the 1 MiB SSE cap.
  - Start with real modern-era fixtures for input-required and for oversized streams.
  - Do F1's `_signin_record.py` tidy-up first.
- [ ] Code debt, when next touched: split `_full_policy` into a `_handle_discover_error` step, and consider a context-manager wrapper for `client.py`'s three `except*` arms (about 150 lines; `client.py` is now 1091 lines).
- [ ] Stdio source editor: make the `Custom…` command entry discoverable (a UX item for a UI flight or a sortie).
- [ ] Methodology: the operator embeds the HAT-instruction rule, then `/mission-control:service-report` when they choose.
- [ ] `/mission-control:routine-maintenance`: the mission boundary is the natural point for it.
