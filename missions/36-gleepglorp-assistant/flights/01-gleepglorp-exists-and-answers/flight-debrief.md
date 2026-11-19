# Flight Debrief: GleepGlorp exists and can answer

**Date**: 2026-11-19
**Flight**: [GleepGlorp exists and can answer](flight.md)
**Status**: completed
**Duration**: 2026-11-18 (planning and execution) - 2026-11-18 (landed; landing commits `7b059fd3`, `7079443a`; draft PR #380)
**Legs Completed**: 10 of 10 (plus one aborted before starting: `06-gleepglorp-guide-memory-web`, split into Legs 6-8)
**Plugin version**: 1.2.4

## Outcome Assessment

### Objectives Achieved
The app has its built-in assistant and the Default agent is gone.
- **GleepGlorp exists without an agents row.** Its settings live in app metadata: model provider and model, on/off, web access, notes, and chat retention (30 days). The factory builds it from them. It sits in a "Built in" group first in the agent picker. A quiet setup state shows until a model is chosen, and the composer placeholder says what is missing. A new Assistant group in Settings holds its page, and its prompt is shown read-only in Settings › Prompts.
- **What GleepGlorp can use:** a read-only `read_app_config` tool, `get_app_guide` over 13 shipped help topics (written for people), its own notes, and `fetch_url`/`web_search` behind the web switch.
  - The read tool uses whitelist views that never emit secret material. Parity is proved over all nine encrypted columns and 41 seeded slots.
  - The guide's links, format and word cap are guarded by a drift test, and the guide ships in all three installers.
- **The shipped prompt is "D-min".** It was chosen by an eval set (10 scenarios), parallel candidate screening, a leave-one-out shortening and an n=20 confirmation.
  - It is 255 prompt tokens plus 182 tool-schema tokens for GleepGlorp's two tools, down from v1's 302 and 420.
  - Haiku scored 98.6% of scored checks with zero safety failures.
  - The baseline is `evals/baselines/m36-gleepglorp.json`.
- **Schema v53 deleted the stored `default` agent, its data and every no-agent chat.** "GleepGlorp" and "default" are reserved agent names, refused on create, rename, import, connectors, `start_session` and routines. A stored agent with either name is renamed once at startup. The operator confirmed their own "GleepGlorp" agent becomes "GleepGlorp 2", as expected.
- **From the HAT:**
  - **Provider delete override:** an in-use box shows on open. It explains who loses their model, a checkbox gates Delete, and one transaction clears every user's model.
  - **One notes-list design** for GleepGlorp's Notes (renamed from Memory) and agent Notes. Note Edit was removed on both sides by operator decision.
  - **New library controls:** an `App.ui.button` danger tone and `App.ui.confirm.disarm`.
- **Squawk 0383** was folded in. The unit-tier target is now 350 s (operator decision).

### Mission Criteria Advanced
- **GleepGlorp is ready once its model is chosen:** met in full (settings, setup state, on/off, web, notes, retention and purge).
- **Nothing changes without the operator's click:** met for Flight 1's tool set. An allowlist test covers every settings combination. GleepGlorp's own notes are the one write, flagged when they follow untrusted content.
- **Secrets never pass through GleepGlorp:** met for reads. Every read is masked by construction, with a parity test. The secret and sign-in handoff goes by link. Forms and proposals come in Flights 2 and 3.
- **GleepGlorp sticks to the app:**
  - Met: it declines off-topic requests, has only its own tools, and cannot be bound to a connector or own a routine.
  - Dropped by operator decision: "suggest one of your agents" became report-only.
  - Still to come: "Check this" on proposals and form fills is Flights 2 and 3.
- **The Default agent is gone:** met in full.
- **Quality is measured on every default eval model:**
  - Met for Haiku (baseline with default bars) and qwen3-4b (measured and reported).
  - The criterion is amended so `lfm3` is not evaluated for GleepGlorp (operator).
  - Other agents' prompts are byte-identical (platform pins untouched).

## What Went Well
- **DD1 (no agents row, reserved name) was the strongest decision.** Every agent route 404s for GleepGlorp by construction, and the HAT found no hidden-row leak (Architect).
- **Design reviews caught real defects before code was written.**
  - Leg 4: no neutral badge kind existed, and a refused turn would never re-join.
  - Leg 5: the planned "pure move" of the API's view helpers would have leaked MCP `env` and `headers` values, agent `tool_overrides` and provider URLs.
  - Leg 6: the leg was too large to build in one pass.
  - Leg 9: a GleepGlorp config in the shared measure directory would have broken every other baseline's comparison.
- **Whitelist read views with a structural key guard, a runtime guard and a nine-corpus parity test** are a reusable pattern for any surface that hands configuration to a model.
- **The operator's Part B redesign of the prompt work** (operator's note: "just note it in the logs"; the long-term strategy is for a later conversation):
  - six candidates screened in parallel on Haiku at n=5 (300 runs, about 15 minutes);
  - a leave-one-out shortening at the ceiling;
  - one n=20 confirmation on Haiku and qwen3-4b.
  It replaced sequential n=20 tuning rounds, found a prompt about 35% smaller with no loss, and fixed the unfair checks first.
