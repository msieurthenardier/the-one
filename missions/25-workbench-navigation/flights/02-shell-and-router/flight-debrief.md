# Flight Debrief: Shell and Router

**Date**: 2026-10-01
**Flight**: [Shell and Router](flight.md)
**Status**: landed
**Duration**: 2026-10-01 to 2026-10-01 (planned and flown in one autonomous session)
**Legs Completed**: 8 of 8. The plan had 7; leg 3 was split at its design review.
**Plugin version**: mission-control 1.2.0

The operator was not interviewed for this debrief; the run was autonomous. Its inputs were:
- the flight log;
- a Developer debrief interview with a full test-metrics run;
- an Architect design review of the outcome;
- the four behavior-test run logs.

## Outcome Assessment

### Objectives Achieved

The objective was met: replace the three-area top bar with the workbench shell without
changing what any page shows.

- **Rail.** A 72px workbench rail (`App.ui.rail`) replaces the top bar. It has four
  destinations: Chats, Agents, Library and Settings. The aside collapses on Agents, and
  the shell is usable at 1024px.
- **Router** (`static/js/router.js`).
  - **URLs.** Hashes are destination-first, with a reserved `~new` create segment that no
    agent name can collide with (`%7E`). Legacy `#chat`, `#studio` and `#admin` URLs
    redirect.
  - **History.** Item opens push history, and Back steps between items.
  - **Rail restore.** The rail returns to each destination's last-open item.
  - **Two URL primitives.** `go()` is a guarded intent; `sync()` is canonicalisation
    only.
  - **Squawk 0082** is closed by construction.
- **Leave guard** (`App.nav`).
  - **Coverage.** One guard covers every path the page controls: the rail, section nav,
    in-app links, Back/Forward, typed URLs, reload and close.
  - **Mechanism.** Per-area dirty sources, a teardown-only discard with an `editorGen`
    guard against resurrection, and a synchronous clean fast path.
  - **Dialog.** Its confirm dialog sits on native `<dialog>` (`App.ui.modal`).
- **`App.store`** caches agents and providers. Cold-boot Agents requests dropped from 2+2
  to 1+1.
- **Test apparatus.**
  - Every browser test navigates through `_nav.py`, policed by an AST guard.
  - The lanes are re-mapped to destinations, with aliases.
  - `THE_ONE_TEST_NETNS=1` isolates WSL2 network-change noise.
- **Accessibility.** A route announcer and `document.title` were added in the
  flight-review fix round.
- **Behavior tests.** All four pass on the new shell:

  | Spec | Checkpoints |
  |---|---|
  | `workbench-navigation` | 28/28 |
  | `shell-navigation-smoke` | 8/8 |
  | `studio-agent-crud` | 18/18 |
  | `system-provider-config` | 18/18 |

### Mission Criteria Advanced

- **SC1 (workbench navigation).** Delivered and behavior-backed by `workbench-navigation`
  and `shell-navigation-smoke`.
- **SC2 (leave-guard half).** Delivered. The list/detail half is Flight 3's.
- **SC6 (control library, continued).** `App.ui.modal` and `App.ui.rail`, each with a demo,
  an inventory row and contract tests in both engines.
- **SC10 (operable and regression-safe).** Delivered:
  - the navigation helper and AST guard;
  - landmarks and the skip link preserved;
  - a keyboard-operable rail;
  - the route announcer;
  - suites and guards green;
  - specs migrated and passing.

## What Went Well

- **Design review on the flight paid for itself.**
  - Two Architect cycles found 21 issues before any code.
  - Three of them were real field-bug classes: the `prevSection` ordering bug, the stale
    `doSelect`, and `sync` firing during a pending guard decision.
  - Splitting leg 3 at its design review (router-core vs item-history) let leg 3 land in
    one pass with all lanes green.
- **Tests first.**
  - Leg 1 migrated about 45 test files onto `_nav.py`.
  - It also fixed the four recurring lane flakes (response-ordering races) before the
    shell changed.
  - After that, no later leg broke tests through markup churn.
- **Exact-count acceptance criteria found real bugs.**
  - Leg 4's AC6 counts WebSocket frames. That exposed a latent chat bug: a `session_list`
    arriving between `new_session` and `session_joined` re-sent `new_session`.
  - Leg 7's request-count table proved the store removed duplicate fetches.
- **Environment root-caused, not papered over.**
  - The library-lane "flakes" traced to WSL2 mirrored networking. Windows' rotating
    IPv6 addresses trigger Chromium's NetworkChangeNotifier, which aborts loopback
    requests.
  - The fix, `THE_ONE_TEST_NETNS=1`, is opt-in and fails loudly.
  - The debrief's sequential run had zero failures and zero flakes.
