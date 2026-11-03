# Flight Debrief: Self-configuration leaves the Tools tab

**Date**: 2026-11-03
**Flight**: [Self-configuration leaves the Tools tab](flight.md) (sortie 08; no parent mission)
**Status**: completed (landed, then debriefed and closed 2026-11-03)
**Duration**: 2026-11-03 (planned, executed and landed the same day)
**Legs Completed**: 1 of 1 (no HAT, by operator decision)
**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved
The agent editor's Tools tab no longer shows the self-configuration server or its tools, and the server now owns everything about that server on an agent:
- Agent writes never attach or detach it; the stored attachment is carried, including when `mcp_source_ids` is omitted.
- A non-empty per-agent `mcp_overrides["self-configuration"]` is refused with a 422 that names the Self-configuration tab.
- `mcp__self-configuration__*` entries in `disabled_tools` are stripped on write.
- Stored withholds of either kind are ignored at every build site and removed at startup.
- `CLAUDE.md`, `the_one/agents.md` and `SECURITY-MODEL.md` name the Self-configuration tab as the only control.

Everything shipped as commit `480662d3` (landing commit `d85c7614`) in PR #355.

### Charter Criteria (the sortie's only criteria assessment)
- [x] **The Tools tab shows no self-configuration tile or tool rows, and shows the empty state when there are no other servers.** Met. Browser tests (`agent-tabs`, `agents`) and behavior-test checkpoints 3, 4 and 12, with screenshots and accessibility snapshots.
- [x] **Saving from any tab keeps self-configuration attached, and the agent keeps its four tools.** Met. Unit carry tests (falsified), browser saves from General and Tools, and behavior-test checkpoints 5 and 6.
- [x] **Old withholds stop applying and are cleared, and the API refuses a new one with a 422.** Met. Behavior-test checkpoints 7-11: a 422 with nothing stored; a real `update_my_description` call succeeded while both legacy withholds were stored; a restart's cleanup logged the agent and removed both; the tool still worked afterwards.
- [x] **The three docs name the Self-configuration tab as the only control.** Met. The leg's greps came back clean, and the Reviewer checked the docs.

### Checkpoints
All four were met. One flight-spec slip: the third checkpoint named a `routing` lane that the leg never touched. The fresh debrief gate ran it green anyway.

## What Went Well
- **The design reviews earned their cost.** Each pass found a real defect before any code existed:
  - Architect review 1: five orphan-via-PUT tests that DD2 would break; an unguarded every-agent scan that could stop startup on one undecryptable row; `disabled_tools` as a second per-tool withhold (DD7); a carve-out that could wipe an ordinary server's overrides.
  - Architect review 2: four inconsistent handlings of a pre-reservation row named `self-configuration`, resolved by declaring that state unsupported.
  - Leg design review: an omitted `mcp_source_ids` detaches today (AC3b), and the credential merge re-injects a stored entry, so any Save needed to pop it (AC7).
- **The behavior test proved the hardest claim with a real tool call, not a projection.** Step 8 wrote legacy withholds straight to the database while the server ran; step 9 had the mock provider call the write tool, and the revision rows could only exist if the tool was truly registered. It passed 11/11 on a scratch instance from the branch, and the Validator needed no fresh observations.
- **Reading the code before writing the charter caught the most important risk.** Studio's Save builds `mcp_source_ids` from the visible switches, so removing the tile alone would have silently detached self-configuration. That finding shaped DD2.
- **Recovery from a partial hand-back was cheap.** The same Developer was resumed with SendMessage, kept its context, and finished the gates, falsification and log without re-reading the leg.
- **Every fixed `PreToolUse` and project rule held.** No shell writes into the tree, `env.sh` was kept out of every commit, every PID was stopped by PID, and ports 8484/8485 were never touched.

## What Could Be Improved

### Process
- **One leg with 22 acceptance criteria was too large for one implementation pass.** The first Developer handed back partial: code done, but the gates, falsification and flight-log entry not started. Both the Architect and the Developer independently name the same seams: (a) server rules plus unit tests, (b) Tools tab plus browser tests, (c) docs, retirement and gates. The flight said (a) must precede (b), which is a real ordering constraint, so the split costs little. A sortie's two-leg soft limit was never at risk here; one leg was a choice, not a requirement.
- **The flight's gate ran two browser lanes solo, never the full `--parallel 3` suite.** AC21 named only `agent-tabs` and `agents`. The PR was marked ready before the full suite had run; it first ran at this debrief, under the crew file's "run fresh" rule, and passed. For a change that touches a shared surface (the agent write routes), the leg's gate should name the full browser run.
- **Falsification was partial.** Five guards were falsified: the carry, the 422, the factory exemption, `override_for` at the projection site, and the startup strip. Not falsified: the `disabled_tools` strip, `override_for` at the provider and `search_tools` index sites, `is_platform_surface`, the prefix pin, the empty-entry drop and the omitted-key cleanup. The two build-time layers (strip on write, ignore at build) can each make the other's tests pass, which is exactly where falsification matters most.

