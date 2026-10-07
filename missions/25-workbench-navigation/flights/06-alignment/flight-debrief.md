# Flight Debrief: Alignment

**Date**: 2026-10-07
**Flight**: [Alignment](flight.md)
**Status**: landed
**Duration**: 2026-10-06 – 2026-10-07 (planning, ten legs, the walk, the mission-close re-runs and this debrief)
**Legs Completed**: 10 of 10 (five were planned; leg 1 was split into 1a and 1b, and 4, 4b, 4c and 4d were added through the DD7 fix-or-feature gate)
**Plugin version**: 1.2.0

## Outcome Assessment

### Objectives Achieved

Mission 25 is closed with the operator.
- **The fix pass came first** and was reviewed and committed before the walk (`52f7612`). It cleared:
  - the carried squawks 0081, 0112–0116 and 0119–0125;
  - create-route 422s that never echo a submitted `api_key`;
  - accessible names for the Tools-tab master toggles and the info icons;
  - focus after Save, edit-mode Cancel, Test and in-place Create in six editors (`App.focusAfter`);
  - the WebSocket's one-`cancelled`-per-`cancel` and degraded-join unsubscribe;
  - the deleted-agent heal;
  - the test robustness items.
- **The operator's reports from using v0.10.0** became seven small, decided changes, each a DD:
  - "Available models" (DD10);
  - section labels as an eyebrow with a rule (DD13);
  - local 12-hour times (DD14);
  - the Agents and Library start pages (DD15);
  - a full-width composer (DD16);
  - text selection in the desktop window (DD17);
  - a plain MCP connection error under "Technical details" (DD19).

  Feature asks went to issues: #223 time tool and time zone, #224 per-message Copy, #225 narrow layouts, #226 the masked MCP cause.
- **The walk.** It was light (DD18), because the operator had already lived with v0.10.0. The verdict: "the walk looks good". DD17 was verified live on a Windows test copy. SC9 was the operator's own packaged-build answer: "All fine".
- **Mission close:**
  - the reference spec §15 register is resolved, and §13 records D6–D9;
  - seven behavior specs were re-run, all passing in both themes (147 checkpoints);
  - one more defect, unthemed bare links, was found and fixed;
  - every gate is green;
  - the published design system is updated;
  - SC1–SC10 are ticked.

### Mission Criteria Advanced

- **SC8 (matches the approved samples):** closed. §15 is resolved, and D1–D9 are operator-accepted. The evidence is the operator's v0.10.0 use plus the light walk.
- **SC9 (the window belongs to the product):** closed by the operator's packaged-app walk ("All fine", 2026-10-06).
- **SC10 (operable and regression-safe):** closed.
  - The accessible names, focus after action and the root `h1` are all done.
  - The unit suite passed 5439, all six lanes are green (contracts in Chromium and WebKit), the guards passed 362, and ruff is clean.
  - The behavior specs pass in both themes.
- **The Known Issue "Ctrl K in WebView2":** closed.
- **SC1–SC7:** re-confirmed by the mission-close behavior re-runs and gates. All ten criteria are ticked in `mission.md` with evidence.

## What Went Well

- **The DD7 fix-or-feature gate.**
  - **How it worked:** seven mid-flight operator reports were each classified out loud and recorded as a DD. Fixes became small legs with a risk tier; features became GitHub issues.
  - **What it bought:** the flight absorbed real feedback without losing its shape, and every addition has a traceable decision, often with the operator's own words.
- **Fixes first, then the walk (DD1).** The walk ran on reviewed, committed code. That is why it could be light: no surprises came from the fix pass.
- **Testid contracts (DD8, DD15).** Reshaping the Agents and Library root pages kept every testid. Test churn stayed to copy pins, and the behavior specs only needed wording re-authors.
- **"Proven by revert" tests.** Most new tests carry evidence that they fail without the fix: 0120's cancel cases, leg 4d's MCP error, the deleted-agent heal, leg 5's info icons and leg 6's link colour.
- **Concurrent behavior runs.** Seven specs ran in two batches, with:
  - live Executor and Validator pairs;
  - one instance and scratch dir per run;
  - per-run checkpoint ledgers;
  - report files handed to the Validator.

  The whole close gate took about an hour of wall time instead of four. Squawk 0121's recipe, now in the crew file, made the prompts short.
