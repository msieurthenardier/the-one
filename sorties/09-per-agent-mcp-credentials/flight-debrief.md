# Flight Debrief: Per-agent MCP credentials

**Date**: 2026-11-04
**Flight**: [Per-agent MCP credentials](flight.md) (sortie 09)
**Status**: completed
**Duration**: 2026-11-03 (charter) - 2026-11-04 (landing)
**Legs Completed**: 7 of 7 (legs 1-3 as planned, the HAT leg, and legs 5-6 added at the HAT)
**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved
One Library MCP server can now be shared by many agents, each connecting with its own header values (HTTP) or environment variables (stdio) and each seeing the tools that key allows.
- **The tile:** the agent Tools tab tile shows the server's headers in the Library's own table, locked by default. **Override headers** unlocks Key / Value / Sensitive / trash, and the tile's **Save** writes the agent's values immediately through a targeted route (`PUT /api/agents/{name}/mcp-overrides/{source_id}/credentials`).
- **Taking effect:** credentials are validated on save, blank values are never sent, and a saved change reaches the next tool call even in an open chat (resolve-at-connect plus eviction).
- **Each agent's own tools:** each credentialed agent lists its tools with its own key (a per-agent cache, schema v50, and `POST /api/mcp-sources/{id}/test/agent`).
- **Sign-in servers:** a per-agent Authorization is refused on a server with OAuth sign-in.

The branch also carries the v0.14.0 version bump and release notes (`0e96ea17`), at the operator's request, so a release can be cut after the merge.

### Charter Criteria Assessment
| Criterion | Result | Note |
|---|---|---|
| 1. The Tools tab tile lets an agent set its own value for any server header or env var, or add new ones; values are write-only; a blank Library value is labelled and never sent | **Met, with operator-approved changes** | Two changes, both recorded in the flight log: write-only was narrowed to *sensitive* values (DD12, a per-row Sensitive switch); and the Library's "Set per agent" label became the placeholder `value` with the hint "Optionally override headers in agent settings." (H1). A blank value is still never sent. Verified at HAT H1-H2 and H7, and in behavior steps 2-7. |
| 2. After Save, the next chat turn uses the new values, with no restart or idle wait; two agents reach the server with different keys | **Met** | Key-server log, HAT H4: the open chat's `tools/call` went from `-7Q2` to `-3K8` with no reload. Behavior run 2 steps 10-13 showed the same, with the idle TTL pinned at 3600 s, and beta used `-9Z4`. |
| 3. Each agent's tools come from a listing with its own credentials; switching on tests immediately and shows tools or a plain reason; a key-less Library server still lists tools for an agent with a key | **Met** | HAT H2-H3; behavior steps 4-9 (`needs_values` without connecting; alpha `[echo]`, beta `[echo, add]`). |
| 4. On an OAuth sign-in server, a per-agent Authorization is refused with a plain reason; other headers can still be overridden | **Met** | HAT H6, including a live API 422 with the plain sentence. The tile shows no Authorization row, only a note. Unit tests on the validator. |

All four criteria are met, so the sortie delivered its charter.

## What Went Well
- **Two Architect reviews before any code caught the server traps on paper.**
  - DD1's merge (a dropped name or a `null` would break builds).
  - `auth_posture` isn't evidence of OAuth.
  - The Library Test writes the shared cache.
  - Resolving at connect rather than evicting alone.
  
  Legs 1-2 landed with no divert, and the server contract survived the full UI redesign.
- **Per-leg review and commit** (a deviation from one review per flight) caught real defects in every leg: anchored regexes, a too-broad orphan exemption, the Phase A extraction details. It also gave checkpoints to fall back to.
- **The key-checking fixture** (`tests/fixtures/mcp/key_server.py`, with a `{seq, method, key_tail}` log) made credential flow observable to unit tests, the behavior test and the HAT. Every behavior verdict on "which key reached the server" rests on it.
- **The rendered mockup for DD12.** Three review rounds in the app's real stylesheet and factories took minutes. The built tile matched the screenshots, and H2 passed first time on the rebuilt tile.
- **Falsification discipline.** Almost every new test was shown to fail without its fix. The one test that couldn't prove its claim (the MCP-over-tool focus ordering) was flagged honestly and handed to the HAT.
- **Accessibility review earned its place.** It found a WCAG 2.5.3 Label-in-Name blocker in leg 3, and focus-after-failure and pill-overlap issues in leg 6.