- **Witnessed behavior tests caught test-design defects as well as product ones.** For
  example, the smoke spec's step 9 was not a fresh-document load. The Validators'
  spec-quality notes were folded back into the specs.
- **The apparatus fallback held.** When goldfinch input died mid-run, a CDP-driven headless
  Chromium with real input events and real screenshots took over. Its evidence was
  stronger than goldfinch's PDF and AX path.

## What Could Be Improved

### Process

- **Important — leg count and sizing.**
  - Eight legs is past the soft limit. The Architect judged it justified, because legs
    3–7 each owned a distinct contract.
  - But Leg 4 landed with two open items and needed a follow-up Developer. Leg 5 needed
    two follow-ups for the environment.
  - Legs that ship a new routing or guard contract should budget a follow-up slot.
- **Important — no environment prerequisite for WSL2 network noise.** `ERR_NETWORK_CHANGED`
  cost legs 3–5 two follow-up rounds. The next flight's Prerequisites should carry
  `THE_ONE_TEST_NETNS=1` as a standing item. Flight 3 does.
- **Important — the behavior-test apparatus failed in the middle of a run.**
  - goldfinch stopped delivering synthetic input. The tools returned ok while zero events
    reached the page.
  - Its window topology tools are admin-only, so it could not be diagnosed from the
    session.
  - The run continued on a CDP Chromium, recorded as a deviation.
  - Specs should declare an apparatus fallback list up front; Flight 3's DD12 does.
- **Minor — concurrent behavior runs shared one scratchpad.**
  - Generic script names (`s1.py`…) collided across three Executors, and two of them
    each ran another run's script once.
  - Each affected checkpoint was redone and disclosed.
  - Per-Executor scratch subdirectories prevent this.
- **Minor — an Executor ran an unrequested state-changing probe.** A full-document load
  at `workbench-navigation` D10 forced a re-run of D13. Executor prompts should forbid
  unrequested navigation or history-altering actions.

### Technical

- **Alias-layer debt** (Architect).
  - `studio.js` (3,183 lines) carries both Agents and Library state in one closure.
  - Router state is spread across `hydrateState`, `doSelect`, `selectSeq`, `editorGen` and
    `editorDomStale`, and each area re-implements the stale-then guards.
  - Flight 3 extends it deliberately (its DD3) with leak and race regressions. The split
    is deferred to the next mission.
- **The announcer and `sync` were designed apart.**
  - `sync()` re-titles but never announces. After a provider or MCP save-create, the
    route announcer keeps reading "… — New" until the next navigation.
  - Agent save-create announces, because it uses `go(replace)`.
  - Flight 3 DD8 fixes this: `sync` will announce a create→item transition.
- **`App.store` was scoped to two collections.** Tools, MCP sources, KBs and model caps
  are still fetched twice on the first Studio activation. Flight 3 DD9 adds the Library
  collections.
- **The shared lane is the long pole.**
  - It grew from 437 to 723 tests and takes about 10 minutes.
  - Its growth is the dual-engine `test_ui_*` contracts plus `test_router_*`,
    `test_nav_guard`, `test_store` and `test_shell_rail`.
  - Candidate fix: a `contracts` lane split out of `shared`.
- **Remaining small debt:**
  - the test-only `_dirty` setters on production areas;
  - the flat `index.html` script list, with a manual cache-busting count bump (68 → 72);
  - the 10s chat stalled-join timer can orphan one empty session after a slow join
    (squawk 0111);
  - squawk 0110 (the unnamed chat image input).
- **Pre-existing UI issues surfaced by the behavior runs:**
  - the unstyled Connectors empty-state CTA;
  - long provider names running under the tile badge;
  - section-nav items that are `<button>`s rather than links.
  
  Flight 3's list rebuild absorbs all three.

### Documentation

- `agents.md` should document these patterns:
  - the router's synchronous guard fast path ("never promisify");
  - `editorGen`, `editorDomStale` and the `fresh` hydrate origin;
  - a short decision guide for `go`, `sync` or bypass when adding a route.
- The UI test apparatus notes should record two items:
  - `page.evaluate("window.__p = promise")` hangs;
  - the delete arm is asynchronous: provider Delete arms only after an agent-usage
    pre-fetch, about 57–130ms later, so probes must poll for "Confirm Delete?".

## Test Metrics

