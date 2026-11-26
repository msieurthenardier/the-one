# Flight Debrief: Backend boundaries before connectors

**Date**: 2026-11-26
**Flight**: [Backend boundaries before connectors](flight.md)
**Status**: landed. It was marked completed after this debrief (operator, 2026-11-26).
**Duration**: 2026-11-25, flight start in the afternoon, to 2026-11-26, landed about 11:45 (PR #394)
**Legs Completed**: 4 of 4. They were `mcp-connector-routers`, `agent-write-lock`, `python-size-ratchet` and `closing-gate`. The planned `agent-routers` leg was deferred.
**Plugin version**: mission-control 1.2.4

## Outcome Assessment

### Objectives Achieved
The code work landed as designed. The work that depends on host timing did not.

- **The router split (P1), partly done.**
  - The MCP and connector groups (17 routes) moved out of `api.py` into `mcp_sources_api.py`, `mcp_connection_api.py`, `mcp_connection_flow.py` and `connectors_api.py`.
  - `api.py` went from 6529 to 5083 lines (5126 after Sortie 20 merged in). The OpenAPI and route-table comparisons are identical.
  - The agent group was deferred to the connectors mission's leg 0. Sortie 20 (PR #392) was still open when that leg would have started, which the flight's sequencing rule anticipated.
- **The per-agent write lock (squawk 0327, completed).**
  - `agent_write_lock(name)` is a refcounted, bounded `asyncio.Lock` registry. Five whole-row writers hold it from load to save: `replace_agent`, `change_agent`, the credentials route, revision approve and revision restore.
  - The lock order is documented: agent lock first, then the store lock, and never inside a hook.
  - Nine interleaving tests are gated on `asyncio.Event`, with no sleeps.
  - The falsification worked: with the lock removed from the credentials route, both credentials-plus-Save tests lose a change.
- **The Python size ratchet (T3).**
  - `tests/test_python_module_size.py` mirrors the JS area guard: 800 lines, and a reasoned `ALLOWANCE` that only shrinks.
  - It forced four reasoned ceiling raises the day Sortie 20 merged, which is the visible-growth behaviour it was designed for.
- **Write-service logging (P5).** One value-free `logger.info` line runs after commit on each create, update and delete path in six modules, with a caplog test.
- **Squawk 0428 (in progress).**
  - `_nav.goto` now waits for the router (`boot=False` opts out).
  - The gate showed the same race at raw `page.goto(base)` sites. The 5 failing ones were wrapped; about 98 remain unwrapped.
- **The closing gate ran on the sequential fallback.**
  - No quiet window came in 60 minutes: load 1 to 20, from other projects.
  - All 23 lanes ran one at a time, in 6 h 36 min at load 2 to 25.
  - Seven failures, all load races, and none new to this flight. Six were fixed and one was logged as squawk 0433.
  - **T2 (re-budget) is not met**, for the second flight running.

### Mission Criteria Advanced
| Criterion | This flight |
|---|---|
| The web API is split into feature routers (P1) | Partly. The MCP and connector groups moved; the agent group goes to the connectors mission's leg 0; `app.py` is untouched. |
| Concurrent agent writes cannot drop credentials (0327) | Met for the five interactive writers. The background cascades and `delete_agent` are recorded as out of scope. |
| Python modules have a size ratchet (T3) | Met. |
| Every browser lane's budget comes from a quiet reading (T2) | Not met. There was no quiet host on either flight, so it goes to the mission debrief as unmet. |
| The unit tier is under 400 s (T1) | Not re-confirmed. See Test Metrics: the debrief run was killed by a hang. |

## What Went Well
- **Falsification as the lock's proof.** Removing the lock, watching both credentials-plus-Save tests lose a change, then restoring it is the strongest evidence in the flight. It is cheap, and it rules out a test that passes regardless (Architect).
- **Two design-review cycles on Leg 1 paid for themselves.**
  - Cycle 1 caught the inverted size estimate (the MCP group was about 1,080 lines, not small) and the missing rule for names that tests patch on `api.py`.
  - Without the mandated `_api` proxy, `patch("...api.X")` in 35 test references would have silently patched nothing.
- **The ratchet worked on day one.** Sortie 20 merged mid-Leg 4, and the ratchet forced four ceiling raises, each with a reason, in the same diff. That is growth made visible, not blocked.
- **The flight's sequencing rule with a parallel sortie held.** The "defer the agent group if Sortie 20 is open" decision, written at flight start, was applied mechanically at Leg 2 with no rework. Merging `main` mid-Leg 4 was clean.
- **The quiet-host check and fallback (Flight 1 recommendation 2) worked as designed.** The bounded wait ended, the fallback ran without overlap, and nothing was re-budgeted from a loaded run. The gate became a full correctness check of Flights 1 and 2 together.
- **The independent reviewer caught a false record.** Squawk 0433 claimed "passes 3 of 3 in isolation" when the only isolation run had failed. The sign-off is the only thing that caught it.

## What Could Be Improved

### Process
- **Leg 1 was planned from whole-file line counts.** The flight's Citation Audit gave `api.py`'s total size, not the size of each route group, so the leg boundary was chosen blind. Size each candidate group, and grep its patch seams, before choosing leg boundaries (Architect).
- **The closing gate cost almost 8 hours of wall time for a correctness check.**
  - A 60-minute readiness wait, plus 6 h 36 min of sequential lanes at 2 to 3.5x budget.
  - The operator noticed the long silence ("running for almost 7 hrs") before the Flight Director reported.
  - The Flight Director should post progress at lane milestones during a multi-hour gate, not only at the end.
- **T2 cannot ride a code flight on this host.** It has been carried twice and missed twice. Both Developer and Architect recommend decoupling timing criteria (T1, T2) from code flights: an operator-triggered measurement run when the host is known quiet, or accept T2 as unmet.
- **Leg 4's "pre-existing on `main`" evidence rests on Sortie 20's recorded `main` run.** This flight did not run `main` itself. It was acceptable here, because those tests are in 0428's Sortie 20 evidence list, but it is borrowed evidence.
- **Crew slips:**
  - the Leg 3 Developer tried three shell writes that the hook blocked;
  - Leg 2's and Leg 3's unit tiers were incomplete or loaded until the Flight Director re-ran them;
  - the Leg 4 Developer wrote an unverified "passes 3 of 3" into a squawk.

### Technical
- **The `_ApiModule` proxy is copy-pasted in 9 modules under `interfaces/web/`,** 4 of them new this flight (Developer). It is sound as a transitional device, but it hides the real dependency: the shared helpers belong in a deps module, not in `api.py`. Every new router will repeat it until the connectors mission's leg 0 extracts the helpers once (Architect).
- **The lock's scope is a convention, not a guard.** Several writers are outside it: the background cascades (`self_configuration/manage.py`, `mcp/rename_references.py`, `knowledge/kb_rename.py`, `db/override_cleanup.py`, `db/migration.py`) and `delete_agent`. "Every new writer takes the lock" lives only in `agents.md`. A static test asserting that every agent whole-row `store.save` site sits under `agent_write_lock` (or is on an allowlist) would enforce it. The lock is also ordering-only: a stale UI read can still be lost, with no `updated_at` precondition.
- **`api.py` is still 5126 lines**, and `app.py` (4171), `repositories.py` (4170) and `schema.py` (3662) are untouched. The ratchet stops growth; it does not shrink anything. `schema.py` is append-only by design and may deserve a labelled permanent allowance rather than repeated raises (Architect).
- **About 98 raw `page.goto(<base>)` sites in `tests/browser/`** have no boot wait. They passed this gate, but they are the 0428 class.
- **The unit tier has no per-test timeout.** `make test-unit` passes no `--timeout`, so one hung test consumes the whole `TEST_TIMEOUT` (see Test Metrics).
- Nit (flight review): in `agent/service.py`, the new `logger =` line separates the retry comment from `_MAX_ATTEMPTS`.

### Documentation
- CLAUDE.md's "Agent PUT preserves credentials" contract does not mention `agent_write_lock`. The lock rule is only in `agents.md`.
- The `_api` proxy and patch rule is only in `agents.md` ("Web route modules (M37 F2 L1)"). That is the right place under CLAUDE.md's no-growth rule, but the debrief notes it for the connectors flight's designers.

## Test Metrics
Every figure names its source. None is a quiet-host reading.

**Unit tier**

| Reading | Tests | Time | Load | Source |
|---|---|---|---|---|
| M37 F1 clean, N=4 | 12353 | 180.6 s and 212.4 s | about 1.6-8 | F1 debrief |
| F2 Leg 1 | 12356 passed | 299.7 s | 10-17 | flight log |
| F2 Leg 2, first run | killed at 98% by 1200 s, in `test_resolver_clip` | — | 17-28 | flight log |
| F2 Leg 2, re-run | 12365 passed, 15 skipped | 310.5 s | 2.8 → 15 | flight log (Flight Director) |
| F2 Leg 3 | 12370 | 786 s | about 18 | flight log |
| F2 Leg 4, merged tree | 12387 passed, 15 skipped | 761.7 s | about 14 | flight log |
| **Debrief run** | **killed at 98% by 3600 s (rc 137)**; 12190 PASSED lines, 0 failed | 3622 s | 15.4 → 18.8 | Developer's fresh run |

- **The debrief run is invalid, not a pass.** It hung in `tests/test_resolver_clip.py::TestProperties::test_clip_is_total_and_resolve_of_the_clip_never_raises[FilesystemConfig]`, a seeded property test that canonicalises generated paths on the real filesystem (F1 profiled it at 7.6 s).
  - Leg 2's first run died at the same place under a 1200 s timeout.
  - Two kills at one test, under two different timeouts, point to a hang or an extreme slow path under load, not load alone.
  - Flight 2 did not touch the resolver, so this is not a Flight 2 regression.
  - Leg 4's 12387 / 15 at 761.7 s is the last valid full reading.
- **Trend.** Test count grew 12353 → 12387 (+0.3%), so volume explains nothing. Time tracks external load. The only near-quiet reading (310.5 s at load 2.8) is consistent with F1. At load 14-18, readings are about 2.4x that, so N=4 has no headroom on a host other projects hold at 15 or more. T1 (under 400 s) holds only below about load 10, and is again unconfirmed on a quiet host.

**Browser tier** (Leg 4 sequential fallback, reference only, not budget readings)
- 23 lanes, one at a time: 7 failed, 4976 passed, 7 skipped, in 23733 s, at load 2 to 25. The sum of the lane budgets is 9900 s, so the heavy lanes ran at 2 to 3.5x budget.
- **Failures:**
  - `chats`: 5 (4 in `test_flow_new_chat`, 1 mid-turn join);
  - `chats-transcript`: 1 (a 5 s `httpx` timeout on `/api/config`);
  - `providers`: 1 (`test_first_start_provider_setup_flow`).
- All seven reproduced in isolation at load 17-22, and all match Sortie 20's record on pristine `main`. Six were fixed (boot wait, 30 s timeout); one is squawk 0433.
- Not comparable with Mission 36 Flight 5's quiet 2736 s `--parallel 3` gate.

**Flakes:** none observed as intermittent. Every failure reproduced under load: the boot-wait race class and the 0433 class.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| The MCP group split three ways, plus the `_api` proxy | Size estimate inverted; tests patch names on `api.py` | Yes: size groups and grep patch seams before leg design |
| `agent-routers` leg deferred, legs renumbered | Sortie 20 still open | Yes: a written sequencing rule with a parallel branch |
| Merged `main` mid-leg; four ceilings raised with reasons | Sortie 20 merged during Leg 4 | Yes: ceiling raises are the expected merge cost |
| The 0428 fix extended to 5 raw `page.goto` sites | The gate showed the same race outside `_nav.goto` | Partly: a sweep or a guard should follow |
| Closing gate on the sequential fallback; T2 not met | No quiet host | Yes, the fallback; but move T2 out of code flights |
| Debrief metrics: fresh unit tier only, browser from the Leg 4 gate | Host loaded all day; a fresh quiet browser run was impossible | Same as F1 observation 4 |

## Key Learnings
- **Size the groups, not the file.** A whole-file line count says nothing about where a split boundary falls, or what a moved group depends on (private helpers, test patch seams).
- **A ratchet with "raise with a reason" coexists with parallel work.** Pinning ceilings to today's counts and allowing reasoned raises let Sortie 20 merge without friction, while making its growth visible.
- **A boot-ready wait belongs to every navigation, not just the helper.** Under load, any `page.goto(base)` followed by a first `expect` races the router start.
- **A whole-suite watchdog hides a single hung test.** Without a per-test timeout, the unit tier reports "killed at 98%" rather than the test's name and stack.

## Methodology Observations
All observations are on mission-control 1.2.4.

1. **agentic-workflow, Phase 2b (a long autonomous leg). Recurrence: 1, first seen.**
   - **What happened:** the closing-gate leg ran about 8 hours in one Developer spawn. The Flight Director reported only at the start and at `[LAND:leg]`, and the operator had to ask ("the agent has been running for almost 7 hrs").
   - **Expected:** for a leg bounded by host time, status at milestones (each lane, or each hour).
   - **Cost:** operator attention and uncertainty. No rework.
2. **flight skill, Phase 4 (design decisions) / leg design (size estimates). Recurrence: Leg 1 here.**
   - **What happened:** the leg's sizing came from the Citation Audit's whole-file counts. The skill's "Interface changes: grep for consumers" check caught the patch-seam issue only at design review.
   - **Expected:** for a code-move leg, the design measures the moved group and its consumers.
   - **Cost:** a second design-review cycle and a re-cut into three modules. Caught before code, so no code rework.
3. **flight-debrief, "reuse the flight's gate" (project rule). Recurrence: 2, F1 observation 4 and this flight.**
   - **What happened:** the gate was loaded, so the rule says run fresh, but a fresh quiet browser run was impossible again. The Flight Director again ran only a fresh unit tier, and this time that run hit a hang and was invalid.
   - **Expected:** the rule names the "host never quiet" case.
   - **Cost:** about 1 hour of a killed unit run. It did surface a real hang.
4. **squawk / leg-execution crew, record integrity. Recurrence: 1.**
   - **What happened:** a Developer recorded a verification result ("passes 3 of 3") that no run produced.
   - **Cost:** a blocking review finding and a fix cycle.
   - The independent sign-off caught it as designed. This is recorded as evidence that the sign-off earns its cost, not as a defect.

## Recommendations
1. **Diagnose the `test_resolver_clip` property-test hang, and give the unit tier a per-test timeout,** before any further unit-tier timing claim. Two whole-tier kills in one flight. **Critical** for T1 credibility.
2. **Connectors mission leg 0: move the agent routes and extract `api.py`'s shared helpers into one deps module,** so the `_ApiModule` proxy stops multiplying (9 copies). Then put the background cascades and `delete_agent` under `agent_write_lock`, or decide explicitly that they stay out. **Important.**
3. **Take T1 and T2 out of code flights.** Record T2 as unmet in the Mission 37 debrief, and re-budget in an operator-triggered measurement run when the host is known quiet. **Important.**
4. **Close the boot-wait class.** Sweep the about 98 raw `page.goto(<base>)` sites onto `_nav.goto`, or add a `tests/test_nav_helper.py` guard whose count only shrinks. **Important.**
5. **A static guard for the lock rule:** a test that every agent whole-row `store.save` sits under `agent_write_lock` or on a reasoned allowlist. **Minor.**

## Action Items
- [x] **Small follow-ups, logged as squawks** (operator, 2026-11-26):
  - [0434](../../../../squawks/0434-resolver-clip-property-test-hangs-under-load.md): the `test_resolver_clip` `[FilesystemConfig]` property test hangs under load;
  - [0435](../../../../squawks/0435-unit-tier-has-no-per-test-timeout.md): the unit tier has no per-test `--timeout`;
  - [0436](../../../../squawks/0436-claude-md-agent-contract-omits-write-lock.md): the CLAUDE.md agent contract omits `agent_write_lock`;
  - [0437](../../../../squawks/0437-agent-service-logger-splits-retry-comment.md): the `logger =` line splits the retry comment.
- [ ] Connectors mission leg 0: the agent-routes move, the shared deps module, and the lock for the cascades and `delete_agent` (recommendation 2).
- [ ] Mission 37 debrief: T2 unmet; T1 unconfirmed on a quiet host; the open squawks 0428 and 0433.
- [ ] Raw `page.goto` sweep or guard (recommendation 4). Its follow-up is already recorded in squawk 0428.