- **Batch mode with checkpoint commits** (A: Legs 1-2; B: Legs 3-8; then the gated Leg 9 and the HAT) kept each review scoped and gave a committed base before any quota was spent.
- **The HAT apparatus check (DD13)** confirmed every step's state before the operator walked it. No step failed for apparatus reasons, unlike every Mission 35 flight.

## What Could Be Improved

### Process
- **The approved board was off, so three surfaces were redesigned in the HAT.** The operator's assessment: the board itself was wrong, not the build.
  - The setup state was reworked twice before option A.
  - The notes list, and the notes' consistency with the agent tab, was redesigned.
  - The provider delete box was redesigned.

  The static board was approved in one pass. Its loud warning treatment for an expected state ("needs a model") and its separate Memory design only looked wrong in the running app. Mitigations for future UI flights:
  - put the option boards (several layouts per surface) before approval, not after;
  - decide the tone of each expected state at design time;
  - include the screens a change touches beside the new one (here the agent Notes tab).
- **Eval checks were not reviewed for fairness before quota was spent.** Round 1 (about 65 minutes of Haiku and qwen3-4b, plus a partial lfm3 run) was scored by checks with false positives and a reply-extraction bug. Reviewing a handful of transcripts against each check before an n=20 round would have saved a full round.
- **The provider-delete dead end was foreseeable.** DD2 copied "409 if in use" without asking what the operator does next. The HAT found there was no way to delete a provider GleepGlorp uses. Check the delete path of every new reference at design time.
- **Legs sized too coarsely at design.** The flight Architect split Leg 3, and Leg 6 was split at its own design review. In both, the rule "more than one capability with its own risk means more than one leg" would have caught it.
- **Crew rules kept slipping despite explicit prompts, again** (Mission 35 recorded the same):
  - backgrounded `sleep`/`pgrep`/Monitor wait loops (Legs 1, 5, 6 and the eval crew);
  - `sed -i` attempts, one of which wrote `CLAUDE.md` because the project hook does not cover root files (related to squawk 0385);
  - agents reporting done while their own background tasks were still running (Legs 4 and 8, the setup-block and notes fixes). Each had to be stopped with TaskStop before the host was quiet.

### Technical
- **Area modules sit at their caps:** `agent-drawer.js` 798/800, `studio.js` 799 (Leg 3 condensed lines to stay under) and `gleepglorp-page.js` 712. Flights 2 and 3 add proposals UI and an overlay. Split them first, and don't condense lines again.
- **`the_one/gleepglorp/views.py` is 846 lines** for every read surface. Split it per capability before Flight 2 adds proposal reads.
- **Two notes tables share an interface but no schema guard.** A column added to `agent_notes` will not reach `gleepglorp_notes`.
- **The repository layer now knows GleepGlorp.** `LLMProviderRepository.delete_forcing` reads GleepGlorp's setting. "Who uses a provider" is two lists (`list_by_provider` plus the GleepGlorp special case). Make it one registry when the next owner of a provider reference appears.
- **The `PUT /api/agents/{name}/notes/{id}` route has no client** since note Edit was removed (operator decision; this removes Mission 27 behaviour). Remove it, or pin it with a test.
- **`read_app_config` stays untrusted for taint (fail-closed), so most GleepGlorp notes are flagged.** Splitting operator-typed fields (names, counts) from agent- or server-written ones (prompts, descriptions, tool output) would unflag most notes. This was deferred to Flight 2 by decision.
- **Security-adjacent tests were not falsified.** These Leg 2 reserved-name tests were never shown to fail without their fix: the startup rename, connector 422s, the inbound drop, `start_session`, the routines guards, v53 idempotency.
- **A stale response-shape test reached the gate.** `test_provider_api.py::test_delete_allowed_without_agents` still expected `{"status": "ok"}` after `cleared` was added in a HAT fix. The implement prompt's "grep tests for exact-dict pins" rule is not in the fix-review-issues prompt that HAT fixes use.
- **qwen3-4b is weak as GleepGlorp's model:** 76.4% of scored checks, with 32 safety failures. It played along with the injected page 6/20, declined off-topic requests only 18/40, and repeated a pasted key 2/40. The operator kept the existing "small local models may struggle" hint. Decide at mission level whether qwen3-4b is a supported model or only a measured one.