The Developer's debrief run, 2026-10-01: sequential, lanes under `THE_ONE_TEST_NETNS=1`.

| Suite | F1 debrief | F2 debrief | Delta |
|---|---|---|---|
| Unit (`make test-unit`) | 4,929 passed, 10 skipped, 666.9s | 5,001 passed, 10 skipped, 680s | +72 tests, +13s (+2%) |
| chats (was chat) | 41, 99s | 42 passed, 101s | +1, +2s |
| agents + library (was studio) | 188 passed, 3 skipped, 500s | agents 97 passed, 2 skipped, 225s · library 95 passed, 1 skipped, 346s (192 / 3 / 571s) | +4, +71s (+14%) |
| settings (was system) | 124, 228s | 125 passed, 240s | +1, +12s |
| shared (now holds the `test_ui_*` contracts) | 437 + 257 contracts = 694 passed, 4 skipped, 256s | 723 passed, 1 skipped, 627s | +29, +371s (+145%) |

- **Failures and flakes.** There were no failures and no flakes. Skips went from 4 to 1:
  leg 6 retired the three dead picker skips, and the remaining skip is WebKit forced
  colours.
- **Shared.** This lane is the real cost of the flight. The new router, guard, store, rail
  and modal tests run in both engines and fall into the complement lane. It is now about
  10 minutes, the long pole, and the first candidate to split.
- **Library.** This is the slowest lane per test: about 3.6s per test, against 2.3s for
  agents. The likely cause is the `_nav.goto_settled` quiet-window waits, 400ms and
  1,500ms, across about 277 migrated navigations, plus MCP and KB editor mounts that wait
  on list fetches.
- **Totals.** The whole sequential browser run is about 26 minutes, plus about 11 minutes
  for unit.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Leg 3 split into `router-core` and `item-history-and-exact-rendering` at design review | The original leg bundled four contracts | Yes. Split any leg that introduces more than one contract. |
| `THE_ONE_TEST_NETNS=1` added mid-flight | WSL2 `ERR_NETWORK_CHANGED` aborted loopback requests | Yes. A standing prerequisite for browser lanes on WSL2. |
| Leg 4 landed with open items, followed by a follow-up Developer | A latent chat bug found by the frame-count AC; file-level flakiness | Partly. Budget a follow-up slot for contract-heavy legs. |
| Route announcer added in the flight-review fix round | Accessibility review found silent route changes | Yes. Design announcements together with any new routing primitive. |
| Behavior runs moved from goldfinch to a CDP-driven Chromium | goldfinch stopped delivering input | Yes. An apparatus fallback list in every spec. |
| `system-provider-config` run on a CDP Chromium, not chrome-devtools | That MCP is not registered in this session | Yes. Specs accept any CDP-driven Chromium. |
| The `workbench-navigation` Light variant and the Dark passes of both CRUD specs batched | Orchestration cost of repeating a variant | Yes, for variant repeats with file-based evidence. |

## Key Learnings

- **Acceptance criteria that count things** (frames, requests, dialogs, history entries)
  catch real bugs that pass visual checks. Keep writing them, with state-driven waits
  specified up front.
- **The fastest fix for "flaky" lanes was root-causing the host.** Of the three flake
  classes, two were app response-ordering races, fixed with `_nav.goto_settled`. The
  third was the WSL2 network notifier, fixed with netns.
- **A behavior-test Validator is as good at catching bad tests as bad code.**
  - Smoke step 9 claimed a cold load but did a same-document hash change.
  - The workbench D13 failure came from the apparatus, not the app.
  - Both were caught because the Validator demands evidence.
- **Headless CDP Chromium is a better behavior-test apparatus than goldfinch on this host.**
  It gives real screenshots, real input, and per-run isolation. Keep it as the documented
  fallback, and consider making it the default for leg-level checks (Flight 3 does).

## Methodology Observations

These are recorded, not judged. Plugin `mission-control` 1.2.0.

1. **behavior-test skill, Phases 2–4 (live mode).**
   - **What happened.** The skill runs an Executor and a Validator as persistent agents
     via SendMessage. In practice each agent ended every turn with a final hand-back and
     often wrote "this handback ends my run; spawn a fresh Executor". Resuming them with
     SendMessage worked every time.
   - **Expected.** Agents that understand they will be resumed.
   - **Cost.** No rework, but about 15 needless "I can't continue" notes, plus one
     Executor stating it could not receive `[CLOSING]`.
   - The crew prompt could say "you will be resumed by SendMessage after each step".
