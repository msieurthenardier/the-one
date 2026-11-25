# Flight Debrief: The remaining kinds

**Date**: 2026-11-24
**Flight**: [The remaining kinds](flight.md)
**Status**: landed. It was marked completed after this debrief (operator, 2026-11-24).
**Duration**: 2026-11-23 - 2026-11-24
**Legs Completed**: 10 of 10 (01a, 01b, 02, 03a, 03b, 04a, 04b, 05, 06, 07)
**Plugin version**: mission-control 1.2.4

## Outcome Assessment

### Objectives Achieved
GleepGlorp now fills and proposes for the four remaining kinds, built on Flight 4's registry.
- **Knowledge bases:** create by fill, and rename by proposal with the agent tool-name carry.
- **Library secrets' metadata:** name, description and allowed tools. Values stay operator-only.
- **Built-in tool configs:** ordinary fields only. Paths, hosts, keys and the sandbox stay
  operator-only.
- **App settings:** Date and time takes proposals only; Knowledge indexing takes fills and
  proposals.

Each kind has:
- a write service, with the read and write in one transaction;
- outside-value guarding on its fields;
- an editor seam with fill and follow notes (the Date and time follow reaches every window);
- guide topics, and unit and browser tests.

**Supporting work:**
- `Kind` registry hooks replaced the per-kind branches;
- shared client fill and follow cores;
- squawks 0400, 0382, 0401, 0402 and 0406 completed;
- the GleepGlorp lane split into three lanes;
- `fill_form` reworded kind-neutral (89 to 82 tokens);
- ten new eval scenarios.

**Checks:**
- The operator's HAT passed 9 of 9 steps, with no fix needed.
- The quiet-host closing gate passed.
- PR #385 (draft).

### Mission Criteria Advanced
- **GleepGlorp fills the form; the operator saves it.** It now covers knowledge bases, secret
  metadata, tool configs and Knowledge indexing.
- **GleepGlorp proposes; the operator approves.** It now covers all nine kinds, including Date and
  time, which takes proposals only.
- **Secrets never pass through GleepGlorp.**
  - Secret values, API keys and the operator-only tool fields are refused by code.
  - The exit-1 fix routes `value`, `key`, `secret` and `secret_value` to the values refusal.
  - *Not fully met in model behaviour:* Haiku still repeats a pasted secret value in its handoff
    (6 of 20 at the last measurement). The value is never stored or filled. The operator accepted
    this for now, because the value is already in the transcript (DD15 known gap); it is carried
    to alignment.
- **GleepGlorp sticks to the app.** The outside-value guard covers the new `address_or_command`
  fields (`searxng_base_url`, `google_pse_cse_id`). The eval tripwire for it passed 20 of 20.
- **Quality is measured on every default eval model.**
  - Haiku: one n=20 round on the ten new scenarios, plus a 40-run re-run after the fixes.
  - qwen3-4b: measured.
  - No baseline was recorded, by operator decision (DD12). The baseline belongs to alignment.

## What Went Well
- **The Flight 4 recommendations paid off** (Architect).
  - The `Kind` hooks and the shared client cores let four kinds land without touching the
    proposal or fill loop.
  - The five existing kinds stayed byte-identical. That was proven with before and after captures
    of `describe()` and the views, a pattern worth naming: "capture before, diff after".
  - `provider-editor.js` went from 894 to 628 lines.
- **Dependent legs were designed after their predecessor landed** (Flight 4 recommendation 4).
  Leg 1a recorded four DD2 refinements made against landed code, and the 3a/3b and 4a/4b
  server-then-client pairs kept each review tractable.
- **The pre-named exits and the stop-on-safety read worked.**
  - Every one of the 13 failing Haiku safety transcripts was read before a number was recorded.
  - The operator chose exits in minutes, and none was improvised.
  - The reading also found a check false negative (`secret-create-fill` f2p3).
- **FD probes of the safety regexes before any quota was spent.** The no-claim exemption was
  first too narrow, then too broad, then too broad again in the exit-1 fix. Each time, lie
  sentences the Developer had not seen caught it, before quota or a commit.
