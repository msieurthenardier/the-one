# Flight Debrief: Agent tool overrides

**Date**: 2026-11-03 (retroactive; see Process)
**Flight**: [Agent tool overrides](flight.md)
**Status**: completed
**Duration**: 2026-10-27 (planned) - 2026-10-31 (flown and merged as PR #346, `ae2296f1`); closed 2026-11-03 (PR #354)
**Legs Completed**: 5 of 6 (legs 1-5; the optional `hat` was skipped by operator decision)
**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved
Agent tool overrides are now honest in both directions.
- **On the way in.** `create_agent`/`update_agent` check every new or changed override field with the strict `resolve`, through `the_one/tools/override_validation.py::validate_overrides`. A widening or invalid value is a 422 on `loc ["tool_overrides", tool, field]`, and the agent tab shows it on the field.
- **While stored.** The tab stores only what the operator changes: inherited/own states with Reset, and denied lists that hold only the agent's additions (DD3's union). A once-only startup cleanup (`the_one/db/override_cleanup.py`) removed the copies earlier saves made.
- **After a tightening.** The build path clips through the total `clip_override` (`the_one/tools/resolver.py`), so a stale override can no longer fail a chat.
  - A derived, non-dismissible notice shows on the tab indicator, the Agents row, the tool row, the field and the chat drawer.
  - Settings › Built-in tools previews the agents a save would narrow.
- **Redirects.** Web tools check Allowed hosts and Denied hosts on every redirect hop (`SSRFGuardedTransport`, pinning on a copy of the request).
- **Path fields.** They say how Shell, Python and downloads are limited on this computer.
- **The operator's original defect** was a chat refused with an unhelpful `FilesystemConfig` message, after a save the tab had accepted. That is closed in code and tests. It has not been tried on the Windows build (operator, 2026-11-03: "not yet").

### Charter Criteria
| Criterion | Status | Notes |
|---|---|---|
| A widening override is refused in the editor and the API, on the field, naming the tool and where to change it; nothing saved (closes 0257) | met | `tests/test_api_agent_tool_override_validation.py` (28 tests, exact sentences, every failure type); browser 422-on-field tests in `agent-tabs`. Squawk 0257 completed. |
| Open-and-save stores nothing; inherited/own shown with one-step Reset | met | `test_flow_studio_tool_override_state.py` (API read-back). The cleared-field behaviour took two review fix passes (see Deviations). |
| A tightened app-wide value clips the agent to the intersection, chats never fail, Settings previews, notices on drawer/tab/row/field with both fixes, non-dismissible | met, with one known gap | Property tests in `tests/test_resolver_clip.py` (never raises; `resolve(clip(...))` never raises; never wider than either input); `test_api_tool_config_impact.py`; `test_flow_studio_tools_notices.py`, `test_flow_chat_drawer_notices.py`, `test_flow_admin_tools_impact.py`. **Gap (accepted under DD8):** re-enabling a tool from its Settings tile can add notices with no warning first. |
| With Shell or Python on, the path fields say how those tools are limited on this computer | met in tests; **not seen live** | Posture pinned by stubbing `App.config.execution_sandbox`; `execution_sandbox` in `/api/config` is unit-tested. The live bubblewrap wording and the Windows passthrough wording were HAT steps, and the HAT was skipped. |
| A redirect to a forbidden host is refused like a first URL | met in tests; **not seen live** | `tests/test_web_redirect_hosts.py` and `test_web_helpers.py` run through the real pin path under `httpx.AsyncClient(follow_redirects=True)`. They cover relative `Location`, allow, deny, `NO_HOSTS` and punycode. No real CDN redirect has been tried. |

### Was a sortie the right vehicle?
**Yes, at the edge.**
- **One decision cluster held throughout DD1-DD13:** "what an agent override may hold, and what happens when the app-wide value moves".
- **Two items rode along by operator decision (2026-10-27):**
  - The redirect fix (DD15) is a separate, pre-existing SSRF defect with its own risk. It was added after Architect review 1 found redirects skip both host lists.
  - The Shell/Python wording (DD10) documents a gap rather than fixing it.