### Technical
- **`api.py` grew by about 100 lines** (to about 6950). `_normalize_surface_fields` and `_drop_surface_override` are write-boundary rules that belong beside `carry_surface_attachment` in `self_configuration/manage.py`. `create_agent` and `update_agent` each now carry an ad hoc list of server-owned fields: the Routines switches, `tool_overrides`, `kb_ids`, credential preservation, and now the surface. The next one must be remembered in both routes.
- **A new dependency direction: `mcp/` imports `self_configuration.constants`.** It is acceptable because `constants.py` is a leaf, but it is new.
- **`is_platform_surface` is read with `getattr(..., False)`.** That is duck typing chosen for test stubs, not a typed contract. If a second platform-owned source ever appears, promote it to a `Tool` base attribute.
- **`SURFACE_TOOL_PREFIX` is a hand-copied literal**, pinned by a test against the normalization rule.
- **Known, accepted effects:**
  - A leftover legacy `self-configuration (<agent>)` key stays stored and logs a WARNING on each build.
  - Each agent changed by the strip gets one `updated_at` bump.
  - A deep link to the surface's Tools tile does nothing.
  - One over-long docstring line in `_reject_reserved_surface_name`.

### Documentation
- `flight.md` DD4 still names `strip_surface_overrides(agent_store, mcp_repo)`. The code takes only `agent_store`, a change made at the leg review and recorded in the flight log. Annotated in `flight.md` with this debrief.
- `the_one/agents.md` (the "Sortie 08" bullet at about line 920) names `is_platform_surface` and the unsupported same-name state in one line. It does not give the `getattr` fallback contract, when to promote it to a base attribute, or why there is no carve-out. Without those, a later maintainer may re-add a carve-out. → squawk 0326.

## Test Metrics (fresh run at this debrief, on `d85c7614`)

| Item | This run | Prior (source) | Delta |
|---|---|---|---|
| Unit tier, `THE_ONE_TEST_NETNS=1 make test-unit` | 8777 passed, 15 skipped, 0 failed, 226 s (start load 0.03) | 8577 passed, 12 skipped, 229 s solo (Mission 34 F1 L01) | +200 tests: Sortie 07, Mission 34 and about 37 from this sortie. The skips are the documented netns count. 3 s faster. |
| Browser gate, `--parallel 3` | `PARALLEL_RESULT rc=0 total=1858s lanes=17 failed=-` (start load 0.85) | `rc=1 total=2027s lanes=17` (Mission 34 F1 L02, start load 0.23) | 169 s faster; no failures. The flight-gate `agents` flake did not recur (180/180). |
| Full gate | about 2084 s (35 min) | 2256 s (Mission 34 F1) | Within the 43-minute target. |

Lane times (wall seconds against budget, passes): routing 570/720 (186), agents 526/630 (180), agent-tabs 373/510 (163), chats 381/420 (176), contracts-controls 363/600 (1172, 4 skipped), shared 349/420 (354), providers 344/420 (139), library 328/420 (106), knowledge 318/420 (65), mcp-connection 284/390 (94), settings 275/360 (108), agent-routines 271/300 (86), chats-transcript 270/390 (97), mcp 263/330 (87), settings-tools 258/330 (172), contracts-overlay 175/330 (548, 1 skipped), contracts-chat 47/90 (148). None is over budget.

The tightest lanes are `chats` (91% of budget) and `agent-routines` (90%). This sortie touched neither. The shorter browser total is most likely run-to-run variance plus the absence of the retry Mission 34's run had; this sortie did not change the lane mix, and `agent-tabs` kept its 163 tests.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| DD7 (`disabled_tools`) added at Architect review 1 | A second per-tool withhold path would have contradicted the charter | Yes: when a flight removes a control, ask "what other field grants the same capability?" at design time |
| DD4's same-name carve-out added at review 1, dropped at review 2 | Four inconsistent handlings of one corner case; the state was already broken by tool-name collision | Yes: name an unreachable or already-broken state as **unsupported** rather than special-casing it |
| `strip_surface_overrides(agent_store)`, without `mcp_repo` | The strip scans agents by name; it needs no repo | No (case by case) |
| AC3b (omitted `mcp_source_ids`) and AC7 (post-merge pop) added at the leg review | The flight's DD2/DD3 solved the refusal path but missed the omitted-field and re-injection paths | Yes: for "server owns field X", design every write shape (field present, omitted, merged from storage) together |
| Implementation resumed after a partial hand-back | The leg was too large for one pass | Yes: legs over about 15 ACs get a split or explicit resumable checkpoints |
| Full browser suite first ran at the debrief, not before the PR was ready | AC21 named only the two owning lanes | Yes: a leg touching a shared server route names the full `--parallel 3` gate |
| Behavior-test spec reworded after its first run | Six Validator observations (two-sentence 422 message, repeated mock calls, setup field names, etc.) | Yes: a first run of a new spec is also its shakedown; budget for wording fixes |
| No HAT; a Flight-Director-run behavior test instead | Operator decision at charter time | Yes, for a removal with no new layout |