- **Investigation before accepting a "load flake."** The `gleepglorp-chat` failures (7 of 9 runs)
  were not waved through. A worktree comparison against `fbf11634` found a pre-existing router
  race in the test harness (squawk 0406). After the fix, the lane passed 3 of 3 alone and again
  in the gate.
- **Falsification discipline was consistent.** Nearly every new safety, race and contract test
  was shown to fail with its fix removed (the flight log lists them per leg).
- **The HAT's second-window step** (Date and time followed in a window the operator wasn't
  looking at) passed first time. So did the dirty-editor follow (step 5).

## What Could Be Improved

### Process
- **The FD spoiled a verification run.** The Leg 4b Developer was spawned while Leg 4a's lanes
  were running. Its static JS edits were served to those lanes, and the run had to be recorded as
  inconclusive. The rule adopted mid-flight: no crew edits the tree while a recorded verification
  run is in progress.
- **A Developer landed before its gates finished** (Leg 4a). The FD ran the lanes itself. Later
  crew prompts said "do not signal `[LAND:leg]` until every gate run has finished and you have
  read its result", and the problem did not recur.
- **Crew hygiene recurred.**
  - Self-matching `pgrep -f` wait loops (the same class as Flight 4).
  - A log file left in the home folder.
  - Leg 2's Developer skipped the squawk 0334 sweep, so the FD ran it.
- **Eval quota needed three operator decisions:** the round's scope, the exit after round 1,
  and the exit after the re-run. The operator has since given standing permission for small
  exit-1 re-runs; see Recommendations.

### Technical
- **The unit tier is 466-470 s, against its 350 s target** (squawk 0403, now 33% over). This
  flight added 451 tests and about 82 s. That is about 0.18 s per test, against about 0.034 s per
  test across Flights 1-4, and the readings were already high in Legs 1a and 1b (429 s and 495 s).
  So per-test setup cost is a likelier cause than volume. The Developer's suspects, not yet
  verified:
  - the new eval test files;
  - the race-heavy service tests;
  - the static guards scanning a JS tree that grew by about 30 modules.
- **`keepFocus`** (`static/js/areas/admin/tools-page.js:20` and `:150-156`, set in
  `tool-config-kinds.js:43-44`) is a module-level flag. It is cleared only if `afterNavigate`
  runs, so a throw in between would suppress focus for later real navigations. Its race has no
  test.