## What Could Be Improved

### Process
- **An ASCII mockup approved a surface the operator then rejected** (Critical). DD10's ASCII sketch fixed the structure but couldn't show font, field widths, or that the section should look and act like the Library headers table, with its own Save/Test/Cancel. The gap surfaced only at the HAT and cost about two and a half legs: leg 5's options, the leg 6 rewrite, about 1,170 lines of tests, 12 retired testids, and spec churn in five steps. The operator flagged it in the debrief, and it echoes squawk 0293's rule. Nobody asked "which existing surface should this resemble?".
- **The HAT restart didn't take effect.** The recorded `$!` wasn't the server's PID. The new instance hit `Errno 98` and exited, and `/api/live` kept answering from the old process. The H5, H6, leave-guard and H8 re-checks ran on server code from `1bce9b4b`, so H5's server half was never operator-witnessed. The operator accepted the browser test for it. Verify the port owner (`ss -ltnp`) after every restart.
- **HAT bugs that earlier tests should have caught** (operator: the second-largest slowdown):
  - name-vs-value 422 placement (the `loc` couldn't say which part was refused);
  - the leave guard's no-op `discard`, which assumed teardown on navigation, but the agent editor stays mounted.
  
  Both came from assumptions the leg specs stated without checking (`App.nav`'s discard contract, the 422 shape's expressiveness).
- **The behavior spec drifted after HAT fixes.** Spec step 5 (pill timing) was authored before H6 changed the behaviour, and run 2 failed on it. A spec step must be re-read after every HAT fix that touches its surface.
- **Scope grew from 3 legs plus HAT to 6 plus HAT** through a gate-promoted HAT feature. The operator judged the sortie the right vehicle: the growth came from the design miss, not a second decision cluster. The Architect agreed that the decision cluster held, but noted that DD12 brought a real decision set: per-row sensitivity, a new write route, a shared-control API change.

### Technical
- **`api.py` grew to 7,244 lines (+349 net).** The agent-MCP-override cluster (the merge with `plain_names` prune, response masking, eviction hooks, the targeted route, the validation gate) is about 400 coherent lines that belong in their own module. `_merge_preserved_mcp_credentials` now carries credential, tool-filter and `plain_names` rules: the highest-risk function in the sortie. This reinforces the sortie 08 recommendation (one declared table of agent field write semantics).
- **A narrow race between the targeted credentials route and a whole-agent PUT.** Both do load, merge, then save of the whole row with awaits in between, so whichever saves last silently drops the other's changes, in either direction. It was accepted at leg 5 (single-user local app), but a per-agent `asyncio.Lock` around both write paths is cheap and closes it.
- **Module sizes near the 800-line guard:** `mcp-agent-credentials.js` 735, `agent-editor-controller.js` 783, `mcps-tab.js` 659.
- **`lockBy` became a token list** (`key|row|toggle`) to fit one case, the server Authorization row. It's a mini-DSL; watch for creep.
- **`plain_names` is a parallel name list** (headers case-insensitive, env exact, plus a prune). A per-name `{value, sensitive}` shape would have been simpler. Not worth reopening, but don't extend the pattern.
- **Dead text:** `mcp-error.js:21`'s `fetchMcpSourceTools: HTTP` alternative is now dead. Tile errors still match its `Server error` alternative, so behaviour is unaffected.
- **The `block_shell_writes.py` hook (squawk 0292)** let one `sed -i` through on `the_one/interfaces/web/static/js/areas/studio/mcp-agent-credentials.js`, while blocking a second one on `the_one/agents.md`.

### Documentation
- `the_one/agents.md` has the sortie 09 block (server and Tools-tab halves), and `SECURITY-MODEL.md` has the "Per-agent MCP credentials" paragraph, including the clear-text non-sensitive values and the `_looks_masked` limitation.
- **Worth adding:** a line in the leave-guard section of `agents.md` saying a `discard` must act on a still-mounted editor; and the `part: name|value` 422 field as a convention for any detail whose `loc` ends at a map key.
- `flight.md` keeps DD10 and parts of DD12 as superseded-in-place text. It's acceptable, but it reads as layered; the flight log is the authoritative sequence.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Per-leg review and commit instead of one review at flight end | The operator was told "each leg ends with a commit"; legs 1-2 both touched the Library Test path | Yes, for multi-leg flights with risky shared-path legs |
| DD6's route logic in `interfaces/web/mcp_agent_test.py`, not `mcp/` | `mcp/` must not import from `interfaces/` | Yes (layering rule) |
| The factory builds MCP tools before the search index (leg 2) | The index must see Path A's per-agent cache write | No (one-off ordering fix) |
| Leg 3 split into part A/B with a checkpoint commit; leg 6 the same | Over about 15 ACs | Yes (already the project rule) |
| DD12 redesign promoted through the fix-vs-feature gate and built as legs 5-6 after a rendered mockup | The operator rejected the ASCII-approved tile at the HAT | Yes: a rendered mockup before implementing a reshaped surface |
| Main Save stops carrying credentials; a targeted per-source route | Operator: the tile's Save saves right away, like the Library editor | Yes (partial-update routes need a concurrency answer) |
| Behavior-test read-only and HTTP-only checkpoints batched into one Executor turn | Cost; no state change between them | Yes, for read-only and independent checkpoints |
| The H5 server half accepted from the browser test, not re-witnessed | The HAT restart miss | No (an apparatus failure) |

## Key Learnings
- **Ask which existing surface a new UI should look and act like before drawing it.** The Library headers table and the MCP editor's Save/Test/Cancel trio were the obvious models. The operator's mental model (a per-server Save inside the tile) followed from them.
- **A rendered mockup in the app's real CSS and factories is cheap** (a scratch page served on a spare port, loading the instance's static files through the session cookie) and catches what ASCII can't.
- **For a 422 whose `loc` ends at a map key, say which part was refused** (`part: name|value`). Otherwise the client can't place the message.
- **In this app, an `App.nav` source's `discard` runs on a still-mounted editor.** Never assume teardown.
- **HAT apparatus:** record the real server PID and verify it owns the port after every restart. `/api/live` answering proves nothing about *which* process answers.
- **Re-read behavior-spec steps after each HAT fix that changes their surface,** before re-running the spec.
- **Test metrics** (sources named):
  - **Unit tier:** 8963 passed, 15 skipped in 242 s (debrief run, start load 0.44). One failure was a mid-run race with the version-bump commit; `tests/test_packaging_metadata.py` passes at HEAD, 49 passed.
  - **Comparison:** sortie 08 had 8777 tests in 226 s, and M34 F1 had 8577 in 229 s. That's +186 tests for +16 s, in line with the average.
  - **Browser gate (leg 6 part B):** `PARALLEL_RESULT rc=0 total=1855s lanes=17`, flat against sortie 08's 1858 s. The leg 3 gate was `rc=1 total=1931s` (a test-assertion bug and an unrelated `routing` flake, both cleared on lane re-runs).
  - **`agent-tabs`** is now 425-439 s against its 510 s budget (about 83%). The next sortie adding tests there will push it over.
  - **Flakes:** `test_flow_agents_focus_after.py::test_form_is_clean_and_shows_the_stored_model_while_loading` (known, sortie 08) once, and `test_store_library.py::test_invalidate_mid_flight_then_get_issues_a_second_request[knowledge-bases]` once; both passed isolated.

