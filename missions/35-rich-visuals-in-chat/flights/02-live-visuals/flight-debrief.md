# Flight Debrief: Live Visuals

**Date**: 2026-11-11
**Flight**: [Live Visuals](flight.md)
**Status**: landed (marked `completed` after this debrief, operator 2026-11-11)
**Duration**: 2026-11-09 (planning, `251c4d24`) - 2026-11-11 (closing commit `9d8edf9d`)
**Legs Completed**: 9 of 10 (leg 3 `widget-control` aborted before implementation and split into 3a, 4 and 5)
**Plugin version**: mission-control 1.2.3 (1.2.4 available, not installed)

## Outcome Assessment

### Objectives Achieved
Model-written HTML widgets (```` ```widget ```` blocks) now run in chat, inside a sandboxed `srcdoc` iframe behind a page-level `frame-src 'none'`, a height-only message channel identified by `event.source`, and a reviewed prelude that closes what the sandbox and policy leave open (WebRTC, WebKit history, clipboard, link preconnect and DNS prefetch, focus theft, `document.write` paths). Around it: the widget card with its marking, Pause/Restart/View source and notices; a pure `reconcile(facts)` lifecycle (run in view, pause off screen, 3 running, 8 loaded); a three-layer hang guard (crash record, stall, heartbeat); streaming with a "Rendering widget" placeholder; the widget prompt text and eval check; and a desktop pass that removes pywebview's native message handlers on Linux and macOS and clears the crash record on a clean quit. Charts debt from Flight 1 was paid down first (the `chart.js` split, `stream-commit.js`, `visual-stream.js`, measured text width).

Verification: the escape battery was silent (sink 0/0/0) in Chromium, WebKit, WebKitGTK and WebView2; the `widget-escape` behavior test passed 9/9; the desktop bridge was proven unreachable with a positive-control harness on Linux, by a frame-vs-page move probe on WebView2 157, and by the hosted macOS probe (`native_bridge=removed`, no move, no print dialog); the macOS `lifecycle` dispatch read 13 PASS; the HAT walk passed all eleven steps (two with accepted residuals).

### Mission Criteria Advanced
Assessed per the flight's "Contributing to Criteria" (Architect review, confirmed by the Flight Director against the log):

| Criterion | Result | Evidence |
|---|---|---|
| Live visuals run in the app, walled off | **met** | battery silent in four engines; `widget-escape` 9/9; HAT step 5 (sink 0/0/0, address bar unchanged, composer keeps typing); `SECURITY-MODEL.md` "Live visuals" written with its residuals |
| A visual appears when it is ready | **met** | placeholder, cut-off and too-large notices, Copy reply in flow tests; HAT steps 1 and 8 |
| Long chats stay responsive | **partly met** | caps, ceiling, pause and hang guard built and contract-tested; residuals: a small first-scroll shift per never-seen card (HAT step 4, accepted), a WebKit freeze once per busy-looping widget, Start anyway intermittently hanging in some Chromium-based hosts (accepted, documented) |
| Operators choose per agent | **met** | prompt section and hint widened; HAT step 10 |
| The prompt cost is measured and accepted | **met, with caveats** | operator gates 3-3e; visuals section 209 → 425 tokens (prompt text all-on 525 → 741); `m35f2b-*` same-prompt baselines including the first widgets set; lfm3 `no-secrets` 19/20 accepted as noise; qwen3-4b `planted-flagged` 19/20 is an eval-check gap, not a product failure |
| Visuals work in the desktop app | **partly met** | WebKitGTK (real shell) and WebView2 checked in both themes with the bridge result; WKWebView probed by the hosted run, but no chart screenshot and no widget seen animating (Reduce motion on the runner) — accepted by the operator |

## What Went Well
- **Probes before code.** The planning probes and two Architect design-review cycles found five escape paths the sandbox and CSP leave open, and all were closed on paper before implementation. No hostile-widget surprise reached the HAT.
- **A go/no-go leg first.** Leg 1 measured every engine (Playwright, WebKitGTK, WebView2, the pywebview bridge replica) and ended in an operator gate ("go with mitigations"). Every mitigation it named landed (legs 3a, 5, 8).
- **Flight 1's debrief was acted on.** Re-baseline before a prompt change (B1, squawk 0337), the `chart.js` split and shared seams (leg 2), engine checks owned by legs (legs 1 and 8), a HAT apparatus self-check (leg 9).
- **Falsification as routine.** Almost every new test in the flight was shown to fail without its fix, and the log says which were not.
- **Diagnose-only crew runs during the HAT.** When two Developers needed the same files, one diagnosed without editing while the other fixed. Measurement-first diagnosis overturned two plausible hypotheses: "our auto-scroll code" (zero writes trapped in headed Chrome) and "a stuck renderer on Start anyway" (19 clean trials in Chromium).
- **Positive-control arms.** The bridge harness (calls recorded without the removal, none with it), the frame-vs-page move on WebView2, the synthetic stale crash record on WebView2, and `kill -9` on Linux made every "unreachable" or "no notice" result meaningful.
- **The operator's live input during the HAT** narrowed each defect fast ("scrolling over the frame counter", "smooth after brute-force scrolling to the top", the pasted pendulum source).

## What Could Be Improved

### Process
- **Every probe and test ran headless and in-process.** The HAT then found three real-browser defects the crew could not see: Chrome's scroll anchoring under a smooth wheel (first-load slot height changes above the viewport), Chromium site isolation giving a sandboxed frame 0 width at script start (canvas widgets blank until Restart), and scrollbars from a model's `width:100%` + border CSS. Flight 1's debrief had already warned that "only the real app showed" a layout defect. A crew-run headed pass with real model output and site isolation should precede the HAT for any frame, scroll or layout work.
- **Leg 7 became a mini-flight.** Ten sub-parts (A1, B1, A2, B2, A2'-A2''', B2'-B2''') with five operator gates; each n=20 round cost about two hours of local model time. There was no stated stop rule for prompt-text iteration, and DD15's must-mention list did not anticipate the fenced-example, copying and canvas-colour problems.
- **The leg's "quota only on committed code" rule** was relaxed for A2'-A2''' (operator choice to iterate in the tree); it held only because the final measured text was committed unchanged.
- **A Windows/macOS AC cannot be met autonomously.** Leg 8's AC6 and AC11 depended on a real desktop and a hosted runner and ended partial; the spec should have marked them operator-gated from the start.
- **The closing browser gate was skipped** (operator decision, 2026-11-11). The full browser tier last ran green at the Flight 1 close (`PARALLEL_RESULT rc=0 total=2163s lanes=17`); since then 114 files changed, including shared CSS, `index.html`, `app.py` and the transcript. Only the widget lanes ran at the close.
- **Doc drift after a DD amendment** (CLAUDE.md still said `srcdoc` before insertion; the `chats-widgets` lane listed one file instead of four) was caught only by the Flight Director's Phase 3 check.

### Technical
- **Residuals accumulate** in `SECURITY-MODEL.md` "Live visuals": a WebKit freeze once per bad widget, Start anyway in some Chromium hosts, the crash record needing working storage, the bridge removal's cost (`window.print()` on macOS, `alert` on GTK), unknown engine APIs. Acceptable for a single-user local app, but they warrant a periodic review.
- **The prelude is a security-critical blob** in a 674-line JS file, pinned by exact text. The pin is a strength; a plain source file unit-tested under node and embedded at build would be easier to review.
- **Module size:** `widget-frame.js` 674 lines, `transcript.js` 667 (+~230 this flight), `widget.js` 535, `widget-lifecycle.js` 501; `tests/browser/test_ui_widget_lifecycle_contract.py` 852 lines (a lane-budget risk).
- **The armed-load rule relies on engines firing the initial about:blank load synchronously at insertion;** the contract test is the guard, and the comment says so.
- **The isolated-Chromium regression test skips** when that Chromium cannot launch or the probe shows no early 0 width, so in CI it can become a silent no-op.
- **Small local models never write widgets** (qwen3-4b reached 20/20 only after the fenced example; lfm3 1-3/20). The feature effectively serves Haiku-class models.

### Documentation
- A named convention for the armed-srcdoc insertion order in `the_one/agents.md` "Project Conventions".
- The HAT apparatus (seed scripts in the session scratchpad `hat/`, the model widget sources in `step9/`) is not in the repo; the next widget HAT would rebuild it.
- The four widget lanes' budgets are provisional (`contracts-widget` 300 s, `contracts-widget-lifecycle` 300 s, `chats-widgets` 240 s with four files now, and `chats-transcript` already over budget at the Flight 1 close).

## Test Metrics
- **Fresh unit run at the debrief** (Developer, `THE_ONE_TEST_NETNS=1 make test-unit` on `9d8edf9d`): 9769 passed, 15 skipped (the expected netns count), 4649 deselected, **248.85 s**. Neither known unrelated failure appeared (`test_cached_no_auth_posture_still_takes_the_branch_and_keeps_its_posture` passed; the order-dependent `test_evals_fingerprint` case did not fail).
- **Closing fix pass** (final code; only a docs commit since): unit 9769 / 15; `contracts-widget` 156 passed, 2 skipped (the Chromium-only focus-steal tests under WebKit); `contracts-widget-lifecycle` 113; `chats-widgets` 25 (the isolated-Chromium test ran).
- **Against Flight 1's closing gate** (`8f20d378`): unit 9642 / 15 in 256 s → 9769 / 15 in 249 s (+127 tests, about 3% faster). The browser total is not comparable: no full gate ran this flight.
- **New lanes this flight:** `contracts-widget`, `contracts-widget-lifecycle`, `chats-widgets` (twenty lanes in all). None has a quiet-host `--parallel 3` reading yet.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Leg 3 `widget-control` aborted before implementation, split into 3a/4/5 | too large for one leg once the leg 1 gate added the focus gate, link blocking and pause | yes: split at design review when a leg carries more than one surface |
| DD2 amended at the HAT: insert sandboxed, read width, arm, then `srcdoc` | Chromium site isolation gives the frame 0 width at script start | yes, as the frame insertion convention |
| Pre-measure (a DD7 amendment) designed, reviewed and dropped for a lighter fix | the review found four high issues and a security cost (a hostile history widget runs on chat open) | no; keep DD7, revisit only if long unseen-widget chats matter |
| Cocoa `browserDelegate` removed with `jsBridge` | a widget could open a print dialog; the app never prints | n/a |
| macOS check added to the existing `probe` mode, not a new mode | a new mode needs a stub on `main` first | yes, for observation-only hosted checks |
| Squawk 0343 committed on the flight branch, not a squawk branch | a leg was live in the same working tree | yes, when a leg is live in the tree |
| Prompt iterated in the working tree before commit (A2'-A2''') | the operator chose to iterate | no: commit each measured text, or state the exception up front |
| Closing browser gate skipped | operator decision | no |
| The other session's notes-layer edit kept out of `C3` and left uncommitted | not this flight's work; it changes platform prompt text | n/a: settle before merge |

## Key Learnings
- **A sandboxed frame's behaviour depends on the browser's process model.** Under site isolation the frame learns its size only at its first animation frame. Test frame-layout behaviour under `--site-per-process --enable-features=IsolateSandboxedIframes`, not only in Playwright's default in-process mode.
- **Scroll stability needs real smooth scrolling to observe.** Headless instant scrolling hid Chrome's anchoring compensation; structural slot-height tests (every slot-height change recorded) are the deterministic guard.
- **Model-written widgets size themselves from layout at start** (`canvas.width = canvas.offsetWidth`) and use `width:100%` with borders. A corpus of real model widgets is a better regression net than synthetic canvases.
- **Prompt examples get copied.** The counter example was returned verbatim by qwen3-4b; a bare skeleton (`/* draw */`) was not copied. Canvas colour needed an explicit `getPropertyValue` example; `var(--…)` in JS is a syntax error the structural eval check passes.
- **Measure before fixing in a HAT.** Two of four plausible hypotheses were wrong.
- **A per-host residual (Goldfinch) can be real and unreproducible in the lab;** record the host and the decision rather than chase it.

## Methodology Observations
1. **Agentic workflow, Phase 2a (risk-tiering) and the HAT leg, plugin 1.2.3.** The method has no step that runs the feature in a headed real browser with realistic content before the human walk. The HAT found three defects (scroll anchoring, 0-width isolated frame, scrollbars) that every autonomous leg's headless tests passed. Cost: four HAT fix rounds, two design detours (pre-measure), about four extra hours of operator time. Expected: a crew-run "real-browser smoke" leg or HAT pre-step for UI flights touching iframes, scroll or layout, with real model output.
2. **Agentic workflow, operator-gated parts inside one leg, plugin 1.2.3.** Leg 7 (ten sub-parts, five gates) and leg 8 (autonomous Linux, operator Windows, outward macOS) were run as single legs with A/B/C parts. The skill's leg model (design → implement → land) does not describe gated multi-part legs; the Flight Director improvised the structure, the commit points and the review placement each time. Flight 1's debrief asked for the same pattern.
3. **Agentic workflow, Phase 3 documentation check, plugin 1.2.3.** A DD amended at the HAT left CLAUDE.md describing the old behaviour until the Flight Director's Phase 3 check. Expected: the HAT fix-vs-feature gate (or any DD amendment) carries a "grep the docs for the old wording" step.
4. **Squawk skill, branch step, plugin 1.2.3.** The squawk verb requires a `squawk/{id}` branch, which is impossible while a leg is live in the shared working tree; the squawk was committed on the flight branch and its PR folded into the flight's. Expected: the skill names the mid-flight case.
5. **Flight debrief crew file, test metrics (project rule), plugin 1.2.3.** The rule "reuse the flight's gate, else run fresh" assumes a gate exists; when the operator skipped it, the debrief could only run the unit tier (the operator's decision stands), so the browser-tier comparison has no data point for this flight.
6. **Agentic workflow, crew parallelism in one tree, plugin 1.2.3.** Running two Developers on the same files needed ad-hoc "diagnose only, wait for the other" messages; it worked, but the skill has no guidance for overlapping HAT fixes.

## Recommendations
1. **Add a crew-run real-browser pass before every UI HAT** that touches frames, scrolling or layout: headed Chrome with site isolation and smooth wheel scrolling, real model output from the target models, and the HAT seed apparatus. (Critical: it would have prevented the HAT's four fix rounds.)
2. **Run `make gate` once before this branch merges, and re-budget the widget lanes from that quiet run** (`contracts-widget`, `contracts-widget-lifecycle`, `chats-widgets`, `chats-transcript`), updating CLAUDE.md's table and `scripts/run-tests.sh` together. The browser tier is a flight old against 114 changed files.
3. **Promote the real model widgets** (the HAT's pendulum, bouncing balls, calculator and the operator's checkers game, if available) into `tests/fixtures/widgets/` with a corpus test asserting paint, no scrollbars and a non-zero size at start, in Chromium (isolated) and WebKit.
4. **Make the isolated-Chromium test loud:** fail instead of skip under a require flag (as `THE_ONE_REQUIRE_WEBKIT` does for WebKit).
5. **Give prompt-iteration legs a stop rule** (a round budget and a "good enough" bar per model) and commit each measured text before its runs.

## Action Items
- [ ] Settle the other session's uncommitted `the_one/db/_notes.py`, `tests/test_prompt_layers.py`, `tests/behavior/agent-notes-round-trip.md` (and `env.sh`) before merge; the notes change needs its own eval against `m35f2b-platform`.
- [ ] Run `make gate` on a quiet host before merge and re-budget the four widget lanes (recommendation 2).
- [x] Squawks logged (Phase 6, operator confirmed): [0345](../../../../squawks/0345-eval-untrusted-note-positional-args.md) the `notes_from_untrusted_flagged` positional-args gap; [0346](../../../../squawks/0346-evals-fingerprint-test-order.md) the order-dependent `test_evals_fingerprint` failure after `test_prompt_layers.py`; [0347](../../../../squawks/0347-windows-test-copy-dev-mode-relaunch.md) `windows_test_copy.py launch` dropping `THE_ONE_DEV_MODE` and refusing to relaunch while the previous watchdog lives; [0348](../../../../squawks/0348-isolated-chromium-test-silent-skip.md) the isolated-Chromium test's silent skip. The MCP consent-timeout test failure seen during the flight is already [0344](../../../../squawks/0344-mcp-cached-no-auth-test-consent-timeout.md).
- [ ] Mission follow-ups (not squawks): Copy source, Expand, Download/save and pop-out; Pause also blocking input (operator: accepted for now); a `transcript.js` split; a macOS probe that scrolls the chart into view and reads `reduceMotion`; a WebView2 check with a canvas sized at start.
- [ ] Debrief notes carried from the flight: load one local model at a time for evals (`OLLAMA_MAX_LOADED_MODELS=1` or a CLAUDE.md rule); `run --resume` needs the scenario set restated; lfm3 `notes-proactive` bimodal across runs.