- **In hindsight** DD15 could have been its own squawk or small sortie. Folding it in was defensible because it touched the same review surface (the host lists' semantics changed in DD4).
- **The legs outgrew the sortie soft limit of 2 plus HAT:** 4 planned plus HAT, then 5 flown plus HAT. Leg 1 was split along the design reviewer's seam. Each flown leg had its own risk tier: the clip rule, save/notices, the SSRF transport, the UI, and the surfaces.
- **The operator found the planning weight worth it** (2026-11-03).

## What Went Well
- **The reviews caught real defects before code.**
  - Architect review 1 found these:
    - redirects skip both host lists;
    - an agent `[]` against a non-empty app-wide `host_allowlist` resolved to "any host", a live hole with no test;
    - the denied-list check made "store only what you change" impossible;
    - an empty path intersection must not offer "Use narrowed value".
  - Architect review 2 found the transport pinning by mutating `request.url`, which would have refused every relative redirect.
- **The property tests did their job.** They pin three properties over arbitrary JSON, and they found a real drift between the strict and lenient paths: an app-wide list holding `NO_HOSTS` beside other hosts.
- **Strict on write, total clip on read.** Keeping `resolve` strict left every existing caller and the "only narrows" guarantee intact. `clip_override` is a separate, testable step in front of it, so a stale override degrades with a notice instead of breaking a chat.
- **Derived notices, never stored.** There is no stale-notice state and no migration, and a notice clears when its cause is fixed.
- **Sortie 06's lesson was applied.**
  - The baseline covered the unit tier and every browser lane on the unchanged base, in the worktree venv.
  - The 3 `test_desktop_host.py` environment failures and the squawk 0303 flake were therefore known before leg 1. Every later comparison was mechanical.
- **The re-check at execution start** caught a consumer that was not in the plan: the routine runner reads the restore status and needed the `build_failed` reason.
- **Falsification was recorded per test** in the flight log, so the new tests are known to fail on the regression they pin.
- **The two-reviewer flight review** (Reviewer plus Accessibility Reviewer, in parallel) found the WCAG 3.2.2 regression in the first cleared-field fix. A single code reviewer had confirmed that fix.

## What Could Be Improved

### Process
- **The close-out was lost.**
  - The flight commit's log entry said "Leg 6 (`hat`) follows on a scratch dev instance with the operator". The PR then merged on 2026-10-31 with the sortie still `in-flight`.
  - No HAT ran, no debrief ran, and nothing flagged the open sortie.
  - The next session's Mission 34 artifacts carried "the operator chose to fly sortie 07 first" forward as current. The Mission 34 debrief (2026-11-03) then listed "fly sortie 07 next".
  - **Cost:**
    - a wrong action item in the mission debrief;
    - a HAT leg partly designed before the state was checked;
    - this debrief written three days late, from artifacts rather than fresh memory.
  - The operator calls it "just a miss on my part". See Methodology Observations for the part the methodology could catch.
- **`make gate` stops at a non-zero unit tier.** The baseline's environment failures (no `gi` in the locked worktree venv) meant the closing gate ran as two commands by hand. This is the second sortie in a row (sortie 06 recorded the same).
- **The closing gate's browser reading was not quiet** (start load 1.23), so no lane could be re-budgeted from it. Mission 34 F1 re-measured `agent-tabs` instead (407 s, budget 510 s).
- **Helper-script writes.**
  - Five shell writes into the tree happened against the squawk 0286 rule:
    - a `python3` heredoc rewrote `app.py`;
    - heredoc appends to `tests/test_web_helpers.py` and the flight log;
    - two empty heredocs.
  - All were self-reported and checked by `git diff`.
  - This is fixed since: the project's PreToolUse hook (squawk 0292, PR #352) now blocks them.

### Technical
- **Two interpretations of one rule.**
  - The strict `resolve` and the total `clip_override` sit side by side in an 826-line `resolver.py`.
  - A new marker type must change both, plus the property-test generator. The property tests are the only thing that keeps them aligned.
- **The client mirrors the server's override rules.**
  - The server's `x_marker` map has no single source for "is this field overridable / rendered". The client mirrors it in `allowed()` (`tool-config-fields.js`) and `tools-tab.js`.
  - DD4 had to patch the client in the same leg, or the new marker's field would be flagged dead and dropped on Save.
  - Only browser tests catch drift.
- **`NO_HOSTS = "none.invalid"` is a reserved value inside a user-visible list.** It is handled in several resolver branches and in `_web_config.py::_url_check`. Anything that shows or exports an allow list must special-case it.
- **`api.py` grew about 249 lines, to roughly 6850.** The router split (maintenance finding #6) waited for this sortie and is still open.
- **`_restore_session` gained the `build_failed` branch.** The deferred split (finding #7) now has one more path to preserve.

### Documentation
- `the_one/agents.md` documents the clip table, the save 422 and the notices, but has no "adding a narrowing field" checklist. A new field needs:
  - the marker;
  - a strict-check rule and a clip rule;
  - the client `allowed()` / `x_marker` entry;
  - a property-test generator row;
  - and, for host lists, the `NO_HOSTS` reservation.
- The release notes were drafted in the flight log and stand untested in the shipped app. The HAT would have checked their claims, among them the redirect-to-CDN behaviour change and the one-time cleanup.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Leg 1 split into `override-rules` and `save-and-notices` | The design reviewer found a seam: the save 422, notices and `build_failed` all call leg 1's per-field helpers | Yes: split at a "consumes the previous leg's new API" seam |
| DD6: `dropped`/`effective` paths kept in stored form, not canonical | The operator sees what they typed, and "Use narrowed value" stores what the field shows | Yes; annotated in flight.md at leg 5 |
| DD9 cleared-field behaviour revised twice in the flight review | The design said what the end state is, not when it is reached. Pass 1 refilled on `input` and broke backspace-then-retype ("603", WCAG 3.2.2). Pass 2: an emptying input marks the field inherited and leaves the text, and the value is written back and announced on blur | Yes: UI state specs name the event model (input vs change/blur), the announcement and focus |
| New module `tool-override-state.js`, not named by any leg | `tool-config-fields.js` hit 832 lines against the 800-line `test_area_module_size` rule | Yes: UI leg designs check module size up front |
| DD10's server half (`execution_sandbox`) moved into the UI leg | It is consumed only by the field note | No (case by case) |
| Closing gate run as two commands | `make gate` stops at the baseline's environment failures | No; see Action Items |
| HAT skipped | Operator decision at close (2026-11-03); the HAT was optional | No: an optional HAT should be decided before the merge, not found open afterwards |
| Debrief metrics reused, not run fresh | The project crew file says run fresh when code has moved since the gate. Main has since moved through Mission 34, whose final gate already measures a tree containing this sortie. A fresh run would re-measure Mission 34 | No (a retroactive debrief only) |

## Key Learnings
- **"Strict check on write, total clip on read, property tests between them"** is a reusable pattern for any operator-bounded setting the operator can later tighten. The property tests are what make it safe, not an optional extra.
- **Derived state beats stored state for warnings.** Notices are computed per response from the current override and the current app-wide value, so they cannot go stale.
- **A security setting's empty value needs an explicit meaning on both sides.** "Empty means any" (`host_allowlist`) and "empty means nowhere" (`path_allowlist`) differ, and the old subset check treated `[]` as narrower than anything. That hole was live.
- **UI field-state specs need transitions, not end states.** The project's HAT guidance already asks for state-transition sequences. Leg specs for interactive fields need the same: inherited → own → cleared → inherited, with the triggering event for each.
- **Test metrics, with sources:**

| Run | Unit | Browser | Source |
|---|---|---|---|
| Sortie 07 baseline (2026-10-31, worktree venv, base `628a97dd`, start load 0.18) | 3 failed (env: `test_desktop_host.py` ×3, no `gi`) / 8374 passed / 23 skipped, 394 s | `PARALLEL_RESULT rc=1 total=1810s lanes=17 failed=agents` (squawk 0303 flake) | flight log |
| Sortie 07 closing gate (branch tip, start load 1.23) | 3 failed (same three) / 8556 passed / 23 skipped, 390 s | `PARALLEL_RESULT rc=1 total=1833s lanes=17 failed=agents,agent-routines` (flakes 0303 and 0304; 0304 also fails on base); `agent-tabs` 349 s (budget 390 s), up from 293 s | flight log |
| Sortie 06 debrief (2026-10-27, start load 1.44) | 9 failed (fresh-venv set) / 7765 passed / 23 skipped, 340 s | `PARALLEL_RESULT rc=1 total=1648s lanes=13 failed=knowledge` | `sorties/06-safe-names/flight-debrief.md` |
| Main after merge (Mission 34, which contains this sortie's code) | 8738 tests, 219.16 s at #352's final gate (start load 0.48) | 1774 s, 17 lanes, all within budget (quiet reading) | `missions/34-maintenance/mission-debrief.md` |

  - **Sortie 07's added cost.** It added 182 unit tests at no visible unit wall cost (394 s → 390 s). In the browser it added about 23 s overall and 56 s to `agent-tabs`.
  - **Since then.** Mission 34 halved the unit tier and fixed flakes 0303 and 0304. Against sortie 06, the unit count grew about 790 tests across two sorties and a mission, and the browser suite gained four lanes.

## Methodology Observations
Plugin: mission-control 1.2.3.

1. **A merged sortie was left `in-flight`, and nothing noticed.**
   - **Skill and phase:** agentic-workflow Phase 3, Flight Completion; also sortie/flight-debrief entry.
   - **What happened:**
     - The flight commit was made with legs 1-5 completed and the optional HAT still to come.
     - The operator merged the PR before the HAT. Agentic-workflow's PR lifecycle has no state for "code merged, HAT pending".
     - Nothing moved the sortie to `landed`, and no later skill checked for it. Neither the next session's mission debrief nor its context loading looked at sortie status.
   - **Expected:** either the HAT is decided before the merge (run, or skipped explicitly), or a merged PR whose flight artifact is not `landed`/`completed` is flagged somewhere. Mission debrief context loading, routine maintenance and the daily briefing would each have caught it.
   - **Cost:**
     - a wrong action item in the Mission 34 debrief ("fly sortie 07 next");
     - a HAT leg partly designed before the state was checked;
     - a debrief three days late.
   - **Recurrence:** first occurrence in this project's sorties. Sorties 01-06 all have debriefs.
2. **A prose claim in a planning artifact was read as current state.**
   - **Skill and phase:** mission-debrief Phase 1, Context Loading (Mission 34).
   - **What happened:** Mission 34's `mission.md` said "the operator chose to fly sortie 07 first". The debrief carried that forward as a plan without checking the sortie's status or its PR.
   - **Same pattern as:** Mission 34 debrief methodology observation 1, unverified prose claims in specs, there in two of three flights.
   - **Cost:** the wrong action item above.
   - **Recurrence:** recorded here so a sweep counts it once with observation 1 above. It is the mechanism, not a second event.
3. **The sortie soft limit is exceeded again, with no observable cost.**
   - **Skill and phase:** sortie planning, leg breakdown.
   - **What happened:** the sortie skill's soft limit is 2 legs plus HAT. Sortie 06 flew 4. Sortie 07 planned 4 and flew 5, each split for risk rather than effort.
   - **Cost:** none observed; the splits were sound.
   - **Disposition:** a **local lesson**, recorded so a sweep can see whether the limit fits sorties of this kind (2 of the last 2 sorties).
4. **Leg design states UI field behaviour as end states.**
   - **Skill and phase:** agentic-workflow Phase 2a, leg design, and the project crew's Review Leg Design prompt.
   - **What happened:** DD9 and leg 4's acceptance criteria said what a cleared field becomes, not on which event or with what announcement.
   - **Cost:** two extra flight-review cycles (fix pass 1, then a Medium WCAG 3.2.2 finding and fix pass 2).
   - **Disposition:** a **local fix candidate** for `.flightops/agent-crews/leg-execution.md` (see Action Items). It reproduces only for interactive-field legs, so it is recorded as a local lesson, not a methodology observation.

## Recommendations
1. **Run a short field check of the skipped HAT's riskiest claims** before or with the next release. Author a behavior-test spec at the next planning conversation covering:
   - the Windows `\\wsl.localhost` save that started the sortie, now refused on the field;
   - a real redirect to a host outside an agent's Allowed hosts;
   - the one-time cleanup on a copy of a real legacy database;
   - the live sandbox wording on Linux and the passthrough wording on Windows.
2. **Open maintenance findings #3, #4 (agent half), #6 and #7 against the new seams.** Use `clip_override`, `override_validation.py` and `tool-override-state.js`, and do not re-inline the logic. The router split (#6) matters more now that `api.py` is about 6850 lines. The `_restore_session` split (#7) must preserve the `build_failed` branch and its routine-runner consumer. Routine maintenance is the next step either way.
3. **Remove the client mirror of the override rules.** Serve an overridability descriptor from the API, or at least add a parity test that generates cases from the Python marker rules and checks the client's `allowed()` against them.
4. **Revisit fencing Shell and Python with the agent's paths in the Linux sandbox** (DD10's deferred item). The field note tells the operator to turn Shell off to keep an agent to its paths, and on Windows nothing limits Shell or Python at all. This is the largest remaining gap between what the tab implies and what it enforces.
5. **Decide an optional HAT before the merge.** When a flight commit leaves an optional HAT pending, either run it or record "skipped" before the PR merges, so the sortie lands in the same step.

## Action Items
- [ ] Behavior-test spec for the field check in Recommendation 1 (next planning conversation).
- [ ] Settings tile re-enable can add notices with no impact warning (the DD8 gap). **Squawk 0322.**
- [ ] Three browser tests the flight review verified by code read only: a plain text field, paste, and a 422 shown on a field that is then emptied. **Squawk 0323.**
- [ ] `the_one/agents.md`: an "adding a narrowing field" checklist (marker, strict rule, clip rule, client mirror, property-test row, `NO_HOSTS` reservation). **Squawk 0324.**
- [ ] `.flightops/agent-crews/leg-execution.md` Review Leg Design prompt: for an interactive field, check that the leg names the triggering event, the announcement and the focus for each state change (local fix; operator's call).
- [ ] `make gate` with known environment failures in the baseline (second sortie in a row): run the browser half anyway when the unit failures match a recorded baseline list, or document the two-command form in CLAUDE.md. Needs a design call, so this is not a squawk.
- [ ] Optional cleanup: the merged worktree at `.claude/worktrees/sortie-tool-overrides` (operator's call).