2. **behavior-test skill, Phase 2 (apparatus).**
   - **What happened.** The skill's apparatus discovery assumes MCP browser tools.
     goldfinch passed discovery, then silently stopped delivering input mid-run. The
     skill has no guidance for an apparatus that degrades mid-run.
   - **Cost.**
     - one Light-variant Executor spawned and aborted;
     - Flight Director diagnosis time;
     - an improvised CDP apparatus, with Playwright's `new_context` disposed on
       disconnect, so raw `Target.createBrowserContext` was needed.
   - **Expected.** A sanctioned fallback path, and a "probe input delivery" step at the
     start, for example a click with a capture-phase listener.
3. **behavior-test skill (concurrency).**
   - **What happened.** Nothing in the skill covers running several specs concurrently.
     The Flight Director ran three in parallel on separate browsers. They shared one
     scratchpad, and generic script names collided, so two Executors each executed
     another run's script once.
   - **Cost.** Two checkpoint redos and disclosure overhead.
   - **Expected.** Per-run scratch subdirectories as a stated rule, if concurrency is
     sanctioned.
4. **behavior-test skill, Phase 4 (checkpoint loop with variants).**
   - **What happened.** The loop has no notion of spec variants (themes). Specs that run
     "the full table per theme" doubled the checkpoints: 28, 18 and 18. The Flight Director
     invented `D`/`L` evidence prefixes and, for the variant repeats, batched execution
     with separate per-checkpoint judging.
   - **Cost.** About 100 orchestration messages for the four specs.
   - **Expected.** Guidance for variants, or a batch mode for repeats with file-based
     evidence.
5. **Executor crew prompt.**
   - **What happened.** "Perform the Actions" did not stop an Executor from adding a
     "supplementary" full-document probe that altered history.
   - **Cost.** A re-run of one checkpoint and a wrong interim Flight Director hypothesis
     (a spec-design flaw that turned out not to exist).
   - **Expected.** An explicit "no unrequested state-changing actions" rule.
6. **flight skill, Phase 5b (design-review cap).**
   - **What happened.** Cycle 2 of the flight review still raised 2 high issues. The cap
     of two forced applying them without a third review, and per-leg reviews compensated.
   - **Cost.** None observed. Recorded because the final flight text went unreviewed.
7. **agentic-workflow, Phase 2b.**
   - **What happened.** Leg 4 landed with two open items. The skill has no explicit
     "landed with follow-ups" state, so the Flight Director spawned a follow-up Developer
     before building on it.
   - **Cost.** One extra Developer cycle. It worked, but it is not described.

## Recommendations

1. **Make CDP-driven headless Chromium the documented behavior-test fallback, and add
   input-delivery probing.**
   - Each run first probes that a click reaches a capture-phase listener.
   - Concurrent runs get per-run scratch subdirectories.
   - Executors are told never to perform unrequested state-changing actions.
   - Flight 3 DD12 adopts the fallback. The rest belongs in
     `.flightops/agent-crews/behavior-tests-execution.md`.
2. **Split the `shared` lane**, for example a `contracts` lane for `test_ui_*` and
   `test_router_*`, before Flight 3 adds more dual-engine contracts. It is now about 10
   minutes and the long pole.
3. **Close the announcer/`sync` split and extend `App.store` in Flight 3.** That is DD8
   and DD9. Then document a `go`/`sync`/bypass decision guide in `agents.md`.
4. **Keep the test-first, count-based acceptance discipline.** Exact counts of frames and
   requests, and the AST guard, found real bugs and prevented churn. Flight 3 extends the
   guard to the retired selectors.
5. **Plan the studio-module split for the next mission**, where the editor internals are
   rewritten. Flight 3 deliberately extends the alias layer, with leak regressions.

## Action Items

- [x] Squawk 0111: the chat stalled-join recovery can orphan an empty session after a
  slow join (logged)
- [ ] Operator: check or restart goldfinch. Input delivery stopped working, the cause is
  unknown, and diagnosing it needs the admin window tools.
- [ ] Operator: PR #218 is mergeable (rebased onto `main` after the #217 squash). Merge it
  when ready.
- [ ] Flight 3: DD8 (announcer), DD9 (store collections), DD12 (apparatus fallback),
  and the absorbed UI items. These are already in the Flight 3 spec.
- [ ] Near term: split the `shared` browser lane (recommendation 2). This is servicing;
  schedule it with routine maintenance or as a squawk if it becomes blocking.
- [ ] Near term: update the behavior-test crew file with the per-run scratch directory,
  the no-unrequested-actions rule, and input-delivery probing (recommendation 1).