## Methodology Observations
Recorded against mission-control **1.2.3**. Not judged.

1. **flight skill, Phase 5b / flight-design crew rule 6 (squawk 0293): ASCII mockup accepted as the approved mockup.**
   - *What happened:* the crew rule requires "an operator-approved mockup (or two layout options)" before legs lock. An ASCII sketch satisfied it.
   - *Expected:* the rule should require a mockup rendered in the product's real styles and controls for a reshaped UI surface, and the design step should ask which existing surface it should resemble.
   - *Cost:* the HAT rejected the surface. About two and a half legs of redesign and rework (legs 5-6, a test rewrite, 12 retired testids, spec churn), plus a security-relevant charter relaxation made under HAT pressure.
2. **sortie skill, "Re-check the gate" / agentic-workflow HAT fix-vs-feature gate: no path for a gate-promoted feature that adds legs to a sortie.**
   - *What happened:* the sortie skill checks the leg budget only before `ready`, and its escalate verb says an in-flight sortie must not move. The HAT gate promoted a feature (DD12) that needed two more legs.
   - *Expected:* guidance on whether a HAT-promoted feature may add legs to an in-flight sortie, how far, and how the operator decides.
   - *Cost:* the Flight Director improvised: it asked the operator whether to add legs or file sortie 10, and the operator chose to add legs. Sortie scope reached 6 legs plus HAT against a 2-leg soft limit. It worked, but nothing in the skills covered it.