- **`tests/browser/_drawer.py` router helpers** (squawk 0406's fix):
  - `wait_router_started` runs twice in a row on the `boot()` path;
  - the helpers live outside `_nav.py`, which is the navigation home.
- **No-claim patterns are copied across ten scenario TOMLs**, so a fix has to be made ten times.
  The tests in `tests/test_evals_gleepglorp_fixes.py` are the net.
- **Refusal declarations on `Kind`** now come in four forms: `operator_only`,
  `operator_only_message`, `operator_only_aliases` and `fill_refused`/`action_refused`. They are
  candidates for one `Refusal` declaration.
- **Adding a kind is mechanical.** It takes three or four client files per kind (`*-fill`,
  `*-controller`, the kinds file, the registry entry) on top of the server kind and its service.
- **Not re-measured:** the field-list fix (`cfd77095`), by operator decision. Alignment inherits
  an unmeasured change to `secret-create-fill`.

### Documentation
- **The `agents.md` "Kind registry contract"** covers the server hooks only. There is no
  "adding a kind" walkthrough listing every file: server kind, service, client fill, controller
  and kinds files, guide page, eval cells, lane glob.
- **The flight log's top-level Deviations and Anomalies** read "(none yet)" until this debrief
  filled them in, although the leg sections recorded both.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| `ui/field.js` `wire()` fixed at its root (Batch C) | The accessibility review: `setError`/`setHint` dropped the note's `aria-describedby` link on every form | yes: fix shared-control defects at the control, then run the full browser suite |
| Squawk 0406 fixed in-flight as grounding | The lane gates the flight; the harness raced the router | yes |
| DD11 figures stale at Leg 5 (`propose_change` 114/120, not 83) | Earlier legs appended provisional kind names | yes: mark planned figures "re-measure at the leg" |
| DD12's warning cells dropped; a tenth scenario added | A `propose_change` reply carries no warning; the design review found an outside-value gap | no (case-specific) |
| `Kind.operator_only_aliases` added at Leg 6 | Haiku sent `value`; only `values` was operator-only | yes: enumerate likely aliases per operator-only field at design |
| Debrief test metrics: fresh unit run plus the gate's browser numbers | The project rule counts a docs-only `agents.md` change (squawk 0405) | see squawk 0405 |

## Key Learnings
- **Tool-result text does not override the prompt's repeat behaviour.** Haiku was refused with
  "I never take, fill or repeat one" and still repeated the value in its handoff (8 of 20, then
  6 of 20). That is evidence for code-level reply handling of the hard lines at alignment, as
  Flight 4 recommendation 1 suggested.
- **Replacing a generic refusal can lose information the model was using.** The generic shape
  refusal listed "Allowed fields". The specific values refusal did not, so successful fills fell
  from 15 to 7. Check what a refusal's wording does for the model's next call, not only that it
  refuses.
- **A safety regex needs a must-fail lie corpus written at design time,** next to the
  honest-reply tests. Every exemption widening in this flight was caught by lies, not by
  honest-reply tests.
- **A click gate is only as strong as what the card shows.** At HAT step 4, the operator approved
  a proposal that silently dropped `http_request`, because the card shows the whole new list
  without marking removals. The operator judged a card diff not needed (2026-11-24). It is
  recorded here as an observation, not a recommendation.
- **Provisional lane budgets set before measuring were off by 2x.** `gleepglorp-kinds` was set at
  210 s and measured 352 s once four kinds landed. A provisional budget should be marked as such
  and re-measured at the gate, as this flight did.

## Test Metrics

Sources: the **browser** numbers are the closing gate at `679ed850` (quiet host, load 0.57,
`--parallel 3`). The **unit** numbers are a fresh debrief run (load 0.34) and the gate's unit
tier, which agree.

- **Unit:** 12349 passed, 15 skipped (expected under netns), 5049 deselected, 0 failed.
  - Debrief run: 466.18 s. Gate: 470.19 s. No flake and no drift.
  - Trend: F1 10695 / 309 s; F2 11031 / 344 s; F3 11331 / 381 s (loaded); F4 11898 / 384-387 s;
    **F5 12349 / 466-470 s.**
- **Browser:** `PARALLEL_RESULT rc=0 total=2736s lanes=23 failed=-`.
  - Against F4's 2616 s on 21 lanes, that is +120 s (+4.6%), with two more lanes from the split:
    flat like-for-like.
  - The critical path is `routing` 654 s, `agents` 615 s and `agent-tabs` 609 s, none of them
    GleepGlorp's.
- **The GleepGlorp split:**
  - Before: one lane, 167 tests in 478 s alone.
  - After, in the gate: `gleepglorp-chat` 243 s, `gleepglorp-fill` 145 s, `gleepglorp-kinds`
    352 s.
  - `gleepglorp-kinds` grows about 25 s per kind and is the lane to watch.
- **Re-budgeted:** `gleepglorp-kinds` 210 to 450 s and `settings` 360 to 480 s. The other two
  GleepGlorp lanes' provisional budgets (330 s and 210 s) were confirmed.
- **Gate length:** about 53.5 min against the 43-minute target, the mission's longest (F4 was
  50:46).
- **Flakes:** none on the quiet gate. In-flight, under load: `gleepglorp-chat` (squawk 0406,
  fixed); `test_hash_routing_settings_nav_pushes_history` and the provider dirty-guard test,
  once each, which passed alone and on the quiet gate.

## Methodology Observations
1. **agentic-workflow, Phase 2b, plugin 1.2.4.**
   - **What happened:** the skill spawns the next leg's Developer as soon as the previous one
     lands. Here the FD was still running the landed leg's verification lanes on the same tree,
     and the new Developer's static JS edits were served to them.
   - **What was expected:** guidance not to start implementation on a shared tree while a
     recorded verification run is in progress.
   - **What it cost:** one inconclusive `gleepglorp-chat` run, re-proven later. The FD added the
     rule by hand.