- **The behavior runs found a real defect.** Bare links rendered the browser-default blue. The flight's own unit and browser tests could not see it; a Validator judging rendered screenshots did.
- **Subagent hand-backs arrived** for every agent this flight (Flight 5's observation 1 did not recur).

## What Could Be Improved

### Process

- **DD11 and DD15 should have been decided together.**
  - Leg 1a built a visually hidden root `h1` and re-authored `list-and-detail` step 2.
  - Leg 4c then made the `h1` visible as the start page's title and re-authored the step again.
  - A start-page look at planning would have saved one build and one re-author.
- **Screenshot evidence was deferred** in legs 4, 4b, 4c and 4d. DOM and computed-style assertions stood in, and the walk was meant to show the visuals. The walk was then lightened (DD18), so for those legs the visual evidence came only from the mission-close behavior runs.
  - **The rule:** a UI leg either captures its two-theme screenshots or names the later step that will.
- **The flight log's Deviations and Anomalies sections stayed empty** during the flight. Every deviation went into Decisions or the leg entries, so this debrief had to reconstruct the deviation table.
- **The time cost of every leg's gate.** Each leg ran the unit suite (about 11–12 minutes) plus several lanes. A full sequential gate is about 53 minutes.
  - The harness's 30-minute cap on background commands cut the leg 6 unit run at 78%. That run was restarted with a longer cap.
  - Two `make down` calls also outran the 2-minute foreground limit.

### Technical

- **Helpers placed to avoid the script-count pin.** Placing a helper in an already-loaded file avoided a pin bump, but coupled modules:
  - `App.time.formatClock` lives in `app.js`;
  - `App.mcpErrorMessage` and `App.buildMcpError` live in `areas/studio/mcps-tab.js` (an agent-editor tab) but are used by the Library's `mcp-server-editor.js`.

  Both should move to their own modules (`time.js`, `mcp-error.js`), raising the pin deliberately.
- **The MCP error classifier matches strings.** It keys on the raw `"{Class}: {message}"` text and known phrases, so a new backend exception class silently gets the generic headline. Pin the class list against `the_one/mcp` by test now. Replace the matcher with a structured error code when #226 lands.
- **The WebSocket cancel bookkeeping** (`_started_tasks`, `_running_tasks`, `_cancel_tokens`, `_notify_cancelled_once`) is correct and tested, but it is module-level state in `app.py`. It wants a small cancel-registry class with a state table before a third cancel squawk arrives.
- **The create-route 422 handling** (`include_input=False`) is hand-written in two routes. A shared helper would stop an input-echo leak from reappearing in a third.
- **`App.focusAfter` call sites** are repeated across six editors (`begin`, `defer`, `flush`, `cancel`). A seventh editor can miss one. A pairing guard test would catch that. Better still, fold it into a shared editor shell (#207).
- **The global link rule.** `a:any-link { color: var(--accent); }` is a sound base-layer default: every class rule wins, and the contrast is AA on every surface (lowest 5.62:1). Its scope is still global, so future unclassed links take accent by default. That is now documented in `agents.md`.
- **The testid registry extractor** does not see a `'data-testid':` attrs key. The start pages had to use `setAttribute('data-testid', …)` literals.
- **The unit skip count flaps between 10 and 12** across this flight's gate runs on the same environment, with no skip marker added: a conditional pair (squawk 0132).

### Documentation

- **`agents.md`'s "Focus after an in-place action"** should record leg 1b's finding. An editor that re-renders on save (the agent editor) loses focus to the re-render itself, while one that patches in place (the provider editor) does not. So never-steal checks must target an element that survives the re-render.
- **The behavior specs carry wording drift** from this flight's intended changes, listed in each run log's Validator closing:
  - `system-provider-config`: the intro line, the toasts, the visually hidden "Used by", the inline test result, and the armed-state re-arm and settle;
  - `shell-navigation-smoke`: step 9's "first sample", step 4's "begins with", step 7's absent preference key;
  - `studio-agent-crud`: single-provider pre-selection, the step 8 settle time, step 9's `new-agent-btn`;
  - `list-and-detail`: step 18's Design language demo alerts.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Five legs became ten: leg 1 was split into 1a/1b, and 4, 4b, 4c and 4d were added | Leg 1 touched six editors. Then came seven operator reports, each through the DD7 gate | Yes. The gate and the DD-per-report record worked |
| The hidden root `h1` (DD11) was replaced by a visible start-page title (DD15) | The operator asked for start pages after DD11 was built | No. Decide page semantics after the operator has seen the page |
| The full ordered walk (DD6) was replaced by a light walk (DD18) | The operator had already used v0.10.0 for a day | Yes, when the operator has lived with the release. Otherwise keep the full walk |
| Squawk 0126 was absorbed into leg 4c; the same bug in `mcp-server-editor.js` was fixed alongside | Found in leg 1b, in the same editors | Yes, when the surface is shared and the fix is one line |
| Two-theme screenshots were deferred in legs 4–4d | DOM and computed-style probes stood in; the walk was meant to show the visuals | No. Name the later step that captures them, or capture them in the leg |
| A global `a:any-link` rule rather than per-site link rules | The audit found three bare-link surfaces and no reason any should be blue | Yes, as a base-layer default with class opt-outs |
| The behavior runs' armed-delete re-arm accommodation | The about-3-second armed state lapses while the Validator judges | Yes. Specs with a transient state should say so (see Methodology 1) |
| The debrief reused leg 6's gate metrics instead of a fresh full run | The gates ran minutes earlier on identical code; only docs changed since | Yes, when no code has changed since the gates |

## Key Learnings

- **An alignment flight grows by operator reports, and that is its job.** Ten legs from five was not scope creep: every addition was decided, small and traced. The cost was test time, about an hour per leg gate. A change-to-lane map would cut it.
- **Rendered-state judging catches what DOM assertions cannot.** The unthemed link passed every unit and browser test for the whole flight. One Validator looking at a Light screenshot found it.
- **Plan UI semantics after the operator sees the page.** DD11's hidden `h1` was correct to the reference spec, and moot a day later.
- **Behavior specs need to say how to handle a transient state.** The armed delete lapses in about 3 seconds. Live judging between steps cannot hold it, and a capture at 0.13 s shows a mid-transition button.

## Test Metrics

All gates ran at leg 6 with `THE_ONE_TEST_NETNS=1`, on code identical to the landing commit apart from docs.

- **Unit** (`TEST_TIMEOUT=3000 make test-unit`): **5439 passed**, 12 skipped, 1898 deselected, 0 failed, 12:01 (725 s).
  - **Against Flight 5:** 5428 passed and 10 skipped in 675 s pytest (709 s wall). That is +11 tests, +2 skips and about +50 s.
  - **Where the tests came from:** the backend work (0119, 0120, the 422s) added about 8; the rest are static pins.
  - The skip count flaps between 10 and 12 across runs, with no marker added: a conditional pair (squawk 0132).
- **Browser lanes:**

  | Lane | Result | Time | Against Flight 5 |
  |---|---|---|---|
  | `chats` | 168 | 4:30 | +5 (clock formatter, composer width, deleted-agent heal) |
  | `agents` | 153, 2 skipped | 6:16 | +19, +47 s (focus-after, root heading and start pages, MCP error) |
  | `library` | 153, 1 skipped | 8:39 | +8, +39 s (library focus, connector rename, MCP error) |
  | `settings` | 203 | 6:35 | +20, +45 s (focus-after, visible fixes, section labels, link colour) |
  | `contracts` | 672, 3 skipped | 3:01 | +26 (the focus-after contract × 2 engines, the eyebrow caption) |
  | `shared` | 465 | 12:06 | flat |

  - **Totals:** 1614 passed, 6 skipped, about 41 minutes summed (Flight 5: 1601, about 38.5).
  - **Per-test cost** is unchanged. Each lane's time grew in proportion to its tests.
  - **`shared`** is still the long pole at about 12 minutes. **`library`** is the slowest per test, at about 3.4 s.
- **Static guards:** 362 passed (3.8 s). **ruff:** clean, 528 files.
- **Flakes:** none at close, and no reruns.
  - The in-flight first-run failures were real pin misses, each fixed: the script-count pin in 1b, a settings reading-order test in 1a, two describedby pins in 5, and the testid registry in 4c.
- **Behavior:** seven specs, 147 checkpoints, all passing in both themes. One checkpoint, chat-roundtrip step 4, was INCONCLUSIVE on its first attempt from an apparatus selector and passed on re-run.
- **Trend from Flight 3 to Flight 6:** browser 1362 to 1614 (+18%), unit 5045 to 5439 (+8%). Wall time came mainly from the Flight 3 and 4 additions; Flights 5 and 6 are near flat.

## Methodology Observations

Plugin version 1.2.0 throughout.

1. **Live judging versus a transient UI state.**
   - **What the methodology did:** the behavior-test skill's Phase 4 judges each checkpoint before advancing, so the Validator can still re-observe. That is the right default.
   - **The conflict:** `studio-agent-crud` steps 8→9 and `system-provider-config` steps 9→10 depend on an armed state that lapses after about 3 s, so it always lapsed while being judged.
   - **What happened:** I ruled a re-arm accommodation (one recorded click, then confirm inside the window) four times.
   - **What it cost:** four rulings, and Validator notes asking the specs to allow it.
   - **Expected:** authoring guidance that a step depending on a time-boxed state either folds the arm and the confirm into one checkpoint, or states the re-arm.
   - **Where:** `/mission-control:behavior-test`, Phase 4 and `AUTHORING.md`.
2. **Executors adapted one variant's report from the other's text.**
   - **What happened:** twice (workbench-navigation Dark step 4, list-and-detail Dark step 3), despite a spawn-prompt rule to write each variant's report from its own observations.
   - **What it cost:** an Orchestrator instruction to judge from the variant's own evidence files. The Validators caught it, and no verdict changed.
   - **Expected:** the crew file's Executor prompt carries the rule, and the Validator prompt says to judge from the variant's own state file whatever the prose says.
   - **Where:** `/mission-control:behavior-test`, Phases 2–4; the project crew file.
3. **The flight log's Deviations section stayed empty.**
   - **What the methodology did:** the agentic-workflow skill asks for decisions in Flight Director Notes, and pivots and scope changes there too.
   - **What happened:** nothing prompted a Deviations entry when a planned DD was replaced (DD6→DD18, DD11→DD15) or legs were added.
   - **What it cost:** the debrief reconstructed the deviation table from Decisions.
   - **Expected:** a prompt in Phase 2c (leg transition) to record any deviation from the flight spec in the Deviations section.
   - **Where:** `/mission-control:agentic-workflow`, Phase 2c.
4. **The debrief's "run the full suite" step duplicated a gate run minutes old.**
   - **What happened:** the flight-debrief skill asks the Developer to run the full suite once. The mission-close gates had just run every suite on identical code.
   - **What I did:** the metrics were reused, as in Flight 5.
   - **What it cost:** nothing, but it is a deviation from the skill's text.
   - **Expected:** the skill accepts recent gate metrics on an unchanged tree.
   - **Where:** `/mission-control:flight-debrief`, Phase 2 (Developer interview).
5. **The harness's background caps met the project's long gates.**
   - **What happened:** a 30-minute background cap and a 2-minute foreground cap are harness limits, not plugin ones, against a 12-minute unit suite and a 53-minute full gate.
   - **What it cost:** one unit gate restart (about 9 minutes lost), and two `make down` calls moved to the background.
   - **Where:** `/mission-control:agentic-workflow`, Phase 2b (Developer gates). This is recorded for the sweep and is not a plugin defect.
6. **Squawk 0121's crew-file recipe paid off** (resolving Flight 5's observation 2). The behavior crew file now carries:
   - the CDP driver lifetime;
   - PID-only kills;
   - the report-file hand-off;
   - the per-run ledger.

   I still appended the protocol bullets the skill requires per spawn. The project-specific apparatus no longer needed hand-assembly.

## Recommendations

1. **Plan #207, the editor shell, as the next control-library mission.** This flight paid the duplicated-editor tax repeatedly:
   - six `App.focusAfter` call sites;
   - the same stale-title bug in two editors;
   - a re-render editor versus a patch-in-place editor with different focus behaviour;
   - about 50 section-title sites;
   - an MCP error helper living in an Agents tab file.

   A shared shell (title, breadcrumb, unsaved caption, save and cancel with focus, section titles, error blocks) would make these internal. **Critical** for the next mission in this area.
2. **Move the misplaced helpers and pin the MCP error classes.** `App.time.formatClock` goes to `time.js`, and the MCP error helpers to `mcp-error.js`, raising the script-count pin deliberately. Pin the classifier's class list against the backend exceptions by test. **Important.**
3. **Bring the behavior specs up to date with this flight's intended changes,** and add authoring guidance for transient states (Methodology 1). **Important.**
4. **Consolidate the server-side patterns:**
   - a cancel-registry class for the WebSocket's per-session cancel state;
   - one create-route `ValidationError` helper with `include_input=False`.

   **Important**: each prevents a repeat of a squawk class.
5. **Cut gate time.**
   - Split `shared` again, or run lanes in parallel on separate ports.
   - Add a change-to-lane map so a CSS-only leg does not pay the whole unit suite.
   - Record the background-cap rule (`run_in_background` with an explicit timeout above the run's length) in the crew file.

   **Minor.**

## Action Items

- [ ] Squawk 0127 (servicing): the behavior-spec wording drift from Flight 6's intended changes, plus a transient-state note for the armed delete (recommendation 3)
- [ ] Squawk 0128 (servicing): move `App.time.formatClock` to `time.js` and the MCP error helpers to `mcp-error.js`, raising the script-count pin deliberately (recommendation 2)
- [ ] Squawk 0129 (servicing): pin the MCP error classifier's class list against the backend's MCP exception classes by test (recommendation 2)
- [ ] Squawk 0130 (servicing): teach the testid registry extractor the quoted `'data-testid':` attrs key
- [ ] Squawk 0131 (servicing): `agents.md`'s focus-after section gains the re-render finding
- [ ] Squawk 0132 (servicing): identify the conditional pair behind the unit skip count's 10↔12 flap
- [ ] Mission planning: #207 as the editor-shell mission (recommendation 1); #223, #224, #225 and #226 carried as issues
- [ ] Routine maintenance: the cancel registry and the create-route 422 helper (recommendation 4); the lane split (recommendation 5)
- [ ] Merge PR #227 and release v0.10.1 (the operator's direction, 2026-10-07)