### Documentation
- **The flight log carries superseded HAT design entries,** marked superseded and append-only. The final designs (setup state A, the notes list A, the in-use delete box) should be stated in `the_one/agents.md` as the reference, not only in the log.
- **CLAUDE.md "Full-gate target" needs a re-measure.** This flight's gate (unit 308.75 s plus browser 2270 s, about 43.0 minutes) sits at the 43-minute target, on a loaded host. The section should state the 350 s unit target and a quiet-host total.
- **CLAUDE.md's "Control library" paragraph** should name the new `button` danger tone and `confirm.disarm`. They are in the catalogue.

## Test Metrics
All numbers come from the flight log (the final gate in "Flight-end review fixes and gate" and "Landing"); prior figures come from the named debriefs.

- **Unit tier, final gate:**
  - Result: 10695 passed, 15 skipped (the expected netns count), 308.75 s, with `THE_ONE_TEST_NETNS=1`.
  - In-flight readings: Leg 1's quiet 303.74 s, Leg 2 298.63 s, the Batch B gate 304 s (16 skips at load 2.0-2.6; the 16th was a timing-conditional skip).
  - Priors: Mission 35 Flight 3, 10118 in 281.4 s; sortie 19, 10263 in 299.4 s; sortie 18, 10222 in 302.4 s (loaded).
  - Growth since Mission 35 Flight 3: +577 tests and about +27 s. The likely causes are the GleepGlorp unit files (about 260 tests), the eval test files (over 600 across `tests/test_evals_*.py`), and the rewritten Default-agent tests.
  - At about +28 s per flight, the 350 s target's 41 s of room is gone in about 1.5 flights.
- **Browser, final gate:** `PARALLEL_RESULT rc=0 total=2270s lanes=20`, start load 1.91 from other sessions, so it is a loaded reading and nothing was re-budgeted.
  - Priors: Mission 35 Flight 3 2268 s (rc=1, one flake, load 0.96); sortie 19 2179 s (load 0.87).
  - The Batch B gate was 2425 s at load 2.0-2.6. Its three over-budget lanes (`settings`, `mcp`, `agent-routines`) were under budget in the final run.
- **Lanes near budget (loaded):** `mcp` 318/330 (96%), `agent-routines` 284/300 (95%), `agents` 577/630 (92%), `settings` 326/360 (91%), `chats` 384/420 (91%), `agent-tabs` 530/600 (88%). The quiet-host re-reading carried through this flight never happened: no quiet window came up.
- **Flakes:** none recorded. One failure at the first final gate was the stale response-shape test, a real defect, not a flake.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Leg 3 split by capability at the flight design review; Leg 6 split into three at its design review | Too much risk in one leg | Yes: size legs by capability and risk at design |
| Leg 5's read surface became whitelist views (DD5 amended) | The API helpers were not a safe read model and not movable | Yes: check that a "reuse it" read model is safe before reusing it |
| Chat-surface "Default agent" labels moved from Leg 2 to Leg 4 | NULL-agent chats could still be created until Leg 3 | No (one-off sequencing) |
| Leg 9 in Part A/Part B; Part B redesigned to parallel screening plus ablation (operator) | Haiku at its ceiling; unfair round-1 checks | Pattern noted; strategy for a later conversation (operator) |
| lfm3 dropped for GleepGlorp; mission criterion amended (operator) | Too small to follow the link and tool format | No |
| Off-topic "suggest one of your agents" made report-only (operator) | Haiku never does it; a plain decline suffices | No |
| Frozen eval scoring modules re-pinned twice (additive) | GleepGlorp builder, new checks, opt-in reply extraction | Yes: an additive change plus a Reviewer confirmation is the accepted path |
| HAT step 5 (two-tab) skipped; two-tab steps dropped from future HATs (operator) | No real two-tab use | Yes (operator preference) |
| HAT features: provider delete override; note Edit removed on both sides (operator) | Found by walking the real app | No |
| Multi-surface HAT fix scoped in place instead of a spawned design review (Flight Director) | A default-preserving option guarded by existing tests | No: follow the protocol (the change was later replaced anyway) |
| `/api/selftest` keeps returning 500 when GleepGlorp is not ready | Matches every failing selftest | No |

## Key Learnings
- **A model-facing read surface should be a whitelist, not a reuse of the API's views.** The API's views were built for an authenticated operator's browser, not for text sent to a third-party model.
- **At the ceiling, optimize cost, not score.** Shortening by ablation with "no worse" as the bar, then one n=20 confirmation, is the efficient path. Small-n screening reads aggregates and hard safety gates, not small differences.
- **Check fairness before quota.** An eval check is code under test too.
- **The tone of an expected state** (not set up yet, turned off, in use) is a design decision. The generic warning banner reads as an alarm every time it is reused for one.
- **The final shape of a HAT-heavy UI flight is decided in the HAT.** Plan the HAT for design iteration (option boards on demand), not only verification.