2. **agentic-workflow, Phase 2b, plugin 1.2.4.**
   - **What happened:** the Leg 4a Developer signalled `[LAND:leg]` with its unit run unfinished
     and its browser lanes not run.
   - **What was expected:** that the Implement prompt forbids landing before every gate run has
     finished and been read.
   - **What it cost:** about 20 minutes of FD-run lanes. The FD's added wording fixed it for
     later legs.
3. **agentic-workflow, the operator-gated eval leg, plugin 1.2.4.**
   - **What happened:** the skill has no shape for a quota leg: no gates, no standing quota
     authority, no record format.
   - **What it cost:** the FD modelled one on Flight 4 Leg 7. It took three operator round-trips
     for a single round, and standing permission for small re-runs was only settled at the
     debrief.
4. **flight-debrief, test metrics, plugin 1.2.4** (the project crew rule; second occurrence,
   squawk 0405).
   - **What happened:** the "reuse the flight's gate" rule forced a fresh unit run because the
     only non-artifact change since the gate was a docs-only `the_one/agents.md` edit plus the
     budget table.
   - **What it cost:** about 8 minutes. The numbers were identical to the gate (12349 passed and
     15 skipped, both times).
5. **flight, Phase 5 citation audit, plugin 1.2.4.**
   - **What happened:** DD11 recorded token figures at planning (`propose_change` 83/120). The
     flight's own earlier legs then changed them, so the figure was stale by Leg 5, which
     depended on it.
   - **What was expected:** that figures intermediate legs will move are marked "re-measure at
     the leg".
   - **What it cost:** a survey round at Leg 5 to re-establish them. No wrong code resulted.

## Recommendations
1. **Alignment flight: re-measure first, then tune.** Re-measure `secret-create-fill` (the
   field-list fix `cfd77095` was never measured) and `secret-widen-propose`. Then take the exit-2
   items:
   - the value repeat (Haiku 6/20, qwen3-4b 12/20);
   - the "Done!" and "I've set up" claims (two cells at 19/20);
   - proposing instead of filling in the drawer;
   - the pasted-Brave-key refusal;
   - `read_app_config kind=tool_config`;
   - the dropped allowed-tool on a widen;
   - qwen3-4b's tool discovery.

   Since tool-result text did not stop the repeat, try code-level reply handling for the hard
   lines. Decide where eval run evidence lives, because `evals/runs/` is uncommitted.
2. **Standing eval authority for alignment** (operator, 2026-11-24). The FD may re-run only the
   failing scenarios after a reviewed exit-1 fix, up to about 40 Haiku runs, and report
   afterwards. New rounds and anything larger still go to the operator.
3. **Profile the unit tier before alignment adds tests** (squawk 0403). Run `pytest
   --durations=50`, find the per-test setup cost behind 0.18 s per test, then fix it or restate
   the 350 s target.
4. **Safety-regex hygiene as a design rule.** Every no-claim or not-repeated safety cell ships
   with a must-fail lie corpus, alongside the honest-reply tests. The FD probes it before quota.
   Consider one shared pattern definition instead of ten copies.
5. **Enumerate operator-only aliases per kind at design.** Add a per-kind test that every
   singular, plural and synonym name a model might use (`value`, `key`, `secret`) is refused
   with the specific sentence.

## Action Items
- [ ] **Alignment flight planning:** Recommendations 1 and 2, re-measure first.
- [ ] **Squawk 0403:** profile the unit tier.
- [ ] **Squawk 0405:** exempt `the_one/agents.md` (docs) from the debrief's fresh-run trigger.
- [ ] **Squawk 0407:** a replaced proposal's card keeps its buttons.
- [ ] **`agents.md`:** an "adding a kind" walkthrough listing every file, and the "capture
  before, diff after" refactor convention.
- [ ] **Small follow-ups, logged as squawks (operator, 2026-11-24):**
  - **squawk 0408:** `keepFocus` cleared on every exit of a fill's navigation;
  - **squawk 0409:** the router-wait helpers moved to `_nav.py`, with the duplicate wait
    dropped;
  - **squawk 0410:** crew-prompt lines on the `pgrep -f` self-match and on keeping logs in the
    scratchpad.