3. **agentic-workflow, Phase 2d: one review and commit per flight is the default.**
   - *What happened:* the default is a single review and commit after the last autonomous leg. This flight reviewed and committed per leg, and recorded that as a deviation.
   - *Expected:* for multi-leg flights whose legs share risky surfaces, per-leg review is safer. Every per-leg review found real defects.
   - *Cost:* none (positive). Recorded because the default would have batched about 9.7k changed lines into one review.
4. **agentic-workflow, HAT legs: no guidance on HAT apparatus hygiene.**
   - *What happened:* the Flight Director restarted the scratch instance mid-HAT. The restart silently failed (wrong PID recorded), and the operator re-verified fixes on stale server code.
   - *Expected:* a HAT-apparatus checklist covering a recorded real PID, port ownership verified after each restart, and a link re-minted after any restart.
   - *Cost:* one fix (H5's server half) was never operator-witnessed.
5. **behavior-test skill, Phase 4 / crew prompts: agents report that a hand-back ends their run.**
   - *What happened:* in live mode the Executor and Validator use SubagentHandback for each step and repeatedly added "this report ends my turn, please resume me". The resume by message worked every time.
   - *Expected:* the crew prompt's "YOU ARE RESUMED BY SENDMESSAGE" note should tell agents that a hand-back is the normal per-step channel.
   - *Cost:* noise only.
6. **behavior-test skill, Phase 4: no guidance on batching read-only checkpoints.**
   - *What happened:* the Orchestrator batched read-only and HTTP-only checkpoints (2-3, 8-9) into one Executor turn with separate reports and verdicts.
   - *Expected:* the skill could state when batching is safe: no state change between the checkpoints, per-step report files, per-step verdicts.
   - *Cost:* none; it saved two round trips.
7. **behavior-test spec lifecycle: a spec re-authored in a leg went stale after later HAT fixes.**
   - *What happened:* leg 6 re-authored the spec, then HAT H6 changed the pill timing, and run 2 failed step 5 on a spec error.
   - *Expected:* the agentic-workflow HAT protocol should prompt a re-read of any behavior spec that pins a surface a HAT fix changes.
   - *Cost:* one FAIL verdict and an operator interruption mid-run.

## Recommendations
1. **Require a rendered mockup for any new or reshaped UI surface** (in the product's real CSS and control factories), and ask "which existing surface should this look and act like?" at flight design. Make it a hard gate in the project's flight-design crew file (squawk 0293's rule). Also raise it upstream through the next `/mission-control:service-report`.
2. **Extract the agent-MCP-override cluster out of `api.py`** into its own module, and adopt the sortie 08 "declared field write-semantics table" before the next feature touches agent writes. `plain_names` is its first non-trivial row.
3. **Close the targeted-route versus agent-PUT race** with a per-agent `asyncio.Lock` around load, merge and save in both write paths, plus an interleaving test.
4. **HAT apparatus checklist** in the project's leg-execution crew file: record the real server PID, verify the port owner after every restart, re-mint links, and re-read affected behavior-spec steps after each HAT fix.
5. **Budget and split before growth:** split `mcp-agent-credentials.js` (735 lines) before its next change, and plan an `agent-tabs` lane split or re-budget at the next maintenance pass (83% of budget).

## Action Items
- [x] Squawk 0327 (deferred): the race between the targeted credentials route and a whole-agent PUT.
- [x] Squawk 0328 (deferred): `block_shell_writes.py` let a `sed -i` through on a protected JS file.
- [x] Squawk 0329 (deferred): the dead `fetchMcpSourceTools: HTTP` alternative in `mcp-error.js:21`.
- [ ] Watch: the `test_store_library.py` `[knowledge-bases]` flake. File a squawk if it recurs.
- [ ] Next maintenance: the `api.py` agent-override extraction, the `mcp-agent-credentials.js` split, and the `agent-tabs` lane budget.
- [ ] Project crew files: the rendered-mockup gate (flight-design) and the HAT apparatus checklist (leg-execution).
- [ ] After the merge: tag `v0.14.0` on `main` to run the release workflow.
