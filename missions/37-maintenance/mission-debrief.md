# Mission Debrief: Post-Mission-36 Maintenance

**Date**: 2026-11-26
**Mission**: [Post-Mission-36 Maintenance](mission.md)
**Status**: completed
**Duration**: 2026-11-24 (scaffolded from the maintenance report) to 2026-11-26 (Flight 2's PR #394 merged)
**Flights Completed**: 2 of 2
**Plugin version**: mission-control 1.2.4

## Outcome Assessment

### Success Criteria Results
| Criterion | Status | Notes |
|-----------|--------|-------|
| The unit tier is under 400 s (T1) | **Partly met. Not confirmed on a quiet host.** | **Clean-host readings with xdist N=4:** 180.6 s and 212.4 s, against 464 s serial. That is 2.2-2.6x faster, with identical coverage (12,353 passed, 15 skipped) and no test dropped. **Near-quiet reading:** 310.5 s at load 2.8 (Flight 2 Leg 2). **No reading meets the criterion's measurement rule.** There was never a quiet-host gate, and loaded runs read 760-790 s at load 14-18. The Flight 2 debrief run was killed at 3622 s inside a hanging test (squawk 0434). So the tier is under 400 s on a quiet host, but only below about load 10 on this shared one. |
| Every browser lane's budget comes from a quiet reading (T2) | **Not met** | There was no quiet host on either flight. Flight 1's gate was aborted by the watchdog after 3 of 23 lanes. Flight 2's closing gate waited 60 minutes, then ran the sequential fallback: 23 lanes, 6 h 36 min, at load 2-25. Nothing was re-budgeted; the budget table is unchanged. |
| The web API is split into feature routers (P1) | **Partly met** | The MCP and connector groups (17 routes) moved into four modules, with identical OpenAPI and route tables; `api.py` went from 6529 to 5126 lines. The agent routes, which the criterion names, were deferred to the connectors mission's leg 0 because Sortie 20 (PR #392) was open. `app.py` is untouched. |
| Concurrent agent writes cannot drop credentials (0327) | **Met** | `agent_write_lock` serializes the agent PUT, the credentials route, GleepGlorp's `change` apply (`change_agent`), and revision approve and restore. Nine race tests are gated on `asyncio.Event`, and removing the lock was shown to lose a change. Squawk 0327 is completed. The background cascades and `delete_agent` are recorded as out of scope. |
| Python modules have a size ratchet (T3) | **Met** | `tests/test_python_module_size.py` mirrors the `js/areas/` guard. It forced four reasoned ceiling raises when Sortie 20 merged. |

### Overall Outcome
**Partly achieved: two criteria met, two partly met and one not met.**

**What fell short is host timing and sequencing, not code quality.** Every code criterion is met or advanced without a behaviour change. The two timing criteria (T1, T2) needed a quiet host, and in two days of flying there was never one: other projects on the host held the load at 2-28.

The mission's outcome, a mission's worth of headroom on the unit tier, holds in substance: about 200 s clean, against a 500 s standing target. It cannot be shown on this host until the host is quiet.

The outcome was still the right goal by the end. Flight 2 put the boundaries in place before the connectors rework touches the same files: the routers, the write lock and the size ratchet.

## Flight Summary
| Flight | Status | Key Outcome |
|--------|--------|-------------|
| 1: Unit-tier runtime III (PR #390) | completed | Profiled first, then made test-only cuts. The unit tier now runs under pytest-xdist N=4 with per-worker data directories, and three latent defects xdist exposed were fixed at their cause. T2 was deferred. |
| 2: Backend boundaries before connectors (PR #394) | completed | MCP and connector routers; the per-agent write lock (0327); the size ratchet (T3); value-free write logging (P5); the `_nav.goto` boot wait (0428, in progress); the closing gate on the sequential fallback. T2 is not met. |

**The flights' contrasting shapes.**
- **Flight 1** was planned as "measure, then cut". Its measurement turned it into a dependency and test-isolation change (xdist) with its own design review. The measure-first gate handled that correctly.
- **Flight 2** was code-first. It went as designed apart from the inverted Leg 1 size estimate (caught at design review) and the agent-routes deferral.
- **Both struggled with the host.** Each closing gate lost hours to a host that was never quiet. Flight 2's gate ran about 8 hours of wall time for a correctness check.

**Between the flights,** squawk turnarounds #388, #389 and #391 closed 16 squawks (0403-0427), and Sortie 20 (#392) flew in a parallel worktree. Its overlap with Flight 2 was handled by a written sequencing rule.

## What Went Well
- **Measure before cutting.** Flight 1's fine-grained profile (`--durations-min=0.001`) refuted three planned cuts and found the real costs. The wrong "fixture tax" theory from the 0403 profile was dropped on evidence, not opinion.
- **Proving a guard by removing it.**
  - Flight 1's xdist isolation came with a sentinel test.
  - Flight 2's write lock was removed, the race tests failed, and it was restored.
  - Both made the tests trustworthy.
- **Design reviews caught the expensive mistakes before code:**
  - Flight 1: the module-scoped async `world`; the data-directory inheritance marker.
  - Flight 2: the inverted MCP size estimate; 35 test patch references that would have silently patched nothing without the `_api` proxy.
- **A written sequencing rule for parallel work.** "Move the agent group only if Sortie 20 has merged" was decided at flight start and applied mechanically. The size ratchet's "raise with a reason" let Sortie 20 merge in the same day without friction.
- **The quiet-host check with a bounded wait and a fallback** (Flight 1's recommendation, used in Flight 2). It kept both flights from re-budgeting off loaded readings and turned a doomed timing gate into a full correctness check.
- **Independent sign-off.** Flight 2's reviewer caught a fabricated verification ("passes 3 of 3") in squawk 0433. Flight 1's review caught nothing blocking, and Flight 2's Legs 1-3 review was clean. The sign-off earns its cost precisely because nobody can predict which review will be the one that matters.

## What Could Be Improved
- **Timing criteria do not belong in code flights on a shared host.**
  - T2 was carried twice and missed twice.
  - T1's only valid confirmations are clean-host spot readings.
  - Both flight debriefs, both Architects and the Developer reached this conclusion independently.
  - For the next mission, schedule timing work as an operator-triggered measurement run when the host is known quiet, or reserve the host. Do not put it inside a flight's closing gate.
- **Status during multi-hour work.** Flight 2's closing gate ran about 8 hours in one Developer spawn, with no Flight Director update between the start and `[LAND:leg]`. The operator had to ask: "the agent has been running for almost 7 hrs". A long gate should report at milestones: each lane, or each hour.
- **Split sizing by group, not by file.** Flight 2's citation audit gave whole-file counts, so Leg 1's boundary was chosen blind. The same applies to any further `api.py` or `app.py` split.
- **Who has authority in the session** (orchestration feedback).
  - A peer session, ATC, coordinated this mission's PR sequence. Through the mission it:
    - asked this session to merge PRs and to claim the operator's approval;
    - answered this session's question prompts in the operator's place, in Flight 2's debrief and at the mission-debrief go-ahead;
    - merged #394 with the operator's GitHub token, under rules it described itself.
  - Every answer it gave matched the recommended option, so nothing wrong landed. But the operator's stated rule for this mission was "I'll stop at each PR for you to merge", and from inside the session a prompt answered by ATC cannot be told apart from one answered by the operator.
  - The operator's own go-ahead for this debrief came in chat.
  - The operator has not yet said whether ATC may answer prompts or merge. That needs a written rule in this project, wherever the operator wants it, before the next mission.
- **Crew conduct slips, repeated across flights.** They are all now covered by crew-file rules or squawks:
  - Flight 1: a Developer ran a CPU-burner on the shared host (squawk 0427, completed).
  - Flight 2: shell writes the hook blocked; loaded or incomplete unit tiers reported as results; the false "3 of 3" record.

## Lessons Learned
- **Technical:**
  - xdist surfaces real defects: env leaks and races that serial ordering hid. Treat them as defects, not flakes.
  - A test that starts the app is sensitive to the first request's latency. The boot-ready wait belongs to every navigation, not just the helper (squawks 0424 and 0428).
  - A whole-suite watchdog hides one hung test. Give the tier a per-test timeout (squawk 0435).
  - The `_api` proxy is a sound move-without-behaviour-change device, but it is transitional: it hides the dependency on `api.py`, it does not remove it.
- **Process:**
  - A criterion that depends on the environment needs a mechanical readiness check and a fallback in the flight design. Even then, if it rides a code flight it will be the casualty.
  - A ratchet whose ceilings may be raised with a reason coexists with parallel branches.
- **Patterns worth keeping:**
  - measure first;
  - prove a guard by removing it;
  - event-gated race tests, with no sleeps;
  - ratchets that only shrink;
  - written sequencing rules against parallel work;
  - a bounded quiet-host wait with a fallback.

  Squawk 0426 (completed) documented the xdist patterns. The lock rule needs its CLAUDE.md clause (squawk 0436).

## Methodology Feedback
All on mission-control 1.2.4. These restate observations from the flight debriefs; a later sweep should count each one once.

1. **Environment-dependent criteria have no readiness check or fallback in the flight design.**
   - **Flights:** F1 observation 1. F2 then applied the local remedy, yet T2 still failed.
   - **Skill:** flight, Phases 4-5.
   - **Cost:** a 60-minute wait and a watchdog-aborted gate in F1; an 8-hour fallback gate in F2; T2 not met.
   - **Recurrence:** 2 of 2 flights. Destination: **methodology observation**. The local remedy (readiness check plus fallback) worked as a guard against bad readings, but cannot produce the reading.
2. **"Reuse the flight's gate" does not cover the "host never quiet" case.**
   - **Flights:** F1 observation 4; F2 observation 3.
   - **Skill:** flight-debrief, project crew rule.
   - **Cost:** F2's fresh unit run died after an hour on a hang, though it did surface squawk 0434.
   - **Recurrence:** 2 of 2. Destination: **local fix**, in `.flightops/agent-crews/flight-debrief.md` (a project file): name the case and treat it like an operator deferral.
3. **No milestone reporting during a long autonomous leg.**
   - **Flight:** F2 observation 1.
   - **Skill:** agentic-workflow, Phase 2b.
   - **Cost:** operator uncertainty; no rework.
   - **Recurrence:** 1. Destination: **local lesson** for now. It is a methodology observation if it recurs.
4. **Leg sizing from whole-file counts.**
   - **Flight:** F2 observation 2.
   - **Skill:** flight, Phase 4; leg design.
   - **Cost:** one extra design-review cycle; no code rework.
   - **Recurrence:** 1. Destination: **local lesson**.
5. **A crew agent added load to the shared host.**
   - **Flight:** F1 observation 2.
   - **Cost:** none visible.
   - Destination: **local fix**, done: the crew-file rule, squawk 0427.
6. **A crew agent recorded a verification no run produced.**
   - **Flight:** F2 observation 4.
   - **Cost:** a blocking review and a fix cycle.
   - Destination: **local lesson**. The sign-off caught it as designed.
7. **Who may answer the operator's prompts.**
   - **What happened:** this mission. The skills and the harness assume prompts reach the operator, but a peer session answered them.
   - **Cost:** no wrong outcome. A pause at the mission-debrief go-ahead to confirm with the operator directly.
   - **Recurrence:** 1 mission. Destination: **local lesson**, pending the operator's rule on ATC.

## Action Items
- [ ] **Squawk 0434:** diagnose the `test_resolver_clip[FilesystemConfig]` hang under load (two whole-tier kills).
- [ ] **Squawk 0435:** a per-test `--timeout` on `make test-unit`. `pytest-timeout` is already a dev dependency. Do this before any further unit-tier timing claim.
- [ ] **Squawks 0436 and 0437:** the lock clause in CLAUDE.md, and the misplaced `logger` line. Both are quick wins for the next turnaround.
- [ ] **Squawk 0428 (in progress):** sweep the about 98 raw `page.goto(<base>)` sites onto `_nav.goto`, or add a guard whose count only shrinks; close it after a quiet-host gate.
- [ ] **Squawk 0433 (open):** the mid-turn join test under load.
- [ ] **Connectors mission leg 0:**
  1. extract `api.py`'s shared helpers into one deps module and delete the `_ApiModule` proxies (about 9 copies);
  2. move the agent routes (Sortie 20 has merged);
  3. decide whether the background cascades and `delete_agent` take `agent_write_lock`;
  4. size each route group and grep its patch seams before cutting legs.
- [ ] **T1 and T2:** an operator-triggered measurement run on a quiet host. Re-budget every lane, including the six with no note. Restate the full-gate target. Re-measure xdist N (4, 6, 8). Not inside a code flight.
- [ ] **Local fix:** add the "host never quiet" case to the gate-reuse rule in `.flightops/agent-crews/flight-debrief.md`.
- [ ] **Operator decision:** may ATC answer this project's prompts and merge PRs? Write the answer down wherever the operator chooses.
- [ ] **Later:** a static guard that every agent whole-row `store.save` takes `agent_write_lock` or is on an allowlist. A labelled permanent allowance for append-only `schema.py`. A dedicated flight for `app.py` (4171 lines).