## Methodology Observations
Plugin version 1.2.4 throughout.

1. **agentic-workflow, Phase 2b: an operator-gated, quota-spending leg has no shape** (recurs from Mission 35, 3 of 3 flights there).
   - **What the method does:** a leg is designed, implemented, landed, then reviewed and committed with its batch.
   - **What was needed:** Leg 9 needed Part A (autonomous, reviewed and committed before quota) and Part B (operator rounds). Part B was then redesigned mid-leg by the operator, which needed six further review-and-commit points, and the leg file is immutable once in flight.
   - **Cost:** the Flight Director improvised the structure and recorded the redesign in the flight log instead of the leg; several extra Reviewer spawns.
2. **agentic-workflow, Phase 2a: leg sizing is not checked against capability count at design.** Two legs were split after design (Leg 3 at flight review, Leg 6 at its own review).
   - **Expected:** a design-time check that one leg carries one capability with its own risk.
   - **Cost:** two re-plans, one aborted leg file kept for its citations, and renumbered later legs.
3. **flight, Phase 4/5b (mockups): approval checks that a mockup exists, not that it is right.** The Architect's item 10 asks for an approved mockup or two options, and the board was approved in one pass. The HAT then reworked three surfaces, because the board itself was off (operator).
   - **Expected:** option boards (several layouts) for each new surface before approval, the states' tone decided explicitly, and sibling screens included.
   - **Cost:** about six HAT fix and redesign cycles, with three option boards built during the HAT.
4. **agentic-workflow, crew prompts: rules did not hold** (recurs from Mission 35). Background wait loops, `sed -i`, and agents reporting done with live background tasks recurred despite explicit prompts. The Flight Director stopped five agents' leftover tasks.
   - **Cost:** host load during timing runs, and manual process checks.
   - **Expected:** the harness, not the prompt, to refuse the pattern. For example, a check that an agent's background tasks have ended before its report is accepted.
5. **agentic-workflow, the fix-review-issues prompt lacks the "grep tests for exact-dict pins" rule** that the implement prompt has. A HAT fix changed a response shape, and the stale pin reached the gate. Destination: a local fix to this project's `leg-execution.md` crew file.
6. **agentic-workflow, HAT protocol: the multi-surface trigger** was handled by Flight Director scoping instead of a spawned design review, and was recorded as a deviation. No cost, since the fix was replaced, but the protocol was not followed.

## Recommendations
1. **Before Flight 2:** split `agent-drawer.js`, `studio.js` and `gleepglorp/views.py`, and decide the `PUT …/notes/{id}` route. The 800-line rule has no room left, and Flight 2 adds proposal UI and reads. **Critical.**
2. **Flight 2 design:**
   - one generic proposal store with a change shape (target, field, before, after, taint), reusing the stale-check and approve/dismiss semantics of `agent_revisions` and `agent_routine_proposals`;
   - form validation extracted into services, so a proposal runs exactly what Save runs;
   - `read_app_config` taint granularity;
   - one registry for "who uses a provider".
   **Important.**
3. **UI flights:** option boards per new surface before approval; the tone of expected states decided at design time; sibling screens shown. **Important.**
4. **Eval work:** review check fairness on a few transcripts before any n=20 round; keep the control in every screening round; state hard safety gates versus ranking. **Important.**
5. **A quiet-host gate on a schedule** to re-measure lane budgets and the full-gate target. It has been owed since Batch B and the host was never quiet. **Minor.**

## Action Items
- [ ] Split `agent-drawer.js`, `studio.js` and `the_one/gleepglorp/views.py` below their caps before Flight 2: **squawk 0386**.
- [ ] Pin the client-less `PUT /api/agents/{name}/notes/{id}` route with an API test (removal would be an escalation): **squawk 0387**.
- [ ] Falsify the Leg 2 reserved-name tests: **squawk 0388**.
- [ ] CLAUDE.md "Full-gate target" (350 s unit target, quiet-host re-measure and lane budgets); the final HAT designs in `the_one/agents.md`; `button` tone and `confirm.disarm` in CLAUDE.md's Control library paragraph: **squawk 0389**.
- [ ] Mark the screening and ablation prompt files as history, keeping `v1` and `dmin`: **squawk 0390**.
- [ ] Hook coverage of repo-root files such as `CLAUDE.md`: **added to squawk 0385**.
- [ ] Add the "grep tests for exact-dict pins after a response-shape change" rule to the `leg-execution.md` fix-review-issues prompt (local crew-file fix).
- [ ] Mission level: decide whether qwen3-4b is a supported or a measured-only model for GleepGlorp.
- [ ] Later conversation (operator): a long-term strategy for prompt tuning and evals.