## Key Learnings
- **Removing a UI control can silently change server state through a form that rebuilds its payload from the DOM.** Before deleting any control, check what the save path collects from it; that is how DD2 was found.
- **"The server owns this field" is one rule with many write shapes:** a field present in the body, omitted, re-injected by a merge from storage, carried in a second field, and already stored before the upgrade. This sortie found them one review at a time. Listing the shapes up front would have saved two review cycles.
- **Defence in depth (strip on write plus ignore at build) needs falsification per layer**, because each layer can mask a broken other layer in tests.
- **A behavior test that drives a real tool call through a scripted mock provider is a cheap, decisive observable** for "is this tool registered?", stronger than any projection endpoint.

## Methodology Observations
1. **Agentic-workflow leg implementation, plugin 1.2.3.**
   - What happened: the workflow spawns one Developer per leg, and the leg had 22 acceptance criteria; nothing in leg design prompts a split by size, so the Flight Director kept one leg. The Developer handed back PARTIAL, with code done and gates, falsification and log undone, and had to be resumed by SendMessage.
   - Expected instead: leg design (`agentic-workflow` Phase 2a, "Size for decisions and risk, not effort") would flag a leg whose AC count or file count suggests it will not fit one implementation pass, or would require resumable checkpoints inside such a leg.
   - Cost: one resume cycle, about 15 minutes. It was recoverable only because SendMessage was available; a re-spawn would have had to rebuild context.
2. **Agentic-workflow gate before the PR, plugin 1.2.3.**
   - What happened: the flight's acceptance gate (the leg's AC21) named only the two owning browser lanes. The workflow committed, opened the PR and marked it ready without a full browser suite. The full `--parallel 3` run happened only because the project's debrief crew file requires a fresh gate when none can be reused.
   - Expected instead: the workflow (Phase 2d or Phase 3) confirms that a full test gate ran on the flight's final code before marking the PR ready, or names that gate as a flight-level prerequisite to landing.
   - Cost: none this time, since the run was green. The risk is a regression in an unowned lane reaching a ready PR.
3. **Sortie skill, flight design, plugin 1.2.3.**
   - What happened: the sortie's one "cluster of decisions" was reshaped by three review passes (two Architect, one leg-design), each finding a facet of the same rule. Criterion 2 of the gate ("one cluster") held, but the cluster was wider than the charter conversation saw.
   - Expected instead: nothing is clearly wrong. The re-check gate (sortie skill step 5) was applied and correctly kept it a sortie. Recorded so a sweep can see whether "one cluster, many facets" recurs.
   - Cost: two extra review cycles (about 10 minutes of Architect time), well spent.
4. **Behavior-test skill, Phase 2/3 agent lifetime, plugin 1.2.3.**
   - What happened: both the Executor and the Validator ended their turn after each step with a hand-back. Several Executor hand-backs said "my run ends", despite the crew prompt's "you are resumed by SendMessage" rule. Resuming by SendMessage worked every time, and the browser state persisted.
   - Expected instead: the agents treat their hand-back as interim. In practice each step was a resume, which the skill's live mode allows.
   - Cost: none. The prompt rule does not stop the wording, but it did not matter.

## Operator Input (debrief interview)
1. **Approval mode posture:** keep the default off (operator, 2026-11-03). With per-tool withholding gone, approval mode is the only gate on an agent editing its own prompt. That is intended: `SECURITY-MODEL.md` recommends it for any agent whose context can carry attacker-influenced content, and the operator turns it on per agent. No follow-up.
2. **Follow-ups:** the operator chose to log both squawk candidates, 0325 and 0326.
3. **No further notes on how the sortie ran** beyond the logs.

## Recommendations
1. **Consolidate the agent write boundary.** Move `_normalize_surface_fields` / `_drop_surface_override` into `self_configuration/manage.py`. Then introduce one declared table of server-owned and preserved `AgentConfig` fields (the field, the route that owns it, and whether a write ignores, carries, strips or refuses it), applied by both `create_agent` and `update_agent`, with a unit test that classifies every `AgentConfig` field, modelled on `tests/test_api_name_rule.py`. This is design work: it belongs to routine maintenance or the next mission touching `api.py`, not a squawk.
2. **Falsify the unproven guards.** `override_for` at the provider and `search_tools` index sites, the `disabled_tools` strip (assert on the stored value, not only on tool presence), and the empty-entry drop. Optionally add a grep guard that fails on any new `(mcp_overrides or {}).get(source.name)` outside `override_for`. → **squawk 0325** (servicing, routine, open).
3. **Document the `is_platform_surface` contract and the unsupported same-name state in `the_one/agents.md`.** → **squawk 0326** (servicing, routine, open).
4. **Security posture for prompt self-edits:** decided. The operator keeps approval off by default (see Operator Input). No action.
5. **For future legs:** split or checkpoint any leg over about 15 ACs, and name the full `--parallel 3` browser gate in any leg that touches a shared server route.
